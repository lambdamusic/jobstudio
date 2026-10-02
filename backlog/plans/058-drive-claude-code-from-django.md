# M3 — drive Claude Code from the Django app

> Extracted from [`002-share-as-toolkit.md`](002-share-as-toolkit.md) on 2026-10-02,
> where this was **milestone M3** and lived as §8. `#2` — the umbrella item that plan
> served — is closed; this is the part still open, so it moves to its own file named for
> the item that owns it.
>
> **Section numbers are kept as they were.** `TODO.md`, `001-drop-direct-anthropic-api.md`
> and `log/2026-09-23-status-menu.md` all cite §8.1–§8.4 — renumbering would break every
> one of them for no gain. So this file starts at §8.
>
> **Written 2026-09-20, before the `jobstudio` rename settled** (`002-share-as-toolkit.md`
> §2e). The text below is verbatim and still says `/jobs-search`,
> `.claude/skills/jobs-search/` and `.jobsearch-data`; read those as `/jobstudio`,
> `.claude/skills/jobstudio/` and `.jobstudio-data`. Left as written rather than quietly
> edited, because this is a dated research record and the commands it names were real on
> the day.
>
> Background it refers to — the data root (§3.1), the Dropbox question (§5.2), the
> milestones (§6) — stays in `002-share-as-toolkit.md`.

---

## 8. Stretch goal B — drive Claude Code from the Django app *(recommended)*

Michele's question, 2026-09-20: *is there a way to control Claude Code from a local
Django app?* Yes — two officially supported routes, and this is a much better fit for
this project than §7, because **the web app already exists**.

The idea: buttons in the tracker that run `/jobs-search` subcommands. "Tailor CV" on
the application detail page. "Run scan" on the scans page. "Log application" from a
pasted job description. Claude Code becomes the engine behind the UI Michele already
uses daily, rather than a separate terminal he has to switch to.

### 8.1 The two routes

| | **`claude -p` subprocess** | **Python Agent SDK** |
|---|---|---|
| How | Django shells out to `claude -p "/jobs-search cv #18" --output-format stream-json --verbose` | `claude-agent-sdk` embeds the same agent loop in-process |
| Skill discovery | **Automatic** — cwd at repo root picks up `.claude/skills/jobs-search/` and `CLAUDE.md` exactly as an interactive session does | **Must be explicit** — the SDK loads *no* filesystem settings by default; pass `setting_sources=["user", "project"]` or the skill is invisible |
| Output | Newline-delimited JSON events (needs `--verbose`; `--include-partial-messages` for token deltas) | Structured message objects |
| Effort | ~a day | More, but better error handling and permission control |

**Recommendation: `claude -p` first.** It runs the existing skill completely unchanged
— no repackaging, no cwd-independence work, none of M2 as a prerequisite. That makes
it the cheapest possible test of whether this is actually nice to use. Move to the SDK
only if structured streaming or finer permission control turns out to matter.

### 8.2 Cost — this does not undo `#1`

No pay-per-token API key is needed. Claude subscriptions carry a **monthly Agent SDK
credit** (Pro $20, Max 5x $100, Max 20x $200; Team/Enterprise equivalents), claimed
once and refreshed each billing cycle, covering both the Agent SDK and `claude -p`.
Michele's own local app is squarely within permitted use — the ban on subscription
OAuth for third-party products doesn't apply to your own projects.

**But be clear-eyed about the nuance**, because it's genuinely different from how the
toolkit is used today: the credit is a **dollar allowance, separate from the
subscription's session limits**. It doesn't roll over. When it's exhausted, requests
either bill at API rates or stop outright if usage credits aren't enabled. So driving
the toolkit from Django is *metered differently* from typing `/jobs-search` in a
terminal — not more expensive in any simple sense, but not the same pool. Worth
watching for a month before leaning on it.

### 8.3 Design notes specific to this codebase

1. **The view pattern already exists.** `#24` added a local-only action view plus a
   button on the application detail page, generalised by `#28` into
   `/actions/set-status/<num>/<status>/` behind a status menu.
   An agent-run button is the same shape — `/actions/run/<subcommand>/<num>/` — with
   the same local-only guard.
2. **Runs are slow and there's no Celery here.** CV tailoring takes a minute or more,
   so it can't block a request/response cycle. Lightest thing that fits the existing
   sqlite-as-truth design: `subprocess.Popen` detached, plus a small `AgentRun` model
   (subcommand, target, status, started/finished, log path) that the detail page
   polls. No new infrastructure, and the run history becomes visible in the app — which
   is arguably a feature, since today there's no record of which subcommand produced
   which file.
3. **Permissions must be pre-approved.** Non-interactive means no human to approve
   tool calls: `--permission-mode acceptEdits`, or an explicit `--allowedTools`. A web
   button that runs a file-writing agent deserves deliberate thought even on a
   local-only app — worth deciding per subcommand rather than granting blanket edit
   rights.
4. **cwd must be the repo root**, or skill discovery silently fails. With the §3.1
   data-root split this means: code repo as cwd, data root resolved from
   `.jobsearch-data` — which the refactor gives for free.
5. **Ordering:** M3 does *not* depend on M1 or M2. It could be prototyped this week
   against the repo as it stands today. That's a point in its favour.

### 8.4 The honest limitation

This only works where Claude Code is installed and authenticated. It makes the toolkit
substantially better **for Michele and for anyone technical** — but unlike the Cowork
route, it doesn't widen the audience. It's a depth play, not a reach play. Worth being
explicit about that, because "share it with someone else" (`#2`'s actual goal) is
still served by M1 and M2, not by this.

**Sources:**
[Agent SDK overview](https://code.claude.com/docs/en/sdk/sdk-overview) ·
[Use Claude Code features in the SDK](https://code.claude.com/docs/en/agent-sdk/claude-code-features) ·
[Agent Skills in the SDK](https://platform.claude.com/docs/en/agent-sdk/skills) ·
[Use the Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) ·
[claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
