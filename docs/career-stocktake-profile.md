# How the career stocktake profile works

Part of the **[docs/](README.md)** guide collection. For *when* to run it, see
[workflow.md](workflow.md) "Before all of it" — this is a deep dive into what
`/jobstudio stocktake` actually builds, and where the profile it produces gets used
elsewhere in the pipeline.

Unlike the other deep-dives, this isn't a script — it's a guided, resumable
**conversation** that walks Step 1 of a structured career-transition process ("Taking
stock and what's next") and writes the answers into two files:

- **`jobs/profile/stocktake.md`** — the reflective exercises, as prose
- **`jobs/profile/criteria.yaml`** — the same material distilled into structured,
  machine-readable filters and weights

Both are scaffolded with empty sections marked `_(not started)_`, so the interview is
resumable by construction: a section without that marker is done and gets skipped
unless explicitly revisited.

## The interview's own rules

- **Pre-fill, don't interrogate.** Before asking anything, it reads
  `jobs/notes/ideal-job-notes.md`, `jobs/cv/base/cv_functional.md`, whatever's already
  in `stocktake.md`, and the `<DATA>/extras/career-coach/` session notes, and proposes a draft
  answer for each section — the user edits or confirms rather than starting from a blank
  box.
- **One section at a time**, shown as a draft, confirmed or edited, then written —
  never all questions dumped at once.
- **Stop-anytime.** It's long by design; doing two sections and resuming another day is
  expected, since the files themselves hold all the state.

## What each section actually captures

| `stocktake.md` section | Captures |
|---|---|
| §1 Career so far | Roles/orgs/cultures enjoyed vs. disliked, and why |
| §2 What I can offer | Six significant achievements (what happened, circumstances, motivation, value added), specialist/transferable/day-to-day skills, USPs, and areas of less success + lessons |
| §3 Career anchors & values | Schein's 8 anchors, scored from a questionnaire done outside the chat; the values exercise, also done outside the chat |
| §4 Career stage | Which of the 10-stage ladder he's at now, which is next, and how big that jump is |
| §5 Summary | 2–3 paragraph synthesis: proven capability + anchors/motivators that must be satisfied + realistic shape of the next role |

Two of the §3 inputs are genuinely completed outside the interview and only
transcribed in: the **career anchors questionnaire**
(`<DATA>/extras/career-coach/materials/2.CareeranchorsquestionnaireExcel1.xlsx`, `Summary`
sheet — the `Ranking Report` sheet is a stale template, ignored) and the **values
exercise** (`<DATA>/extras/career-coach/materials/Values exercise.pages` — a zipped,
Snappy-compressed `.iwa` Pages file; the Step 2 groupings live in one `DataList` table
inside it). Both were done 2026-09-09 and are re-read only if the user says they have redone
them.

His anchors, as transcribed: **Autonomy** and **Lifestyle** tied top (6.2), **Technical
/ functional competence** third (5.4), **General managerial competence** last (3.2) —
read together, this is the concrete evidence behind "not a full-time manager" showing
up everywhere else in the pipeline (CV framing, cover-letter voice, the Fit check in
gap analyses).

## `criteria.yaml` — the same material as scoring inputs

Filled by conversation in the same interview — the "what criteria am I looking for"
exercise and the career-choice decision matrix:

- **`hard_filters`** — geography (`[UK, fully-remote]`), salary floor, self-employment
  tolerance, and an explicit `exclude` list of dealbreakers (e.g. "pure people-management
  with no hands-on scope")
- **`preferences`** — sectors, sectors open to *with a leap* (adjacent domains — media,
  music, finance — carrying the same skills somewhere genuinely different), org size,
  culture signals, personal values (ranked groups from the values exercise), role
  types/level/departments
- **`bonus_signals`** — things that tip the balance when present (Asia/China/Japan work,
  e-learning, music tech, open-source footprint) but whose *absence* is never held
  against a role
- **`weighted_motivators`** — the decision matrix as data: 8–12 motivators,
  each weighted 1–5, anything weighted 1 dropped entirely

## Where the profile actually gets used

The files themselves still carry their original "not yet wired into scoring" comment
from when they were first built (2026-09-09) — that's now out of date. As of the same
day's second pass, both files feed three other pieces of the pipeline directly:

- **Portal scan scoring** — `scan-portals.py::load_criteria_block()` formats
  `criteria.yaml` into the scorer's prompt (dealbreakers penalised, top motivators
  rewarded, salary floor and bonus signals flagged in the notes); scoring degrades
  gracefully if the file is missing. See
  [portal-scan-and-scoring.md](portal-scan-and-scoring.md) §3.
- **Gap analysis** — the "Fit check" block appended to every application's `notes.md`
  scores the role against `criteria.yaml`'s hard filters and top motivators. See
  [applications-and-gap-analysis.md](applications-and-gap-analysis.md) §6.
- **Cover letters** — draw on `stocktake.md` §6 (positioning by audience) and
  `criteria.yaml`'s `bonus_signals`. See [cover-letters.md](cover-letters.md).

§6 (Positioning by audience) and §7 (Narratives to have ready) aren't built by the
interview flow at all — they were migrated wholesale from a retired
`jobs/notes/positioning.md` on 2026-09-09, one write, not a repeatable step. They're
still genuinely part of the profile and still read by the same downstream consumers;
there's just no "re-run this section" path for them the way there is for §1–§5.

## Closing out a session

The interview updates `stocktake.md`'s header (`**Status:**` → `in progress` or
`complete`, `**Last updated:**` → today), prints which sections were filled this
session and which remain, and reminds the user of anything deferred. Browsable at
`/profile/` once any section is filled.
