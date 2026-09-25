# jobstudio company

The user wants to track a company they're interested in. Extract the details,
place it in the right category section of the tracker database, and confirm.

## The companies file

Path: the tracker database (relative to project root
`<DATA>`)

Structure: a series of `## Category` sections, each containing a markdown table
with columns: `Company | Role target | Fit | Status | Notes`

**Categories come from the user's own tracker, not from this file.** List what already
exists and reuse one:

```bash
tools/py src/jobsdb.py categories
```

Add a new category only if nothing fits — a category is a grouping of companies by
industry or domain, broad enough that several companies share it. Keep the set small;
one category per company defeats the purpose.

Create one with:

```bash
tools/py src/jobsdb.py add-category --name "Research Infrastructure" --order 1
```

Idempotent, and it is the only way in outside the Django admin. `add-company` **refuses**
a category that does not exist rather than writing the company without one, so this comes
first.

If the tracker is empty (a brand-new data root), propose two or three categories that
suit the kinds of company the user is targeting and confirm them before adding the first
company. For a cold start with no companies at all, `subcommands/init.md` §"Seed the
tracker" is the fuller version of this — ask for direction, research a starting set,
confirm, then add them in one pass.

## Fields to extract

| Field | Notes |
|---|---|
| **Company** | Always format as `[Company](url)`. Use the company's jobs/careers page URL (e.g. `company.com/careers`) as the link target — this is more useful than the homepage. If the user provides a URL, use that; if not, infer the careers page from the company name. Check it resolves to a board `scan` can read before writing it: `tools/py src/scan_sources.py "<name>" "<url>"` (offline, no fetch). On `NOT scanned`, see init.md §"Seed the tracker" step 4 — a corporate page often hides a real ATS, which belongs in `company_overrides` rather than in this field. |
| **Role target** | The kind of role the user would target there — infer from context or company type (VP/Director/Head of Data, PM, Solutions Engineer, etc.) |
| **Fit** | Star rating ★☆☆☆☆ to ★★★★★ — how well the company matches this user's background and criteria. Read `<DATA>/jobs/profile/stocktake.md` and `<DATA>/jobs/profile/criteria.yaml` rather than assuming a domain. Default to ★★★☆☆ if unclear |
| **Status** | One of: `watching` · `researching` · `contacted` · `applied` · `interviewing` · `closed` · `rejected`. Default to `watching` |
| **Notes** | One-line summary: what the company does, any relevant signal (e.g. tech stack, team size, culture) |

## Steps

1. **Read** the tracker database to see the current categories and entries.

2. **Extract fields** from the user's text.

3. **Show a brief summary** — one line per field — and ask for confirmation or corrections before writing. Keep it short.

4. **Insert a new row** at the bottom of the appropriate category table. Determine the next `#` by finding the highest number currently in the file and incrementing by 1:
   ```
   | {#} | {Company or [Company](url)} | {Role target} | {Fit} | {Status} | {Notes} |
   ```
   If no category fits, append a new `## Category Name` section with a fresh table at the end of the file (before adding the row).

5. **Confirm** with one line: "Added: {Company} → {Category}."

## Notes on judgement

- **The user's background and preferences** come from `<DATA>/jobs/profile/stocktake.md`
  (§2 achievements, §6 positioning) and `<DATA>/jobs/profile/criteria.yaml`
  (`preferences.sectors`, `bonus_signals`, `hard_filters`). Lean Fit ratings up when the
  company sits in a preferred sector, down when it is outside them with no bridge.
  Read those files — do not assume a domain from the toolkit's own history.
- Always link the company name to their jobs/careers page, not the homepage. If the user gives a specific job posting URL, note it in the Notes field and link the company name to the careers page instead.
- Don't reformat or reorder existing rows — append only.


---

## Writing the row

Companies live in the tracker database. Create one with:

```
tools/py src/jobsdb.py add-company \
  --name "{Name}" \
  --url "{Careers URL}" \
  --role-target "{Role target}" \
  --fit {1-5} \
  --category "{One of the existing category names}" \
  --notes "{One line — the deep research goes in <DATA>/jobs/companies/<slug>.md}"
```

Status is not set by hand: a company is `watching` until it has an application, then
`applied`, maintained automatically.

For substantial background research, add `<DATA>/jobs/companies/<slug>.md` following the template
in `<DATA>/jobs/companies/README.md` — it renders on the company page.
