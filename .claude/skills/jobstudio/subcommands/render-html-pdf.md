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

3. **Cover letter** — find the latest `*cover-letter*.md` file in the folder (by date). If one exists, render it (one call emits HTML + DOCX + PDF; the DOCX is also copied back into the application folder under the naming convention):

```bash
tools/py src/render.py --cover-letter --file {path_to_cover_letter} --label {folder_name}
```

4. Optionally also emit an ATS-friendly `.docx` of the CV (also copied back into the application folder under the naming convention, since `{path_to_cv_file}` is inside it):

```bash
tools/py src/render.py --docx --functional --file {path_to_cv_file} --label {folder_name}
```

5. Report all output paths. If no cover letter exists, note it and continue.

---

## Notes

- Output lands in `<DATA>/exports/<format>/<YYYY-MM-DD>/`, filename still date-prefixed with today's date. A `.docx` render whose source file lives inside `<DATA>/jobs/applications/NNN-*/` is also copied into that same folder, renamed to the application-folder naming convention (`<folder>-<person-slug>-<filetype>-<date>.docx`).
- Does not call the API — use the **`cv` subcommand** (`subcommands/cv.md`) to tailor a CV first, if you also need to regenerate it.
- Does not publish to the site — use `publish` after this if needed.
