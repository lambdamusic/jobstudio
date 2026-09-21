# How CV generation and export actually work

Part of the **[docs/](README.md)** guide collection. For *when* to run each command, see
[workflow.md](workflow.md) §1 — this is a deep dive into how CV tailoring and `render.py`
actually turn a base CV into a tailored, exported document.

Two base files exist under `jobs/cv/base/` — edit these directly, never a tailored copy:

- **`cv_functional.md`** — competency-clusters-first, condensed history second. **The
  default base** since 2026-09-08.
- **`cv_chronological.md`** — full chronological CV, dates/roles in order. An opt-in
  alternative — pick it for an application by setting that application's `cv_base` field.

Both are hand-edited normally, but if either needs to be built from scratch or fully
rebuilt (revised 2026-09-17), `/jobstudio cv --rebuild` (interview) or `--import
<path>` (from an existing CV document) does it agent-natively — see
`subcommands/cv.md` §A and the exact markdown contract in
`references/cv-base-format.md` (both files are parsed by regex, not a general markdown
engine, so the contract matters). High blast radius — every workflow in this skill
reads from these two files — so it always confirms and backs up the existing files
before overwriting.

Both are tailored the same way: **agent-native, fresh, straight into the application
folder.** There is no pre-generated library of per-area variants any more — a July–September
2026 line of work (`jobs/targets/*.yaml` driving `--runall`/`--target` into
`jobs/cv/variants/<area>/`) accumulated dozens of dated files with no downstream consumer
once the functional CV became the default base, and was retired in favour of this simpler,
on-demand model (2026-09-16).

## Tailoring (agent-native, no API call)

Revised 2026-09-17 — `src/build-cv-variants.py` (which called the Anthropic API
directly) was retired; tailoring now happens inside the Claude Code session that's
already running the `jobstudio application`/`cv` skill subcommands. Since that
session already has full context, the API round-trip was redundant judgement work, not
new capability — see `backlog/done/drop-direct-anthropic-api-plan.md`. This also means
tailoring now runs automatically when an application is logged, not on request
(superseding the earlier "on request only" behaviour).

Follow the **`cv` subcommand** (`.claude/skills/jobstudio/subcommands/cv.md`) — it
documents the rules the agent follows directly instead of sending them out as a
prompt. In short: which base gets tailored depends on the application's stored
`cv_base` field (functional unless set otherwise) — an explicit `--base` override
picks a one-off without changing what's stored. Both branches draw on `job.md` from
the application folder and, if the application has an `area` set, that area's profile
from `jobs/targets/<area>.yaml` (`emphasis`, `key_terms`, `tone`, `expand_sections`,
`condense_sections`, `description`).

- **Functional** — does **not** regenerate the whole CV. Only the `## Core
  Competencies` section (up to the next `## ` heading) is rewritten, informed by the
  area's `emphasis` list and the job description — everything else in the CV (summary,
  career history, education, skills, publications) stays byte-identical to the base.
  Bullets *within* a cluster stay in strict newest-to-oldest order — only cluster-level
  order, titles, and which bullets appear at all are up for reframing (corrected
  2026-09-17 after tailoring drifted the wrong way once). Saved as
  `<folder>-<person-slug>-cv-functional-<date>.md`.
- **Chronological** — the whole document is rewritten: bullets reordered within each
  role to lead with the most relevant evidence, and the Summary tailored to the specific
  job (the area's `emphasis`/`tone`/`expand_sections`/`condense_sections` are positioning
  guidance, not a script to copy verbatim). Saved as
  `<folder>-<person-slug>-cv-chronological-<date>.md`.

### Which CV a folder actually contains

`appfolder.pick_cv()` is the single place this is decided, and both `ensure_folder()`
and the cover-letter skill read it: a tailored CV already in the folder
(`is_tailored_cv()`, matching either base and either naming era) always wins; until one
exists, the untailored base matching the application's `cv_base` is copied in as a
placeholder.

## Rendering (no API call)

`render.py` parses a CV markdown file — `parse_variant()` for the chronological format,
`parse_functional()` for the functional one — into a data dict, then renders it. No
network call is involved at this stage; it's pure templating.

```bash
python src/render.py --functional                                       # HTML
python src/render.py --chronological --file <path> --format pdf          # PDF (via Chrome headless)
python src/render.py --docx --functional --file <path>                   # ATS-friendly Word
python src/render.py --docx --chronological --file <path> --label 001-grafana-labs
```

- **HTML** — `render_html()` / `render_functional()` fill a Python `string.Template`
  file under `src/templates/` (`cv_navy.html` for the two-column chronological layout,
  `cv_functional.html` for the single-column functional one).
- **PDF** — HTML is rendered first, then printed by headless Chrome
  (`--headless --print-to-pdf=...`, no header/footer). `_find_chrome()` looks for a
  local Chrome install; there's no PDF path without it.
- **.docx** — a separate code path (`cv_docx.build_functional()` /
  `cv_docx.build_chronological()`, needs `python-docx`) builds a real single-column Word
  document with actual heading styles and no pseudo-bullets, rather than converting the
  HTML/PDF layout — that's what makes it reliably ATS-parseable.

**If the source markdown lives inside an application folder**, any HTML/PDF/docx
rendered from it is *also* copied back into that folder under the application-folder
naming convention (`_maybe_copy_to_app_folder()`, keyed off `appfolder.app_folder_of()`)
— so exporting a tailored CV automatically leaves a copy alongside `job.md` and
`notes.md`, not just in `exports/`.

## Which export format, and why

- **`.docx` is the default** — it's the ATS-safe version: upload it to applicant
  tracking systems and online forms. Generate HTML only when it's headed for the
  website (`site-build`/`publish` — see [publishing.md](publishing.md)); generate PDF
  only when the *designed* version is specifically wanted (a human reader, or a
  portfolio link).
- The two-column `cv_navy.html` PDF is specifically unreliable for ATS parsing — column
  linearisation, pseudo-element bullets, letter-spaced headings all confuse parsers. The
  `.docx` sidesteps all of that by construction.

Every export lands at `exports/<format>/<YYYY-MM-DD>/`, created by `_export_dir()` — a
date subfolder inside `html/` / `pdf/` / `docx/`, with the filename itself keeping the
same date prefix. This is a different naming convention from the one used inside
`jobs/applications/NNN-*/` (see
[applications-and-gap-analysis.md](applications-and-gap-analysis.md) "File naming inside
an application folder") — the two trees serve different purposes (a dated export archive
vs. the working set for one specific application) and were never meant to match.
