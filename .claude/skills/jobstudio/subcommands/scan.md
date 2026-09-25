# jobstudio scan

Rescan tracked companies (the tracker database) for new open roles via public ATS
APIs (Greenhouse, Lever, Workable, Workday, Ashby, SmartRecruiters, Teamtailor,
Rippling ATS) plus a generic first-party-JSON fetcher, score matches on
two independent dimensions — Area Score, fit against a target-area profile
(`<DATA>/jobs/targets/*.yaml`) — and personal "ideal job" fit (`<DATA>/jobs/notes/ideal-job-notes.md`
plus the structured `<DATA>/jobs/profile/criteria.yaml` — dealbreakers, weighted motivators,
bonus signals, salary floor) — and produce a report for manual review. Every company
always gets scored against some area (see "Category → area mapping" below); roles that
aren't UK-based or fully remote are excluded from the main Matches tables (only
counted), unless the match is strong enough to surface anyway (see "Strong matches —
wrong location" below).

Nothing is auto-written into the tracker — this only
surfaces candidates. Use the existing `company` / `application` subcommands to
promote anything worth pursuing.

> Revised 2026-09-17: scoring is split into two independent paths — see
> `backlog/done/drop-direct-anthropic-api-plan.md` §2. **Default: agent-native, no API
> call** — you (the agent) score live, since you already have full context. **Opt-in:
> `--api`** — runs the old API-based scoring as a separate script, for when scoring
> volume is high or session budget is tight (agent-native scoring spends Claude Code
> session/rate-limit budget; the API path bills separately per token instead), or for
> a fully headless/cron-able run. Both paths score against the exact same rubric
> (`src/prompts/scan_score_rubric.md`) and produce the same report format
> (`src/scan_report.py`) — pick whichever fits the moment, the output is equivalent.

## Steps

0. **Check the configuration resolves** — only worth doing when something looks off, or
   on a data root that has not been scanned before:

   ```bash
   tools/py src/scan_config.py --check
   ```

   Every problem it reports is one the scan itself swallows: no target areas at all, a
   `category_to_area` entry or `default_area` naming a file that does not exist, a
   tracked category resolving to no area. In each case `profiles.get(area, {})` returns
   an empty profile and scoring proceeds against nothing — the report still fills with
   Area Scores, and they mean nothing. `subcommands/init.md` §"Define the target areas"
   is how to fix an empty `jobs/targets/`.

1. **Fetch and pre-filter (mechanical, no API call, both paths)**:
   ```bash
   tools/py src/scan-portals.py
   ```
   Writes `<DATA>/jobs/scans/YYYY-MM-DD-candidates.json` — the plausible (unscored)
   candidates plus every already-computed bookkeeping section (not-scanned, no-roles,
   filtered-out, excluded-by-location, coverage notes). Prints the path.

2. **Score the candidates** — pick one:

   **Default — score live, no API call.** Read `<DATA>/jobs/scans/YYYY-MM-DD-candidates.json`
   and `src/prompts/scan_score_rubric.md` (the canonical rubric — read it directly, it's
   written to be followed as-is, not paraphrased). For each `{placeholder}` in the
   rubric, substitute the real content:
   - `{area_name}` / `{description}` / `{emphasis}` / `{key_terms}` — the matching
     fields from that candidate's `<DATA>/jobs/targets/<area>.yaml`
   - `{ideal_job_notes}` — the full contents of `<DATA>/jobs/notes/ideal-job-notes.md`
   - `{criteria_block}` — read `<DATA>/jobs/profile/criteria.yaml` and apply it per the
     rubric file's own field-by-field breakdown (dealbreakers, salary floor, leap
     sectors, sectors to avoid, weighted motivators, culture/values, bonus signals)
   - `{postings}` — the candidates you're scoring (batch by area, or all at once —
     your context budget, not a hard chunk size like the API path needs)

   For every candidate, fill in `cv_score`, `ideal_score`, `location_category`, and
   `notes` directly on its object (same four fields the rubric's JSON shape
   describes). Write the whole updated structure — context sections unchanged,
   candidates now scored — to `<DATA>/jobs/scans/YYYY-MM-DD-scored.json`.

   **Opt-in — `--api`:**
   ```bash
   source tools/env.sh && tools/py src/score-candidates.py --candidates <DATA>/jobs/scans/YYYY-MM-DD-candidates.json
   ```
   `tools/env.sh` sets `ANTHROPIC_API_KEY` for this command only. Scores via the API
   (chunked, same rubric file), writes the same `*-scored.json` shape, and — unlike
   the default path — renders the final report itself in the same run (step 3 below
   is already done when this finishes; skip straight to step 4).

3. **Render the report (mechanical, no API call, default path only — `--api` already did this)**:
   ```bash
   tools/py src/scan_report.py --scored <DATA>/jobs/scans/YYYY-MM-DD-scored.json
   ```
   Classifies each scored candidate (matches / discarded-by-location / needs-review),
   assembles the Strong/Other match tables, and writes
   `<DATA>/jobs/scans/YYYY-MM-DD-portal-scan.md` — refreshing the web app's `/scans/` data
   along the way.

4. **Read the generated report** at `<DATA>/jobs/scans/YYYY-MM-DD-portal-scan.md`.

5. **Summarize it back to the user**:
   - **Strong matches** (Area Score + Ideal-Job Score ≥ 7) — company, title, both scores, and the notes. This is the section to actually read in full.
   - **Strong matches — wrong location** — same bar, but not UK/remote-eligible; worth a mention, not necessarily action.
   - A skim of **Other matches** for anything that stands out despite a lower score.
   - The **discarded (non-UK/non-remote), weak fit** count from Coverage notes — these were never shown individually, just tallied (the strong ones *are* shown, in the section above).
   - Count and list of companies **not scanned**, with the specific reason (bespoke page, unintegrated ATS, fetch error) — be explicit these need manual checking if the user wants them covered
   - Anything flagged "needs manual review" (scoring failed, or a candidate the live scoring pass didn't get to)
   - Any **coverage notes** (the largest Workday and SmartRecruiters boards are capped and not exhaustive)
   - If a company the user cares about shows 0 results everywhere, check the **"Filtered out before scoring"** section before concluding it has no roles — a high count there means postings existed but none matched the crude keyword pre-filter

6. **Offer next actions** for any strong match: "Want me to log this via `/jobstudio company` or `/jobstudio application`?"

## Notes

- **Matches are grouped by company** (alphabetical), sorted by combined score within each — **Strong matches** (Area Score + Ideal-Job Score ≥ 7, `STRONG_THRESHOLD` in `scan_report.py`) and **Other matches** (everything else scored). Each company heading shows its Category → Area once (they're company-level, never vary within one company's group); the table under it is Role | Location | Area Score | Ideal-Job Score | Notes. Area Score is fit against the target-area profile assigned to the posting (skills/domain/seniority); Ideal-Job Score is fit against `<DATA>/jobs/notes/ideal-job-notes.md` and `<DATA>/jobs/profile/criteria.yaml` — the *nature* of the work (hands-on building vs pure management, customer-facing/evangelist-type roles vs backstage, ownership/autonomy, etc.), not skills. The scorer is told to push Ideal-Job Score down for a suspected dealbreaker and nudge it up for a bonus signal, and to call either out in the Notes cell — so scan the Notes column, not just the numbers.
- **Category → area mapping.** Company categories (an industry grouping, e.g. "Fintech") and target areas (a CV positioning, e.g. `data-platform`) are orthogonal — a company's category doesn't need its own bespoke area to be scored, it's just mapped to whichever existing area fits best (`category_to_area` in `<DATA>/jobs/scan-config.yaml`; that file's `default_area` is the safety-net fallback for any category not yet listed there). This is why Category and Area are separate columns on every row — they no longer imply each other the way "grouped by area, area = category" used to.
- Location is classified into `uk` / `remote` / `other` per posting, by whichever scoring path ran. Only `uk` and `remote` roles appear in the main Matches tables; `other` is excluded from them by default. The exception is **"Strong matches — wrong location"**, nested inside the Strong matches section — a strong match (same ≥7 bar) that's excluded purely by location is kept visible there rather than silently discarded, since it's worth knowing it existed. Anything `other`-location that *isn't* strong stays a silent count only, in Coverage notes' Summary block ("Discarded (non-UK/non-remote), weak fit").
- **Location pre-filter, before scoring.** A second, free pre-filter (`excluded_by_location_prefilter()`) runs alongside the keyword one, before a posting is even queued for scoring — conservatively: excludes only when the location text has *no* UK/remote-adjacent keyword anywhere in it (no country/city/"remote" mention at all); vague or missing location text is never excluded, always sent to scoring. Excluded postings land in **"Excluded by location"**, grouped by company (alphabetical) with the full per-posting list (each posting's raw location text shown too — the actual reason it was excluded), same treatment as "Filtered out before scoring". This cuts real volume — a recent run saw 417 candidates heading to the scorer drop to 62 once this was added, since most large-org multi-location postings never happen to mention the UK or "remote" at all.
- 8 platforms are supported: Greenhouse, Lever, Workable, Workday, Ashby, SmartRecruiters, Teamtailor, Rippling ATS — plus `firstparty_entries`, a generic fetcher for a company whose own frontend calls a first-party JSON endpoint (the URL comes from the override; the parser expects `{"entries": [{title, url, officeTeamLocation}]}`). Many tracked companies' careers URL is a generic corporate careers page that hides one of these underneath — `company_overrides` in `<DATA>/jobs/scan-config.yaml` maps company name → real board/tenant/domain for those cases. If a new company is added and shows up "not scanned" as a bespoke page, it's worth checking whether it's secretly on one of these platforms before assuming it truly has no API.
- **Rippling ATS has no public API** — its fetcher parses the page's Next.js SSR hydration payload (`__NEXT_DATA__`), which is undocumented and could silently break on a frontend redesign (degrades to a normal "not scanned" ScanError if the expected JSON shape disappears, doesn't crash). Only worth doing for a company specifically requested, not as a default.
- A few platforms are confirmed but genuinely not reachable or not yet integrated. Which of *your* tracked companies sit on them is recorded per company in `known_unsupported` in `<DATA>/jobs/scan-config.yaml`, so the report gives a precise reason instead of the generic bespoke-page fallback:
  - **Dayforce/Ceridian** — its jobs API is Cloudflare-protected (needs a real browser render + CSRF token + session cookies, not a plain HTTP request). Deliberately not built — that would cross into anti-bot-evasion territory rather than a normal public API integration.
  - **BambooHR, SuccessFactors, UKG/Ultipro** — platform identified but no fetcher built yet (low priority unless requested).
  - **Webitrent** (UK public-sector ATS) — no public API found.
  - A company may also simply not be hiring, or have an unconfirmed board token; both are worth rechecking periodically.
- Workday and SmartRecruiters both apply a server-side keyword filter (derived from the company's tracked role target) and then paginate through all matching results, up to a 200-per-company safety cap (`MAX_RESULTS_PER_COMPANY`). Only companies whose keyword-filtered total still exceeds 200 hit the cap — in practice the very largest multinationals — so check the report's "Coverage notes" section for these.
- LinkedIn is out of scope entirely — not attempted, not reported as "not scanned" (it isn't a tracked company career page).
- Postings that get fetched and pass dedup, but fail the local title/role-target word-overlap pre-filter, are tracked in a **"Filtered out before scoring"** section — grouped by company (alphabetical), full per-posting list under each so any of them can be manually followed up on. This is what surfaces a company that fetches plenty of postings but whose titles don't share a keyword with the tracked role target — previously these vanished with zero visibility.

## User arguments

- `--area <slug>` on step 1 (`scan-portals.py`) limits the whole run to one target area
- `--dry-run` on step 1 prints fetch/dedup/pre-filter stats and writes nothing —
  useful for a quick sanity check without generating files to score
- `--api` (mentioned by the user, or invoked when scoring volume looks large or
  session budget is a concern) selects the opt-in API scoring path in step 2
