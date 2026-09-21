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
| `job.md` + `notes.md` (Fit check, CV gaps, Preparation steps) in the application folder | Role/technical questions, and honest bridging answers for already-identified gaps |
| The tailored CV, else `jobs/cv/base/cv_functional.md` | Concrete achievements to answer from |
| `jobs/companies/<slug>.md` | Culture signals — feeds "why this company" and the questions-to-ask-them list |
| `jobs/profile/stocktake.md` §1–§3, §7 | Behavioural and emotional-intelligence material — see below |
| `jobs/profile/criteria.yaml` | `weighted_motivators`/`bonus_signals` ground "why this role" in what actually matters, not flattery |
| `jobs/notes/interview-technique.md` | The reusable answer bank — checked before drafting anything new |
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
- Check `jobs/notes/interview-technique.md` before drafting anything — a question that's already been answered well in a real interview gets reused verbatim, not redrafted.
- Drafted as one full pack, not section-by-section like the stocktake — this is time-pressured prep, not a reflective exercise.

## Where it's written

**Application mode** writes into that application's `notes.md`, under the existing
`## Interview prep` heading (already scaffolded by `/jobstudio application`).
**`--practice` mode** writes nothing — it's rehearsal in chat only, for when there's
no specific interview lined up yet.

## Growing the bank

After a real interview, if an answer landed well and needs no role-specific
rewriting, it gets appended to `jobs/notes/interview-technique.md`'s **Standard
answer bank** section — a short note on which interview validated it and why the
phrasing matters, then the answer verbatim. The existing "why did you leave Digital
Science" entry (validated at the Comply HR screen, 2026-09-16) is the template for
new entries.
