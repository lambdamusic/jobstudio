# How interview prep works

Part of the **[docs/](README.md)** guide collection. For *when* to run it, see
[workflow.md](workflow.md) — this is a deep dive into what `/jobstudio interview`
actually builds. Not to be confused with **[career-stocktake-profile.md](career-stocktake-profile.md)**
(`/jobstudio stocktake`), which builds the career profile once, before any of this.

```
/jobstudio interview [company or #N] [--stage screening/technical/panel/final] [concerns]
/jobstudio interview --practice [topic]        # no application, rehearsal only
```

## What it reads

| Source | Feeds |
|---|---|
| `job.md` + `notes.md` (Fit check, CV gaps, and the tasks in `## To do`) in the application folder | Role/technical questions, and honest bridging answers for already-identified gaps |
| The tailored CV, else `jobs/cv/base/cv_functional.md` | Concrete achievements to answer from |
| `jobs/companies/<slug>.md` | Culture signals — feeds "why this company" and the questions-to-ask-them list |
| `jobs/profile/stocktake.md` §1–§3, §7 | Behavioural and emotional-intelligence material — see below |
| `jobs/profile/criteria.yaml` | `weighted_motivators`/`bonus_signals` ground "why this role" in what actually matters, not flattery |
| `jobs/notes/interviewing/interview-technique.md` | The reusable answer bank — checked before drafting anything new |
| `<DATA>/extras/career-coach/materials/emotional-intelligence.md` (optional) | The 5-tip framework the EI question set is built from |

## Four question categories

1. **Role / technical** — from the JD's responsibilities/requirements, cross-referenced with `notes.md`'s CV gaps section (which already exists from `/jobstudio application`'s gap analysis — see [applications-and-gap-analysis.md](applications-and-gap-analysis.md)). Each gap becomes a question plus an honest bridging answer, never a claim the gap doesn't exist.
2. **Behavioural / competency** — "tell me about a time…" prompts mapped to specific achievements from `stocktake.md` §2, drafted in STAR (Situation, Task, Action, Result).
3. **Emotional intelligence** — one question per tip in `emotional-intelligence.md`, each sourced from a specific part of the profile:

   | Tip | Source |
   |---|---|
   | Relationships | `stocktake.md` §1 + team-dimension achievements in §2 |
   | Challenges & resilience | `stocktake.md` §2 "areas of less success, and lessons" |
   | Weaknesses / self-awareness | An honest gap — from `notes.md` CV gaps, or asked directly |
   | Passions / hobbies | `ideal-job-notes.md`, or asked directly |
   | Culture questions to ask *them* | `jobs/companies/<slug>.md` + `criteria.yaml` `preferences.culture` |

   The weakness and passion prompts are deliberately **never fabricated** — the source material calls these out as not derivable from existing prep, so the skill asks rather than guesses.
4. **Why this role / why this company** — grounded in the top-weighted motivators this specific role actually satisfies, plus a concrete company hook.

## Drafting rules

- Every answer is grounded in real material already in the CV or `stocktake.md` — no invented numbers, employers, or outcomes, same non-invention constraint as CV tailoring and cover letters.
- Check `jobs/notes/interviewing/interview-technique.md` before drafting anything — a question that's already been answered well in a real interview gets reused verbatim, not redrafted.
- Drafted as one full pack, not section-by-section like the stocktake — this is time-pressured prep, not a reflective exercise.

## Where it's written

**Application mode** writes **one file per interview round**, into the application
folder:

```
<application-id>-<person-slug>-interview-<stage>-<YYYY-MM-DD>.md
001-grafana-labs-alex-rivera-interview-hiring-manager-2026-09-24.md
```

The date is the date of the **interview**, not the day the file was written — unlike
CVs and cover letters, where it is the creation date. That makes sorting on the
filename a real chronology of the process, and `## Timeline` in `notes.md` indexes the
rounds with a link each.

Stages: `hr-screen`, `hiring-manager`, `technical`, `panel`, `final`, `informal`
(`appfolder.INTERVIEW_STAGES`). Each file follows one shape:

| Section | Holds |
|---|---|
| `## Details` | date, stage, who, format, duration |
| `## Who I'm meeting` | research on the interviewer |
| `## Prep` | the drafted Q&A pack |
| `## Questions to ask them` | |
| `## To do` | one line linking this round's tasks, gathered from `notes.md` by tag |
| `## Private — not for the call` | |
| `## Outcome` | filled in afterwards — what was asked, what landed, next step |

`## Outcome` is what makes a round self-closing, and it is the first thing the next
round's prep reads.

**A round's tasks live in `notes.md`, not in the round file** (2026-10-08, TODO `#84`).
What to study or do for the round goes into the `## To do` section that opens `notes.md`.
One place then answers "what is left for this application", and a task done once is not
left unticked in a second file.

Since 2026-10-13 (TODO `#91`) that section is grouped by **theme** — four fixed `###`
headings: Domain, Stories & positions, Tech & Data, Questions & Practicalities — and a
task meant for one round ends with that round's **tag**, `@<stage>`:

```markdown
### Tech & Data

- [ ] **Learn the plugin architecture.** Enough to follow a technical conversation. @hr-screen
    - => written up in [study notes](#file-…)
```

Every task opens with a bold short title; a note on how it went is an indented
sub-bullet. The round's focus page gathers the tasks tagged for it, under their themes,
and the round file's `## To do` link lands there. They are views of one line, not copies:
each checkbox carries its index in `notes.md`, so a tick on either page writes the same
line. On My notes the tag shows as a small pill.

Themes beat stages because the same kind of preparation (domain reading, a story to
rehearse) recurs across rounds; grouping by stage split each across three or four
headings. The earlier layout — `### Application` then `### <Round label> — <date>` per
round, which `manage.py migrate_todos` produced from the older `### Preparation steps` and
`## Study before` lists — is still read: the round page tries the dated heading first.

**Why one file per round** (decided 2026-09-24): all of this used to live under a
single `## Interview prep` heading in `notes.md`, which put a round's prep, its
outcome and its timeline entry in three different places and pushed one real folder to
63% interview content. Each round has its own interviewer, emphasis and result, so
the round is the unit.

**Files only — no database row.** Prose lives on disk; the tracker keeps status. A
round gets a model the day scheduling or reminders need one.

## On the page

Rounds render on an **Interviews** tab, stacked newest first, between *Job description*
and *My notes* — once a process is live the rounds are what gets reread, and the JD is
what they're read against.

From two rounds up the panel opens with an index (one per round, newest first), each
entry linking `#round-<stage>-<date>` — an id on that round's heading. `tabs.js` resolves
a hash naming an element inside a panel by opening the panel that holds it, so those
links work on a fresh load and when shared, not only in-session. `## Timeline` in
`notes.md` uses the same anchors.

A single round shows no index: a one-item list is noise.

**`--practice` mode** writes nothing — it's rehearsal in chat only, for when there's
no specific interview lined up yet.

## Growing the bank

After a real interview, if an answer landed well and needs no role-specific
rewriting, it goes into `jobs/notes/interviewing/interview-technique.md`, the answer bank.
The bank is grouped by what a question is about (About me, Research analytics, Product
management, Technical and architecture…), one `##` per category, and each answer is a
`###` under its category: the question as the heading, a *Tested* line saying which
interview validated it and when, a few lines on why the phrasing matters, then the answer
verbatim. A new answer is filed under its category, never appended at the end, and a
category is created only when an answer needs one. Restructured this way on 2026-10-08,
when a flat list of answers had stopped being findable.
