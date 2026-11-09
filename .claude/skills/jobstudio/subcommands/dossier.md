# jobstudio dossier

Put everything an application has gathered into one `.docx` to read: on a train, on a
plane, the evening before an interview. No API call. TODO `#98`.

It is for reading, not sending. What goes out is still the separate CV and cover letter
that `render` makes.

Arguments:
- One or more applications: `#1`, `1`, or a company name prefix (`grafana`)
- `--out <folder>` (optional): where to write. Default: each application's `export/` folder

**Steps:**

1. Resolve each argument to an application number. A number needs nothing doing. For a
   name, run `tools/py src/appfolder.py path <ref>`: the folder name starts with the number
   (`001-grafana-labs` → `1`).

2. Run:

   ```bash
   tools/py src/web/manage.py dossier 1 4 [--out <folder>]
   ```

   One file per application, named like the folder's other documents
   (`001-grafana-labs-<you>-dossier-2026-11-09.docx`). A second run on the same day
   replaces the first.

3. Report each output path with its section list, as the command prints it.

## What goes in

A title page with a contents list, each entry a link to its section. Then the same
documents as the application page's **Documents index**, in reading order, each on a new
page:

1. Overview: role, status, next action, contact, the fit summary
2. Job description
3. The CVs and cover letter, copied from their `.docx` in `export/`, so the dossier
   holds what was sent. One not rendered yet goes in from its markdown.
4. Other markdown files in the folder (study files, application answers)
5. My notes, then To do
6. Interview rounds, oldest first
7. The company page
8. Every note the folder's files link to

A note only gets in if something in the folder links to it, as on the Documents index. If
one is missing, the fix is to link it from `notes.md`, not to add it by hand.

## Notes

- **Links work inside the file.** The contents list, and any link from one document to
  another (a round linking a note, the notes linking a round), jump to that section, or
  to the heading the link names. They are bookmarks rather than a Word TOC field, so
  they survive opening the file in Google Docs, which never refreshes a field. Web links
  stay web links; a link to a site page the dossier doesn't hold is kept as text.
- Markdown goes through the site's own renderer (the `markdown` template filter), then
  into Word headings, lists, tables, task boxes and highlights. The sent CV and cover
  letter keep their own styles.
- A dossier saved in `export/` shows on the application page under the folder's other
  files. Only markdown goes into a dossier, so a later dossier never contains an earlier one.
