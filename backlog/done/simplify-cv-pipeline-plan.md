# Simplify the CV variants pipeline

> ✅ **Done 2026-09-17** — see commit 3296033 (`cv: simplify pipeline to two
> tailored-per-application base CVs`, merged in 138feb4). Verified against this plan's own
> checklist: `cv_functional.md`/`cv_chronological.md` both live in `jobs/cv/base/`,
> `jobs/cv/variants/` and `tools/build-all.sh` are gone, `CvVariant` remains only in migration
> history.

## Context

The repo has two CV pipelines. The one actually used day to day (confirmed by
`appfolder.pick_cv()`'s own docstring, decided 2026-09-08) is: a single functional CV
(`jobs/cv/base/cv_functional.md`) copied into each application folder, optionally tailored
per job by rewriting only its Core Competencies section
(`build-cv-variants.py --application`), then rendered to HTML/PDF/DOCX.

The other — five target-area YAMLs (`jobs/targets/*.yaml`) driving
`build-cv-variants.py --runall`/`--target` to generate full chronological CV rewrites via
the API into a stored library at `jobs/cv/variants/<area>/`, then `render.py --all` to
export all of them, chained by `tools/build-all.sh` — has had no consumer in the live
application workflow since that same 2026-09-08 decision. It kept running anyway
(`/jobs-search build-all`), accumulating ~30 dated `.md` files since June with nothing
downstream reading them for applications, plus real bit-rot: a broken
`from export import ...` (the module was renamed to `render.py` in June and never fixed),
two redundant no-VP mechanisms (a static file and a regex deriver, only the latter wired
in), and duplicated path/filename logic split across two files. It also fed a browsable
"CVs" section of the internal Django dashboard (`src/web/apps/cvs/`).

**Revised direction (per discussion):** don't reduce to one base format. Keep **two** base
CVs — functional (`cv_functional.md`) and chronological (`cv_base.md`, **renamed to
`cv_chronological.md`** for naming symmetry — see step 0) — as equally valid starting
points. Each application picks one (default **functional**, overridable) and gets a
**tailored final version generated at application time**, written straight into the
application folder. What goes away is the **pre-generated library**: no more calling
`--runall` across 5 target areas ahead of time and stockpiling dated files in
`jobs/cv/variants/`. Generation happens once, on demand, per application — which is what
already happens for the functional CV today; this plan extends the same on-demand model to
the chronological CV instead of retiring it.

One knock-on benefit: `jobs/targets/*.yaml`'s `tone`/`expand_sections`/`condense_sections`
fields — previously read only by the now-removed library generator and otherwise
unconsumed — become live inputs to the chronological per-application tailoring prompt
again, instead of vestigial. No schema changes needed to the targets or the Django `Area`
model.

## Changes

### 0. Rename `jobs/cv/base/cv_base.md` → `jobs/cv/base/cv_chronological.md`

`git mv` the file, for symmetry with `cv_functional.md` now that both are equal-standing
base formats — "cv_base" read oddly once it stopped being *the* base and became just one of
two. This ripples through every reference to the old path/stem, called out at each spot
below (`appfolder.py`'s `CHRONOLOGICAL_CV` constant, `build-cv-variants.py`'s base-CV
loader, the Django `BaseCv` slug/label, docs). Do the rename first so the rest of the plan
can just say "the chronological base."

### 1. `jobsdb` / Django `Application` model — where the base preference lives

`tracker/models.py` already has a legacy field, `cv_variant_label` (plain `CharField`,
`blank=True`), left over from the pre-database markdown era and not read by any live code
path today (checked: not referenced by `pick_cv`, `generate_functional`, or anything else).
Repurpose it rather than adding a second field:

- Rename `cv_variant_label` → `cv_base`, and turn it into a real choice field:
  `models.CharField(max_length=20, choices=[("functional", "Functional"), ("chronological", "Chronological")], default="functional")`.
- One migration: `RenameField` + `AlterField` (adds choices/default; old free-text values
  — leftover per-area labels from the retired library era — don't map to the new choices,
  so they reset to the new default, `"functional"`, which matches "unless otherwise noted"
  anyway).
- `admin.py`: update the `("Notes", {...})` fieldset reference from `cv_variant_label` to
  `cv_base`; optionally add it to `list_display`/`list_filter` for quick scanning.
- `templates/tracker/application_detail.html`: update `app.cv_variant_label` → `app.cv_base`
  (label "CV variant" → "CV base").
- `src/jobsdb.py::_app_dict()`: expose `"cv_base": a.cv_base` instead of `"cv": a.cv_variant_label`.

### 2. `src/build-cv-variants.py` — one generalized per-application tailoring path

Remove (library generation, as before): `generate_one`, `generate_no_vp`,
`strip_vp_section`, `save_variant`, `find_latest_variant`, `base_suffix`, `list_targets`,
`load_base_cv`, `ALL_BASES`, `CV_BASE_NO_VP`, `VARIANTS_DIR`, and the four broken
`from export import ...` lines. Remove CLI flags `--runall`, `--list/-l`, `--output/-o`,
`--no-vp`.

Keep and extend the `--application/--app` path:
- Keep `generate_functional`/`build_functional_prompt`/`split_competencies` as the
  functional branch, unchanged (still spliced — only Core Competencies is rewritten, so
  there's nothing else for the model to drift).
- Add a chronological branch, reusing `build_prompt()` (currently dead-ends at library
  generation) adapted to take **job_description** the way `build_functional_prompt` already
  does, instead of a static per-area canned `summary:`. It still draws on the same target
  YAML fields (`emphasis`, `key_terms`, `tone`, `expand_sections`, `condense_sections`,
  `description`) via `load_target_config(app["area"])`, plus the job posting text, and
  rewrites the **whole document** (reordered bullets, tailored summary) — unlike the
  functional branch, there's no single section to splice, so this mirrors the old
  `generate_one()` call shape but is driven by one application's job description instead of
  a fixed area profile, and is called once per application rather than once per area ahead
  of time.
- `--target`/`--base`/`-t`/`-b` flags are retired (no more "pick a base file, pick a target
  area" library invocation); replace with `--base {functional,chronological}` as an
  **override** for `--application`, defaulting to the application's stored `cv_base` field
  from step 1.
- Rename `src/prompts/cv_variant.md` → `src/prompts/cv_chronological_tailored.md` and adapt
  it to take `{company}`/`{role}`/`{job_description}` placeholders (mirroring
  `cv_functional_tailored.md`), dropping the "use this exact text verbatim" summary
  instruction in favour of "tailor the summary to this job, using the notes below as
  positioning guidance."
- Replace `load_base_cv()`/`CV_BASE` with a `CHRONOLOGICAL_CV = JOBS / "cv" / "base" / "cv_chronological.md"`
  constant (same renamed path as `appfolder.py`'s, step 3) — this is what the chronological
  branch reads as `{base_cv}` for the prompt above.
- Output for both branches lands only in the application folder via
  `appfolder.app_filename(folder, "cv-functional"|"cv-chronological", "md")` — never under
  `jobs/cv/variants/`.
- Keep `--dry-run`.

### 3. `src/appfolder.py` — pick either base, detect either tailored file

- `FUNCTIONAL_CV` stays as-is; add `CHRONOLOGICAL_CV = JOBS / "cv" / "base" / "cv_chronological.md"`
  (the renamed file from step 0).
- Generalize `is_tailored_functional_cv()` → `is_tailored_cv(name)`: matches
  `cv_functional`/`cv-functional` **or** `cv-chronological` in the name, excluding the
  untailored base copies (`cv_functional.md`, `cv_chronological.md`). (The existing
  docstring at line 87 already anticipated "or a chronological variant copy" — this was
  half-planned.)
- `pick_cv(row)`: if a tailored file of either kind already sits in the folder, return the
  newest one (unchanged logic, generalized predicate). Otherwise return the untailored base
  matching `row.get("cv_base", "functional")` — `CHRONOLOGICAL_CV` if `"chronological"`,
  else `FUNCTIONAL_CV`.
- `ensure_folder()`/`copy_cv()` need no changes — they already delegate to `pick_cv()`.

### 4. `src/render.py` — keep chronological rendering, drop the library plumbing

Keep (generalized, not removed as previously planned): `_parse_experience`,
`parse_variant`, `_r_job`, `_r_early_career`, `_r_publications`, `render_html`,
`cv_navy.html`, `export_docx_variant` (rename to `export_docx_chronological`) —
i.e. chronological rendering stays a first-class sibling of functional rendering.

Decouple it from the retired library:
- `parse_variant()` drops its `target_config` parameter (and the `target_subtitle` it fed —
  the navy template's tagline under the name). Chronological CVs are now single
  application-scoped files, not part of a named-target library, so there's no
  `jobs/targets/<area>.yaml` to look up a display name from.
- `export_html`/`export_pdf`/`export_docx_chronological` stop taking a `target` name +
  library lookup; like `export_functional`/`export_docx_functional` already do, they take a
  `--file` path directly.
- Remove: `find_latest_variant`, `_extract_suffix`, `--all`, `--no-vp` (no library to
  iterate), and the `TARGETS_DIR`/target-yaml coupling in this file.
- CLI becomes symmetric: `--functional` or `--chronological`, each combinable with
  `--file`, `--format`, `--docx`, `--label` — mirroring each other exactly.

### 5. `src/cv_docx.py` — no change

`build_chronological()` stays (previously slated for removal) — it already just takes a
parsed `data` dict + `out_path`, no library coupling to unwind.

### 6. Delete dead files (unchanged from before)

- `tools/build-all.sh` (chained only the retired library build)
- `jobs/cv/base/cv_base_no_vp.md` (still unreachable by any code path — `strip_vp_section`,
  its only would-be reader, is being removed; the no-VP mechanism isn't part of this
  redesign either — note this is the *old* no-VP file, distinct from the `cv_base.md` →
  `cv_chronological.md` rename in step 0)
- `jobs/cv/variants/` (all ~30 dated files — no reader left once the above lands; the new
  model never writes here)

Both `jobs/cv/base/cv_chronological.md` (renamed in step 0) and `cv_functional.md` are
kept — both are now live, equally-weighted base documents.

### 7. Django `cvs` app — drop `CvVariant`, keep `BaseCv` (unchanged from before)

`BaseCv` already models both the chronological and functional base files (its `LABELS`
dict has entries for both, keyed by file stem), so this part of the plan is unaffected by
the redesign, aside from following the step-0 rename through:

- `models.py` — remove `CvVariant`; update `BaseCv.LABELS`: drop the `cv_base_no_vp` entry,
  and rekey `"cv_base": ("Base CV", 0)` → `"cv_chronological": ("Chronological CV", 0)` to
  match the renamed file's new stem (`find_base_cvs()` in `parsers.py` keys `BaseCv.slug` off
  `md.stem`, so this follows automatically once the file is renamed — just needs the
  `LABELS` dict updated to match).
- `admin.py` — remove `CvVariantAdmin` and the `CvVariant` import.
- `views.py` — remove `cv_detail`; rewrite `cv_list` to just pass `BaseCv.objects.all()`.
- `urls.py` — remove the `<slug:slug>/<str:stamp>/` variant-detail route; keep `""` and
  `base/<slug>/`.
- `templates/cvs/cv_list.html` — keep only the "Master CVs" section.
- Delete `templates/cvs/cv_detail.html` and the unused placeholder `templates/cvs/list.html`.
- New migration dropping the `CvVariant` model/table.

### 8. Django `tracker` app — remove the other `CvVariant` touchpoints (unchanged)

- `models.py` — update the module docstring (drops "CvVariant" from the file-derived-models
  list).
- `admin.py` (`AreaAdmin`) — remove `cv_count`/`"cv_count"` from `list_display`, drop the
  `_cvs=Count("cv_variants", ...)` annotation.
- `views.py` (`area_list`) — drop the `n_cvs=Count("cv_variants", ...)` annotation.
- `context_processors.py` — nav "cvs" badge becomes `BaseCv.objects.count()` only.
- `management/commands/import_jobs.py` — remove `import_cv_variants()` and its call, the
  `CvVariant` import, and the docstring line.
- `management/commands/build_static.py` — remove the `CvVariant` URL-list comprehension and
  import.
- `parsers.py` — remove `find_cv_variants()` and `parse_cv_filename()`.
- `tests.py` — trim `test_every_cv_detail_renders` to the `BaseCv` loop only; delete
  `test_base_cv_route_beats_variant_route` (its route-ordering conflict no longer exists).

### 9. Skill docs (`.claude/skills/jobs-search/`)

- Delete `subcommands/build-all.md`.
- Rewrite `subcommands/render-html-pdf.md`: drop Mode A (render-all); Mode B branches on
  which tailored file is present in the folder — `cv-functional-*` → `render.py --functional`,
  `cv-chronological-*` → `render.py --chronological` — instead of inferring a target area
  from the filename.
- `SKILL.md`: remove `build-all`; update `render-html-pdf`'s description.
- `subcommands/application.md`: fix the stale `jobs/cv/variants/<area>/` references (Sources
  table, "CV variant" field row, "Read the CV variant copied into the folder") to describe
  the real flow — the untailored **functional** CV is copied by default at Step 5 unless the
  application's `cv_base` says chronological — and extend the "After review" section with the
  chronological tailoring option alongside the existing functional one.
- `subcommands/publish.md`: line 21 ("run `build-all` first") → point at rendering the
  specific application instead.

### 10. Docs and changelog

- Update `docs/cv-pipeline.md`, `docs/workflow.md`, `docs/applications-and-gap-analysis.md`,
  `docs/publishing.md` wherever they describe the retired library flow, to describe the
  two-base-CV, tailor-per-application model.
- Add a `CHANGELOG.md` entry. (`log/*.md` stays untouched — append-only history.)

### 11. Memory (after the change lands)

Update `project_cv_pipeline.md` to describe: two base CVs (functional default,
chronological opt-in via `cv_base`), tailored once per application into the app folder, no
stored variant library.

## Verification

- `python -m py_compile src/build-cv-variants.py src/render.py src/cv_docx.py src/appfolder.py`
- `build-cv-variants.py --application <ref> --dry-run` (functional, the default) and
  `--application <ref> --base chronological --dry-run` — confirm both prompts build
  correctly end to end.
- `render.py --functional --format html`, `--chronological --file <a chronological test file> --format html`, `--docx` variants of both, `--cover-letter --file ...` — confirm all render paths work.
- Django: `manage.py makemigrations tracker cvs` (review both generated migrations —
  especially the `cv_variant_label` → `cv_base` rename), `manage.py migrate`,
  `manage.py import_jobs`, `manage.py test`.
- Dev server: `/cvs/` shows both master CVs; `/cvs/base/cv_chronological/` (renamed slug)
  and `/cvs/base/cv_functional/` both render; `/applications/<n>/` shows the renamed "CV
  base" field; create/refresh a test application and confirm `pick_cv()` picks the right
  base by default and respects an explicit chronological override.
- Repo-wide sweep: `grep -rn "CvVariant\|cv/variants\|cv_variant_label\|cv_base\.md\|build-cv-variants.py --runall\|build-cv-variants.py --target" src/ .claude/ docs/` should return nothing outside `log/` and `CHANGELOG.md` history (note: `cv_base` the *field name* is intentional and expected to still match — only the old `cv_base.md` *filename* should be gone).
