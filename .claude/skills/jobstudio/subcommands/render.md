# jobstudio render

Render one application's CV and cover letter to `.docx` — no API call.

`.docx` is what employers ask for and what gets sent, so it is the whole job here.
HTML and PDF are no longer produced (TODO `#46`, 2026-09-29): this subcommand used to
emit both every time, which left files in the application folder nobody had asked for
and nothing downstream read. **Only render them if the user asks for them by name** —
see "If the user does want a PDF" below.

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

No `--format` is needed — `.docx` is the default. The command prints a parse report
first (`Parsed …: employers: 3, roles: 4, …`); **read it**. The parsers drop what they
cannot match, so a CV can render a clean, well-formed, *empty* document. If the report
carries a `WARNING`, the rendered file is wrong no matter how healthy it looks — fix the
markdown against `references/cv-base-format.md` and render again.

3. **Cover letter** — find the latest `*cover-letter*.md` file in the folder (by date). If one exists, render it:

```bash
tools/py src/render.py --cover-letter --file {path_to_cover_letter} --label {folder_name}
```

The `.docx` lands in the application's `export/` subfolder. Nothing else is written.

4. Report all output paths. If no cover letter exists, note it and continue.

---

## If the user does want a PDF or HTML

Add `--format pdf` or `--format html` to either command above. Both are opt-in, and
`--format` on a cover letter is an *addition* — the `.docx` is written either way,
because that is the copy that gets sent.

The PDF path shells out to headless Chrome and builds its own HTML in a temp file, so
`--format pdf` does not leave an `.html` behind. Most employers take a `.docx` happily,
and anything that opens one can save a PDF — so treat a PDF as a specific request, not a
courtesy.

## Notes

- Output lands where its source lives (2026-09-24): a source inside `<DATA>/jobs/applications/NNN-*/` renders into that application's `export/` subfolder, named by the application-folder convention (`<folder>-<person-slug>-<filetype>-<date>.<ext>`); a base CV from `<DATA>/jobs/cv/base/` renders into `<DATA>/jobs/cv/export/`. One copy, not two — `<DATA>/exports/<format>/<YYYY-MM-DD>/` is now only the fallback for a source that belongs to no folder.
- Does not call the API — use the **`cv` subcommand** (`subcommands/cv.md`) to tailor the CV first, if the role is worth it and nobody has yet.
- Does not publish to the site — use `publish` after this if needed.
- To check a base CV parses without rendering anything at all, use `tools/py src/render.py --functional --check` (see `cv.md` step 8).
