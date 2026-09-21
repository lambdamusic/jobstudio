# jobstudio status

A terminal mirror of the web dashboard (`/` in the Django app) — what's happened
recently across applications, companies, and portal scans.

## Run it

```
tools/py src/jobsdb.py status
```

Print the output verbatim — this command's report is already formatted for reading,
not raw data to reformat. `--json` returns the same data unformatted, if it's ever
needed for something else.

## Where the data comes from

`jobsdb.py::dashboard_summary()` queries the same Django models through the same
helper functions the dashboard view itself uses (`tracker.views._status_summary`,
`_activity_weeks`, `_recently_applied`, `_recent_companies`, `_recent_scans`) — so this
report can never drift out of sync with what `/` shows. See
**`docs/dashboard-status.md`** for the full breakdown of each section.

Do not hand-roll counts by reading `jobs/` files directly — that was the old approach
(pre-Django, when `applications.md`/`companies.md` were the source of truth) and is why
this subcommand went stale before. The database is the only source of truth now.
