# jobstudio application

Log a job application and set up its full workspace in one step: index entry, company profile, folder, a copy of the CV, job description file, gap analysis + fit summary, and a thin cover-letter draft.

**It does not tailor anything** (revised 2026-10-01, TODO `#55`). The CV copy is
mechanical and the cover letter is a short generic draft, because both get refined by
hand before they are sent — a polished draft was producing work to undo rather than
saving it. Full tailoring is a request: `/jobstudio cv #N`, `/jobstudio cover-letter #N`.

Handles two modes automatically:
- **New application** — URL or text not yet in the tracker: log it, then build the full workspace.
- **Refresh** — company name or `#N` already in the tracker: skip logging, create only what's missing in the folder.

---

## Sources

| Source | Purpose |
|---|---|
| Tracker database (`src/jobsdb.py`) | Applications and companies — the source of truth |
| `<DATA>/jobs/cv/base/cv_functional.md`, `<DATA>/jobs/cv/base/cv_chronological.md` | Master CVs — the functional one (default) is copied into the folder as-is, bar the mechanical role-strip; chronological is opt-in via an application's `cv_base` field |
| `<DATA>/jobs/profile/stocktake.md` | Career profile: §6 positioning by audience, §2 achievements/USPs, §5 objectives, §7 narratives to have ready |
| `<DATA>/jobs/profile/criteria.yaml` | Hard filters, weighted motivators, bonus signals — for the gap analysis's fit check |
| `<DATA>/jobs/companies/README.md` | Template for the long-form company research file |

---

## Step 0 — Detect mode

Check whether the user's input matches an existing application:

```
tools/py src/jobsdb.py show "<company or #N>"
```

- If it prints a row → **Refresh mode** (skip to Step 4).
- Otherwise → **New application mode** (continue from Step 1).

---

## Step 1 — Fetch and extract (new application only)

If the input is a URL, fetch the page and extract the job posting text. If it's pasted text, use it directly.

Extract or infer:

| Field | Notes |
|---|---|
| **Company** | Organisation name |
| **Role** | Job title |
| **Area** | One of the user's own target areas — the filenames in `<DATA>/jobs/targets/` (`ls <DATA>/jobs/targets/`), each a CV positioning rather than an industry. Pick the best fit, reading the YAML's `description` and `key_terms` if the slug alone is ambiguous. An area may be a *role-type* target that cuts across industries (solutions architecture, developer advocacy) — choose it when the role itself is that shape, whatever the company's category. If none fits, say so rather than forcing one; a missing area is better than a wrong one, since it drives both CV tailoring and scan scoring |
| **Job URL** | Any URL present; blank if none |
| **Applied** | Date in `YYYY-MM-DD` if mentioned; default to today |
| **CV base** | Defaults to `functional`; only set to `chronological` if the user explicitly asks for that format |
| **Status** | Default `saved` unless the user says otherwise. |
| **Contact** | Name/email if mentioned; blank otherwise |
| **Next action** | Explicit next step if given; otherwise `"Review CV and apply"` |
| **Summary** | One scannable line for list views — a *complete* phrase, roughly 100–150 chars. Never a truncation of the Notes: the tables already truncate for display, so a cut-off summary just gets cut twice |
| **Notes** | Key points from the JD: requirements, seniority, culture signals, salary, location — distil, don't dump |

If a field genuinely can't be inferred, leave it blank.

---

## Step 2 — Confirm (new application only)

Show a brief one-line-per-field summary to the user and ask for confirmation or corrections. Keep it short — the goal is to catch obvious errors, not reprint everything.

---

## Step 3 — Log the application (new application only)

Applications live in the tracker database, not in markdown. Create the row with:

```
tools/py src/jobsdb.py add-application \
  --company "{Company}" \
  --role "{Role}" \
  --area {area-slug} \
  --url "{Job URL}" \
  --date YYYY-MM-DD \
  --status saved \
  --next-action "{Next action}" \
  --summary "{one line, ~60 chars, for list views}" \
  --notes "{the full record — requirements, seniority, culture signals, salary, location}" \
  --contact "{Contact}"
```

It prints the assigned row number — you'll need it for the next steps.

`--summary` is the scannable one-liner shown in tables; `--notes` is the full write-up
shown on the application page. Don't duplicate one into the other, and write `--notes`
in **paragraphs** — a single unbroken block is hard to read (the renderer will split it
at sentence boundaries as a fallback, but authored breaks are better).

## Step 4 — Ensure the company is tracked (both modes)

Every application needs a `Company` row and a researched `<DATA>/jobs/companies/<slug>.md` —
this runs every time, not just for brand-new applications, so a refresh of an
application whose company was never tracked still fills the gap.

```
tools/py src/jobsdb.py show-company "{Company}"
```

- **If found** → run `link-company` to make sure this application's `company` foreign
  key is set (idempotent, harmless if already linked), then skip to Step 5:
  ```
  tools/py src/jobsdb.py link-company <row-num>
  ```
- **If not found** → do both of the following:

  1. **Add the company row.** Infer `role-target`, `fit` (★☆☆☆☆–★★★★★), and `category`
     the same way the `company` subcommand does (`subcommands/company.md` — background
     on the fields and judgement calls lives there):
     ```
     tools/py src/jobsdb.py add-company \
       --name "{Company}" \
       --url "{careers page URL}" \
       --role-target "{role target}" \
       --fit {1-5} \
       --category "{one of the existing category names}" \
       --notes "{one line}"
     ```
  2. **Research and write `<DATA>/jobs/companies/<slug>.md`.** Web-research the company — mission,
     technology/data posture, where they are now (ownership, funding, size, direction) —
     and write the file following the template in `<DATA>/jobs/companies/README.md`: `## Mission`,
     `## Technology`, `## Where they are now`, `## Fit with my mission` (honest for/against
     read against `<DATA>/jobs/profile/stocktake.md`), `## Sources` (dated links). Match the depth
     of existing profiles (e.g. `<DATA>/jobs/companies/grafana-labs.md`) — this is real research,
     not a one-paragraph stub. Header line: `*Researched {today's date}.*`
     **Add a `## Glossary` whenever the sector is unfamiliar** (judge against
     `stocktake.md`, not general knowledge — healthcare, finance, regulation, a lab domain).
     One bullet per term, opening with a bold label (`- **EHR (Electronic Health Record).** …`),
     defined plainly. Mark each term ***in bold italic*** where it first appears in a section;
     the page then links it and shows the definition on hover. Skip terms the user already
     knows well — the glossary is for the domain, not for their own field.
     **Company-level only:** anything about this particular role or its interviews (band,
     office days, hiring manager, what to stress in a round) goes in the application's
     `notes.md`, not here — the company file must stay true for every future application.
  3. **Link the application to the new company row:**
     ```
     tools/py src/jobsdb.py link-company <row-num>
     ```

## Step 5 — Create the application folder

Run:
```
tools/py src/appfolder.py ensure <row-num>
```

This idempotently creates the folder `<DATA>/jobs/applications/NNN-company-name/`,
writes `notes.md` if it doesn't exist, installs the application's own copy of the CV if
the folder has none, and creates an **empty** cover-letter file as a placeholder. Print
the folder path.

The CV copy (2026-10-01, TODO `#55`):

- Named by the folder convention —
  `NNN-company-<person-slug>-cv-functional-YYYY-MM-DD.md` — **even though nothing has
  been tailored**. It is the file that gets edited and sent, so it is named for the job
  it is going to.
- The one change from the base is mechanical, and `appfolder.copy_cv()` does it, not
  you: the role in brackets comes off every `## Core Competencies` bullet
  (`- **Employer (Head of Data):** …` → `- **Employer:** …`). Career History keeps its
  role titles.
- **Never overwritten.** A second run on a folder that already has a CV leaves it
  alone, whether it was tailored, hand-edited, or the bare `cv_functional.md` of a
  folder scaffolded before this change.
- Whether a CV has actually been worked on is a content question, not a filename one
  (`appfolder.is_untouched_copy()`); the application page's CV tab marks an untouched
  one "unedited copy".

All application folders live directly under `<DATA>/jobs/applications/` regardless of status
(the archive/ split by status was retired 2026-09-08 — the database is the source of
truth for status, so nothing needs to move on disk when it changes).

Table ordering and company status are synced automatically: the database orders
applications by status directly, and a company becomes `applied` automatically as soon as
it has a qualifying application.

## Step 6 — Save job.md

If `{folder}/job.md` does not already exist, write it with the full extracted job description or the key fields in structured form:

```markdown
# {Company} — {Role}

**URL:** {Job URL}
**Area:** {Area}
**Date logged:** {Applied}

## Job description

{Full text of the job posting, or the extracted notes if the full text is unavailable}
```

---

## Step 7 — Gap analysis (append to notes.md)

Read the CV in the folder (the `*-cv-*.md` file — a copy of the functional base by
default, unless the application's `cv_base` is chronological).
Read `<DATA>/jobs/profile/stocktake.md` and `<DATA>/jobs/profile/criteria.yaml`. Analyse the JD
against the CV **and** against the user's profile.

If `notes.md` already contains a `### CV gaps` section, skip this step (analysis already done).

Otherwise append under `## My notes` in `notes.md`:

### Fit check
Score this role against `<DATA>/jobs/profile/criteria.yaml`:
- **Hard filters** — for each of `geography`, `salary_floor_gbp`, `self_employment_ok`
  and every `exclude` rule, say pass / fail / unknown, quoting the JD evidence. **Any
  fail or a stack of unknowns is a flag** — call it out plainly at the top.
- **Weighted motivators** — pick the 3–4 highest-weight motivators and say, in a line
  each, whether the role looks likely to satisfy them (judge from the JD).
- **Bonus signals** — note any that the company hits (Asia / China / Japan,
  e-learning, music tech, foundational AI, open-source footprint).
- **One-line verdict** — is this worth custom CV + cover-letter effort, or a
  borderline/skip?

### CV gaps
Bullet list: for each requirement or signal in the JD that is absent or underplayed in the CV, quote the JD phrase and name what's missing.

### CV improvements
For each gap that is fixable now:
- **What**: the CV line or section to change (quote it, or say "missing")
- **Why**: what the JD is asking for
- **Suggested text**: the actual revised or new text to use — draw on `stocktake.md`
  §2 (achievements, USPs) and §6 (the positioning block for this area)

### Preparation steps
Ordered list prioritised for this specific role:
- Company/team/product research to do
- Skills, tools, or concepts to brush up on
- Talking points or stories to prepare — cross-reference `stocktake.md` §7 (team
  size, why-I-left, domain translation, philosophy, stepping back from VP)
- Domain gap mitigation if the area is a stretch

### Fit summary (write to the database)

Distil the Fit check above into the scannable pros/cons/unknowns shown on the app's
Record tab (`Application.fit_level` / `fit_pros` / `fit_cons` / `fit_unknowns` —
2026-09-10; admin-editable, derived from this gap analysis, not a replacement for it).
Skip if `notes.md` already had a `### CV gaps` section (this step was skipped above too).

- **Level** — `strong` (passes every hard filter, hits most top motivators) ·
  `moderate` (passes hard filters, mixed motivator fit) · `stretch` (a real gap —
  domain leap, seniority question, or a hard-filter unknown — but worth pursuing) ·
  `weak` (fails a hard filter, or mostly cons).
- **Pros / Cons / Unknowns** — 3–6 short bullets each, one point per line, distinct
  from (shorter than) the Fit check prose above — this is the five-second read, not
  the analysis.

```
tools/py src/jobsdb.py set-fit <row-num> \
  --level {strong|moderate|stretch|weak} \
  --pros "{point one}
{point two}" \
  --cons "{point one}
{point two}" \
  --unknowns "{point one}
{point two}"
```

---

## Step 8 — Thin cover-letter draft (revised 2026-10-01)

**No CV tailoring here** — Step 5 already put the application's CV in the folder and
that is the CV. Tailoring it is a separate request (`/jobstudio cv #N`, i.e.
`subcommands/cv.md` §B) for the roles that earn the effort; don't offer to do it as
part of logging, and don't do it unasked. The reason is in TODO `#55`: these documents
get refined by hand before they go out, so a generated draft is something to read
closely and undo, not a saving. A thin, predictable starting point is worth more than a
polished wrong one.

### Write a thin cover letter

Follow the **`cover-letter` subcommand** in its `--thin` mode
(`subcommands/cover-letter.md` → "Thin draft", structure §3 in
`references/cover-letter-structures.md`): the job-ID opening line, one short honest
paragraph on why the role is interesting, one line on fit, standard close. ~120–160
words, agent-native, and no company research beyond what Step 4 already wrote.

Two rules do not relax: it opens with the "I'm applying for `<role>` at `<company>`"
line, and it must not overclaim the domain — a letter that enthuses about a sector the
user is lukewarm on is worse than a flat one they can rewrite.

Step 5 created the empty `{folder-name}-<person-slug>-cover-letter-YYYY-MM-DD.md` stub;
this fills it in. Show the draft for review (saying plainly that it is a thin draft to
refine, and that `/jobstudio cover-letter #N` writes the full version), unless the user
has said not to. Don't render a `.docx` — nothing is going out in this state.

---

## Step 9 — Confirm

Print a summary of what was created or skipped:

```
Done: {Company} — {Role}
  ✓ Logged as #{N} in the tracker database   [new] / [existing — skipped]
  ✓ Company tracked + <DATA>/jobs/companies/{slug}.md [new] / [already tracked]
  ✓ Folder: <DATA>/jobs/applications/{folder}/
  ✓ job.md                                   [new] / [already present]
  ✓ Gap analysis appended to notes.md        [new] / [already present]
  ✓ Fit summary (pros/cons/unknowns) saved   [new] / [already present]
  ✓ CV copied: {cv-filename}.md              [new] / [already present]
  ✓ Cover letter (thin draft): {filename}.md [new] / [already present]
```

Then one line on what is *not* done, since this used to do it: the CV is a mechanical
copy and the letter is a thin draft — `/jobstudio cv {N}` and
`/jobstudio cover-letter {N}` write tailored versions if this role is worth it.

## Changing an existing application — status, next action, the rest

"Mark #N as discarded", "#N: rejected", "change the next action on #N" are updates, not
a new log. Use `update-application`, not the Django admin:

```
tools/py src/jobsdb.py update-application {N} \
  [--status {status}] [--next-action "..."] [--summary "..."] [--notes "..."] \
  [--contact "..."] [--url "..."]
```

Only the flags given are touched; `""` clears a field. An unknown status is refused.
**When a status change ends the plan** (discarded, rejected, closed), set the next action
in the same call, e.g. `--next-action "None — discarded YYYY-MM-DD ({short reason})"`.
`set-status` alone leaves the old "Review CV and apply" showing on the list views.

Record the reason as a dated line under `## Timeline` in
`<DATA>/jobs/applications/{folder}/notes.md`:

```
- **YYYY-MM-DD** — Discarded. {The user's reason, in their terms.}
```

