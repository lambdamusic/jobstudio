# jobstudio interview

Prep for an **actual interview with a company** — likely questions, drafted answers,
and questions to ask them. Not to be confused with `/jobstudio stocktake`, which
builds the career profile once, before any of this.

Two modes:

- **Application mode** (default): `/jobstudio interview [company or #N] [--stage
  screening/technical/panel/final] [free text: specific concerns]` — full prep pack
  for one application, written into its `notes.md`.
- **Bank mode**: `/jobstudio interview --practice [topic]` (no company) — practise
  answers against `<DATA>/jobs/notes/interview-technique.md` and `stocktake.md` directly,
  with nothing written to an application folder. Use this when there's no specific
  interview lined up yet, or the user just wants to rehearse.

Either mode ends the same way: if an answer is good enough to reuse as-is next time,
offer to promote it into the reusable bank (see "Growing the bank" below).

---

## Sources

| Source | Feeds |
|---|---|
| The tracker database (`src/jobsdb.py list`) | Role title, area, status |
| `job.md` in the application folder | The actual JD — responsibilities/requirements drive the technical & gap questions |
| `notes.md` in the application folder — **Fit check**, **CV gaps**, **Preparation steps** sections | Already-identified risk areas; turn each into a question + an honest bridging answer instead of redoing this analysis |
| The tailored CV in the folder (`*cv-functional*.md`), else `<DATA>/jobs/cv/base/cv_functional.md` | Concrete achievements and phrasing to draw answers from |
| `<DATA>/jobs/companies/<slug>.md` | Culture signals, "Fit with my mission" — feeds both the "why this role" answer and the questions-to-ask-them list |
| `<DATA>/jobs/profile/stocktake.md` §1–§3, §7 | §1 orgs/cultures enjoyed & disliked (relationships/culture answers) · §2 six achievements + areas of less success and lessons (behavioural + weakness answers) · §3 anchors/values (keeps "why this role" authentic, not generic) · §7 narratives to have ready |
| `<DATA>/jobs/profile/criteria.yaml` | `weighted_motivators` and `bonus_signals` — ground "why this role/company" in what actually matters to him, not flattery |
| `<DATA>/jobs/notes/interview-technique.md` | The reusable answer bank — **check this before drafting anything new**; reuse verbatim where a question matches |
| `<DATA>/extras/career-coach/materials/emotional-intelligence.md` | The 5-tip framework the EI question set is built from (read in full each time — short file) |

---

## Step 1 — Identify context

**Application mode:** match by company name or row `#` from `src/jobsdb.py list`.
Read `job.md`, `notes.md` (all of it — Fit check and CV gaps are prep work already
done, don't repeat it), the tailored CV if one exists, and
`<DATA>/jobs/companies/<slug>.md` if it exists. Note the `--stage` flag if given — weight
the mix (a screening call leans EI/culture/why-us; a technical round leans role
questions; a final/panel round leans both plus seniority/comp).

**Bank mode:** skip the above; read `stocktake.md` and `interview-technique.md`
directly, and ask what topic or question type to focus on if not given.

Read `<DATA>/jobs/notes/interview-technique.md` in full either way — the point of the bank
is to stop re-deriving answers that already work.

---

## Step 2 — Build the question set

Four categories. Skip a category only if it's genuinely not relevant (e.g. no
technical round expected at screening stage).

### A. Role / technical

Pull directly from `job.md`'s responsibilities and requirements. For each
requirement already flagged as a gap in `notes.md`'s **CV gaps** section, turn it
into the question an interviewer would actually ask ("tell me about your experience
with X") plus an honest bridging answer — translate adjacent real experience, never
claim the gap doesn't exist. Where `notes.md` already has a **Preparation steps**
item ("brush up on Docker/Kubernetes"), that's a flag to *study*, not something to
draft an answer for — list it as a to-do instead of manufacturing a fake answer.

### B. Behavioural / competency

Standard "tell me about a time…" prompts, mapped to specific achievements from
`stocktake.md` §2 (the six significant achievements) — pick whichever achievement
actually fits the prompt, don't force the same story onto everything. Draft each
answer in **STAR** (Situation, Task, Action, Result) using only facts already in the
CV or `stocktake.md` — no invented numbers, employers, or outcomes.

### C. Emotional intelligence

Read `<DATA>/extras/career-coach/materials/emotional-intelligence.md` **if it exists** (optional private material — most users will not have it; fall back to general EI question practice) and generate one
question + one drafted answer per tip, using this mapping to source material:

| Tip | Draws on | Drafting note |
|---|---|---|
| 1. Highlight relationships | `stocktake.md` §1 (orgs/cultures worked well in) + §2 achievements with a team dimension | Give credit to others by name/role where the source material does — EI here is explicitly about crediting the team, not just "I did X" |
| 2. Challenges & resilience | `stocktake.md` §2 "areas of less success, and lessons" | Frame as agility/learning, not just survival — what changed in how he works afterward |
| 3. Weaknesses / self-awareness | Real, honest gap — check `notes.md` CV gaps first for one already identified for *this* role; otherwise **ask the user directly**, don't invent one | Pair the honest gap with the concrete thing being done about it. No cliché deflections ("I work too hard") |
| 4. Passions / hobbies | `<DATA>/jobs/notes/ideal-job-notes.md` if it names outside interests; otherwise **ask directly** | Genuine energy > generic "I enjoy reading" — leadership/organising within a hobby counts |
| 5. Questions about culture | `<DATA>/jobs/companies/<slug>.md` (culture/tech notes) + `criteria.yaml` `preferences.culture` | Produce 3–5 actual questions to ask *them*, not answers — tailored to this company, not generic ("what's the culture like?") |

Tips 3 and 4 are explicitly flagged in the source material as not derivable from
existing prep — **do not fabricate an answer for either; ask.**

### D. Why this role / why this company

Ground this in `criteria.yaml`'s top-weighted `weighted_motivators` that this role
actually satisfies (say which, and how — specific, not flattering) plus one concrete
hook from `<DATA>/jobs/companies/<slug>.md`'s "Fit with my mission" if present. Check
`interview-technique.md` first — reusable answers like "why did you leave Digital
Science" slot in here unchanged.

---

## Step 3 — Draft and show

Draft the full pack in one pass (this is prep under time pressure, not a reflective
exercise — don't do the stocktake's one-section-at-a-time pacing here). Show it
grouped by category A–D, marking clearly:

- Anywhere a weakness/passion answer needs the user's own input (per §2C above)
- Anywhere a reused bank answer was slotted in, and from where
- Study-only items (no answer drafted, just a flag)

Ask for edits before writing anything.

---

## Step 4 — Write

**Application mode:** write the confirmed pack into that application's `notes.md`,
under the existing `## Interview prep` heading (already scaffolded by
`/jobstudio application` — replace it if it already has content from a prior prep
pass, don't duplicate). Structure:

```markdown
## Interview prep

### Role / technical

- **Q:** …
  **A:** …

### Behavioural

- **Q:** …
  **A:** …

### Emotional intelligence

- **Q:** … *(relationships)*
  **A:** …
  [repeat per tip]

### Why this role

**Q:** …
**A:** …

### Questions to ask them

- …

### Study before the call

- …
```

**Bank mode:** nothing is written to an application folder — just confirm the
drafted answers in chat, and move to Step 5 for anything worth keeping.

---

## Step 5 — Growing the bank

After drafting (or, better, after the real interview happens and the user reports
back what actually worked), ask whether any answer is good enough to reuse verbatim
next time — same test as an existing "why did you leave <employer>" entry: it
worked in a real interview and doesn't need role-specific rewriting.

For each one the user confirms, append to `<DATA>/jobs/notes/interview-technique.md` in the
same style as the existing entry: a short dated note on when/where it worked and why
the phrasing matters, then the answer verbatim in a blockquote. Prefer this over
drafting a fresh version of the same answer next time — check the bank in Step 1
before ever redrafting something that's already there.

---

## User arguments

- A company name or `#` row number to identify the application (application mode)
- `--practice [topic]` — bank mode, no application, no file written
- `--stage screening|technical|panel|final` — weights which categories get emphasis
- Free-text additions: specific concerns ("they'll probably grill me on Kubernetes",
  "this is the hiring manager round, not HR")
