# M1.5 complete: a synthetic data root, `init`, a smoke test — and four bugs it found

**Date:** 2026-09-21 (continues `log/2026-09-20-toolkit-migration-steps-1-2.md`)
**Session focus:** Finishing M1.5 of the share-as-toolkit plan (`backlog/share-as-toolkit-plan.md`, `#2`): the example dataset, the synthetic DB fixture, migrating the test suite off Michele's data, `/jobs-search init`, and a from-scratch smoke test.

**Headline:** M1.5 is done. 78 tests green against synthetic data, and `tools/smoke-test` passes from a clean clone. Along the way the work found **four real bugs in code that had been passing tests for months** — all four invisible while the only data the code ever saw was Michele's.

All work is on the sandbox branch `data-root-move`, except two fixes that belong to the
daily driver and went to `main`.

---

## 1. The synthetic DB fixture (`3c90ee4`) — the release blocker, cleared

The committed test fixture was **95 companies, 47 applications, 86 status changes, 68
admin log entries, and an `auth.user` row carrying a `pbkdf2` password hash and a real
email address**. It sits outside `jobs/` and `exports/`, so the data-root move would
never have carried it away — it was the one piece of personal data that stays behind in
the code repo *by design* (§3.1 keeps `FIXTURE_DIRS` repo-anchored).

`tools/build-example-fixture` now rebuilds `example-data/backups/django/dump.json` from
the example files plus `_fixture_rows.py`, in a throwaway data root, **through the real
models**. Two things hand-written JSON cannot give: it is valid against the current
models by construction, and when the models change you re-run it rather than editing
JSON.

**Proof it captures behaviour rather than shape:** the `applicationstatuschange` rows
appeared on their own, written by the post_save signal. Nobody typing a fixture would
have thought to include them.

`auth.user` and `admin.logentry` are excluded outright — the suite creates its own
superuser, so nothing needs them. The build script **asserts** both are absent and that
no real identity appears anywhere in the output, so a regression fails the build rather
than reaching a commit.

## 2. Migrating the test suite (`2863579`) — the plan was wrong about the size

`settings.py` now sets `$JOBSEARCH_DATA` to `example-data/` when `sys.argv[1] == "test"`,
**before** `local_settings` is imported — that is where `config.data_root()` is first
called, and `appfolder.py` and `render.py` read it at module level too. One place
reaches all of them.

That ordering is the whole lesson. The plan assumed pointing `FIXTURE_DIRS` at the
synthetic dump was the job. Measured, across 78 tests:

| | failures |
|---|---|
| `FIXTURE_DIRS` swapped only | **42** |
| data root **and** fixture moved together | **13** |
| after migrating the 9 coupled tests | **0** |

The fixture swap was about a fifth of the work. What exposes it is the group of tests
that read **files from the data root** while asserting against **fixture rows** —
company notes by slug, application folders, cover letters on disk. With only the
fixture swapped, the database says "Grafana Labs" while the disk still holds someone
else's companies.

**Where coupling was avoidable it was removed rather than repointed.** The fit-summary
test asserted `"fit-banner is-stretch"` because application #30 happened to be a
stretch; it now asserts `f"fit-banner is-{app.fit_level}"` — pinning the class
convention instead of one person's data.

**Two failures were the example being too thin, not the tests being wrong**, so the
fixture grew to fit: three more watched companies (Elastic, PostHog, Snowplow — real,
public boards), because several tests need an application-free company and parametrised
ones consume a fresh one per subtest; and a third application with no folder and no
company FK, which gives the tabs test genuinely empty sections while keeping all three
watched companies free.

## 3. `init` and the smoke test (`60c39fb`, `77d9d44`)

`src/jobsinit.py` is deliberately **non-interactive** — every answer arrives as a flag.
`/jobs-search init` is the conversational half. Keeping prompts in the skill and
mechanics in the script means one code path, testable headlessly, and a smoke test that
can drive it. Idempotent, nothing overwritten without `--force`, and **no wipe mode** —
it points at a directory holding someone's whole job search.

It writes the data root, `config.yaml`, `.jobsearch-data`, `~/.jobsearch.ini`,
`tools/py`, `.claude/settings.local.json` (data root in `additionalDirectories`),
`job-search.code-workspace`, and `local_settings.py` if missing; then migrates, loads
the example fixture and imports areas and base CVs.

`tools/smoke-test` runs against a **fresh clone**, for two reasons: `init` writes into
the repo, so running it in place would modify the checkout; and a clone contains only
committed files — no `local_settings.py`, no `tools/py`, no `db.sqlite3` — which is
exactly the state a new user starts from. It asserts the clone is bare, runs
`init --from-example`, checks the data root and the wiring, runs `status`, renders a
docx, and greps the whole new data root for the author's name.

## 4. `init`'s four on-ramps (`7aaf679`)

Michele's point: `init` should offer to take a CV and fill the gaps conversationally, or
look the user up online and bootstrap from what is public.

Four on-ramps, offered explicitly rather than defaulting to the empty one — typing a
career into a blank file is the worst of the four and the one people abandon:
**the example**, **from a CV**, **from the web**, **from scratch**. B, C and D converge
on `stocktake`, because a CV and the web give history and facts but never motivation,
constraints, or what someone wants next.

Mostly routing — `cv --import`, `cv --rebuild` and `stocktake` already existed. The new
flow is the web one, and it carries two guardrails:

- **Identity first.** Name collisions are the normal case. Ask for a disambiguator,
  search with it, and show findings for confirmation *before* writing anything. If
  results look like more than one person, say so rather than merging two careers.
- **Nothing web-sourced reaches a CV unconfirmed.** This document goes to employers, so
  a mis-scraped title or wrong dates is not a typo — it reads as a lie on an
  application, and the user carries it. Findings are confirmed per item, not as a
  finished draft to nod through, and anything unconfirmed is dropped rather than
  softened.

**LinkedIn is named as the source that works worst** — routinely bot-blocked, and
scraping it is against its terms — with the instruction to ask for a pasted profile or
the exported PDF instead. Faster, more accurate, and it turns the web on-ramp into the
CV one. Better to be straight about that than promise it and half-fail.

---

## The four bugs

All four had been passing tests for months. The common cause is stated at the end.

### 1. `is_tailored_cv()` — half the tailored CVs were invisible (`a142d36`, **main**)

Matched only `cv_functional` / `cv-functional` / `cv-chronological`, but tailored CVs
are named after the **target area**: `004-<company>-...-cv-ai-knowledge-work-....md`.
**15 of 30 in the real repo were unrecognised.** Via `pick_cv()` → `ensure_folder()`,
those applications fell back to the untailored base — and because the base's own
filename wasn't in the folder, a refresh would copy a generic CV in alongside the good
tailored one, every time.

**The test hid it rather than catching it.** It asserted
`assertIn("cv-functional", picked.name)`, which passed only because application 030
happened to have a `cv-functional`-named CV. The assertion had been written from the
*implementation* rather than the *convention*, so it encoded the same narrow pattern as
the bug and could never have failed on it.

### 2. Leaked template comment (`235a031`, **main**)

The four `test_templates_have_no_leaked_comment_markup` failures had been carried as
"pre-existing, unrelated" through every migration commit. They were a real,
user-visible bug: `_app_table.html` opened with a **three-line `{# … #}`**, and
Django's `{# #}` is **single-line only** — so all three lines rendered into the page,
visible to the reader, on `/`, `/applications/`, `/applications/all/` and `/areas/`.
The test existed specifically to catch this and was being ignored.

**The suite is now genuinely green**: 78 tests, 0 failures. Every earlier commit saying
"the same 4 pre-existing failures" was comparing against this.

### 3. The gitignore was eating `example-data/jobs/` (`4fab6e3`)

Step 2's trailing-slash fix (`jobs/` → `jobs`, so a post-split symlink would still be
ignored) had a side effect nobody looked for: **an unanchored pattern matches every
path component of that name, at any depth.** So `jobs` ignored `example-data/jobs/`, and
**14 of the example dataset's 17 files were never committed** — git had three, while the
working tree looked complete.

This one is worth dwelling on, because the earlier session log and the commit for it
both claimed 17 files. That count came from `find`, not `git ls-files`. Nothing else
would have caught it: the files are present locally, so every test, every render and
every manual check passed. The smoke test found it only because it **clones**, and a
clone sees only what is tracked.

    jobs/    only a real directory, any depth   (misses a symlink)
    jobs     anything of that name, any depth   (eats example-data/jobs)
    /jobs    anything of that name, at the root (right)

### 4. `init` resolved the venv symlink away (in `60c39fb`)

`Path(venv_python).resolve()` follows a virtualenv's `bin/python` symlink to the system
interpreter — losing the venv's site-packages, so Django was not importable and every
`manage.py` call failed. Absolute, not resolved. Caught by the smoke test on its first
real run.

---

## Why all four surfaced now

None of these are about the toolkit split. They surfaced because M1.5 forced the code to
run against **data that wasn't Michele's** for the first time — a different person's
filenames, a different fixture, a clean clone with none of the gitignored files.

Real data satisfies every assumption that was derived from it. That is why it cannot
find this class of bug, and it reframes why M1.5 was worth pulling forward: the stated
reason was getting tests off personal data, but the actual return is that **synthetic
data finds bugs real data cannot**.

Two of the four were found specifically by the *clone* step, not the synthetic data —
worth remembering when M1.8's clean-room pass comes around, because that is the same
mechanism applied to a whole machine.

## Where things stand

| | |
|---|---|
| M1.2 `config.py` | ✅ on `main` |
| M1.5 example data, fixture, `init`, smoke test | ✅ sandbox |
| M1.9 skill data paths | ✅ sandbox |
| M1.10 platform | decided (macOS + Linux); three fixes unbuilt |
| M1.1 inventory, M1.3 identity, M1.4 `tools/py` | open |
| M1.6 public repo, M1.7 migration, M1.8 verification | open; M1.7 gated on the §5.5 trial |

**Next is M1.3**, and the reason is sharper than its position in the list:
`config.yaml` is written by `init` and **read by nothing** — all 8 references are
writers in `jobsinit.py`. Meanwhile `appfolder.app_filename()` still hardcodes
`michele-pasin`, so a new user's first `/jobs-search application` produces
`001-their-company-michele-pasin-cv-2026-09-21.md`. The smoke test cannot catch it
because it never creates an application folder — extending it to do so is part of the
work. 49 hardcoded-identity references across `src/` and the skill.

**Then M1.4:** 28 files still carry the absolute venv path — two of them added by this
session, in `tools/build-example-fixture` and `tools/smoke-test`, flagged `# M1.4` in
the source. `init` already writes `tools/py`, so this is rollout, not design.
