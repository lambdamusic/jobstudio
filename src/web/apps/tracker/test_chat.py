"""Tests for the chat panel (chat.py, docs/chat-panel.md).

None of them runs Claude: the parser is fed stream-json lines shaped like the ones
`claude -p --output-format stream-json --verbose --include-partial-messages` writes, and
the view's subprocess is a stand-in that replays them.
"""

import json
from unittest import mock

from django.test import TestCase, override_settings

from tracker import chat

FIXTURE = ["dump.json"]


# --- stream-json, as Claude Code writes it -------------------------------------------

def _stream_event(event, parent=None):
    return {"type": "stream_event", "event": event, "session_id": "sess-1",
            "parent_tool_use_id": parent}


def message_start():
    return _stream_event({"type": "message_start"})


def message_stop():
    return _stream_event({"type": "message_stop"})


def text(t, parent=None):
    return _stream_event({"type": "content_block_delta",
                          "delta": {"type": "text_delta", "text": t}}, parent)


def tool_use(name, **args):
    return {"type": "assistant", "session_id": "sess-1",
            "message": {"content": [{"type": "tool_use", "name": name, "input": args}]}}


def result(**extra):
    return {"type": "result", "session_id": "sess-1", "is_error": False,
            "total_cost_usd": 0.25, "duration_ms": 4200,
            "usage": {"iterations": [
                {"input_tokens": 5, "cache_read_input_tokens": 100,
                 "cache_creation_input_tokens": 0, "output_tokens": 10},
                {"input_tokens": 2, "cache_read_input_tokens": 30000,
                 "cache_creation_input_tokens": 5000, "output_tokens": 300}]},
            "modelUsage": {"some-model": {"contextWindow": 1000000}},
            **extra}


class FakeProc:
    """Enough of a Popen for chat._run: a stdin to write to, a stdout to read."""

    def __init__(self, lines, returncode=0, stderr=""):
        self.stdin = mock.Mock()
        self.stdout = iter(json.dumps(m) + "\n" for m in lines)
        self.stderr = mock.Mock(read=mock.Mock(return_value=stderr))
        self.returncode = returncode
        self.terminated = False

    def wait(self):
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True


def events(lines):
    return list(chat._events(FakeProc(lines)))


def of(evs, kind):
    return [e for e in evs if e["t"] == kind]


class EventTests(TestCase):
    """stream-json in, the panel's events out."""

    def test_session_is_announced_once(self):
        evs = events([message_start(), text("hi"), message_stop(), result()])
        self.assertEqual(of(evs, "session"), [{"t": "session", "id": "sess-1"}])
        self.assertEqual(evs[0]["t"], "session")

    def test_one_bubble_per_message_with_tools_between(self):
        evs = events([
            message_start(), text("First, the folder."), message_stop(),
            tool_use("Bash", command="ls jobs/applications/001-grafana-labs"),
            message_start(), text("Then the "), text("todo."), message_stop(),
            tool_use("Read", file_path="/data/jobs/applications/001-grafana-labs/todo.md"),
            message_start(), text("Done."), message_stop(),
            result()])
        order = [e["t"] for e in evs if e["t"] in ("message", "tool", "html")]
        self.assertEqual(order, ["message", "html", "tool", "message", "html", "tool",
                                 "message", "html"])
        self.assertIn("Then the todo.", of(evs, "html")[1]["d"])

    def test_tool_only_messages_open_no_bubble(self):
        # The fix for the blank space mid-task: a message that is only a tool call
        # must not start a bubble, and must not leave a paragraph break behind.
        evs = events([
            message_start(), text("Looking."), message_stop(),
            message_start(), tool_use("Bash", command="ls"), message_stop(),
            message_start(), tool_use("Bash", command="pwd"), message_stop(),
            message_start(), text("Found it."), message_stop(),
            result()])
        self.assertEqual(len(of(evs, "message")), 2)
        self.assertEqual("".join(e["d"] for e in of(evs, "text")), "Looking.Found it.")

    def test_reply_is_rendered_as_the_site_renders_markdown(self):
        evs = events([message_start(), text("**Grafana Labs** is at `applied`."),
                      message_stop(), result()])
        html = of(evs, "html")[0]["d"]
        self.assertIn("<strong>Grafana Labs</strong>", html)
        self.assertIn("<code>applied</code>", html)

    def test_message_the_stream_never_closed_is_still_rendered(self):
        evs = events([message_start(), text("Cut short"), result()])
        self.assertIn("Cut short", of(evs, "html")[0]["d"])

    def test_subagent_text_stays_out_of_the_reply(self):
        evs = events([message_start(), text("Mine."), text("A subagent's.", parent="tu_1"),
                      message_stop(), result()])
        self.assertEqual("".join(e["d"] for e in of(evs, "text")), "Mine.")

    def test_tool_summary_is_the_argument_that_says_what_it_does(self):
        evs = events([tool_use("Bash", command="ls -la\nsecond line"),
                      tool_use("Skill", skill="jobstudio"),
                      tool_use("TodoWrite", todos=[]), result()])
        self.assertEqual([e["d"] for e in of(evs, "tool")], ["ls -la", "jobstudio", ""])

    def test_usage_is_the_last_call_against_the_window(self):
        usage = of(events([result()]), "usage")[0]
        self.assertEqual(usage["context"], 2 + 30000 + 5000 + 300)
        self.assertEqual(usage["window"], 1000000)
        self.assertEqual(usage["cost"], 0.25)

    def test_plan_limits_as_percentages(self):
        evs = events([{"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {
            "five_hour": {"utilization": 0.094, "resetsAt": 1794406800},
            "seven_day": {"utilization": 0.12, "resetsAt": 1794643200}}}}, result()])
        self.assertEqual(of(evs, "limits")[0], {
            "t": "limits", "five_hour": {"pct": 9, "resets": 1794406800},
            "seven_day": {"pct": 12, "resets": 1794643200}})

    def test_refusals_come_back_with_the_rule_that_allows_them(self):
        evs = events([result(permission_denials=[
            {"tool_name": "Read", "tool_input": {"file_path": "/home/alex/.jobstudio.ini"}}])])
        self.assertEqual(of(evs, "denied")[0]["items"], [
            {"name": "Read", "d": "/home/alex/.jobstudio.ini",
             "rule": "Read(//home/alex/.jobstudio.ini)"}])

    def test_no_refusals_no_card(self):
        self.assertEqual(of(events([result(permission_denials=[])]), "denied"), [])

    def test_an_error_result_is_reported_before_done(self):
        evs = events([result(is_error=True, result="Prompt is too long")])
        self.assertEqual(of(evs, "error"), [{"t": "error", "d": "Prompt is too long"}])
        self.assertEqual(evs[-1]["t"], "done")


class RuleTests(TestCase):
    """The narrowest permission rule for one refused call."""

    def test_bash_is_the_exact_command(self):
        self.assertEqual(chat._rule("Bash", {"command": "git status"}), "Bash(git status)")

    def test_file_tools_use_the_absolute_path_marker(self):
        for name in ("Read", "Edit", "Write"):
            self.assertEqual(chat._rule(name, {"file_path": "/data/jobs/areas.md"}),
                             f"{name}(//data/jobs/areas.md)")

    def test_web_fetch_is_the_domain(self):
        self.assertEqual(chat._rule("WebFetch", {"url": "https://grafana.com/careers/x"}),
                         "WebFetch(domain:grafana.com)")

    def test_anything_else_is_the_tool_name(self):
        self.assertEqual(chat._rule("WebSearch", {"query": "grafana labs"}), "WebSearch")


@override_settings(CHAT_ENABLED=True, CHAT_PERMISSION_MODE="default")
class ViewTests(TestCase):
    """POST /actions/chat/ — the guards, the command it runs, and what streams back."""

    URL = "/actions/chat/"

    def post(self, **data):
        return self.client.post(self.URL, {"message": "hello", **data})

    def run_turn(self, lines=None, **data):
        """POST with Popen and `which` stubbed; returns (popen mock, events)."""
        lines = lines or [message_start(), text("Hi."), message_stop(), result()]
        with mock.patch.object(chat.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(chat.subprocess, "Popen", return_value=FakeProc(lines)) as popen:
            resp = self.post(**data)
            self.assertEqual(resp.status_code, 200)
            body = b"".join(resp.streaming_content).decode()
        return popen, [json.loads(l) for l in body.splitlines()]

    def test_get_is_refused(self):
        self.assertEqual(self.client.get(self.URL).status_code, 405)

    def test_only_from_this_machine(self):
        resp = self.client.post(self.URL, {"message": "hello"}, REMOTE_ADDR="192.168.1.20")
        self.assertEqual(resp.status_code, 403)

    def test_empty_message_is_refused(self):
        self.assertEqual(self.post(message="  ").status_code, 400)

    def test_missing_claude_is_explained(self):
        with mock.patch.object(chat.shutil, "which", return_value=None):
            resp = self.post()
        self.assertEqual(resp.status_code, 500)
        self.assertIn("claude", resp.json()["error"])

    @override_settings(CHAT_ENABLED=False)
    def test_off_means_not_found(self):
        self.assertEqual(self.post().status_code, 404)

    def test_the_command_it_runs(self):
        popen, _ = self.run_turn(session="sess-1", page="/applications/1/",
                                 allow=["Read(//data/a.md)", "Bash(git status)"])
        cmd, kwargs = popen.call_args.args[0], popen.call_args.kwargs
        self.assertEqual(cmd[0], "/usr/bin/claude")
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "default")
        self.assertEqual(cmd[cmd.index("--resume") + 1], "sess-1")
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], str(chat.settings.DATA_ROOT))
        # --allowedTools takes every value up to the next flag.
        rest = cmd[cmd.index("--allowedTools") + 1:]
        allowed = rest[:next((i for i, a in enumerate(rest) if a.startswith("--")), len(rest))]
        self.assertEqual(allowed, ["Bash(tools/py:*)", "Read(//data/a.md)", "Bash(git status)"])
        self.assertEqual(kwargs["cwd"], chat.REPO_ROOT)
        self.assertEqual(kwargs["env"]["JOBSTUDIO_DATA"], str(chat.settings.DATA_ROOT))

    def test_a_new_conversation_has_no_resume(self):
        popen, _ = self.run_turn()
        self.assertNotIn("--resume", popen.call_args.args[0])

    def test_the_page_travels_with_the_message(self):
        popen, _ = self.run_turn(page="/companies/grafana-labs/")
        proc = popen.return_value
        prompt = proc.stdin.write.call_args.args[0]
        self.assertIn("viewing /companies/grafana-labs/", prompt)
        self.assertTrue(prompt.endswith("hello"))

    def test_the_turn_streams_back(self):
        _, evs = self.run_turn()
        self.assertEqual([e["t"] for e in evs],
                         ["session", "message", "text", "html", "usage", "done"])

    def test_a_failed_run_says_why(self):
        with mock.patch.object(chat.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(chat.subprocess, "Popen",
                               return_value=FakeProc([], returncode=1, stderr="not logged in")):
            body = b"".join(self.post().streaming_content).decode()
        self.assertIn("not logged in", body)

    def test_one_turn_at_a_time_per_conversation(self):
        chat._running.add("sess-1")
        try:
            popen, evs = self.run_turn(session="sess-1")
        finally:
            chat._running.discard("sess-1")
        popen.assert_not_called()
        self.assertEqual(evs[0]["t"], "error")
        self.assertIn("already has a reply in progress", evs[0]["d"])

    def test_the_claim_is_released_when_the_turn_ends(self):
        self.run_turn(session="sess-1")
        self.assertNotIn("sess-1", chat._running)


class PanelMarkupTests(TestCase):
    """The button and the panel appear only where the chat can work."""

    fixtures = FIXTURE

    @override_settings(CHAT_ENABLED=True)
    def test_on(self):
        html = self.client.get("/").content.decode()
        self.assertIn('id="chat-toggle"', html)
        self.assertIn('id="chat-panel"', html)

    @override_settings(CHAT_ENABLED=False)
    def test_off(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn('id="chat-toggle"', html)
        self.assertNotIn('id="chat-panel"', html)


class StaticVersionTests(TestCase):
    """Static URLs carry the file's mtime, so an edit is picked up without a hard reload."""

    def test_static_urls_are_versioned(self):
        from django.templatetags.static import static
        self.assertRegex(static("js/chat.js"), r"^/media/static/js/chat\.js\?v=\d+$")

    def test_a_missing_file_gets_a_plain_url(self):
        from django.templatetags.static import static
        self.assertNotIn("?v=", static("js/no-such-file.js"))
