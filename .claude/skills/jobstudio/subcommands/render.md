# jobstudio render

Render one application's CV and cover letter to `.docx` — no API call.

`.docx` is what employers ask for and what gets sent, so it is the whole job here —
and the only format there is. HTML and PDF export were removed (TODO `#70`, 2026-10-06);
if the user wants a PDF, see "If the user does want a PDF" below.

Argument can be:
- A row number: `#21` or `21`
- A company name prefix: `grafana-labs`
- A direct file path to a `.md` file

**Steps:**

1. If the argument is a row number or company name, resolve the folder with `python src/appfolder.py path <ref>` — this works regardless of status; all application folders live directly under `<DATA>/jobs/applications/`.

2. **CV** — find all CV files in the folder (`*cv-*.md`, or a bare `cv_functional.md`/`cv_chronological.md` in folders scaffolded before 2026-10-01). If there are multiple (e.g. v1 and v2), pick the one with the latest date — or ask the user to confirm if it's ambiguous. The file may be a mechanical copy of the base rather than a tailored CV (TODO `#55`) — render it anyway, that is what gets sent; just don't describe it as tailored. Which flag to pass depends on which base the file is: `cv-functional` (or `cv_functional.md`) → `--functional`; `cv-chronological` (or `cv_chronological.md`) → `--chronological`. Use the folder name as `--label`. Run:

```bash
tools/py src/render.py --functional --file {path_to_cv_file} --label {folder_name}
```

(swap `--functional` for `--chronological` if the CV file is the chronological base)

The command prints a parse report first (`Parsed …: employers: 3, roles: 4, …`);
**read it**. The parsers drop what they cannot match, so a CV can render a clean,
well-formed, *empty* document. If the report
carries a `WARNING`, the rendered file is wrong no matter how healthy it looks — fix the
markdown against `references/cv-base-format.md` and render again.

3. **Cover letter** — find the latest `*cover-letter*.md` file in the folder (by date). If one exists, render it:

```bash
tools/py src/render.py --cover-letter --file {path_to_cover_letter} --label {folder_name}
```

The `.docx` lands in the application's `export/` subfolder. Nothing else is written.

4. Report all output paths. If no cover letter exists, note it and continue.

---

## If the user does want a PDF

Render the `.docx` as usual and tell them to open it in Word or Pages and export a PDF —
one step, and a better PDF than the toolkit's headless-Chrome route ever produced. The
toolkit does not make PDFs itself (TODO `#70`): it would mean carrying a Chrome
dependency for a format that ATS parsers read less reliably than the `.docx`.

## Notes

- Output lands where its source lives (2026-09-24): a source inside `<DATA>/jobs/applications/NNN-*/` renders into that application's `export/` subfolder under the markdown's own name (`...-cv-functional-2026-10-01.md` → `export/...-cv-functional-2026-10-01.docx`, TODO `#80`); a base CV from `<DATA>/jobs/cv/base/` renders into `<DATA>/jobs/cv/export/`. One copy, not two — `<DATA>/exports/<format>/<YYYY-MM-DD>/` is now only the fallback for a source that belongs to no folder.
- Does not call the API — use the **`cv` subcommand** (`subcommands/cv.md`) to tailor the CV first, if the role is worth it and nobody has yet.
- Does not publish to the site — use `publish` after this if needed.
- To check a base CV parses without rendering anything at all, use `tools/py src/render.py --functional --check` (see `cv.md` step 8).
