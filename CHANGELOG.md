# Changelog

Dated entries, newest first.

## 2026-09-23

- **The sidebar has icons, and a link to the repo** — each top-level section carries a
  line glyph that picks up the active item's colour; sub-items stay text-only so the
  indent still reads as hierarchy. The footer links to the GitHub repo, on the published
  site as well as locally.

- **The app is called Job Studio** — the sidebar, the dashboard heading, every browser
  tab and the admin header said "Job search". The name now lives in one place
  (`settings.APP_NAME`), and the sidebar carries a logo of its own — a briefcase glyph
  and the two-tone wordmark as one lockup. The package, repo and command stay
  `jobstudio`.
- **Scan coverage on the companies list** — a new column says whether `scan` picks each
  company up automatically and on which ATS, or the specific reason it doesn't, with a
  count at the top of the page.

- **Any status can be set from the application page** — the page offered one hardcoded
  action, "Mark reviewing"; every other transition meant a trip to the Django admin. A
  "Set status" menu now lists all seven statuses (bar the current one), logging the
  change to the History tab the same way an admin edit does.

- **Every tailored CV is listed on `/cvs/`** — the page showed only the two master CVs,
  so a CV written for a role was invisible unless you knew which application folder it
  was in. It now also lists all tailored CVs, newest first, each naming the application
  it belongs to and linking through to that application's CV tab.

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
