# jobstudio cv

Two responsibilities, both agent-native (no API call):

- **A. Bootstrap** the two base CVs — from scratch via an interview, or by importing
  an existing CV — when they don't exist yet, or on an explicit full rebuild request.
- **B. Tailor** a base CV to one specific application, reading the job description and
  target-area profile directly and writing the tailored text itself, the same way
  `cover-letter` drafts a letter. **On request only** — `application` stopped doing this
  automatically on 2026-10-01 (TODO `#55`); every application folder gets a mechanical
  copy of the base instead, and this is what you run for the roles worth the effort.

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

   **If both files already exist and are in good shape, say what `--rebuild` is for
   before taking the yes.** It is a blank-page tool. Run against a good existing pair
   the realistic outcome is eight steps of re-approving the user's own text, while the
   one thing that genuinely changes is content that lives in only one of the two files
   — and that change is a loss (see A.1's pre-fill rule, and TODO `#61`). Name the
   alternatives in the same breath: editing the two files directly for a targeted
   change, or `--import <path>` if there is a newer document to bring in. Then do what
   the user asks. This is a steer, not a refusal.
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
| Existing `<DATA>/jobs/cv/base/cv_functional.md` **and** `cv_chronological.md` — **read both, every time** | Career history, wording, structure — even on a full rebuild, these are the best starting draft, not just something to discard |
| `<DATA>/jobs/profile/stocktake.md`, if it exists | §2 achievements/USPs, §6 positioning by audience — feeds the Summary framing and which achievements to lead with |

**Read both base CVs and collect the union of what they say. This is the single
easiest way to do real damage with this subcommand.** The two files are *not* two
views of one fact set — they drift, and in practice the functional file's
`## Core Competencies` ends up the richer document, carrying figures, named
initiatives, named events and scale numbers that the chronological file's role bullets
never had (`cv-base-format.md` says which file is the source of record). The failure is
quiet and total: the chronological file's `## Experience` reads as the obvious
career-history pre-fill, step 6 derives both files from whatever step 2 collected, and
every functional-only fact is gone. Both files then parse perfectly and `--check`
reports `CHECK OK`, because nothing is malformed — only poorer.

So, concretely:

- Diff the two in your head section by section before asking the user anything.
- Where a fact appears in one file and not the other, **carry it into the collected set
  and tell the user it was in only one** — a fact may be dropped because the user
  decided to drop it, never because the pre-fill did not look.
- The same applies to `## Skills`, which also differs between the files more often than
  not. Step 4 collects one set and writes it to both, so it silently converges them:
  show the difference and ask which wording is canonical rather than picking one.
- This is why step 8's backups into `archive/` are not optional. No check can tell a
  CV that lost a fact from one that never had it; the backup is the only way back.

Work through these in order, one at a time — draft from pre-fill where possible, show
it, get a yes/edit before moving on. Nothing is written to either base CV file until
the very end (step 8) — this isn't file-backed resumable like the `stocktake`
subcommand; say so up front so the user knows a mid-way stop loses the draft (offer to
recap progress in chat if they want to pause and resume within the same session).

1. **Contact & header** — full name, location, email, and then *whichever* of
   LinkedIn, website, Google Scholar, GitHub or anything else they actually have.
   Ask once, as an open question ("any links you want on it?"), and take "none" for
   an answer: plenty of people have no public profiles, and a CV without them is
   finished, not thin. Don't re-ask, don't leave a placeholder, and don't mention
   the absence in the summary you give back.
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
   write both files to `<DATA>/jobs/cv/base/`, print the paths, and then **verify the
   parse — this step is not optional**:

   ```bash
   tools/py src/render.py --functional --check
   tools/py src/render.py --chronological --check
   ```

   `--check` parses and reports what it read, writing no files. The parsers are regexes
   that discard whatever they cannot match, so a CV in the wrong shape produces an
   *empty* CV rather than an error — a render that "worked" is no evidence the content
   survived. `--check` prints a count per section, names any section it could not read,
   and exits non-zero if anything was lost. Fix the markdown against
   `references/cv-base-format.md` and re-run until it says `CHECK OK`.

   Do not render a `.docx` to eyeball the result instead: `--check` answers the same
   question without producing a file nobody wants (see TODO `#46`).

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
   confirmation, and run `--check` on both (A.1 step 8).

   **Take the format from `references/cv-base-format.md`, not from a CV you read.**
   That file is the contract the parser implements; any other CV — `example-data`'s
   included — is just a file that happens to be lying around, and copying its shape
   is how an import silently loses its entire work history. This is not hypothetical:
   it is what happened on 2026-09-29, twice in one session, because the shipped
   examples were themselves off-contract (backlog/log/2026-09-29-second-machine-findings.md).
   They are correct again now, and `--check` is what keeps the question answerable
   without trusting either file.

---

## B. Tailor a CV to one application

Asked for, not automatic: `/jobstudio cv #N`, "tailor the CV for X", or the user asking
for a rewrite. Logging an application leaves a mechanical copy of the base in the folder
(`appfolder.copy_cv()` — the bracketed roles stripped from Core Competencies and nothing
else), because these get refined by hand before they are sent. This subcommand is the
upgrade from that copy to a CV actually written for the role, and it replaces it in
place.

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
   otherwise), or an explicit `--base functional`/`--base chronological` override.

   An override does not change what is stored, and does not remove the CV already in
   the folder: the application ends up with one CV per base, which is a legitimate
   state (step 6). Only an explicit "from now on" changes the stored value.

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
     `- **Employer:**` bullets — employer only, since you are tailoring the folder's
     copy, which already has the bracketed roles stripped (see `cv-base-format.md`)

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

6. **On confirmation, save** following the application-folder naming convention, dated
   today — the day it was tailored, not the day the role was logged:
   - Functional: `{folder}/{folder-name}-<person-slug>-cv-functional-YYYY-MM-DD.md` —
     splice the new Summary and Core Competencies sections into the **copy already in
     the folder** (everything else stays as-is), and **delete the copy you tailored
     from if its filename differs** (an earlier date, say). One CV per application: two
     files one of which is a stale copy is how the wrong one gets sent. Keep the
     competency bullets in the employer-only form the copy is already in — the
     bracketed role does not come back.
   - Chronological: `{folder}/{folder-name}-<person-slug>-cv-chronological-YYYY-MM-DD.md`
     — the full rewritten document.

   Print the saved path. Then render the `.docx` — the CV is the document that actually
   gets sent, so it is not finished until there is one (TODO `#80`):

   ```bash
   tools/py src/render.py --functional --file "<saved path>"      # or --chronological
   ```

   It is written to the application's `export/` subfolder under the markdown's own name
   and date, so the `.md` and the `.docx` always pair — re-rendering later overwrites it
   rather than adding a second copy. If the render's parse report shows a problem, fix
   the markdown and render again before saying it is done.

   **A `--base` override adds a CV; it does not replace one** (TODO `#60`, decided
   2026-10-01 after trying the other way). Running `--base chronological` on an
   application stored as `functional` leaves the folder holding one CV of each, and
   that is fine: they are two genuinely different documents for the same role, and the
   earlier one may be what was already sent. Do **not** delete the other base's CV to
   tidy up.

   The "one CV per application" rule above is about *the same base* — a tailored pass
   superseding an earlier copy of the file it tailored, where two files differing only
   by date really is how the wrong one gets sent. Two different bases are not that.

   - **Say which CVs the folder now holds**, when you print the saved path. The
     application page's CV tab indexes them all when there is more than one, so the
     answer to "which is live" is "look, they are both there, dated" rather than
     something the toolkit decides by deleting a file.
   - **Leave the stored `cv_base` alone** unless the user says the switch is permanent
     — "use the chronological one for this role from now on". Then, and only then:

     ```bash
     tools/py src/jobsdb.py set-cv-base <num> chronological
     ```

     Without that it stays as it was, so the next `/jobstudio cv #N` with no override
     tailors the original base again — which is correct, and will supersede that base's
     own CV rather than the other one.

## User arguments

For tailoring (B), the user may pass:
- A company name or `#` row number to identify the application
- `--base functional` / `--base chronological` to tailor from the other base. Adds a
  CV alongside the one already there and leaves the stored `cv_base` as it was — step 6
- Free-text additions: extra context, specific things to emphasise

For bootstrapping (A):
- `--rebuild` — mode A.1, rebuild from scratch via interview
- `--import <path>` — mode A.2, import from an existing CV document
