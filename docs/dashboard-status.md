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
