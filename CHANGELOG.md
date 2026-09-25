# Changelog

Dated entries, newest first.

## 2026-09-25

- **A scan can no longer score against nothing without saying so.** `scan-portals.py`
  resolves a company's target-area profile with `profiles.get(area, {})` — so an area
  naming no `jobs/targets/<slug>.yaml` yields an empty profile and the scan carries on:
  the keyword pre-filter falls back to the company's role target alone, the scorer judges
  against no `description`, `emphasis` or `key_terms`, and every row still gets an Area
  Score. Nothing in the report said otherwise. On a fresh data root, where
  `jobs/targets/` is empty and nothing ever wrote into it, that was *every* row — a scan
  that looked like it worked.

  **`tools/py src/scan_config.py --check`** reports the whole chain: no target areas at
  all, a `category_to_area` entry or `default_area` naming a file that doesn't exist, a
  tracked category resolving to no area, a target missing its scoring fields, and the
  unquoted-colon list entry that parses as a mapping instead of a string. Exits non-zero,
  so it can gate a first scan. `scan.md` runs it as step 0 on a data root that has not
  been scanned before.

- **`init.md` §"Define the target areas"** — propose two or three from the stocktake's §6
  and `criteria.yaml`, confirm, write one YAML each, `import_jobs`, check. Areas are
  positionings, not industries: several categories share one, and an area per industry
  produces files that score identically. Placed before "Seed the tracker", which needs
  them to map its categories onto.

- **The shipped example's `category_to_area` was keyed on two category names its own
  fixture never had.** Both entries were dead, every example company fell through to
  `default_area`, and `developer-advocacy` was unreachable in the dataset that exists to
  demonstrate it. Fixed, and the check now runs against the example in the test suite.

- **`init` no longer leaves you with a tracker nothing can scan.** A fresh data root
  finished setup with a CV, a profile and zero companies — and `scan` reads tracked
  companies, so the first run found nothing and the most visible feature in the toolkit
  looked broken on day one, for a reason nothing on screen explained.

  `subcommands/init.md` gains a **"Seed the tracker"** step, placed after `stocktake`
  because that is where the target areas and sectors get written and there is something
  to infer a starting list from. It asks for direction first — sectors, org size,
  geography, companies already in mind — then agrees two or three categories, researches
  10–20 candidates, presents them for a yes per row, and writes only what was approved.
  A tracker seeded with fifty unvetted names is worse than an empty one. `stocktake.md`
  offers the same step at close-out when the tracker is still empty, which is where
  anyone who skipped it at `init` will actually be.

- **`jobsdb.py add-category`** — categories are the user's own taxonomy and the toolkit
  ships none, but until now nothing outside the Django admin could create one. Idempotent,
  and an existing category keeps its hand-set `order`.

- **`add-company` refuses a category that doesn't exist** instead of silently writing the
  company without one. The old behaviour reported success and left an uncategorised row,
  which then scored against `scan-config.yaml`'s `default_area` rather than the area its
  category maps to — a mistake that surfaced far from where it was made. Auto-creating the
  category would have been no better: it turns a typo into a permanent second category
  with one company in it. The error names the tracked categories and the command to add
  the missing one.

- **`scan_sources.py` can be run directly** — `tools/py src/scan_sources.py "<name>"
  "<url>"` prints `scanned via <platform>` or `NOT scanned — <reason>`. The same answer
  the companies page already showed, asked one step earlier: a careers URL is chosen when
  a company is being *added*, and one that resolves to no board makes the company
  invisible to `scan`. Offline, no fetch, so checking twenty candidates costs nothing.

## 2026-09-24

- **A cover letter renders to `.docx` alone unless you ask for more.** HTML was written
  on every render because the PDF path needs something for Chrome to print. That was
  invisible while renders went to `exports/`; once they landed in the application folder
  (above), every cover letter left an `.html` beside its `.docx` that nothing downstream
  reads. The Chrome intermediate is a temp file now, and `--format html` is what puts one
  in the folder for real. `--format` lost its default so the cover-letter path can tell
  "I want HTML" from "I said nothing"; a CV with no `--format` still renders HTML as
  before.

- **A render is written once, where its source lives** — and the 16 MB backlog in
  `exports/` is gone. Every render used to go to `exports/<fmt>/<date>/`, with an
  application's `.docx` copied back afterwards: two copies of each file, under two
  different names, in a flat dated tree that named neither the source nor — for 22 of
  them — any application at all.

  `render._home()` picks the destination up front instead. A source in
  `jobs/applications/NNN-*/` renders into that folder's `export/`; a base CV from
  `jobs/cv/base/` renders into the new `jobs/cv/export/`, named `cv_functional-<date>.docx`
  to match the `base/archive/` convention; anything else still goes to `exports/`, which
  keeps its place as the home for documents belonging to no folder — a career stocktake,
  an ad-hoc `--file` from outside the data root.

  **`manage.py prune_exports`** clears what the old behaviour left behind. Like
  `migrate_exports` it prints its plan and writes nothing without `--apply`. It moves a
  render labelled with an application into that application's `export/`, keeping the date
  it was rendered on; keeps the newest `.docx` of each base CV; deletes the rest —
  superseded base renders, the retired variant library, and unlabelled renders that can't
  be attributed to any application. Anything *not* named the way a render is named was put
  there by a person: it is listed and left alone.

  In the real job search: 40 moved, 220 deleted, 16.0 MB → 48 KB. Eight applications got
  back the only rendered artifacts they had (their PDFs existed nowhere else).

- **Rendered exports move into an `export/` subfolder** — a `.docx` rendered from a
  tailored CV or a cover letter used to land flat in the application folder, beside the
  markdown it came from, so `applications/NNN-<company>/` mixed sources and output. The
  copy now goes to `applications/NNN-<company>/export/`, leaving only authored markdown
  (`job.md`, `notes.md`, the CV, the cover letter, the interview rounds) at the top level.

  Existing folders are **not** migrated, so every reader has to accept both shapes. That
  is now one function rather than a `md.with_suffix(".docx")` repeated at each call site:
  `appfolder.exported_file()` looks in `export/` first, then beside the markdown, and the
  CV tab, the Cover letters tab and `extra_files` all go through it.

  `extra_files` — the "nothing saved here goes invisible" tab — keys its exclusions on
  **paths** now, not bare filenames: with the export one directory down, "is this already
  shown on another tab?" became a question a name alone could not answer. Anything else
  left in `export/` still shows there, listed as `export/<name>`.

  `<DATA>/exports/<fmt>/<date>/` (plural, at the data root) is unchanged — it stays the
  global export area every render writes to first.

  **A render is linked even when its name doesn't match its source.** The copy is named
  with the date of the *render*, not of the markdown it renders, so re-rendering a letter
  written last week produces a stem its source doesn't share — nine of 34 exports in one
  real job search were orphaned this way, showing under *Other files* with no "Open .docx"
  on the tab that owns them. `exported_file()` now falls back to the newest export of the
  same kind (CV or cover letter) in `export/`, and holds off when the folder has more than
  one markdown of that kind, where pairing would be a guess. A superseded earlier render
  keeps its place under Other files rather than being linked.

  **`manage.py migrate_exports`** tidies folders written before today. It shows its plan
  and writes nothing until given `--apply`; it moves only top-level files carrying the
  folder's own name as a prefix, so a JD or a recruiter's PDF saved in by hand stays
  where it was put, and it never overwrites a name `export/` already holds. Readers
  accept both layouts either way, so running it is housekeeping, not a prerequisite.

- **Interview rounds are their own files, and their own tab** — an interview used to be
  written into `notes.md` under a single `## Interview prep` heading. That put one
  round's prep, its outcome and its timeline entry in three different places, and had
  pushed one real application's `notes.md` to 63% interview content across two rounds.

  Each round is now one file in the application folder,
  `<application-id>-<person-slug>-interview-<stage>-<YYYY-MM-DD>.md`, where the date is
  the date of the **interview** — not, as with CVs and cover letters, the day the file
  was written, which is what makes sorting on the name a real chronology of the process.
  Stages: `hr-screen`, `hiring-manager`, `technical`, `panel`, `final`, `informal`.

  Each file carries Details / Who I'm meeting / Prep / Questions to ask them / Study
  before / Private / **Outcome**. `## Outcome` is what makes a round self-closing, and
  `/jobstudio interview` now reads every prior round's before prepping the next one — a
  round's outcome outranks the job description wherever they disagree, being what the
  company said about itself out loud.

  The application page grows an **Interviews** tab, rounds stacked newest first, built
  the way Cover letters already was: discovery by naming convention, no database row.
  Prose lives on disk; the tracker keeps status. A round gets a model the day scheduling
  or reminders need one.

  The tab sits between **Job description** and **My notes** — once a process is live the
  rounds are what gets reread, and the JD is what they're read against. From two rounds
  up the panel opens with an index of them. `notes.md` keeps only what is true of the
  *role* rather than of a meeting, with `## Timeline` indexing the rounds.

  Migration covered every application folder: two of them split into two rounds each,
  three whose `## Interview prep` held written answers to application-form questions
  relabelled `## Application questions` (no interview had happened in any of the three),
  and the empty scaffolded heading removed from the remaining 31.

- **Deep links into a tab** — `tabs.js` reads the URL hash on load to choose a tab, and
  used to fall back to the first tab for any hash that wasn't a tab name. So a link to
  something *inside* a panel worked when clicked and broke on reload, landing on the
  wrong tab with its target hidden.

  It now resolves a hash naming an element inside a panel by opening the panel that
  holds it. Interview rounds (`#round-<stage>-<date>`) and the files under Other files
  (`#file-<slug>`) carry ids, so prose anywhere in a folder can link one directly and the
  link survives a reload or a share.

- **`make-public-tree` derives its company denylist from the tracker** — every other
  content check matches a list someone remembered to write. `.private-terms` held five
  terms, and a changelog entry describing this release named three companies from the
  author's own applications: the mechanism was sound, the list simply could not keep up.
  Nobody maintains a denylist of fifty employers that grows every week.

  The new check reads every company name out of the tracker database — read-only, via
  `sqlite3`, so it needs no Django — and refuses to ship a tree that names one. It cannot
  go stale, because the tracker is the list.

  A tracked company can also be a vendor, a standard, or the maker of a tool the project
  depends on, and the check can't tell "I'm interviewing there" from "we call their API".
  So names can be exempted in a gitignored `.tracked-company-exceptions`
  (`.example` shipped), for the same reason `.private-terms` is gitignored: a list of
  companies you track discloses your search whether it marks them allowed or denied. The
  mechanism ships; the names do not.

  It found real leaks on its first run, in files written the same day: an example
  filename in `appfolder.py`, the interview skill, `docs/interview-prep.md` and five
  assertions in `tests.py` all used a real tracked company as the worked example, and
  one doc named the company an answer-bank entry was validated at. Documentation
  examples now use the shipped `example-data` fixture instead, which is what a reader can
  actually run.

- **The publish check runs on every push** — `make-public-tree` was built to *cut* the
  public repo out of the old private one, a one-off. That job is long done: this repo
  now **is** the public repo, and it pushes `dev` as well as `main`, so every push is a
  publication. The valuable half was the checks, welded to a copier that demanded an
  empty destination — the wrong shape for a recurring gate.

  `tools/make-public-tree --check` now builds into a temp directory, runs every check
  against it, and deletes it. Same script, so the two paths cannot drift into different
  ideas of "clean". In check mode it also pulls in untracked-but-not-ignored files rather
  than refusing on a dirty tree: the point is to catch a leak *before* the commit that
  publishes it, not after.

  `tools/git-hooks/pre-push` runs it and blocks the push on a hit. The hook is versioned
  in the repo rather than left in `.git/hooks` — not backed up, not shared, empty on a
  fresh clone — and `git config core.hooksPath tools/git-hooks` turns it on, which `init`
  now does when the checkout has a remote. `git push --no-verify` bypasses it.

  It cannot run in CI, and that is not an oversight: the tracked-company check reads the
  tracker database in the data root, which is gitignored by design. A GitHub Action has
  no access to it and could not enforce this even in principle. The gate is local.

- **A guard against linking a bare markdown file** — files in an application folder are
  *rendered into* the application page, never published beside it, so a relative
  `[…](notes-something.md)` link resolves to nothing in the web view and fails
  `build_static`'s link checker. Easy to write by accident and invisible until a publish.
  `test_no_folder_markdown_links_a_bare_md_file` now scans every markdown file in every
  application folder and fails on one. Link the anchor instead.

  Note what it can and can't do: the suite runs against `example-data/`, so this guards
  the convention and the shipped example, not a user's own data root. `build_static`
  remains the check for that — worth running before a publish.

## 2026-09-23

- **BambooHR is scanned** — a fetcher for the public JSON behind every BambooHR careers
  page, plus tenant detection from the careers subdomain. Ten ATS integrations now.

- **A careers link on the companies a scan can't reach** — the rows that have to be
  checked by hand now link straight out to the company's careers page, instead of a trip
  through the company page to find the URL.

- **The sidebar has icons, and a link to the repo** — each top-level section carries a
  line glyph that picks up the active item's colour; sub-items stay text-only so the
  indent still reads as hierarchy. The footer links to the GitHub repo, on the published
  site as well as locally.

- **The app is called Job Studio** — the sidebar, the dashboard heading, every browser
  tab and the admin header said "Job search". The name now lives in one place
  (`settings.APP_NAME`), and the sidebar carries a logo of its own — a briefcase glyph
  and the two-tone wordmark as one lockup. The package, repo and command stay
  `jobstudio`.
- **Scan coverage on the companies list** — a new column says whether `scan` picks each
  company up automatically and on which ATS, or the specific reason it doesn't, with a
  count at the top of the page.

- **Any status can be set from the application page** — the page offered one hardcoded
  action, "Mark reviewing"; every other transition meant a trip to the Django admin. A
  "Set status" menu now lists all seven statuses (bar the current one), logging the
  change to the History tab the same way an admin edit does.

- **Every tailored CV is listed on `/cvs/`** — the page showed only the two master CVs,
  so a CV written for a role was invisible unless you knew which application folder it
  was in. It now also lists all tailored CVs, newest first, each naming the application
  it belongs to and linking through to that application's CV tab.

## 2026-09-21

Initial public release.

`jobstudio` is an agent-native job-search toolkit: track companies, log applications,
tailor a CV per role, draft cover letters, run gap analysis, and scan ATS job boards for
new postings — driven end to end from a Claude Code session, with a local Django app for
browsing.

It grew out of one person's job search over several months, then had that person's data
separated from it so anyone could run it. Code and data are two directories: this repo is
the toolkit, and your job search lives in a data root you choose, outside it.

- **Nine ATS integrations** — Greenhouse, Lever, Workable, Workday, Ashby,
  SmartRecruiters, Teamtailor, Rippling, plus a generic first-party-JSON fetcher —
  with two-dimension scoring and a location filter.
- **Two base CVs** (functional and chronological), tailored per application on demand
  rather than kept as a variant library.
- **A local Django app** for browsing applications, companies, CVs and scan reports,
  with an optional static-site export.
- **`/jobstudio init`** sets up a data root from scratch, from an existing CV, or from a
  complete fictional example job search so there is something to look at first.
- **No API key needed.** Every default workflow runs inside your Claude Code session;
  one opt-in path (`scan --api`) wants an Anthropic key for headless scoring.
