"""Per-application folder helpers — shared by the Django app and the jobstudio skills.

Module level stays Django-free (the web app imports the constants below, so importing
Django here would be circular). The CLI bootstraps the database lazily via jobsdb.

All application folders live directly under jobs/applications/ — there is no archive/
split by status (retired 2026-09-08: the database is the source of truth for status, so
"is this closed?" is answered by the web app, not by which directory a folder sits in).

CLI usage:
    python src/appfolder.py ensure <num|company>   # create folder if missing, print path
    python src/appfolder.py path   <num|company>   # print path only, no creation
"""

from __future__ import annotations

import re
import shutil
import sys
import unicodedata
from datetime import date
from pathlib import Path

import config
import identity

# Application folders are data, not code (config.py). DATA_ROOT is the repo itself
# until the split lands, so this is currently the same path as before.
DATA_ROOT = config.data_root()
APPS_DIR = DATA_ROOT / "jobs" / "applications"

# A company is either being watched, or has been applied to. Nothing else — the richer
# per-application statuses live in applications.md and would only drift here.
COMPANY_STATUS_APPLIED = "applied"
COMPANY_STATUS_WATCHING = "watching"
COMPANY_STATUSES = [COMPANY_STATUS_APPLIED, COMPANY_STATUS_WATCHING]

# Application statuses that mean an application was actually submitted (whatever happened
# next) — these are what flip a company to COMPANY_STATUS_APPLIED. `saved` and `reviewing`
# are pre-submission; `closed` means the deadline passed before applying; `discarded`
# means the role was dropped before applying. See docs/workflow.md "Application statuses".
COMPANY_APPLIED_TRIGGER_STATUSES = {"applied", "interviewing", "rejected"}

# Single source of truth for the "by status" sort, shared with the web app.
STATUS_SORT_ORDER = ["applied", "interviewing", "reviewing", "saved", "discarded", "closed", "rejected"]

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def slug(name: str) -> str:
    # Transliterate accents to ASCII first (Django's slugify(allow_unicode=False) does the
    # same) — otherwise `\w` is Unicode-aware and lets accented letters straight through,
    # producing a slug the `<slug:...>` URL converter's ASCII-only regex then 404s on.
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_]+", "-", name).strip("-")


def _folder_name(row: dict) -> str:
    return f"{str(row['num']).zfill(3)}-{slug(row['company'])}"


# ---------------------------------------------------------------------------
# File naming convention for application-specific CVs / cover letters
# (decided 2026-09-08) — applies only to files generated inside
# jobs/applications/NNN-*/, not the exports/ tree.
#
#   <application-folder-name>-<person-slug>-<filetype>-<YYYY-MM-DD>.<ext>
#
# The person-slug comes from identity.py (config.yaml, or the base CV's `# Name`
# heading) — never hardcoded. Recognition below deliberately does NOT key on it, so
# files written before the slug was configurable are still found.
#
# e.g. 001-grafana-labs-<person-slug>-cv-functional-2026-09-08.md
#      001-grafana-labs-<person-slug>-cover-letter-2026-09-08.docx
# ---------------------------------------------------------------------------

def app_filename(folder: Path, filetype: str, ext: str, when: date | None = None) -> str:
    """Build a filename following the application-folder naming convention above."""
    d = (when or date.today()).isoformat()
    return f"{folder.name}-{identity.slug()}-{filetype}-{d}.{ext}"


def app_folder_of(path: Path) -> Path | None:
    """If `path` lives inside jobs/applications/<folder>/ (at any depth), return that
    folder. Used to decide whether a rendered export should also be copied back in."""
    try:
        rel = path.resolve().relative_to(APPS_DIR.resolve())
    except ValueError:
        return None
    return APPS_DIR / rel.parts[0]


# ---------------------------------------------------------------------------
# Rendered exports inside an application folder (2026-09-24)
#
# The markdown in an application folder is authored; a .docx rendered from it is
# output. Keeping both at the top level made the folder read as a pile of files
# rather than a set of sources, so rendered copies go one level down:
#
#   jobs/applications/001-grafana-labs/
#     job.md, notes.md, ...-cv-....md, ...-cover-letter-....md   <- authored
#     export/
#       ...-cv-....docx, ...-cover-letter-....docx               <- rendered
#
# Folders written before this are NOT migrated, so every reader has to accept both
# shapes — which is why finding a rendered copy goes through `exported_file()`
# rather than `md.with_suffix(".docx")` at each call site.
# ---------------------------------------------------------------------------

EXPORT_DIRNAME = "export"


def export_dir(folder: Path) -> Path:
    """Where rendered copies go inside application folder `folder`.

    Singular, and per-application — not to be confused with `<DATA>/exports/<fmt>/<date>/`,
    the global export area every render writes to first (`render._export_dir()`).
    """
    return folder / EXPORT_DIRNAME


def is_rendered_export(folder: Path, name: str) -> bool:
    """Is `name`, sitting at the top level of application folder `folder`, a rendered
    copy that belongs in `export/`?

    Keyed on the naming convention — `<folder-name>-<person-slug>-<filetype>-<date>.<ext>`
    — rather than on "is there a matching .md next to it". A render done on a later day
    than the markdown it rendered is named for the render's date, so a quarter of the
    real ones have no same-stem sibling; a sibling test would leave exactly those behind.
    Anything a person saved into the folder by hand (a JD, a recruiter's PDF) doesn't
    carry the folder's own name as a prefix, and so is left where it was put.
    """
    return (not name.startswith(".") and not name.endswith(".md")
            and name.startswith(f"{folder.name}-"))


_DATE_IN_NAME_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def document_kind(name: str) -> str | None:
    """"cv" or "cover-letter" for a file following the naming convention, else None.

    Coarser than the `<filetype>` in the name itself, deliberately: a tailored CV is
    named after the target area (`...-cv-developer-advocacy-...`) while the .docx
    rendered from it is named after the base it came from (`...-cv-functional-...`), so
    the exact token is not something the two ever agree on. Reuses `is_cv_filename()`
    by asking it about the stem, rather than restating its rules for a second extension.
    """
    if is_cover_letter_filename(name):
        return "cover-letter"
    if is_interview_filename(name):
        return None  # nothing renders these; kept explicit so `-cv-` can't be read into one
    return "cv" if is_cv_filename(f"{Path(name).stem}.md") else None


def exported_file(md_path: Path, ext: str = "docx") -> Path | None:
    """The rendered copy of `md_path` — in `export/`, or beside it for folders written
    before 2026-09-24 — or None when there isn't one.

    Falls back to the newest export of the same kind when no name matches exactly. It
    often won't: the copy is named with the date of the *render* (`app_filename()`), so
    rendering a letter written last week produces a stem its source does not share, and
    a quarter of the exports in one real job search were orphaned this way. The fallback
    holds off when the folder has more than one markdown of that kind — then which
    export belongs to which source is a guess, and a wrong link is worse than none.
    """
    folder = app_folder_of(md_path) or md_path.parent
    beside = md_path.with_suffix(f".{ext}")
    for candidate in (export_dir(folder) / beside.name, beside):
        if candidate.is_file():
            return candidate

    kind = document_kind(md_path.name)
    if kind is None:
        return None
    if sum(1 for p in folder.glob("*.md") if document_kind(p.name) == kind) != 1:
        return None
    def by_date_then_name(path: Path) -> tuple[str, str]:
        m = _DATE_IN_NAME_RE.search(path.name)
        return (m.group(0) if m else "", path.name)

    same_kind = sorted((p for p in export_dir(folder).glob(f"*.{ext}")
                        if document_kind(p.name) == kind), key=by_date_then_name)
    return same_kind[-1] if same_kind else None


def is_tailored_cv(name: str) -> bool:
    """A per-application tailored CV — anything `is_cv_filename()` recognises except
    the two untailored starting copies.

    Tailored CVs are named after the *target area*, not after the base they came from:
    `004-<company>-<person-slug>-cv-<area-slug>-2026-06-23.md`. An earlier
    version of this matched only `cv-functional` / `cv-chronological` / `cv_functional`,
    so half of them were invisible — 15 of 30 in one real job search when this was found —
    and `pick_cv()` fell back to the untailored base for those applications.
    """
    if name in ("cv_functional.md", "cv_chronological.md"):
        return False
    return is_cv_filename(name)


def cv_variant(name: str) -> str:
    """The target-area slug a tailored CV was named after — the `<area-slug>` in
    `004-<company>-<person-slug>-cv-<area-slug>-2026-06-23.md`, or the `<target>` in the
    old `<date>_cv_<target>.md`. Returns "" when the name carries no variant at all.

    Used for labelling a CV in a list where the filename alone is noise. Matches the
    LAST `cv-`/`cv_` in the name, not the first: a company slug can legitimately contain
    one (CV-Library is a real UK employer), and the leftmost match would then label every
    CV of theirs with the rest of their own name.
    """
    stem = re.sub(r"\d{4}-\d{2}-\d{2}", "", Path(name).stem).strip("-_ ")
    m = re.match(r"^.*cv[-_](.+)$", stem)
    return m.group(1).strip("-_ ") if m else ""


def is_cv_filename(name: str) -> bool:
    """Any CV-related markdown file in an application folder, old or new naming."""
    return name.endswith(".md") and (
        name == "cv_functional.md"
        or (name.startswith(("cv_", "20")) and "cv_" in name)  # old: <date>_cv_<target>.md
        or "-cv-" in name  # new: <application-id>-<person-slug>-cv-<...>-<date>.md
    )


def is_cover_letter_filename(name: str) -> bool:
    """A cover-letter file, old naming (`cover-letter-<date>.md`) or new
    (`<application-id>-<person-slug>-cover-letter-<date>.<ext>`)."""
    return "cover-letter" in name


# ---------------------------------------------------------------------------
# Interview rounds (2026-09-24)
#
# One file per round, not one per process: each round has its own interviewer,
# its own emphasis, and its own outcome, and the prep for round N+1 is driven by
# the outcome of round N. They used to be packed into notes.md under a single
# `## Interview prep` heading, which put prep, outcome and timeline for one round
# in three places and pushed one real folder to 63% interview content.
#
#   <application-folder-name>-<person-slug>-interview-<stage>-<YYYY-MM-DD>.md
#
# e.g. 001-grafana-labs-<person-slug>-interview-hiring-manager-2026-09-24.md
#
# The date is the date of the INTERVIEW, not the date the file was written —
# unlike CVs and cover letters, where it is the creation date. That is what makes
# `parse_date()` on the filename a real chronology and a real "what's next".
#
# Built with app_filename(folder, f"interview-{stage}", "md", when=<interview date>);
# no separate builder, so the one convention keeps one implementation.
# ---------------------------------------------------------------------------

# The stages `/jobstudio interview --stage` accepts, and the order a process runs in.
INTERVIEW_STAGES = ["hr-screen", "hiring-manager", "technical", "panel", "final", "informal"]

_INTERVIEW_STAGE_LABELS = {
    "hr-screen": "HR screen",
    "hiring-manager": "Hiring manager",
    "technical": "Technical",
    "panel": "Panel",
    "final": "Final round",
    "informal": "Informal chat",
}


def is_interview_filename(name: str) -> bool:
    """An interview-round file — `<application-id>-<person-slug>-interview-<stage>-<date>.md`,
    or a bare `interview-<stage>-<date>.md` written by hand."""
    return name.endswith(".md") and ("-interview-" in name or name.startswith("interview-"))


def interview_stage(name: str) -> str:
    """The `<stage>` slug an interview file was named after, or "" when it carries none
    (`...-interview-2026-09-24.md`). Matches up to the date, so a multi-word stage like
    `hiring-manager` survives intact."""
    m = re.search(r"interview-(.*?)-?(\d{4}-\d{2}-\d{2})", Path(name).stem)
    return m.group(1).strip("-_ ") if m else ""


def interview_label(stage: str) -> str:
    """Display name for a stage slug — known stages get real capitalisation, anything
    else is de-slugified rather than rejected, so a hand-named round still reads."""
    if not stage:
        return "Interview"
    return _INTERVIEW_STAGE_LABELS.get(stage, stage.replace("-", " ").capitalize())


def app_folder(row: dict) -> Path:
    """Canonical folder location for this row."""
    return APPS_DIR / _folder_name(row)


def existing_folder(row: dict) -> Path | None:
    """This application's folder, if it's been created yet, else None."""
    candidate = app_folder(row)
    return candidate if candidate.is_dir() else None


def has_folder(row: dict) -> bool:
    return existing_folder(row) is not None


# ---------------------------------------------------------------------------
# Folder creation
# ---------------------------------------------------------------------------

def notes_stub(row: dict) -> str:
    """Skeleton notes.md for a new application folder.

    Deliberately carries no metadata header: company/role/area/URL/status live in the
    database and used to be duplicated here, in the applications.md table, and in its
    detail block — three copies that drifted apart. This file is for prose only.
    (applications.md was retired in Phase 6.)

    No `## Interview prep` heading either, since 2026-09-24: interview rounds are their
    own files (see the naming block above). What stays here is what is true of the *role*
    rather than of a meeting — the notes, the contacts, and a timeline that indexes the
    round files.
    """
    return (
        f"# {row['company']} — {row['role']}\n\n"
        "## My notes\n\n\n"
        "## Contacts\n\n\n"
        "## Timeline\n"
    )


FUNCTIONAL_CV = DATA_ROOT / "jobs" / "cv" / "base" / "cv_functional.md"
CHRONOLOGICAL_CV = DATA_ROOT / "jobs" / "cv" / "base" / "cv_chronological.md"


def pick_cv(row: dict) -> Path | None:
    """Return the CV to put in this application's folder.

    There are two base CVs — functional (default) and chronological — chosen per
    application via its `cv_base` field. Either is tailored per job by the agent-native
    `cv` skill subcommand (`.claude/skills/jobstudio/subcommands/cv.md`), which writes
    a tailored copy straight into the application folder (never into a pre-generated
    library). Once a tailored copy exists it wins. Until then the folder gets the
    untailored base matching `row["cv_base"]` as a starting point.
    """
    folder = existing_folder(row)
    if folder is not None:
        tailored = sorted((p for p in folder.glob("*.md") if is_tailored_cv(p.name)),
                          reverse=True)
        if tailored:
            return tailored[0]
    base = CHRONOLOGICAL_CV if row.get("cv_base") == "chronological" else FUNCTIONAL_CV
    return base if base.is_file() else None


def copy_cv(row: dict, folder: Path) -> Path | None:
    """Copy the selected CV variant into the app folder. Return destination path or None."""
    src = pick_cv(row)
    if src is None:
        return None
    dest = folder / src.name
    shutil.copy2(src, dest)
    return dest


def ensure_folder(row: dict) -> Path:
    """Create the application folder, notes.md, an untailored CV copy, and an empty
    cover-letter stub, for whatever doesn't already exist. Return the folder path.

    This is scaffolding only — the plain functional CV plus a blank cover-letter file.
    Tailoring the CV and drafting the cover letter are separate agent-native steps
    (`subcommands/cv.md`, `subcommands/cover-letter.md`) that the `application` skill
    subcommand now runs automatically right after this, as part of logging (revised
    2026-09-17 — previously deferred until the user asked for them explicitly).
    """
    folder = app_folder(row)
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / "notes.md").exists():
        (folder / "notes.md").write_text(notes_stub(row))
    # Copy CV if no CV file is present yet (folder may pre-date CV copy feature)
    cv_src = pick_cv(row)
    if cv_src and not (folder / cv_src.name).exists():
        shutil.copy2(cv_src, folder / cv_src.name)
    # Empty cover-letter stub — content is written later, on request
    if not any(is_cover_letter_filename(p.name) for p in folder.iterdir()):
        (folder / app_filename(folder, "cover-letter", "md")).touch()
    return folder


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import jobsdb

    if len(sys.argv) < 3 or sys.argv[1] not in ("ensure", "path"):
        print(__doc__.strip())
        sys.exit(1)

    cmd, ref = sys.argv[1], sys.argv[2]
    row = jobsdb.find_application(ref)
    if row is None:
        print(f"Error: no application found for '{ref}'", file=sys.stderr)
        sys.exit(1)

    if cmd == "ensure":
        folder = ensure_folder(row)
        # Stored relative to the data root; models.Application.folder_path rejoins it
        # against settings.DATA_ROOT, so the two must agree.
        jobsdb.set_folder(row["num"], str(folder.relative_to(DATA_ROOT)))
    else:
        folder = existing_folder(row) or app_folder(row)

    print(folder)
