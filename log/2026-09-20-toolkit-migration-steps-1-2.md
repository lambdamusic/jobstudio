# Share-as-toolkit: plan closed, then steps 1 and 2 of the code/data split

**Date:** 2026-09-20
**Session focus:** Turning `backlog/share-as-toolkit-plan.md` (#2) from a menu of options
into an agreed design, then actually starting the migration — `src/config.py` landed on
the real repo, and the data-root move built and verified **in a sandbox only**. The
session ended abruptly mid-way through a follow-up experiment; this entry exists so the
next one doesn't have to reconstruct it from commit messages.

**Where it stands in one line:** step 1 of plan §5.3 is done and pushed; step 2 exists as
one commit on a sandbox branch that has **not** been pulled into the real repo; the real
repo is still the undivided single-folder layout.

---

## 1. The plan became a design (13:06, `ab53bd1`)

Four open decisions closed:

- **Distribution** — GitHub template repo first, `pip` package second. Both, in that
  order, not either/or.
- **Data location** — an external data root. `db.sqlite3` and *all* personal data live
  outside the code.
- **Example content** — a completely synthesised dataset (fictional person, full profile,
  CV, companies, DB) so the app is explorable before it's personalised.
- **Hardcoded strings** — `config.yaml` identity plus a generated `tools/py` wrapper.

A second audit pass corrected the first draft on two counts, both of which changed the
plan's shape:

- **Personal data in git is ~4x worse than first recorded** — ~690 of 810 tracked files,
  because `exports/` (245) and `site/` (179) had been missed entirely. That kills any
  history-scrub option: the public repo has to be a **fresh** repo.
- Two more hardcoded-name sites than the four already known: `appfolder.app_filename()`
  bakes the name into the filename convention, and `cover-letter-structures.md` carries
  name and email as literals.

Both stretch goals were researched against live docs and **swapped places**: §7 (Claude
Desktop / Cowork) turned out *easier* than the first draft claimed — attached workspace
folders solve the durable-filesystem problem, so sqlite-as-truth survives — but is
**parked** (egress bugs break `scan`, synced Dropbox folders are the discouraged config,
and Cowork merged into Claude on 2026-09-16). §8 (**drive Claude Code from the local
Django app**) replaces it as the recommended stretch goal: `claude -p` runs the existing
skill unchanged, and it depends on neither M1 nor M2, so it could be prototyped any time.

## 2. Three scope calls, one of them reversed within the hour

- **`afb8372` (15:34)** — scoped the surge.sh publishing path out of the plan entirely.
- **`31e547b` (17:32)** — **partially reversed it**: keep the site-export feature, but
  demote it from default to **opt-in**. Rebuilding only when a published snapshot is
  actually wanted. This also restores the static-HTML viewer the parked Cowork route
  depended on. Recorded consequence: with nothing exercising `site-build` routinely, it
  can rot silently, so M1.5 gains an occasional standalone check.
- Same commit: **all references to the third-party career-transition manual were stripped
  from every shipping file** (SKILL.md, `subcommands/stocktake.md`,
  `cover-letter-structures.md`, `docs/`, `jobs/profile/*`, `profile.html`), several of
  which carried page citations. The method is described generically now — the structure
  was never the copyrightable part. Source PDFs stay in `extras/`, which never goes near
  a public repo. **LICENSE will be MIT.**
- **`d62dd4d`** rebuilt `site/` (182 pages), picking up that removal plus accumulated
  drift: applications 43→47, companies 92→95.

## 3. Plan §3.1 hardened by two questions (17:45–17:58)

Michele asked what `.jobsearch-data` actually does, and whether Django can reach a
database outside the repo. Answering both surfaced a **correction worth more than the
answers** (`83be840`):

> `FIXTURE_DIRS` had been listed as a data path to migrate. It isn't — it's where the
> **test suite** loads `dump.json` from. Pointing it at the data root would make tests
> depend on a personal data root existing, so they'd fail on a fresh clone — exactly what
> M1's smoke test exists to catch. Two needs were sharing one path.

So: `FIXTURE_DIRS` and `STATIC_ROOT` stay **repo**-anchored; only `db-dump`/`db-load`'s
default output moves. Knock-on: `example-data`'s `dump.json` gains a second job as the
test fixture, so it must stay valid against the models rather than merely look plausible.

Also recorded there: why a pointer file rather than an env var alone (would need setting
in every shell, cron entry and Claude Code session) or `local_settings.py` (which imports
Django at line 8 — making it the source would force every standalone script to import
Django to resolve a path, and `appfolder.py` is deliberately Django-free at module level).
And the ordering gotcha: `local_settings` is imported at `settings.py:16`, *before* `src/`
joins `sys.path` at line 27, so it must do its own `sys.path.insert` before
`import config` — silent `ModuleNotFoundError` otherwise.

`0e52da6` then settled that in the split layout **neither `db.sqlite3` nor its dumps go
near the toolkit repo** — both live in the data root, keeping the public/private line in
one place. New §3.1.1: timestamped `dump-<YYYY-MM-DD-HHMM>.json`, newest-by-glob-sort on
load, with a retention rule. Consequence recorded rather than discovered later: this
**downgrades what protects the data** — today the dump is committed so git is the backup;
post-split nothing in the data root is version-controlled and protection becomes Dropbox
file history. The timestamped dumps are the compensating mechanism, so `init` should
schedule `db-dump` rather than trust memory.

`37015f6` added §5.4 (Michele's point): splitting code from data doesn't mean working in
two places — a **VS Code multi-root workspace** holds both in one window, and Source
Control lists the two repos separately, so a commit to the public toolkit can't quietly
sweep up personal data. That's a safety property, not just convenience. The easy-to-miss
half: **Claude Code needs the same treatment** — the data root in
`permissions.additionalDirectories` (`.claude/settings.local.json`), or `--add-dir`
per session, or every post-migration session prompts on every file access.

## 4. Safety nets, then the sandbox (17:50–17:58)

Three nets before touching anything (`3822c85`, `ac4c3db`, `96b9dac`):

1. Pushed everything to GitHub.
2. Refreshed `backups/django/dump.json` — it had **silently drifted four days**, 43→47
   applications, 92→95 companies.
3. Dated full-folder copy to `dev2/jobsearch-backups/2026-09-20-pre-toolkit-migration`.

Then `ac4c3db` **started tracking `db.sqlite3`** in this (private) repo, closing the gap
that the drift exposed. Verified `PRAGMA integrity_check ok` and `journal_mode=delete`
first, so there's no `-wal`/`-shm` sidecar to lose; those are now explicitly ignored,
since committing a stale `-wal` alongside a database can corrupt a restore. Note this is
deliberately the *opposite* of what the split layout will do, and it's right in both
places for different reasons.

**Why the sandbox is not a branch** — the counterintuitive bit, worth not re-deriving:

> The files at risk are `db.sqlite3`, `jobs/` and `exports/`. `db.sqlite3` was gitignored,
> so git wasn't protecting it at all — neither a branch switch nor `git reset --hard`
> restores it. And the data root lives *outside* the repo by design, so it's shared across
> every branch and worktree. **A branch isolates precisely the files that were never in
> danger.**

Setup, deliberately outside Dropbox (no syncing a throwaway duplicate, no conflict-copies
mid-move, no sqlite-on-a-sync-service confusing a test failure with a real bug):

```
~/dev2/jobsearch-sandbox/repo    # clone; origin = the real repo
~/dev2/jobsearch-sandbox/data    # throwaway data root
```

## 5. Step 1 — done, on the real repo (`ac65d99`, `4237dcc`)

`src/config.py`: resolution order `$JOBSEARCH_DATA` → `.jobsearch-data` pointer file →
`REPO_ROOT`. Every data path routed through it, while still resolving to the same
directory — so no data moved and no behaviour changed. An explicitly configured root that
doesn't exist raises rather than silently writing a second copy of someone's job search
somewhere unintended. Stdlib only, because `appfolder.py` imports it and must stay
Django-free.

Deliberately landed on the real repo without the sandbox: it changes no behaviour and
moves no data, yet it's the fiddly, silent-failure-prone part of the job.

**The finding that matters.** The §3.1 call-site table had a blind spot: **eight further
sites use `settings.SITE_ROOT`, not `ROOT = Path(__file__)`**, so no grep for the latter
could see them — `admin._abs`, `Note.body_md`, `views._open_locally`, the folder-create
view, `import_jobs.rel` and its `handle()`, `build_static`'s output dir,
`cvs.BaseCv.full_path`. **Every one meant "the data root"**; `settings.SITE_ROOT` is never
used as a code path in app code. `views._open_locally` is the one to remember: a security
guard refusing paths outside the repo, which would have refused every real file
post-split.

**And only a real split run found them.** "Nothing changed" testing passes happily with
all eight bugs present; the split run failed with a `relative_to` ValueError in
`site-build` plus four test errors. **Any future step here needs a deliberate split run,
not just a regression run.**

⚠️ **`src/web/local_settings.py` is gitignored, so its edit doesn't travel.** Pulling the
branch into the real repo left `DATA_ROOT` undefined and Django refused to start; it had
to be hand-applied. `init` must write that block for new users.

## 6. Step 2 — built and verified, but **sandbox only** (`8dbf513`)

Branch `data-root-move` in the sandbox clone. Not merged, not pulled, not on GitHub.

- `jobs/`, `exports/`, `site/` and `db.sqlite3` moved into the data root; **707 files
  deleted, tracked files 810 → 163**. Copied and verified byte-identical before anything
  was deleted — no bare `mv` on real data.
- `backups/` splits in two, as §3.1 called for: `<repo>/backups/django/dump.json` stays as
  the frozen test fixture (`tests.py` pins the literal name); `<data-root>/backups/django/
  dump-<ts>.json` holds the user's real backups.
- That split is what unblocked the timestamped dumps: `db-dump` keeps the 20 most recent
  (`--keep N`), and **refuses to keep a dump that's empty or not valid JSON** — a
  `dumpdata` that dies mid-write otherwise leaves something that looks like a backup but
  restores nothing. `db-load` takes the newest by default, `--list` to see them, and
  always passes an **absolute** path so `loaddata` can't resolve a name through
  `FIXTURE_DIRS` and quietly restore the test fixture over real data.
- `config.data_root()` now fails loudly: the `REPO_ROOT` fallback is honoured only if the
  repo still holds data. A fresh clone with nothing configured used to create an empty
  sqlite and die with `no such table: tracker_application` three frames deep in Django.
- **Marker subtlety, found only by testing it:** Django creates `db.sqlite3` the moment it
  opens a connection, so one failed run in an unconfigured checkout leaves a 0-byte file
  that would make that directory look like a valid data root *forever after* — turning the
  check into a one-shot. Hence `looks_like_data_root()` requires a **non-empty** database.

Verified: fresh clone contains no `jobs/`, `exports/`, `site/` or `db.sqlite3`; pointed at
an external data root it runs `status`, `site-build` (182 pages, link check clean) and the
test suite (77 tests, the same 4 pre-existing failures as the untouched backup — the
template-comment-markup ones, unrelated to paths). Error paths checked individually:
nothing configured, 0-byte db, non-existent path, empty directory — each gives a specific,
actionable message.

## 7. Where the session actually stopped (18:18–18:19)

An **uncommitted experiment** in the sandbox, with no note explaining its rationale:

- `repo/jobs` and `repo/exports` were made **symlinks** into the data root. `site` was
  **not** symlinked.
- `.gitignore` was edited (uncommitted) to drop the trailing slashes — `jobs/` → `jobs` —
  because a trailing slash matches a real directory but **not a symlink**, so the
  post-split repo could otherwise have offered to commit a symlink into personal data.

The design question this implies — whether the split layout wants convenience symlinks
back into the data root at all, and whether `site` joins them — was never settled.

## Gotchas / carry-forward

1. **The real repo is untouched by step 2.** It still has `jobs/`, `exports/`, `site/`,
   `db.sqlite3` in-tree and no `.jobsearch-data`. Pulling `data-root-move` into it is the
   destructive half: real data must be copied to a real data root and the pointer written
   **first**, and `local_settings.py` hand-edited (gitignored, doesn't travel — §5 above).
2. **The plan is stale.** §5.3 still shows step 2 as pending and §9 still reads "Nothing
   implemented". Fix before trusting either.
3. **No CHANGELOG entry** — arguably correct, since nothing has shipped to the real repo
   beyond `config.py`, but worth a deliberate call.
4. **Split runs, not regression runs.** Restating §5's lesson because it will apply to
   every remaining step: a test pass against the unsplit layout proves nothing about path
   handling.
5. `extras/` stays behind — personal archive, nothing reads it, and it holds third-party
   copyrighted PDFs.

## Next

- Settle the symlink question, commit or discard the `.gitignore` edit.
- Update plan §5.3 / §9 to match reality.
- Then the real-repo migration (§5.3 steps 2–3, M1.7), with the data-root copy and the
  `local_settings.py` hand-edit as explicit first moves.
- Still outstanding from M1 as originally sequenced: M1.1 (exhaustive inventory —
  `jobs/notes/` and whether any `docs/*.md` embeds personal specifics are explicitly
  unchecked), M1.3 (`config.yaml` identity), M1.4 (`tools/py`), M1.5 (`example-data/` +
  `init` + smoke test — worth pulling forward, since it gets every test off Michele's real
  data).

---

## Addendum — same day, after the log above was written

Retracing the session prompted two decisions that reorder the rest of the plan.

### The real repo is not migrated next; the sandbox is where building continues

Michele: keep building in the sandbox and use it for a while before touching the real
repo. §5.3 gained a new step 3 (the trial) and the real migration slid to step 4. Full
reasoning in the plan's new **§5.5**; the load-bearing part is the data-truth rule:

> **The real repo stays the daily driver.** Applications get logged, scans run and CVs
> rendered *there*. The sandbox data root is throwaway — refresh it from the real repo
> when a verification run needs current data, and never do real job-search work in it.

Stated as a rule, not a preference, because two sqlite databases that have both
received real work cannot be merged in any sane way — no diff, no three-way merge, no
`loaddata` that reconciles them. One application logged in the wrong place costs far
more than the convenience that put it there.

Honest cost of choosing it this way: the layout gets tested as *code* but not as
*ergonomics*. The §5.4 question — whether working across a code repo and a data root
feels fine day to day — is not answered by a sandbox nobody lives in.

**And the branch should not be merged.** `main` keeps committing to `jobs/`,
`exports/` and `db.sqlite3` — files `data-root-move` deleted — so every day of trial
adds delete/modify conflicts to a future merge. But the endgame is a **brand-new public
repo with no history**, so the branch's history has nowhere to go; only the file state
matters, and step 2's code half is four files. `data-root-move` is a **worked
reference**, not a merge candidate. Corollary: build `init` / `config.yaml` /
`example-data/` as *separate* commits so they stay cherry-pickable, and make docs and
plan edits on `main` so the copy read daily stays current.

### The test fixture is a release blocker, and it was nearly invisible

Michele's catch: `backups/django/dump.json` in the sandbox is still personal data and
must never reach the public repo. Verified — it's worse than that:

- 95 companies, 47 applications, 86 status changes, 68 admin log entries
- one `auth.user` row with a **`pbkdf2_sha256` password hash** and
  the author's email address

What makes it easy to miss: it's the one piece of personal data that the data-root move
**doesn't** carry away. It isn't under `jobs/` or `exports/`, and §3.1 deliberately
keeps `FIXTURE_DIRS` repo-anchored so the test suite doesn't depend on a personal data
root existing. Correct decision, and its side effect is that the file stays behind in
the code repo by design. §1's inventory counted it among 810 tracked files without
singling it out.

Now recorded in §4 as a blocker with the verified contents, as an explicit M1.5
deliverable, and as a hard gate on M1.6. With no history in the new repo there is
nothing to scrub later, so it has to be synthetic **before the first commit** — and the
M1.5 smoke test should assert it (fail on any `auth.user` with a usable password hash,
or any email outside the example domain) rather than leaving it to memory.

### Done in this addendum

- Sandbox gained a `github` remote (private repo `lambdamusic/2026-jobs-search`);
  `data-root-move` pushed there. `origin` is still the local real repo. The sandbox
  data root is backed up by none of this and needs none — it's throwaway.
- Plan updated: header, §4, §5.3 steps 3-5, new §5.5, M1.5, M1.6, §9.

### Still open

- **The symlink question** (§7 above) — untouched, still uncommitted in the sandbox.
- **`main` has unpushed commits.** The log entry and these plan edits are local.

---

## Addendum 2 — why the symlinks existed, and what it uncovered

Michele's hunch, asked as a passing question: *were the symlinks added to make sure the
skills worked correctly?* Checking it turned out to be the most valuable question of
the session.

**They were, and the underlying problem is blocker 9.** The skill has **no notion of a
data root**. `SKILL.md` and `subcommands/` carry ~76 `jobs/`/`exports/` references, and
the only path convention stated anywhere is `company.md:8` — "relative to project
root". These are not documentation of where a script writes; they are instructions the
*agent* executes with its own file tools against the working directory:

- `application.md:120` — "**Research and write `jobs/companies/<slug>.md`**"
- `application.md:171` — "Read `jobs/profile/stocktake.md` and `jobs/profile/criteria.yaml`"
- `company.md:73` — "add `jobs/companies/<slug>.md` following the template in
  `jobs/companies/README.md`"

Post-split, without symlinks: reads fail, and **writes land silently in the code repo**
— the one destined to be public. Same class as step 1's eight `settings.SITE_ROOT`
sites (a path meaning "data root" resolving to the code), except it lives in Markdown,
where no grep over `src/` and no test run will ever find it.

**This reversed the recommendation made an hour earlier.** The symlinks had been called
papering-over and slated for deletion. On the evidence they're load bearing — they are
what kept the skill working after step 2. Revised: keep them for the trial, delete them
when M1.9 lands, and keep the `.gitignore` trailing-slash fix permanently regardless.
`site` was never symlinked, which is a decent hint that the set was assembled
reactively rather than designed.

**Fix chosen (Michele, of three options): `$DATA/jobs/...` placeholders** — M1.9. The
placeholder *is* the mechanism: a bare `jobs/...` reads as repo-relative and an agent
will treat it that way; `$DATA/...` cannot be misread and cannot be silently "already
correct". Not taken, recorded so it isn't relitigated: a single convention line leaving
the references bare (cheapest; one forgotten prefix writes personal data into the
public repo, silently), and moving the writes into code (most robust, right long-term
shape, far beyond M1).

Verification is the awkward part — nothing mechanical catches a wrong path in Markdown.
M1.5's smoke test should drive at least one real agent write against a temp data root
and assert the file landed in the data root and **not** in the repo.

## Addendum 3 — `~/.jobsearch.ini`, Michele's proposal

Adopted as §3.6, with two boundaries.

**It earns its place for a reason other than the obvious one.** The data root is
already resolvable via `.jobsearch-data` and `src/config.py`, so for a session in the
repo a global file adds nothing. What it adds is **findability when the working
directory isn't the repo** — post-split the common case, not the edge one: editing
`jobs/companies/<slug>.md` means the session starts in the *data root*, where there is
no `.jobsearch-data`, no `tools/py`, no `src/config.py` to run. That is exactly blocker
9's failure mode, which is why the two decisions fit together.

**`.ini` is right here, and not arbitrarily**, despite YAML being the house format.
`src/config.py` is deliberately stdlib-only because `appfolder.py` imports it at module
level. `configparser` is stdlib; `PyYAML` isn't. YAML would push a third-party import
into the one module every entry point loads first. So: `.ini` for bootstrap,
`.yaml` for content.

**Boundary 1 — the per-checkout pointer still wins.** Global is per *machine*,
`.jobsearch-data` is per *checkout*, and this machine currently needs both: real repo →
Dropbox data root, sandbox → throwaway. A global-only setting collapses them and breaks
the trial. Order: `$JOBSEARCH_DATA` → `.jobsearch-data` → `~/.jobsearch.ini` → error.

**Boundary 2 — identity does not move.** `config.yaml`'s identity block belongs to the
job search, not the machine, and `example-data/config.yaml` ships a fictional person so
the app is explorable before personalisation (decision 2c). Global identity breaks
that. The line: machine-level `.ini` = *where things are*; search-level `.yaml` =
*who you are and how you search*.

Costs accepted up front: layered config acquires a "why isn't it picking that up" mode,
so `config.describe()` must print the whole chain and which layer won (it already
exists and is already in `status`); and `init` writing to `$HOME` is more invasive than
writing in-project, so it prompts and never silently overwrites.

## Addendum 4 — M1.9 step 1 shipped, and a portability blocker found next to it

**`~/.jobsearch.ini` exists and `config.py` reads it** (`32e6772`, sandbox, its own
cherry-pickable commit). Michele's point that it couldn't wait for `init` was right:
`init` is M1.5, M1.9 needs `$DATA` resolvable now, so the file is hand-written and
`init` adopts it later.

Two output modes were added for consumers rather than humans: `--path` (the bare path,
which is what the skill will call) and `--chain` (every layer, marking the winner).
`--chain` is the mitigation §3.6 promised for the cost of layering, and it paid for
itself immediately — see the symlink finding below.

Verified in the four cases that matter:

| case | result |
|---|---|
| sandbox, split | the per-checkout pointer still beats the `.ini` — **the trial isn't broken** |
| cwd = data root, not a repo | resolves — the case the file exists for |
| `$HOME` alone, no repo reachable | resolves — blocker 9's failure mode |
| real repo (daily driver) | unchanged; `status` runs normally |

**Found while testing:** in the sandbox the repo fallback reports the *repo* as a valid
data root, because `repo/jobs` is a symlink into the real one, so `looks_like_data_root()`
sees a directory and says yes. The step-2 symlinks defeat the guard built specifically
to stop a wrong directory being treated as a data root — a third independent reason
they can't outlive M1.9.

### Blocker 10 — macOS-only in three places

Auditing what *else* belongs in a machine-level settings file turned up an unrecorded
portability problem. The sweep was deliberately wider than one pattern, since a
one-pattern grep is exactly what produced blocker 9:

- `render.py:568-570` — `_CHROME_PATHS`, two `/Applications/...app` paths. PDF export
  raises off macOS. Mildest of the three: it fails loudly, and docx is the default path.
- `views.py:363` — `subprocess.Popen(["open", …])`, two callers. `open` doesn't exist on
  Linux → `FileNotFoundError` straight out of the view → **Django 500**. The
  "Open folder" button hands the user a stack trace, which is worse than silence.
- **Ten** `vscode://file/` literals — 8 templates, `admin.py:40`, `web/README.md`.
  Degrades quietly, but hardcodes one editor for every user of a public toolkit.

Confirmed portable and needing nothing: docx is pure `python-docx`; the other
`subprocess` call uses `sys.executable`. Windows is a separate, bigger question —
everything in `tools/` is bash, including §3.3's planned `tools/py`.

Recommendation recorded as **M1.10**: declare macOS + Linux (Windows via WSL), say so
in the public README, and do three cheap fixes — `chrome_path` in the `.ini`,
per-platform `open`/`xdg-open`/`start`, and the editor scheme collapsed from 10
literals into one setting behind a single template tag. Those are also the first
non-`data_root` keys the `.ini` will hold, which confirms the §3.6 line: machine-level
settings are *where things are*, not who you are.

Left deliberately open: the platform decision itself is Michele's, not a default I
should pick.

**Platform decided (Michele, same day): macOS + Linux only, for now.** Windows is out
of scope rather than "supported via WSL" — nothing built or tested for it. Recorded
with the emphasis on *for now*: it's a scope decision, not an architectural one. What
would reopen it is someone actually asking, and the cost then is the `tools/` bash
layer and §3.3's `tools/py`, not M1.10's three fixes. Keeping those fixes
settings-driven rather than branching on `sys.platform` everywhere is what keeps the
door open cheaply.

---

## Addendum 5 — M1.9 done: the skill learns where the data root is

Blocker 9 is closed. Two sandbox commits, both still off `main` by design.

### What landed

**`32e6772` — `~/.jobsearch.ini`** (§3.6). Written by hand rather than by `init`,
because `init` is M1.5 and M1.9 needed `$DATA` resolvable immediately. Holds
`data_root` only, with a comment block stating what belongs in it and what doesn't —
the identity boundary written where someone will actually read it, not only in the
plan. `config.py` gained `--path` (bare path, for consumers) and `--chain` (every
layer, marking the winner).

**`070d823` — 74 references rewritten** to `<DATA>/...` across 9 files, plus a
resolution preamble in `SKILL.md`.

### Three judgement calls inside the "mechanical" pass

1. **`<DATA>`, not `$DATA`** — a deviation from the spelling in the option Michele
   picked, and the reason is concrete: `scan.md:61` and `:70` put the path inside a
   bash command line. `$DATA` there expands to the empty string — nothing exports it,
   and shell state doesn't survive between tool calls — so a pasted command writes to
   `/jobs/scans/...` silently. `<DATA>` can't expand, fails loudly if pasted, and
   matches the `<slug>`/`<ref>` convention already in these files.
2. **74, not ~76.** Keying the rewrite on the seven known data subdirectories rather
   than on `jobs/` meant `company.md`'s two "their jobs/careers page" prose mentions
   were never at risk. Worth noting as method: the sed was made safe by what it
   *didn't* match, not by review afterwards.
3. **Three bare mentions kept on purpose**, with the preamble saying so: the help
   table is printed verbatim to the user, where `<DATA>` is noise not information; and
   `status.md`/`publish.md` mention `jobs/` when describing what a *script* does.
   Leaving them silently would have weakened the rule; stating the exception keeps it.

### The preamble was wrong when first written, and running it caught that

The first draft said: resolve `<DATA>` by reading `~/.jobsearch.ini` first. Running it
from the sandbox showed the problem immediately —

```
via ~/.jobsearch.ini -> .../2026-05-job-search        (the REAL job search)
via config.py --path -> .../jobsearch-sandbox/data    (correct for this checkout)
```

`.ini`-first would have had an agent sitting in the sandbox operate on Michele's live
data: precisely the cross-contamination §5.5's data-truth rule exists to prevent.
Correct order is `config.py --path` first — it applies the full layering, so it
respects a checkout that points somewhere specific — and the `.ini` only when no repo
is reachable. The warning is in the preamble itself, because the failure is silent and
the wrong order looks more convenient.

This is the third time in two days that **only running it split** found the bug.
Step 1 found eight invisible `SITE_ROOT` sites that way; step 2 found the 0-byte sqlite
marker that way; M1.9 found this.

### The symlinks had to go *before* verification, not after

The reason is worth keeping, because it's counterintuitive: while `repo/jobs` pointed
into the data root, a **wrong** bare path still landed in the **right** place. The
sandbox literally could not distinguish correct behaviour from incorrect. So removing
them wasn't cleanup after M1.9 — it was a precondition for M1.9's verification meaning
anything. (They also defeated `looks_like_data_root()`, which reported the repo as a
valid data root because `repo/jobs` resolved to a directory.)

The `.gitignore` trailing-slash fix (`jobs/` → `jobs`) was committed and is kept
permanently: it costs nothing with no symlink present, and guards against committing
one later.

### Verification

Mine, in the split sandbox with no symlinks: a bare `jobs/` path resolves to nothing;
`config.py --path` gives the sandbox data root; both of `application.md`'s real call
sites (the stocktake read at :171, the companies write target at :120) resolve into the
data root rather than the repo or the real job search; `status` unchanged.

**Michele's, which is the one that counts:** ran the skill for real afterwards and
confirmed **every save lands in `~/dev2/jobsearch-sandbox/data`**.
Paths resolving is not the same as watching a file land, and no grep can prove
Markdown — so this was the missing assertion, and it is now made. M1.5's smoke test
should still automate it so it can't rot.

### Carried forward

- **`070d823` and `32e6772` must reach `main` together**, or the preamble's step 1
  (`config.py --path`) returns the `describe()` line instead of a bare path. Neither
  is on `main` yet, deliberately, per the §5.5 trial.
- `scan.md:61` still carries a hardcoded venv path — M1.4's territory, noticed in
  passing, not touched.

---

## Addendum 6 — M1.5 started, and the first bug found by not being Michele

### `example-data/` — the file side (`c890dd6`, sandbox)

A complete fictional job search for **Alex Rivera**, 17 files: `config.yaml`, two base
CVs, two target areas, `areas.md`, stocktake and criteria, ideal-job notes, three
company research files, two application folders (one with a tailored CV and a cover
letter, so the outputs are visible).

**Fictional person, real companies** — §4 constraint 1. Grafana Labs, dbt Labs and Monzo
all have public ATS boards, so `/jobs-search scan` works on a first run instead of
failing against invented companies, which would be the worst possible first impression.

**Both base CVs verified through the real renderer rather than eyeballed**: exported to
`.docx` from a temp data root (39KB, 37KB). That is §4 constraint 3 — "the CV must be
structurally exact" — actually checked rather than asserted. The load-bearing headings
are `## Summary`, `## Core Competencies`, `## Career History`, `## Education`,
`## Skills`, which is what `render.py` and `cv_docx.py` parse.

Application-folder filenames use the `alex-rivera` slug — the correct *end state* after
M1.3 makes the person-slug configurable. `appfolder.app_filename()` still hardcodes
`michele-pasin`, so these were hand-written on purpose rather than tool-generated.

### The bug that fell out of it (`a142d36`, **on `main`**)

Checking that the example filenames were still recognised by the toolkit turned up
something that had nothing to do with the toolkit split.

`appfolder.is_tailored_cv()` matched only `cv_functional`, `cv-functional` and
`cv-chronological`. But **tailored CVs are named after the target area**, not after the
base they came from:

```
004-<company>-<name>-cv-ai-knowledge-work-2026-06-23.md
003-<company>-<name>-cv-data-platform-2026-06-07.md
```

**15 of the 30 tailored CVs in the real repo were not recognised.**

What it broke, via `pick_cv()` → `ensure_folder()`: for those 15, `pick_cv` missed the
tailored CV and returned the **untailored base**. Because the base's own filename
(`cv_functional.md`) wasn't in the folder, refreshing one of those applications would
copy a generic CV in alongside the good tailored one — and would do it again on every
refresh, since `is_tailored_cv` explicitly rejects that basename. Anything asking "which
CV belongs to this application" got the generic answer.

Fix: recognise the convention rather than two special cases — anything
`is_cv_filename()` accepts, minus the two untailored copies. Covers old naming
(`<date>_cv_<target>.md`) and new alike.

**The existing test hid the bug rather than catching it**, and that's the part worth
remembering. `test_pick_cv_prefers_a_tailored_copy_in_the_folder` asserted
`assertIn("cv-functional", picked.name)` — which passed only because application 030
happens to have a `cv-functional`-named CV. The assertion had been written from the
*implementation* rather than from the *convention*, so it encoded the same narrow
pattern as the bug and could never have failed on it. It now asserts
`is_tailored_cv(picked.name)`.

Added `test_is_tailored_cv_recognises_area_named_cvs`: pure filename logic, no fixture
and no folder on disk, so it can't quietly depend on whatever is in one person's job
search. Pins both directions, including old naming and a cover letter as a negative.

Verified: 78 tests, the same 4 pre-existing template-markup failures, no new ones; 0 of
30 unrecognised, down from 15; `pick_cv` returns the tailored CV for applications 2, 3
and 4, which previously fell back to the base.

### Why this matters beyond the one bug

The bug surfaced because `example-data` forced a **different person's filenames** through
the code for the first time. Nothing in the repo had ever run against data that wasn't
Michele's, so an assumption baked into both the implementation *and* its test went
unchallenged for months.

That is a stronger argument for M1.5 than "clear the `dump.json` blocker". Pulling it
forward (§5.3's note) was justified on the grounds that tests would stop depending on
real data; the actual return is that synthetic data **finds bugs real data cannot**,
because real data satisfies every assumption that was derived from it.

### Where M1.5 stands

- ✅ `example-data/` file side — 17 files, CVs render
- ⬜ `backups/django/dump.json` — the synthetic DB fixture, and the release blocker.
  Plan: generate it through the real models (fresh sqlite → migrate → create the rows →
  `db-dump`) so it is valid by construction rather than hand-written JSON that merely
  looks plausible. Companies and applications live only in the DB since Phase 6, so
  this is the only way the example's tracker content can exist.
- ⬜ `/jobs-search init` (§3.2)
- ⬜ The from-scratch smoke test, which is also where M1.9's "watch a file actually
  land" assertion belongs
