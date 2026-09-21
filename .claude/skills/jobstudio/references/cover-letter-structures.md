# Cover letter structures

> **`{{full_name}}`, `{{email}}` and `{{location}}` are placeholders.** Substitute the
> real values before writing anything — resolve them with `tools/py src/identity.py`,
> which reads the data root's `config.yaml` (`identity:` block) and falls back to the
> base CV's `# Name` heading. These reference files are shared toolkit code, not one
> person's documents, so no real name belongs in them.

One structure family — **standard** — with two variants. Standard 1 follows a
conventional career-transition cover-letter shape. Standard 2 is based on a template
Supplied by the toolkit's author 2026-09-17, adapted to this file's sourcing rules and close guidance.

> Revised 2026-09-17: the earlier **mirror** and **advanced** structures were retired
> (see `backlog/done/drop-direct-anthropic-api-plan.md` §1.2) — one structure family is
> simpler to keep aligned than three, and Standard 2 gives a punchier alternative
> without their extra mode-selection logic.

Pick a variant with the logic in `subcommands/cover-letter.md` (Standard 1 default,
Standard 2 only if asked for). In every variant: first-person, British English, no
filler openers, no "enclosed CV", never mention salary or availability. Numbered beats
below are the scaffold for drafting — **they are never printed as headings in the
final letter.**

---

## File structure (both variants)

```
# Cover letter — <Company>, <Role>

**{{full_name}}**  
{{location}}  
{{email}}

<D Month YYYY>

---

Dear <name, or "Hiring Manager" / "Hiring Team">,

<body>

Yours sincerely,  
{{full_name}}
```

- The `# Cover letter — …` line is a **file label**, not printed on the page — the renderer
  uses it for the document title only, and the web tracker strips it.
- Everything from the name down to the `---` is the **letterhead**: name, town, email, then
  the date on its own line, long form ("10 September 2026"). The renderer styles this zone
  small, grey, left-aligned. Keep it to those four lines — no street address, no phone
  (both are on the CV / not expected for online applications).
- Every line that should wrap (the three letterhead lines, "Yours sincerely,") ends with
  **two trailing spaces** — that's the hard line break.
- The `---` rule separates letterhead from body and must be present.

---

## 1. Standard 1 (default) — ~280–320 words, 4 short paragraphs

Opening job-ID line · research/hook · marketing · close.

1. **Identify the job — its own opening line.** A single direct sentence naming the role
   (and the req number if there is one), standing alone as its own short paragraph, then
   a blank line before paragraph 2. Not a throat-clear.
   - Yes: *"I'm applying for the Director, Search & AI Evaluation role (R113861)."*
   - No: *"I am writing to express my strong interest in applying for the position of…"*
   If responding to an advert, you can name where/when you saw it; for a targeted or
   networked approach, say why you're writing and who referred you.
2. **Research / hook.** Its own paragraph. Why *this* organisation — something specific and
   true you know about them (a product, a direction, a recent move), tied to what you do.
   Shows you've done the work; not flattery for its own sake.
3. **Marketing paragraph.** 2–3 concrete, named achievements that map onto the role's
   requirements. **Mirror the advert's wording** — use their nouns for the work. Include
   scale, technology, outcome. Lead with the USPs from stocktake §2. Differentiate from
   the likely other candidates.
4. **Close.** See "Close guidance" below.

---

## 2. Standard 2 — ~220–260 words, 4 more compressed paragraphs

A punchier, more compressed alternative to Standard 1 — same sourcing rules and the
same close guidance, just a different paragraph shape. Based on a template the toolkit's author
supplied 2026-09-17; use only when explicitly asked for (`--standard2`).

1. **Opening — self-intro + job-ID + hook, one paragraph.** Unlike Standard 1, the
   job-ID sentence isn't a standalone paragraph here — it opens the same paragraph as
   a one-line self-intro and the hook. Still leads with the direct job-ID sentence,
   never a throat-clear:
   > "I'm applying for the [Job Title] role at [Company]. I'm {{full_name}}, a
   > [Title/Field] with experience in [Key Skill 1] and [Key Skill 2] — I think my
   > background in [Relevant Experience] could help [Company] [solve a problem they
   > mentioned]."
2. **Achievements paragraph.** 2 named, concrete achievements with numbers/outcomes —
   same sourcing as Standard 1's marketing beat: lead with the USPs from stocktake §2,
   mirror the advert's wording.
3. **Why this company.** The research/hook paragraph — same sourcing as Standard 1's
   beat 2 (something specific and true about the organisation), just placed third
   instead of second.
4. **Close.** See "Close guidance" below — **the same rules apply to both variants**;
   Standard 2 does not get its own close style (decided 2026-09-17: no restating
   phone/email, no call-to-action, "Yours sincerely" sign-off, same as Standard 1).

---

## Close guidance (both variants)

**Default — portal / ATS application, no named contact:**
One sentence of specific interest in their particular challenge (not "your company's
continued success"), then:

> Yours sincerely,
> {{full_name}}

No call-to-action, no "I will call you", no "enclosed CV", no availability or salary.

**Named contact, networked, or speculative approach only:**
A light, low-pressure follow-up line is allowed — "I'll follow up next week, but do
reach out sooner if that's useful." Never a hard dated phone commitment ("I will call
you on Tuesday"): it reads as dated and doesn't fit portal-driven hiring.

**Bridging a gap:** if there's an honest gap (domain, a named methodology), one plain
sentence naming it and why it's small — never a paragraph of hedging. Matter-of-fact
register: state it, size it, move on.

---

## Phrases to avoid

- "I feel I can make a valuable contribution to the future success of your company"
- "I am convinced that I have the abilities which can help your company prosper"
- "I am writing to express my interest in the position of…", "It is worth noting
  that…", "Please find enclosed…"

Anything that softens the approach or could have been sent to any employer. Note the
distinction: a padded opener is banned, but a **direct** one-line job identification
("I'm applying for the X role") is the correct way to open either variant — not a
banned phrase.
