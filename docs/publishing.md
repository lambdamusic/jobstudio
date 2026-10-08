# The static-site export (legacy)

Part of the **[docs/](README.md)** guide collection. **Legacy:** this is not a step in
the normal workflow, and nothing deploys the output any more. The web app
(`tools/run-dev-local-db`) is how the search is browsed; this file covers the one script
that renders the same pages to static HTML, which still works and is kept mainly
because it checks every internal link. The full Django app internals (models, layout,
tests) live in **`src/web/README.md`**.

```bash
tools/site-build --clean      # rebuild <DATA>/site/ from the database + jobs/ tree
tools/site-preview            # browse it locally at http://127.0.0.1:9111/
```

Until 2026-10-08 a `/jobstudio publish` subcommand pushed the build to Surge as a
private copy of the search. That went in `#69`; there is no deploy target now.

## `site-build` — two Django management commands

**`manage.py import_jobs`** refreshes only what's *derived from files on disk*:

| Derived from | Model |
|---|---|
| `jobs/targets/*.yaml` | `Area` |
| `jobs/cv/base/*.md` | `BaseCv` |
| `jobs/scans/*.md` | `Scan` |

It **never touches `Application` or `Company`** — those live only in the database, which
is the source of truth (see [applications-and-gap-analysis.md](applications-and-gap-analysis.md)
and [companies.md](companies.md)). Two things need no `import_jobs` step at all because
they're scanned from disk by filename convention at request time, not stored as rows:
cover letters and per-application CV snapshots (`is_cover_letter_filename()` /
`is_cv_filename()`). A portal scan also self-refreshes — `scan-portals.py` calls
`import_jobs --quiet` at the end of its own run, so a new report shows up at `/scans/`
immediately.

**`manage.py build_static`** then renders every page **in-process**, via Django's test
client — no live server, no wget crawl, roughly 150 pages in about two seconds. This
replaced `src/make-docs.py` (2026-09-07).

Two hard rules the build enforces, both by design rather than by accident:

- **`site/` is fully regenerated.** `--clean` deletes everything in it except `CNAME`
  and `.nojekyll` — never hand-edit a file there, it will vanish on the next build.
- **Every internal link is verified before the build is accepted**, and it must be a
  real path, not a querystring — a static build can't contain `?status=applied`. A link
  that 404s or is a querystring fails the *build*, not the page load; the fix is adding
  the missing route to `site_urls()` in
  `src/web/apps/tracker/management/commands/build_static.py`, not patching the link.

## What the build contains

A page for:

- every application, with its job description, gap-analysis notes, cover letters and the CV variant used
- every company, and every company category
- every target area — positioning, emphasis, key terms, its CV variants and applications
- every CV: both base CVs in `jobs/cv/base/`, and every per-application tailored copy
- every portal scan report and every file in `jobs/notes/`
- the career stocktake profile (`jobs/profile/`) at `/profile/`
- filtered application views as real paths (`/applications/status/applied/`, `/applications/area/data-platform/`, `/applications/active/`)

It does **not** regenerate CV exports — if a base CV changed, run `/jobstudio render`
for the relevant application(s) first (see [cv-pipeline.md](cv-pipeline.md)).

## Privacy

Everything above goes into `site/`, including gap-analysis notes and fit summaries. If
you host the output anywhere, treat its URL as a secret.
