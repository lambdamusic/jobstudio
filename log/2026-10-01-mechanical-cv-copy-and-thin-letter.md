# Logging an application stops tailoring (TODO `#55`)

2026-10-01

The entry was written on 2026-09-30 and deliberately left one thing open — what the copy
is called — because three readers key off the answer. Michele resolved it mid-build: the
standard application name, `NNN-company-<person-slug>-cv-functional-<date>.md`, even when
nothing has been changed. Everything else followed from that.

## What `application` does now

Step 8 used to run `cv` §B and the full `cover-letter`. It runs neither. The folder's CV
is whatever `appfolder.copy_cv()` installed at Step 5, and the only drafting left is a
**thin cover letter** — structure §3, new: the job-ID line, one honestly-thin paragraph on
why the role is interesting, one line on fit, standard close. ~120–160 words and no
company research, since a role that earns the research earns a Standard 1 instead.

Demoted, not deleted, per the entry's own recommendation. `/jobstudio cv #N` and
`/jobstudio cover-letter #N` still do the full job, and `cover-letter --thin` is how the
short form is reachable by hand.

The gap analysis was the thing most at risk of being swept up — it sits immediately before
the step that was removed — and it is untouched. It is the main source for `interview`, and
an HR screen prep the day before had been built almost entirely out of it.

## The filename, and what it cost to accept

Naming the copy like a tailored CV makes it indistinguishable *by name* from one. That was
the entry's objection to the idea, and it is a real cost — but it is the wrong thing to pay
for, because the file is the deliverable: it is what gets edited and sent, and the `.docx`
rendered from it already carried the application's name (`render._home()` →
`app_filename()`). A CV named `cv_functional.md` sitting in `012-some-company/` is a file
that reads as scaffolding and gets treated as it.

So the question moved off the filename, where it had stopped belonging:

- **`is_tailored_cv()` → `is_app_cv()`** — name level, unchanged behaviour, honest name:
  "belongs to this application". Its one real consumer, `pick_cv()`, wanted exactly that
  all along.
- **`is_untouched_copy(path)`** — content level. Compares the file against a fresh
  `strip_competency_roles()` of each base; equal means nobody has touched it. Both bases
  rather than the application's own `cv_base`, because callers iterate over files and a CV
  copied before the field changed is still an untouched copy.

`Application.tailored_cvs` is now `is_app_cv and not is_untouched_copy`, which keeps the
`/cvs/` list meaning what its heading says, and the CV tab marks an untouched one
**"unedited copy"**. The side effect is an improvement: a copy refined *by hand* counts as
worked on, where before only an agent pass did — and by hand is how these actually get
finished.

## The transform

Nine lines. `- **Employer (Role):** …` → `- **Employer:** …`, scoped by locating
`## Core Competencies` and stopping at the next `## `. No agent pass: the target form
already occurs in the base, and the rule has no judgement in it.

Two things the regex has to get right, both covered by tests because neither fails
loudly:

- **Career History keeps its role titles.** The section scope is the whole defence; a
  file-wide regex would strip them there, where the title is the entire content of the
  line.
- **Bullets with no employer prefix are left alone** (`- Maintains **some-lib** (a small
  package)…`). Anchoring on `- **` plus `:**`, with `[^*()]` for the employer, does it.

Checked against the real base CV before trusting it: 14 bullets changed, nothing else in
the file, and `render.py --check` parses the result with no warnings — the competency
parser never cared what was inside the bold text.

`copy_cv()` also stopped being able to overwrite. A folder holding any CV keeps it,
including the bare `cv_functional.md` of folders scaffolded earlier, which are not
migrated — the same stance `export/` took in September. Before #55 overwriting was
harmless because the copy was byte-identical to the base; now the file in the folder is
the work.

## Tests

`MechanicalCvCopyTests`, nine of them. The two that earn their place are the Career
History one and `test_a_second_run_does_not_touch_the_cv_already_there` — a refresh
silently eating a hand-edited CV is the failure this change makes possible, and it would
not show up until the wrong document had been sent.

One existing test changed meaning rather than breaking:
`test_creates_folder_with_untailored_cv_and_empty_cover_letter` asserted
`cv_functional.md` exists in the new folder. It now asserts a single
`*-cv-functional-*.md` and that the bare name is *absent*, so the old scaffolding cannot
come back unnoticed.

All 283 tests pass; `make-public-tree --check` clean; `smoke-test` passes.
