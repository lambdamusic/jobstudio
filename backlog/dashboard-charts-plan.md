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
- Library still to pick. One library should cover all charts rather than accumulating
  several. **Apache ECharts** is the pragmatic default — Sankey, stacked area and pie all
  native, one file, MIT. **Plotly.js** covers the same ground and is larger. **d3 +
  d3-sankey** is smallest and most controllable but every chart is authored by hand;
  there is a `gen-d3` skill if that route is taken.

This is the web app's **first runtime dependency**. Record the version and origin, note
the licence, and check the minified bundle does not trip `tools/make-public-tree --check`.

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

- **R-S1 — Per-status entry stubs, not one source node.** A row with a blank `from_status`
  is where an application entered. On the tracker measured, of 57 applications only 33
  entered at `saved`; the other 24 were logged directly at `closed`, `applied`,
  `discarded`, `rejected`, `reviewing` or `interviewing`. A single "all applications"
  source node would assert a funnel nobody went through. Each status gets its own entry
  ribbon sized by its blank-`from_status` count.
- **R-S2 — Terminal "still here" stubs.** An application sitting in a status has no
  outgoing edge and would vanish from a flow diagram. Each node needs a terminal ribbon
  for its current occupancy. This is also the correctness check: for every node,
  `in − out = current count`. That reconciled exactly on the tracker measured, for all
  seven statuses, and a unit test should assert it rather than trusting it.
- **R-S3 — Backward edges: drop, but report.** A Sankey is a DAG; real transitions go
  backwards (`applied → reviewing` on a re-open). Order nodes by `STATUS_SORT_ORDER`,
  drop edges that run against it, and **print the count dropped beneath the chart**. On
  the tracker measured this was 2 of 120, so the rule is cheap — but silently losing
  edges is how a diagram starts lying.
- **R-S4 — The `applied` node is not what it looks like.** It is the largest node and
  includes applications that have had no response for months. Cross-reference §7: the
  ageing view must be adjacent, or this chart overstates how much is in flight.

**Must not.** Interpolate or infer transitions that were never recorded. Merge `discarded`
and `closed` — they mean different things (dropped by the candidate vs closed by the
employer) and the distinction is the interesting part of pre-application attrition.

**Done when.** Ribbons balance per R-S2 under test; the toggle switches without a page
load; the empty tracker and the 3-application example both render correctly per R3 — the
example having no inter-status edges at all is the specific case to get right.

---

## 4. Chart — status stock over time

**Question.** How has the shape of the pipeline changed — not how many events happened,
but how many applications sat in each status at each point in time.

**Source.** Replay `ApplicationStatusChange` forward in date order, carrying each
application's state; bucket weekly (ISO, Monday-starting, matching `_activity_weeks()`).

**Shape.** Stacked area, one band per status, ordered by funnel position so the bands read
top-to-bottom as the pipeline.

**Rules.**

- **R-T1 — Stock, not flow.** The existing Activity chart is flow (events per week). This
  is the complement and the one not currently shown. Do not replace the Activity chart;
  they answer different questions.
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

**Done when.** The total across bands equals the application count at every point; bulk
periods are visibly distinct; a tracker with one week of history renders R-T4's message.

---

## 5. Chart — companies tracked vs companies applied to

**Question.** How much of the watchlist has actually been acted on?

**Source.** `Company.status`, which is derived automatically — `applied` when the company
has an application in a *submitted* status (`applied` / `interviewing` / `rejected`), else
`watching`.

**Shape.** Donut with the proportion stated in the middle, rather than a two-slice pie.

**Rules.**

- **R-C1 — Say which definition is being used.** "Applied to" here means *submitted*. A
  company with three applications still at `saved` reads as `watching`. On the tracker
  measured, 23 companies had a submitted application while **35** had at least one
  application of any status — a 50% difference between two readings of the same phrase.
  The chart must name the one it means.

**Done when.** The two segments sum to the tracked company count, and the definition is on
the chart, not only in documentation.

---

## 6. Chart — applications per company

**Question.** How much of the tracker has been acted on, and where has the same company
been approached more than once? Replaces the originally-requested companies-vs-applications
pie, which charted two numbers that are not parts of a whole — an application belongs to a
company and one company can have several, so the two do not sum to anything and a pie
asserts that they do.

**Source.** `Company.objects.annotate(n=Count("applications"))`, bucketed 0 / 1 / 2 / 3+.

**Shape.** Small horizontal bar histogram, with the headline counts stated beside it.

**Rules.**

- **R-A1 — Declare unlinked applications.** `Application.company` is nullable, so an
  application with no company is invisible to a per-company count and the chart silently
  under-reports unless it states the number excluded. This was 12 of 57 when the
  requirements were written and is 0 today (see §9), but the rule stands: the count is
  shown whenever it is non-zero, with a pointer to `jobsdb.py link-company`, rather than
  the chart quietly covering fewer applications than it claims.

**Done when.** Bucket totals plus unlinked equals the application count, and the unlinked
count is shown.

---

## 7. Chart — ageing at `applied`

Not originally requested, and on the evidence the highest-value item here: it changes how
every other chart is read.

**Question.** Which submitted applications have gone quiet?

**Source.** For each `Application` with `status="applied"`, days since its most recent
`ApplicationStatusChange`.

**Shape.** Primarily a **list**, not a chart — the rows are individually actionable in a
way a distribution is not. A small strip plot of the ages alongside it is optional.

**Rules.**

- **R-G1 — Stale after 30 days** with no status change. On the tracker measured this
  flagged 4 of 17.
- **R-G2 — Pair with `next_action`.** The field already exists and nothing currently
  surfaces applications by staleness. A stale row with no `next_action` is the strongest
  signal on the dashboard.
- **R-G3 — State the consequence.** The `applied` count on the stat bar and the `applied`
  node in the Sankey both include these. Say so where they appear: an apparent pipeline of
  17 that contains several dead applications is not a pipeline of 17.

**Done when.** The list is reachable from the `applied` stat box, and the Sankey's
`applied` node carries the stale count.

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

0. **The `/stats/` page skeleton (§2a)** — view, template, URL, nav entry, `build_static`
   registration, and the empty/example states from R3 before any chart exists. Doing this
   first means every chart lands into a page whose cold-start behaviour is already proven.
1. **Ageing (§7)** — a list, no library needed, highest actionable value, and it
   establishes the framing the other charts are read through.
2. **Sankey (§3)** — the requested headline; brings the library in.
3. **Companies donut (§5)** and **applications-per-company (§6)** — cheap once the
   library is present; §9 is already done.
4. **Stock over time (§4)** — last, both because it is the most complex and because it
   improves as more organic history accumulates.
