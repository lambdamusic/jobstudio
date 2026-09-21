# How publishing the site actually works

Part of the **[docs/](README.md)** guide collection. For *when* to publish, see
[workflow.md](workflow.md) §4 — this is a deep dive into what `/jobstudio publish`
does. The full Django app internals (models, layout, tests) live in
**`src/web/README.md`**; this file only covers the publish pipeline itself.

```bash
bash tools/publish-surge.sh
```

Two steps, always in this order:

```bash
tools/site-build --clean          # 1. rebuild site/ from the database + jobs/ tree
surge site/ <your-domain> # 2. push it live
```

## 1. `site-build` — two Django management commands

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
immediately without waiting for a publish.

**`manage.py build_static`** then renders every page **in-process**, via Django's test
client — no live server, no wget crawl, roughly 150 pages in about two seconds. This
replaced `src/make-docs.py` (2026-09-07).

Two hard rules the build enforces, both by design rather than by accident:

- **`site/` is fully regenerated.** `--clean` deletes everything in it except `CNAME`
  and `.nojekyll` — never hand-edit a file there, it will vanish on the next build.
- **Every internal link is verified before the build is accepted**, and it must be a
  real path, not a querystring — a static build can't publish `?status=applied`. A link
  that 404s or is a querystring fails the *build*, not the page load; the fix is adding
  the missing route to `site_urls()` in
  `src/web/apps/tracker/management/commands/build_static.py`, not patching the link.

## 2. Surge — the actual deploy

`surge site/ <your-domain>` pushes the freshly-built `site/` folder. Requires
`surge` installed and authenticated beforehand; `/jobstudio publish` reports success
(live at https://<your-domain>/) or surfaces whatever error Surge returned.

## What publish does *not* do

It never regenerates CV exports — if a base CV changed, re-run `render-html-pdf` for the
relevant application(s) first (see [cv-pipeline.md](cv-pipeline.md)); `publish` only
republishes whatever's already on disk and in the database.

## Privacy

The published site is **public but unlisted** — everything on it, including
gap-analysis notes and fit summaries, is reachable by anyone with the URL. Treat the
Surge URL as a secret rather than as something to share casually.

## Rebuilding without publishing

```bash
tools/site-build --clean      # rebuild site/ only
tools/site-preview            # browse it locally at http://127.0.0.1:9111/
```

Useful for checking a build (especially the link-verification failure above) before
pushing it live.
