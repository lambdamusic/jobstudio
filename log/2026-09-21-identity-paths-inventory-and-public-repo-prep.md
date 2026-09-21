# M1.3, M1.4, M1.1, M1.10 and the public repo prepared — everything but the publishing

**Date:** 2026-09-21 (continues `log/2026-09-21-m15-example-data-init-and-four-bugs.md`)
**Session focus:** Clearing the rest of M1 after M1.5 — identity, the venv path, the inventory pass and its cleanup, the platform fixes, and preparing M1.6 locally.

**Headline:** M1.1–M1.5, M1.9 and M1.10 are all done. The public tree builds and verifies. Nothing has been published — Michele is creating the repo himself and will supply the path.

All work is on the sandbox branch `data-root-move`; plan and log edits go to `main`.

---

## M1.3 — identity comes from the data root (`b2bcdfe`)

`src/identity.py` replaces the hardcoded literals at the three sites that actually
generate output:

| Site | Was |
|---|---|
| `appfolder.app_filename()` | the person-slug in every generated filename |
| `cv_docx.py` | `core_properties.author` — **.docx metadata travels to the employer**, so every user's CV carried the toolkit author's name inside it |
| `render.py` (×2) | the fallback name when a CV has no `# Name` heading |

**A design decision the plan did not specify, and the reason matters.** Resolution is
`config.yaml` → **the base CV's `# Name` heading** → a loud error. The plan had
`config.yaml` as *the* source; that would break every existing user who doesn't have
one yet, and "run `init` first" is a poor answer to someone whose setup already works.
With the second layer, an existing data root keeps working untouched and `config.yaml`
becomes an override rather than a prerequisite. Verified: with no `config.yaml`,
`app_filename()` returns exactly what it did before.

`config.yaml` was, until this commit, **written by `init` and read by nothing**.

Filename *recognition* still deliberately does not key on the slug, so files written
before it was configurable are still found — the §3.4 caveat, and exactly the trap
`is_tailored_cv` fell into.

**The gap that let this live:** the smoke test never created a file, so it could not
have caught a wrong name in one. It now generates an application folder and asserts the
filename carries *this* user's slug:
`042-smoke-test-co-alex-rivera-cover-letter-2026-09-21.md`.

## M1.4 — the venv path (`5f9fc9b`)

32 replacements across 12 files, plus seven `tools/` scripts and `CLAUDE.md`. Scripts
resolve the interpreter with `$JOBSEARCH_PY` as an override and a failure that names
the fix.

**Three things left alone on purpose.** `log/*.md` and `CHANGELOG.md` are dated records
of what was *actually run at the time* — rewriting the commands in them would falsify
the history they exist to preserve. The plan quotes the path as the problem.

`tools/py` was not gitignored. It is generated and holds a personal absolute path, so
it should never have been committable.

**Bug found while doing it:** the README's developer setup **could not work for a new
user** — it said create a venv, then run `tools/py -m pip install`, but `tools/py` is
written by `init`, which runs later. A chicken-and-egg nobody hits because everyone who
has run it already had the file.

## M1.1 — the inventory pass (`fa0ef89`), and its cleanup (`5cca8ec`, `ddc1bb5`)

`backlog/m1.1-inventory.md`: 190 tracked files sorted into never-ships / resolved-now /
must-rewrite. **Two findings were recorded in the plan as already done.**

**1. The real `dump.json` was still tracked at the repo root** — 95 companies, 47
applications, 68 admin log entries, an `auth.user` row with a `pbkdf2` hash and a real
email. §4 called it a release blocker. Building the synthetic fixture and repointing
`FIXTURE_DIRS` made it *unused*; it was then reported as cleared. **Nothing ever
deleted the file.** Removed.

**2. Twelve third-party manual citations survived**, with page numbers, across five
files including a whole "Manual pp." table column. Commit `31e547b` said they were
removed from every shipping file; M1.6 only asks to "verify none crept back". They did
not creep back — they were never fully removed. (Twelve, not the eleven first counted:
my grep used `the manual` and one site reads `The manual's`.)

Schein's career anchors are **kept and still named** — a published framework in its own
right, not part of any one course's materials — with a note saying so, since the
distinction would otherwise be re-litigated or wrongly stripped.

**C2/C3 split the text three ways** rather than renaming uniformly: "Michele" meaning
*the user* → "the user"; biographical facts used as **worked examples** rewritten
(`company.md` inferred company Fit from the author's background — it now reads the
user's own `stocktake.md` and `criteria.yaml`, which is what those files are for;
`cv.md`'s cluster-ordering example spelled out a whole career and now states the rule);
code comments name the role, not the person.

The sidebar was the one that mattered: `base.html` rendered "Michele Pasin · 2026" on
**every page** of the web app, for every install.

**A category the inventory itself missed**, found by sweeping after the named fixes: 21
occurrences of `michele-pasin` inside illustrative **filename patterns**. Since M1.3
made the slug configurable these were *factually wrong* as well as personal —
documentation promising a filename that will never be generated.

## M1.10 — the platform fixes (`a59aceb`)

All three became **settings** in `~/.jobsearch.ini` read through a new
`config.setting()`, rather than `sys.platform` branches — so a third platform is data,
not a code change, which is what "Windows out of scope, revisit on real demand" needs
in order to stay cheap.

- **Chrome:** Linux paths added, then `$PATH` fallback; `chrome_path` overrides.
- **Opening files:** `open` / `xdg-open`, `open_command` overrides. The raw `-R`
  callers passed became `reveal=True` — only macOS has that flag, so **passing it
  through made the function macOS-only by construction**. A missing opener now raises a
  404 naming the setting instead of a `FileNotFoundError` 500 and a stack trace.
- **Editor links:** ten `vscode://file/` literals → one `EDITOR_URL_SCHEME`. Worth
  doing regardless of platform: one editor was hardcoded for every user.

Verified beyond the suite, since none of these have tests: a rendered page carries the
scheme from the setting, shows the example owner in the sidebar, and contains no
occurrence of the author's name. My own `format_html` argument-order bug in `admin.py`
was caught by the admin smoke test.

## M1.6 — prepared, not published (`bcff6fa`, `6e09851`)

`LICENSE` (MIT), `README.md` rewritten for a stranger, `CLAUDE.md` rewritten as toolkit
instructions leading with the `<DATA>` convention, and **`tools/make-public-tree`**,
which copies the tree into a target directory and then *checks* it, refusing to leave
anything carrying personal data.

It enumerates `git ls-files` rather than walking the working tree, so gitignored files
are excluded **by construction** rather than by memory.

**The checks found four leaks three earlier sweeps had missed**, because mine were
case-sensitive and narrower:

| | |
|---|---|
| `cover-letter.md` | a duplicated letterhead block with the real name **and email address** |
| `render-html-pdf.md` | another `michele-pasin` filename pattern |
| `docs/workflow.md` | "in Michele's casual-but-precise voice" |
| `cv-base-format.md` | "Pasin Consulting SAS" in a CV-format example |

**That is the argument for the script over a checklist: the checklist was followed
three times and still left an email address in a file destined to be public.**

Two things the first runs caught. `LICENSE` was silently absent — untracked, so
`git ls-files` skipped it; there is now a required-files assertion. And the script
flagged *itself*, since it greps for the name it is looking for; allowlisted with a
comment, so nobody "fixes" it later by weakening the pattern.

Verified end to end: the generated tree clones, `init`s from scratch against a fresh
data root, and reports the three example applications. 138 files.

---

## The running theme

Counting from M1.5 onward, this sequence has found **nine** defects in code that had
been passing tests for months:

1. `is_tailored_cv` missing 15 of 30 real tailored CVs
2. a three-line `{# #}` rendering into four pages
3. an unanchored gitignore excluding 14 of 17 example files
4. `init` resolving a venv symlink away
5. the README's impossible install order
6. the dump "cleared" but never deleted
7. twelve manual citations "removed" but not removed
8. 21 filename patterns documenting a slug that no longer exists
9. a real email address in a skill reference file

Almost all share one shape: **something was marked done on the strength of the change
that was made, rather than a check that it was finished.** The fixes that stick are the
ones that end in an assertion — `build-example-fixture` refusing to emit a fixture with
`auth.user`, `smoke-test` refusing a generated filename carrying the author's name,
`make-public-tree` refusing to leave a tree with an email address in it.

Worth carrying into M1.8: the clean-room pass is the same mechanism applied to a whole
machine, and on this record it should be budgeted as real work rather than a formality.

## Where things stand

| | |
|---|---|
| M1.1 inventory, M1.2 config, M1.3 identity, M1.4 `tools/py`, M1.5 example data, M1.9 skill paths, M1.10 platform | ✅ |
| M1.6 public repo | prepared locally; **nothing published** — awaiting Michele's repo path |
| M1.8 verification | automated ✅; clean-room and second-person passes outstanding |
| M1.7 Michele's own migration | gated on the §5.5 trial |

78 tests green; `tools/smoke-test` passes; `tools/make-public-tree` passes.

Nothing from the sandbox has reached `main` except the two fixes that belong to the
daily driver (`is_tailored_cv`, the template comment) and the plan/log updates.

---

## Addendum — M1.11, the rename to `jobstudio` (`a357e12`)

M1.11 arrived from a parallel Claude thread as §2e plus a milestone row, and was done
the same day. Sequencing was the substance of the decision: M1.6 cuts a brand-new repo
with no history, so renaming **before** publication costs nothing — no redirects, no
history rewrite, no muscle memory to migrate — and after publication costs a lot.

The survey in the plan had gone stale in the few hours since it was written, because
M1.3–M1.6 added files: **250** `jobs-search` occurrences across 64 files, not the 208
across 61 recorded.

Four kinds of work, and the plan was right to separate them:

- **(a) Prose** — 45 files.
- **(b) The skill** — directory and frontmatter `name:` must agree or the slash command
  breaks. Took the opportunity to fix a `description:` that still read "for the 2026 job
  search repo", and to add `init` to `argument-hint`, missing since M1.5.
- **(c) Live identifiers** — `JOBSTUDIO_DATA`, `.jobstudio-data`, `~/.jobstudio.ini`,
  `[jobstudio]`, and the package name. No back-compat shim: nobody outside this machine
  has the old names, so a fallback layer would be dead code at birth.
- **(d) The gitignored local state**, in the same sitting as (c). Verified with
  `config.py --chain` before and after.

### Three things found doing it

**1. The prose sweep could not see the unhyphenated identifiers.** `settings.py` still
exported `JOBSEARCH_DATA` after `config.py` had moved to `JOBSTUDIO_DATA`, so the suite
ran against the sandbox data root instead of `example-data` — **33 of 78 failed**. The
plan listing (c) as its own category is exactly what this failure looks like when it is
*not* anticipated, and it was.

**2. `~/.jobsearch.ini` had been hand-edited** — pointing at `<root>/jobs` rather than
`<root>`, with a trailing `# comment` that `configparser` keeps **as part of the
value**. Neither was biting, because `main`'s `config.py` predates that whole layer —
but both would have broken the real repo the moment the sandbox work landed. Corrected
in the renamed file, and `ConfigParser` now takes `inline_comment_prefixes` so
annotating one's own settings file cannot silently produce a broken path.

Worth noting as a pattern: this is the second time local, gitignored state has been the
sharp edge (the first was `local_settings.py` not travelling with the branch in §5.3
step 1). Anything outside git is invisible to every check the repo can run on itself.

**3. The Surge domain was hardcoded in four shipping files.** §2e decided — correctly —
not to *rename* `2026jobsearch.surge.sh`, because it is Michele's deployment rather than
the toolkit's identity. But it did not follow that it should not **ship**: every user of
the public repo would have had one person's publish target baked into their copy.
*"Don't rename his deployment"* and *"don't ship his deployment"* are different
requirements and only the first was stated. Now `surge_domain` in `~/.jobstudio.ini`,
failing with instructions when unset — the M1.10 pattern.

### Deliberately not renamed

`log/`, `CHANGELOG.md` and `backlog/` keep the old name: dated records of what things
were called at the time, and excluded from the public tree anyway. Same reasoning that
kept the venv path in them during M1.4.

78 tests green, smoke test passes, public tree builds and verifies at 138 files.

## Addendum 2 — `extras/` moves to the data root, and blocker 6 was wrong twice

Michele: *"that folder is private to me, I want to put it in data"*. 24 files, 7.7MB —
career-coach session notes, third-party copyrighted PDFs, a LinkedIn export, competitor
screenshots. Copied and verified byte-identical before anything was deleted, then
untracked and gitignored as `/extras`.

Checking what referenced it turned up that **§1 blocker 6 was wrong on both of its
claims.**

**"No code reads it."** The *skill* reads it, in two subcommands — `stocktake.md` (the
session notes, the goals file, the anchors questionnaire `.xlsx`, the values-exercise
`.pages`) and `interview.md` (`emotional-intelligence.md`, the framework its EI
question set is built from). The blocker was written from a grep over `src/`, and the
skill is Markdown — the same blind spot as blocker 9, one milestone later.

Worse than personal: those rows sat in source tables **next to `<DATA>/...` rows**, so
they resolved repo-relative. They would have broken for Michele after the split too,
not only for other users — and the public skill was instructing every user to read
files only one person has.

Repointed at `<DATA>/extras/...` and, more importantly, marked **optional**, with the
table stating that most users will have none of them, a missing one is not an error,
and it is not something to ask the user to produce. Without that an agent treats the
absence as a problem to solve and starts asking for coaching notes.

**"It doesn't go in the data root."** Michele's call: it does. It is his data, it is
private, and that is where private things live. The plan's original reasoning — that it
needs no structure and no config entry, so anywhere is fine — was true but answered a
different question than "where does it belong".

Historical mentions ("retired to `extras/retired/`") were reworded rather than
repointed: where a file went in 2026-09 is not something a new user needs to know.

The public tree stays at 138 files — `extras/` was already excluded by the denylist, so
nothing ever shipped. What changed is that it is no longer in git at all.

Also fixed in passing: a sentence my own C3 rename had mangled into "only if the user
sayele says he's redone them".

## Addendum 3 — M1.6 done: `jobstudio` exists

`github.com/lambdamusic/jobstudio`, private for now. Built with
`tools/make-public-tree`, `git init`, one commit, pushed.

**138 files · 1 commit · 0 personal files in history.**

**A separate local checkout was required, and the reason is worth keeping.** The
obvious move is to add a remote to the sandbox and push the branch. That would have
published everything: the sandbox carries **215 commits and 799 personal files ever
tracked**, and `backups/django/dump.json` — 95 companies, 47 applications, a pbkdf2
password hash — is still retrievable from its history. A clean working tree is
irrelevant when `git log` carries the rest, which is exactly why §1 concluded the public
repo had to be a fresh repo rather than a scrubbed one.

So: `dev2/jobstudio`, outside Dropbox for the same reason the sandbox is (no syncing a
git repo that also lives on GitHub).

Verified as an **install**, not as a file listing: cloned it fresh, ran
`init --from-example` from scratch, `status` reported the three example applications,
and the full suite passed (78, OK) against the example data root. That is the same
check `tools/smoke-test` automates, run against the thing actually published.

### Two open questions, flagged rather than drifted into

**Where toolkit development lives from here.** Right now the source of truth is the
sandbox branch `data-root-move` and `jobstudio` is a generated snapshot. That works
once. As an ongoing arrangement it does not — edits in one place, regeneration in the
other, and no path back. The natural end state is `jobstudio` as the toolkit's home with
the sandbox retired, but it should be chosen, not fallen into.

**M1.7 is what actually ends the split-brain.** Until Michele's own setup becomes
"clone of jobstudio + a data root", the real repo remains undivided and the daily driver
is still the old layout.

## Addendum 4 — development moves to `jobstudio`, and the README learns `mkvirtualenv`

**Michele: "toolkit development will live in jobstudio."** Taken at the only moment it
was free: `jobstudio` had just been generated from the sandbox and the two were
byte-identical. Recorded as §5.6, which retires the §5.5 arrangement.

The sandbox keeps two jobs — worked reference for §5.3 step 2 (the data move the real
repo still needs) and trial environment — but is **read-only for toolkit work** from
here. It still holds a complete copy, so nothing but discipline stops someone editing a
subcommand there out of habit, and nothing would catch it.

### Making `jobstudio` actually developable found a gap

Creating `tools/py` by hand was not enough — `local_settings.py` is gitignored and
written by `init`, so the checkout was in exactly the fresh-clone state the smoke test
exercises, and `manage.py test` died on `ModuleNotFoundError: local_settings`. Running
`init` properly (dev data root at `dev2/jobstudio-devdata`, `--skip-global` so the real
`~/.jobstudio.ini` was left alone) fixed it: 78 tests green, smoke test passes, `status`
reports the example data.

Then `git status` showed **`jobstudio.code-workspace` untracked and not ignored** — a
file `init` generates, holding absolute paths for one machine. §5.4 always said it
should be gitignored; nothing had enforced it because until now `init` had only ever run
in temp directories. Ignored now, alongside `tools/py` and `.jobstudio-data`.

That is the third time a generated-and-personal file has needed catching
(`local_settings.py` not travelling with a branch; the hand-edited `~/.jobstudio.ini`;
now the workspace file). The pattern holds: **anything outside git is invisible to every
check the repo runs on itself**, so it only surfaces when someone runs the real thing in
a real place.

### README: both virtualenv routes

Michele uses `mkvirtualenv`; the README documented only plain `venv`. Both are there
now, with the point that matters raised above them: all step 2 needs is the **path** to
the environment's `python` — how it was created is irrelevant to the toolkit.

The genuine wrinkle was that `CLAUDE.md` tells sessions never to use `source` or
`workon`, which reads as contradicting a recommendation to use `mkvirtualenv`. They are
not in conflict, but only if you say why: **create** with whatever you like, **run**
through `tools/py`, because activation does not survive between commands and an agent
session relying on `workon` would silently fall back to the system Python. That is now
spelled out rather than left to be inferred.

## Addendum 5 — the sandbox is retired

Michele: *"can we stop working on ~/dev2/jobsearch-sandbox/ from now
on?"* Yes — but not silently, because one thing still pointed at it.

**`~/.jobstudio.ini` named the sandbox data root as the machine-level default.** That
file exists specifically to answer "where is the data?" when the working directory is
*not* a repo — blocker 9's case, and the reason §3.6 exists at all. Abandoning the
sandbox while that entry stood would have left an agent, started anywhere outside a
checkout, quietly writing into a retired throwaway. Repointed at the real job search:
today the Dropbox repo itself, since it is still undivided; at M1.7 it becomes the
external data root and nothing else about the file changes.

`jobstudio` is unaffected — its own `.jobstudio-data` pointer wins over the global file,
which is exactly the layering §3.6 argued for: per-checkout beats per-machine, so a
development checkout can aim somewhere specific without touching `$HOME`.

**What the sandbox was still nominally for, and why it no longer is.** §5.6 kept it as
the worked reference for §5.3 step 2 — the data move the real repo still needs. But that
reference now exists in a better form: `jobstudio` *is* the post-split layout, running,
tested and published. The branch was never a merge candidate; only its file state
mattered, and that file state is now upstream. M1.7 can be done against `jobstudio`
directly.

⚠️ **It still holds ~33MB of real personal data** — 34 application folders, the 448KB
database with 47 applications, `exports/`, and the 7.7MB `extras/` archive. A stale copy
that nothing backs up and that will drift from the real one. Every original is in the
Dropbox repo, so it is safe to delete; left in place rather than removed unprompted,
since deleting a directory full of someone's job search is not a call to make on their
behalf.

## Addendum 6 — published, relocated, retired, and an admin account that did not exist

### `jobstudio` is live

`github.com/lambdamusic/jobstudio`, private. Built by `tools/make-public-tree`,
`git init`, one commit, pushed: **138 files, 1 commit, 0 personal files in history**.

A separate local checkout (`dev2/jobstudio`) was required rather than pushing the
sandbox branch, and the numbers are the argument: the sandbox carries **215 commits and
799 personal files ever tracked**, with the password-hash `dump.json` still retrievable.
A clean working tree is worth nothing against `git log`. §1 reasoned its way to "fresh
repo, not scrubbed history" long ago; this measured it.

### Development moved, and the sandbox was retired

Michele: toolkit development lives in `jobstudio` (§5.6), then: stop working in the
sandbox at all. Taken at the one free moment — `jobstudio` had just been generated from
it and the two were byte-identical.

**One live dependency had to be cleared first.** `~/.jobstudio.ini` named the *sandbox*
data root as the machine-level default — the layer that answers "where is the data?"
when the working directory is not a repo, which is blocker 9's whole case. Retiring the
sandbox with that entry standing would have left an agent started anywhere outside a
checkout writing into a dead throwaway. Repointed at the real job search.

The sandbox's last justification dissolved too: it was the worked reference for the
§5.3 step 2 data move, but `jobstudio` *is* the post-split layout, running and
published, so M1.7 can be done against it directly. `backlog/TODO.md` `#26` tracks
deleting the directory — it still holds ~33MB of real data (34 application folders, the
database, `exports/`, the `extras/` archive).

### README: `mkvirtualenv`

Michele uses virtualenvwrapper; the README documented only plain `venv`. Both are there
now, with the point that matters raised above them: all `init` needs is the **path** to
the environment's `python`.

The wrinkle was that `CLAUDE.md` forbids `source` and `workon`, which reads as
contradicting a recommendation to use `mkvirtualenv`. Not in conflict, but only if the
reason is stated: **create** with whatever you like, **run** through `tools/py`, because
activation does not survive between commands and a session relying on `workon` would
silently fall back to the system Python.

### The admin account did not exist

Michele: *how do I log into the Django admin with the example data?* You could not.

§3.2 step 5 specified "migrate + superuser bootstrap". The implementation did migrate,
`loaddata` and `import_jobs`, and silently dropped the superuser. Since Phase 6 the
admin **is** the editing surface, and the example fixture deliberately ships no
`auth.user` (a public repo must not carry a password hash) — so every fresh install
could browse everything and change nothing. Silent: the app works right up until you try
to edit.

**The smoke test could not have caught it, because it never logged in.** Same shape as
`app_filename` (nothing generated a file) and the gitignore over-match (nothing cloned):
the checks covered everything except the one path nobody was worried about.

`init` now creates `admin`/`admin` by default — Michele's call — with
`$JOBSTUDIO_ADMIN_PASSWORD` to override, `--admin-user` for the name and `--no-admin` to
skip. No `--admin-password` flag, deliberately: a flag lands in shell history and the
process list. The default is **announced** in `init`'s output with the `changepassword`
command rather than set quietly; it is fine while the server binds `127.0.0.1` and not
fine the moment anyone changes that, and a silent default is the one that gets
forgotten. The README now covers all of it — it had said nothing about the admin at all.

**And then the fix for that gap failed to land.** The commit message claimed the smoke
test now asserts the admin account; the edit had matched against the check's *output*
text rather than the source, failed its assertion, and `git add -A` pushed everything
else regardless. Corrected in `85a950f`, which says so. Twice in a row the work was
done and the verification that it was done was not — which is the exact pattern this
milestone keeps surfacing, reproduced live.

### `CLAUDE.md` in this repo now orients a fresh session

Two coherent worlds now exist on one machine: this repo (live data, `/jobs-search`, no
`tools/py`, pre-split) and `dev2/jobstudio` (toolkit, `/jobstudio`, `tools/py`, external
data root). Each is internally consistent; the danger is starting in one and assuming
the other. `CLAUDE.md` gained a block at the top saying which is which, that toolkit
edits go to `jobstudio` and plan/log edits stay here, that the sandbox is retired, and
that M1.7 is why this repo still runs the old code.
