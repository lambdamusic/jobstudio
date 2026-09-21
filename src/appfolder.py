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
    """
    return (
        f"# {row['company']} — {row['role']}\n\n"
        "## My notes\n\n\n"
        "## Interview prep\n\n\n"
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
