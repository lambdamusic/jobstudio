# Changelog

Dated entries, newest first.

## 2026-09-24

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
