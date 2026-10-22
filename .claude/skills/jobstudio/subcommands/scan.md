# jobstudio scan

Rescan tracked companies (the tracker database) for new open roles via public ATS
APIs (Greenhouse, Lever, Workable, Workday, Ashby, SmartRecruiters, Teamtailor,
BambooHR, Pinpoint, Recruitee, UKG, Hireserve, Rippling ATS), the feeds behind SuccessFactors and
Radancy career sites, a sitemap fallback and a generic first-party-JSON fetcher, score matches on
two independent dimensions — Area Score, fit against a target-area profile
(`<DATA>/jobs/targets/*.yaml`) — and personal "ideal job" fit (`<DATA>/jobs/notes/search/direction/ideal-job-notes.md`
plus the structured `<DATA>/jobs/profile/criteria.yaml` — dealbreakers, weighted motivators,
bonus signals, salary floor) — and produce a report for manual review. Every company
always gets scored against some area (see "Category → area mapping" below); roles that
aren't UK-based or fully remote are excluded from the main Matches tables (only
counted), unless the match is strong enough to surface anyway (see "Strong matches —
wrong location" below).

Nothing is auto-written into the tracker — this only
surfaces candidates. Use the existing `company` / `application` subcommands to
promote anything worth pursuing.

> Scoring is agent-native, no API call — you (the agent) score live, since you already
> have full context (`backlog/plans/001-drop-direct-anthropic-api.md` §2). The rubric is
> `src/prompts/scan_score_rubric.md`; the report is rendered by `src/scan_report.py`.
> The opt-in `--api` path that scored through the Anthropic API was removed 2026-10-08
> (TODO `#52`).

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

1. **Fetch and pre-filter (mechanical, no API call)**:
   ```bash
   tools/py src/scan-portals.py
   ```
   Writes `<DATA>/jobs/scans/YYYY-MM-DD-candidates.json` — the plausible (unscored)
   candidates plus every already-computed bookkeeping section (not-scanned, no-roles,
   filtered-out, excluded-by-location, coverage notes). Prints the path.

   **Job boards (`#8`).** With a key for Adzuna and/or Reed (`~/.jobstudio.ini`:
   `adzuna_app_id`, `adzuna_app_key`, `reed_api_key`; or the environment; or
   `job_boards` in `scan-config.yaml`) and searches listed in `job_boards.queries`, the
   same run also searches those boards and adds what it finds to the candidates, each
   with a `source`. Without both, nothing is searched and the report is unchanged. See
   `docs/portal-scan-and-scoring.md` §1 for the query format. `--dry-run` prints a `Job boards:` line with the counts — use it
   first after adding keys, since a bad key shows up there as an error per query.

2. **Score the candidates — live, no API call.** Read `<DATA>/jobs/scans/YYYY-MM-DD-candidates.json`
   and `src/prompts/scan_score_rubric.md` (the canonical rubric — read it directly, it's
   written to be followed as-is, not paraphrased). For each `{placeholder}` in the
   rubric, substitute the real content:
   - `{area_name}` / `{description}` / `{emphasis}` / `{key_terms}` / `{excludes}` —
     the matching fields from that candidate's `<DATA>/jobs/targets/<area>.yaml`
     (`excludes` is optional; where an area has none, say so in its place rather than
     leaving the section empty)
   - `{ideal_job_notes}` — the full contents of `<DATA>/jobs/notes/search/direction/ideal-job-notes.md`
   - `{criteria_block}` — read `<DATA>/jobs/profile/criteria.yaml` and apply it per the
     rubric file's own field-by-field breakdown (dealbreakers, salary floor, leap
     sectors, sectors to avoid, weighted motivators, culture/values, bonus signals)
   - `{postings}` — the candidates you're scoring (batch by area, or all at once —
     your context budget decides)

   A candidate with a `source` came from a job board, not a tracked company: it has no
   `role_target`, and its `snippet` and `salary` are what to judge it on (the rubric says
   so). `agency: true` means the company named is a recruitment agency, not the employer.

   For every candidate, fill in `cv_score`, `ideal_score`, `location_category`, and
   `notes` directly on its object (same four fields the rubric's JSON shape
   describes). Write the whole updated structure — context sections unchanged,
   candidates now scored — to `<DATA>/jobs/scans/YYYY-MM-DD-scored.json`.

   **If `criteria.yaml` has no `weighted_motivators`, say so when you hand the report
   over** (TODO `#62`). Still score — a low `ideal_score` with a note saying what could
   not be judged is more useful than a blank — but the number is then about the empty
   profile rather than the role, and the person reading it cannot tell those apart from
   the column. `scan_report.py` puts a banner at the top of the report saying this, so
   you are reinforcing it rather than being its only source; **do not leave it to the
   banner alone**, because the point of failure is a reader who skims to the table.

   Name the consequence for the *ranking*, not just the column: the Strong-matches cut
   is on the combined score, so with one half flat the bar is effectively Area Score
   plus a constant. Then point at `/jobstudio stocktake` as the fix, and say it changes
   the ordering rather than merely filling in a blank — otherwise it reads as optional
   tidying.

3. **Render the report (mechanical, no API call)**:
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
   - **Discovered on job boards**, if the section exists — the strongest few, said plainly
     to be **unvetted**: companies nobody has decided to watch, some advertised through
     agencies. Offer `/jobstudio company` for any employer worth tracking from now on.
   - The **discarded (non-UK/non-remote), weak fit** count from Coverage notes — these were never shown individually, just tallied (the strong ones *are* shown, in the section above).
   - Count and list of companies **not scanned**, with the specific reason (bespoke page, unintegrated ATS, fetch error) — be explicit these need manual checking if the user wants them covered
   - Anything flagged "needs manual review" (scoring failed, or a candidate the live scoring pass didn't get to)
   - Any **coverage notes** (the largest Workday and SmartRecruiters boards are capped and not exhaustive)
   - If a company the user cares about shows 0 results everywhere, check the **"Filtered out before scoring"** section before concluding it has no roles — a high count there means postings existed but none matched the crude keyword pre-filter

6. **Offer next actions** for any strong match: "Want me to log this via `/jobstudio company` or `/jobstudio application`?"

## Notes

- **Matches are grouped by company** (alphabetical), sorted by combined score within each — **Strong matches** (Area Score + Ideal-Job Score ≥ 7, `STRONG_THRESHOLD` in `scan_report.py`) and **Other matches** (everything else scored). Each company heading shows its Category → Area once (they're company-level, never vary within one company's group); the table under it is Role | Location | Area Score | Ideal-Job Score | Notes. Area Score is fit against the target-area profile assigned to the posting (skills/domain/seniority); Ideal-Job Score is fit against `<DATA>/jobs/notes/search/direction/ideal-job-notes.md` and `<DATA>/jobs/profile/criteria.yaml` — the *nature* of the work (hands-on building vs pure management, customer-facing/evangelist-type roles vs backstage, ownership/autonomy, etc.), not skills. The scorer is told to push Ideal-Job Score down for a suspected dealbreaker and nudge it up for a bonus signal, and to call either out in the Notes cell — so scan the Notes column, not just the numbers.
- **Keep `role_target` and `key_terms` to *qualifiers*, not seniority words.** The
  pre-filter splits both into words and passes a posting if its title shares *any* of
  them, so one generic word swamps a large board: on a real run, "Research Engineer" and
  "Member of Technical Staff" in an area's `key_terms` let through 264 of 353 candidates,
  with "engineer" alone accounting for almost an entire frontier lab's board. "Safety
  Systems" was nearly as bad, because it contributes "systems".
  Trimming those to qualifiers — Alignment, Interpretability, Evaluations, Oversight —
  cut the same run to 113 without losing a single role at the small, focused companies,
  where a bare "Research Engineer" *is* the relevant job. The rule that follows: generic
  titles belong in a **company's** `role_target`, where they only ever match that
  company's own board; an **area's** `key_terms` should carry only words that
  discriminate. When a company's board is huge, narrow that company's `role_target` to
  qualifiers too. Nothing is lost silently — every dropped posting is listed per company
  under "Filtered out before scoring".
- **One company, more than one area.** A company whose name appears in `company_areas`
  (`<DATA>/jobs/scan-config.yaml`) is scanned against every area listed there, in
  preference order, instead of the single area its category maps to — for an org that
  genuinely hires into two positionings at once. Each posting is assigned one of those
  areas by title overlap with the area's `key_terms`, so a posting still gets one score;
  in the report that company's table gains an **Area** column and its heading says
  "scored per role" instead of naming one. Its `role_target` should list titles from both
  angles, since that string is also part of the pre-filter. Use it sparingly — for most
  companies the category is the right answer, and `--check` warns on a single-area entry
  that buys nothing.
- **Area exclusions.** `excludes` in a `<DATA>/jobs/targets/<area>.yaml` is that area's
  anti-fit list, and it beats every positive signal on the Area Score: a posting matching
  one is capped at 2 however well the subject, key terms and seniority fit, with the
  reason in the Notes cell. It is aimed at the case the 1–5 scale gets wrong unaided — a
  posting squarely inside the area's subject matter whose actual job is the wrong shape,
  which otherwise scores 4–5 on topic alone and lands at the top of the report. Unlike
  `hard_filters.exclude` in `criteria.yaml` it is per-area, so the same role shape can be
  excluded from one positioning and welcome in another. It changes ranking, never
  visibility: an excluded posting is still fetched, still scored, still listed under
  Other matches — narrowing `key_terms` is what removes a posting from view, and is
  usually the wrong tool for this.
- **Soft negatives.** `soft_negatives` in `<DATA>/jobs/profile/criteria.yaml` is the
  mirror of `bonus_signals`: a reservation that nudges the Ideal-Job Score down a point
  or two and gets named in the Notes cell, rather than a dealbreaker
  (`hard_filters.exclude`) which is scored 1–2. Use it for a trait worth knowing about a
  role but never worth hiding it for.
- **Category → area mapping.** Company categories (an industry grouping, e.g. "Fintech") and target areas (a CV positioning, e.g. `data-platform`) are orthogonal — a company's category doesn't need its own bespoke area to be scored, it's just mapped to whichever existing area fits best (`category_to_area` in `<DATA>/jobs/scan-config.yaml`; that file's `default_area` is the safety-net fallback for any category not yet listed there). This is why Category and Area are separate columns on every row — they no longer imply each other the way "grouped by area, area = category" used to.
- Location is classified into `uk` / `remote` / `other` per posting, by whichever scoring path ran. Only `uk` and `remote` roles appear in the main Matches tables; `other` is excluded from them by default. The exception is **"Strong matches — wrong location"**, nested inside the Strong matches section — a strong match (same ≥7 bar) that's excluded purely by location is kept visible there rather than silently discarded, since it's worth knowing it existed. Anything `other`-location that *isn't* strong stays a silent count only, in Coverage notes' Summary block ("Discarded (non-UK/non-remote), weak fit").
- **Location pre-filter, before scoring.** A second, free pre-filter (`excluded_by_location_prefilter()`) runs alongside the keyword one, before a posting is even queued for scoring — conservatively: excludes only when the location text has *no* UK/remote-adjacent keyword anywhere in it (no country/city/"remote" mention at all); vague or missing location text is never excluded, always sent to scoring. Excluded postings land in **"Excluded by location"**, grouped by company (alphabetical) with the full per-posting list (each posting's raw location text shown too — the actual reason it was excluded), same treatment as "Filtered out before scoring". This cuts real volume — a recent run saw 417 candidates heading to the scorer drop to 62 once this was added, since most large-org multi-location postings never happen to mention the UK or "remote" at all.
- Supported: Greenhouse, Lever, Workable, Workday, Ashby, SmartRecruiters, Teamtailor, BambooHR, Pinpoint, Recruitee, Rippling ATS, UKG, Hireserve, SuccessFactors career sites, Radancy career sites, and a sitemap fallback. **Greenhouse, Lever, Workable, BambooHR, Ashby, SmartRecruiters, Teamtailor, Pinpoint and Recruitee are detected from the tracked URL alone** when the company links straight at its board (`jobs.ashbyhq.com/<token>`, `jobs.lever.co/<token>`, `<token>.pinpointhq.com`, `<token>.recruitee.com` and so on) — no override needed. The rest always need one, because their URL is either on the company's own domain or does not spell the board out:
  - `recruitee: {token}` — only when the board is on the company's own domain (`careers.<company>.com`), which is common. The token is the subdomain of `<token>.recruitee.com/api/offers/`; it is usually the company's name, and the page source names it if not.
  - `workday: {tenant, wd, site}` — from `<tenant>.<wd>.myworkdayjobs.com/<site>`.
  - `rippling: {token}`; `ukg: {tenant, board}` — the two path segments of `recruiting.ultipro.com/<tenant>/JobBoard/<board>/`.
  - `successfactors: {domain, filter?, locale?}` — a SuccessFactors career site on the company's own domain (the RSS feed at `/services/rss/job/`; the older `careerN.successfactors.com` deployment has none). `filter` is matched against each posting's description, for a site that carries several organisations when only one is tracked.
  - `hireserve: {domain, site_id}` — `site_id` is the `p_web_site_id` hidden field in the careers site's search form.
  - `radancy: {domain, locale?}` — a Radancy (TalentBrew) career site: `tbcdn.talentbrew.com` in the page source, `/<locale>/job/...` posting URLs.
  - `sitemap: {sitemap, path}` — the fallback for a site with no feed: posting URLs (those containing `path`) come from the sitemap, and each posting's title and location from its schema.org JobPosting JSON-LD. One request per posting, so capped at 50.
  - `firstparty_entries`, a generic fetcher for a company whose own frontend calls a first-party JSON endpoint (the URL comes from the override; the parser expects `{"entries": [{title, url, officeTeamLocation}]}`). Many tracked companies' careers URL is a generic corporate careers page that hides one of these underneath — `company_overrides` in `<DATA>/jobs/scan-config.yaml` maps company name → real board/tenant/domain for those cases. If a new company is added and shows up "not scanned" as a bespoke page, it's worth checking whether it's secretly on one of these platforms before assuming it truly has no API.
- **Rippling ATS has no public API** — its fetcher parses the page's Next.js SSR hydration payload (`__NEXT_DATA__`), which is undocumented and could silently break on a frontend redesign (degrades to a normal "not scanned" ScanError if the expected JSON shape disappears, doesn't crash). Only worth doing for a company specifically requested, not as a default.
- A few platforms are confirmed but genuinely not reachable or not yet integrated. Which of *your* tracked companies sit on them is recorded per company in `known_unsupported` in `<DATA>/jobs/scan-config.yaml`, so the report gives a precise reason instead of the generic bespoke-page fallback:
  - **Dayforce/Ceridian** — its jobs API is Cloudflare-protected (needs a real browser render + CSRF token + session cookies, not a plain HTTP request). Deliberately not built — that would cross into anti-bot-evasion territory rather than a normal public API integration.
  - **Webitrent** (UK public-sector ATS) — no public API found.
  - A company may also simply not be hiring, or have an unconfirmed board token; both are worth rechecking periodically.
- **"I'm not interested in X any more"** → add it to `excluded_companies` (name → reason) in `<DATA>/jobs/scan-config.yaml`; don't delete the company, which would take its application history with it. It then shows under Not scanned as "excluded from scans", and the job-board search drops it as well.
- Workday and SmartRecruiters both apply a server-side keyword filter (derived from the company's tracked role target) and then paginate through all matching results, up to a 200-per-company safety cap (`MAX_RESULTS_PER_COMPANY`). Only companies whose keyword-filtered total still exceeds 200 hit the cap — in practice the very largest multinationals — so check the report's "Coverage notes" section for these.
- LinkedIn is out of scope entirely — not attempted, not reported as "not scanned" (it isn't a tracked company career page).
- Postings that get fetched and pass dedup, but fail the local title/role-target word-overlap pre-filter, are tracked in a **"Filtered out before scoring"** section — grouped by company (alphabetical), full per-posting list under each so any of them can be manually followed up on. This is what surfaces a company that fetches plenty of postings but whose titles don't share a keyword with the tracked role target — previously these vanished with zero visibility.

## User arguments

- `--area <slug>` on step 1 (`scan-portals.py`) limits the whole run to one target area
- `--dry-run` on step 1 prints fetch/dedup/pre-filter stats and writes nothing —
  useful for a quick sanity check without generating files to score
