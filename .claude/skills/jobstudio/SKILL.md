---
name: jobstudio
description: >
  Job-search toolkit: track companies, log applications, tailor a CV per role, draft
  cover letters, run gap analysis, and scan ATS job boards for new postings. Use when
  the user says "jobstudio <subcommand>", "new company", "new application", "log this
  job", "write a cover letter", or references tracking or applying to a role.
argument-hint: "help | init | company | application | cv | cover-letter | stocktake | interview | status | scan | render-html-pdf | publish"
---

# Jobs Search

Toolkit for managing the 2026 job search: companies, applications, and cover letters.

## help Command

When the argument is `help` or no argument is given, output ONLY the following and nothing else:

---

**jobstudio** — Job search toolkit

**Subcommands:**

| Command | Description |
|---|---|
| `init` | First-run setup: create a data root, wire this checkout to it, and start from the example, an existing CV, public web research, or a blank interview |
| `company` | Add a company to the tracker for watching |
| `application` | Log a job application: creates folder, gap analysis, tailored CV, and cover letter |
| `cv` | Tailor a CV to a specific application (agent-native, no API call) |
| `cover-letter` | Generate a tailored cover letter for an application |
| `stocktake` | Guided "taking stock" interview — builds the career profile in `jobs/profile/` |
| `interview` | Prep for an actual interview with a company — likely questions, drafted answers (incl. emotional-intelligence questions), questions to ask them |
| `status` | Dashboard summary of companies and applications |
| `scan` | Rescan tracked companies for new open roles, score matches, report for review |
| `render-html-pdf` | Render a tailored application CV/cover letter to HTML + PDF (no API call) |
| `publish` | Refresh site/ and sync to Surge |

**Usage examples:**

```
/jobstudio company Crossref
/jobstudio application [paste job description or URL]
/jobstudio cv #18 --base chronological
/jobstudio cover-letter Grafana Labs
/jobstudio cover-letter #30 --standard2 --emphasise knowledge graphs
/jobstudio interview #41
/jobstudio scan
```

---

## Subcommands

Each subcommand has its own instruction file under `subcommands/`:

| Invocation | Description |
|---|---|
| `company [name or url]` | Track a new company — extracts details, picks category, inserts row |
| `application [description, url, or #N]` | Log a new application or refresh an existing one — creates folder, saves job.md, gap analysis, tailored CV, and cover letter |
| `cv [company or #N] [--base functional/chronological]` | Tailor a CV to a specific application (agent-native, no API call) — functional rewrites Summary + Core Competencies, chronological rewrites the whole document |
| `cv --rebuild` / `cv --import <path>` | Bootstrap the two base CVs from scratch via interview, or from an existing CV document — high blast radius, always confirms and backs up first (see `subcommands/cv.md` §A) |
| `cover-letter [company or #N] [--standard2] [extra context]` | Draft a tailored cover letter — standard structure, Standard 1 by default or Standard 2 (a shorter alternative) on request — from the application entry, functional CV, company notes, and `jobs/profile/` |
| `stocktake` | Guided interview through Step 1 of a structured career-transition process ("taking stock") — writes `jobs/profile/stocktake.md` and `jobs/profile/criteria.yaml`. Section-by-section, pre-filled from existing notes, resumable |
| `interview [company or #N]` | Prep for an actual interview — reads the job description, fit check, CV gaps, and `jobs/profile/`, drafts likely questions (technical, behavioural, emotional-intelligence) with STAR-grounded answers and questions to ask them, writes into the application's `notes.md` "Interview prep" section, and offers to promote durable answers into the reusable `jobs/notes/interview-technique.md` bank |
| `status` | Dashboard: application counts by status/area, active applications, companies by category and fit |
| `scan [--api]` | Run `python src/scan-portals.py` (mechanical fetch), then score live by default (agent-native, no API call) or via `python src/score-candidates.py` if `--api`; render with `python src/scan_report.py`; summarize the report: top matches, unscored roles, not-scanned companies |
| `render-html-pdf` | Render a specific application's tailored CV and cover letter to HTML + PDF, no API call |
| `publish` | Run `tools/publish-surge.sh` — refresh site/ and push to Surge |

**To execute a subcommand**: read the corresponding file in `subcommands/` and follow its instructions exactly.

---

## `<DATA>` — where this user's job search lives

Every data path in this skill is written **`<DATA>/...`**. `<DATA>` is the **data root**:
the directory holding `jobs/`, `exports/`, `db.sqlite3` and `backups/`. It is *not*
necessarily the repo — the toolkit's code and one person's job search are separate
directories, and the working directory may be either one (or neither).

**Resolve it once at the start of any subcommand that touches a file, then substitute
the real path everywhere.** In order:

1. **If the repo is reachable, run `python src/config.py --path`** — from the repo
   root, or with the full path to that file. It prints the resolved root and nothing
   else. Prefer this whenever it is available.
2. **Only if no repo is reachable**, read `~/.jobstudio.ini` and take `data_root` from
   the `[jobstudio]` section.
3. If neither works, stop and tell the user to run `/jobstudio init` — do **not**
   guess, and do **not** fall back to the current directory.

⚠️ **The order is this way round for a reason, and getting it backwards is dangerous.**
`config.py` applies the full layering — `$JOBSTUDIO_DATA`, then the checkout's
`.jobstudio-data`, then `~/.jobstudio.ini` — so it respects a checkout that points
somewhere specific. Reading the `.ini` directly skips the first two layers. On a
machine with more than one checkout (a real one and a sandbox, say) that means
operating on the **wrong person's data root** while sitting in the other one. The
`.ini` is the fallback for when there is no repo to ask, not the first thing to try.

⚠️ **`<DATA>` is a placeholder in this document, not a shell variable.** Nothing
exports it, and shell state doesn't survive between commands. Substitute the actual
path before running anything — never pass `<DATA>` through to a command, a file read,
or a file write.

**Two places deliberately keep bare `jobs/...`, and neither is a path to act on.** The
help table above is printed verbatim to the user, where `<DATA>` would be noise rather
than information; and `status.md` / `publish.md` mention `jobs/` generically when
describing what a *script* does — those scripts resolve the data root themselves. If
you are about to read or write a file, the path is written `<DATA>/...`; anything else
is prose.

Why this matters more than it looks: a bare `jobs/...` path resolves against the
working directory, so if the session started in the code repo, a write lands **in the
toolkit's own git repo** instead of in the user's data — silently, and in a repo that
may be public. That is the failure this convention exists to prevent.

---

## Trigger patterns

Invoke `init` when the user says: "set this up", "first run", "I just cloned this", "where does my data go", or when a command fails because no data root is configured.

Invoke `company` when the user says: "new company", "add this company", "log this org", "I want to watch X", or pastes a careers URL.

Invoke `application` when the user says: "new application", "log this job", "add this role", "track this application", or pastes a job description.

Invoke `cv` when the user says: "tailor the CV for X", "regenerate the CV", "redo the CV in chronological", or references tailoring a CV for a specific application.

Invoke `cv --rebuild`/`--import` when the user says: "rebuild my CVs from scratch", "redo my base CVs", "import my CV from this file", or the base CVs don't exist yet and a CV-dependent workflow needs them.

Invoke `cover-letter` when the user says: "write a cover letter for X", "generate a cover letter", "redo the cover letter", or references an application by company name or row number.

Invoke `application` (refresh mode) when the user says: "refresh this application", "set up folder for X", "create missing files for #N", or "promote this application".

Invoke `scan` when the user says: "scan portals", "check for new postings", "run a portal scan", "any new roles at my tracked companies?", or similar.

Invoke `stocktake` when the user says: "taking stock", "work out what's next", "run the stocktake", "build my career profile", "career anchors", "what am I looking for in my next role", or references Step 1 of the career-transition process.

Invoke `interview` when the user says: "prep me for the interview", "help me prepare for X interview", "what will they ask me", "practice interview questions", "emotional intelligence questions", "STAR answers", "I have an interview with X", or references preparing for an actual interview (as opposed to the stocktake).
