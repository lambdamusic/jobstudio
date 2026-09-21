# Plan — drop direct Anthropic API calls, let the agent do the judgement work live

> ✅ **Done 2026-09-17** — three commits: `390b3f2` (CV tailoring agent-native +
> cover-letter consolidation), `92731db` (scan scoring split, agent-native default +
> opt-in `--api`), `d1ba93e` (CV bootstrap — `cv --rebuild`/`--import`). Verified
> against this plan's own checklist: `src/build-cv-variants.py` and its two prompt
> files are gone; `anthropic` is imported in exactly one place
> (`src/score-candidates.py`); `subcommands/cv.md`, `subcommands/scan.md`, and
> `references/cv-base-format.md` exist and match §1/§2's design. **Not yet verified:**
> a real, live run of any of the three agent-native flows (`cv` tailoring, `scan`'s
> default scoring, `cv --rebuild`/`--import`) — see `backlog/TODO.md` `#23`.

> Supersedes `backlog/scan-skill-only-refactor-plan.md` (renamed/broadened here
> 2026-09-17 after auditing the codebase and finding a second call site). Original
> scan-only plan history preserved untouched at
> `log/2026-09-12-scan-skill-only-refactor-plan.md` (append-only).

Date: 2026-09-12 (scan half), broadened 2026-09-17 (CV-tailoring half), Part A
revised 2026-09-17 (feedback round 2 — new subcommand file, trigger-timing change,
cover-letter structure consolidation), Part B revised 2026-09-17 (feedback round 3 —
keep the API scoring path alive as a deliberate opt-in alternative, not a full removal)
Status: **All parts implemented 2026-09-17** — Part A near-term (§1.4), Part A-later
base-CV bootstrap (§1.1(a)), Part B (§2.4), Part C cleanup (§3, mostly a side effect
of how A/B were built).

## 0. Scope — both call sites, not just scan

A repo-wide audit (2026-09-17) found **two** places that import `anthropic` and call
the API directly, not one:

| Script | What it calls the API for | Invoked from |
|---|---|---|
| `src/scan-portals.py` | `score_candidates()` — scores ~18–20 plausible postings per scan against the target/ideal-job/criteria profiles | `/jobs-search scan` (`subcommands/scan.md`) |
| `src/build-cv-variants.py` | `generate_variant()` — rewrites the Core Competencies section (functional) or the whole CV (chronological) to fit one job | `/jobs-search application` → "Tailor the CV to this job" (`subcommands/application.md`); relocating to a new `subcommands/cv.md` and firing automatically at logging time, per the revised Part A (§1) |

Both are always run from inside a Claude Code session (there is no other entry point
today), so the same argument applies to both: the agent already has — or can read —
everything the prompt would otherwise serialize and send out, so the API round-trip is
redundant judgement work, not new capability.

`tools/env.sh` (gitignored, holds `ANTHROPIC_API_KEY`) exists solely to feed these two
scripts. Nothing else in the repo imports `anthropic` (confirmed by grep 2026-09-17;
`build-cv-variants` is still actively used post-`#14`/`#16` CV-pipeline simplification —
it's the per-application tailoring step, not a retired variant-generator).

Cover-letter drafting is **already** agent-native — `subcommands/cover-letter.md` has
the agent write the letter directly and show it for review before saving. That's the
existing precedent both pieces below should match.

## 1. Part A — CV & cover-letter creation (revised 2026-09-17, feedback round 2)

Michele's feedback on the first draft of this section changed its shape in three
ways, beyond just removing the API call. Recorded here as decisions, not just ideas,
since they came back as direct feedback rather than open questions:

1. **New subcommand file, not folded into `application.md`.** `application.md` is
   already long, and already has a working precedent for this exact problem:
   `cover-letter.md` is a separate file it calls out to, not inlined. So the
   tailoring instructions (today's `src/prompts/*_tailored.md`, sent as an API
   prompt) move into a **new `subcommands/cv.md`**, mirroring how `cover-letter.md`
   is structured and referenced. `application.md` keeps only a short pointer to it,
   same shape as its existing cover-letter pointer.
2. **Trigger timing reverses.** Both the tailored CV and the cover letter are now
   created **immediately when an application is logged**, using their default modes
   — not gated behind "ask me first." This **supersedes** the 2026-09-09 decision
   recorded in `application.md` ("Do not run either of these automatically as part of
   logging a new application... only when he explicitly asks") — that section needs
   rewriting when this is implemented, not just the two tailoring scripts. The
   existing "show the draft for review before saving" step doesn't go away — it just
   now happens inline, within the same logging turn, instead of at some later
   explicit request. This also resolves the open question from the first draft of
   this plan (whether tailored-CV output should be shown for review like cover
   letters are) — yes, and it happens as part of the same automatic, immediate flow.
3. **Cover-letter structures consolidated.** Drop the **mirror** and **advanced**
   structures entirely — keep only **standard**, now with two variants:
   - **Standard 1** (default) — today's existing standard structure, unchanged.
   - **Standard 2** (override flag, exact name TBD at implementation — e.g.
     `--standard2`) — a new structure based on the template Michele supplied
     2026-09-17 (§1.3 below), populated from the same real sources standard 1 already
     draws on (stocktake achievements/USPs, job description wording, company file) —
     not literal `[bracket placeholders]`.
   - Default stays standard 1 unless overridden.

### 1.1 `subcommands/cv.md` — two responsibilities

New file, called from `application.md` the same way `cover-letter.md` is today.

**(a) Bootstrap the base CVs (first run only) — new scope.** If
`jobs/cv/base/cv_functional.md` / `cv_chronological.md` don't exist yet, `cv.md` is
where that gets built — either from an existing CV document Michele points at, or via
an interview flow shaped like the `jobs/profile/stocktake.md` interview in the
`interview` subcommand. This is genuinely **new scope**, not part of the original
Anthropic-API-removal ask — it surfaced because making tailoring agent-native forces
the "what if there's no base CV yet" question to be answered somewhere. It also feeds
directly into `#2`/`backlog/share-as-toolkit-plan.md` (a new user starting from
scratch has no base CV at all), so scope it properly as its own sub-step rather than a
one-liner when this is picked up — don't bolt it on as an afterthought to (b) below.

**Implemented 2026-09-17** — two modes in `cv.md` §A: **A.1 rebuild from scratch**
(interview, mirroring the `interview` subcommand's pre-fill-then-confirm philosophy,
but not file-backed resumable like that one — nothing is written until both files are
fully drafted and confirmed) and **A.2 import from an existing CV** (reads
`.md`/`.txt`/`.pdf` directly, extracts `.docx` via `python-docx` first, asks the user
to convert anything else). Both modes converge on the same final steps: derive the
functional file's Core Competencies clusters and condensed Career History from the
same facts the chronological file uses (never new content), draft the two files'
distinct Summary framings separately, show both full files for review, then write.
New reference file `references/cv-base-format.md` spells out the exact regex-parsed
markdown contract `render.py` expects (derived directly from `parse_functional()`/
`parse_variant()`) — both new bootstrap modes and the existing tailoring rules in
`cv.md` §B point at it, so the contract lives in exactly one place. Safety: this is
higher blast radius than a single tailored copy (every workflow in the skill reads
these two files) — always confirms before starting if either file exists, and backs
up existing files to `jobs/cv/base/archive/` (outside `find_base_cvs()`'s glob, so a
backup never shows up as a third "base CV" in the web app) before writing.

**(b) Tailor to one application (existing behavior, relocated + made agent-native).**
Once the base CVs exist: same logic `build-cv-variants.py` has today, moved to
agent-native per the original Part A draft —
- fold the "what to emphasise" / "you may / you may not" rules from
  `src/prompts/cv_functional_tailored.md` and `cv_chronological_tailored.md` into
  `cv.md` as agent instructions (same constraints: no invented achievements/dates/
  technologies, preserve markdown structure) — then delete those two prompt files
- agent reads the base CV, `job.md`, and the target-area YAML
  (`emphasis`/`tone`/`key_terms`/`expand_sections`/`condense_sections`) itself and
  writes the tailored text; shows it for review inline (see point 2 above)
- `build-cv-variants.py` keeps only the mechanical part: locate the application/
  folder via `jobsdb`/`appfolder`; functional — split around `## Core Competencies`
  (`split_competencies()` stays), splice in the agent-provided text, write via
  `appfolder.app_filename(folder, "cv-functional", "md")`; chronological — write the
  agent-provided full text via `appfolder.app_filename(folder, "cv-chronological",
  "md")` directly (no splice needed, so the agent may not even need the script for
  this branch — decide at implementation)
- drop `generate_variant()`, `MODEL`, `import anthropic`,
  `build_functional_prompt()`/`build_chronological_prompt()`, and `--dry-run` (no API
  call left to preview)

### 1.2 `cover-letter.md` / `cover-letter-structures.md` changes

- Remove the **mirror** and **advanced** sections from `references/cover-letter-
  structures.md`, and the corresponding mode-selection table + `--mirror`/`--advanced`
  flags from `subcommands/cover-letter.md` (`job.md` itemised-criteria detection and
  `jobs/companies/<slug>.md` richness detection, currently used to pick a structure,
  both go away with them).
- Add the **Standard 2** structure (§1.3) alongside the existing standard structure;
  update the mode table to just standard-1 (default) / standard-2 (override).
- Carry over the existing invariant unchanged: **every mode still opens with the
  direct "I'm applying for..." job-ID sentence** — this is an enforced house rule
  (see memory `feedback_cover_letter_opening_line.md`), not something either standard
  variant gets to drop.
- Update Step 7 (save) to fire automatically as part of application logging, per
  point 2 above, rather than only on a later explicit request.

### 1.3 Standard 2 — new structure (template supplied 2026-09-17)

Four paragraphs, more compressed than standard 1's four beats — a reordering of the
same source material and sourcing rules, not new content to invent:

1. **Opening — self-intro + job-ID + hook, one paragraph.** Standard 1 keeps the
   job-ID line as its own standalone paragraph; the supplied template folds self-intro
   and hook into the same paragraph as the job mention. To preserve the house opening-
   line rule, lead with the direct sentence, then continue in the same paragraph:
   > "I'm applying for the [Job Title] role at [Company]. I'm Michele Pasin, a
   > [Title/Field] with experience in [Key Skill 1] and [Key Skill 2] — I think my
   > background in [Relevant Experience] could help [Company] [solve a problem they
   > mentioned]."
2. **Achievements paragraph** — 2 named, concrete achievements with numbers/outcomes.
   Same sourcing as standard 1's marketing beat: stocktake §2 USPs, mirror the
   advert's wording, lead with the most relevant evidence.
3. **Why this company** — the research/hook paragraph; same sourcing as standard 1's
   hook beat (company file, stocktake §7), just placed third instead of second.
4. **Close** — per the supplied template: an invitation to discuss + thanks.

**Open question for Michele — the template's close conflicts with house style.** The
supplied template's close restates phone/email and signs off "Best regards," but the
existing "Close guidance (all modes)" in `cover-letter-structures.md` explicitly bans
restating contact info already in the letterhead and any call-to-action ("no call-to-
action... no availability"), and every mode today signs off "Yours sincerely." Two
ways to resolve — pick one before implementing:
  - (a) Standard 2 follows house style like standard 1 does: drop the phone/email line
    and "Best regards," keep the existing close guidance and "Yours sincerely"
    sign-off — only paragraphs 1–3 actually differ from standard 1 in substance.
  - (b) Standard 2 is deliberately a different, more direct register and gets its own
    close guidance, exempt from the "all modes" rule.
  Recommendation is (a), for consistency with the no-CTA/no-restated-contact-info rule
  already in force and the shared letterhead both variants use — but this is
  Michele's call to make explicitly, not one to infer silently.

### 1.4 Implementation notes (2026-09-17) — what actually got built

A-near-term (§1.1(b), §1.2, §1.3, and the trigger-timing change) is done. One decision
made at implementation time, not fully settled in the draft above:

- **`build-cv-variants.py` was retired outright**, not kept as a trimmed mechanical
  splicer. `subcommands/cv.md` has the agent read the base CV, splice the new Core
  Competencies section itself (functional) or write the full rewrite directly
  (chronological), and save with the naming convention — exactly the same pattern
  `cover-letter.md` already used with no Python bridge at all. This was simpler than
  standing up a hand-off contract between agent output and a script, and keeps the
  precedent consistent between the two skill subcommands.
- Deleted along with it: `src/prompts/cv_functional_tailored.md` and
  `cv_chronological_tailored.md` (content now lives in `cv.md`), plus every doc
  reference to the script (`README.md`, `docs/cv-pipeline.md`, `docs/workflow.md`,
  `docs/applications-and-gap-analysis.md`, `docs/cover-letters.md`, `SKILL.md`,
  `render-html-pdf.md`, `appfolder.py` docstrings).
- Caught and fixed in passing while rewriting the functional-tailoring rules: the old
  prompt said to reorder bullets *within* a cluster by relevance — that was already
  wrong per `[[feedback-cv-tailoring-bullet-order]]` (corrected during application
  #39) and had never been fixed in the prompt file itself. `cv.md` now states the
  newest-to-oldest rule directly.
- §1.1(a) (base-CV bootstrap) is untouched, as planned — still separate scope for
  later, ideally alongside `#2`/`share-as-toolkit-plan.md`.
- Not yet done: a new CHANGELOG.md entry for this work, and running the Django test
  suite / actually using `/jobs-search application` end-to-end to confirm the new
  flow in practice (docs and subcommand files were updated, not exercised live).

## 2. Part B — scan scoring (`scan-portals.py`), default agent-native + opt-in API path

Revised 2026-09-17 (feedback round 3). Michele's concern: the cost trade-off isn't
really "API dollars vs. free" — it's *which budget* the cost lands on. Agent-native
scoring spends Claude Code session/rate-limit budget; the API path bills separately
per token and doesn't touch that quota. That's worth keeping available as scan volume
grows (`#8`/`#9`, discovery scanning), not throwing away. Decision: keep the API
scoring path, but as a **deliberately separate, opt-in alternative** — not the default,
and not welded into the mechanical script as a conditional branch (Option 2 from the
2026-09-17 discussion, chosen over gating it behind a flag inside `scan-portals.py`
itself).

### 2.1 Default path — mechanical script + live agent scoring

Same as the original 2026-09-12 draft:
- `scan-portals.py` becomes, and **stays**, fully `anthropic`-free — fetch, dedup,
  keyword-prefilter, classify not-scanned / no-target-profile / already-tracked. Drop
  the `anthropic` import, `score_candidates()`, `SCORE_PROMPT`, `MODEL`,
  `load_criteria_block()`, `load_ideal_job_notes()` from this file **entirely** — they
  move out to §2.2, not behind a flag in this file.
- Script writes an intermediate file, e.g. `jobs/scans/YYYY-MM-DD-candidates.json`,
  with the plausible candidates per area (company/title/url/location/role_target/area)
  plus the already-computed unscored/filtered-out/not-scanned/coverage sections.
- `subcommands/scan.md`'s default step: agent reads the candidates file, the shared
  rubric file (§2.3), and the three profile sources (`jobs/targets/*.yaml`,
  `jobs/notes/ideal-job-notes.md`, `jobs/profile/criteria.yaml`), scores each candidate
  live on the same three dimensions (CV fit, ideal-job fit, location), and writes the
  Matches table straight into the final report markdown.

### 2.2 Opt-in alternative — standalone `src/score-candidates.py`

- New script. This is the **only** place `anthropic` gets imported for scan — a slimmed
  extraction of today's `score_candidates()` plus its supporting plumbing
  (`SCORING_CHUNK_SIZE` batching, `MODEL`, JSON-parse-failure fallback), all of which
  already works today and just needs to move file, not be rewritten.
- Input: `--candidates jobs/scans/YYYY-MM-DD-candidates.json` — the exact same file
  the mechanical script always produces. No separate "API mode" branch inside
  `scan-portals.py`; it never needs to know this script exists.
- Should assemble the **complete final report** end-to-end (scored Matches table +
  the unscored/filtered-out/not-scanned/coverage sections the mechanical script
  already computed), not just emit raw scores — that's what makes chaining
  `scan-portals.py` → `score-candidates.py` a fully headless, cron-able pipeline
  again, equivalent in spirit to today's monolithic script (see §4, this actually
  restores the "unattended scanning" capability the original Part B draft flagged as
  lost, as a side effect of the split — not just a cost-budget release valve).
- Invocation shape (name TBD at implementation): `/jobs-search scan --api` —
  `subcommands/scan.md` branches: default → agent scores live per §2.1; `--api` → skip
  the live-scoring step, run `score-candidates.py` instead, print/link its report.

### 2.3 Shared rubric file — prevents the two paths drifting apart

- Extract today's `SCORE_PROMPT` text (the actual scoring rubric — CV fit, ideal-job
  fit, location criteria, output JSON shape) out of `scan-portals.py` into a
  standalone file, e.g. `src/prompts/scan_score_rubric.md`.
- `score-candidates.py` reads this file and formats it per candidate batch, same as
  `SCORE_PROMPT.format(...)` does today.
- `subcommands/scan.md`'s live-scoring step instructs the agent to read the **same**
  file directly as its rubric — not a paraphrase copied into the doc's prose.
- This is the point of choosing Option 2 over a flag: **one rubric, two consumers.**
  Either path drifting out of sync becomes a one-file diff to catch, not two
  independently-maintained copies (a Python prompt constant vs. prose in a
  subcommand doc).

### 2.4 Implementation notes (2026-09-17) — what actually got built

Implemented and smoke-tested end-to-end (mechanical fetch, a hand-scored candidates
file, render, and a Django `import_jobs` refresh). One deviation from §2.1/§2.2 above:

- **A third module, `src/scan_report.py`, holds the report renderer** — `write_report()`
  and its table/list helpers, the `Candidate` dataclass, and `classify()` — rather than
  the agent hand-writing the whole final report in markdown as §2.1 originally
  described. Reasoning: `write_report()` already does real, tested, non-trivial
  computation (grouping by company, the strong/other/wrong-location split, coverage
  arithmetic) — reusing it exactly, unchanged, removes a source of report-format
  drift that hand-authoring the whole thing in prose would have risked, at basically
  no extra cost (it's a pure function, no judgement, no `anthropic` import). Both
  scoring paths now end at the same three-stage pipeline:
  1. `scan-portals.py` — fetch/dedup/pre-filter, writes `*-candidates.json` (unchanged
     from the plan).
  2. Scoring fills in `cv_score`/`ideal_score`/`location_category`/`notes` on each
     candidate and writes `*-scored.json` — the agent does this directly (reading
     `scan_score_rubric.md` as instructed in `scan.md`) for the default path;
     `score-candidates.py` does it via the API for `--api`.
  3. `scan_report.py --scored <path>` renders the final `*-portal-scan.md` from a
     scored file — used explicitly by the agent path, called in-process by
     `score-candidates.py` at the end of its own run (so `--api` stays one command,
     fully headless).
- `load_area_profiles()` also moved to `scan_report.py` (both `scan-portals.py` and
  `score-candidates.py` need it, and it has nothing to do with scoring judgement).
- `load_criteria_block()`/`load_ideal_job_notes()` moved to `score-candidates.py`
  (API-path-only formatting helpers); the agent path derives the equivalent directly
  from `jobs/profile/criteria.yaml`/`jobs/notes/ideal-job-notes.md`, per instructions
  now spelled out in both `scan_score_rubric.md` and `scan.md`.
- `write_report()`'s first parameter changed from `scanned: list[dict]` to
  `scanned_count: int` — the only thing it ever used from that list was its length,
  and a plain count travels through the JSON contract more simply than a list of
  company dicts.
- Verified live: `scan-portals.py` (both `--dry-run` and a real `--area
  knowledge-graph` run) still fetches/filters identically to before the split;
  `scan_report.py --scored` correctly renders and refreshes the Django `Scan` rows.
  (Caught and fixed in testing: a test render briefly overwrote the real committed
  `2026-09-17-portal-scan.md` — restored via `git checkout` and re-ran `import_jobs`
  to resync the web DB; no lasting effect, but worth remembering the report path is
  named only by date, so a same-day test run should point `--scored` at a scratch
  copy or accept the overwrite consciously.)
- Not yet done: an actual live API-scoring run of `score-candidates.py` (only the
  render half was exercised, via a hand-built scored file) and a real invocation of
  the `scan` skill subcommand's new agent-scoring step from a fresh Claude Code turn.

## 3. Part C — cross-cutting cleanup (once both A and B are done, not before)

Revised 2026-09-17: this is no longer "remove `anthropic` entirely" — Part B keeps one
deliberate call site alive (`src/score-candidates.py`, §2.2). Cleanup becomes "make
the default paths API-free and make the remaining one clearly opt-in," not "delete
the dependency."

- Do **not** drop `anthropic` from the venv's dependencies — `score-candidates.py`
  still needs it. If the project's packaging supports optional/extras groups, consider
  moving it into one (e.g. an `api-scoring` extra) so the default install doesn't pull
  it in; otherwise leave it a normal dependency and just document it as "only
  exercised by `scan --api`."
- `tools/env.sh`/`ANTHROPIC_API_KEY` is no longer needed for anything by **default**
  (CV tailoring is fully agent-native with no alternative kept, per Part A; scan
  defaults to agent-native too) — but don't delete the file or its docs, **reframe**
  them: update `README.md`, `docs/workflow.md`, `docs/portal-scan-and-scoring.md`,
  `subcommands/scan.md` to say it's required only if using `scan --api`, not remove
  all mention of it.
- Update `backlog/share-as-toolkit-plan.md` §8 to match: a new user doesn't *need* an
  Anthropic API key to use either default path — only if they explicitly want the
  `scan --api` fallback. Softer framing than "no longer needed at all."
- Re-grep the repo for `anthropic`/`ANTHROPIC_API_KEY` before closing this out. Now the
  expected result is **exactly one** code hit (`score-candidates.py`) plus doc mentions
  of the opt-in path — any other hit is a leftover to investigate, not something that
  should still exist.

**Status (2026-09-17): done, as each bullet above describes** — `anthropic` stayed a
normal (non-extras) dependency, with a `pyproject.toml` comment explaining it's
opt-in-only; `tools/env.sh`/`ANTHROPIC_API_KEY` reframed (not removed) across
`README.md`, `docs/workflow.md`, `docs/portal-scan-and-scoring.md`, `scan.md`;
`share-as-toolkit-plan.md` §8 updated; re-grep confirms exactly one code hit
(`score-candidates.py`). Not done: actually moving `anthropic` into an extras group —
left as a normal dependency per the "otherwise" branch above, a deliberate choice, not
an oversight.

## 4. Trade-offs

**Gains (apply to both parts):**
- One less piece of infra (API key, `tools/env.sh`, SDK dependency, JSON-parse-failure
  fallback path in scan's case)
- Judgement steps already have full profile/CV/job context loaded natively rather than
  re-serialized into a prompt string
- Confirmed 2026-09-12 (scan) that the judgement step does genuine reasoning about
  company reputation/politics/culture fit — that reasoning is just as available to the
  agent directly. The same is true of CV tailoring's "which competency framing fits
  this employer" judgement.
- Matches the cover-letter precedent already in production — one fewer inconsistent
  pattern in the skill

**Costs — differ by part:**
- **Scan**: with the §2.2 opt-in kept alive, all three of the original costs below are
  now *avoidable per-run* rather than permanent regressions — that's the whole point of
  keeping the API path rather than deleting it:
  - *Not scriptable/unattended by default* — the live-agent default needs an
    interactive session every run. Mitigated: `scan-portals.py` →
    `score-candidates.py`, chained, is a fully headless/cron-able pipeline, same as
    today's monolithic script, just split across two files (§2.2). Use that chain, not
    the default, for any unattended/scheduled use case (relevant to `#8`/`#9`).
  - *Consistency drift* — a pinned model + fixed prompt scores every posting the same
    way scan-to-scan; live agent reasoning is more flexible but slightly less
    reproducible. Mitigated: run `--api` for scans where exact scan-to-scan
    reproducibility matters (e.g. comparing two runs of the same batch).
  - *Doesn't scale as gracefully* — fine at ~20 scored candidates/run; a big volume
    jump burns a lot of turn/context (and session-quota) budget scored inline.
    Mitigated: switch to `--api` for large batches, which is exactly the
    quota-vs-dollars trade-off Michele raised — pay per token instead of spending
    session budget when volume is high.
  The residual cost is just having two scoring code paths to keep behaviourally
  aligned — addressed by the shared rubric file (§2.3), not eliminated but reduced to
  a one-file diff risk.
- **CV tailoring**: none of the above apply. Even with the timing change (fires
  automatically at logging time rather than on a later explicit ask, per §1 point 2),
  it's still triggered by Michele logging an application interactively — never cron'd
  or headless. It's inherently bespoke per application (not a repeated batch judged
  the same way, so "consistency drift" isn't a meaningful cost), and volume is one CV
  per logged application, not a growing batch. This part is close to a pure win.
- **Cover-letter consolidation (§1.3)**: not an API-removal cost as such, but worth
  naming — dropping mirror/advanced is a real loss of a structure choice for JDs with
  itemised requirements or companies with a strong POV file, in exchange for one fewer
  thing to maintain. Standard 2 is meant to cover some of that gap with a punchier,
  more compressed default option, not to replace mirror/advanced's actual mechanism
  (the two-column requirement-matching table, or the company-strategy narrative).

## 5. Recommendation

Do **Part A first**, but split it into two waves rather than one block:

- **A-near-term**: §1.1(b) (agent-native tailoring + `build-cv-variants.py` trim),
  §1.2/§1.3 (cover-letter consolidation + Standard 2), and the trigger-timing change
  (§1 point 2). This is the actual API-removal + workflow-change work, and it's still
  small and self-contained (two subcommand docs, one script, no batching to redesign).
  Resolve the §1.3 close-guidance question before writing `cover-letter-structures.md`.
- **A-later** (§1.1(a), the base-CV bootstrap flow) — **implemented 2026-09-17**, on
  request, ahead of `#2`/`share-as-toolkit-plan.md` rather than designed alongside it
  as originally suggested. Worth revisiting whether `#2`'s onboarding story wants
  anything different from what `cv.md` §A already does once that plan is picked up.

Do **Part B (scan)** second. Build both halves together, not the default first and the
opt-in "later" — `score-candidates.py` (§2.2) and the shared rubric file (§2.3) are
small enough that deferring them would just mean redoing the `SCORE_PROMPT` extraction
twice. Decide the `--api` flag name and whether `score-candidates.py` gets packaged as
an optional extra (§3) before writing code, not after.

Do **Part C (cleanup)** only after both, as a final pass, not incrementally — half-done
cleanup (e.g. removing `tools/env.sh` while one script still needs it) would break
whichever half isn't finished yet.

## 6. Not started

This file exists purely to not lose the idea and to record the (now two-part) shape of
the work. No code changes made toward this plan.
