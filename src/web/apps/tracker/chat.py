"""A chat panel that talks to Claude Code running headless (prototype, branch `chat-panel`).

No API key and no SDK: each message spawns `claude -p` as a subprocess, so it runs on
whatever account the terminal's `claude` is logged into, and sees what a terminal
session sees — this repo's CLAUDE.md and `.claude/skills/` (the cwd is the repo root),
the user's global ~/.claude config and memory, and the data root via `--add-dir`.

One subprocess per turn, chained with `--resume <session_id>`: the session lives in
Claude Code's own transcript store, so the conversation survives a page change, a
server restart, and can be picked up in the terminal with `claude --resume <id>`.

The output is `stream-json`, which this view boils down to a handful of event types
and passes on as NDJSON, one object per line:

    {"t": "session", "id": "..."}            once, as soon as the session is known
    {"t": "text", "d": "..."}                a chunk of the reply
    {"t": "tool", "name": "...", "d": "..."} a tool call, with a one-line summary
    {"t": "html", "d": "..."}                the whole reply, rendered like the site's markdown
    {"t": "denied", "items": [...]}          tool calls refused for want of a permission
    {"t": "usage", "context": n, "window": n, "cost": 0.12}   context size after the turn
    {"t": "limits", "five_hour": {...}, "seven_day": {...}}  plan usage, as `/usage` shows it
    {"t": "done", "cost": 0.12, "ms": 3400}  the turn finished
    {"t": "error", "d": "..."}               something went wrong

Headless Claude cannot ask for permission, so anything not already allowed by the
settings files is refused rather than prompted. `CHAT_PERMISSION_MODE` (default
`acceptEdits`) decides how much it may do without asking. What it was refused comes
back as `denied`, each with the rule that would allow it; the panel offers to allow
it, and sends the rules it has collected with every later turn as `allow` — they last
as long as the conversation in the panel, and are never written to a settings file.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.http import HttpResponseNotAllowed, JsonResponse, StreamingHttpResponse

from .templatetags.jobs_extras import markdownify

REPO_ROOT = Path(__file__).resolve().parents[4]
PERMISSION_MODE = getattr(settings, "CHAT_PERMISSION_MODE", "acceptEdits")

# Appended to Claude Code's system prompt on every turn. The URL guide is there because
# the page path is all the panel sends, and without it Claude read /applications/66/ as
# database id 66 rather than application number 66.
SYSTEM_NOTE = """\
This session is driven from the Job Studio web app's chat panel. <DATA> is already
resolved: {data}. There is no terminal: nobody can approve a permission prompt, so
prefer tools that are already allowed; if one is refused, say what you needed and stop,
and the user can allow it from the panel.

Each message says which page of the app the user is viewing. The app's URLs:
/applications/<num>/ is the application with that number (Application.num, the NNN-
prefix of its folder under <DATA>/jobs/applications/), never the database id;
/applications/<num>/rounds/<anchor>/ is one interview round in it;
/companies/<slug>/ is <DATA>/jobs/companies/<slug>.md; /notes/<slug>/ a file under
<DATA>/jobs/notes/; /scans/<slug>/ a report under <DATA>/jobs/scans/; /cvs/ the CVs
under <DATA>/jobs/cv/; /profile/ <DATA>/jobs/profile/."""


def _rule(name: str, args: dict) -> str:
    """the narrowest permission rule that allows this one call."""
    if name == "Bash" and args.get("command"):
        return f"Bash({args['command']})"
    if name in ("Read", "Edit", "Write") and args.get("file_path"):
        # `//` marks an absolute path in a permission rule; a single `/` would be read
        # relative to the settings file.
        return f"{name}(/{args['file_path']})"
    if name == "WebFetch" and args.get("url"):
        host = args["url"].split("//", 1)[-1].split("/", 1)[0]
        return f"WebFetch(domain:{host})"
    return name


def _tool_summary(name: str, args: dict) -> str:
    """one line for a tool call: the argument that says what it is doing."""
    for key in ("command", "file_path", "pattern", "skill", "url", "query", "description"):
        if args.get(key):
            return str(args[key]).splitlines()[0][:160]
    return ""


def _usage(result: dict) -> dict:
    """how full the context is after this turn, and what the turn would cost on the API.

    The context is the size of the turn's last API call (input, cache read and cache
    written, plus what it wrote): that is what the next turn starts from. The cost is
    `total_cost_usd`, an API-price equivalent, not a charge on a subscription.
    """
    usage = result.get("usage") or {}
    last = (usage.get("iterations") or [usage])[-1]
    context = sum(last.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens",
                                             "cache_creation_input_tokens", "output_tokens"))
    windows = [m.get("contextWindow") for m in (result.get("modelUsage") or {}).values()]
    return {"t": "usage", "context": context, "window": max(filter(None, windows), default=None),
            "cost": result.get("total_cost_usd")}


def _events(proc):
    """translate Claude Code's stream-json into the panel's event lines."""
    sent_session = False
    reply = []
    fresh = False
    for raw in proc.stdout:
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        sid = msg.get("session_id")
        if sid and not sent_session:
            sent_session = True
            yield {"t": "session", "id": sid}
        kind = msg.get("type")
        # Top-level text only: a subagent's stream carries a parent_tool_use_id.
        if kind == "stream_event" and not msg.get("parent_tool_use_id"):
            ev = msg["event"]
            delta = ev.get("delta", {})
            if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                text = delta["text"]
                # A new assistant message starts a fresh paragraph — but only once it
                # has text: most messages mid-task are a bare tool call, and a break
                # for each of those stacked up as blank space in the reply.
                if fresh and reply:
                    text = "\n\n" + text.lstrip("\n")
                fresh = False
                reply.append(text)
                yield {"t": "text", "d": text}
            elif ev.get("type") == "message_start":
                fresh = True
        elif kind == "assistant":
            for block in msg["message"].get("content", []):
                if block.get("type") == "tool_use":
                    yield {"t": "tool", "name": block["name"],
                           "d": _tool_summary(block["name"], block.get("input", {}))}
        elif kind == "rate_limit_event":
            windows = msg.get("rate_limit_info", {}).get("unifiedWindows") or {}
            yield {"t": "limits", **{
                name: {"pct": round(w.get("utilization", 0) * 100), "resets": w.get("resetsAt")}
                for name, w in windows.items()}}
        elif kind == "result":
            yield _usage(msg)
            text = "".join(reply).strip()
            if text:
                yield {"t": "html", "d": str(markdownify(text))}
            denied = [{"name": d["tool_name"],
                       "d": _tool_summary(d["tool_name"], d.get("tool_input", {})),
                       "rule": _rule(d["tool_name"], d.get("tool_input", {}))}
                      for d in msg.get("permission_denials") or []]
            if denied:
                yield {"t": "denied", "items": denied}
            if msg.get("is_error"):
                yield {"t": "error", "d": msg.get("result") or msg.get("subtype", "error")}
            yield {"t": "done", "cost": msg.get("total_cost_usd"), "ms": msg.get("duration_ms")}


def _stream(cmd, prompt, env):
    proc = subprocess.Popen(cmd, cwd=REPO_ROOT, env=env, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    proc.stdin.write(prompt)
    proc.stdin.close()
    try:
        for ev in _events(proc):
            yield json.dumps(ev) + "\n"
        proc.wait()
        if proc.returncode:
            err = proc.stderr.read().strip()[-500:]
            yield json.dumps({"t": "error", "d": err or f"claude exited {proc.returncode}"}) + "\n"
    finally:
        # The browser went away mid-turn (closed the panel, reloaded): stop the run.
        if proc.poll() is None:
            proc.terminate()


def chat_send(request):
    """POST `message`, optional `session` (to continue), `page` (the URL being viewed)
    and any number of `allow` (permission rules the user granted from the panel)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    # This hands a shell-capable agent to whoever can reach the server: loopback only.
    if request.META.get("REMOTE_ADDR") not in ("127.0.0.1", "::1"):
        return JsonResponse({"ok": False, "error": "local only"}, status=403)
    message = request.POST.get("message", "").strip()
    if not message:
        return JsonResponse({"ok": False, "error": "empty message"}, status=400)
    claude = shutil.which("claude")
    if not claude:
        return JsonResponse({"ok": False, "error": "`claude` is not on the server's PATH"}, status=500)

    session = request.POST.get("session", "").strip()
    page = request.POST.get("page", "").strip()
    prompt = message
    if page:
        prompt = f"[Sent from the Job Studio web app; the user is viewing {page}]\n\n{message}"

    cmd = [claude, "-p", "--output-format", "stream-json", "--verbose",
           "--include-partial-messages", "--permission-mode", PERMISSION_MODE,
           "--add-dir", str(settings.DATA_ROOT),
           # The server has already resolved <DATA>; saying so spares a lookup that a
           # headless run would need a permission for and cannot ask for.
           "--append-system-prompt", SYSTEM_NOTE.format(data=settings.DATA_ROOT),
           "--allowedTools", "Bash(tools/py:*)", *request.POST.getlist("allow")]
    if session:
        cmd += ["--resume", session]
    # Same data root as the app, whatever the layering resolved it to — so pointing the
    # server at scratch data points the chat there too.
    env = {**os.environ, "JOBSTUDIO_DATA": str(settings.DATA_ROOT)}

    resp = StreamingHttpResponse(_stream(cmd, prompt, env), content_type="application/x-ndjson")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp
