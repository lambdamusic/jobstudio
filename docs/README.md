# Help

Guides on how to use this job-search toolkit. They come in **two layers**, because
there are two very different questions people arrive with.

---

## 1. What you can do, and how

You drive this toolkit by talking to a Claude Code session opened in it. Every task has
a command; none of them require reading any Python.

- **[screenshots.md](screenshots.md)** — **start here if you just want to see it.** A
  captioned tour of every page of the web app, shot against the example data. No setup
  required to read it.
- **[getting-started.md](getting-started.md)** — installing it, signing in, the web
  app, the configuration files, and the checks to run if you are changing the code. The
  [README](../README.md#quick-start)'s quick start is the short version; this is
  everything around it.
- **[workflow.md](workflow.md)** — **then here.** The typical daily/weekly cadence:
  what to run, in what order, across a working session. Prepare a CV → scan for
  postings → log and work applications.

The same thing is summarised inside the web app itself, at **`/help/`**, which is
usually closer to hand while you are looking at your search.

## 2. How each piece actually works

One guide per piece of functionality, for when you want to know what something is
doing rather than how to invoke it — how a posting gets scored, what a derived status
means, where a profile gets used downstream.

- **[portal-scan-and-scoring.md](portal-scan-and-scoring.md)** — how `/jobstudio scan`
  fetches, pre-filters, and scores postings, and how to read the report.
- **[applications-and-gap-analysis.md](applications-and-gap-analysis.md)** — how
  `/jobstudio application` logs a role, sets up its folder, and generates the gap
  analysis + fit summary.
- **[companies.md](companies.md)** — how `/jobstudio company` tracks a company, what
  its derived status means, and the research-file template.
- **[cv-pipeline.md](cv-pipeline.md)** — how the base CVs become per-application
  tailored copies, and how each export format is built.
- **[cover-letters.md](cover-letters.md)** — how `/jobstudio cover-letter` picks a
  structure and what it reads to draft one.
- **[career-stocktake-profile.md](career-stocktake-profile.md)** — what
  `/jobstudio stocktake` builds, and where the profile it produces gets used elsewhere.
- **[interview-prep.md](interview-prep.md)** — how `/jobstudio interview` turns a job
  description and the career profile into likely questions and drafted answers, and how
  reusable answers are filed (the answer bank for about-me questions, the notes for subjects).
- **[dashboard-status.md](dashboard-status.md)** — what the web dashboard shows, and
  how `/jobstudio status` mirrors it in the terminal from the same queries.

## Under the hood

- **[under-the-hood.md](under-the-hood.md)** — the Python entry points and shell
  scripts the commands drive, in one place. You never need this to *use* the toolkit.
  It is for running a single step to see what it did, for extending the code, and for
  automating a piece of it where there is no session to talk to.
- **[publishing.md](publishing.md)** — *legacy:* rendering the web app to a static
  `site/` folder with `tools/site-build`. Not part of the normal workflow.

---

Design history for the pieces these guides don't cover lives in `log/*.md` (dated,
append-only session records) and `src/web/README.md` (the Django app internals) — both
written for someone extending the code rather than using it.
