# jobstudio render-html-pdf

Render one application's CV and cover letter to HTML and PDF — no API call.

Argument can be:
- A row number: `#21` or `21`
- A company name prefix: `grafana-labs`
- A direct file path to a `.md` file

**Steps:**

1. If the argument is a row number or company name, resolve the folder with `python src/appfolder.py path <ref>` — this works regardless of status; all application folders live directly under `<DATA>/jobs/applications/`.

2. **CV** — find all CV files in the folder (`*cv-*.md`, or the untailored `cv_functional.md`/`cv_chronological.md` if nothing has been tailored yet). If there are multiple (e.g. v1 and v2), pick the one with the latest date — or ask the user to confirm if it's ambiguous. Which flag to pass depends on which base the file is: `cv-functional` (or `cv_functional.md`) → `--functional`; `cv-chronological` (or `cv_chronological.md`) → `--chronological`. Use the folder name as `--label`. Run:

```bash
tools/py src/render.py --functional --file {path_to_cv_file} --label {folder_name} --format html
tools/py src/render.py --functional --file {path_to_cv_file} --label {folder_name} --format pdf
```

(swap `--functional` for `--chronological` if the CV file is the chronological base)

3. **Cover letter** — find the latest `*cover-letter*.md` file in the folder (by date). If one exists, render it (this emits the `.docx`, plus a PDF because `--format pdf` is passed; both land in the application's `export/` subfolder):

```bash
tools/py src/render.py --cover-letter --file {path_to_cover_letter} --label {folder_name} --format pdf
```

`--format pdf` is required here: without it the cover-letter exporter writes only the
`.docx`, which is the version that gets sent. This subcommand is the one place a PDF is
wanted by default — everywhere else, a cover letter renders without shelling out to
headless Chrome. **Never pass `--format html` unless the user asked for HTML**: it puts
a file in the application folder that nothing downstream reads. The PDF path builds its
own HTML in a temp file.

4. Optionally also emit an ATS-friendly `.docx` of the CV (also copied back into the application folder under the naming convention, since `{path_to_cv_file}` is inside it):

```bash
tools/py src/render.py --docx --functional --file {path_to_cv_file} --label {folder_name}
```

5. Report all output paths. If no cover letter exists, note it and continue.

---

## Notes

- Output lands where its source lives (2026-09-24): a source inside `<DATA>/jobs/applications/NNN-*/` renders into that application's `export/` subfolder, named by the application-folder convention (`<folder>-<person-slug>-<filetype>-<date>.<ext>`); a base CV from `<DATA>/jobs/cv/base/` renders into `<DATA>/jobs/cv/export/`. One copy, not two — `<DATA>/exports/<format>/<YYYY-MM-DD>/` is now only the fallback for a source that belongs to no folder.
- Does not call the API — use the **`cv` subcommand** (`subcommands/cv.md`) to tailor a CV first, if you also need to regenerate it.
- Does not publish to the site — use `publish` after this if needed.
