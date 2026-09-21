# How the portal scan and its scoring work

Part of the **[docs/](README.md)** guide collection. For *when* to run the scan, see
[workflow.md](workflow.md) — this is a deep dive into what `/jobstudio scan` /
`src/scan-portals.py` actually does, step by step.

Revised 2026-09-17: scoring is now a separate step from fetching, with two
interchangeable paths — see `backlog/done/drop-direct-anthropic-api-plan.md` §2.

```bash
python src/scan-portals.py                                              # 1. fetch + pre-filter (mechanical, no API)
# then either:
#   default — the `scan` skill subcommand scores live, agent-native, no API call
# or:
source tools/env.sh && python src/score-candidates.py --candidates jobs/scans/YYYY-MM-DD-candidates.json   # opt-in API scoring
python src/scan_report.py --scored jobs/scans/YYYY-MM-DD-scored.json    # 3. render (mechanical, no API; skip if --api already did it)
```

`tools/env.sh` injects `ANTHROPIC_API_KEY` only for the opt-in `score-candidates.py`
path — the default path needs no API key at all. Nothing from a scan is ever
auto-written into the tracker — it only produces a report for you to review and act
on manually via `/jobstudio company` / `/jobstudio application`.

**Why two scoring paths instead of one:** agent-native scoring (the default) spends
Claude Code session/rate-limit budget rather than API dollars — fine at today's scale
(~20 candidates/run), but worth having a per-token-billed alternative as scan volume
grows, or when session budget is tight, or for a fully headless/cron-able run
(`scan-portals.py` → `score-candidates.py` chained needs no interactive session at
all). Both paths score against the exact same rubric
(`src/prompts/scan_score_rubric.md`) so methodology can't drift between them, and
both produce output in the same shape that `scan_report.py` renders identically.

---

## 1. Fetch (mechanical — no LLM)

For every tracked company with a recognized ATS — Greenhouse, Lever, Workable, Workday,
Ashby, SmartRecruiters, Teamtailor, Rippling ATS, plus a generic fetcher for companies
whose own frontend calls a first-party JSON endpoint — every open posting is pulled via
that platform's public API.

When a company's tracked careers URL is a generic corporate page hiding one of these
underneath, `company_overrides` in `<DATA>/jobs/scan-config.yaml` maps it to the real
board/tenant. That file holds everything company-specific about scanning — the overrides,
the category → area mapping, and the reasons a company isn't scanned — because those are
facts about *your* search rather than about how scanning works. It is optional: without
it the scanner still runs on URL detection alone. See `src/scan_config.py`.

Companies with no recognized ATS (a bespoke career page, or a platform not yet
integrated) land in the report's **Not scanned** section with a reason, not silently
dropped.

## 2. Category → area mapping, then dedup + keyword pre-filter (mechanical — still no LLM)

A company's tracked **category** (an industry grouping, e.g. "Fintech") and a
CV **target area** (e.g. `data-platform`) are orthogonal — a category doesn't need its
own bespoke area to be scored. Every category maps to whichever of the 5 existing areas
fits it best (`category_to_area` in `<DATA>/jobs/scan-config.yaml`); any category not
listed there falls back to that file's `default_area` as a safety net. This means **every company always
gets a real area now** — there's no "no target profile for this category" case left
(decided 2026-09-14; before this, 4 of 8 categories had no mapping at all, and those
companies' postings never reached the scorer).

With the area resolved:

- `is_plausible_match(title, role_target, key_terms)` checks whether the posting title
  shares **any word** with the company's tracked `role_target` or the assigned area's
  `key_terms` list (e.g. data-platform's key terms include "data-as-a-product",
  "BigQuery", "data mesh"...).
- No overlap → dropped before ever reaching the model. Grouped by company
  (alphabetical) in **Filtered out before scoring**, full per-posting list under each —
  a high count there is worth a manual look, since it usually means real postings
  exist, just not ones the crude keyword filter caught; the full list is right there to
  check directly.

A posting that survives the keyword filter hits a **second, free pre-filter — location**
(`excluded_by_location_prefilter()`), added 2026-09-14 after a live run showed 417
candidates queued for scoring, most of them clearly not UK/remote-eligible just from
their raw location string. Deliberately conservative, same direction as the keyword
filter: excludes only when the location text has **no** UK/remote-adjacent keyword
anywhere in it at all (no UK country/city name, no "remote") — vague or missing
location text is never excluded, always sent through to real scoring. Excluded
postings are grouped by company (alphabetical) in **Excluded by location**, full
per-posting list under each with the raw location text shown too (the actual reason
it was excluded) — same treatment as Filtered out before scoring. This one filter cut
that run's scoring volume from 417 candidates to 62 (~85%) — mostly large
multi-region postings ("4 Locations", "JAPAN-Tokyo-...") that never happened to
mention the UK or "remote" anywhere.

## 3. Scoring — the judgement step

Only postings that survive step 2 reach here — as a separate step from fetching now,
reading `jobs/scans/YYYY-MM-DD-candidates.json` rather than being wired directly into
the fetch script. Two interchangeable paths, both applying the same rubric
(`src/prompts/scan_score_rubric.md` — the canonical source, read directly by the
agent path and `.format()`-ted by the API path):

- **Default — agent-native, no API call.** The `scan` skill subcommand reads the
  candidates file and the rubric directly and scores live, writing a
  `*-scored.json` file with the same shape plus four filled-in fields per candidate.
- **Opt-in — `score-candidates.py --candidates <path>`.** Batched by area, in chunks
  of 20 (`SCORING_CHUNK_SIZE`, to keep each response well under the token limit), one
  `claude-sonnet-4-6` API call per chunk (`score_candidates()`). Needs
  `ANTHROPIC_API_KEY` (`source tools/env.sh` first).

Either way, each candidate is scored on **three independent dimensions**:

- **Area Score (1–5)** — purely role/domain/seniority match against the assigned area's
  target YAML: its `description`, `emphasis` bullets, and `key_terms`. Location is
  explicitly ignored here. (Internally this is still the `cv_score` field in the code
  and the JSON the model returns — only the report-facing label changed.)
- **Ideal-Job fit (1–5)** — the *nature* of the work (hands-on vs. management,
  customer-facing vs. backstage, autonomy, etc.), judged from title/role_target alone —
  the scorer never sees the full job description at this stage. Fed by two sources:
  - `jobs/notes/ideal-job-notes.md` — free-text notes on what makes a job satisfying.
  - `jobs/profile/criteria.yaml` — the API path formats it via `load_criteria_block()`
    (now in `score-candidates.py`); the agent path reads the YAML directly and applies
    the same rules, spelled out in `scan_score_rubric.md`:
    - **Dealbreakers** (`hard_filters.exclude`) — pull the score down hard (1–2), and
      the note must say so if a role clearly looks like one.
    - **Salary floor** (`hard_filters.salary_floor_gbp`) — flags a stated range that
      tops out below it.
    - **Leap sectors** (`preferences.sectors_open_to_with_a_leap`) — don't penalise an
      unfamiliar domain if it's one of these.
    - **Sectors to avoid** (`preferences.avoid_sectors`) — a soft negative, not an
      auto-fail.
    - **Weighted motivators** — pull the score up, proportional to weight (1–5).
    - **Culture traits** and **personal values** — soft nudges based on what the
      scorer knows or can infer about the company's reputation, not the JD text
      itself (e.g. a large, politically complex organisation gets nudged down even
      without an explicit dealbreaker match).
    - **Bonus signals** — nudge the score up if clearly hit (e.g. work touching Asia,
      e-learning, music tech, a real open-source footprint).
- **Location** (categorical: `uk` / `remote` / `other`) — its own field, not blended
  into either 1–5 score. `remote` means genuinely globally remote, not restricted to a
  non-UK region.

Either path ends up with the same four fields per candidate (`cv_score`, `ideal_score`,
`location_category`, `notes`) — the API path as one compact JSON object per candidate
in the model's response, the agent path written directly onto each candidate object.
`notes` is where the reasoning goes, e.g. naming a dealbreaker or bonus signal spotted.

## 4. Bucketing the results

Area Score + Ideal-Job Score, summed, against `STRONG_THRESHOLD` (currently 7), decides
strength; `location_category` decides eligibility. Four outcomes:

- **`uk`/`remote` and combined ≥7** → **Strong matches** — the main thing to read.
- **`uk`/`remote` and combined <7** → **Other matches** — still fully listed, just not
  competing for attention with the strong ones.
- **`other` and combined ≥7** → **Strong matches — wrong location**, a second table
  nested inside the Strong matches section. Excluded from the main tables since it's
  not eligible today, but kept visible rather than silently discarded — a role this
  strong is worth knowing existed.
- **`other` and combined <7** → discarded silently, only counted (Coverage notes'
  Summary block: "Discarded (non-UK/non-remote), weak fit").

JSON response fails to parse → **Needs manual review** (rare — the section is dropped
from the report entirely when empty).

Both match tables are grouped by company (alphabetical), sorted by combined score
within each — **Category** and **Area** are shown once per company heading rather than
repeated on every row, since they're company-level and never vary within one
company's group. Worth knowing they're shown at all: since the two are now
orthogonal, the area a posting was scored against no longer tells you the company's
actual category (a fintech company can easily be
scored via `data-platform`) — the heading spells out both.

## 5. Everything else in the report is bookkeeping, not scoring

**Not scanned**, **No open roles found**, and **Coverage notes** (e.g. the largest multinational boards
truncated at 200 postings — `MAX_RESULTS_PER_COMPANY`) are all mechanical, no model
involved. Coverage notes also carries the run's summary stats (companies scanned, roles
found, discarded counts, etc.) — moved there from a standalone Summary section on
2026-09-14, since it's bookkeeping about the scan, not something to read before Strong
matches.

---

## Reading the report

The report lands at `jobs/scans/YYYY-MM-DD-portal-scan.md` and is browsable at
`/scans/` (defaults to the latest report; `/scans/all/` lists every one, oldest report
still reachable at `/scans/<slug>/`). The page splits the report into tabs — **Strong
matches** (first, default-active), **Other matches**, Filtered out before scoring,
Excluded by location, Not scanned, Coverage notes.

Reports from before 2026-09-14 have a different shape (Summary and Matches as their own
sections, Matches grouped by area rather than Strong/Other, and an Unscored section for
categories that had no area mapping yet) — still fully browsable, the web page just
renders whatever sections a given report actually contains.

## The important boundary

Nothing is ever auto-written to the tracker. The scan is purely advisory — a match,
however high-scoring, only becomes an application when you (or Claude, on request) run
`/jobstudio application` against it.
