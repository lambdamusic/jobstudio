# Help

Guides on how to use this job search framework — two kinds:

- **[workflow.md](workflow.md)** — the typical daily/weekly cadence: what to run, in
  what order, across a working session. Start here.
- **Deep-dive guides**, one per piece of functionality, for how something actually
  works internally rather than just how to invoke it:
  - **[portal-scan-and-scoring.md](portal-scan-and-scoring.md)** — how
    `/jobstudio scan` fetches, pre-filters, and scores postings, and how to read the
    report.
  - **[applications-and-gap-analysis.md](applications-and-gap-analysis.md)** — how
    `/jobstudio application` logs a role, sets up its folder, and generates the gap
    analysis + fit summary.
  - **[companies.md](companies.md)** — how `/jobstudio company` tracks a company,
    what its derived status means, and the research-file template.
  - **[cv-pipeline.md](cv-pipeline.md)** — how the base CVs turn into per-area
    variants and per-application tailored copies, and how each export format is built.
  - **[cover-letters.md](cover-letters.md)** — how `/jobstudio cover-letter` picks a
    structure and what it reads to draft one.
  - **[publishing.md](publishing.md)** — how `/jobstudio publish` rebuilds and
    deploys the site.
  - **[career-stocktake-profile.md](career-stocktake-profile.md)** — what
    `/jobstudio stocktake` builds, and where the profile it produces gets used
    elsewhere in the pipeline.
  - **[dashboard-status.md](dashboard-status.md)** — what the web dashboard shows,
    and how `/jobstudio status` mirrors it in the terminal from the same queries.
  - **[interview-prep.md](interview-prep.md)** — how `/jobstudio interview` turns a
    job description and the career profile into likely questions and drafted
    answers, and how the reusable answer bank works.

More guides get added here as pieces of the framework are worth explaining in depth.
`workflow.md` links out to the relevant deep-dive wherever one exists.

Architectural/design history for the pieces this docs/ set doesn't cover yet still
lives in `log/*.md` (dated, append-only session records) and `src/web/README.md` (the
Django app internals) — those are written for someone extending the code, not using
it day to day.
