# jobstudio cv

Two responsibilities, both agent-native (no API call):

- **A. Bootstrap** the two base CVs — from scratch via an interview, or by importing
  an existing CV — when they don't exist yet, or on an explicit full rebuild request.
- **B. Tailor** a base CV to one specific application, reading the job description and
  target-area profile directly and writing the tailored text itself, the same way
  `cover-letter` drafts a letter.

Both read and write `<DATA>/jobs/cv/base/cv_functional.md` / `cv_chronological.md` (A) or a
per-application copy of them (B) — **always following the exact structural contract
in `references/cv-base-format.md`**. Read that file before writing a word of CV
markdown in either mode: `render.py` parses these files with regexes, not a general
markdown engine, so an off-pattern bullet or a hyphen where an em dash belongs fails
silently (a blank/misplaced field in the rendered CV), not with an error.

---

## A. Bootstrap the base CVs

Trigger: `<DATA>/jobs/cv/base/cv_functional.md` or `cv_chronological.md` doesn't exist yet
and the user wants a CV workflow to work at all; or the user explicitly asks to
"rebuild my CVs from scratch" / "redo my base CVs" / "import my CV from
`<file>`" — `--rebuild` (interview) or `--import <path>` (from an existing document).

**This is high blast radius — every other workflow in this skill reads from these two
files** (tailoring, cover letters, the `stocktake` pre-fill). Handle accordingly:

1. **Confirm before starting**, if either file already exists: tell the user this
   replaces both base CVs everywhere they're used, and that you'll back up the
   current ones first. Don't proceed without a clear yes.
2. **Back up existing files before writing**, always, into
   `<DATA>/jobs/cv/base/archive/cv_functional-YYYY-MM-DD.md` /
   `cv_chronological-YYYY-MM-DD.md` (create `archive/` if needed). This directory is
   deliberately outside `find_base_cvs()`'s plain `*.md` glob
   (`src/web/apps/tracker/parsers.py`), so a backup never shows up as a third "base
   CV" in the web app.
3. **Never write either file until both are fully drafted and shown for review** —
   unlike a single tailored copy or cover letter, there's no "just this one
   application" blast-radius limit here.

### A.1 — Mode: rebuild from scratch (interview)

Pre-fill sources, read first (same philosophy as the `stocktake` subcommand — draft
from what's known, don't interrogate from a blank page):

| Source | Feeds |
|---|---|
| Existing `<DATA>/jobs/cv/base/cv_functional.md` / `cv_chronological.md`, if present | Career history, wording, structure — even on a full rebuild, these are the best starting draft, not just something to discard |
| `<DATA>/jobs/profile/stocktake.md`, if it exists | §2 achievements/USPs, §6 positioning by audience — feeds the Summary framing and which achievements to lead with |

Work through these in order, one at a time — draft from pre-fill where possible, show
it, get a yes/edit before moving on. Nothing is written to either base CV file until
the very end (step 8) — this isn't file-backed resumable like the `stocktake`
subcommand; say so up front so the user knows a mid-way stop loses the draft (offer to
recap progress in chat if they want to pause and resume within the same session).

1. **Contact & header** — full name, location, email, LinkedIn, website, Google
   Scholar, GitHub, any other links to include.
2. **Career history, one employer at a time, most recent first.** For each: employer
   name + URL, overall dates there, and — if there were multiple internal roles — a
   one-line context/summary plus each role's own dates. For **each role**, collect
   3–6 concrete achievement bullets (name the scale, technology, and outcome; numbers
   help) and, optionally, the core technologies used.
3. **Education** — degree(s), institution(s), years, focus area.
4. **Skills** — categorised (match the existing labels — AI & Tooling / Technical /
   Product / Domains / Languages with proficiency levels — but the user can add or
   rename categories).
5. **Publications** — titles + links, if any.
6. **Derive the two files' distinct framings from the same facts** (don't invent new
   content here, just reshape what's already collected):
   - **Core Competencies clusters** (functional) — propose 3–5 thematic clusters
     grouping the achievement bullets from step 2, show the proposed grouping and
     which bullets land where, get confirmation/edits. Apply the newest-to-oldest
     bullet-order rule within each cluster per `cv-base-format.md`.
   - **Career History** (functional) — condensed titles/dates only, derived directly
     from step 2's raw employer/role data, no achievement prose.
   - **Two Summaries** — draft the functional-style Summary (competency/leadership-led)
     and the chronological-style Summary (delivery/achievement-led) separately, per
     `cv-base-format.md`'s note that these read differently, not just shorter/longer.
   - **Subtitle line** (functional) — a short tagline from the top competency areas.
7. **Assemble both full files** exactly per `references/cv-base-format.md`, and show
   both in full for review.
8. **On confirmation**: back up any existing files (step 2 of the safety list above),
   write both files to `<DATA>/jobs/cv/base/`, print the paths, and suggest checking the
   render (`python src/render.py --functional` / `--chronological`, or
   `/jobstudio render-html-pdf` for a specific application copy) before considering
   it done.

### A.2 — Mode: import from an existing CV

1. **Read the source file** the user points at:
   - `.md` / `.txt` / `.pdf` — read directly.
   - `.docx` — extract text first (python-docx is already a repo dependency):
     ```bash
     tools/py -c "from docx import Document; print('\n'.join(p.text for p in Document('<path>').paragraphs))"
     ```
   - Anything else (`.pages`, `.rtf`, ...) — ask the user to export or paste it as
     one of the above first, rather than guessing at an unsupported format.
2. **Extract the same categories A.1's interview collects** — contact/header, career
   history per employer/role with achievements, education, skills, publications.
   Where the source is ambiguous, thin, or missing something the target format
   expects (no "core technologies" per role, no obvious thematic grouping for
   competency clusters) — **ask**, don't invent. This can be a short, scoped
   round of clarifying questions rather than the full A.1 interview.
3. **From here, same as A.1 steps 6–8** — derive the two summaries and the
   functional clustering/condensed career history from the extracted facts, assemble
   both files per `cv-base-format.md`, show for review, back up + write on
   confirmation.

---

## B. Tailor a CV to one application

### Sources

| File | Purpose |
|------|---------|
| `<DATA>/jobs/cv/base/cv_functional.md` / `cv_chronological.md` | The base CV to tailor from |
| `job.md` in the application folder | The job description this CV is tailored to |
| `<DATA>/jobs/targets/<area>.yaml` | Target-area profile — `emphasis`, `tone`, `key_terms`, `expand_sections`, `condense_sections` |

### Steps

1. **Identify the application** — match by company name or row `#` from
   `src/jobsdb.py list`/`show`. Read `cv_base`, `area`, and the folder path. If called
   from `application` right after logging, this context is already known — skip
   straight to step 2.

2. **Choose the base** — the application's stored `cv_base` (functional unless set
   otherwise), or an explicit `--base functional`/`--base chronological` override for a
   one-off (this never changes what's stored).

3. **Read the sources** — the chosen base CV, `job.md` (or note if it's not saved yet:
   "(No job description saved for this application.)"), and, if `area` is set, that
   target's YAML.

4. **Write the tailored text**, following the rules for the chosen base:

   ### Functional (default)

   Rewrite the `## Summary` and `## Core Competencies` sections; everything else
   stays byte-identical to the base.

   **`## Summary`** — re-angle the 2-paragraph summary for this specific opportunity,
   using the matching **`stocktake.md` §6 Positioning by audience** block (lead-with +
   frame) for the application's `area` as the steer, not a script to copy verbatim.
   Same rules as Core Competencies: same facts, reframed — no new achievements,
   employers, dates, or numbers. Keep it to 2 paragraphs, matching the base's length
   and register (competency/leadership-led, not the chronological file's
   delivery-led tone — see `cv-base-format.md`).

   **`## Core Competencies`** —

   You may:
   - reorder the competency **clusters** so the most relevant comes first
   - retitle a cluster if a different framing fits the job better
   - drop a cluster bullet that's irrelevant to this role, or promote a buried one
     **into** a cluster (but see the ordering rule below)
   - adjust wording and emphasis so the language matches how this employer talks,
     mirroring the advert's own terms where genuine

   You may not:
   - invent achievements, employers, dates, numbers or technologies — same facts,
     reframed for this reader
   - **reorder the bullets *within* a cluster by perceived relevance** — keep them in
     strict newest-to-oldest order by role — most recent employer first, and within
     one employer the most recent title first, before moving to the employer before
     it. Take the order from the base CV's own Career History section rather than
     inventing one. Cluster-level order, titles, and which bullets appear at all
     are fair game — once a cluster's bullet list is decided, sort strictly by
     recency, never by topical fit to the JD
   - add a cluster whose content isn't already supported by the bullets given
   - change the markdown structure: `### Cluster name` headings with
     `- **Employer (Role):**` bullets

   Output only the rewritten `## Summary` and `## Core Competencies` sections — no
   preamble, no other sections.

   ### Chronological

   Rewrite the whole document — tailor the Summary to this specific opportunity (use
   the target's `tone`/`emphasis`/`key_terms` as guidance for angle and language, not a
   script to copy verbatim), and reorder the bullet points **within each role** to lead
   with the most relevant evidence for this employer, expanding sections named in
   `expand_sections` and condensing ones named in `condense_sections`.

   Rules:
   - Preserve all factual content — do not invent achievements, employers, dates or
     numbers
   - You may adjust emphasis and word choice, but not underlying facts
   - Preserve the same markdown structure and headings as the base

   Output the full tailored CV in markdown, no preamble or explanation.

5. **Show the draft for review** before saving, naming which base was used, unless the
   user has said not to.

6. **On confirmation, save** following the application-folder naming convention:
   - Functional: `{folder}/{folder-name}-<person-slug>-cv-functional-YYYY-MM-DD.md` —
     splice the new Summary and Core Competencies sections into the base CV (everything
     else stays as-is), replacing whichever untailored/previously-tailored copy
     `ensure_folder` put there.
   - Chronological: `{folder}/{folder-name}-<person-slug>-cv-chronological-YYYY-MM-DD.md`
     — the full rewritten document.

   Print the saved path.

## User arguments

For tailoring (B), the user may pass:
- A company name or `#` row number to identify the application
- `--base functional` / `--base chronological` to override the stored `cv_base` for a
  one-off
- Free-text additions: extra context, specific things to emphasise

For bootstrapping (A):
- `--rebuild` — mode A.1, rebuild from scratch via interview
- `--import <path>` — mode A.2, import from an existing CV document
