# Workflow

Part of the **[docs/](README.md)** guide collection — this file is the typical
daily/weekly cadence: what to run, in what order.

**Everything here is a Claude command.** You drive this toolkit by talking to a Claude
Code session opened in it; the Python underneath is an implementation detail you never
have to touch. Where a step is backed by a script worth knowing about, this file says
so and links to **[under-the-hood.md](under-the-hood.md)**, which is the whole scripts
layer in one place. For how a specific piece works internally, see the dedicated guides
linked from `docs/README.md` (e.g.
[portal-scan-and-scoring.md](portal-scan-and-scoring.md)).

Four stages, roughly in order: prepare a CV → scan for postings → log and work applications → publish for easy review.

**Before all of it (once, revisit as needed):** `/jobstudio stocktake` builds the
career "taking stock" profile in `jobs/profile/` — `stocktake.md` (what I've done,
what I'm good at, career anchors, career stage, positioning by audience, narratives
to have ready) and `criteria.yaml` (hard filters, preferences, bonus signals,
weighted motivators). A guided, resumable interview based on Step 1 of a structured
career-transition process. Feeds the portal scan's Ideal-Job score, the application
gap-analysis "Fit check", and cover-letter framing. Browsable at `/profile/`. **How each section works, and where the profile gets used
elsewhere:** see **[career-stocktake-profile.md](career-stocktake-profile.md)**.

**Once an actual interview is scheduled:** `/jobstudio interview [company or #N]`
preps for it — likely questions (technical, behavioural, emotional-intelligence)
with STAR-grounded draft answers, and questions to ask them — written into that
application's `notes.md`. Not to be confused with `stocktake` above: this is
per-company interview prep, not the career-profile-building exercise.

---

## Summary — commands per phase

| Phase | What you're doing | Main commands |
|-------|-------------------|---------------|
| **1. Prepare a CV** | Edit base files; logging an application (Phase 3) copies one in mechanically, so tailor per application only when a role earns it; export to .docx | `/jobstudio cv [company or #N]` (agent-native, no API call — tailors the functional CV by default, `--base chronological` for the other base)<br>`/jobstudio render [company or #N]` |
| **2. Scan for postings** | Rescan tracked companies for new open roles, scored for review | `/jobstudio scan` (fetches, then scores live — agent-native, no API call) |
| **3. Log & work applications** | Log a role, set up its folder, refine notes + cover letter, finalise to .docx | `/jobstudio application [url or paste]` (or `#N` / company name to refresh)<br>`/jobstudio cover-letter [company or #N] [extra context]`<br>`/jobstudio render #N`<br>`/jobstudio company [name or url]` (track a new company) |
| **3c. Interview prep** | Once an interview is scheduled — likely questions, STAR-grounded draft answers, questions to ask them | `/jobstudio interview [company or #N]` |
| **3b. Review / edit** | Browse and change statuses | `tools/run-dev-local-db` → http://127.0.0.1:8010/ |
| **4. Publish for review** | Rebuild the `site/` folder and sync to Surge | `/jobstudio publish` |
| **Any time** | Dashboard summary of companies + applications | `/jobstudio status` |

---

## Any time — checking status

`/jobstudio status` prints a terminal mirror of the web dashboard (`/`) — status
counts, recent activity, recently logged/applied applications, recently added
companies, and the latest portal scans — sourced from the same database queries the
dashboard itself uses, so the two can't drift apart. **How each section is computed:**
see **[dashboard-status.md](dashboard-status.md)**.

---

## 1. Preparing a CV

### Edit the base

Two base files exist — edit these directly, never a tailored copy:

- `jobs/cv/base/cv_functional.md` — **functional** format: transferable-skill competency
  clusters first, condensed career history second. **The default** since 2026-09-08.
- `jobs/cv/base/cv_chronological.md` — full chronological CV, dates/roles in order. An
  opt-in alternative — pick it per application via that application's `cv_base` field.

Both are tailored the same way, fresh, straight into that application's folder — there
is no pre-generated library any more (retired 2026-09-16; the old
`jobs/cv/variants/<area>/` library had no consumer once the functional CV became the
default base).

### Tailor for an application

Tailoring is agent-native (no API call) and happens **on request** — logging an
application leaves a mechanical copy of the base in the folder (§3), and this is the
upgrade from it, for the roles worth the effort:

```
/jobstudio cv 30                        # default base (functional)
/jobstudio cv 30 --base chronological   # override for one-off
```

- **Functional** rewrites only its **Core Competencies** section — reordering and
  reframing the clusters for the role in question (bullets *within* a cluster stay
  newest-to-oldest), leaving summary, career history, education, skills and
  publications untouched.
- **Chronological** rewrites the whole document — bullets reordered per role, Summary
  tailored to the specific job.

`appfolder.pick_cv` follows the same rule either way: a CV already in the folder wins
(new or old naming — see "File naming inside an application folder" below), otherwise
the base matching the application's `cv_base` is what gets copied in. Since every
per-application CV carries the same kind of name, "has this one actually been worked
on?" is a content question — `appfolder.is_untouched_copy()`, which is what the
"unedited copy" marker on the CV tab and the tailored count on `/cvs/` both read.

**How tailoring and export actually work internally:** see
**[cv-pipeline.md](cv-pipeline.md)**.

### Export

```
/jobstudio render [company or #N]
```

Renders that application's tailored CV and cover letter to **`.docx`** — the format
employers ask for and the one that gets sent. Files land in the application's
`export/` subfolder.

`.docx` is the only thing produced — it is the format applicant tracking systems read
most reliably. Need a PDF? Open the `.docx` in Word or Pages and export one.

**Read the parse report.** Rendering prints a line like
`Parsed cv_functional.md (functional): … employers: 3, roles: 4 …`. The CV parsers
discard whatever they cannot match, so a CV in the wrong shape renders a clean,
well-formed, *empty* document — a file existing is not evidence its content survived.
If that line carries a `WARNING`, fix the markdown before sending anything. To ask the
question without producing a file at all, see `--check` in
**[under-the-hood.md](under-the-hood.md#cvs-and-cover-letters)**.

**Where a render lands** is decided by where its source lives (`render._home()`,
2026-09-24) — one copy, written straight to its home:

| Source | Render goes to |
|---|---|
| `jobs/applications/NNN-*/…` | `jobs/applications/NNN-*/export/`, named by the application-folder convention |
| `jobs/cv/base/*.md` | `jobs/cv/export/`, as `cv_functional-<YYYY-MM-DD>.docx` — the naming `base/archive/` already uses |
| anything else | `exports/<format>/<YYYY-MM-DD>/`, the generic area for documents belonging to no folder |

Until 2026-09-24 every render went to `exports/` and an application's `.docx` was *then*
copied back, which left two copies of each file and a flat dated tree naming neither the
source nor, for 22 of them, any application at all. `exports/` is still there and still
useful — a career stocktake, an ad-hoc file from outside the data root — it is just
no longer where work with a home of its own goes.

---

## 2. Scanning for job postings

`/jobstudio scan` rescans every tracked company for new open roles, without writing to the tracker — it only surfaces candidates for you to review and decide on manually.

Two steps behind one command: a mechanical fetch and pre-filter, then scoring. Scoring
is done live by the agent reading the fetched candidates, against the rubric in
`src/prompts/scan_score_rubric.md`. Running either step on its own:
**[under-the-hood.md](under-the-hood.md#scanning-job-boards)**.

**How the fetching, scoring and report work:** see
**[portal-scan-and-scoring.md](portal-scan-and-scoring.md)** — this file just covers
when to run it and what to do with the result.

**Where it saves:** a report at `jobs/scans/YYYY-MM-DD-portal-scan.md`, browsable at
`/scans/` (defaults to the latest one; `/scans/all/` lists every report).

**Nothing is auto-written** into the tracker. After reviewing the report, promote anything worth pursuing with `/jobstudio company` (new company) or `/jobstudio application` (log a role).

---

## 3. Logging jobs and working on applications

### Application statuses

| Status | Meaning |
|---|---|
| `saved` | Bookmarked — not yet applied |
| `reviewing` | Actively working on the application materials — not yet submitted |
| `applied` | Application submitted |
| `interviewing` | In the interview process |
| `rejected` | Applied, then turned down by the employer |
| `closed` | The deadline passed before I could apply |
| `discarded` | I decided I'm no longer interested in the role |

A company's derived status on the companies page is `applied` if it has any application in `{applied, interviewing, rejected}` — i.e. one that was actually submitted, whatever happened next — `reviewing` if nothing was submitted but something is still live (`saved`/`reviewing`), and `watching` otherwise. `closed` and `discarded` leave a company `watching`: neither implies an application was ever sent, and neither is still live.

### Add a new application or job post

`/jobstudio application [url or paste]` handles logging and workspace setup in one step. Claude:

1. Fetches/parses the posting and extracts company, role, area, status, next action
2. Confirms the extracted fields with you, then creates the application in the tracker database
3. Creates `jobs/applications/NNN-company/`, copies the functional CV in — named for the application, with the bracketed roles stripped from the competencies and nothing else changed — and creates an **empty** cover-letter file as a placeholder
4. Saves `job.md` with the full job description
5. Generates a gap analysis (CV gaps, improvements, prep steps) appended to `notes.md`

**How each step actually works, and how the gap analysis is structured:** see
**[applications-and-gap-analysis.md](applications-and-gap-analysis.md)**. For how a new
company gets tracked along the way, see **[companies.md](companies.md)**.

**Logging does not tailor anything** (revised 2026-10-01, TODO `#55`, superseding the
2026-09-17 decision to do both automatically). The CV is a mechanical copy and the
cover letter is a thin generic draft — three short paragraphs opening with the job-ID
line — because both get refined by hand before they are sent, so a polished draft was
producing work to undo rather than saving it. Ask for the full versions on the roles
that earn them: `/jobstudio cv [company or #N]` for a tailored CV,
`/jobstudio cover-letter [company or #N]` for a full letter. Both are agent-native, no
API call.

Calling the same command again on an existing entry (`/jobstudio application #11` or `... Grafana Labs`) is **refresh mode** — it fills in only whatever's missing, without re-logging or re-asking for confirmation.

If an application was logged without a folder (e.g. it predates this workflow, or was
dropped before reaching this step), the application page's **"Create folder"** button —
next to "Job posting" — creates it on demand with the same defaults, no need to run the
skill again.

### File naming inside an application folder

Decided 2026-09-08 — applies only to files generated inside `jobs/applications/NNN-*/`
(not the `exports/` tree, which keeps its own convention):

```
<application-folder-name>-<person-slug>-<filetype>-<YYYY-MM-DD>.<md|docx>
```

`<filetype>` is `cv-functional` or `cv-chronological`, or `cover-letter`.
`appfolder.app_filename()` is the single source of truth for building these names;
`appfolder.is_cv_filename()` / `is_app_cv()` / `is_cover_letter_filename()`
recognise them (old-style names from before this date are still recognised, just not
regenerated).

The application folder structure:

```
jobs/applications/001-grafana-labs/
  job.md                                                            ← full job description
  notes.md                                                          ← JD detail + gap analysis + personal notes
  001-grafana-labs-<person-slug>-cv-functional-2026-09-08.md        ← this application's CV
  001-grafana-labs-<person-slug>-cover-letter-2026-09-08.md         ← this application's cover letter
  export/
    001-grafana-labs-<person-slug>-cv-functional-2026-09-08.docx    ← ATS-friendly export
    001-grafana-labs-<person-slug>-cover-letter-2026-09-08.docx     ← ATS-friendly export
```

**Rendered output goes in `export/`** (2026-09-24) — the top level holds only what was
authored, so a folder listing reads as a set of sources rather than a pile of files.
`appfolder.export_dir()` names it and `appfolder.exported_file()` finds a copy again.
Folders written before that date keep the `.docx` beside its markdown and both shapes
stay readable, so nothing has to be migrated; `manage.py migrate_exports` tidies them
anyway (it prints its plan and needs `--apply` to move anything). Not to be confused with
`exports/` (plural, at the data root), which since 2026-09-24 holds only documents that
belong to no folder — `manage.py prune_exports` moved the rest to where it belonged.

All application folders live directly under `jobs/applications/`, regardless of status
— the archive/ split by status was retired 2026-09-08. The database is the source of
truth for status; browse by status in the web app rather than by folder location.

### Refine the notes and cover letter with Claude

- **Gap analysis** lives under `## My notes` in `notes.md` (`### CV gaps`, `### CV improvements`, `### Preparation steps`) — ask Claude to revisit or expand it, or edit it directly.
- **Cover letter** — use `/jobstudio cover-letter [company or #N] [extra context]` to (re)draft it: 3 paragraphs (~300 words), hook → concrete achievements → close, in the user's casual-but-precise voice. Claude shows the draft for review before saving; pass free-text context (e.g. `--emphasise knowledge graphs`) to steer tone. **How structure selection and drafting actually work:** see **[cover-letters.md](cover-letters.md)**.
- Both files are just markdown — hand-editing them directly is always fine; Claude only fills gaps, it never overwrites what's already there.

### Finalise by rendering the documents

Once the CV variant and cover letter for an application are settled, render them:

```
/jobstudio render #21
/jobstudio render grafana-labs
```

This finds the latest CV and cover letter in the application's folder and renders both to `.docx`, straight into that application's `export/` subfolder, named by the application-folder convention. No API call — run `/jobstudio cv [company or #N]` first if the CV is still the mechanical copy and this role deserves a tailored one.

### Using the local web app

The Textual TUI (`src/dashboard.py`) was retired on 2026-09-08. Its replacement is the
Django app:

```bash
tools/run-dev-local-db          # http://127.0.0.1:8010/
```

One of the few shell commands in this file rather than in
[under-the-hood.md](under-the-hood.md): the server is long-running, so you want it in
its own terminal rather than holding a Claude session open, and there is no `/jobstudio`
equivalent for that reason.

Browse applications, companies, target areas, CVs, notes and scans. `/help/` in the app
itself summarises the workflow below and the command for each step. **To change an
application's status**, click its status badge — that links straight to the Django admin,
where `status` and `next action` are editable inline from the changelist. Edits are saved
to the database, which is the source of truth; nothing overwrites them.

Every application page has a **History** tab, tracking status changes only (added
2026-09-08) — one entry per transition, written automatically whenever `status` changes,
so there's nothing to maintain by hand.

Application and company pages both have local-only quick-edit links — **Open folder** /
**Open in VS Code** next to the page title (added 2026-09-09) — for jumping straight to
the underlying files. A company page shows them once `jobs/companies/<slug>.md` exists; an
application without a folder yet shows **Create folder** instead, which scaffolds one on
demand with the same defaults as logging a new application.

Back up after a working session:

```bash
tools/db-dump                   # -> backups/django/dump.json (commit this)
```

See `src/web/README.md` for the full picture.

## 4. Publishing HTML pages for easier exploration

`/jobstudio publish` refreshes the `site/` folder and syncs it to the private Surge site in one step:

```
/jobstudio publish
```

It rebuilds the site and pushes it, and needs `surge` installed and authenticated. It does **not** regenerate CV exports — if a base CV changed, run `/jobstudio render` for the relevant application(s) first. Rebuilding or previewing without publishing: **[under-the-hood.md](under-the-hood.md#the-web-app)**.

**How the rebuild-and-deploy pipeline actually works:** see
**[publishing.md](publishing.md)**. See **`src/web/README.md`** for how the front end
works, how to run it locally, and where each page's content comes from.

The build re-imports the markdown into sqlite and renders the whole site from the Django app in `src/web/`, with no server running — a couple of seconds for a search of any realistic size.

The published site has a page for:

- every application, with its job description, gap-analysis notes, cover letters and the CV variant used
- every company, and every company category
- every target area — positioning, emphasis, key terms, its CV variants and applications
- every CV: both base CVs in `jobs/cv/base/`, and every per-application tailored copy
- every portal scan report and every file in `jobs/notes/`
- the career stocktake profile (`jobs/profile/`) at `/profile/`
- filtered application views as real paths (`/applications/status/applied/`, `/applications/area/data-platform/`, `/applications/active/`)

Every internal link in the output is verified before the build is accepted, so a missing
page fails the build rather than 404ing after publish.

To rebuild `site/` only, without syncing to Surge:

```bash
tools/site-build --clean      # rebuild
tools/site-preview            # browse it at http://127.0.0.1:9111/
```
