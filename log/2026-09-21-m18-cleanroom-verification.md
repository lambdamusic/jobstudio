# M1.8 — the clean-room pass, and two exemptions that were hiding real content

**Date:** 2026-09-21 (continues `log/2026-09-21-m17-data-root-split-and-archive.md`)
**Session focus:** The first two of M1.8's three passes — automated, then a genuine
clean-room install following the public README from zero.

**Headline:** Both passes green. The install itself had no findings at all; the two real
findings were in the *verifier*, which was exempting files it should have been reading.
The third pass — a second real person — is still open and cannot be done from here.

---

## Pass 1 — automated

`tools/smoke-test` SMOKE PASS, `manage.py test tracker cvs` 78 green. Baseline only;
this was already known to pass.

## Pass 2 — clean room

The plan asks for "a different machine or a different user account". A different machine
was not available, so the substitute was a **fresh `$HOME`** — an empty directory
exported as `HOME` for every command. That is what actually matters here, because it
removes `~/.jobstudio.ini`, which is the one piece of per-user state the whole config
chain hangs off. Fresh directory, fresh clone, fresh venv, README followed literally.

**This is the part `smoke-test` cannot do, and the reason the pass was worth running.**
The smoke test deliberately shortcuts three things: it passes `--skip-global` (so it
never writes or reads `~/.jobstudio.ini`), it passes `--venv-python` pointing at *this*
machine's existing interpreter (so it never creates a virtualenv), and it never opens the
README. Venv creation, the global config file, and the written instructions were
therefore all untested by anything until now.

Verified, in README order:

- Clone is clean — 148 tracked files, and none of `tools/py`, `.jobstudio-data`,
  `local_settings.py`, `db.sqlite3`.
- `python3 -m venv` + `pip install -e .` works verbatim. All eight runtime imports
  resolve; Django 5.2.17.
- `jobsinit.py --from-example` **without** `--skip-global` — creates the data root
  including a parent (`~/Dropbox/` did not exist), writes the pointer, `tools/py`,
  `local_settings.py`, the workspace file, the admin account, and `~/.jobstudio.ini`
  into the fresh home.
- `tools/py src/jobsdb.py status` → the 3 example applications.
- **Config layering**, the bit with no coverage elsewhere: resolves with the
  `.jobstudio-data` pointer moved aside (global ini alone), and from a working directory
  that is the data root rather than the repo. Both correct.
- Web app boots; `/`, `/companies/`, `/applications/`, `/admin/login/` all 200.
- 78 tests green in the clean room; `smoke-test` passes from inside the clean clone.
- `site-build` (32 pages, link check clean) and `db-dump` — both write into the data
  root, not the checkout.
- New data root: zero mentions of the author. No absolute home-path literals anywhere in
  the tree.

**No findings against the install or the README.** Every documented step worked as
written, first time.

## The two findings, both in `tools/make-public-tree`

The verifier reported `PUBLIC TREE OK — no personal identity` on a tree in which
`src/web/apps/tracker/tests.py` contained `michele-pasin` five times. It was on
`ALLOW_NAME`.

1. **`tests.py` was exempt, and was carrying real job-search content.** Not the author's
   byline — the names of four companies he actually applied to, with dates, as fixture
   filenames. That is precisely the
   "personal job-search CONTENT" the guard's own comment says it exists to stop, and it
   was being waved through by a sentence written to justify a different pair of files
   (the ones that assert the name is *absent*). The strings are pure filename logic —
   the test's own docstring says nothing depends on one person's data — so they were
   replaced with example-data names and the exemption dropped.

2. **`src/appfolder.py` was exempt and contained nothing.** Zero hits. The exemption
   presumably dates from the hardcoded author slug in `app_filename()` that M1.5 fixed,
   and outlived it.

Auditing the rest the same way: **every entry on `ALLOW_PATH` was dead** except
`make-public-tree` itself, whose own grep literals are the absolute paths it would
report.
Four exemptions for four files that contain no absolute path at all. Trimmed.

This is the M1.7 lesson again, in a smaller key — there, `backlog/` and `log/` were on
the *denylist*, so the verifier would have skipped them and reported clean on files it
had never read. Same shape: **an exemption no file needs is not free, it is a blind spot
waiting for the next file whose path happens to match.** Both lists are now minimal, and
the comment says so, so the next person to add an entry has to justify it.

## Confirming the guard bites

Trimming an allowlist is only worth anything if the check underneath it works, so each
was tested by planting a violation and watching the build refuse — the same technique
M1.7 used:

| planted | result |
|---|---|
| author name in `tests.py` | REFUSING TO SHIP: personal identity |
| author name in `appfolder.py` | REFUSING TO SHIP: personal identity |
| an absolute home path in `docs/README.md` | REFUSING TO SHIP: absolute home-directory paths |
| a former employer / home town in `docs/workflow.md` | REFUSING TO SHIP: personal identity |

All four refuse. Working tree restored after each.

## State

78 tests green and `PUBLIC TREE OK` after the fixes. The two changed files
(`tests.py`, `make-public-tree`) are **uncommitted** — note that `smoke-test` and the
clean-room clone both test committed `HEAD`, so they were validating the pre-fix tree;
`make-public-tree` reads the working tree and covers the fixes.

**Still open: M1.8 pass 3 — a second real person.** Nothing in the toolkit blocks it;
it needs someone else's machine and someone else's time.

---

## Later the same day — the scrub the clean room implied, and why the guard was split

M1.8's `tests.py` finding turned out to be one instance of a pattern, not a one-off.
Michele read `backlog/TODO.md` with a publishing eye and found what the guard had been
exempting all along: a former employer's competitor-intelligence dashboard named in
`#19`/`#20`, the tracked-company list spelled out in `#5`/`#10`, a real application path
in `#23`, and a worked shortlisting example in `#21`.

**Scrubbed, keeping every item's technical meaning.** `#5` still records which ATS each
unscanned company sits on and why it was not built — "one on Dayforce, Cloudflare-
protected, deliberately not bypassed" says everything the company name did. The plan's
`location:` example and `m1.1-inventory.md`'s four entries (which quoted the employment
history they were recording the *removal* of) went the same way, as did three `log/`
files — including this one, which reproduced the four company names while describing the
finding. Then `docs/`, `.claude/skills/` and `src/`: an application-folder example named
after a real application, three named employers standing in for "large traditional org",
and a dead pointer to a specific cover letter by application number — a reference into
private data that no other user could ever resolve. Those now use the `example-data`
companies, which exist for exactly this.

**`COMPANY_OVERRIDES` stays** — a company → ATS map is functionality, not biography:
useful to every user of a scanning tool, about public employers with public job boards.
Same for `KNOWN_UNSUPPORTED_REASONS` and the one first-party fetcher. The line drawn is
**integration data stays, illustrations drawn from one person's applications go** — the
latter were never better examples, just closer to hand.

> **Superseded later the same day** (see the last section). The reasoning above holds for
> the *data* but drew the wrong conclusion about where it should live: useful-to-everyone
> and belongs-in-shared-code are different claims, and only the first was true. The map
> was externalised to the data root rather than kept — which keeps the functionality and
> removes the target list, instead of trading one for the other.

### The structural fix

One identity check became two, because one pattern was doing two different jobs:

| pattern | exempt in |
|---|---|
| the author's name (two terms) | `backlog/`, `log/`, LICENSE, the three tool scripts |
| `PRIVATE` — former employers, home town, the competitor dashboard (five terms) | **nothing** but the script itself |

The exact terms are in `tools/make-public-tree`; this file deliberately does not repeat
them, for the reason the next paragraph but one explains.

The old single check **already matched the employer and home-town terms**. The only
reason `#19` and the inventory survived it was `^backlog/|^log/` on the allowlist. A
byline in a signed design document is expected; a former employer in the roadmap is not,
and the two had been sharing one exemption.

This matters more than the scrub, because a roadmap for a job-search tool *accretes*
job-search specifics — it is what the tool is for. Planting a `PRIVATE` term in `backlog/TODO.md` now fails with `REFUSING TO SHIP:
employer / job-search specifics`, so the next entry is caught by the build rather than
by someone re-reading 180KB of backlog before a release.

### A third instance, caught by Michele at the last step

The scrub above was verified with `make-public-tree` and reported **PUBLIC TREE OK**.
It was wrong, and Michele caught it while reading the hand-over commands — a plain
`git grep` for the employer terms returned hits in *this file*, which had just been
written to document the new check and quoted the pattern verbatim.

The reason is the same one twice already recorded. `make-public-tree` enumerates from
`git ls-files`, so the copied tree — and therefore every check — sees **committed state
only**. This file was untracked when the verifier ran, so it was never copied and never
read. Committing it changed nothing about its content and flipped the same tree from
`PUBLIC TREE OK` (148 files) to `REFUSING TO SHIP` (149).

Two fixes. The file now describes the two patterns instead of spelling them — a document
explaining a guard should not trip it. And **the script refuses to run on a dirty tree**
rather than silently under-checking one: uncommitted or untracked files are listed and
the build stops. That closes the class, not just this case.

Worth being blunt about the pattern, since it has now appeared three times in one day —
the `backlog/`/`log/` denylist (§5.7), the `tests.py` exemption (M1.8), and this. Every
time, the verifier said clean about files it had never read, and every time the fix was
to make the set it reads match the set that ships. **A green check is only worth what
its input set is worth**, and that set deserves as much scrutiny as the rules applied
to it.

### State

78 tests, SMOKE PASS, PUBLIC TREE OK. Still open and still Michele's call: whether `log/`
ships at all. §5.1's original default was to leave it in the private archive, §5.7
reversed that, and the evidence here leans back toward §5.1 — four of the six files
needing a scrub were `log/` files. Nothing blocks publishing either way.

---

## Externalising the scanner's company data, and the taxonomy behind it

Michele, reading `src/scan-portals.py` with the same publishing eye: it held his target
list. Not as illustration — as working data. Four module constants (`COMPANY_OVERRIDES`,
`KNOWN_UNSUPPORTED_REASONS`, `CATEGORY_TO_AREA`, `DEFAULT_AREA`), 40 entries between
them, plus one company's first-party API endpoint hardcoded in a fetcher branch.

**This is the better fix, and worth naming as a principle.** Everything before it was a
scrub — find the personal string, reword it. This one asks *why the string was there*,
and the answer is that data about one person's search had been written as code. Scrubbing
that would mean deleting working functionality; externalising it keeps the functionality
and makes it configurable for everyone. **Where a scrub and a refactor both remove the
same string, the refactor is the one that stops it coming back.**

The four now live in `<DATA>/jobs/scan-config.yaml`, read through `src/scan_config.py`,
next to `jobs/targets/*.yaml` — already where "what am I looking for" is configured. The
file is optional: without it the scanner still runs on URL detection alone, losing only
the hand-researched overrides that no URL pattern could infer. The hardcoded endpoint
became `platform: firstparty_entries` with the URL supplied by the override, so the
parser keeps the response shape it understands while no company's domain sits in the
repo.

**The migration was generated, not retyped.** The YAML was built by AST-parsing the
constants out of the module and dumping them, then asserted equal to what the loader
reads back, and `resolve_source()` was checked to return the same answers for the same
inputs. 40 hand-copied entries would have been a transcription bug waiting to happen.

### The taxonomy underneath

The same sweep found the categories and areas themselves: `CATEGORY_SHORT_NAMES` (8
categories), `Area.SHORT_NAMES` and `Area.ABBR` (5 slugs) in `models.py`, the skill's
`company.md` handing the agent those 8 categories to choose from, `application.md` doing
the same with the 5 areas, and a test asserting a fixed table of abbreviations.

Michele's call: **delete the lookup tables rather than migrate them.** All three already
had fallbacks — full name for the labels, slug initials for the abbreviation — and the
example data uses none of the five slugs, so the tables were dead weight for everyone but
their author. No migration, no fixture change, and the tab bars simply show full names.

The skill files matter more than the tables did, because they were *instructions*: "pick
one of these 8 categories" is wrong for anyone else. `company.md` now runs
`jobsdb.py categories` (a new subcommand, counts included) and reuses what the user's own
tracker holds; `application.md` reads `<DATA>/jobs/targets/`. Both degrade sensibly on an
empty data root — propose a few and confirm, rather than assume.

The abbreviation test is the small lesson: it asserted five specific slugs and skipped
anything else, so it passed vacuously for every user but one. It now tests the derivation
itself, on slugs the example data actually has.

### State

82 tests (4 new for `scan_config`, including a regression guard that fails if the
constants or a company endpoint reappear in `scan-portals.py` — canary-tested).
SMOKE PASS. `CHANGELOG.md` restarted as a single release entry for the public repo, on
Michele's call.
