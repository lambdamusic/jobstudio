# M1.7 — the data root split for real, and the old repo frozen rather than stripped

**Date:** 2026-09-21 (continues `log/2026-09-21-identity-paths-inventory-and-public-repo-prep.md`)
**Session focus:** The last destructive milestone. Split Michele's real job search out of
the pre-split repo into an external data root, make `dev2/jobstudio` the daily driver,
and move the planning here.

**Headline:** M1 is complete except M1.8. Nothing was deleted anywhere in this migration.

---

## What was done

The data root is `_Jobs/jobstudio-data`, a Dropbox sibling of the old repo (§5.2) —
named `jobstudio-data` rather than the plan's `job-search-data`, for one spelling
everywhere after M1.11. It holds `jobs/`, `exports/`, `site/`, `extras/`, `backups/`,
`config.yaml` and `db.sqlite3`.

Copied with `rsync -a`, then **verified before anything depended on it**: `diff -r` across
all four trees (225 + 250 + 187 + 26 = 688 files identical) and `sha256` on the database
and the dump. The old repo's `backups/django/dump.json` — the real one, 95 companies and
47 applications — was carried over as a timestamped dump rather than left behind, per the
§5.3 step 2 split between the frozen test fixture and a user's real backups.

`config.yaml` was written by hand, its values taken from the base CV's `# Name` heading
and contact block — which is exactly what `identity.py` layer 2 would have fallen back to,
so the file is an override that changes nothing rather than a new source of truth.

## The one deviation from the plan, and it is Michele's

§5.3 step 4 said to copy the data out and then `git rm` it, stripping the old repo. **He
chose to copy and freeze instead.** Nothing was deleted from the old pre-split repo
at all — it keeps its code, its data and its history, and its `CLAUDE.md` was rewritten
into a redirect that opens with "⛔ read-only archive".

Worth recording why this is better, because the original was the more elegant plan:
**the destructive half bought nothing.** Its only real purpose was to stop the old repo
being mistaken for the live one, and a `CLAUDE.md` that says so achieves that for free —
while a `git rm` spends the single irreversible action in the whole project to get there.
The copy was verified identical first, so the data was never in only one place.

The residual risk is the one §5.6 named when retiring the sandbox: a stale second copy
that silently drifts. Here it is accepted deliberately rather than missed — the archive
is frozen and labelled, not live and forgotten.

## The decision with teeth: a bare command now hits real data

`dev2/jobstudio/.jobstudio-data` pointed at the example data. It was **deleted**, so
resolution falls through to `~/.jobstudio.ini` and a bare `tools/py src/jobsdb.py status`
in the toolkit checkout reads the real job search.

The alternative — pointer left at example data, real work carrying `JOBSTUDIO_DATA=` —
is safer by default but wrong by frequency. Real use is the common case; development is
the exception; the exception should carry the ceremony.

That is only acceptable because the two things that run most often defend themselves
instead of relying on memory: `settings.py` pins `$JOBSTUDIO_DATA` to `example-data/`
before `local_settings` is imported whenever `argv[1] == "test"`, and `smoke-test` works
in a temp clone. Both were re-run after the repoint and neither touched real data. What
*is* exposed is an ad-hoc script run while developing a file-writing code path — now
called out explicitly in `CLAUDE.md`.

## Verification (the §5.3 gate)

| Check | Result |
|---|---|
| `config.py --chain` | falls through env → pointer → `.ini` → `jobstudio-data` |
| `config.py --path` (skill preamble step 1) | bare path, as the preamble needs |
| `status` | 47 applications, 13 active — the real data |
| `manage.py test tracker cvs` | 78 passed, against `example-data/` |
| `site-build` | 182 pages into the data root, link check clean |
| `db-dump` | wrote to `<DATA>/backups/django/`, byte-identical to the carried-over dump |
| `render.py --docx --functional` | landed in `<DATA>/exports/docx/`, `.docx` author = `Michele Pasin` (so `config.yaml` is being read) |
| `smoke-test` | SMOKE PASS |
| `git status` in the toolkit | clean; no `jobs/`, `exports/`, `site/` or `db.sqlite3` in the repo |

## `backlog/` and `log/` came here, and that broke the verifier in an instructive way

Michele's call, reversing M1.6: nothing in them is secret, and they are the rationale for
the code shipping beside them. `log/` was seeded with only the three toolkit-migration
entries — the other 21 mix design notes with personal job-search context and stay in the
archive.

Both directories were on `make-public-tree`'s `DENY` list. **Leaving them there would not
have kept them private** — they live in the public repo now, so they ship regardless. It
would have meant the copier skipping them, every check running against a tree that did not
match what is published, and the tool printing `PUBLIC TREE OK` for files it had never
read. A denylist that silently disagrees with reality is worse than either shipping or
withholding.

They moved to the exemptions instead, with the reason written into the file: these are
signed design documents about their author's own migration, anonymising them would gut
them, and the guard exists to stop job-search *content* leaking — not to hide who wrote
the toolkit, whose name is on the `LICENSE` and every commit.

Running it then **caught two real things**, which is the argument for having kept it:

1. The `Manual pp.` citation check fired on `m1.1-inventory.md` and a log entry — both of
   which quote those strings *while recording that they were removed* (`31e547b`). A
   document describing the deletion of a citation is not a citation.
2. Having fixed that with a comment, it fired on **its own new comment**. Both are now
   path-scoped rather than blanket-exempted, so a real citation creeping back into
   `subcommands/` or `docs/` is still caught.

## Scrubbed afterwards, and it bought back a check

Michele asked for his email and absolute paths out of the shipping docs. 4 email
occurrences and 13 absolute home-directory paths across `backlog/` and `log/`. Paths
became `~/...`; the email became `you@example.com` in the example `config.yaml`, and "the
author's email address" where the point was only *that a literal appeared somewhere*.

The part worth recording: `make-public-tree` used a single `ALLOW_NAME` list for both the
author-name check and the absolute-path check, so exempting these directories from one
exempted them from the other. With the paths gone the exemption is unnecessary, and the
lists are now split — `ALLOW_NAME` still covers `backlog/` and `log/`, `ALLOW_PATH` does
not. Confirmed by planting a fake home path in `TODO.md` and watching the build
refuse. The last bare home-path literal, in `m1.1-inventory.md` where it *describes* one that
was removed, was rephrased rather than exempted — so the check now has no special cases.

## CHANGELOG.md carried over too

Michele asked for it in the new repo with "all relevant things" brought across. Nearly all
of it qualified: 614 lines that are overwhelmingly about the code, which is why it was
worth keeping rather than restarting. What came out was the job-search record threaded
through it — tracked companies and watchlist additions, application numbers and the
companies behind them, the career-anchor scores and salary floor from the first stocktake
run, a former employer's name, a personal Surge URL, and job titles used as examples in
the CV-pipeline entries. Where a bug report depended on a real company (the accented-slug
404) the mechanism was kept and the tracker rows genericised, because the bug is the
instructive part, not who it happened to.

It also gained two new entries — M1.7, and a condensed M1.1–M1.6/M1.9–M1.11 — which until
now existed only as `log/` narrative. `CHANGELOG.md` came off the `DENY` list and went
into the must-be-present list, so it is copied *and* checked rather than skipped.

## One rescue

`backlog/m1.1-inventory.md` existed **only in the retired sandbox** — written during M1.1,
never copied to the Dropbox repo, and referenced by `make-public-tree`'s own comment. TODO
`#26` would have destroyed it. It is now in `backlog/`. A file-by-file comparison of the
sandbox's `backlog/` and `log/` against the archive found nothing else unique, which is
what unblocks `#26`.

## The archive's location is deliberately not load-bearing

Checked before Michele relocates it to `~/dev2/jobsearch-backups/`: nothing points at the
old repo by path. `~/.jobstudio.ini` names the *data root*, not the archive; the workspace
file and `.claude/settings.local.json` never mentioned it; and the only references in this
repo are prose. That is a property of freezing it rather than keeping it in the loop, and
it is worth stating so the next person does not go looking for a config file to update.

Moving it out of Dropbox also takes `tools/env.sh` and the old `.claude/settings.local.json`
— the two files holding a live API key — off a sync service, which is a small security
improvement rather than a cost. Nothing unique is at risk in the move: everything tracked
is pushed to the private GitHub repo, and the two gitignored things worth keeping
(`db.sqlite3`, `extras/`) already live in the data root.

## Still open

- **M1.8** — the clean-room pass on a different machine or user account, then a second
  real person. The automated third of it already passes.
- ~~**TODO `#26`**~~ — done same day: Michele deleted `~/dev2/jobsearch-sandbox` (52M) by hand, once the rescue above made it safe.
- ~~**Two dev data roots**~~ — resolved same day: Michele deleted `jobstudio-devdata2`
  and kept `jobstudio-devdata` as the scratch root for exercising the example data. The
  workspace file and `.claude/settings.local.json` were repointed at it.
