# Rendered exports move into `export/` (TODO `#35`)

2026-09-24

## The problem

`applications/NNN-<company>/` was a flat list mixing two kinds of file: markdown that
was written (`job.md`, `notes.md`, the tailored CV, the cover letter, the interview
rounds) and `.docx` rendered from it. A folder with a CV and a letter, each in two
formats, reads as six files where there are four things.

## What changed

`_maybe_copy_to_app_folder()` (`src/render.py`) — the one function behind
`export_docx_functional`, `export_docx_chronological` and `export_cover_letter` — now
writes into `appfolder.export_dir(folder)`, i.e. `<folder>/export/`, creating it on
first use. That is the whole write side.

The rest was the read side, which assumed one flat level.

**Existing folders are not migrated** (the same call as `#27`, which will renumber these
names). So both shapes have to keep working, and the old `md.with_suffix(".docx")`
sibling lookup — repeated in `cv_files` and `cover_letter_files` — became
`appfolder.exported_file(md)`: `export/` first, then beside the markdown, else `None`.
One function rather than a rule restated at each call site, which is what stops the two
copies drifting when `#27` lands.

`Application.extra_files` keys its exclusions on **paths** now, not filenames. It exists
so nothing dropped into an application folder goes invisible, and it decided "already
shown on another tab?" by name, only for top-level files. With the export one directory
down, a name no longer answers that question: the docx would have been listed under
*Other files* while the CV tab, looking for a sibling, showed no "Open .docx" link at
all. Paths are compared `.resolve()`d, because `exported_file()` builds its answer from
`appfolder.APPS_DIR` while the model works from `settings.DATA_ROOT` — two spellings of
one directory would compare unequal and let every export through.

Anything else in `export/` still appears under Other files, as `export/<name>`.

## What did not need changing

`find_cover_letters()` walks into a `cover-letter-*/` directory, treating it as a round
of drafts — but it only considers entries `is_cover_letter_filename()` matches, and
`export` does not. Left alone, with a test asserting it rather than a defensive guard.

## Verified

Test suite (127, six new in `ExportFolderTests`), `make-public-tree --check`,
`smoke-test`. Plus a live render against the scratch data root: the `.docx` landed in
`export/`, and the web app linked it from the Cover letters tab with nothing duplicated
under Other files.

Three of the six new tests fail against the pre-change code; the other three guard
invariants that had to survive it (the flat lookup, `export/` not being read as cover
letters, a stray file in `export/` still being visible).

One trap found while checking that: the first version of the write-side test registered
its cleanup on `dest.parent`, the path the code *returned*. Run against the old
implementation that was the application folder itself, and the cleanup deleted the
example data. It cleans up by the path the test *expects* now.

## Left open

`_maybe_copy_to_app_folder()` names the copy with `app_filename(..., date.today())`
rather than after the markdown it rendered, so re-rendering a letter written on an
earlier day produces `...-cover-letter-<today>.docx` next to `...-cover-letter-<then>.md`.
The stems no longer match, `exported_file()` finds nothing, and the export falls through
to Other files instead of being linked from its own tab. Pre-existing — the flat sibling
lookup had exactly the same hole — and it only bites when source and render happen on
different days, which is why it has not shown up in the real search. Fixing it means
either naming the export after its source or matching on filetype instead of stem, both
of which are `#27`'s territory. Flagged, not fixed.

## Migrating the existing folders

Decided the other way on the same day, at Michele's request: `manage.py migrate_exports`,
in the `backfill_status_history` mould — prints its plan, writes nothing without
`--apply`, never overwrites a name `export/` already holds, safe to re-run. 34 files
across 15 folders in the real data root.

What it moves is keyed on the naming convention (`appfolder.is_rendered_export()`), not
on "is there a matching `.md` next to it". Nine of the 34 have no same-stem sibling — the
date trap below — so a sibling test would have left exactly the ones worth tidying. The
converse rule is what protects `030-*/resources/`, two PDFs filed there by hand: they
don't carry the folder's own name as a prefix, so they are not renders and don't move.

The dual-shape readers stay. Migrating one data root doesn't migrate anyone else's, and
`exported_file()` costs nothing now that it exists.

## The date trap, closed

Migrating made the flagged defect conspicuous rather than causing it: nine of the 34
exports carry the date of the *render*, not of the markdown they render, so their stems
never matched and they showed under *Other files* with no "Open .docx" on the tab that
owns them. Four applications, `#40`, `#44`, `#45`, `#46`.

Three ways out were put to Michele: match by kind, rename the files to match their
sources, or leave it for `#27`. He chose **match by kind**. `exported_file()` now falls
back to the newest export of the same kind in `export/` when no name matches exactly.

Why that one holds up: no filename changes, so it cannot collide with `#27`, which will
reorder every one of these names; it fixes the ones already on disk and every future
render from the same cause; and it keeps the record of when each render was actually
made, which renaming would erase.

Two guards make it honest rather than merely convenient:

- **Kind, not filetype.** `document_kind()` answers only "CV" or "cover letter". The
  `<filetype>` token can't be used: a tailored CV is named after its target area
  (`...-cv-developer-advocacy-...`) while the .docx is named after the base it was built
  from (`...-cv-functional-...`), so the exact token is the one thing the two never
  agree on.
- **No guessing under ambiguity.** With more than one markdown of that kind in the
  folder — `ensure_folder()` scaffolds an untailored `cv_functional.md` beside the
  tailored CV — the fallback declines. Linking one file under two headings reads as two
  documents, and a wrong link is worse than no link.

A superseded earlier render is not linked and keeps its place under Other files: it isn't
wrong, just stale. Two of those remain in the real data (`#44`, `#45`, both 2026-09-21),
which is the intended outcome, not a leftover.

The sort key had a real bug on first run — `re.search(...) or name` compared two
`re.Match` objects and raised. Only the superseded-render test caught it, because it is
the only one with two exports of one kind to sort.

## One home per render (TODO `#36`)

Same day, straight after. `#35` put an application's exports in `export/`; this asks the
prior question — why were they being written somewhere else first at all?

Every render went to `exports/<fmt>/<date>/`, and `_maybe_copy_to_app_folder()` then
copied the .docx into the application. Two copies of each file, under two different
names. The staging name drops the application label unless `--label` was passed, so the
dated tree is a worse record of "what did I send, and when" than the application folders
now are — when the cleanup came, 22 cover-letter renders could not be attributed to any
application at all. Date alone doesn't do it: 2026-09-18 matches seven applications.

`render._home(src, filetype, ext, stem=…)` picks the destination up front:

    jobs/applications/NNN-*/...  ->  <that folder>/export/   (folder naming convention)
    jobs/cv/base/*.md            ->  jobs/cv/export/         (cv_functional-<date>.docx)
    anything else                ->  exports/<fmt>/<date>/

`_maybe_copy_to_app_folder()` is gone; `test_nothing_is_written_twice` greps the module
for it, so the two-copy behaviour can't creep back under a new name.

I recommended keeping `exports/` as a staging area and Michele pushed back — correctly.
The argument was "smallest change", which is not an argument when the task is a cleanup.
What survives is narrower and real: a render whose source has no home still needs
somewhere to go. So `exports/` stays as the generic area for documents belonging to no
folder — the career stocktake sitting there is exactly the case — rather than as a
waypoint everything passes through.

The base-CV name (`cv_functional-2026-09-22.docx`) deliberately copies
`jobs/cv/base/archive/`, which already names dated copies of the same two files that way.
One convention in that tree, not two.

### Clearing the backlog

`manage.py prune_exports`, same shape as `migrate_exports`: plan printed, `--apply` to
act, safe to re-run. 263 files, 16.0 MB.

- **40 moved.** A render labelled with an application (`..._001-grafana-labs.pdf`) goes to that
  application's `export/`, renamed to the folder convention **keeping the date it was
  rendered on** — restamping with today's would turn a June PDF into a September one and
  destroy the tree's only real piece of information. Eight applications got back the only
  rendered artifacts they had; their PDFs existed nowhere else.
- **220 deleted.** 175 renders of the retired variant library (`#14`/`#16` — the source
  markdown is gone), 22 unattributable cover-letter renders, 14 superseded base renders,
  7 byte-identical duplicates of files already in an application folder, 2 copies of
  files in `jobs/cv/drafts/`.
- **3 left alone.** Not named the way a render is named, so not the command's to touch.
  That rule is what protects the stocktake without a hardcoded filename in shared code.
  It also spared the two hand-renamed CVs from May and September, which were then deleted
  by hand as agreed.

16.0 MB -> 48 KB, 60 empty date directories removed. Nothing read `exports/` — `jobsinit`
creates it, `render.py` wrote to it, `make-public-tree` excludes it, and the published
site renders CVs from `BaseCv` markdown — so there was nothing to break.

## A cover letter renders to `.docx` alone (TODO `#37`)

Michele, straight after: "for new applications there is also an html cover letter. That
is not needed, unless explicitly requested."

`export_cover_letter()` had always written the HTML unconditionally, because
`_chrome_print_pdf()` needs a file to print and the HTML was it. That cost nothing while
every render went to `exports/` — one more file in a tree nobody looked at. `#36` moved
renders into the application folder, and the same line became a stray `.html` sitting
beside the `.docx` in every new application.

So the intermediate moved to a `tempfile.TemporaryDirectory()`, and `fmt="html"` is now
what puts an HTML file in the folder for real. `.docx` is still written every time: it is
the version that gets sent.

The flag needed a change to carry the distinction. `--format` defaulted to `"html"`, so
the cover-letter path could not tell "I want the HTML" from "I said nothing". It defaults
to `None` now and each branch resolves its own: CVs to `html` (unchanged), cover letters
to `docx`. The skills also passed `--cover-letter --docx` in two places, where `--docx`
has never done anything — the cover-letter branch returns before it is read — so the
examples dropped it rather than keep implying it matters.

`test_a_pdf_render_prints_from_a_temp_file_and_keeps_no_html` mocks Chrome and asserts
both halves: the HTML handed to it is real and readable, and its directory is not the
export folder. Asserting only "no .html afterwards" would pass just as well against a
version that printed from nothing.

Not retro-applied. 22 `.html` files are already in application `export/` folders, moved
there by `prune_exports`, and for the eight oldest applications they are part of the only
rendered artifacts those applications have.
