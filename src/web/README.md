# Web front end

Django app for browsing the job search — applications, companies, target areas, CVs,
notes and portal scans — and for publishing the same content as a static site.

Design decisions, data model and phase history: **`log/2026-09-07-django-frontend-plan.md`**.

## The one rule

**This database is the source of truth for applications and companies.** The admin is the
editing surface; edits stick. `jobs/applications.md` and `jobs/companies.md` no longer
exist — they were retired in Phase 6 (2026-09-08), along with the Textual TUI.

Still derived from files on disk, and refreshed by `manage.py import_jobs`:

| Derived from | Model |
|---|---|
| `jobs/targets/*.yaml` (config the CV generator reads) | `Area` |
| `jobs/cv/base/*.md` | `BaseCv` |
| `jobs/scans/*.md` | `Scan` |

`import_jobs` never touches applications or companies. There is no model for
per-application tailored CVs — those are scanned from the application folder by naming
convention at request time, same as cover letters (see below).

`Scan` is a special case: `src/scan-portals.py` calls `manage.py import_jobs --quiet`
itself at the end of every run (`refresh_web_db()`, 2026-09-13), so a new report shows
up at `/scans/` immediately — no manual `import_jobs` step needed after running
`/jobstudio scan`. `Area`/`BaseCv` still only refresh when `import_jobs` is run
explicitly (e.g. via `tools/site-build`, or by hand).

**Cover letters and per-application CV snapshots have no model.** Both are scanned from
each application folder by naming convention at request time — `*cover-letter*.md` via
`Application.cover_letter_files`, `is_cv_filename(...)` via `Application.cv_snapshots` —
so a new file shows on the application page immediately, with no `import_jobs` step. A
sibling `.docx` with the same stem is linked automatically; an empty cover-letter stub
(from `ensure_folder()`) is ignored until it has content.

`ApplicationStatusChange` (added 2026-09-08, powers the application page's History tab) is
pure database state, not file-derived — one row per status transition, appended
automatically by a `post_save` signal in `models.py` whenever `Application.status`
changes (including the very first save). It only tracks status; document adds/edits are
not logged. `manage.py backfill_status_history` seeded a starting entry for applications
that predate the model.

**`tools/db-dump` is the backup that
matters** — `<data-root>/backups/django/dump-<ts>.json` is the portable record, and `example-data/backups/django/dump.json` is the test fixture the tests load.
It includes the admin account and its edit history, so a restore gives you a working login;
`contenttypes`, `auth.permission` and `sessions` are excluded because including them makes
`loaddata` fail on a UNIQUE constraint.

## Running it

```bash
tools/run-dev-local-db          # http://127.0.0.1:8010/   (8000 is taken by another project)
tools/site-build --clean        # render every page to site/
tools/site-preview              # browse site/ at http://127.0.0.1:9111/
bash tools/publish-surge.sh     # site-build, then push to surge
tools/db-dump                   # <data-root>/backups/django/dump-<ts>.json — the portable backup, not the .sqlite3
tools/db-load <file.json>       # restore from a dump
```

Always call the venv python directly — never `source` or `workon`:

```bash
tools/py src/web/manage.py <command>
```

## Layout

```
src/web/
  settings.py  urls.py  wsgi.py  manage.py
  local_settings.py            # gitignored; copy from local_settings_example.py
  apps/tracker/                # applications, companies, areas, scans + the importer
  apps/cvs/                    # CV variants and master CVs
  templates-global/            # base.html + the admin banner override
  static/css/site.css
```

`src/` (the pipeline scripts) is on `sys.path`, so the app imports `appfolder` and `render`
rather than duplicating their parsers. Status ordering, the two-state company status, and
the application-folder file-naming convention all come from `appfolder.py` — one
definition, used by the skills and the web app alike.

## Where content lives

| On disk | Shown at |
|---|---|
| database (`Application`) | `/applications/` (active by default: applied + interviewing), `/applications/all/`, and `/applications/<n>/` |
| database (`Application.fit_level` / `fit_pros` / `fit_cons` / `fit_unknowns`) | pros/cons/unknowns boxes at the top of the Record tab |
| database (`ApplicationStatusChange`) | History tab on the application detail page; weekly Activity timeline on the dashboard |
| `jobs/applications/NNN-*/job.md`, `notes.md`, `*cover-letter*.md`, CV files, and any other file in the folder | application detail page (Job description, My notes, Cover letters, CV, and Other files tabs) |
| database (`Company`) | `/companies/` |
| `jobs/companies/<slug>.md` | Notes section on `/companies/<slug>/` — see that folder's README |
| `jobs/targets/*.yaml` + `jobs/areas.md` | `/areas/` |
| `jobs/cv/base/*.md` | `/cvs/` |
| `jobs/notes/*.md`, `jobs/scans/*.md` | `/notes/`, `/scans/` |

Long-form prose is never copied into the database — only its path is stored, and it is
rendered from disk at request time (plan §2.2).

## Local-only bits

Rendered only when `ENVIRONMENT=local`, and never present in the published mirror:

- the **Admin** link in the sidebar, and the status badges on every list, which link into
  the admin change form (new tab) where `status` and `next action` are editable inline
- **Open folder** → `/actions/reveal/<num>/`, which runs `open` on the server. Chrome
  blocks `file://` navigation from an `http://` page, so a plain link cannot work; the
  endpoint refuses any path outside the repo.
- **Open in VS Code** → a `vscode://file/...` link, which the browser hands to the app
- **Set status** → a `<details>` menu on the application detail page listing every status
  except the current one, each linking to `/actions/set-status/<num>/<status>/`. The
  status is validated against `STATUS_SORT_ORDER` rather than trusted, since it arrives
  from the URL. Saving goes through `Application.save()`, so `status_order` and the
  History tab's log are maintained exactly as they are for an admin edit.

The admin change forms carry Django's **View on site** button (from `get_absolute_url()`),
linking back to the public page.

## Two notes fields

`Application.summary` is the one-line scannable description shown in tables.
`Application.notes` is the full record shown on the detail page. They came from the two
different places the old markdown kept them and are genuinely different prose — don't
collapse them.

## Publishing

`manage.py build_static` renders every page in-process with Django's test client: no
server, no wget, ~2s for 150 pages. It replaced `src/make-docs.py`, now in
the owner's private archive.

Two things to know:

- **`site/` is generated.** `site-build --clean` deletes everything in it except `CNAME`
  and `.nojekill`. Never keep hand-written files there.
- **Filters must be real paths**, not querystrings — a static build cannot publish
  `?status=applied`. The build fails if any internal link is a querystring or does not
  resolve to a file, which is what replaces wget's crawl-based discovery.

The published site is public but unlisted (plan §2.3): everything goes on it, including
gap-analysis notes. Treat the surge URL as a secret.

## Tests

```bash
tools/py src/web/manage.py test tracker
```

They run against the **real** `jobs/` tree, not fixtures — the thing most likely to break
is the markdown format drifting. They cover the parsers, importer idempotency, every detail
page, the admin, and the invariants (no querystring links, company status two-state and in
sync, notes filenames matching company slugs).
