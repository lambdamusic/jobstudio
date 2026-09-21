# How logging an application actually works

Part of the **[docs/](README.md)** guide collection. For *when* to log a role, see
[workflow.md](workflow.md) §3 — this is a deep dive into what `/jobstudio application`
does step by step, and how the gap analysis it produces is structured.

Two modes, chosen automatically by whether the input already matches a tracker row:

```
tools/py src/jobsdb.py show "<company or #N>"
```

- **Prints a row → refresh mode.** The company/role/URL already exist — only whatever's
  missing in the folder gets created (no re-logging, no re-asking for confirmation).
- **Nothing → new application mode.** The full sequence below runs from the top.

---

## 1. Fetch, extract, confirm (new application only)

A URL gets fetched and parsed; pasted text is used directly. Company, role, area (one of
the 5 target slugs — see [cv-pipeline.md](cv-pipeline.md)), applied date, status
(defaults to `saved`), contact, next action, a one-line **summary** and the fuller
**notes** are all extracted or inferred, then shown back for a quick one-line-per-field
confirmation before anything is written. Fields that genuinely can't be inferred are
left blank rather than guessed.

`summary` and `notes` are deliberately two different fields, not one truncated into the
other: `summary` is the scannable line shown in list views, `notes` is the full write-up
shown on the application detail page.

## 2. The row lives in the database, not markdown

```bash
tools/py src/jobsdb.py add-application \
  --company "{Company}" --role "{Role}" --area {area-slug} --url "{Job URL}" \
  --date YYYY-MM-DD --status saved --next-action "{...}" \
  --summary "{one line}" --notes "{full record}" --contact "{...}"
```

`src/jobsdb.py` is a thin wrapper that bootstraps Django lazily and writes straight to
the same `Application` model the web app reads (`src/web/apps/tracker/models.py`) —
`jobs/applications.md` was retired along with the Textual TUI (2026-09-08); the sqlite
database is the only source of truth. The command prints the assigned row number, needed
for every step after this.

## 3. Every application needs a tracked company

This runs on *every* call, not just new ones — a refresh of an application whose company
was never tracked still fills the gap:

```bash
tools/py src/jobsdb.py show-company "{Company}"
```

- **Found** → `link-company <row-num>` makes sure the application's `company` foreign key
  is set (idempotent, harmless if already linked).
- **Not found** → the company gets added and researched the same way `/jobstudio
  company` does it, then linked. Full detail on that step —fields, categories, the
  research file template — lives in **[companies.md](companies.md)**.

## 4. The application folder

```bash
tools/py src/appfolder.py ensure <row-num>
```

Idempotent — creates whatever's missing:

- `jobs/applications/NNN-company-slug/` (the folder name comes from `appfolder.slug()` —
  lowercase, non-word characters stripped, spaces/underscores collapsed to hyphens)
- `notes.md`, from a bare skeleton (`## My notes`, `## Interview prep`, `## Contacts`,
  `## Timeline`) — deliberately carries no metadata header, since company/role/area/status
  live in the database and used to drift out of sync across three copies
- an **untailored** copy of the functional CV (`appfolder.pick_cv()` — see
  [cv-pipeline.md](cv-pipeline.md) for the tailored-vs-untailored logic)
- an **empty** cover-letter stub (`<folder>-<person-slug>-cover-letter-<date>.md`) —
  content is written later, on request (decided 2026-09-09, see §6 below)

All application folders live directly under `jobs/applications/` regardless of status —
the old archive/-by-status split was retired 2026-09-08, since the database (not folder
location) is what answers "is this closed?".

If a row was ever logged without a folder (predates this workflow, or the flow was
dropped before reaching this step), the application page's **Create folder** button
scaffolds it on demand with the same defaults — no need to re-run the skill.

## 5. `job.md`

Written once, if it doesn't already exist: the full extracted job description, or the
structured fields if the full text wasn't available. Never overwritten after that.

## 6. Gap analysis — appended to `notes.md`

Skipped entirely if `notes.md` already has a `### CV gaps` section (idempotency guard —
re-running `application` on an existing row doesn't redo this). Otherwise, the CV variant
copied into the folder, `jobs/profile/stocktake.md`, and `jobs/profile/criteria.yaml` are
read together and the JD is analysed against both, appended under `## My notes`:

| Section | What it holds |
|---|---|
| **Fit check** | Hard filters (`geography`, `salary_floor_gbp`, `self_employment_ok`, `exclude` rules) scored pass/fail/unknown against JD evidence — any fail or a stack of unknowns is flagged plainly. Then the 3–4 highest-weight motivators, judged against the JD. Then any bonus signals hit. Closes with a one-line verdict: worth custom effort, or borderline/skip. |
| **CV gaps** | Bullet list — for each JD requirement or signal missing or underplayed in the CV, the JD phrase quoted next to what's missing. |
| **CV improvements** | For each fixable gap: the CV line/section to change, why the JD wants it, and suggested replacement text drawn from `stocktake.md` §2 (achievements/USPs) and §6 (positioning by audience). |
| **Preparation steps** | An ordered, role-specific list — company/team research, skills to brush up, talking points from `stocktake.md` §7, domain-gap mitigation if the area is a stretch. |

### Fit summary — the structured half

The Fit check above is prose for a human to read. A second, much shorter pass distils it
into the four fields the Record tab renders as a coloured banner
(`Application.fit_level` / `fit_pros` / `fit_cons` / `fit_unknowns`, added 2026-09-10):

```bash
tools/py src/jobsdb.py set-fit <row-num> \
  --level {strong|moderate|stretch|weak} --pros "..." --cons "..." --unknowns "..."
```

`strong` passes every hard filter and hits most top motivators; `moderate` passes hard
filters with mixed motivator fit; `stretch` has a real gap (domain leap, seniority
question, hard-filter unknown) but is still worth pursuing; `weak` fails a hard filter or
is mostly cons. This is admin-editable and hand-maintained going forward — it's a
five-second read, not a replacement for the Fit check prose.

## 7. CV tailoring and cover-letter drafting (revised 2026-09-17)

Both now run automatically as part of logging, right after the gap analysis —
superseding the earlier "on request only" decision of 2026-09-09. Both are
agent-native (no API call); the agent reads the job description and profile sources
directly instead of sending them to a separate model call. Re-run either standalone
later to redo a one-off:

```
/jobstudio cv [company or #N]             # tailor the CV
/jobstudio cover-letter [company or #N]   # draft the letter
```

See [cv-pipeline.md](cv-pipeline.md) and [cover-letters.md](cover-letters.md).

---

## File naming inside an application folder

Decided 2026-09-08, applies only inside `jobs/applications/NNN-*/` (the `exports/` tree
keeps its own convention — see [cv-pipeline.md](cv-pipeline.md)):

```
<application-folder-name>-<person-slug>-<filetype>-<YYYY-MM-DD>.<md|docx>
```

`appfolder.app_filename()` is the single source of truth for building these names;
`is_cv_filename()` / `is_tailored_cv()` / `is_cover_letter_filename()`
recognise them — old-style names from before this date are still recognised, just not
regenerated. This is also how the web app finds CV snapshots and cover letters with no
database model at all: they're scanned off disk by filename pattern at request time
(`src/web/README.md`), so a new file shows up on the application page immediately.

## Application statuses and how they drive company status

The status vocabulary (`saved` → `applied` → `interviewing` → …) and what each one means
are documented once, in [workflow.md](workflow.md) "Application statuses" — this is
where to look them up. Worth knowing at the model level: a company flips from `watching`
to `applied` automatically the moment one of its applications reaches `applied`,
`interviewing`, or `rejected` (`refresh_company_status()`,
`src/web/apps/tracker/models.py`) — a `saved`/`reviewing` placeholder doesn't count, and
neither does `closed` or `discarded`. Every status change is also logged to
`ApplicationStatusChange`, which powers the application page's History tab and the
dashboard's weekly activity timeline — nothing to maintain by hand.
