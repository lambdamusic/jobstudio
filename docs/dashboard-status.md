# How the dashboard and status report work

Part of the **[docs/](README.md)** guide collection. For *when* to check it, see
[workflow.md](workflow.md) "Any time" — this is a deep dive into what the web
dashboard (`/`) shows, and how `/jobstudio status` mirrors it in the terminal.

Fixed 2026-09-16: `/jobstudio status` used to tell Claude to read the retired
`applications.md`/`companies.md` markdown files by hand and compute counts against a
status vocabulary (`screening`, `offer`) that no longer exists — a leftover from before
the Django migration. It now just runs one command and prints the result verbatim.

```bash
tools/py src/jobsdb.py status
python src/jobsdb.py status --json    # same data, unformatted
```

## One function, two consumers

`jobsdb.py::dashboard_summary()` queries the Django models through the **same private
helper functions** the dashboard view (`tracker.views.home()`) itself calls —
`_status_summary()`, `_activity_weeks()`, `_recently_applied()`, `_recent_companies()`,
`_recent_scans()`. The web dashboard and the CLI report are two renderings of one query
layer, not two implementations that happen to agree — that's the fix, not just a
rewrite. `_recent_companies()` and `_recent_scans()` were extracted out of `home()`
specifically to make this possible (2026-09-16); `_status_summary()`, `_activity_weeks()`
and `_recently_applied()` were already standalone.

## At a glance: pace and outcome rates

Added 2026-09-30. The first thing on `/stats/` (not the dashboard, by choice) and the
first block of `/jobstudio status`, both from `_headline_metrics()`:
applications per week over the last 4 weeks and all time, and the share that reached
interview, were rejected, and have no answer yet.

Everything is **out of submitted applications**, meaning those whose history ever reached
`applied`, not everything tracked. Interviewed and rejected are "ever reached", so an
application interviewed and then rejected counts in both. "No answer yet" is shown beside
them because while it is large, both rates are lower bounds. Submission dates that are
backfill (exactly local midnight) are counted and the all-time pace says it is approximate.

## The charts page (`/stats/`)

`/stats/` is where the charts from `backlog/dashboard-charts-plan.md` live. It is
deliberately not the dashboard: `/` is the page used daily and should not churn while the
designs are being judged, and `/stats/` can carry the numbers each chart was computed from
beside it. Promotion to the dashboard is a separate decision, chart by chart.

| Chart | Helper | What it is |
|---|---|---|
| **Ageing at applied** | `_ageing_at_applied()`, `_ageing_bands()` | Applications at `applied` by how long since they last moved, in bands breaking at 30 days; the rows behind the bars are listed and linked under the chart |
| **Status flow** | `_status_flow()` | A Sankey: an entry ribbon per status, a "still here" ribbon carrying each status's current occupancy, and a toggle between the full funnel and what happens from `applied` onward |
| **Companies tracked vs applied to** | `_company_coverage()` | A donut. "Applied to" means *submitted*, and the looser reading is stated whenever it differs |
| **Applications per company** | `_applications_per_company()` | How many companies carry 0, 1, 2, 3+ applications, with the unlinked applications declared |
| **Status over time** | `_status_stock()` | Weekly replay of the change log, two measures behind a toggle: **stock** (where every application sat at the end of each week, stacked) and **flow** (how many arrived in each status during it, one line per status). Reconstructed weeks shaded in both |

Four things are worth knowing before changing any of them.

**Entries are not transitions.** An `ApplicationStatusChange` with a blank `from_status`
records where an application was first logged; only a move between two statuses is an edge
in a flow diagram or a step in a history. `_stats_volumes()` splits the two and the page
shows both, because the difference is what decides whether a chart can draw at all. The
example data root has three status changes and no transitions, so the flow and stock charts
there state what they are waiting for — `tracker/_chart_slot.html` owns that message, in
three states: nothing tracked at all, not enough of the right data, not built yet.

**The server finishes the arithmetic.** `charts.js` only draws. Everything it needs is in
one `json_script` payload the view rendered, which is what keeps the terminal mirror
possible — `/jobstudio status` already prints the ageing rows from the same helper, under
"Gone quiet" — and the static export inert.

**The table is the page; the chart is the enhancement.** Every chart's numbers are in the
markup as a `<details>` table before ECharts runs, so the page reads with no JavaScript, a
screen reader gets values rather than a drawing, and the numbers can be checked against the
shape. `charts.js` adds `js-charts` to `<body>` and folds the tables away once it has
drawn — the same arrangement `tabs.js` uses.

**The colours are two ordinal ramps, not seven hues.** Status is *ordered*: cool steps run
light-to-dark through the funnel, warm steps through the three ways an application ends,
and gold marks attention. They are defined once as CSS custom properties in `site.css` and
read from there at draw time, so the palette has one home.

## What each section shows

| Section | Query | Notes |
|---|---|---|
| **Status counts** | `_status_summary()` | One row per status in `STATUS_SORT_ORDER` (`appfolder.py`), zeroes included, so a status with nothing in it still shows |
| **Active** | `Application.objects.filter(status__in=ACTIVE_STATUSES)` count | `ACTIVE_STATUSES = ["applied", "interviewing"]` — submitted and still in play; `reviewing` (a placeholder, not yet applied) deliberately excluded |
| **Activity** | `_activity_weeks()` | Weekly counts of three event types — `added` (`Application.date`), `applied` and `rejected` (from `ApplicationStatusChange`) — bucketed by ISO week (Monday-starting), empty weeks kept so the range stays continuous. The CLI report only prints the last 8 weeks and skips all-zero weeks; the web chart renders every week since the first event, as stacked bars |
| **Recently logged** | `Application.objects.order_by("-date")[:6]` | Most recently *dated* applications, not most recently *edited* |
| **Recently applied** | `_recently_applied()` | Most recent `ApplicationStatusChange` row with `to_status="applied"`, deduped per application (a re-applied role only shows its latest transition) |
| **Recently added companies** | `_recent_companies()` | Last 10 by `Company.date_added`, with each one's application count. Companies that predate the `date_added` field (added before 2026-09-15, backfilled to 2026-08-01) sort behind anything with a real date |
| **Latest portal scans** | `_recent_scans()` | Last 3 `Scan` rows (already `-date`-ordered by `Meta.ordering`), each annotated with `parsers.scan_summary_stats()` — companies scanned, roles found, scored matches, and the strong/other split for reports from 2026-09-14 onward (see [portal-scan-and-scoring.md](portal-scan-and-scoring.md)) |

## Relative dates

Both surfaces render dates the same way — `tracker.templatetags.jobs_extras.ago()`
("today" / "N days/weeks/months/years ago"). The CLI report imports this function
directly rather than reimplementing it, specifically so a formatting change in one
place can't silently diverge from the other.
