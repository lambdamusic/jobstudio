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

## Changing a company afterwards

```bash
tools/py src/jobsdb.py update-company <num|exact name|unique prefix> \
  [--role-target "..."] [--fit {1-5}] [--category "..."] [--url "..."] [--notes "..."]
```

Only the flags given are touched. An empty string **clears** the field, so `--url ""`
removes a careers URL that has gone stale — which is what this exists for: a tracked URL
that 404s or redirects to an acquirer is a company the scanner can no longer reach, and
there was no way to correct one outside the Django admin until 2026-10-01 (`#41`).

Two deliberate refusals. An unknown `--category` is rejected by the same resolver
`add-company` uses, rather than writing the company without one. And a name prefix
matching more than one company is rejected rather than resolved to the lowest `num` — the
opposite of `find_application`, because a read can afford that guess and an update cannot.

**No `--name`.** The slug derives from the name, and the company page URL plus the
`company_overrides`, `company_areas` and `known_unsupported` keys in
`<DATA>/jobs/scan-config.yaml` are all keyed on name or slug. Renaming is a separate job
that has to update those too, or scan coverage for that company breaks silently.

## Status is derived, never set by hand

A company has exactly three states, maintained by `refresh_company_status()` off
`Application` save/delete signals (`src/web/apps/tracker/models.py`):

| State | When |
|---|---|
| `applied` | any application reached `applied`, `interviewing` or `rejected` — i.e. was actually submitted, whatever happened next |
| `reviewing` | nothing submitted, but at least one application is still live (`saved` or `reviewing`) |
| `watching` | nothing live at all |

It was two states (`applied` / `watching`) until 2026-09-28. The middle one was missing,
and its absence read as "not acted on" for a company with an application open on the desk.

`watching` covers two different histories — never applied to, and every application ended
without being sent (`closed`, the deadline passed; `discarded`, the role was dropped).
They mean the same thing about *now*, which is what this field is for; `/stats/` states
the split where the difference matters.

There's still no `researching`/`contacted` granularity at the company level — that richer
per-application status lives on the `Application` row instead (see workflow.md
"Application statuses").

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

## In one paragraph    (what it sells, to whom)
## The business at a glance   (Mermaid diagram — when the research supports one)
## Mission
## Technology          (or: Products — what each answers, and who pays for it)
## Glossary            (optional — when the domain is unfamiliar)
## Videos and demos    (optional — official demos, with lengths)
## Where they are now
## Fit with my mission
## Sources
```

**Company-level material only.** The file describes the company as it would read to
anyone considering *any* role there: what it sells, to whom, where it is heading, and
how it fits the user's mission. Anything about one particular role or its interview
process — the posting's band and office days, who the hiring manager is, what to say
in a round, questions to ask, prep to do — belongs in that application's `notes.md`
(or its round files), never here. A company can carry several applications over
time; the research file must stay true for all of them.

Explain the product in plain terms before analysing it: for each product, the question
it answers, who pays for it, and the decision it unblocks — backed by the company's own
case studies where they exist.

**Glossary terms link themselves.** In any document with a `## Glossary` section whose
entries open with a bold label (`- **EHR (Electronic Health Record).** …`), a term
written ***in bold italic*** elsewhere becomes an in-page link to its entry, styled with
a dotted underline to set it apart from outbound links, and shows the definition as a
tooltip on hover or focus (`parsers.link_glossary`). Plurals,
abbreviations and the first words of a longer label all match; a term that matches
nothing stays plain bold italic. Works on every page that renders through the shared
section index, not only company pages.

**Diagrams are Mermaid.** A fenced ```` ```mermaid ```` block in any rendered markdown
file is drawn by `static/js/diagrams.js`, which fetches the vendored Mermaid only on pages
that have one (`static/vendor/README.md`). The same source renders on GitHub and in editor
previews. Prefer `flowchart TB`: a left-to-right chart of more than two columns gets
shrunk to fit the text column and its labels become unreadable.

**Every company page gets a business diagram when there is enough to draw.** The
`## The business at a glance` section is a `flowchart TB` in three layers — what goes in,
the company's products, who pays for which decision — followed by one sentence reading it.
It is skipped, not improvised, when the research is too thin: a box the sources don't
support is worse than no diagram.

**An application's documents use their company's glossary.** Notes, interview rounds and
Other files rarely carry a glossary of their own, so a marked term there resolves against
the company page's `## Glossary` (`Company.glossary`) and links across to it, tooltip
included. A document with its own `## Glossary` uses that instead. The `company`,
`application` and `interview` subcommands all say to keep a glossary for unfamiliar
sectors — definitions written once, on the company page.

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
