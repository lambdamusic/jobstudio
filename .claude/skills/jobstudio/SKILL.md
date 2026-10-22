---
name: jobstudio
description: >
  Job-search toolkit: track companies, log applications, tailor a CV per role, draft
  cover letters, run gap analysis, and scan ATS job boards for new postings. Use when
  the user says "jobstudio <subcommand>", "new company", "new application", "log this
  job", "write a cover letter", or references tracking or applying to a role.
argument-hint: "help | init | company | application | cv | cover-letter | stocktake | interview | status | scan | render"
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
| `application` | Log a job application: creates folder, gap analysis, a CV copy, and a thin cover-letter draft |
| `cv` | Tailor a CV to a specific application, on request (agent-native, no API call) |
| `cover-letter` | Write the full tailored cover letter for an application |
| `stocktake` | Guided "taking stock" interview — builds the career profile in `jobs/profile/` |
| `interview` | Prep for an actual interview with a company — likely questions, drafted answers (incl. emotional-intelligence questions), questions to ask them |
| `status` | Dashboard summary of companies and applications |
| `scan` | Rescan tracked companies for new open roles, score matches, report for review |
| `render` | Render an application's CV/cover letter to .docx (no API call) |

**Usage examples:**

```
/jobstudio company Grafana Labs
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
| `application [description, url, or #N]` | Log a new application or refresh an existing one — creates folder, saves job.md, gap analysis, a mechanical copy of the base CV, and a thin generic cover-letter draft. Tailoring neither (TODO `#55`): ask for `cv` / `cover-letter` on the roles worth it |
| `cv [company or #N] [--base functional/chronological]` | Tailor a CV to a specific application, on request (agent-native, no API call) — functional rewrites Summary + Core Competencies, chronological rewrites the whole document, replacing the copy in the application folder |
| `cv --rebuild` / `cv --import <path>` | Bootstrap the two base CVs from scratch via interview, or from an existing CV document — high blast radius, always confirms and backs up first (see `subcommands/cv.md` §A) |
| `cover-letter [company or #N] [--standard2] [--thin] [extra context]` | Draft a cover letter — standard structure, Standard 1 by default, Standard 2 (a shorter alternative) or `--thin` (the generic draft `application` leaves) on request — from the application entry, CV, company notes, and `jobs/profile/` |
| `stocktake` | Guided interview through Step 1 of a structured career-transition process ("taking stock") — writes `jobs/profile/stocktake.md` and `jobs/profile/criteria.yaml`. Section-by-section, pre-filled from existing notes, resumable |
| `interview [company or #N]` | Prep for an actual interview — reads the job description, fit check, CV gaps, and `jobs/profile/`, drafts likely questions (technical, behavioural, emotional-intelligence) with STAR-grounded answers and questions to ask them, writes into the application's `notes.md` "Interview prep" section, and offers to promote durable answers into the reusable `jobs/notes/interviewing/interview-technique.md` bank |
| `status` | Dashboard: application counts by status/area, active applications, companies by category and fit |
| `scan` | Run `python src/scan-portals.py` (mechanical fetch), then score live (agent-native, no API call); render with `python src/scan_report.py`; summarize the report: top matches, unscored roles, not-scanned companies |
| `render` | Render a specific application's CV and cover letter to .docx, no API call |

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
than information; and `status.md` mentions `jobs/` generically when
describing what a *script* does — that script resolves the data root itself. If
you are about to read or write a file, the path is written `<DATA>/...`; anything else
is prose.

Why this matters more than it looks: a bare `jobs/...` path resolves against the
working directory, so if the session started in the code repo, a write lands **in the
toolkit's own git repo** instead of in the user's data — silently, and in a repo that
may be public. That is the failure this convention exists to prevent.

## Lists of things to do are checklists

Whenever a subcommand writes a list of things for the user to *do* — prep steps, study
items, research to chase — write every item as a `- [ ]` task, never a numbered or plain
bullet. The web app renders `- [ ]` as a checkbox, and ticking it on the local app writes
`[x]` back into the file, so the user works through the list on the page and the file
remembers. Order still matters where the subcommand says so: a task list keeps its order,
it just isn't numbered. One task per item; detail can follow on indented lines.

Lists that are not to-dos — questions, pros and cons, gaps, drafted answers — stay plain
bullets.

**An application's to-dos all live in one place: the `## To do` section of its
`notes.md`**, first in the file (TODO `#84`), grouped by **theme**, with the interview
round as a **tag** on the task (TODO `#91`):

- The section opens with the short "How this list works" paragraph (`TODO_GUIDE` in
  `src/appfolder.py`, which `notes_stub()` writes) — the file explains itself to whoever
  edits it by hand. Keep it; add it if an older file lacks it.
- The `###` headings are four fixed themes, always in this order: **Domain**,
  **Stories & positions**, **Tech & Data**, **Questions & Practicalities**
  (`TODO_THEMES`). Put a new task under the closest one; do not invent others, and do not
  add `### <Round> — <date>` headings.
- Every task is `- [ ] **Short title.** Longer description.` — a bold title the eye can
  scan, then the detail, on indented lines if it runs on.
- A task meant for one interview round ends its description with that round's tag,
  `@<stage>`: `@hr-screen`, `@hiring-manager`, `@technical`, `@panel`, `@final`,
  `@informal` (the stage slug from the round file's name). An untagged task is general
  prep. Tasks that come *after* a call — a follow-up, a sample to send — carry that
  round's tag too.
- A note on how a task went is an indented sub-bullet under it, written by the user
  (`    - => answered in [interview prep](#round-…)`). Leave those alone.

The round's focus page gathers the tasks tagged for it, under their themes. They are not
copies: each checkbox is one line in `notes.md`, so a tick on either page is the same
tick. No other checklist of the application's tasks is written anywhere else: not
elsewhere in `notes.md`, not in a round file.

Older files may still use the earlier layout (`### Application` then one
`### <Round label> — <YYYY-MM-DD>` per round). The app reads both, so do not migrate one
unasked — but when adding to such a file, ask whether to convert it rather than mixing
the two layouts.

## Highlights are the user's — keep them

`==text==` in a notes, company or interview file is a highlight the user made on the page
(TODO `#77`). When editing a file that has them, keep every `==…==` exactly where it is,
including when rewriting the passage around it, and never add one yourself. If a
rewrite genuinely removes a highlighted passage, say so.

## Naming people

Whenever a subcommand writes about a person — a hiring manager, an interviewer, a
recruiter, a referee — **name them in full, first name and surname, every time**, in
every file: `notes.md`, interview rounds, Timeline lines, company research. Weeks later,
with several applications in flight, "Derin said…" no longer says who. If only a first
name is known, ask for the surname rather than writing the first name alone.

Link the first mention in each file to the person's LinkedIn page or other public
profile; later mentions in the same file keep the full name, unlinked. The link comes
from the application's `## Contacts` in `notes.md`, which holds one entry per person —
full name, linked, and their role in the process — so a profile is found once per
application. How a link is found when `## Contacts` lacks one, and the check it must
pass before it is used, is in `subcommands/interview.md` (TODO `#85`).

## Notes and their groups

`<DATA>/jobs/notes/` has three subfolders. `search/` is a tab on the Notes page;
`interviewing/` and `topics/` share the "Interviewing & topics" tab, one section per folder:

- `search/` — direction, reflection and leads, including `ideal-job-notes.md`
  (which `scan` scoring reads in full).
- `interviewing/` — **about me**, shown as **Me: answers and my work**:
  `interview-technique.md`, the answer bank `interview` reads and appends to, plus
  reference notes on what I built (how a product or pipeline worked, my role, the
  figures). Each story is told once, in the answer bank; the reference notes hold the
  detail behind it.
- `topics/` — **about the subject**: general, reusable prep, in one of four subfolders:
  - `topics/product/` — **Product**: product practice (discovery, strategy, delivery).
  - `topics/data-architecture/` — **Data architecture**: system design, APIs, platforms,
    security.
  - `topics/knowledge-graphs/` — **Knowledge graphs**: entity resolution, ontologies,
    graph data.
  - `topics/other/` — **Other**: sector landscapes and anything else.

  A topic note doesn't retell my stories; it says what a story shows and links to it in
  the answer bank (`/notes/interview-technique/#…`) or to the reference note.

**Study material that would serve another application goes to `topics/<subfolder>/`, not
into the application folder.** Name it for the topic (`topics/data-architecture/api-security.md`),
open it with one italic line saying which application it started for and when, and keep
only what is specific to that company or round in the application folder, linking the
note as `/notes/<slug>/`. That company-specific part goes **in `notes.md`**, as a section
under `## My notes` (or in the round file, if it is prep for one round), never in a
separate study or research file that only says "see the note" plus a few lines. Nor
does the note get a list of the applications it served: the Notes page works that out
from the links. When a note straddles two subfolders, file it by what it mostly
teaches; a note left straight in `topics/` still shows, under "Other notes", until it is
sorted. The Notes page lists every application whose folder links a note, so that link is
also how the note keeps its context. The URL is the filename alone, so a note's name must
be unique across all the folders, and moving a note never breaks a `/notes/<slug>/` link —
only a written path to it, which must then be updated.

## Referring to another file

Write the path, in backticks: `` `jobs/notes/interviewing/interview-technique.md` ``,
`` `jobs/companies/<slug>.md` ``, or a file in an application folder by its full name. The
web app turns any reference to a file that has a page into a link to that page (TODO
`#78`), so there is no need to write a markdown link or to work out a URL. Use the
`jobs/...` form, not `<DATA>/...`, and not a bare `notes.md` or `job.md` — every
application folder has one, so on its own it cannot be linked.

---

## Trigger patterns

Invoke `init` when the user says: "set this up", "first run", "I just cloned this", "where does my data go", or when a command fails because no data root is configured.

Invoke `company` when the user says: "new company", "add this company", "log this org", "I want to watch X", or pastes a careers URL.

Invoke `application` when the user says: "new application", "log this job", "add this role", "track this application", or pastes a job description.

Invoke `cv` when the user says: "tailor the CV for X", "regenerate the CV", "redo the CV in chronological", or references tailoring a CV for a specific application. Logging an application does **not** invoke it — the folder's CV is a mechanical copy until someone asks for more (TODO `#55`).

Invoke `cv --rebuild`/`--import` when the user says: "rebuild my CVs from scratch", "redo my base CVs", "import my CV from this file", or the base CVs don't exist yet and a CV-dependent workflow needs them.

Invoke `cover-letter` when the user says: "write a cover letter for X", "generate a cover letter", "redo the cover letter", or references an application by company name or row number.

Invoke `application` (refresh mode) when the user says: "refresh this application", "set up folder for X", "create missing files for #N", or "promote this application".

Invoke `scan` when the user says: "scan portals", "check for new postings", "run a portal scan", "any new roles at my tracked companies?", or similar.

Invoke `stocktake` when the user says: "taking stock", "work out what's next", "run the stocktake", "build my career profile", "career anchors", "what am I looking for in my next role", or references Step 1 of the career-transition process.

Invoke `interview` when the user says: "prep me for the interview", "help me prepare for X interview", "what will they ask me", "practice interview questions", "emotional intelligence questions", "STAR answers", "I have an interview with X", or references preparing for an actual interview (as opposed to the stocktake).
