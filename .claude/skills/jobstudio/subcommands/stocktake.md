# jobstudio stocktake

> Renamed from `interview` on 2026-09-18 — this command builds the career
> "taking stock" profile, not prep for an actual interview with a company. For
> that, see `/jobstudio interview` (`subcommands/interview.md`).

A guided interview that walks **Step 1 of a structured career-transition process**
("Taking stock and what's next") and writes the answers into a structured profile:

- `<DATA>/jobs/profile/stocktake.md` — the reflective exercises as prose
- `<DATA>/jobs/profile/criteria.yaml` — hard filters, preferences, weighted motivators

Both files are scaffolded already (empty sections marked `_(not started)_` /
empty YAML keys). This command fills them in through conversation.

---

## Principles

- **One section at a time.** Ask, listen, draft, show the draft, get a yes/edit,
  write it. Do not dump all questions at once.
- **Pre-fill, don't interrogate.** Read the sources below first and propose a
  draft answer for each section from what's already known. The user edits or
  confirms — he shouldn't be starting from a blank box.
- **Resumable.** A section that no longer contains `_(not started)_` is done —
  skip it unless the user says "redo section N" or "revisit anchors".
- **Their voice, not yours.** Match how the user writes and talks — this document gets
  read back to them for years, and prose in someone else's register reads as untrue even
  when the facts are right.
  Match `<DATA>/jobs/notes/search/ideal-job-notes.md`.
- **Stop when the user wants to stop.** This is long. It's fine to do two sections and
  resume another day — the files hold state.

---

## Sources to read first (for pre-fill)

| Source | Feeds |
|---|---|
| `<DATA>/jobs/notes/search/ideal-job-notes.md` | section 1 (enjoyed/disliked), section 3 (anchors), motivators |
| `<DATA>/jobs/cv/base/cv_functional.md` | section 2 (skills, achievements) |
| existing `<DATA>/jobs/profile/stocktake.md` | anything already captured — this is a resumable re-fill, not a blank start |
| `<DATA>/extras/career-coach/2026-09-02_career-coach-session-1-notes.md` | any section |
| `<DATA>/extras/career-coach/2026-09-08-my-goals.md` | criteria (hard filters), section 4 |
| `MEMORY.md` entries (location preference, career-coach direction) | criteria |

Rows under `<DATA>/extras/` are **optional private material** — coaching notes, course
handouts, questionnaire exports someone happens to have. Most users will have none of
them. Read them when they exist and ignore them when they don't; never treat a missing
one as an error, and never ask the user to produce one.

Two exercises are done outside the chat — both were completed on 2026-09-09 and
their results are already in `stocktake.md` §3. Re-read them only if the user says they have redone them:

- Career anchors questionnaire — `<DATA>/extras/career-coach/materials/2.CareeranchorsquestionnaireExcel1.xlsx`
  (read the `Summary` sheet; ignore the stale `Ranking Report` sheet)
- Values exercise — `<DATA>/extras/career-coach/materials/Values exercise.pages` (a zip of
  Snappy-compressed protobufs; unpack the `Index/Tables/*.iwa` frames — the Step 2
  groupings live in one DataList table)

---

## Step 0 — Orient

1. Read the sources above and both `<DATA>/jobs/profile/` files.
2. Tell the user which sections are already filled and which are `_(not started)_`.
3. Ask where they want to start (default: first unfilled section, in order).

---

## Step 1 — `stocktake.md` §1 · Career so far

Work through these five prompts. For each, offer a pre-filled
draft from `ideal-job-notes.md`, then refine with them:

- Roles / parts of roles enjoyed most, and why
- Roles / parts of roles disliked, and why
- Organisations with most job satisfaction, and why
- Organisations with least, and why
- Organisation cultures thrived in / frustrated by

Write the confirmed prose into the matching subsections, replacing `_(not started)_`.

---

## Step 2 — `stocktake.md` §2 · What I can offer

1. **Six most significant achievements** — pull candidates from `cv_functional.md`
   and any existing `stocktake.md` §2. For each, capture: what
   happened · circumstances that made it possible · what motivated them · how it
   added value (money made/saved, productivity, time-to-market, quality, customer
   outcomes). Aim for six; fewer is fine if that's honest.
2. **Specialist skills** (technical, most marketable)
3. **Transferable skills** (leadership, management, soft)
4. **Day-to-day skills** (tools, software, platforms)
5. **USPs** — what he brings that most other candidates for the same role won't
6. **Areas of less success, and lessons** — ask directly; this one won't be in the
   sources.

---

## Step 3 — `stocktake.md` §3 · Career anchors & personal values

Schein's eight career anchors, plus the separate values exercise. (Schein's anchors
are a published framework in their own right, not part of any one course's materials.)

**If a completed questionnaire is on disk, read it rather than asking from scratch.**
The conventional place is
`<DATA>/extras/career-coach/materials/` — an `.xlsx` export of the anchors
questionnaire (read its `Summary` sheet for the per-anchor averages; a `Ranking Report`
sheet in the common template orders them wrongly, so ignore it) and any values-exercise
file alongside it. Both live in the **data root**, not here: they are one person's
results, and this file is a method shared by everyone who installs the toolkit.

If there is no questionnaire, administer the anchors inline — the eight definitions
below are enough to self-rank against, and a self-ranking the user believes is worth
more than a score they have no feel for.

Either way:

1. **Show the ranking back and confirm it**, capturing the nuance the numbers lose —
   how the top anchors trade off against each other in practice, and whether a
   high-scoring anchor means what its label implies. Entrepreneurial creativity is the
   one that most often misleads: it can read as "wants to found a company" when the real
   signal is creative ownership, which the per-statement answers distinguish and the
   average does not.
2. **Fill the §3 anchors table** in `stocktake.md` and write the **Top 3 and what they
   mean for this search** paragraph.
3. **The values exercise** is the same shape: group the selected values, rank the groups,
   and write them to `stocktake.md` §3 "Personal values" and `criteria.yaml`
   `preferences.values` / `preferences.culture`. Note which groups were selected but not
   ranked rather than discarding them — an unranked group still rules a culture out.

The 8 anchors, with one-line definitions to prompt with:

| Anchor | It's your anchor if… |
|---|---|
| Technical / functional competence | you commit to specialising; work must challenge your skills or it bores you |
| General managerial competence | you want to run things — analyse, lead, own major decisions; specialising feels like a trap |
| Autonomy / independence | you won't be bound by others' rules, hours, standards; you work your own way |
| Security / stability | predictability matters most — tenure, stable employer, good benefits |
| Entrepreneurial creativity | you're driven to build new businesses / products that are yours |
| Service / dedication to a cause | career choices serve a value — improving the world in some way |
| Pure challenge | success = beating impossible problems / tough opponents; no challenge → bored |
| Lifestyle | everything integrates around life and family; flexibility above all |

---

## Step 4 — `stocktake.md` §4 · Career stage

The 10-stage ladder — the relevant band here:

- **5 Gaining membership** — accepted as a key contributor, sense of belonging
- **6 Gaining tenure** — 5–10 years, you and the role fused
- **7 Mid-career reassessment** — "have I accomplished what I want? time for a
  different direction?" (this is where leaving a long-held role usually sits)
- **8 Maintaining momentum / levelling off** — climb further, redefine the work, or
  rebalance; often a realisation that talents/values don't require climbing more

Ask: which stage now? which stage next, by when? how big is the jump and how would
he de-risk it (retraining, network, a sounding board)? Write the three bullets.

---

## Step 5 — `criteria.yaml` · What I'm looking for

Two exercises combined: "what criteria am I looking for in my next role", and the
career-choice decision matrix.

Fill each key by conversation. Pre-fill from `ideal-job-notes.md`, the location
memory (UK or 100% remote only), and `2026-09-08-my-goals.md`.

- `hard_filters.geography` — from memory: `[UK, fully-remote]` unless he changes it
- `hard_filters.salary_floor_gbp` — ask directly (need vs want; acceptable band)
- `hard_filters.self_employment_ok` — ask
- `hard_filters.exclude` — outright dealbreakers (e.g. "pure people-management, no
  hands-on"; "all-day-meetings role")
- `preferences.sectors` / `avoid_sectors`
- `preferences.org_size` — small / mid / large; centralised vs decentralised;
  SMEs are in scope per the career-coach direction memory
- `preferences.culture` — friendly / informal / efficient / relaxed / formal /
  prestigious / meritocratic — which fit?
- `preferences.role_types` / `role_level` / `departments`
- `preferences.sectors_open_to_with_a_leap` — adjacent-but-different domains he'd
  carry the same skills into (media, music, finance, business data). Ask the
  "is it time for a change?" question — what would have to be true of a different
  domain for the same skills to still feel worth using.
- `bonus_signals` — not filters, not core motivators; things that tip the balance
  toward a company when present (e.g. work involving Asia / China / Japan; an
  open-source footprint). Absence is never a mark against a role.
- `weighted_motivators` — **the decision matrix**. Draft 8–12 motivators from
  `ideal-job-notes.md` (deep work, creating projects from scratch, customer-facing
  / evangelist, open source & open data, data storytelling, teaching, hands-on
  building, mission alignment, …). Ask them to weight each **1–5** (5 = critical).
  Drop anything he weights 1.

Write valid YAML. Set `last_updated` to today. Lists of scalars inline
(`geography: [UK, fully-remote]`); `weighted_motivators` as a block list of
`{text, weight}` maps.

---

## Step 6 — `stocktake.md` §5 · Summary

Once §§1–4 and `criteria.yaml` are done, draft the **capabilities and career
objectives** statement — 2–3 short paragraphs synthesising: what they have proven they can
do, the anchors and motivators that must be satisfied, and the realistic shape of
the next role (type, level, sector, working style). Show it, refine, write it.

---

## Step 7 — Close out

1. Update the header of `stocktake.md`: `**Status:**` → `in progress` or `complete`
   (complete only when no `_(not started)_` remains), `**Last updated:**` → today.
2. Print a short summary: which sections were filled this session, which remain.
3. Remind them of any deferred items.
4. **If `<DATA>/jobs/targets/` is empty**, offer to define the target areas now — §6
   has just been written, which is what they are derived from. Without them `scan`
   still runs and scores every posting against nothing, silently. Follow
   `subcommands/init.md` §"Define the target areas".
5. **If the company tracker is empty** (`tools/py src/jobsdb.py categories` prints
   none), offer to seed it now — an empty tracker is the state in which `scan` finds
   nothing at all. Follow `subcommands/init.md` §"Seed the tracker", which needs the
   areas from step 4 to map categories onto.

   Both are cold-start steps, not recurring ones — skip the offer when areas or
   companies already exist.
6. Note the second-pass wiring that's still pending (not for this command to do):
   feeding `<DATA>/jobs/profile/` into scan scoring, gap analysis, cover letters, and the
   static site.
