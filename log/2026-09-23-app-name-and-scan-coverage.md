# "Job Studio", and a coverage column that can't disagree with the scanner

**Date:** 2026-09-23 (third entry of the day; continues `log/2026-09-23-status-menu.md`)
**Session focus:** Four TODOs captured (`#30`–`#33`), then `#32` and `#30` implemented.

**Headline:** Both were nominally small. Both turned out to be about *one definition
instead of several* — the app's name was written out 16 times, and the answer to "is this
company scanned?" was about to be written out twice.

---

## `#32` — the rename

Michele settled both open questions: **"Job Studio", two words, everywhere** — not just
the sidebar.

The display name is deliberately *not* the package name. `#2` fixed the project as
`jobstudio`, "unhyphenated, one spelling everywhere" (plan §2e), and that still holds for
the repo, the command and the package. What was decided here is that the thing a person
looks at may be spelled like English. The settings comment says so, so the next person to
notice the mismatch finds it recorded rather than assumed to be a slip.

"Job search" appeared 15 times across 13 templates plus `admin.site_header`. Rather than
find-and-replace it into 16 new literals, the name moved to `settings.APP_NAME` and is
exposed through the `site_context` processor — which already carries exactly this comment
about `EDITOR_URL_SCHEME`: *"One definition for the whole UI. Was ten literals across
eight templates."* The same mistake, caught twice; this time the fix was already
designed.

Each template's `{% block title %}` dropped its own ` · Job search` suffix and
`base.html` appends the name once. Side effect worth having: the application detail page
never had the suffix at all, so its tab title was inconsistent with every other page.
Now it isn't.

**Distinctiveness:** a two-tone wordmark — navy "Job", gold "Studio", both already in
the palette — beside an inline SVG mark of three bars of decreasing width, which reads as
a shortlist. Inline rather than a file: the published site is a plain file mirror, and a
mark that lives in the markup cannot go missing from it.

## `#30` — the coverage column

The predicate already existed: `resolve_source()`. It was unreachable, because it lived
in `scan-portals.py` and that hyphen makes the module unimportable.

The obvious fix is to make it importable. **The reason to do it is different from the
reason to reach for it**, and worth stating: not access, but agreement. Re-deriving "is
this company scanned?" in the web app would have meant two copies of the ATS patterns and
two copies of the not-scanned reasons, free to drift — and *a coverage column that
disagrees with the scan report is worse than no column at all*. So the move was paired
with rewriting `scan-portals.py`'s own loop to call the new `coverage()`. One function,
two callers, no second opinion.

New module `src/scan_sources.py` rather than `scan_config.py`: that module's docstring is
explicit that it holds settings belonging to *one person's job search*, and Greenhouse
URL shapes are toolkit knowledge, true for everyone. Following the suggestion in the TODO
would have quietly contradicted the file it was going into.

**The reasons stay graded.** "No URL on record" is a gap in the tracker anyone can close
in a minute; a `known_unsupported` entry is a platform confirmed by hand with no fetcher
written (`#10`); the bespoke fallback means nobody has found an API yet (`#22` — this
column is precisely that list). Collapsing all three into "not scanned" would have hidden
the only actionable one. They are rendered as text under the marker rather than a
tooltip, following the visible-over-hover preference recorded in `#25`.

## Checks

`manage.py test tracker cvs` — 99 green (5 new, covering override-wins, bare URL
detection, the hand-written reason, the no-URL case, and every row of the rendered page).
`tools/smoke-test` — SMOKE PASS. `scan-portals.py --dry-run` gives byte-identical output
before and after the refactor (verified by stashing the changes and re-running).
In-browser against `jobstudio-devdata`: wordmark, mark, titles on six pages, and the
column.

## Two things to know

- The **devdata scratch root has no `scan-config.yaml`**, so every company there reports
  "not scanned". That is correct — the overrides are what find these companies, and that
  root has none. `example-data/` does, which is why the tests exercise the override path
  and the browser check could not.
- **Browser CSS caching bit again**, same as yesterday's menu work: the first load showed
  the old sidebar. A hard reload is the first thing to try, not a debugging session.

## Still open from this batch

`#31` (sidebar icons) and `#33` (GitHub link in the footer) — captured, not built.
