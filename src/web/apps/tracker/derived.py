"""Keep the file-derived rows in step with the files they come from.

`Area`, `BaseCv` and `Scan` are a read model: the truth is on disk
(`jobs/targets/*.yaml`, `jobs/cv/base/*.md`, `jobs/scans/*.md`) and
`manage.py import_jobs` copies it into sqlite. Anything that *writes* one of
those files therefore has to remember to re-import, and on 2026-09-29 something
didn't: `init` runs `import_jobs` at the end of its own run, but on-ramp B
writes the base CVs afterwards, so `/cvs/` came up empty on a first install with
no error anywhere to explain it (see log/2026-09-29-second-machine-findings.md).

Rather than add the call to one more write site and wait for the next one to
forget, the read model repairs itself: the list views call `ensure_fresh()`,
which compares what is on disk against what is in the table and re-imports only
when they differ. The comparison is a directory listing and a handful of mtimes,
so the common case — nothing changed — costs nothing worth measuring.

This is the same bargain the CV page already makes for tailored CVs, which have
no rows at all and are read off disk on every request.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.core.management import call_command

from cvs.models import BaseCv
from tracker import parsers as P
from tracker.models import Area, Scan

log = logging.getLogger(__name__)


def _disk_state(paths: list[Path]) -> set[tuple[str, int]]:
    out = set()
    for p in paths:
        try:
            out.add((p.name, int(p.stat().st_mtime)))
        except OSError:      # vanished between listing and stat
            continue
    return out


def _sources(model) -> list[Path]:
    if model is BaseCv:
        return [cv["path"] for cv in P.find_base_cvs(Path(settings.CV_DIR) / "base")]
    if model is Area:
        d = Path(settings.TARGETS_DIR)
        return sorted(d.glob("*.yaml")) if d.is_dir() else []
    if model is Scan:
        d = Path(settings.SCANS_DIR)
        return sorted(d.glob("*.md")) if d.is_dir() else []
    raise ValueError(model)


# Row counts and file mtimes from the last check, per model. A process-local
# cache: a stale one costs an extra import, never a wrong page.
_seen: dict[str, tuple] = {}


def ensure_fresh(*models) -> bool:
    """Re-import if any of these models has drifted from its files. Returns whether
    an import ran.

    Best-effort by design: a page that cannot re-import should still render the
    rows it has, the same way a scan report is still written when its own refresh
    fails.
    """
    stale = False
    for model in models or (Area, BaseCv, Scan):
        try:
            state = (_disk_state(_sources(model)), model.objects.count())
        except Exception:
            log.warning("could not read %s's source files; leaving its rows alone",
                        model.__name__, exc_info=True)
            continue
        if _seen.get(model.__name__) != state:
            _seen[model.__name__] = state
            stale = True

    if not stale:
        return False
    try:
        call_command("import_jobs", quiet=True)
    except Exception:
        # Render what we have rather than 500 the page — but say so, loudly
        # enough to find. A silent no-op here recreates the empty-CV-page bug
        # this module was written to retire.
        log.warning("import_jobs failed; the page may be showing stale rows",
                    exc_info=True)
        return False
    # The import may have changed row counts; re-read so the next call compares
    # against what actually landed rather than re-importing forever.
    for model in models or (Area, BaseCv, Scan):
        try:
            _seen[model.__name__] = (_disk_state(_sources(model)), model.objects.count())
        except Exception:
            _seen.pop(model.__name__, None)
    return True
