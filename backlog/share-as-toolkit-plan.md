# Turn the job-search repo into a shareable toolkit

Date: 2026-09-17, substantially revised 2026-09-20
Status: design agreed on the four open decisions (§2); sequencing and milestones
drafted (§6). **Implementation started 2026-09-20**: §5.3 step 1 is done and on the
real repo; step 2 is built and verified **in the sandbox only**. Work now continues
**in the sandbox** and the real repo is not migrated until the layout has been lived
with — see §5.5 for the trial and its data-truth rule. See also §9.

## 0. What changed on 2026-09-20

> **This section records the morning — the design closing.** The same day then went on
> to implementation: §5.3 steps 1 and 2, blockers 9 and 10 found, M1.9 done, and the
> trial of §5.5 decided. **§9 is the live status**; read it rather than inferring state
> from here. Narrative of the whole day:
> `log/2026-09-20-toolkit-migration-steps-1-2.md`.

Michele closed the four open decisions from the first draft, and the answers turned
out to constrain each other tightly enough that the plan is now a design rather than
a menu:

- **2a (distribution)** → GitHub template repo first; `pip`-installable package as
  milestone 2. Both, in that order, not either/or.
- **2b (data location)** → external data directory. The `db.sqlite3` and *all*
  personal data live there, outside the code. A new `init` subcommand scaffolds it
  with sensible defaults for a first-time user.
- **2c (example content)** → ship a **completely synthesised** example dataset — a
  fictional person with a full profile, CV, companies and DB — so the app is
  explorable before it's personalised. `init` replaces it with the real user's data.
- **Anthropic API** → the app is now fully agent-native (`#1`, done 2026-09-17).
  Claude Code runs every default workflow with **zero API key**. This removes what
  would otherwise have been the ugliest part of onboarding.

Plus three additions Michele raised:

- A **migration story** for himself (§5) — how to go from "my data and the code in one
  repo" to "public code, private data", without running a double life. Including the
  ergonomics (§5.4): a VS Code multi-root workspace keeps both folders in one window
  despite the split, and Claude Code needs the equivalent via `--add-dir`.
- **Stretch goal A** (§7): running this from Claude Desktop / Cowork. Researched
  against live docs; turned out *easier* than the first draft guessed, but **parked**
  — see the status box at §7.
- **Stretch goal B** (§8): **driving Claude Code from the local Django app**, so the
  tracker gets buttons that run `/jobs-search` subcommands. Recommended over A, and
  the only item here that needs neither M1 nor M2 first.

Three corrections to the first draft, from a second audit pass and from Michele on
2026-09-20:

- It **materially under-counted the personal data in git** (§1) — ~690 of 810 tracked
  files, not the 162 first recorded.
- **`extras/` isn't part of the app at all** (§1 blocker 6) — a personal archive
  nothing reads, so it stays behind rather than being genericised.
- **The site export is kept but demoted to opt-in** — no longer rebuilt on every
  change, and `site/` is treated as regenerable output rather than data to migrate.

---

## 1. Context — what's actually in the repo today

First audit 2026-09-17; re-audited and corrected 2026-09-20.

**Already separated (existing prior art — build on this, don't reinvent it):**

- `db.sqlite3`, `README_PRIVATE.md`, `tools/env.sh`, `tools/db-bootstrap`,
  `src/web/local_settings.py` are all gitignored already.
- Django config already follows a copy-and-fill pattern:
  `src/web/local_settings_example.py` → copy to `local_settings.py` (gitignored) →
  holds `SECRET_KEY`, `ALLOWED_HOSTS`, DB path. `src/web/settings.py` fails loudly
  with a clear message if `local_settings.py` is missing. **This fail-loudly
  precedent is the model for how the data root should behave** (§3.1).
- `tools/db-bootstrap_EXAMPLE` → copy to `tools/db-bootstrap` (gitignored) → holds
  the superuser name/email/password for the first Django admin account. **This
  gitignored-generated-script precedent is the model for `tools/py`** (§3.3).
- The repo (`git@github.com:lambdamusic/2026-jobs-search`) is currently **private**,
  and the design assumes single-user/private throughout.
- **The site export is kept, but demoted to opt-in** (Michele, 2026-09-20). The
  feature stays — `tools/site-build`, `tools/publish-surge.sh`, the `publish`
  subcommand, `docs/publishing.md` — because it may be useful to some users, and
  keeping it means Michele's own setup needs no change for now. What changes is its
  *status*: it stops being a default step. **The site is no longer rebuilt every time
  something changes**; it's run when someone actually wants a published snapshot.
  Consequences: `site/` is generated output, so it's gitignored and regenerable
  rather than migrated as data (§3.1); the M1.5 smoke test doesn't build it; and the
  "verify everything still works" pass (§5.3) treats `publish` as optional.

### 1.1 Blockers — corrected counts

**1. Personal data in git is ~4× worse than the first draft said.** The first pass
counted `jobs/` only (162 files, now 222). The real picture, from
`git ls-files | awk -F/ '{print $1}' | sort | uniq -c`:

| Tracked dir | Files | Contents |
|---|---:|---|
| `exports/` | 245 | Every rendered CV and cover letter — **docx and PDF, Michele's real CV content** |
| `jobs/` | 222 | Applications, CVs, company research, profile/stocktake, targets, scans |
| `site/` | 179 | The **built static site** — a browsable HTML copy of the entire tracker. Regenerable build output: gitignored and rebuilt on demand, not migrated as data |
| `src/` | 76 | Code (fine) |
| `extras/` | 24 | A personal archive — career-coach sessions, LinkedIn export, competitor dashboard. **Moved to the data root 2026-09-21** and untracked; the skill *did* read parts of it, see blocker 6 |
| `log/` | 21 | Dated session records |
| `.claude/` | 13 | The skill (fine, modulo hardcoded paths) |
| `docs/` | 11 | Internal docs (fine) |
| `backups/` | 1 | `django/dump.json` — **the whole DB as a JSON fixture** |

**~690 of 810 tracked files are personal.** Roughly 15 MB of history. This kills any
"scrub the history of this repo" idea stone dead — the public repo must be a **fresh
repo with fresh history** (§6, M1). It also means `exports/` needs to be gitignored
*and* moved to the data root, which the first draft missed entirely. `site/` is
gitignored and rebuilt on demand rather than migrated — it's generated output, not
data.

**2. Hardcoded absolute personal path** —
`~/Envs/jobssearch2026/bin/python` — appears in **13 files**:
`tools/db-bootstrap`, `db-bootstrap_EXAMPLE`, `db-dump`, `db-load`,
`run-dev-local-db`, `site-build`, `src/web/README.md`, `README.md`, and five
`.claude/skills/jobs-search/subcommands/*.md` files. This is the project's own
documented convention (`CLAUDE.md`: "always invoke the venv's python binary
directly") — deliberately chosen to avoid `source`/`workon` permission prompts on
Michele's machine, and good for that. Bad for portability as written. Fix in §3.3.

All 13 need fixing, the site-export ones included (`tools/site-build`,
`subcommands/publish.md`) — the feature is kept, just opt-in, so it has to be as
portable as the rest.

**3. Hardcoded name "Michele Pasin" in 6 places, not 4.** The first draft found four;
two more turned up:

| Where | What |
|---|---|
| `src/cv_docx.py:325` | docx author property |
| `src/render.py:292`, `:327` | fallback `full_name` when CV parsing finds no name |
| `src/web/templates-global/base.html:16` | site footer |
| **`src/appfolder.py:app_filename()`** | **new** — `michele-pasin` is baked into the *filename convention* for every generated CV and cover letter (`f"{folder.name}-michele-pasin-{filetype}-{d}.{ext}"`) |
| **`.claude/skills/jobs-search/references/cover-letter-structures.md:27,29,40,87,110`** | **new** — name *and* the author's email address are literals in the cover-letter signature block and in the opening-line example |

`subcommands/cv.md:201,205` also documents the `-michele-pasin-` filename shape, and
`README.md:55-56` repeats it in the directory tree.

**4. Personal target-area content ships as "the" targets** — `jobs/targets/*.yaml` has
5 files (`ai-knowledge-work`, `data-platform`, `knowledge-graph`,
`research-intelligence`, `solutions-architect`), all Michele's actual career framing.

**5. `jobs/profile/`, `jobs/cv/base/`, `jobs/notes/`** — the stocktake, criteria, both
base CVs, and the ideal-job/interview-technique notes are all real personal content.
The *generating* flows (`stocktake`, `cv --rebuild`, `interview`) are reusable
mechanisms; they're just never pointed at empty state today.

**6. `extras/` is a personal archive, not part of the app** (confirmed by Michele
2026-09-20). Reference material Michele keeps around: career-coach session notes, a
LinkedIn export, a competitor-intelligence dashboard export, and CV examples.

⚠️ **Two halves of this were wrong, corrected 2026-09-21.**

*"Nothing in the codebase reads it"* — the **skill** reads it, in two subcommands.
`stocktake.md` pulls the career-coach session notes, the goals file, the anchors
questionnaire `.xlsx` and the values-exercise `.pages`; `interview.md` reads
`emotional-intelligence.md`, the framework its EI question set is built from. Those
rows sat in source tables beside `<DATA>/...` rows, so they resolved **repo-relative** —
they would have broken for Michele after the split, not only for other users, and the
public skill was instructing every user to read files only one person has. Now
`<DATA>/extras/...` and explicitly **optional**, with the table saying a missing one is
not an error and not something to ask the user to produce.

*"It doesn't go in the data root"* — Michele's call, 2026-09-21: **it does.** It is his
data, it is private, and the data root is where his private things live. Moved there
(24 files, 7.7MB), untracked, and gitignored as `/extras`. `main` still tracks its own
copy, correctly: that repo is not split yet, and the archive moves with everything else
at §5.3 step 4.

The negative action still stands unchanged:
The only action it needs is a negative one: make sure it's nowhere near the public
repo. That matters because it also contains **third-party copyrighted PDFs** — a
career-transition manual, STAR briefing/template/examples, and JDs supplied by a
coach — which would be a licensing problem, not just a privacy one, if published.

**Resolved 2026-09-20:** the shipping files no longer name that manual at all.
`SKILL.md`, `subcommands/stocktake.md`, `references/cover-letter-structures.md`,
`docs/career-stocktake-profile.md`, `docs/workflow.md`, `jobs/profile/` and the
`profile.html` template all referred to it by name, several with page citations. They
now describe the same method generically ("Step 1 of a structured career-transition
process"). The *structure* was never the copyrightable part and is unchanged; only
the attribution and page references are gone. This closes the one real licensing
exposure in the files that actually ship.

**7. No `LICENSE` file.** Needed before publishing anything. **Decided 2026-09-20:
MIT** — permissive, universally understood, no obligations on anyone who forks the
toolkit to run their own job search. Add at M1.6.

**10. ⚠️ The toolkit is macOS-only in three places, and the README never says so.**
Audited 2026-09-20 after `~/.jobsearch.ini` raised the question of what else belongs in
a machine-level settings file. Nothing here is hard to fix; the problem is that all of
it is currently invisible to someone cloning on Linux.

| Site | Count | What happens off macOS |
|---|---|---|
| `render.py:568-570` — `_CHROME_PATHS`, two `/Applications/...app` paths | 2 | `_find_chrome()` returns `None` → `RuntimeError("Chrome not found…")`. **PDF export dies.** Fails loudly with a semi-useful message, and PDF is the opt-in path (docx is the default), so this is the mildest of the three. |
| `views.py:363` — `subprocess.Popen(["open", …])`, callers `reveal_folder` and one `-R` | 1 fn, 2 callers | `open` doesn't exist → `FileNotFoundError` raised straight out of the view → **Django 500**. Worse than silent: the "Open folder" button hands the user a stack trace. |
| `vscode://file/...` links | **10** — 8 templates, `admin.py:40`, plus `web/README.md` | Degrades quietly (the browser has no handler), so nothing crashes — but it hardcodes one editor for every user of a public toolkit. |

Confirmed **portable** and needing nothing: docx generation is pure `python-docx`; the
one other `subprocess` call (`scan_report.py:313`) uses `sys.executable`.

**Windows is a separate and bigger question.** Everything in `tools/` is bash, and
§3.3's planned `tools/py` wrapper is bash too. Supporting Windows natively is not a
few fixes, it's a second toolchain.

✅ **Fixed 2026-09-21** — all three, as settings rather than `sys.platform` branches
(see M1.10). The README line remains, with M1.6.

**Decided 2026-09-20 (Michele): macOS + Linux only, for now.** Windows is out of
scope — not "supported via WSL", just out of scope; if it runs there, good, but nothing
is built or tested for it. Stated in the public README as a supported-platforms line,
so a Windows user finds out before cloning rather than at the first `tools/` script.

The "for now" is doing real work in that sentence: this is a **scope** decision, not an
architectural one, and nothing here forecloses Windows later. What would reopen it is
someone actually asking — at which point the cost is the `tools/` bash layer and
§3.3's `tools/py`, not the three fixes below. Keeping the fixes settings-driven rather
than branching on `sys.platform` everywhere is what keeps that door open cheaply.

The three fixes (M1.10), which Linux support requires regardless —

1. `chrome_path` in `~/.jobsearch.ini` (§3.6), plus the usual Linux paths in the
   search list. Cheap, and Chrome discovery is exactly what a machine-level setting is
   for.
2. `_open_locally` picks per platform — `open` / `xdg-open` / `start` — which also
   turns a 500 into a working button.
3. The editor scheme becomes **one** setting (`editor_url_scheme`, default
   `vscode://file/`) consumed by a single template tag. The 10 literals are the real
   work here, and collapsing them to one place is worth doing on its own terms.

These are also the first genuinely non-data keys for `~/.jobsearch.ini`, which until
now held only `data_root` — and they confirm the §3.6 line: machine-level settings are
*where things are*, not who you are.

**9. ⚠️ The skill reads and writes data paths directly, and has no notion of a data
root.** Found 2026-09-20, from Michele's question about why the step-2 symlinks were
added. `SKILL.md` and `subcommands/` carry **~80 `jobs/` and `exports/` mentions** —
74 of them real data paths (all rewritten at M1.9), two prose references to a company's
"jobs/careers page", and the rest generic mentions of the data tree rather than paths
to act on —
and the only path convention stated anywhere is `company.md:8` — *"relative to project
root"*. Crucially these are not documentation of where a script writes: they are
instructions the **agent** executes with its own file tools, against the working
directory. Representative:

- `application.md:120` — "**Research and write `jobs/companies/<slug>.md`**"
- `application.md:171` — "Read `jobs/profile/stocktake.md` and `jobs/profile/criteria.yaml`"
- `company.md:73` — "add `jobs/companies/<slug>.md` following the template in
  `jobs/companies/README.md`"

Post-split and without the symlinks, reads fail and — the serious half — **writes land
silently in the code repo**, the one destined to be public. It's the same class of bug
as step 1's eight `settings.SITE_ROOT` sites: a path meaning "the data root" resolving
to the code. The difference is that this one lives in Markdown, so no grep over `src/`
and no test run can catch it.

✅ **Fixed 2026-09-20** (M1.9, sandbox commits `32e6772` + `070d823`). 74 references
rewritten to `<DATA>/...`, `SKILL.md` carries the resolution preamble, and the
symlinks that were masking the problem are gone. **Michele ran the skill for real
afterwards and confirmed every save lands in the data root** — which is the only
assertion that counts here, since nothing mechanical can check a path in Markdown.

**8. Zero-API-key onboarding (good news).** `#1` landed 2026-09-17: CV tailoring
(`subcommands/cv.md`) and default scan scoring (`subcommands/scan.md`) are both
agent-native. The only remaining `anthropic` import is the opt-in
`src/score-candidates.py` (`scan --api`). **A new user needs no Anthropic API key for
any default workflow** — a key is only needed for the headless/cron scan-scoring
fallback. This should be stated prominently in the public README; it's the single
biggest thing that makes this shareable at all.

---

## 2. Decisions — closed

### 2a. Distribution → **A first, then B**

| | Decision |
|---|---|
| **Milestone 1** | **GitHub template repo.** A fresh public repo, "Use this template" button, zero personal data in it or its history. |
| **Milestone 2** | **`pip`-installable package.** `pip install jobsearch` + `jobsearch init` scaffolds a project anywhere. |
| **Rejected** | *C, documented pattern only* — doesn't satisfy "share it with someone else" literally. |

The ordering matters more than it looks: M1 forces the data/code split to be real
(you can't ship a template that only works in Michele's folder), and M1's work is a
strict subset of M2's. M2 then becomes mostly packaging — entry points, a `MANIFEST`,
and moving `src/` under a package namespace — rather than a rethink.

**M2 dissolves a problem M1 only patches.** Once the code ships as a package with
console-script entry points (`jobsearch db status`, `jobsearch scan`, `jobsearch
render ...`), the 13-file hardcoded-venv-path problem (§1 blocker 2) stops existing:
skill docs call `jobsearch …`, not `<some venv>/bin/python src/foo.py`. So don't
over-engineer the M1 fix for it — see §3.3.

### 2b. Data location → **external data directory**

The code reads a configurable **data root**. Everything personal lives there, outside
the repo: `jobs/`, `db.sqlite3`, `exports/`, `backups/`, and the identity config.
Design in §3.1.

This is the option that pairs with *both* distribution milestones (the first draft
noted Option 1 pairs with A and Option 3 with B — in practice Option 3 *is* Option 1
plus packaging, so picking 1 now costs nothing later).

`init` is part of this decision, not an extra: a new user must get a working data root
with meaningful defaults without hand-copying anything. Design in §3.2.

### 2c. Example content → **a complete synthesised dataset**

Ship `example-data/` in the repo: a full, working data root for a **fictional person**
— profile, criteria, targets, both base CVs, companies, a few applications, and a DB
fixture. The app is then explorable from the first minute, before any personalisation.
Design in §4.

### 2d. Hardcoded personal strings → **config + a generated wrapper**

- **Venv path** → `tools/py`, a gitignored one-line wrapper generated by `init`
  (§3.3). Preserves the no-`source`/no-permission-prompt property `CLAUDE.md` calls
  out, and needs no mental substitution by the agent.
- **Name/email** (6 places, §1 blocker 3) → `identity` block in the data root's
  `config.yaml` (§3.4).

### 2e. Name → **`jobstudio`**, unhyphenated, everywhere

Decided 2026-09-21. The project ships as **`jobstudio`** — repo, skill, slash command,
package, import name and config prefix all spelled the same nine characters.

**Why rename at all.** Three reasons, none of them branding:

1. **The current name is three names.** `2026-jobs-search` (repo), `job-search`
   (folder + README title), `jobs-search` (skill + CLI). A public template can't ship
   that, and the drift is already the source of real confusion in this repo's own docs.
2. **`2026-` dates an evergreen thing.** Someone finding it in 2027 reads it as
   abandoned — the same objection that rules out a `py-` prefix or an `-ai` suffix.
3. **"Search" is the smallest thing the toolkit does.** It tracks companies, tailors a
   CV per application, drafts letters, runs gap analysis and rescans ATS portals. The
   name undersells it.

**Why now, and only now.** M1.6 cuts a **brand-new repo with no history** anyway, so
the rename costs nothing today: no redirects, no history rewrite, no migration. After
publication it costs a lot — `/jobs-search` would be in users' muscle memory, the
README, and the PyPI name, and skill names are effectively frozen once published.

**Why `jobstudio`** (candidates checked on PyPI 2026-09-21):

- *studio* is an Italian word carried unchanged into English, French, German and
  (as *estudio*) Spanish — a second-language speaker reads it without decoding a
  metaphor. This ruled out the earlier front-runner **`jobsmith`**: "smith" needs the
  blacksmith metaphor, and worse, Smith is the archetypal English surname, so
  `jobsmith` can read as a person or a recruitment agency.
- In software, `*Studio` reliably means *an environment where you make things* (Visual
  Studio, Android Studio, RStudio). That is what this is — a Django workspace, an
  authoring pipeline, a tracker. **M3** (driving Claude Code from the Django app) makes
  the GUI more central over time, so the name ages in the right direction.
- Free on PyPI; GitHub has only dead toys at that name (top hit 1 star).
- Runner-up **`jobforge`** (also free) was rejected as slightly generic in dev circles
  and a heavier metaphor than tailoring a CV deserves. `applykit` was the safe
  fallback. `jobkit`, `jobhunt`, `tailor`, `pyjobs`, `jobspy` are all taken on PyPI —
  and `jobspy` is an established job-board scraper, a confusing neighbourhood.

**Unhyphenated, because a hyphen can't survive a Python identifier.** `job-studio`
would fork into `job-studio` for pip and `job_studio` for `import` — the
`python-dateutil` → `import dateutil` papercut. Unhyphenated keeps package name,
module, command, repo and config prefix identical, which is worth more than the word
itself. The seam is safe: `jobstudio` joins on `b|s` with no doubled letter, unlike
`jobssearch`, which is precisely why the *old* name needed its hyphen.

**Not renamed** (deliberate, so it isn't relitigated):

- **`2026jobsearch.surge.sh`** — Michele's personal published site, not the toolkit.
  It stays as-is; `site/` is regenerable output excluded from the public repo anyway
  (§1).

  ⚠️ **Refined 2026-09-21 while doing M1.11.** Not renaming it was right, but the
  domain was **hardcoded in four files that ship** (`tools/publish-surge.sh`,
  `subcommands/publish.md`, `docs/publishing.md`, `docs/workflow.md`) — so every user
  of the public toolkit would have had one person's deployment target baked into their
  copy. "Don't rename Michele's deployment" and "don't ship Michele's deployment" are
  different requirements, and only the first was stated. It is now `surge_domain` in
  `~/.jobstudio.ini` (or `$JOBSTUDIO_SURGE_DOMAIN`), failing with instructions when
  unset — the same pattern M1.10 used for `chrome_path` and `editor_url_scheme`.
- **The venv `jobssearch2026`** — a local path on one machine, and M1.4 removes most
  references to it regardless.

Both are the same principle: rename the *toolkit's* identifiers, not Michele's
deployment.

---

## 3. Design

### 3.1 The data root

```
<data-root>/                      # e.g. ~/Dropbox/_MINE/_Jobs/job-search-data/
  config.yaml                     # identity + settings (§3.4)
  db.sqlite3                      # source of truth for companies/applications
  jobs/
    applications/ companies/ cv/ notes/ profile/ scans/ targets/ areas.md
  exports/                        # rendered docx/pdf/html
  backups/django/
    dump-2026-09-20-1432.json     # timestamped dumps, newest wins (§3.1.1)
    dump-2026-09-18-0901.json
  site/                           # generated by tools/site-build on demand; gitignored,
                                  #   safe to delete, never the source of anything
```

**Both the database and its dumps live in the data root** (Michele, 2026-09-20) — the
toolkit repo holds neither. That keeps the private/public line in one place: if it's
about *this person's* job search, it's in the data root; if it's code, it's in the
repo. No exceptions to reason about later.

Note this is the opposite of the arrangement in Michele's current repo, where
`db.sqlite3` became **tracked** on 2026-09-20. That's right for a private single-user
repo and wrong for a public toolkit — the split layout makes the question moot, since
there's no personal database anywhere near the shipped code.

⚠️ **This changes what protects the data, and it's a downgrade worth naming.** Today
the dump is committed, so git is the backup and a bad session is one `git checkout`
away from recovery. In the split layout nothing in the data root is version-controlled
at all — the protection becomes Dropbox's file-version history, which is time-limited
and has no notion of "the state before I ran that command". Timestamped dumps (below)
are the compensating mechanism, and they only work if they're actually written. Worth
making `init` set up a scheduled `db-dump`, or the `publish`/`status` flows call it,
rather than relying on remembering.

#### 3.1.1 Timestamped dumps

`tools/db-dump` currently overwrites one `dump.json`. Michele's request, 2026-09-20:
timestamp them, so a bad write doesn't destroy the last good copy — which is exactly
the failure mode a single overwritten file invites.

- **Name:** `backups/django/dump-<YYYY-MM-DD-HHMM>.json`.
- **`db-load` takes the newest by glob-sort** unless given an explicit path. The
  ISO-ish name sorts lexicographically, so no parsing needed.
- **Retention:** they accumulate at ~220KB each. Keep the last N (say 20) plus the
  first of each month, and prune the rest — decide N when implementing, but don't
  ship unbounded growth into a synced folder.

⚠️ **Coupled to the `FIXTURE_DIRS` split above — do that first, or tests break.**
`src/web/apps/tracker/tests.py:27` pins `FIXTURE = ["dump.json"]`, a literal filename.
Timestamping without first pointing `FIXTURE_DIRS` at `example-data/backups/django/`
leaves the test suite hunting a file that no longer exists. The two changes are one
piece of work, not two.

The code repo keeps `src/`, `tools/`, `.claude/`, `docs/`, `example-data/`,
`backlog/`, `README.md`, `pyproject.toml`, `LICENSE` — and nothing personal.

**Resolution order** for the data root, in one new module (`src/config.py`), imported
by everything that currently computes `ROOT`:

1. `JOBSEARCH_DATA` environment variable, if set.
2. A `.jobsearch-data` file in the repo root (gitignored, one line: the absolute
   path) — written by `init`.
3. **Fail loudly**, with the exact `init` command to run — mirroring what
   `src/web/settings.py` already does for a missing `local_settings.py`.

**Why a pointer file at all, rather than just the env var or `local_settings.py`?**
(Asked 2026-09-20; worth recording, since it looks like redundant machinery.)

- *Env var alone* would have to be set in every shell, every cron entry and every
  Claude Code session. The file answers "where is my data?" for anything that runs,
  from anywhere, with no setup.
- *`local_settings.py`* is tempting — already gitignored, already holds the DB path —
  but `src/appfolder.py` is **deliberately Django-free at module level** (see its
  docstring: the Django app imports its constants, so importing Django there would be
  circular), and `local_settings.py` does `import django` at line 8. Making it the
  source of the data root would force every standalone script to import Django just
  to resolve a path. A plain text file costs nothing and depends on nothing.

**Worked example — how Django reaches a database outside the repo.** sqlite doesn't
care where the file lives; `NAME` is just an absolute path. Two lines change:

```python
# src/web/local_settings.py — SITE_ROOT is already computed here (line 18)
sys.path.insert(0, os.path.join(SITE_ROOT, "src"))   # see ordering note below
import config
DATA_ROOT = config.data_root()

DATABASES = {"default": {..., "NAME": os.path.join(DATA_ROOT, "db.sqlite3")}}  # was SITE_ROOT
```

```python
# src/web/settings.py:96
JOBS_DIR = os.path.join(DATA_ROOT, "jobs")           # was SITE_ROOT
```

Lines 97–104 (`AREAS_MD`, `COMPANY_NOTES_DIR`, `TARGETS_DIR`, `APPLICATIONS_DIR`,
`CV_DIR`, `SCANS_DIR`, `NOTES_DIR`, `PROFILE_DIR`) all derive from `JOBS_DIR`, so they
follow automatically — only line 96 needs touching.

⚠️ **Ordering gotcha.** `local_settings` is imported at `settings.py:16`, *before*
`src/` joins `sys.path` at line 27. So `local_settings.py` must do its own
`sys.path.insert` before `import config`, as above. Small, but a silent
`ModuleNotFoundError` that's easy to misdiagnose.

⚠️ **`FIXTURE_DIRS` (settings.py:91) must NOT move to the data root** — correction to
this plan, 2026-09-20. It was listed below as a data path, but it's where the **test
suite** loads `dump.json` from. Pointing it at the data root would make tests depend
on a personal data root existing and containing that user's records — so they'd fail
on a fresh clone, which is precisely what M1's smoke test exists to catch. Two
different needs share one path today:

| Need | Where it should point |
|---|---|
| Tests loading a stable fixture | `example-data/backups/django/` — **in the repo**, synthetic, committed |
| `tools/db-dump` writing the user's real backup | `<data-root>/backups/django/` — private |

So `FIXTURE_DIRS` stays repo-anchored and only `db-dump`/`db-load`'s default output
path moves. This also gives the M1.5 smoke test a fixture it can rely on.

**Call sites to migrate** (from the audit — `ROOT = Path(__file__).parent.parent` and
its derivatives):

| File | Lines |
|---|---|
| `src/appfolder.py` | 24–25, 150–151, 227 |
| `src/jobsdb.py` | 21, 31 |
| `src/render.py` | 27–31, 669, 690, 820 |
| `src/scan_report.py` | 33–35, 305 |
| `src/score-candidates.py` | 34–37 |
| `src/scan-portals.py` | 44 |
| `src/web/settings.py` | 96 (`JOBS_DIR`) only — **not** 91 (`FIXTURE_DIRS`), see above |
| `src/web/local_settings_example.py` | 39 (DB `NAME`) only — **not** 30 (`STATIC_ROOT`) |

Note the split, which is the whole difficulty of this refactor: `SITE_ROOT`-derived
**code** paths stay anchored to the repo, only **data** paths move. Staying put:
`settings.py` lines 23, 24, 27, 59 (`libs`, `apps`, `src`, `templates-global`), line
91 (`FIXTURE_DIRS` — test fixture, see above), and `local_settings` line 30
(`STATIC_ROOT` — `collectstatic` output is build product of the *code*, not user
data). A mistake here fails silently rather than loudly, so it deserves its own test
in §6.

Also needs auditing for repo-root assumptions (not in the `ROOT` grep): the **104
path references** across `.claude/skills/jobs-search/subcommands/*.md`, which mix
`src/…` (code, stays relative to repo), `jobs/…` and `exports/…` (data, must move),
and `tools/…` (code).

### 3.2 `init`

A new `/jobs-search init` subcommand (and, at M2, a `jobsearch init` CLI command).
What it does:

1. Asks where the data root should live. **Default suggestion: a Dropbox/Drive
   folder** — see §5.2 for why this is the recommended model, not just a convenience.
2. Creates the tree in §3.1.
3. Writes `config.yaml` — asks for name, email, location; everything else defaulted.
4. Writes `~/.jobsearch.ini` (§3.6) — the machine-level settings file. Prompts
   first, since this is outside the project, and never silently overwrites an
   existing one.
5. Writes the four per-user files, all gitignored, all holding the same absolute
   paths so they can't drift apart:
   - `.jobsearch-data` in the repo root — the data-root pointer (§3.1)
   - `tools/py` — the venv wrapper (§3.3)
   - `.claude/settings.local.json` — data root in `permissions.additionalDirectories`,
     so Claude Code doesn't prompt on every access outside the repo (§5.4)
   - `job-search.code-workspace` — the two-folder VS Code workspace (§5.4)
6. Runs the Django migrate + superuser bootstrap (what `tools/db-bootstrap` does
   today, but reading creds from prompts rather than a hand-copied script).
7. Offers three starting points:
   - **`--from-example`** — copy `example-data/` in, so the app is populated and
     browsable immediately. Best first-run experience.
   - **empty** — bare scaffold, then hand off to `/jobs-search stocktake` and
     `/jobs-search cv --rebuild` (or `cv --import <path>`) to build the profile and
     base CVs from a real interview. This is the "genuinely from scratch" path, and
     it already exists as machinery (`#1`) — it has just never been run against empty
     state.
   - **`--import-cv <path>`** — shortcut: scaffold, then `cv --import`.

**One deviation from Michele's framing, deliberately.** Michele described it as: the
example data ships *as* the live data, and `init` wipes and replaces it. Recommend
instead that `example-data/` stays **read-only in the repo** and `init --from-example`
*copies* it into a fresh data root. Same UX, better mechanics: `init` stays
re-runnable and idempotent, there's no wipe step that could destroy real data if
someone re-runs it later, and the example can't accidentally be committed back with a
user's edits mixed in. It also means the example doubles as the smoke-test fixture
(§6, M1.5) for free.

### 3.3 `tools/py` — the venv-path fix

Generated by `init`, gitignored, exactly like the existing `tools/db-bootstrap`:

```bash
#!/usr/bin/env bash
exec ~/Envs/jobssearch2026/bin/python "$@"
```

Every script and skill doc then says `tools/py src/jobsdb.py status` instead of
`~/Envs/…/bin/python src/jobsdb.py status`.

Why this over the two alternatives considered:

- vs. **"just document activating your venv"** — loses the property `CLAUDE.md`
  explicitly protects: no `source`, no `workon`, no permission prompts.
- vs. **a `$JOBSEARCH_PYTHON` env var referenced in skill docs** — would require the
  agent to substitute the value mentally every time it reads a command. Agents follow
  literal, runnable command strings far more reliably than ones needing
  substitution. `tools/py` is literal and runnable.

Touches the 13 files in §1 blocker 2. At M2 this becomes vestigial — the entry points
replace it — so keep the change mechanical and don't build anything on top of it.

### 3.4 `config.yaml` — identity

```yaml
identity:
  full_name: Michele Pasin
  slug: michele-pasin          # used in generated filenames
  email: you@example.com
  location: Your City
site:
  footer_name: Michele Pasin   # defaults to identity.full_name
```

Consumed by all six hardcoded-name sites in §1 blocker 3 — including the two the
first draft missed: `appfolder.app_filename()` (so generated filenames become
`{folder}-{identity.slug}-{filetype}-{date}.{ext}`) and the cover-letter signature
block in `references/cover-letter-structures.md` (which needs to become a
`{{full_name}}`/`{{email}}` template the skill fills from config, since skill
reference files are shared code, not per-user).

**Filename-convention caveat:** `appfolder.is_tailored_cv()` /
`is_cv_filename()` / `is_cover_letter_filename()` already pattern-match on the *old*
naming as well as the new. Making the slug configurable must not break recognition of
Michele's existing 222 `jobs/` files. Match on the `-cv-`/`-cover-letter-` segment,
not on the person-slug — check this explicitly when editing.


### 3.5 Naming convention for copy-me files

The current three conventions (`local_settings_example.py`, `db-bootstrap_EXAMPLE`,
and `jobs/targets/*.yaml` with no convention at all) collapse to almost nothing under
this design: `example-data/` handles the content, and `init` generates the config
rather than asking anyone to copy a file. What's left is the two Django/bootstrap
files — standardise both on a `.example` suffix (`local_settings.py.example`,
`db-bootstrap.example`) and be done.

### 3.6 `~/.jobsearch.ini` — the machine-level settings file

Michele's proposal, 2026-09-20: a global settings file written at `init` time, which
the skill always consults. Adopted, with two boundaries that matter.

**Why a global file earns its place** — and it is not the reason it looks like. The
data root is *already* resolvable via `.jobsearch-data` and `tools/py src/config.py`,
so for a session running in the repo this adds nothing. What it adds is
**findability when the working directory isn't the repo** — which post-split is the
common case, not the edge one: editing `jobs/companies/<slug>.md` means Claude Code is
started in the *data root*, where there is no `.jobsearch-data`, no `tools/py` and no
`src/config.py` to run. A file at a fixed `$HOME` path is reachable from anywhere. That
is precisely blocker 9's failure mode.

**Why `.ini` rather than YAML, which is the house format everywhere else.** Not
arbitrary: `src/config.py` is deliberately **stdlib-only**, because `appfolder.py`
imports it at module level and must stay dependency-free. `configparser` is stdlib;
`PyYAML` is not. Making the bootstrap file YAML would push a third-party import into
the one module every entry point loads first. So the split is principled:

    ~/.jobsearch.ini          bootstrap — stdlib configparser, read before anything
    <data-root>/config.yaml   content — YAML, like every other data file

**Boundary 1 — the per-checkout pointer still wins.** A global file is per *machine*;
`.jobsearch-data` is per *checkout*. Those answer different questions, and right now
this machine needs both: the real repo points at the Dropbox data root while the
sandbox points at a throwaway one (§5.5). A global-only setting would collapse them and
break the trial. Resolution order therefore becomes:

    1. $JOBSEARCH_DATA          per shell — most specific, wins
    2. .jobsearch-data          per checkout — the sandbox case
    3. ~/.jobsearch.ini         per machine — the new default layer
    4. error                    (never a silent fallback; see §5.3 step 2)

**Boundary 2 — identity does not move here.** `config.yaml`'s `identity` block (§3.4)
belongs to the *job search*, not the machine, and §4 ships `example-data/config.yaml`
with a fictional person precisely so the app is explorable before it's personalised
(decision 2c). Putting name and email in `~/.jobsearch.ini` would break that. The line
to hold:

    machine-level (.ini)   where things are, and per-machine preferences:
                           data_root (today, the only key); and at M1.10
                           chrome_path and editor_url_scheme, which are exactly
                           the hardcoded macOS assumptions in blocker 10
    search-level (.yaml)   who you are and how you search: identity, cv_base
                           default, target areas — travels with the data, and is
                           synthetic in the example

✅ **Written by hand 2026-09-20**, ahead of `init` — M1.9 needed `$DATA` resolvable
immediately and `init` is M1.5, so the file exists now and `init` adopts it later. It
holds `data_root` only. `src/config.py` reads it (sandbox `32e6772`), with `--path`
for consumers and `--chain` for diagnosis.

**Two costs, accepted rather than discovered later.** Any layered config acquires a
"why isn't it picking that up" failure mode, so `config.describe()` must print the
whole resolution chain and which layer won, not just the answer — it already exists and
is already wired into `status`. And `init` writing into `$HOME` is more invasive than
writing inside the project: it must say so, and must never silently overwrite an
existing file.

---

## 4. The example dataset

`example-data/` — a complete data root for a fictional person. Sketch:

```
example-data/
  config.yaml                    # "Alex Rivera", fictional email/location
  jobs/profile/stocktake.md      # a plausible, complete stocktake
  jobs/profile/criteria.yaml
  jobs/targets/*.yaml            # 2 target areas, not 5
  jobs/cv/base/cv_functional.md  # full fictional CV, correct structure
  jobs/cv/base/cv_chronological.md
  jobs/notes/ideal-job-notes.md
  jobs/companies/*.md            # 3-4 company research files
  jobs/applications/00N-*/       # 2-3 application folders, incl. one tailored CV
                                 #   + cover letter, so the outputs are visible
  backups/django/dump.json       # DB fixture: the companies + applications above.
                                 #   Keeps the FIXED name — this is the test fixture
                                 #   (tests.py pins "dump.json"); only the user's own
                                 #   dumps in the data root are timestamped (§3.1.1)
```

Three design constraints that aren't obvious:

1. **Fictional person, real companies.** The `scan` feature hits *live* ATS APIs
   (Greenhouse, Lever, Workable, Workday, Ashby, SmartRecruiters, Teamtailor,
   Rippling). If the example ships fictional companies, `/jobs-search scan` — one of
   the most impressive things the toolkit does — is **broken on first run**, which is
   the worst possible first impression. So: invent the person, the profile, the CV
   and the applications; use a handful of **real, well-known companies with public
   ATS boards** for the tracker. Their careers pages are public information; nothing
   personal is disclosed.
2. **Ship a DB fixture, not a `db.sqlite3`.** `backups/django/dump.json` round-trips
   through the existing `tools/db-load` / `tools/db-dump` machinery, is diffable in
   review, and survives Django model migrations. A committed binary sqlite file does
   none of those. This file now has a **second job**: it's what `FIXTURE_DIRS` points
   at, so the Django test suite loads it too (§3.1). That raises its bar — it has to
   stay valid against the models, not just look plausible — but it's the right
   trade: tests stop depending on whatever happens to be in Michele's database.
✅ **Cleared 2026-09-21** (`3c90ee4`). The synthetic fixture is generated through the
real models by `tools/build-example-fixture`, which also *asserts* that no `auth.user`,
no `admin.logentry` and no real identity appear in its output — so a regression fails
the build rather than reaching a commit. The original finding, kept because it explains
why the check exists:

⚠️ **`backups/django/dump.json` as it stood was a release blocker, not a
placeholder.** Michele flagged this on 2026-09-20 and it's worse than "personal data".
Verified contents of the committed fixture: **95 companies, 47 applications, 86 status
changes, 68 admin log entries**, and one `auth.user` row carrying a **`pbkdf2_sha256`
password hash and the author's email address**. It is the whole job search plus a
credential hash, in a single file, in the repo root — and unlike everything else in
§1's inventory it is **not** under `jobs/` or `exports/`, so the data-root move does not
carry it away. It stays behind in the code repo *by design* (§3.1: `FIXTURE_DIRS` is
repo-anchored), which is exactly what makes it easy to miss.

Two things follow. It has to be **synthetic before the public repo's first commit**, not
before its first release — with no history there is nothing to scrub later (M1.6). And
the check belongs in the M1.5 smoke test as an assertion, not in someone's memory: fail
if the fixture contains any `auth.user` with a usable password hash, or any email
outside the example domain.

3. **The CV must be structurally exact.** `src/render.py` and `src/cv_docx.py` parse
   the base CVs, and `references/cv-base-format.md` defines the contract. A
   loosely-written example CV will produce broken renders for every new user and look
   like a bug in the toolkit. This file is the highest-risk piece of the example set —
   generate it by running `cv --rebuild` against the fictional persona rather than
   hand-writing it.

**Bonus:** `example-data/` is also the fixture for the automated from-scratch smoke
test (§6, M1.5). Same artefact, two jobs.

---

## 4a. What building the example found

Four bugs, none of them about the toolkit split, all of them passing tests for months.
Recorded together because the *cause* is common and will apply again at M1.8.

| | Where | |
|---|---|---|
| `is_tailored_cv()` matched only `cv-functional`/`cv-chronological`, but tailored CVs are named after the **target area** | `appfolder.py`, fixed on `main` `a142d36` | **15 of 30** real tailored CVs unrecognised; `pick_cv()` fell back to the untailored base and a refresh copied a generic CV in beside the good one, every time. Its test asserted `assertIn("cv-functional", …)` — written from the implementation rather than the convention, so it encoded the same pattern as the bug and could never fail on it. |
| A three-line `{# … #}` in `_app_table.html`; Django's `{# #}` is **single-line only** | fixed on `main` `235a031` | All three lines rendered into `/`, `/applications/`, `/applications/all/` and `/areas/`, visible to readers. Carried as "4 pre-existing failures, unrelated" through every migration commit — by a test written specifically to catch it. |
| An **unanchored** gitignore pattern matches every path component of that name at any depth | `4fab6e3` | Step 2's `jobs/` → `jobs` fix (for symlinks) silently excluded `example-data/jobs/`: **14 of 17 files never committed** while the working tree looked complete. Correct form is `/jobs` — anchored *and* unslashed. |
| `Path(venv_python).resolve()` follows a virtualenv's `bin/python` to the system interpreter | in `60c39fb` | Lost the venv's site-packages, so Django was unimportable and every `manage.py` call failed. |

**The common cause.** All four surfaced because the code ran against data that wasn't
Michele's for the first time — a different person's filenames, a different fixture, a
clean clone with none of the gitignored files. **Real data satisfies every assumption
derived from it**, which is precisely why it cannot find this class of bug.

That reframes why M1.5 was worth pulling forward (§5.3). The stated reason was getting
tests off personal data; the actual return is that synthetic data finds bugs real data
cannot.

**Two of the four were found by the *clone* step rather than by the synthetic data** —
the gitignore over-match and the venv resolve. That is the same mechanism M1.8's
clean-room pass applies to a whole machine, so expect it to find things too, and budget
for that rather than treating M1.8 as a formality.

---

## 5. Michele's own migration

The question Michele raised: how do you go from "I develop the app and use it with my
data, in the same repo" to "the app is public and my data stays private", without a
painful double life?

### 5.1 One repo, not two

**Recommendation: one public repo. Michele develops in it and uses it, with his data
in the external data root like everyone else.** The alternative — a private dev repo
plus a sanitised public mirror — means every change needs syncing and every commit
needs checking for leaked personal content. That's a permanent tax for no benefit.

Mechanically, because the history can't be scrubbed (§1 blocker 1):

- **New public repo, fresh history.** `2026-jobs-search` (current, private) is kept
  as-is, private, as an archive — it holds `log/`, `CHANGELOG.md` and the full
  development history, which is worth keeping but not worth publishing.
- The public repo starts from a clean copy of `src/`, `tools/`, `.claude/`, `docs/`,
  `example-data/`, plus a fresh `README.md`, `LICENSE` and `CHANGELOG.md`.
- `log/` and `backlog/`: judgement call. `backlog/` is toolkit-development material
  and can go public (this file included, minus personal specifics). `log/` mixes
  design rationale with personal job-search context — **default to leaving it in the
  private archive**, and lift anything genuinely reusable into `docs/`.

### 5.2 Where Michele's data goes — and the model

`~/Dropbox/_MINE/_Jobs/job-search-data/` — a **sibling of the current repo**, which is
itself already inside Dropbox (`~/Library/CloudStorage/Dropbox/_MINE/_Jobs/…`). So
there is zero sync setup: the data root is already in a synced, backed-up, shareable
location on day one.

This generalises into the model to document for other users, and it's the right one:

> **The data you produce is always yours.** The toolkit is code you install or clone;
> your job search — applications, CVs, notes, research — lives in a folder you own, in
> your own Dropbox or Drive. Uninstall the toolkit and your data is untouched. Switch
> machines and it follows you. Share a folder and you've shared your search with a
> coach or a friend, without sharing the tool.

Two caveats worth writing into the docs rather than discovering the hard way:

- **sqlite on a sync service is single-writer.** One machine at a time is fine (and
  is Michele's situation). Two machines with the app open can corrupt the file or
  produce Dropbox conflict copies. Mitigation: **timestamped `tools/db-dump` output**
  (§3.1.1) is the documented durable backup — and since nothing in the data root is
  version-controlled, it's the *only* one, which is why it can't be left to memory.
  Worth considering a `--warn-if-synced` check in `init` that detects a
  Dropbox/iCloud/Drive path and prints this once.
- **`exports/` will be the bulk of the bytes** (245 files today, mostly rendered PDFs
  and docx). It's *regenerable*. Consider putting it under the data root but outside
  whatever the user backs up, or accepting the sync cost — document the choice either
  way. (`site/` is comparable in size at 179 files, but it's generated on demand and
  gitignored, so it never needs syncing or backing up at all.)
- **⚠️ A synced data root is the configuration Cowork warns against.** Anthropic's
  guidance is that a work folder inside Dropbox/iCloud/Drive is "a real source of weird
  bugs" for Cowork — version confusion, pending syncs, conflict copies (§7.3). This
  does **not** affect Claude Code, which is the primary and only supported path through
  M1 and M2, so the Dropbox model above stands as written. But if M3 (§7) is ever
  pursued, revisit: the likely answer is data root on local disk, with Dropbox holding
  `backups/` and `exports/` only. Worth knowing now rather than after the move.

### 5.3 Order of operations (no big-bang)

The safe sequence, each step verifiable before the next:

1. ✅ **Done 2026-09-20** (`ac65d99`). Built `src/config.py` and migrated the call
   sites (§3.1) — still resolving to the current in-repo locations, so nothing moved
   and nothing changed. Two findings worth carrying forward:
   - **The §3.1 call-site table had a blind spot.** Eight further sites use
     `settings.SITE_ROOT`, not `ROOT = Path(__file__)`, so no grep for the latter
     could see them: `admin._abs`, `Note.body_md`, `views._open_locally`, the
     folder-create view, `import_jobs.rel` and its `handle()`, `build_static`'s
     output dir, `cvs.BaseCv.full_path`. **Every one meant "the data root"** —
     `settings.SITE_ROOT` is never used as a code path in app code.
     `views._open_locally` is the one to remember: a security guard refusing paths
     outside the repo, which would have refused every real file post-split.
   - **Only running with the data actually split found them.** Testing that nothing
     changed passes happily with all eight bugs present. Any future step here needs a
     deliberate split run, not just a regression run.
   - ⚠️ **`src/web/local_settings.py` is gitignored, so its edit doesn't travel.**
     Pulling the branch into the real repo left `DATA_ROOT` undefined and Django
     refused to start. Hand-applied there; `init` must write this block for new users
     (§3.2), and the example file carries it for anyone copying by hand.
2. ⚠️ **Done in the sandbox only, 2026-09-20** (`8dbf513`, branch `data-root-move`
   in `dev2/jobsearch-sandbox/repo`). **Not pulled into the real repo** — the real
   repo still holds `jobs/`, `exports/`, `site/` and `db.sqlite3` in-tree with no
   `.jobsearch-data`. What the sandbox commit does:
   - Moves `jobs/`, `exports/`, `site/` and `db.sqlite3` into the data root —
     copied and verified byte-identical before anything was deleted, no bare `mv` on
     real data. Tracked files 810 → 163.
   - Splits `backups/` per §3.1: `<repo>/backups/django/dump.json` stays as the
     frozen test fixture (`tests.py` pins the literal name); the user's real,
     timestamped dumps go to `<data-root>/backups/django/`. That split is what
     unblocked §3.1.1 — `db-dump` keeps the 20 most recent (`--keep N`) and refuses
     to keep a dump that is empty or not valid JSON; `db-load` always passes an
     absolute path so `loaddata` can't resolve a name through `FIXTURE_DIRS` and
     quietly restore the test fixture over real data.
   - Makes `config.data_root()` fail loudly: the `REPO_ROOT` fallback is honoured
     only if the repo still holds data. **Marker subtlety found only by testing it:**
     Django creates `db.sqlite3` the moment it opens a connection, so one failed run
     in an unconfigured checkout leaves a 0-byte file that would make that directory
     look like a valid data root forever after. A *non-empty* database is required.
   - Verified split: `status`, `site-build` (182 pages, link check clean), 77 tests
     with the same 4 pre-existing failures as the untouched backup. Error paths
     checked individually: nothing configured, 0-byte db, non-existent path, empty
     directory.
   - ✅ **`extras/` moved into the data root 2026-09-21** (Michele's call), untracked
     and gitignored. It is private data and the data root is where private data
     lives. The skill's optional reads of it are now `<DATA>/extras/...` — see
     §1 blocker 6, which was wrong on both counts.
   - ✅ **Resolved 2026-09-20.** The symlinks left uncommitted here (`repo/jobs`,
     `repo/exports`; `site` was never linked) turned out to exist because the skill's
     relative paths broke without them — blocker 9. They were removed with M1.9; the
     `.gitignore` trailing-slash edit (`jobs/` → `jobs`) was committed and kept as a
     permanent guard. See §5.5.
3. **Keep building in the sandbox and live with it for a while** — see §5.5. This
   step was inserted on 2026-09-20 and it reorders everything after it.
4. ✅ **Done 2026-09-21 — but not as written.** The plan said "redo step 2 against the
   real repo": copy the data out, then `git rm` it and strip the old repo down. **Michele
   chose to copy and freeze instead** — the data was copied into
   `_Jobs/jobstudio-data` and *nothing was deleted from the old repo at all*. It keeps
   its code, its data and its history, and is marked read-only in its `CLAUDE.md`.

   Why that is better, and it is worth stating because the original was more elegant:
   **the destructive half of this migration bought nothing.** Its only purpose was to
   stop the old repo being confusable with the live one — and a `CLAUDE.md` that says
   "⛔ read-only archive, the live search is over there" does that for free, while a
   `git rm` spends the one irreversible action in the whole plan to achieve it. The
   copy was verified byte-identical before anything depended on it (688 files, plus
   sha256 on the database and the dump), so there is no window in which the data
   existed in only one place. Disk is cheap; an unrecoverable mistake is not.

   The residual risk is the one §5.6 named for the sandbox — a stale second copy that
   drifts — and it is accepted deliberately here rather than overlooked: the archive
   is frozen and labelled, not live and forgotten.

   ~~Redo step 2 against the real repo, once §5.5's trial says the layout is right.~~
   The destructive half, and the order matters: copy the real data to a real data
   root and write `.jobsearch-data` **first**, hand-apply the `local_settings.py`
   block (gitignored, so it doesn't travel — see step 1), verify the full workflow
   end-to-end (`status`, `application`, `cv`, `cover-letter`, `render-html-pdf`,
   `scan`), and only then `git rm` the data from the private repo and take the
   gitignore entries.
5. ✅ **Done 2026-09-21**, out of order — M1.6 landed before step 4 rather than after. Stand up the public repo (§6, M1.6) — brand new, **no history**.

Step 4's verification is the real gate. Everything else is reversible.

**Where to do the work — the sandbox (set up 2026-09-20).** Michele uses this repo
every day and can't afford to be stuck if the migration goes wrong. The instinct is a
branch; **a branch is the wrong tool here**, and the reason is worth stating because
it's counterintuitive:

> The dangerous files aren't the code — they're `db.sqlite3`, `jobs/` and `exports/`.
> `db.sqlite3` is **gitignored**, so git isn't protecting it at all: switching
> branches won't restore it and `git reset --hard` won't either. And by design the
> data root lives *outside* the repo, so it's shared across every branch and
> worktree. A branch isolates exactly the files that were never at risk.

The setup instead:

```
~/dev2/jobsearch-sandbox/repo   # git clone of the real repo
~/dev2/jobsearch-sandbox/data   # throwaway data root
~/dev2/jobsearch-backups/2026-09-20-pre-toolkit-migration
```

Outside Dropbox deliberately: no syncing a throwaway duplicate, no Dropbox
conflict-copies while files are being thrown between folders, and no
sqlite-on-a-sync-service hazard (§5.2) confusing a test failure with a real bug.

A clone doesn't bring the gitignored files — `db.sqlite3`,
`src/web/local_settings.py`, `tools/db-bootstrap`, `tools/env.sh`. Copying them in by
hand is **the rehearsal**, since those files are exactly what the migration is about.
Work flows back with a normal `git pull` from the sandbox path.

**Three safety nets, done 2026-09-20 before any of this:** pushed all commits to
GitHub; refreshed `backups/django/dump.json` via `tools/db-dump` (the only
version-controlled record of applications and companies, since `db.sqlite3` is
gitignored — it had drifted, 43→47 applications, 92→95 companies); and took a dated
full-folder copy to `dev2/jobsearch-backups/`.

**Two things that reduce risk more than the sandbox does:**

1. **Step 1 above needs no sandbox at all.** Building `src/config.py` and migrating
   the call sites *while they still resolve to the current in-repo locations* changes
   no behaviour and moves no data — and it's the fiddly, silent-failure-prone part of
   the job. Land it on the real repo, normally. The sandbox only earns its keep from
   step 2 on.
2. **Pull M1.5 (`example-data/`) forward, out of order.** Nothing forces it to be
   fifth. Built early, every test runs against a synthetic data root and Michele's
   real job search never participates in a test at all — a far better trade than any
   amount of sandboxing.

### 5.4 Day-to-day ergonomics — two folders, one workspace

The obvious objection to splitting code from data is that Michele would spend his day
flipping between two places. He doesn't have to (Michele, 2026-09-20): **a VS Code
multi-root workspace holds both folders in one window**, even though they're separate
directories with separate git repos.

```jsonc
// job-search.code-workspace
{
  "folders": [
    { "path": "/path/to/jobs-search",      "name": "toolkit (code)" },
    { "path": "/path/to/job-search-data",  "name": "my job search (data)" }
  ]
}
```

What this buys: one window, file-open and search spanning both, and — the part that
matters for the split — **Source Control shows both repos separately**, so commits to
the public toolkit can't accidentally sweep up personal data. That's a safety property,
not just a convenience: it makes the boundary visible at exactly the moment it's easiest
to cross by accident.

Two practical notes:

- **The workspace file itself contains Michele's absolute paths**, so it's personal.
  `init` should generate it (gitignored) rather than the repo shipping one — same
  pattern as `tools/py` and `.jobsearch-data` (§3.2, §3.3). Ship a
  `job-search.code-workspace.example` if a starting point is wanted.
- **⚠️ Claude Code needs the same treatment, and this is easy to miss.** A session
  started in the code repo treats the data root as outside its working directory and
  will prompt on every access. Fix: `claude --add-dir <data-root>` (flag confirmed
  present in the installed CLI), or better, the durable form — add the data root to
  `permissions.additionalDirectories` in `.claude/settings.local.json`, which `init`
  can write at the same time as everything else. Without this, every session after
  the migration gets noticeably more annoying than today's single-folder setup, which
  would be a bad first impression of the new layout — for Michele *and* for anyone
  following the README.

---

### 5.6 Where the toolkit lives now — decided 2026-09-21

**Toolkit development moves to `github.com/lambdamusic/jobstudio`** (local checkout
`dev2/jobstudio`), effective immediately. Michele's call, taken at the right moment:
`jobstudio` was generated from the sandbox and the two were byte-identical, so there was
nothing to reconcile. A week later there would have been.

This retires the arrangement §5.5 set up. What each thing is now:

| | |
|---|---|
| `dev2/jobstudio` | **The toolkit.** All code, skill and docs changes land here. Public repo (private until Michele flips it). |
| `dev2/jobstudio-devdata` | Its development data root — the example dataset, so the checkout is runnable and self-contained. Not anyone's real job search. |
| `dev2/jobsearch-sandbox` | **Retired entirely, 2026-09-21** — Michele's call, not just read-only. Nothing is to be run or edited there. Its worked reference for §5.3 step 2 survives as the *file state of `jobstudio`*, which already is the post-split layout, so the branch itself is no longer needed to do M1.7. Its GitHub branch `data-root-move` stays as history. ✅ **Deleted 2026-09-21** (TODO `#26`), after M1.7 rescued its one unique file. What follows is why it could not simply be left alone: its **data root held ~33MB** — 34 application folders, the 448KB database, `exports/`, and the `extras/` archive — a stale copy of Michele's real job search that nothing backs up and that will silently drift. Delete it when convenient; the originals are all in the Dropbox repo. |
| the Dropbox repo (`main`) | Still the daily driver, still undivided, and still where **this plan, `log/` and `backlog/` live** — none of which ship, so they stay private by design. |

**One live dependency had to be cleared before the sandbox could be abandoned:**
`~/.jobstudio.ini` pointed at the sandbox data root. That file is the layer that answers
"where is the data?" when the working directory is not a repo (§3.6) — precisely
blocker 9's case — so leaving it aimed at a retired directory would have meant an agent
writing into a throwaway copy. Repointed at the real job search (today the Dropbox repo
itself, pre-split; at M1.7 it becomes the external data root).

**The thing to avoid is editing the toolkit in two places.** The sandbox still contains
a full copy of it; nothing stops someone changing a subcommand there out of habit, and
nothing would catch it. Treat `dev2/jobsearch-sandbox/repo` as read-only from here.

✅ **Resolved 2026-09-21 by M1.7 — see §5.7.**

~~**Still outstanding:** §5.3 step 4 / M1.7 makes Michele's own setup a clone of
`jobstudio` plus a real data root. Until then his daily driver runs the pre-split code,
and the two do genuinely diverge — the sandbox's toolkit is now behind `jobstudio`.~~


---

### 5.7 The end state — M1.7, 2026-09-21

The migration is done. Three directories, each with exactly one job:

| | |
|---|---|
| `dev2/jobstudio` | **The toolkit, and the daily driver.** Development and real use happen in the same checkout, which is what §5.1 argued for. `backlog/` and `log/` live here now, so the planning sits beside the code it plans. |
| `_Jobs/jobstudio-data` | **The real job search.** `jobs/`, `exports/`, `site/`, `extras/`, `backups/`, `config.yaml`, `db.sqlite3`. In Dropbox, so it is synced and backed up with no setup (§5.2). Named by `~/.jobstudio.ini`. |
| the old pre-split repo (`2026-05-job-search`) | **Read-only archive.** Frozen, not stripped. Michele is relocating it to `~/dev2/jobsearch-backups/` alongside the pre-migration snapshot — nothing functional points at it, so its path is not load-bearing anywhere. Holds the full development history and the 21 older `log/` entries that do not ship. Its `CLAUDE.md` is now a redirect. |

**The decision with teeth: a bare command resolves to the real data.** Deleting
`dev2/jobstudio/.jobstudio-data` means resolution falls through to `~/.jobstudio.ini`,
so `tools/py src/jobsdb.py status` in the toolkit checkout reads Michele's actual job
search. The alternative — pointer left at the example data, real work needing an env
var — is safer by default but wrong by frequency: real use is the common case and
development is the exception, so the exception is the one that should carry the
ceremony (`JOBSTUDIO_DATA=... tools/py ...`).

That trade is only acceptable because the two things that run most often defend
themselves rather than relying on anyone remembering: **the test suite pins
`$JOBSTUDIO_DATA` to `example-data/`** in `settings.py` before `local_settings` is
imported, and **`smoke-test` works in a temp clone**. Both were re-run after the
repoint and neither touched the real data root. What is genuinely exposed is an ad-hoc
script run while developing a code path that writes files — which is now called out in
`CLAUDE.md`.

**`backlog/`, `log/` and `CHANGELOG.md` became public, reversing the M1.6 position.** Michele's call:
nothing in them is secret, and they are the rationale for the code shipping beside
them. `log/` was seeded with only the three toolkit-migration entries; the other 21 mix
design notes with personal job-search context and stay in the archive.

The changelog was carried over from the private repo and edited down: the entries record
what changed in the *code*, so they were worth keeping, while one person's job-search
specifics — tracked companies, application numbers, career-anchor scores, a salary floor,
a former employer — were cut or genericised. It also gained entries for M1.1–M1.7, which
had until then existed only as `log/` narrative.

This forced a fix in `tools/make-public-tree`, and the shape of the bug is the
interesting part. All three were on its `DENY` list. Leaving them there would
**not** have kept them private — they live in the public repo now, so they ship
regardless. It would have meant the copier skipped them, every check ran on a tree that
did not match what is published, and the tool reported `PUBLIC TREE OK` for files it had
never read. A denylist that silently disagrees with reality is worse than either
shipping or withholding. Both moved to the name/citation exemptions instead, with the
reason written down: these are signed design documents about their author's own
migration — anonymising them would gut them (§5 is literally "Michele's own migration"),
and the guard exists to stop job-search *content* leaking, not to hide who wrote the
toolkit, whose name is on the `LICENSE` and every commit.

Running it after the change **caught two real things** and is why the tool is worth
keeping: the citation check fired on `m1.1-inventory.md` and a log entry that quote the
`Manual pp.` strings *while recording their removal*, and then fired on its own new
comment. Both are now path-scoped.

**Scrubbed on Michele's instruction, same day.** His email address (4 places) and every
absolute home-directory path (13 places) came out of `backlog/` and `log/`.
The paths became `~/...`, which is shorter, still accurate, and true on anyone's machine;
the email became either `you@example.com` in the example `config.yaml` or the phrase "the
author's email address" where the point was *that the literal appeared somewhere*, not
what it was.

**That bought back a real check, which is the reason it was worth doing beyond taste.**
`make-public-tree` used one exemption list, `ALLOW_NAME`, for both the author-name check
and the absolute-path check — so exempting `backlog/` and `log/` from the first
necessarily exempted them from the second. With the paths gone they no longer need that
exemption, so the two lists are now separate: `ALLOW_NAME` still covers them (the byline
is deliberate and unavoidable), `ALLOW_PATH` does not. A future plan document pasting a
real home path is now caught instead of inherited-permission'd through. Verified by
planting one and watching the build refuse. The one bare home-path literal left — in
`m1.1-inventory.md`, *describing* a path it had removed — was rephrased rather than
exempted, so the check needs no special cases at all.

**One rescue.** `backlog/m1.1-inventory.md` existed only in the retired sandbox — written
during M1.1, never copied to the Dropbox repo, and referenced by `make-public-tree`. It
would have been destroyed by TODO `#26`. It is now in `jobstudio/backlog/`.

**Cleared the same day.** Michele deleted the retired sandbox (52MB, TODO `#26`) and the
duplicate example data root `jobstudio-devdata2`, keeping `jobstudio-devdata` as the
scratch root for exercising the example data. The workspace file and
`.claude/settings.local.json` were repointed at it. Nothing pointed at either deleted
directory — that was checked before, not after.

**Still open: M1.8 alone** — the clean-room pass on a different machine or user account,
then a second real person. The automated third of it already passes.

---

### 5.5 The trial period — build in the sandbox, don't touch the real repo

Michele, 2026-09-20: keep building in the sandbox and use it for a while before the
real repo is migrated. Not a delay — a different order. The real migration (§5.3
step 4) becomes the *last* thing that happens rather than the next.

**The data-truth rule, and it is the one that matters:**

> **The real repo stays the daily driver.** Applications get logged, scans get run and
> CVs get rendered *there*, against the undivided layout, exactly as today. The
> sandbox data root is **throwaway** — refresh it from the real repo whenever a
> verification run needs current data, and never do real job-search work in it.

Worth stating as a rule rather than a preference because two sqlite databases that
have both received real work cannot be merged in any sane way. There is no diff, no
three-way merge, no `loaddata` that reconciles them — it would be a hand
reconstruction. The cost of accidentally logging one application in the sandbox is out
of all proportion to the convenience of having done so.

The trade-off accepted in exchange: the split layout gets tested as *code* but not
quite as *ergonomics*. The §5.4 two-folder workspace question — whether working across
a code repo and a data root actually feels fine day to day — isn't really answered by
a sandbox nobody lives in. Worth knowing going in, rather than concluding the layout is
proven when the trial ends.

**Consequence: the branch will drift, and that's fine.** `main` keeps receiving daily
commits to `jobs/`, `exports/` and `db.sqlite3` — files `data-root-move` deleted. Any
later merge gives a delete/modify conflict per touched file, resolved as "delete" every
time, and the pile grows with the length of the trial.

> **So don't plan to merge the branch.** The endgame is a brand-new public repo with no
> history (§1, M1.6), so the branch's *history* has no destination. What has to survive
> is the **file state**, and the code half of step 2 is four files (`.gitignore`,
> `src/config.py`, `tools/db-dump`, `tools/db-load`). Redoing step 2 against the real
> repo from scratch is cheaper and safer than keeping a 707-file deletion mergeable for
> weeks. Treat the branch as a **worked reference**, not a merge candidate.

Corollary: anything built in the sandbox that *isn't* about the data move — `init`,
`config.yaml`, `tools/py`, `example-data/` — should be its own commit, separable from
the deletion commit, so it can be cherry-picked onto `main` without dragging the move
along. Docs and plan edits are better made on `main` directly and pulled into the
sandbox, so the copy Michele reads every day stays current.

**The symlinks are gone (2026-09-20), removed with M1.9.** The record of why they
existed and why they had to go, since neither was obvious at the time: `repo/jobs` and
`repo/exports` were symlinked into the data root at the end of step 2 with no note
saying why. Michele's guess — that they were keeping the *skill* working — was right,
and investigating it produced blocker 9. They were load bearing, not decoration:
without them the skill's relative paths broke or, worse, wrote into the code repo.

They could never have shipped. The toolkit ships the skill, so if its paths resolve only through
a symlink, `init` must create one for every user and the code/data boundary is
fictional everywhere — and the link itself is a personal absolute path.

**A third reason emerged only when they were removed, and it is the one to remember:
while they existed, the sandbox could not tell correct behaviour from incorrect.** A
wrong bare `jobs/...` path still landed in the right place, *through the link*. So
removing them was not cleanup after M1.9 — it was a precondition for M1.9's
verification meaning anything. They also defeated `looks_like_data_root()`, which
reported the repo as a valid data root because `repo/jobs` resolved to a directory.

The `.gitignore` trailing-slash fix (`jobs/` → `jobs`) is **kept permanently**: it
costs nothing with no symlink present and guards against committing one later. `site`
was never symlinked, a decent hint that the set was assembled reactively rather than
designed.

**Backup, set up 2026-09-20:** the sandbox gained a second remote, `github`, pointing
at the private GitHub repo, and `data-root-move` is pushed there; `origin` remains the
local real repo. The sandbox *data root* is backed up by none of this and needs no
backup — it's throwaway by the rule above.

---

## 6. Milestones

### M1 — public template repo

Milestone IDs are **permanent**, so M1.9–M1.11 were appended rather than
renumbered and the table is not in execution order. Execution order is: M1.1–M1.4,
then **M1.9**, then **M1.11** (the rename), then M1.5–M1.7. **M1.10** is independent of
all of them, and **M1.8 (verification) is last** despite its number.

**M1.11 sits after M1.4 and before M1.6**, and both halves of that are load-bearing:
after M1.4 because M1.4 already rewrites the 26 files carrying `jobssearch2026`, so
renaming first would touch them twice for nothing; before M1.6 because the fresh
public repo's **first commit must already say `jobstudio`** — that is the whole reason
the rename is free. It must also precede **M1.8**, or the clean-room pass verifies a
name that never ships.

| | |
|---|---|
| **M1.1** | Full inventory pass. §1 is two audit passes but still not exhaustive — explicitly unchecked: `jobs/notes/`, and whether any `docs/*.md` embeds personal specifics. (`extras/` needs no inventory — it's a personal archive nothing reads, so it just stays behind; confirm no code path references it and move on.) Produce a checklist. |
| **M1.2** ✅ | **Done 2026-09-20** (`ac65d99`, on `main`) — §5.3 step 1. `src/config.py` + data-root resolution, call sites migrated. The estimate of "8 files / ~20 call sites" was low: eight further sites used `settings.SITE_ROOT` and were invisible to the grep the estimate came from (§5.3 step 1). Repo-vs-data split in `src/web/settings.py` was indeed the risky bit. |
| **M1.3** | `config.yaml` identity; fix the 6 hardcoded-name sites (§3.4), preserving old-filename recognition. |
| **M1.4** | `tools/py` + strip the absolute venv path from the 13 files (§3.3). |
| **M1.5** ✅ | **Done 2026-09-21** (sandbox `3c90ee4`, `2863579`, `60c39fb`, `77d9d44`, `4fab6e3`, `7aaf679`). `example-data/` for a fictional Alex Rivera with real companies; the fixture regenerated through the real models by `tools/build-example-fixture`; the suite migrated onto it (78 green, nothing touching Michele's data); `src/jobsinit.py` + `subcommands/init.md`; `tools/smoke-test` passing from a clean clone. **Scope was badly underestimated and the number is worth keeping: swapping `FIXTURE_DIRS` alone left 42 of 78 tests failing, 13 once the data root moved too, 0 after nine coupled tests were migrated — the fixture swap was about a fifth of the job.** The reason is that many tests read files from the data root while asserting against fixture rows, so the two must move together; `settings.py` now points `$JOBSEARCH_DATA` at `example-data/` during tests, before `local_settings` is imported. **It also found four bugs** (§4a). Original scope: `example-data/` (§4) — including replacing `backups/django/dump.json` — + `/jobs-search init` (§3.2) + an automated from-scratch smoke test that runs `init --from-example` into a temp dir, renders a CV to docx, and runs `status` — failing loudly on any leftover personal assumption. Cheap to re-run after every later change. Building the site is *not* part of it (opt-in feature, §1) — but a separate, occasional `site-build` check is worth having so the feature doesn't silently rot now that nothing exercises it routinely. |
| **M1.6** ✅ | **Done 2026-09-21.** `github.com/lambdamusic/jobstudio` (private for now), built with `tools/make-public-tree` and pushed: **138 files, 1 commit, 0 personal files in history**. A separate local checkout at `dev2/jobstudio` was required rather than reusing the sandbox — the sandbox carries 215 commits and 799 personal files ever tracked, and the password-hash `dump.json` is still retrievable from its history, so a clean working tree would have meant nothing. Verified as an install, not just as files: fresh clone → `init --from-example` → `status` → 78 tests green. **Still open:** the supported-platforms README line is in (from M1.10), but deciding where toolkit development lives from here — `jobstudio` as home versus the sandbox as source — is not, and it should be settled deliberately rather than drifting. Original scope: Fresh public repo, **no history** — §1 found ~690 of 810 tracked files personal, so there is nothing worth scrubbing: the first commit must already be clean. **Hard gate: `backups/django/dump.json` (see M1.5).** **MIT `LICENSE`**; public `README.md` leading with **"no API key needed"** (§1 blocker 8); confirm `extras/` is excluded outright, third-party PDFs included (§1 blocker 6). (Third-party-manual references were stripped from the skill and docs on 2026-09-20 — verify none crept back.) |
| **M1.7** ✅ | **Done 2026-09-21.** Michele's own migration (§5.3). The data root is `_Jobs/jobstudio-data` (15M `exports/`, 7.7M `extras/`, 4.9M `site/`, 4.7M `jobs/`, the 448K database), **copied and verified byte-identical — 688 files across four trees plus two sha256 checks — and nothing deleted**: the old repo is frozen in place as a read-only archive rather than stripped, which is the one deviation from §5.3 step 4 and Michele's call. `dev2/jobstudio` is now both the development checkout and the daily driver: its `.jobstudio-data` pointer was **deleted** so a bare command falls through to `~/.jobstudio.ini` and hits the real job search. `backlog/` and `log/` moved here too (§5.7). Verified: `--chain`, `status` (47 applications), 78 tests, `site-build` (182 pages, link check clean), `db-dump`, a real `.docx` render, `smoke-test`. |
| **M1.9** ✅ | **Done 2026-09-20** (`32e6772`, `070d823` — sandbox; not yet on `main`). Landed as described below, with three deviations worth carrying forward: the placeholder is spelled **`<DATA>`** not `$DATA` (two references sit inside bash command lines, where `$DATA` expands to the empty string — nothing exports it and shell state doesn't survive between commands — so a pasted command would write to `/jobs/scans/...` silently; `<DATA>` can't expand, fails loudly, and matches the `<slug>`/`<ref>` convention already in these docs); **74** references were rewritten rather than ~76, because keying on the seven known data subdirectories left `company.md`'s two "their jobs/careers page" prose mentions correctly untouched; and three further bare mentions were left deliberately, with the preamble saying why (the help table is printed verbatim to the user; `status.md`/`publish.md` describe what a *script* does). **Sequencing constraint: `070d823` and `32e6772` must reach `main` together**, or the preamble's step 1 (`config.py --path`) returns the `describe()` line instead of a bare path. Original scope, for reference: |
| **M1.10** ✅ | **Decided 2026-09-20: macOS + Linux only; Windows out of scope, revisit only on real demand. Three fixes done 2026-09-21** — Chrome discovery searches Linux paths and falls back to `$PATH`, with `chrome_path` overriding; `_open_locally` picks `open`/`xdg-open` (and the raw `-R` became a platform-neutral `reveal=True`, since only macOS has that flag — elsewhere it opens the containing folder), with a 404 naming the fix instead of a 500 stack trace; the ten `vscode://file/` literals collapsed to one `EDITOR_URL_SCHEME` in the shared context processor plus one call in `admin.py`. All three are settings in `~/.jobsearch.ini` read through a new `config.setting()`, so a third platform is data rather than a code change — which is what "revisit only on real demand" needs to stay cheap. **Still open:** the supported-platforms line in the public README (pairs with M1.6). Original scope: `chrome_path` in `~/.jobsearch.ini` plus Linux paths in `_CHROME_PATHS`; `_open_locally` per-platform (`open`/`xdg-open`/`start`) so the reveal-folder button stops 500-ing off macOS; and the `vscode://file/` scheme collapsed from 10 literal sites into one setting consumed by a single template tag. M1.8's clean-room pass is where this would otherwise be discovered the hard way — on someone else's machine, which is the most expensive place to find it. |
| **M1.11** ✅ | **Done 2026-09-21** (sandbox `a357e12`), before M1.6 published — which was the point of the sequencing. Counts ran higher than surveyed because M1.3–M1.6 added files in between: **250** `jobs-search` across 64 files, not 208 across 61. All four parts landed; `config.py --chain` verified (d) before and after. **Three things found doing it:** the prose sweep could not see the unhyphenated identifiers, so `settings.py` still exported `JOBSEARCH_DATA` against a renamed `config.py` and **33 of 78 tests failed** — which is why (c) is listed separately here; `~/.jobsearch.ini` had been hand-edited to point at `<root>/jobs` with a trailing `# comment` that `configparser` keeps *inside the value*, latent because `main`'s `config.py` predates that layer, so `ConfigParser` now takes `inline_comment_prefixes`; and the Surge domain turned out to be **hardcoded in four shipping files** (see §2e). Original scope: **The rename to `jobstudio`** (§2e). Mechanical but wide, and it splits into four kinds of work that must not be confused. **(a) Docs and prose — the bulk:** `jobs-search` is 208 occurrences across 61 files (mostly `/jobs-search <sub>` cross-references inside `subcommands/`), `job-search` another 35 across 22, `2026-jobs-search` 4 across 3. **(b) The skill itself:** `.claude/skills/jobs-search/` → `.claude/skills/jobstudio/`, plus the `name:` field in its frontmatter and the stale "for the 2026 job search repo" wording in its `description:` — the directory and the frontmatter name must agree or the slash command breaks. Root `CLAUDE.md` references the skill too. **(c) Three live identifiers in `src/config.py` and one in `pyproject.toml`** — `ENV_VAR = "JOBSEARCH_DATA"` → `JOBSTUDIO_DATA`, `POINTER_FILENAME = ".jobsearch-data"` → `.jobstudio-data`, `~/.jobsearch.ini` → `~/.jobstudio.ini`, and `name = "job-search-pipeline"` → `jobstudio` (which binds to M2's PyPI publish). **No back-compat shim** — nobody outside this machine has the old names, so a fallback layer would be dead code at birth. **(d) The one genuinely risky step, because it is outside git:** Michele's own `~/.jobstudio.ini` and the repo-root `.jobstudio-data` pointer are gitignored local state that M1.9 made load-bearing for path resolution. Rename those two files **in the same sitting as (c)** or the next agent write resolves nothing and the resolution preamble fails at step 1. Verify with `config.py --chain` before and after. Out of scope by §2e: the Surge domain and the venv name. |

**M1.9's two options not taken**, recorded so the choice isn't relitigated: a single
convention line in `SKILL.md` leaving every reference bare (cheapest, but one forgotten
prefix writes personal data into the public repo — silent, and the blast radius is the
whole point of the project); and moving the writes into code so the agent never touches
a path (most robust, the right long-term shape, far beyond M1).

**M1.9's verification requirement, still outstanding:** no test and no grep can catch a
wrong path in Markdown, so M1.5's smoke test must drive at least one real agent write
against a temp data root and assert the file landed **in the data root and not in the
repo**. Michele confirmed this by hand on 2026-09-20; automating it is what stops it
rotting.


### M1.8 — verification

Three passes, in this order (the first draft had this right; keeping it):

- **Automated** ✅ — the M1.5 smoke test, headless, re-runnable. SMOKE PASS, 78 tests.
- **Manual clean-room** ✅ **done 2026-09-21** — fresh folder, fresh clone, fresh venv,
  follow the README from zero on a different machine or a different user account. Note
  every silent assumption.
- **A second real person** ⬜ — the actual bar implied by "share it with someone else".
  Most convincing, slowest, burns someone else's time — so do the other two first.

**Clean-room result (see `log/2026-09-21-m18-cleanroom-verification.md`).** A different
machine was not available; the substitute was a **fresh `$HOME`**, which is the part that
actually matters, since it removes `~/.jobstudio.ini` and with it the per-user state the
whole config chain hangs off. Every README step worked verbatim, first time — **no
findings against the install or the docs.**

Worth recording *why* this pass was not redundant with the smoke test, because the
temptation to treat it as a formality was real. `smoke-test` deliberately shortcuts three
things: `--skip-global` (never touches `~/.jobstudio.ini`), `--venv-python` pointing at
the existing interpreter (never builds a virtualenv), and it never opens the README. So
venv creation, the global config file and the written instructions had **no coverage from
anything** until this pass. Nor did the config layering with the `.jobstudio-data` pointer
absent, or with the working directory set to the data root — both now checked, both
correct.

The two findings were in `tools/make-public-tree` itself, which reported *"no personal
identity"* on a tree where `tests.py` contained `michele-pasin` five times — it was on
`ALLOW_NAME`. The exemption was hiding real job-search content: the names and dates of
companies Michele actually applied to, as fixture filenames, which is exactly the
"personal job-search CONTENT" the guard's comment says it exists to stop. A second
exemption, `src/appfolder.py`, was dead — zero hits, outliving the hardcoded-slug bug
M1.5 fixed. Auditing the rest the same way, **every `ALLOW_PATH` entry was dead** but
`make-public-tree` itself. Both lists trimmed to what is load-bearing, and each check
re-tested by planting a violation and watching the build refuse.

This is §5.7's lesson in a smaller key — there the denylist made the verifier skip files
and report clean on tree it had never read. Same shape: **an exemption no file needs is a
blind spot waiting for the next file whose path matches it.**

### M2 — pip package

Move `src/` under a package namespace; console-script entry points replacing the
`tools/py src/foo.py` calls (which retires `tools/py` and most of M1.4); `jobsearch
init` as a real CLI command; `MANIFEST`/package data for `example-data/` and the
skill; PyPI publish. Skill docs get rewritten from `tools/py src/jobsdb.py status` to
`jobsearch db status` — a mechanical pass over the ~104 path references in
`subcommands/`.

### M3 — drive Claude Code from the Django app *(recommended stretch goal)*

See §8. Give the existing web app buttons that run `/jobs-search` subcommands, with
Claude Code as the engine behind them. Reuses the skill unchanged, needs no
architectural change, and inverts the limitation the Cowork route ran into: instead of
losing the web app, the web app becomes the driver.

### M4 — Claude Desktop / Cowork *(parked)*

See §7. Researched 2026-09-20 and found easier than first thought, but parked on
Michele's call 2026-09-20 — the egress bugs, the Dropbox conflict and the
just-merged-into-Claude product churn make it a poor bet right now, and M3 delivers a
better version of the same goal. The research stands if it's ever revisited.

---

## 7. Stretch goal A — Claude Desktop / Cowork *(parked)*

> **Status: parked 2026-09-20.** Researched properly (below) and it's more viable than
> the first draft claimed — but three things argue against spending effort here now:
> the egress bugs that break `scan` (§7.1 #4), the direct conflict with the Dropbox
> data root (§7.3), and the fact that Cowork was folded into Claude four days before
> this was written, so the target is moving. **§8 is the better route to the same
> goal.** Keeping this section because the findings are solid and would be tedious to
> re-derive.

Michele's question: what would it take to run this from Claude Desktop or Cowork
instead of Claude Code?

**Researched against current documentation 2026-09-20** (the first draft of this
section was guesswork and got the hardest problem wrong — see 7.2). Sources at the end
of the section. Two things to know before anything else:

- **Cowork stopped being a separate product four days ago.** Anthropic folded it into
  the main Claude interface on 2026-09-16, alongside Claude Docs and Claude Slides;
  requests now route automatically rather than the user picking a tab. The
  *capability* is unchanged and the Cowork docs still stand — but "build for Cowork"
  is now "build for Claude", and the surface is moving. Don't design against details
  that might be a month old.
- **Cowork runs the same agentic architecture as Claude Code**, in Claude Desktop,
  without a terminal. So this is much less of a port than the first draft assumed.

### 7.1 The five requirements, re-checked

| # | Requirement | Verdict |
|---|---|---|
| 1 | **Durable filesystem** | ✅ **Solved — this is a product feature.** The user attaches **workspace folders**; the agent "can then read, create, and modify files anywhere inside those folders, **and run code against them inside the sandbox VM**". Files stay in place on disk — "no uploading or re-downloading, and edits land directly in the folder." So the data root can be an ordinary local folder and the Python scripts can work on it directly. |
| 2 | **Dependencies** | ✅ Workable. `pip` works and PyPI is reachable when egress is configured; network egress exists specifically so Claude "can access the internet to install packages and libraries". Cost is cold-start install time per session, since the sandbox is provisioned per session. Django is heavy but installable. |
| 3 | **The Django web app** | ⚠️ Still the real limitation. No `runserver` + `localhost:8000` browsing. Half-solved already, and this survives now that the site export is being **kept** (§1): `tools/site-build` renders every page to static HTML **in-process, no server, ~2s**, and that output can be handed back as files. So the *viewer* survives; the *Django admin* — editing rows by hand — does not. Worth noting the feature earns part of its keep here. |
| 4 | **Network egress** | ⚠️ Configurable but currently flaky. There's an account-level "Allow network egress → All domains" setting, enforced by a proxy. But there are multiple open bugs (Sept 2026) where cloud containers come up enforcing a **~5-host allowlist regardless of the setting**, and a macOS regression where the sandbox VM starts with no network route at all. `scan` hits 8 ATS platforms, so it's exactly the feature this breaks. Treat as "should work, verify empirically, don't build on it yet". |
| 5 | **Skill packaging & cwd** | ⚠️ Needs work, and M2 does most of it. Custom skills are uploaded as a **ZIP** via Settings → Features / **Customize**, need a paid plan with code execution, and — importantly — **Cowork does not read `~/.claude`**. So `.claude/skills/jobs-search/` can't just be pointed at; it has to become a self-contained, cwd-independent skill bundle. The ~104 repo-root-relative path references in `subcommands/` are the work. |

### 7.2 The fork in the road has moved

The first draft argued that requirements 1 and 3 together meant
sqlite-as-source-of-truth was the wrong shape, forcing a choice between a reduced
desktop mode and reversing the Phase 6 decision (`log/2026-09-07-django-frontend-plan.md`).

**That was wrong, and the reason is requirement 1.** The data root doesn't need to
live in an ephemeral sandbox — it lives on local disk as an attached workspace folder,
and sandboxed code runs against it. sqlite stays exactly where it is. **Option β
(files as truth, DB as index) is not required and should be dropped from
consideration** — it would reverse a decision that solved a real drift problem, to buy
something that's now free.

So this collapses into a much smaller thing:

**Option α, and only α.** Keep sqlite-as-truth. Package the skill as an uploadable
ZIP, make it cwd-independent, point it at the attached data root.
`stocktake`, `cv`, `cover-letter`, `interview`, `application`, `company` and `status`
all work — they're markdown-and-sqlite in, markdown out, and already agent-native
since `#1`. `scan` works if egress cooperates. The web app degrades to
`tools/site-build`'s static output; Django admin editing stays Claude Code–only.

That's a genuinely modest amount of work on top of M2, and most of it is M2's
packaging pass being reused.

### 7.3 Three caveats worth writing down now

1. **⚠️ Cowork and Dropbox conflict — this hits §5.2 directly.** Anthropic's own
   guidance: if your work folder is inside iCloud, Dropbox or Google Drive, Cowork
   "can sometimes get confused about file versions, pending syncs, or sync conflicts…
   a real source of weird bugs." Michele's data root is planned for Dropbox precisely
   because it's synced and shareable. For Claude Code that's fine. For the Cowork
   path it's the discouraged configuration. See the note added to §5.2 — this doesn't
   block M1, but it means M3 may want the data root on local disk with Dropbox used
   for backups/exports only.
2. **sqlite over a sandbox-mounted folder is untested here.** File locking across a VM
   mount is the classic place this goes wrong. Cheap to test early, ugly to discover
   late — make it the first thing M3 tries.
3. **Scheduled tasks can't see local files.** Cowork scheduled tasks run "even when
   your computer is off", and "if the desktop app is offline, the session can't reach
   your computer." So a nightly automated `scan` — the obvious thing to want — can't
   use a local data root. That's an argument for keeping the existing headless
   `scan-portals.py` → `score-candidates.py --api` path (the one remaining use for an
   Anthropic API key) rather than retiring it.

**Sources:**
[Cowork overview](https://claude.com/docs/cowork/overview) ·
[Desktop and filesystem access](https://claude.com/docs/third-party/claude-desktop/local-access) ·
[Get started with Cowork](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork) ·
[Use Cowork safely](https://support.claude.com/en/articles/13364135-use-claude-cowork-safely) ·
[Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude) ·
[Anthropic merges chat and Cowork (TechCrunch, 2026-09-16)](https://techcrunch.com/2026/09/16/anthropic-merges-claude-chat-and-cowork-in-one-interface/) ·
egress bugs: [#93525](https://github.com/anthropics/claude-code/issues/93525),
[#93512](https://github.com/anthropics/claude-code/issues/93512),
[#93507](https://github.com/anthropics/claude-code/issues/93507)

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

1. **The view pattern already exists.** `#24` added a local-only action view
   (`/actions/mark-reviewing/<num>/`) plus a button on the application detail page.
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

---

## 9. Status

**Updated 2026-09-21 — M1 is done except verification.**

**M1.7 landed (§5.7), and M1 is now complete bar M1.8.** The data root is
`_Jobs/jobstudio-data`; `dev2/jobstudio` is both the development checkout and the daily
driver, with its `.jobstudio-data` pointer deleted so a bare command resolves to the
real job search through `~/.jobstudio.ini`; the old repo is a frozen read-only archive
rather than a stripped one — nothing was deleted anywhere in this migration. Verified
end to end: `config.py --chain`, `status` (47 applications, the real ones), 78 tests
green against `example-data/`, `site-build` (182 pages, link check clean), `db-dump`
into the data root, a real `.docx` render carrying the right author metadata, and
`smoke-test`.

**`backlog/` and `log/` now live in `jobstudio` and will be public** — reversing M1.6's
position, on Michele's call. The interesting part is what that exposed in
`make-public-tree`: both were on its denylist, which after the move would have meant the
verifier skipping them and reporting a clean tree it had never read. See §5.7.

**M1.8 is now two-thirds done (2026-09-21).** The automated and clean-room passes are
both green — the clean room found nothing wrong with the install or the README, and two
stale exemptions in `make-public-tree` that were letting real company names ship in
`tests.py`. **Only the second real person remains**, and nothing in the toolkit blocks
it: it needs someone else's machine and someone else's time. TODO `#26` is closed — the
retired sandbox is deleted, its one unique file (`backlog/m1.1-inventory.md`) rescued
first.

---

**Updated 2026-09-20 (end of session).** §2's decisions are agreed; §3, §4, §6–§8 are
still design, not code. §5.3 has moved:

- **Step 1 done and on the real repo** (`ac65d99`, `4237dcc`). `src/config.py` plus
  every data path routed through it, still resolving to the in-repo locations. Two
  findings carried into §5.3: the call-site audit missed eight `settings.SITE_ROOT`
  sites that a grep could not see, and only a *deliberate split run* finds that class
  of bug — a regression run against the unsplit layout passes with all of them present.
- **Step 2 done in the sandbox only** (`8dbf513`, branch `data-root-move`), verified
  there and **not pulled back**. The real repo is still the undivided layout.
- **Step 3 (the §5.5 trial) is where things now sit** — building continues in the
  sandbox, the real repo is untouched. The symlink experiment left open at the end of
  step 2 was resolved by M1.9 (below): the links existed to keep the skill working,
  and they are gone.

**Decided later the same day (§5.5):** building continues **in the sandbox**, and the
real repo is not migrated until the layout has been lived with for a while. The real
repo stays the daily driver — the sandbox data root is throwaway and must never
receive real job-search work. `data-root-move` is pushed to the private GitHub repo as
a backup, but is a **worked reference, not a merge candidate**: the public repo will
have no history, so only the file state needs to survive.

Also decided: the public repo is **brand new with no history**, and
`backups/django/dump.json` is a **release blocker** — it holds 95 companies, 47
applications and a password hash (§4).

**Blocker 9 found and fixed, 2026-09-20.** Answering why the step-2 symlinks existed
uncovered that the skill had no notion of a data root and wrote 74 paths relative to
the working directory — a public-repo data leak no test could catch. **M1.9 is done**
(sandbox `32e6772` + `070d823`): `~/.jobsearch.ini` as the machine-level layer (§3.6),
`config.py --path`/`--chain`, 74 references rewritten to `<DATA>/...`, a resolution
preamble in `SKILL.md`, and the masking symlinks removed. Michele ran the skill
afterwards and confirmed every save lands in the data root.

Two things that came out of doing it, both now in the text: the preamble's resolution
order was wrong on first writing (`.ini` first would have had a sandbox session operate
on the real job search — caught only by running it split), and the symlinks had to go
*before* verification rather than after, because while they existed a wrong path still
landed in the right place.

**Also found 2026-09-20 (blocker 10):** the toolkit is macOS-only in three places —
`_CHROME_PATHS`, `subprocess.Popen(["open", …])` and ten `vscode://file/` literals —
and the README never says so. **Platform decided 2026-09-20: macOS + Linux only,
Windows out of scope for now.** Off macOS, PDF export raises, the reveal-folder button
returns a Django 500, and the editor links do nothing. Fix and the platform
declaration are **M1.10**; the three settings involved are the first non-`data_root`
keys `~/.jobsearch.ini` will hold.

**Carried: `070d823` and `32e6772` must reach `main` together**, or the preamble's
step 1 returns prose instead of a path. Neither is on `main` yet — deliberately, per
the §5.5 trial.

**M1.5 done 2026-09-21.** The example dataset, the synthetic fixture, the migrated
test suite, `init` and the smoke test all landed (sandbox). It found four bugs in code
that had been passing tests for months — §4a, and two of them are fixed on `main`.

✅ **Renamed 2026-09-21** (M1.11, sandbox `a357e12`). The text below stands as the
decision record.

**Name decided 2026-09-21: the project ships as `jobstudio`** (§2e) — unhyphenated,
one spelling across repo, skill, slash command, package, import and config prefix.
Nothing is renamed yet; the work is **M1.11**, sequenced after M1.4 and before M1.6 so
the public repo's first commit already carries the name. Michele's Surge domain and the
venv name are deliberately out of scope.

Next concrete steps, in order: **M1.3** (`config.yaml` identity) — `config.yaml` is
written by `init` and read by *nothing*, and `appfolder.app_filename()` still hardcodes
`michele-pasin`, so a new user's first `application` produces a file with the author's
name in it; ~49 hardcoded-identity references. Then **M1.4** (`tools/py`): 28 files
still carry the absolute venv path, two of them added by M1.5 itself and flagged
`# M1.4` in the source. Then **M1.1** (inventory) and **M1.10**'s three platform fixes.
Then **M1.11** (the rename), which wants M1.4 finished first.
**M1.7** stays gated on the §5.5 trial.

Full session narrative: `log/2026-09-20-toolkit-migration-steps-1-2.md`.

Both stretch goals were researched against live documentation on 2026-09-20. §7
(Cowork) had its conclusion reversed — materially easier than the first draft claimed
— but is **parked**: egress bugs, the Dropbox conflict, and product churn make it a
poor bet now. §8 (Django drives Claude Code) replaces it as the recommended stretch
goal and, unlike everything else here, could be prototyped without waiting for M1 or
M2. M1 and M2 stand as written; neither is affected by any of this research.

See `backlog/TODO.md` `#2` under Architecture.
