# Changelog

Dated entries, newest first.

## 2026-09-21

Initial public release.

`jobstudio` is an agent-native job-search toolkit: track companies, log applications,
tailor a CV per role, draft cover letters, run gap analysis, and scan ATS job boards for
new postings — driven end to end from a Claude Code session, with a local Django app for
browsing.

It grew out of one person's job search over several months, then had that person's data
separated from it so anyone could run it. Code and data are two directories: this repo is
the toolkit, and your job search lives in a data root you choose, outside it.

- **Nine ATS integrations** — Greenhouse, Lever, Workable, Workday, Ashby,
  SmartRecruiters, Teamtailor, Rippling, plus a generic first-party-JSON fetcher —
  with two-dimension scoring and a location filter.
- **Two base CVs** (functional and chronological), tailored per application on demand
  rather than kept as a variant library.
- **A local Django app** for browsing applications, companies, CVs and scan reports,
  with an optional static-site export.
- **`/jobstudio init`** sets up a data root from scratch, from an existing CV, or from a
  complete fictional example job search so there is something to look at first.
- **No API key needed.** Every default workflow runs inside your Claude Code session;
  one opt-in path (`scan --api`) wants an Anthropic key for headless scoring.
