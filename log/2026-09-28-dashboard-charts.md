# The charts page (TODO `#42`)

2026-09-28

Requirements were settled against a live tracker that morning
(`backlog/dashboard-charts-plan.md`); this is the build. Five charts, a new page, and the
web app's first runtime dependency.

## Why a separate page

`/stats/`, not the dashboard. The dashboard is the page used daily and should not churn
while chart designs are still being judged; several of these might not survive contact
with real rendering; and a staging page can carry the debugging affordances a finished
dashboard should not — the raw numbers beside each chart, the reconciliation check shown
rather than only asserted.

The skeleton went in **before any chart**: view, template, URL, nav entry, `build_static`
registration, and the three data tiers from R3 — nothing tracked at all, data but not the
data this chart needs, not built yet. That order was the right call. Most people meet a
page like this on a tracker with almost nothing in it, and those states are the part that
is hardest to retrofit; building them first meant every chart landed into a page whose
cold-start behaviour was already proven, and each one kept the slot as its else-branch.

## The library

**Apache ECharts 6.1.0**, Apache-2.0, vendored at `src/web/static/vendor/`, 1.1 MB
minified. One file covers Sankey, stepped stacked area, donut and bar; d3 + d3-sankey is
smaller and more controllable but is four chart types authored by hand. Vendored rather
than CDN so the site stays self-contained and makes no third-party request while someone
browses their own job search. SVG renderer, not canvas, so the marks are in the DOM.

The two predictions in the plan both held: `build_static._copy_static()` shipped it into
`site/` with no change to the builder, and `make-public-tree --check` stays clean with a
megabyte of minified JavaScript in the tree (it costs the scan about ten seconds).

## Two things the build changed in the plan

**R-S3's node order was wrong, and the plan's own measurement is what shows it.** The rule
said to order Sankey nodes by `STATUS_SORT_ORDER` and drop edges running against it. But
that is the *triage* order — `applied`, `interviewing`, `reviewing`, `saved`, … — so
`saved → applied` would run backwards and the rule would drop the commonest transition in
any tracker. The plan also recorded that only **2 of 120** transitions ran backwards, which
can only be true of the funnel order its own "Shape" paragraph spells out. The code carries
its own `FUNNEL_ORDER`.

**§7 became a chart, mid-build.** It was specified as "primarily a list, not a chart — the
rows are individually actionable in a way a distribution is not", and it was built that
way first. Michele's call on seeing it: the individual rows belong on `/applications/`,
which already tabulates them and wants a sort by last-moved; what a separate page adds is
the *shape* — whether the quiet end is growing. So: bands of 0–7, 8–14, 15–30, 31–60, 60+
days, the third ending exactly at the staleness threshold, the two past it in gold and
labelled *quiet*. That trade is only finished when the applications list grows the sort;
until then the quiet rows are reachable but not sortable.

## Things worth keeping

**The terminal stub is a check, not just a shape.** Each Sankey node carries a "still here"
ribbon for its current occupancy, taken from the database rather than from the arithmetic —
so `entered + in − out` must equal the status count, and the page says whether it did. The
test that matters is the second one: it writes a status behind the signal's back
(`.update()`, no `save()`) and asserts the check *fails*. A correctness check nobody has
seen fail is decoration.

**Backfilled history is detectable, not guessable.** The 2026-09-08 backfill dated its rows
from `Application.date` via `datetime.combine(date, time())` — so every one of them sits at
exactly local midnight. That is a precise signal for "this week was reconstructed", far
better than the volume heuristic the plan imagined. Bulk logging sessions still need one (a
day holding five or more transitions), and a week where those outnumber the organic ones is
shaded gold. Without it the chart shows two cliffs and reads as a change in activity that
did not happen.

**The table is the page; the chart is the enhancement.** Every chart's numbers are in the
markup as a `<details>` table before ECharts runs. Three requirements collapse into that
one arrangement: the page reads with no JavaScript, a screen reader gets values rather than
a drawing (the published mirror has no other affordance), and §2a's "raw numbers beside
each chart" is satisfied without building anything extra.

**Colour: two ordinal ramps, not seven hues.** Status is ordered, so the `dataviz` skill's
rule applies — one hue, monotone lightness steps. Cool steps run light-to-dark through the
funnel, warm steps through the three ways an application ends, gold marks attention. Each
ramp was run through the skill's validator rather than eyeballed (monotone L, adjacent
ΔL ≥ 0.06, light end ≥ 2:1 on white); the first candidates failed the light-end contrast
floor and were re-stepped. Defined as CSS custom properties in `site.css` and read at draw
time, so a dark mode later is a change in one place.

## What is left

Promotion to the dashboard (chart by chart, undecided), the sortable applications list,
§8's four suggestions — funnel conversion rates first — and dark mode, which the charts are
ready for but the app does not have.

---

## Second pass, same day: review comments

Michele reviewed the five charts. Most of what came back was not about charts.

**"The colors should reflect the colors of the status pills."** Fair, and it exposed a real
inconsistency: the charts had their own two ordinal ramps, defensible on their own terms
(status *is* ordered) and wrong in practice, because the same seven words were one set of
colours in a pill and another in a diagram. There is now one status palette in `site.css`
that both read. Two hues had to move to make it work at chart scale: `closed` was a
near-twin of `rejected` — ΔE 5 under normal vision, 1.2 under protanopia — and the plan
refuses to merge those two statuses precisely because they mean different things, so a
palette that made them look identical was arguing against the plan. It went amber.
`discarded` was the same grey as `saved` and went slate. Every adjacent pair in funnel
order now clears both CVD floors.

**"I don't understand why we have a status 'logged'. Maybe this is an artifact of old
data? If so, let's rectify in the data."** It is not an artifact, and this is the one thing
in the review I did not do. The tracker was read (read-only) to answer it: of 57
applications, **33 entered at `saved` and 24 did not** — 8 logged straight into `closed`,
5 into `applied`, 4 `discarded`, 3 `reviewing`, 3 `rejected`, 1 `interviewing`. Those are
roles logged after the deadline had passed, or after already applying. Forcing them all
through `saved` would invent 24 applications' worth of transitions that never happened,
which is the one thing §3 says the chart must not do. The node was relabelled **"added"**
instead — it read as an eighth status, which was the real complaint.

**"Not sure the 'still here' stage makes sense."** Right, and the replacement he proposed
is better: two ends, `active` and `inactive`, rather than seven stubs saying the same thing
seven times. One wrinkle worth knowing — `active` here means "not over", which is wider
than `ACTIVE_STATUSES` (applied + interviewing), the definition the stat bar's *active* box
uses. The same word now means two things on the same site, so the note under the chart
spells out which one it is.

**The company donut needed a third state**, and that turned out to be a model change rather
than a chart change: `Company.status` was two states and could not tell "I have an
application open with them" from "I have never done anything about them". Three now, derived
the same way. Doing it in the chart alone would have made the donut disagree with the badge
on the company's own row.

**And two pages got rebuilt.** `/applications/` traded its target-area chips for a toolbar
(search, area, status, sorts including *longest without moving*) and gained a **Last moved**
column from the change log — which is what finally pays for §7 giving up its table.
`/companies/` became one searchable, sortable, paged table with category as a column. Both
filter in the browser, which is the only way this works in a published static mirror:
a querystring cannot be a file.

**One bug worth recording.** Three helpers ended up defined twice in `views.py`, the stale
copies shadowing the new ones, because an insertion anchored on a comment marker that the
inserted text itself contained. The suite stayed green throughout — the duplicated
`_company_coverage` was identical, and the per-company tests only checked counts, which the
old implementation also satisfied. What caught it was looking at the page. The test that
would have caught it (every bucket names its companies) exists now.

---

## Third pass: the data cleanup, and the rest of the review

**The `saved` entries.** The previous pass argued that 24 of 57 applications genuinely did
not enter at `saved`, and that rewriting history to say otherwise would be inventing
transitions. Michele's answer was the right one and I had missed it: the *reason* those 24
look different is that he was building the tracker at the time — adding applications and
setting their status in one go, before there was a status log at all. That is not history
worth preserving. It is a scar from the tool's own construction.

So `manage.py backfill_saved_entry` gives each of them a `saved` entry dated the day before
its first recorded status, and points the old first change at it so it becomes a transition.
Applied to the live tracker after `tools/db-dump`: 24 fixed, 33 already fine, every node
still reconciles, still 2 backward edges — the same number the requirements measured, which
is the check that the rewrite did not quietly break the arithmetic.

**The rule it papers over stays in the code.** `_status_flow()` still draws one entry ribbon
per status. An application logged straight into `closed` next week will get its own again,
correctly. What changed is the data, not the assumption — a chart that hardcoded "everyone
starts at saved" would go back to lying the first time that happened.

**`reviewing` showing 0 was a derived-field problem, not a chart problem.** `Company.status`
is maintained by a signal on application save, so widening it from two states to three only
affected companies whose applications happened to move afterwards. Migration
`0013_recompute_company_status` recomputes every row. On the live tracker: 24 applied,
8 reviewing, 120 watching — the 8 that were invisible.

**The status dropdown on `/applications/`** now appears only on `/all/`. Everywhere else
the page *is* a status, chosen by the boxes above it, and a second control saying the same
thing is furniture. On the full list there is no status yet and it composes with the search
and the area filter, which the boxes cannot do.

**The stock chart's second view** is one line per status. Worth stating why both exist: in
a stack, a band's thickness is its own value but its *height* is everyone else's, so a
status that never moved still appears to move. That makes a stack unreadable one series at
a time, which is exactly what "what happened to `interviewing`" asks.

**The CV page** was two links in a wide panel. Now two cards with what each base is for, its
length in words, its section count and when it was last edited — read off the file, because
a stored copy goes stale the moment someone edits the CV in an editor. And the tailored
table carries the application's status, so the page that lists the effort also says what
came of it.

**Two follow-ups, same evening.** The "added" column went: with every application now
starting at `saved`, a stub in front of the first node only said "these applications
exist". The *rule* narrowed rather than disappeared — entering at the window's first status
is not drawn, entering anywhere else still is, so the next application logged straight into
`closed` is visible instead of being silently routed through statuses it never touched.

And the unstacked stock view was still drawing stock, which made it a worse version of the
stacked one. It now shows **flow**: how many applications arrived in each status during that
week. That is a different measure, not a different skin, and the note says so — a quiet week
reads zero here and a flat line there. It also makes the bulk-logging weeks obvious, since a
session that recorded a fortnight of decisions in one afternoon is a spike in this chart and
barely a step in the other.
