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

---

## Addendum — the mark, revised after review

The three-bars tile described above did not survive Michele looking at it. Rather than
iterate blind, six variants were mocked up in one throwaway page — rendered at real size
on the real sidebar background, which is the only way to judge a 24px mark — and reviewed
in the browser: the bars tile, a single lockup, a monogram tile, a wordmark with a gold
rule, an outline glyph, and the mark stacked above the words.

Michele picked **the outline glyph (E) in the lockup layout (B)**: a briefcase in navy
stroke with a gold lens, and the wordmark drawn beside it inside the same SVG.

Two things fell out of that choice worth recording:

- **A lockup keeps the parts fixed to each other.** Glyph and words in one SVG cannot
  drift apart at different zoom levels or font settings the way two flex children can.
  It is drawn at its exact pixel size and never scaled, so the type stays crisp.
- **It is a deliberate exception to the `APP_NAME` consolidation made hours earlier.**
  The words are drawn, not interpolated: a fixed-width viewBox would be overrun by a
  longer name. An exception nobody can see is a trap, so `BrandTests.
  test_the_wordmark_matches_the_app_name` reads the tspans out of the template and
  compares them to `settings.APP_NAME`. Verified it actually bites, by changing the
  setting and watching it fail.

The monogram variant is worth a warning if this is ever revisited: "JS" in a tile reads
as JavaScript.

## The lockup shipped broken, and the suite did not notice

The lockup commit also carried a stray `</div>`, which closed `<nav class="sidebar">`
early and threw every page's content out of the layout. Michele saw it immediately; 101
tests did not.

**Cause:** the edit was a string replacement whose end anchor was `"    </div>"` — four
spaces — which is a *substring* of the `"      </div>"` six spaces in. It cut at the
wrong closing tag and left the outer one behind. Anchoring an edit on indentation is a
bad idea for exactly this reason.

**Why nothing caught it:** every test in the suite asserts content — a status code, a
substring, a link being present. An unbalanced tag changes none of those. The HTML was
all there; only its nesting was wrong, and nothing was looking at nesting.

So `MarkupTests.test_every_page_nests_correctly` now runs twelve pages through
`html.parser` and fails on a tag that closes the wrong element or is never closed,
naming the line and what it actually closed. Verified by reintroducing the exact bug:

    line 31: </div> closes <nav> opened on line 14

This is the second time today a visual check found something green tests missed (the
first was a CSS cache, which was not a real defect). The pattern worth keeping: for
anything that renders, look at it.

## `#31` and `#33` — the rest of the sidebar

**Icons.** Nine glyphs, defined once as `<g id="i-…">` in an inline sprite and drawn with
`<use>`. Same-document symbols rather than an external sprite file, for the same reason
the lockup is inline: the published site is a plain file mirror, and anything the static
build has to copy is something that can go missing from it.

`stroke="currentColor"` does the real work — the glyphs inherit the active item's navy
and the local-only grey without a second set of rules.

Two things the change quietly broke and had to be put back:

- `.nav-group a` was `justify-content: space-between`, which with a glyph in front pushes
  the icon away from its own label to opposite ends of the row. Switched to `flex-start`,
  with the count and the local-only `::after` badge each pushed right by `margin-left:
  auto` instead.
- Sub-item indent was tuned to the label above it, not the glyph: 8px padding + 16px icon
  + 8px gap = 32px. They stay text-only on purpose — a second column of glyphs would
  flatten the hierarchy the indent exists to show.

**The repo link** is the one sidebar link that renders in *both* environments. Everything
else local-only is hidden from the mirror; this is the opposite case, since the published
site is exactly where someone might want to know what built it. `test_the_repo_link_
survives_publishing` asserts it under `ENVIRONMENT="publish"` too, so a future tidy-up
that sweeps the footer behind `{% if IS_LOCAL %}` fails instead of quietly deleting it.

**Both got a test for their silent failure mode**, which is the lesson from the stray
`</div>` earlier: a typo'd `<use href>` renders *nothing* — no error, no missing text,
just a gap — and no content assertion would ever notice. `test_every_nav_icon_points_at_a_
symbol_that_exists` compares referenced ids against defined ones; verified by breaking
one and watching it fail.

## `#34` — the careers link

Small follow-on to `#30`: the coverage column said *why* a company isn't scanned, but
acting on that still meant opening the company page to find its URL. The reason text on
those rows now carries a `careers ↗` link.

The condition is the whole design: **only where scanning can't help, and only where there
is something to link to.** On a scanned row the link would be noise — that company is
already being watched — and a row reading "no URL on record" has nothing to point at, the
reason being the prompt to go and fill it in. The test asserts both halves, present and
absent, so it can't quietly spread to every row later.

**Process note:** while checking that both branches existed in the data, I ran
`manage.py shell` without `JOBSTUDIO_DATA` and it resolved through `~/.jobstudio.ini` to
the *real* job search — exactly what CLAUDE.md warns about. It was a read-only print and
nothing was written, but the habit is wrong: ad-hoc runs against this repo need the env
var set, every time. (The suite itself is safe regardless — `settings.py` pins it to
`example-data/` before `local_settings` loads.)
