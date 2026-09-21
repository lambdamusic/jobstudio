# How company tracking works

Part of the **[docs/](README.md)** guide collection. For *when* to track a company, see
[workflow.md](workflow.md) §3 — this is a deep dive into what `/jobstudio company`
does, and how a company's status and research file work.

A company gets a tracker row in one of two ways: explicitly, via `/jobstudio company`,
or as a side effect of logging an application against a company that isn't tracked yet
(step 4 of [applications-and-gap-analysis.md](applications-and-gap-analysis.md)) — both
paths do the same thing underneath.

## Fields captured

```bash
tools/py src/jobsdb.py add-company \
  --name "{Name}" --url "{Careers URL}" --role-target "{Role target}" \
  --fit {1-5} --category "{One of the existing category names}" --notes "{One line}"
```

| Field | Notes |
|---|---|
| **name** | The organisation name |
| **url** | The **careers/jobs page**, not the homepage — this is what the portal scan uses to detect which ATS (Greenhouse, Lever, Workday, …) the company runs on. See [portal-scan-and-scoring.md](portal-scan-and-scoring.md) §1 and `company_overrides` in `<DATA>/jobs/scan-config.yaml` if the tracked URL is a generic corporate page hiding the real board underneath. |
| **role-target** | The kind of role the user would target there — VP/Director/Head of Data, PM, Solutions Engineer, etc. |
| **fit** | Star rating, 1–5. Lean up for the kind of company the user most wants to work for, down for a weak domain or culture fit. Default `★★★☆☆` if unclear. |
| **category** | One of the existing category names (`tools/py src/jobsdb.py categories`) — add a new one only if nothing fits. |
| **notes** | A single scannable line. Deep research goes in `jobs/companies/<slug>.md` instead (see below), not here. |
| **date_added** | Set automatically to today by `add-company` — not a CLI flag. Blank for rows that predate this field (added recently; only *new* additions set it). |

## Status is derived, never set by hand

A company has exactly two states — `watching` or `applied` — maintained by
`refresh_company_status()` off `Application` save/delete signals
(`src/web/apps/tracker/models.py`): `applied` the moment the company has any application
that reached `applied`, `interviewing`, or `rejected`; `watching` otherwise. There's no
`researching`/`contacted` granularity at the company level — that richer per-application
status lives on the `Application` row instead (see workflow.md "Application statuses").

## Category vs. target area — two different groupings

**Category** is what a company *is* — your own taxonomy, built up as you track
companies rather than shipped with the toolkit. `tools/py src/jobsdb.py categories`
lists what you have, with a count each. **Area** (your CV target slugs, one per
`jobs/targets/*.yaml` — [cv-pipeline.md](cv-pipeline.md)) is what kind of role/CV
framing to pursue there. These are orthogonal by design: a company categorised by its
industry can perfectly well be scored via a platform-engineering area. The portal scan
bridges the two with a fixed
`category_to_area` mapping in `<DATA>/jobs/scan-config.yaml` (every category maps to an area, with a safety-net
default) — see [portal-scan-and-scoring.md](portal-scan-and-scoring.md) §2.

## The research file

`jobs/companies/<slug>.md` is created **on demand**, following the template in
`jobs/companies/README.md`:

```markdown
# Company Name

## Mission
## Technology
## Where they are now
## Fit with my mission
## Sources
```

`Fit with my mission` is an honest for/against read against
`jobs/profile/stocktake.md`, not a sales pitch — this is what
[cover-letters.md](cover-letters.md) reads to feed the research/hook paragraph with a
real, specific POV on the company's challenge. A company without this file simply
shows no Notes section on its page (`Company.notes_path` in `models.py` — derived from
the slug, not stored, since the location is deterministic).
Match the depth of existing profiles (e.g. `jobs/companies/grafana-labs.md`) — this is
real research, not a one-paragraph stub.

## Where it shows

`/companies/` lists every tracked company by category; `/companies/<slug>/` is the
detail page, rendering the research file's markdown alongside the tracked fields. The
admin's "View on site" button links back from any company's change form.
