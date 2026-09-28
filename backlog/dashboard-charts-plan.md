# Dashboard charts — requirements

Detail for `#42` in `TODO.md`. Raised 2026-09-28; requirements settled the same day
against a live tracker, so the design decisions below are grounded in real data
distributions rather than guessed at.

Figures quoted are from one live tracker at time of writing (57 applications, 141
companies, 120 recorded status transitions). They are here to justify design choices,
not as targets — every rule below must hold for an empty tracker and a large one too.

---

## 1. What exists, and the constraint that shapes everything

The dashboard (`/`, `tracker.views.home()`) has **one** chart: weekly Activity bars, three
event types, stacked. It is `div`s with server-computed inline pixel heights (`tl-bars` in
`home.html`). Everything else on the page is counts in boxes (`_statbar.html`) and tables.

**Rendering: a vendored JavaScript charting library.** Decided 2026-09-28.

- Stacked `div`s cannot express a Sankey — proportional ribbons between nodes need real
  geometry. Server-generated inline SVG was the dependency-free alternative and was
  rejected as more authoring effort than four chart types justify.
- **The static export is not a blocker.** `build_static._copy_static()` already copies
  every `STATICFILES_DIRS` tree into `site/`, so a library under `static/` ships with the
  export and the builder needs no change.
- **Vendor the file; do not use a CDN.** The site then stays self-contained, works
  offline, and makes no third-party request while someone browses their own job search.
- **Picked 2026-09-28: Apache ECharts 6.1.0**, Apache-2.0, vendored at
  `src/web/static/vendor/echarts-6.1.0.min.js` (1.1 MB minified). It covers Sankey,
  stepped stacked area, donut and bar in one file; Plotly.js covers the same ground and is
  larger; d3 + d3-sankey is smaller and more controllable but is four chart types authored
  by hand. Provenance, hash and the upgrade procedure are in `static/vendor/README.md`.
  Rendered with the **SVG** renderer rather than canvas, so the marks are in the DOM and
  the published mirror stays inspectable and printable.

This is the web app's **first runtime dependency**. Recorded, licensed and checked:
`make-public-tree --check` stays clean with the bundle in the tree (it costs the scan
about ten seconds), and `build_static` ships it into `site/` with no change to the builder,
exactly as predicted above.

**Load the `dataviz` skill before building any of these.** They must read as one system —
shared palette, shared type scale, consistent legends — not four separately-styled charts.

---

## 2. Requirements common to every chart

**R1 — One query layer.** `dashboard_summary()` (CLI) and `home()` (web) share private
helpers on purpose; see `docs/dashboard-status.md` "One function, two consumers". Every
new chart's data comes from a new `_helper()` used by both, or `/jobstudio status` and the
dashboard begin to disagree. That divergence was a real bug, fixed 2026-09-16.

**R2 — The server computes, the client draws.** Follow the existing split: the view
produces finished numbers, the template embeds them as JSON, the library only renders. No
aggregation in JavaScript. This keeps the CLI mirror possible and the static export inert.

**R3 — Works from zero. This is a first-class requirement, not a fallback.** Most people
who see these charts will see them on a tracker with almost nothing in it, and a dashboard
that looks broken on day one is worse than one with fewer charts. Three tiers must all be
correct, and all three are testable:

| Tier | Data | Every chart must |
|---|---|---|
| **Empty** | Fresh data root: 0 applications, 0 companies, 0 transitions | Render a stated absence — "no applications yet", with a pointer to `/jobstudio application`. Never an empty axis, a zero-height shape, a division by zero, or a legend for series that do not exist |
| **Example** | `init --from-example`: **3 applications** (one each `applied`, `saved`, `reviewing`), **3 status changes — all of them `(start) → X`, so zero transitions between statuses**, 6 companies | Render truthfully at tiny scale. The Sankey in particular has *no inter-status edges at all* here and must say so rather than drawing a degenerate diagram |
| **Real** | Tens to hundreds | Stay legible as volume grows |

The example tier is the sharp one and it is free to test: the suite is pinned to
`example-data/`, so each chart gets a test asserting it renders at exactly that volume.
A chart that cannot be made to look right with three applications should render its
"needs more data" state instead, and say what it needs — that is a legitimate outcome,
not a failure.

**R4 — Reconstructed history must be visibly marked.** `ApplicationStatusChange` rows
created by the 2026-09-08 backfill take their timestamp from `Application.date`, and bulk
logging sessions cluster many transitions on one day. On the tracker measured, **two ISO
weeks held 62% of all 120 transitions**. Any time-based chart that smooths over this
implies precision that does not exist. See §4.

**R5 — Theme and accessibility.** Must work in both light and dark, not rely on colour
alone to distinguish series (status is also ordered, so use position and labels), and
carry text alternatives — the dashboard is exported to a static site where a screen
reader is the only fallback.

**Resolved 2026-09-28: one status palette for the whole site.** The charts first used two
ordinal ramps of their own, which was defensible and wrong in practice — the same seven
words were one set of colours in a pill and another in a chart. Badges and charts now read
the same CSS custom properties (`--st-*` in `site.css`). Two hues moved to make that work:
`closed` went from dusty red to amber, because it was a near-twin of `rejected` and the two
mean different things, and `discarded` went from the same grey as `saved` to slate. Every
adjacent pair in funnel order clears the CVD and normal-vision floors; the two greys sit
below the chroma floor on purpose, because grey *is* their meaning.

**R6 — No new model.** `ApplicationStatusChange(application, changed_at, from_status,
to_status)` is written automatically by a `post_save` signal and already backfilled. It is
an edge list and an event stream. Nothing below needs a migration.

---

## 2a. Where these live: a new `/stats/` page

**Not on the dashboard yet.** Everything below is built on a new **`/stats/`** page, as a
staging ground for review and testing. Reasons: the dashboard is the page most used daily
and should not churn while chart designs are still being judged; several of these may not
survive contact with real rendering; and a separate page can carry the debugging affordances
(raw numbers beside each chart, the reconciliation check from R-S2 shown rather than only
asserted) that a finished dashboard should not.

- New view, template and URL alongside the existing list pages; linked from the main nav so
  it is reachable, and enumerated in `build_static` so the link-check pass does not fail.
- The same `_helper()` functions required by R1 — `/stats/` is a second *consumer* of the
  query layer, never a second implementation.
- **Promotion to the dashboard is a later, separate decision**, chart by chart. Some may
  stay on `/stats/` permanently; that is a fine outcome for anything analytical rather than
  daily.

All of it on a **branch** — `dashboard-charts` — not on `dev`.

---

## 3. Chart — status flow (Sankey)

**Question.** Where do applications actually go, and where do they die?

**Source.** `ApplicationStatusChange`, grouped by `(from_status, to_status)`. Statuses and
their order come from `STATUS_SORT_ORDER` in `appfolder.py`: `applied`, `interviewing`,
`reviewing`, `saved`, `discarded`, `closed`, `rejected`.

**Shape.** Two views behind a toggle, defaulting to the full funnel.

- **Full funnel** — entry → `saved` → `reviewing` → `applied` → `interviewing` →
  `rejected` / `closed` / `discarded`.
- **Post-application** — only what happens from `applied` onward. Tighter, and answers
  "what happens after I submit" without the pre-application attrition.

**Rules.**

- **R-S1 — Entry stubs for mid-funnel arrivals, not one source node.**

  **Superseded in the data and narrowed in the code, 2026-09-28.** The measurement below
  was real — 24 of 57 applications did not enter at `saved` — but it described how the
  tracker was used while it was being built, not a difference between those applications
  and the rest. Nobody applies to a role they never looked at. `manage.py
  backfill_saved_entry` gave each of them a `saved` entry dated the day before its first
  recorded status, so the funnel starts in one place.

  The rule then narrowed to match: entering at the window's **first** status is no longer
  drawn, because that node *is* the start and a stub in front of it only said "these
  applications exist". Entering anywhere else still gets its own ribbon — an application
  that appears at `closed` never passed through the statuses to its left, and a diagram
  that quietly routed it through them would be lying. So there are no entry stubs on this
  tracker today, and there will be one the next time it happens for real.

  The original argument, which is why the rule survives at all: A row with a blank `from_status`
  is where an application entered. On the tracker measured, of 57 applications only 33
  entered at `saved`; the other 24 were logged directly at `closed`, `applied`,
  `discarded`, `rejected`, `reviewing` or `interviewing`. A single "all applications"
  source node would assert a funnel nobody went through. Each status gets its own entry
  ribbon sized by its blank-`from_status` count.
- **R-S2 — Terminal stubs.** An application sitting in a status has no outgoing edge and
  would vanish from a flow diagram. Each node needs a terminal ribbon for its current
  occupancy. This is also the correctness check: for every node,
  `in − out = current count`. That reconciled exactly on the tracker measured, for all
  seven statuses, and a unit test should assert it rather than trusting it.

  **Changed 2026-09-28.** Seven per-status "still here" stubs said the same thing seven
  times. The occupancy ribbons now run on to **two** end nodes instead — `active`
  (anything not `discarded`, `closed` or `rejected`) and `inactive` — which is the same
  information plus where the tracker actually stands. The reconciliation is unchanged:
  occupancy still comes from the database, not from the ribbons, so it is still the check.

  Note `active` here is **wider than `ACTIVE_STATUSES`** (applied + interviewing), which is
  what the stat bar's *active* box counts. Two different questions — "submitted and still
  in play" and "not over yet" — and the note under the chart says which this one is, since
  the same word now appears on the same site meaning two things.
- **R-S3 — Backward edges: drop, but report.** A Sankey is a DAG; real transitions go
  backwards (`applied → reviewing` on a re-open). Order nodes by funnel position, drop
  edges that run against it, and **print the count dropped beneath the chart**. On
  the tracker measured this was 2 of 120, so the rule is cheap — but silently losing
  edges is how a diagram starts lying.

  **Correction, 2026-09-28 (building it).** This rule originally said to order nodes by
  `STATUS_SORT_ORDER`. That is the *triage* order — most active first: `applied`,
  `interviewing`, `reviewing`, `saved`, … — so orienting the flow by it would make
  `saved → applied` run backwards and the rule would drop the commonest transition in any
  tracker, not two edges in a hundred. The measured "2 of 120" is itself the evidence: it
  can only hold for the funnel order this section's **Shape** already spells out. The code
  has its own `FUNNEL_ORDER` (`tracker/views.py`) — `saved`, `reviewing`, `applied`,
  `interviewing`, then the three terminal statuses keeping their `STATUS_SORT_ORDER`
  sequence relative to each other.
- **R-S4 — The `applied` node is not what it looks like.** It is the largest node and
  includes applications that have had no response for months. Cross-reference §7: the
  ageing view must be adjacent, or this chart overstates how much is in flight.

**Must not.** Interpolate or infer transitions that were never recorded. Merge `discarded`
and `closed` — they mean different things (dropped by the candidate vs closed by the
employer) and the distinction is the interesting part of pre-application attrition.

**Done when.** ✅ 2026-09-28. Reconciliation is asserted for every node, and there is a
second test that *breaks* it (a status written behind the signal's back) so the check
cannot quietly become decoration. Both views ship in one payload, so the toggle is a
redraw. The example tracker has no inter-status edge at all and says so instead of drawing.

---

## 4. Chart — status stock over time

**Question.** How has the shape of the pipeline changed — not how many events happened,
but how many applications sat in each status at each point in time.

**Source.** Replay `ApplicationStatusChange` forward in date order, carrying each
application's state; bucket weekly (ISO, Monday-starting, matching `_activity_weeks()`).

**Shape.** Stacked area, one band per status, ordered by funnel position so the bands read
top-to-bottom as the pipeline — and, behind a toggle (2026-09-28), **one line per status
showing what moved that week**.

The second view is deliberately a different *measure*, not the same numbers unstacked. It
counts applications that arrived in each status during that week, so it falls back to zero
in a quiet week where the stock view holds a flat line — and it is the reading that can be
followed one status at a time, which a stack cannot be: a band's thickness is its own value
but its height is everyone else's, so a status that never moved still appears to.

**Rules.**

- **R-T1 — Stock, not flow.** The existing Activity chart is flow (events per week). This
  is the complement and the one not currently shown. Do not replace the Activity chart;
  they answer different questions.

  *Amended 2026-09-28: the toggle adds flow per status, which the Activity chart does not
  show — it counts three event types across the whole tracker. Three charts, three
  questions, and none of them replaces another.*
- **R-T2 — Mark reconstructed periods.** Per R4. Weeks whose transitions came
  predominantly from the backfill, or from a single bulk-logging day, are shaded
  differently and the legend says "reconstructed". On the tracker measured this covers the
  two weeks holding 62% of history — without the marking, the chart shows two cliffs and
  reads as a dramatic change in activity that did not happen.
- **R-T3 — Steps, not curves.** No smoothing or interpolation between points. State
  changes are discrete events; a smooth curve invents intermediate values.
- **R-T4 — Degrade honestly when thin.** Below a threshold of distinct weeks with
  organic (non-bulk) transitions, say so rather than drawing. The chart improves on its
  own as the tracker is used; it should not pretend to be ready before it is.

**Must not.** Back-fill state for applications before their first recorded transition.

**Done when.** ✅ 2026-09-28. Backfilled rows are detected exactly rather than guessed
at: the 2026-09-08 backfill dated them from `Application.date`, so they sit at precisely
local midnight. A bulk logging session is a day holding 5+ transitions. A week where those
outnumber the organic ones is shaded gold and called reconstructed. Below three weeks
carrying organic transitions the chart states what it needs instead of drawing.

---

## 5. Chart — companies tracked vs companies applied to

**Question.** How much of the watchlist has actually been acted on?

**Source.** `Company.status`, which is derived automatically — `applied` when the company
has an application in a *submitted* status (`applied` / `interviewing` / `rejected`), else
`watching`.

**Shape.** Donut with the proportion stated in the middle, rather than a two-slice pie.

**Three slices since 2026-09-28, and a model change behind them.** `Company.status` was two
states, and two could not tell "I have an application open with them" from "I have never
done anything about them". It is now `applied` / `reviewing` / `watching`, derived the same
way off the same signals, and the donut draws it directly — so the chart and the badge on
the company's own row cannot disagree. See `docs/companies.md`.

**Rules.**

- **R-C1 — Say which definition is being used.** *(Still the rule, now about a different
  ambiguity: with three states, the slippery one is `watching`, which covers both "never
  applied to" and "tried and it ended". The chart states the split.)* "Applied to" here means *submitted*. A
  company with three applications still at `saved` reads as `watching`. On the tracker
  measured, 23 companies had a submitted application while **35** had at least one
  application of any status — a 50% difference between two readings of the same phrase.
  The chart must name the one it means.

**Done when.** ✅ 2026-09-28. Both readings are computed and the looser one is stated
beneath the donut whenever it differs, so the gap is visible rather than a footnote.

---

## 6. Chart — applications per company

**Question.** How much of the tracker has been acted on, and where has the same company
been approached more than once? Replaces the originally-requested companies-vs-applications
pie, which charted two numbers that are not parts of a whole — an application belongs to a
company and one company can have several, so the two do not sum to anything and a pie
asserts that they do.

**Source.** `Company.objects.annotate(n=Count("applications"))`, bucketed 0 / 1 / 2 / 3+.

**Shape.** Small horizontal bar histogram, with the headline counts stated beside it, and
each bucket naming the companies in it (2026-09-28) — a count answers "how many", and the
next question is always "which". Long buckets link into `/companies/` narrowed to
themselves via a `#apps=<bucket>` fragment rather than a querystring, which the static
build could not publish.

**Rules.**

- **R-A1 — Declare unlinked applications.** `Application.company` is nullable, so an
  application with no company is invisible to a per-company count and the chart silently
  under-reports unless it states the number excluded. This was 12 of 57 when the
  requirements were written and is 0 today (see §9), but the rule stands: the count is
  shown whenever it is non-zero, with a pointer to `jobsdb.py link-company`, rather than
  the chart quietly covering fewer applications than it claims.

**Done when.** ✅ 2026-09-28. Asserted both ways: buckets sum to the company count, and
linked applications plus unlinked sum to the application count.

---

## 7. Chart — ageing at `applied`

Not originally requested, and on the evidence the highest-value item here: it changes how
every other chart is read.

**Question.** Which submitted applications have gone quiet?

**Source.** For each `Application` with `status="applied"`, days since its most recent
`ApplicationStatusChange`.

**Shape.** Bars over age bands: 0–7, 8–14, 15–30, 31–60, 60+ days, the third band ending
exactly at `STALE_AFTER_DAYS` so "past this line is quiet" is a property of the bands
rather than a rule drawn over them. The two stale bands take the gold ramp and say *quiet*
in the axis label, so the threshold is carried by colour **and** position **and** words.

**Changed 2026-09-28, mid-build.** This said "primarily a **list**, not a chart — the rows
are individually actionable in a way a distribution is not", and it was built that way
first. The list is the applications page's job: it already tabulates rows, and sorting it
by last-moved would put them where someone is already looking. What a separate page can
say that a table cannot is the *shape* — whether the quiet end is growing. Applications
with no recorded date are counted separately rather than swept into the first band; an
unknown age is not a small one.

The rows came back under the chart the same day, as a linked table. The bars answer "is
the quiet end growing"; the original objection — that these rows are individually
actionable — was right about what you do next. `/applications/` has the sortable list, and
this is the same rows in band order, one click from each application.

**Rules.**

- **R-G1 — Stale after 30 days** with no status change. On the tracker measured this
  flagged 4 of 17.
- **R-G2 — Pair with `next_action`.** The field already exists and nothing currently
  surfaces applications by staleness. A stale row with no `next_action` is the strongest
  signal on the dashboard.
- **R-G3 — State the consequence.** The `applied` count on the stat bar and the `applied`
  node in the Sankey both include these. Say so where they appear: an apparent pipeline of
  17 that contains several dead applications is not a pipeline of 17.

**Done when.** ✅ 2026-09-28. The view is reachable from the `applied` stat box — which
now carries a one-line note, on every page that shows it, saying how much of that count has
not moved — and the Sankey's `applied` node is labelled `applied · N quiet`. The same rows
are in `/jobstudio status` under "Gone quiet", from the same helper, so the terminal and
the page cannot come to disagree about what quiet means.

---

## 8. Also suggested

Lower priority, listed so they are not re-derived later.

- **Funnel conversion rates** — the Sankey's nodes as percentages between stages. Shows
  *where* applications die rather than how many did.
- **Outcome rate by target area** — applications per `Application.area` with interview
  rate. Feeds directly back into which `jobs/targets/*.yaml` deserves effort and how the
  CV is positioned. Note the distribution is uneven — on the tracker measured one area
  held 27 of 57 — so small-sample areas need a minimum before a rate is shown at all.
- **Scan → application conversion** — of roles a scan scored strong, how many became
  applications. The only real measure of whether scanning earns its run cost.
- **Fit-rating calibration** — do 5-star companies convert better than 3-star? A check on
  one's own judgement, answerable only from tracked history.

---

## 9. Data-quality prerequisite — done 2026-09-28

12 of 57 applications had no `company` link, which would have left §6 and §8 quietly
covering 45 of 57. Resolved before building anything, and the resolution is worth
recording because the obvious fix did not apply:

**`link-company` could not fix any of them.** It matches an application's `company_name`
against `Company.name` exactly, and none of the twelve companies were in the tracker at
all — they were applications made before the company tracker existed. Fuzzy matching found
nothing real either. So the gap was eleven missing company rows, not eleven broken links.

Eleven rows were created to carry that history, plus one genuine mis-link: an application
recorded under a departmental name pointed at an organisation already tracked under its
institute name — strings with nothing in common, which no matching rule would ever catch,
and only a person reading both would spot.

**The rows carry no careers URL on purpose.** Nine of the twelve applications are already
closed, discarded or rejected, and inventing careers URLs for them would add nine
companies to what `scan` fetches on every run, forever, for no benefit. With the field
empty, `scan_sources.coverage()` reports the graded reason "no URL on record" — accurate,
and the one reason in that vocabulary that anyone can close in a minute if they later care.

Distribution afterwards: 105 companies with no application, 40 with one, 5 with two, 1
with three, 1 with four; 0 unlinked applications; 47 companies with at least one
application against 24 with a *submitted* one — which is the §5 R-C1 distinction, now with
a nearly two-fold gap between the two readings.

**One flaw found doing it:** `jobsdb.link_company()` **silently does nothing when no
company matches.** It looks the name up, finds nothing, saves nothing, and returns the
application dict, so the CLI prints `#N Company` exactly as it does on success. That is how
twelve applications stayed unlinked without anyone noticing. Worth making it say so —
small, and in the same family as `#41`.

---

## 10. Suggested build order

0. **The `/stats/` page skeleton (§2a)** — ✅ **done 2026-09-28.** View, template, URL,
   nav entry, `build_static` registration, and the empty/example states from R3 before any
   chart exists. Doing this first means every chart lands into a page whose cold-start
   behaviour is already proven.

   What landed, and what a chart inherits by using it:

   - `tracker.views._stats_volumes()` — the counts every chart's "can I draw this
     honestly?" turns on, in one helper because the page *states them beside the charts*:
     a refusal to draw and the readout explaining it have to come from one query. It
     splits **entry events** (blank `from_status`) from **transitions**, which is the
     distinction R-S1 and R3 both hang on and the one a bare "status changes" count hides.
   - `tracker/_chart_slot.html` — the three R3 states in one place: nothing tracked at
     all, data but not the data this chart needs, and not built yet. A chart keeps the
     slot as its else-branch rather than replacing it; the tiers are permanent, not
     scaffolding.
   - Sections are laid out in this build order rather than the document order above, so
     ageing sits above the Sankey per R-G3.
   - Eight tests in `StatsPageTests`, covering all three tiers — including the example
     tier's sharp case (three status changes, none of them a transition, so only the two
     history charts are held back) and R-A1's unlinked count appearing and disappearing.
1. **Ageing (§7)** — ✅ done 2026-09-28. Built as a list, then changed to age bands
   mid-build (see §7). It does establish the framing: the `applied` stat box and the
   Sankey's `applied` node both now say how much of that number has gone quiet.
2. **Sankey (§3)** — ✅ done 2026-09-28. Brought ECharts in (§1), and turned up the
   node-order correction recorded under R-S3.
3. **Companies donut (§5)** and **applications-per-company (§6)** — ✅ done 2026-09-28.
   Cheap once the library was present, as expected.
4. **Stock over time (§4)** — ✅ done 2026-09-28. The most complex, and the one that
   improves on its own: it stays behind its "not enough lived history" message until
   three weeks carry organic transitions.

## 11. What is left

- **Promotion to the dashboard** (§2a) — still an open decision, chart by chart. Nothing
  has moved to `/` except the one-line staleness note on the stat bar, which is a
  correction to a number the dashboard already shows rather than a chart.
- ~~**A sortable applications list.**~~ Done 2026-09-28: `/applications/` has a toolbar —
  search, target area, status, and sorts including *longest without moving* — and a
  **Last moved** column taken from the change log rather than from `Application.date`.
  `/companies/` got the same treatment: one table instead of a tab per category, with
  category and date-added as columns, filters, and paging.
- **§8's four suggestions** — none built. Funnel conversion rates are the natural next one:
  the Sankey's nodes as percentages, which is where applications die rather than how many.
- **Dark mode.** The chart palette is defined as CSS custom properties in `site.css` and
  read from there at draw time, so a dark scheme is a change in one place. The app has no
  dark mode at all today, so there is nothing yet for the charts to follow — which is why
  R5's light-and-dark requirement is only half met, on purpose.
