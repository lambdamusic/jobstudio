# `/cvs/` lists every tailored CV, not just the two masters

**Date:** 2026-09-23
**Session focus:** Three TODOs captured (`#27`, `#28`, `#29`), then `#29` implemented.

**Headline:** A CV tailored for a role was only reachable if you already knew which
application folder it was in — the CVs page showed the two base CVs and nothing else.
It now lists all of them, newest first, each naming its application and linking to that
application's CV tab. No new view or route was needed; the deep link already worked.

---

## What was captured

- `#27` — re-order the application-folder naming convention to
  `{type}-{date}-{username}-{job-slug}`, and extend it to `notes.md` / `job.md`, which
  today carry neither date nor owner. Not implemented; the entry records the recognisers
  and parsers that must keep matching **both** namings, since folders on disk are not
  renamed.
- `#28` — turn the application page's single hardcoded "Mark reviewing" action into a
  control covering all seven statuses in `STATUS_SORT_ORDER`. Not implemented. Open
  question left in the entry: dropdown vs. button row, seven being a lot for a row.
- `#29` — this. Implemented below.

## `#29` — what it took

Three pieces, each in the layer that owns the knowledge:

- **`cv_variant()` in `src/appfolder.py`** — pulls the target-area slug out of a CV
  filename so a row can say "Developer advocacy" rather than
  `001-grafana-labs-alex-rivera-cv-developer-advocacy-2026-09-15.md`. It lives in
  `appfolder.py` beside `is_tailored_cv()` deliberately: that file owns the naming
  convention, and `#27` will move the date around inside these strings, so all the
  string knowledge should be in one place when it does.
- **`Application.tailored_cvs`** — `cv_snapshots` filtered through `is_tailored_cv()`.
  The filter matters: `ensure_folder()` scaffolds every folder with an *untailored*
  copy of the base CV, and listing that as a tailored CV would report work that was
  never done.
- **`cvs.views.tailored_cvs()`** — flattens the above across applications and sorts.

**One real trap, caught by an existing test.** The template comment I wrote used
`{# #}`, which in Django is *single-line only* — so a multi-line one is not a comment at
all and every line rendered into the visible page. `test_templates_have_no_leaked_comment_markup`
caught it immediately. This is the same failure `_app_table.html` already carries a note
about; the note is there because it happened before. Switched to `{% comment %}`.

## Two decisions worth recording

**"View the CV" links to `/applications/<num>/#cv`, not to a new CV detail page.**
Checked `tabs.js` before deciding: it already reads `window.location.hash` on load and
activates the matching panel, and the CV panel is `data-tab="cv"`. So the deep link cost
nothing — no view, no route, no template. Verified in-browser rather than assumed: the
link lands with the CV tab active and the CV rendered.

**The folder scan is accepted, with a marker left behind.** There is no database row for
a tailored CV — a CV is a file recognised by naming convention — so building this list
means one folder scan per application. At the scale of a real job search (tens of
applications) that is fine, and adding a table to track files that already exist on disk
would be a second source of truth to keep in sync. The cost is written into
`tailored_cvs()`'s docstring so that if `/cvs/` ever feels slow, the reason is the first
thing found rather than something to rediscover.

## Checks

`manage.py test tracker cvs` — 90 green (8 new in `src/web/apps/cvs/tests.py`, which had
been an empty stub). `tools/smoke-test` — SMOKE PASS. Page verified in the browser
against the `jobstudio-devdata` scratch root, not the real job search.
