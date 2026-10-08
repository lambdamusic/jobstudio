# jobstudio interview

Prep for an **actual interview with a company** — likely questions, drafted answers,
and questions to ask them. Not to be confused with `/jobstudio stocktake`, which
builds the career profile once, before any of this.

Two modes:

- **Application mode** (default): `/jobstudio interview [company or #N] [--stage
  hr-screen/hiring-manager/technical/panel/final/informal] [free text: specific
  concerns]` — full prep pack for one round, written as **its own file** in that
  application's folder (one file per round, since 2026-09-24 — see Step 4).
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
| `notes.md` in the application folder — **Fit check** and **CV gaps** sections, and `## To do` (its `### Application` tasks and any earlier round's) | Already-identified risk areas; turn each into a question + an honest bridging answer instead of redoing this analysis |
| **Prior round files** in the folder (`*-interview-*.md`), newest first — their `## Outcome` above all | What was already asked, what landed, what the interviewer corrected or flagged. Never re-prep a round in ignorance of the one before it |
| The tailored CV in the folder (`*cv-functional*.md`), else `<DATA>/jobs/cv/base/cv_functional.md` | Concrete achievements and phrasing to draw answers from |
| `<DATA>/jobs/companies/<slug>.md` | Culture signals, "Fit with my mission" — feeds both the "why this role" answer and the questions-to-ask-them list |
| `<DATA>/jobs/profile/stocktake.md` §1–§3, §7 | §1 orgs/cultures enjoyed & disliked (relationships/culture answers) · §2 six achievements + areas of less success and lessons (behavioural + weakness answers) · §3 anchors/values (keeps "why this role" authentic, not generic) · §7 narratives to have ready |
| `<DATA>/jobs/profile/criteria.yaml` | `weighted_motivators` and `bonus_signals` — ground "why this role/company" in what actually matters to them, not flattery |
| `<DATA>/jobs/notes/interview-technique.md` | The reusable answer bank — **check this before drafting anything new**; reuse verbatim where a question matches |
| `<DATA>/extras/career-coach/materials/emotional-intelligence.md` | The 5-tip framework the EI question set is built from (read in full each time — short file) |

---

## Step 1 — Identify context

**Application mode:** match by company name or row `#` from `src/jobsdb.py list`.
Read `job.md`, `notes.md` (all of it — Fit check and CV gaps are prep work already
done, don't repeat it), **every prior round file in the folder** (`*-interview-*.md`,
especially each `## Outcome`), the tailored CV if one exists, and
`<DATA>/jobs/companies/<slug>.md` if it exists. Note the `--stage` flag if given — weight
the mix (a screening call leans EI/culture/why-us; a technical round leans role
questions; a final/panel round leans both plus seniority/comp).

A prior round's `## Outcome` outranks the JD wherever they disagree: it is what the
company said about itself, to this candidate, out loud.

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
claim the gap doesn't exist. Where `notes.md`'s `## To do` already has a task
("brush up on Docker/Kubernetes"), that's a flag to *study*, not something to
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

### The business at a glance — once per company, at the first interview

**Only for companies with an application at interview stage**, and only once: if the
company page already has `## The business at a glance`, leave it (update it if a round
taught you something it gets wrong). Otherwise add it, together with a short
`## In one paragraph` (what they sell, to whom, where the money comes from) if the page
lacks one, both before `## Mission`.

The diagram is a ```` ```mermaid ```` `flowchart TB` in three layers: *what goes in*
(data, people, partners), *the company's products*, *who pays, for which decision*. Short
labels; solid arrows for data flowing, dotted ones for people, advice or shared methods;
then one sentence that reads the diagram in a line. Keep the arrows few — a box with an
edge to every buyer is better said once in its label. Draw from the company's own product
pages and what interviewers have said (cite it: "per the hiring manager"). **If the
research is too thin to draw without guessing, research more or leave it out** — a box
the sources don't support is worse than no diagram. Check it renders on the company page.

### Glossary — define the domain once, on the company page

Prep is where unfamiliar terms pile up. Before drafting, read the company page's
`## Glossary` (create one if the sector is unfamiliar and there is none — format in
`application.md` step 2, including the link out each entry ends on). **Add any term the
pack relies on that it lacks**: a regulation, a buyer type, an acronym from the JD. Definitions live on the company page
only, never in the round file.

Then, in the round file, mark each glossary term ***in bold italic*** the first time it
appears in a section. An application's notes and round files have no glossary of their
own, so their marked terms resolve against the company page's: they link there and show
the definition on hover. Never mark inside a heading, a link, code, or text that is
already bold or italic — the markers would collide.

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

**Application mode:** write the confirmed pack into **its own file** in the application
folder — one file per round, never appended to `notes.md`:

```
<application-folder-name>-<person-slug>-interview-<stage>-<YYYY-MM-DD>.md
001-grafana-labs-alex-rivera-interview-hiring-manager-2026-09-24.md
```

- `<stage>` is one of `hr-screen`, `hiring-manager`, `technical`, `panel`, `final`,
  `informal` (`appfolder.INTERVIEW_STAGES`) — map `--stage` onto it; ask which, if the
  user didn't say.
- **The date is the date of the interview, not today.** Ask for it if it isn't known;
  it is what orders the process on the page. Don't guess it from the calendar.
- `<person-slug>` comes from `identity.slug()` — read it, never hardcode it. The whole
  name is what `appfolder.app_filename(folder, f"interview-{stage}", "md", when=<date>)`
  builds, so use that rather than assembling the string by hand.

**Link the people and organisations you name.** An interviewer, the company, a product,
a paper or talk someone is known for: if a URL for it is in the job posting, the
company's own site, the scan data, the application folder, or something the user pasted
into this session, make the mention a markdown link. A person with no link to hand may
be searched for, under the check below. People are named in full every time — see
"Naming people" in `SKILL.md`. `## Who I'm meeting` is where this pays off most — a name you can click
through to beats a paragraph describing who they are.

**Add the link inside the existing line; never re-wrap the paragraph to fit it.** The
app renders these files with markdown's `nl2br`, so a newline can be a visible line break
on the page. Since 2026-10-07 the renderer joins a line that is plainly a continuation
(lowercase start, indented, or after a long line that does not end a sentence), but a
re-wrap that puts a sentence break or a capitalised name at the start of a line still
shows. `[Derin](https://…)` makes a line long in the file and changes nothing on the page.
Keep a `[…](…)` label on one line too.

**A person may be searched for, but only a checked match is linked** (decided
2026-10-08, TODO `#85`). Look first in the application's `## Contacts` in `notes.md`: a
person linked there is already found, so reuse that link and do not search again.
Otherwise search for their LinkedIn page, or another public profile (a staff page, a
personal site), and link it **only when both hold**: the profile names the same
employer, and its title is consistent with the part the person plays in this process (a
hiring manager in the team the role sits in, a recruiter in talent or HR). Names repeat,
and a confident link to the wrong person lands on a named individual and on the user,
who walks into a call having read about someone else. So when either check fails, or
two profiles both pass, leave the name plain and say so in one line to the user, who
can hand you the URL. A URL the user gives is sourced and linked as it is.

Record the person in `## Contacts` once found — full name, linked, then their role in
the process — so the next round reuses it rather than searching again.

Structure:

```markdown
# <Stage label> — <interviewer name, title>

## Details

- **Date:** …
- **Stage:** …
- **Who:** …
- **Format / duration:** …

## Who I'm meeting

…research on the interviewer — skip the section if there's nothing real to say…

## Prep

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

## Questions to ask them

- …

## To do

→ [This round's tasks, in My notes](#notes--<label-slug>-<date>)

## Private — not for the call

…honest reservations, comp thinking, read on the company…

## Outcome

_(to fill in after the call — what was asked, what landed, what didn't, next step)_
```

**The round's tasks are not written in the round file** (TODO `#84`). What to study or
do before the call goes into `notes.md`, in a new `### <Round label> — <YYYY-MM-DD>`
subsection at the end of `## To do` (create the section, first in the file, if it is
missing). The heading follows the fixed pattern in "Lists of things to do are checklists"
in `SKILL.md`: the label the Interviews tab shows for the round, an em dash, the round's
date — `### Hiring manager — 2026-09-24`, `### Final round — 2026-10-10`. Every item a
`- [ ]` task, one task per item, detail on indented lines. The round file's `## To do`
is one line linking that subsection: `#notes--` plus the heading's slug
(`#notes--hiring-manager-2026-09-24`, `#notes--final-round-2026-10-10`). On the
application page it opens My notes at the subsection; on the round's focus page the
round's tasks are shown above the round, under that same id.

**The `**Q:**` / `**A:**` markers are load-bearing, not decoration.** The Interviews tab
colours every question red so the eye can find them without reading the answers between
(`mark_qa` in `jobs_extras.py`). That only works on the markers, so write every question as
`- **Q:** …` with its `**A:**` beneath — never as a heading, a numbered list, or a bolded
topic title. Four of the five rounds written before this convention each invented their own
structure, and the result is a set of files that read differently from one another for no
reason. Use `###` for the four category headings only (Role / technical, Behavioural,
Emotional intelligence, Why this role).

A question hard-wrapped over several source lines is fine — the whole question stays
coloured. STAR sub-markers (`**S:**`, `**T:**`, `**A:**`, `**R:**`) sit inside an answer and
are left plain.

Then **add one line to `## Timeline` in `notes.md`** linking the new file, so the
folder still reads as one process:

```markdown
- **2026-09-24** — hiring manager round with Phil Wilkinson, 30 minutes.
  → [`001-grafana-labs-alex-rivera-interview-hiring-manager-2026-09-24.md`](#round-hiring-manager-2026-09-24)
```

The link target is the round's anchor on the page — `#round-<stage>-<date>` — **not** the
file. Round files are rendered into the Interviews tab, never published as raw `.md`, so
a relative file link is a broken link on the published site and `build_static`'s link
checker fails the build on it. `tabs.js` resolves a hash naming an element inside a panel
by opening that panel, so the anchor works on a fresh load too, not just in-session.

`notes.md` itself keeps only what is true of the **role** rather than of a meeting —
`## To do` (every task, by stage), `## My notes`, `## Contacts` (people recur across
rounds), and that `## Timeline`.
Background on the sector itself (what the domain is, how it works) is true of the
company, not the role: it goes in the company page's `## The domain`, with its terms in
the `## Glossary`, never in `notes.md`. Never re-create a `## Interview prep` heading there; it was retired
2026-09-24.

If the application isn't already `interviewing`, offer to set it:
`tools/py src/jobsdb.py set-status <num> interviewing`.

**After the interview happens**, fill in that round's `## Outcome` — what was asked,
what landed, what didn't, and the next step. It is the first thing the next round's
prep reads, and the thing that is worth most when the process runs long.

**Bank mode:** nothing is written to an application folder — just confirm the
drafted answers in chat, and move to Step 5 for anything worth keeping.

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
- `--stage hr-screen|hiring-manager|technical|panel|final|informal` — weights which
  categories get emphasis, and names the round file
- Free-text additions: specific concerns ("they'll probably grill me on Kubernetes",
  "this is the hiring manager round, not HR")
