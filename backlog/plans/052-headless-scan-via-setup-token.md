# Headless scans via `claude setup-token` — deferred

> **Status:** `#52` closed 2026-10-08 as a plain deletion of `scan --api` (see `DONE.md`).
> Nothing in this plan was built; it stays here for if an unattended scan is ever wanted.

Detail for `#52` in `TODO.md`. The idea was raised with the item on 2026-09-30; set
aside 2026-10-08 by Michele: *"no need to check the claude setup-token route… for now
it's not needed."* `#52` goes ahead as a plain deletion of `scan --api`; this file keeps
the headless route on record in case an unattended scan is ever wanted.

## What exists today

`#1` kept `scan --api` (`src/score-candidates.py`) for two reasons: it was the only
fully headless, cron-able scan (`scan-portals.py` → `score-candidates.py`, chained),
and it billed scoring per token instead of spending session/rate-limit budget. The
default scan is agent-native — `subcommands/scan.md` step 2 scores live inside a Claude
Code session — so without the API path, a scan always needs someone to start it.

Nobody runs scans from cron today. That is why the route is not needed now: deleting
`--api` loses a capability that is not being used.

## The route, if it is ever wanted

`claude setup-token` prints a one-year OAuth token (Pro/Max/Team/Enterprise plan),
meant for scripts and CI. With it exported as `CLAUDE_CODE_OAUTH_TOKEN`, a
non-interactive `claude -p` run authenticates on the user's own subscription — so the
normal agent-native scan can run headless with no API key anywhere in the toolkit.
[Auth docs](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token).

Rough shape of the invocation, unverified:

```bash
env -u ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN=… \
  claude -p "/jobstudio scan" --allowedTools "Bash(tools/py:*),Read,Write,Edit"
```

## Open questions — the spike, if it is picked up

- **Does it reach a written report without a permission prompt?** Work out the
  allowlist it needs: `tools/py` calls, and writes into the data root (which is outside
  the repo, so the working directory's permissions may not cover it).
- **`--bare` ignores the token**, so the run must not use it.
- **Test against a scratch data root** (`JOBSTUDIO_DATA=…`), never the real search.
- Once it works: a documented cron recipe in `docs/portal-scan-and-scoring.md`, with a
  warning that the token is a personal credential — kept in the user's environment,
  never in the data root or the repo.

## Trade-off already accepted

Dropping `--api` also loses `#1`'s second reason — per-token billing for high-volume
scoring, which matters more once `#8`/`#9` widen discovery. This route does not bring it
back: a headless `claude -p` run spends the same subscription budget as an interactive
one (and, per `plans/058-drive-claude-code-from-django.md` §8.2, may draw on a separate
monthly Agent SDK credit). If volume bites, the fix is a smaller candidate set or
batching, not restoring the API path.

## Related

`#58` (drive Claude Code from the Django app) uses the same `claude -p` subprocess, and
would answer most of the permission questions above along the way.
