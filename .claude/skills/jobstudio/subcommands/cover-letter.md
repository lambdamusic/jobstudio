# jobstudio cover-letter

Generate a cover letter tailored to a specific application, using the **standard**
structure — two variants, Standard 1 (default) or Standard 2 (a more compressed
alternative), chosen to fit the role.

**Called directly, this writes the full letter** — that is the point of asking for it.
The thin generic draft that `application` leaves in the folder when a role is logged is
a different thing (`--thin`, structure §3; see "Thin draft" below), and running this
subcommand over it is how it gets replaced with a real letter.

> Revised 2026-09-17: the earlier **mirror** and **advanced** structures were
> retired — one structure family (standard) is simpler to maintain, and Standard 2
> covers some of what mirror/advanced offered (a punchier, more direct alternative)
> without their extra selection logic. See
> `backlog/plans/001-drop-direct-anthropic-api.md` §1.2 for the reasoning.

## Sources

| File | Purpose |
|------|---------|
| the tracker database (`src/jobsdb.py list`) | Application entry: role, area, notes, status |
| `job.md` in the application folder | The job description — mirror its wording for the work |
| the application's own CV (`*-cv-*.md` in the folder), else `<DATA>/jobs/cv/base/cv_functional.md` | Concrete achievements to draw on |
| `<DATA>/jobs/companies/<slug>.md` | Company POV — **Technology**, **Where they are now**, **Fit with my mission** — feeds the research/hook paragraph |
| `<DATA>/jobs/profile/stocktake.md` | §6 Positioning by audience (lead-with + frame), §2 achievements + USPs, §7 narratives to have ready |
| `<DATA>/jobs/profile/criteria.yaml` | Bonus signals (Asia, e-learning, music tech, foundational AI) — mention if the company hits one |
| `references/cover-letter-structures.md` | All three structures in full, and the close guidance — **read this before drafting** |

## Steps

1. **Identify the application** — match by company name or row `#` from `src/jobsdb.py list`. Read the full entry for role title, area, notes, job URL.

2. **Choose the CV** — the **functional CV** is the default. Use the application's own copy in its folder (`*-cv-*.md`) if there is one, otherwise `<DATA>/jobs/cv/base/cv_functional.md`. Scan it for the achievements most relevant to the job notes. (Since 2026-10-01 that copy is often a mechanical copy of the base rather than a tailored CV — it is still the right file to read, just don't assume its wording was chosen for this role.)

3. **Read the profile and company file** — from `<DATA>/jobs/profile/stocktake.md`, take the matching block from **§6 Positioning by audience** plus anything relevant in **§7**. Check `criteria.yaml` `bonus_signals`. Read `<DATA>/jobs/companies/<slug>.md` if it exists.

4. **Pick the structure** — **Standard 1** is the default; **Standard 2** only if the
   user explicitly asks for it (`--standard2`, or "the other/shorter/punchier version");
   the **thin draft** only with `--thin`, or when `application` is calling this as part
   of logging a role (see "Thin draft" below).

5. **Read `references/cover-letter-structures.md`**, then draft in the chosen structure. Start from the file skeleton there — the `# Cover letter — …` label line, the letterhead block (**{{full_name}}** / {{location}} / {{email}} / date, long form), the `---` rule, then the body. Targets: Standard 1 ~280–320 words in 4 paragraphs; Standard 2 ~220–260 words in 4 more compressed paragraphs. The numbered beats are scaffold only — **never print them as headings**. Every variant opens with a direct one-line job identification (role name + req number) — Standard 1 as its own short paragraph, Standard 2 folded into the opening paragraph (see the reference file). Mirror the job description's wording for the work. Use the close guidance in the reference file (default = no call-to-action, plain sign-off) — it applies to **all three** structures.

6. **Show the draft** to the user for review, naming which structure you used and why. Ask: "Happy with this, or any changes?"

7. **On confirmation**, ensure the application folder exists:
   ```
   tools/py src/appfolder.py ensure <row-num>
   ```
   Save following the application-folder naming convention:
   `{folder}/{folder-name}-<person-slug>-cover-letter-YYYY-MM-DD.md` (date = today).
   Print the saved path. Then render the `.docx`:
   ```
   tools/py src/render.py --cover-letter --file "<saved path>"
   ```
   The `.docx` is written straight into the application's `export/` subfolder — the
   markdown stays at the top level. `.docx` is the only format (TODO `#70`); a user who
   wants a PDF exports one from Word or Pages.

   The cover letter appears on the application page automatically — no `import_jobs` step
   (letters are scanned from the folder by naming convention).

## Thin draft (`--thin`)

What `application` asks for when it logs a role (2026-10-01, TODO `#55`) — and what to
use if the user says "just a quick one". Structure §3 in
`references/cover-letter-structures.md`: the job-ID line, a short honestly-thin
paragraph on why the role is interesting, one line on fit, standard close. ~120–160
words.

Two things do **not** relax for it: the opening job-ID line, and the rule against
overclaiming the domain — a letter that enthuses about a sector the user is lukewarm on
is worse than a flat one, because they are the one who has to send it.

Steps 1 and 2 only (the application entry, `job.md`, and the CV in the folder for the
one fit line). **Skip step 3** — no company research, no stocktake positioning, no
bonus signals; a role that earns that research earns a Standard 1 instead. Save it the
same way (step 7) into the empty stub `appfolder.ensure_folder()` already created —
but **don't render the `.docx`**: nothing is going out in this state, and `render` is
there for when it is. Say in one line that it is a thin draft to refine, and that
`/jobstudio cover-letter #N` writes the full version.

## Writing style

**Voice:** Casual but precise — like talking to a smart colleague, but rigorous. First-person throughout. Confident, not apologetic.

**Sentences and paragraphs:**
- Short paragraphs, one idea each — split if a paragraph runs past 4–5 lines
- Mix short punchy sentences with the occasional longer one for rhythm
- Never start a paragraph with a definition or a disclaimer

**Language:**
- Plain English over academic language; concrete over abstract
- Contractions are fine (it's, that's, I've, I'd)
- British English spelling (organisation, modelling, colour)
- No buzzwords unless they earn their place — "ontology" is precise; "synergy" is not

**Avoid:**
- Passive voice
- Padded openers ("I am writing to express my interest in the position of…", "It is worth noting that…") — but note every letter *should* open with a direct one-line job identification ("I'm applying for the X role (req N)"); that is not a banned opener
- Hedging every claim
- Never mention salary, availability, or reference "enclosed CV"
- The dated phone call-to-action ("I will call you on Tuesday…") — see the close guidance in `references/cover-letter-structures.md`

**Formality:** Slightly more formal for large traditional orgs (legacy publishers, financial-data firms, government departments); default conversational register for everyone else.

## User arguments

The user may pass:
- A company name or `#` row number to identify the application
- `--standard2` to use the Standard 2 variant instead of the default (Standard 1)
- `--thin` for the thin draft (structure §3) instead of a full letter
- Free-text additions: extra context, specific things to emphasise, tone notes
