"""One-off: empty the global exports/ tree of everything that now has a home.

Until 2026-09-24 every render was written to `exports/<fmt>/<date>/` and an application's
.docx was *then* copied back into its folder — two copies of each file, and a flat dated
tree whose filenames name neither the source nor, half the time, the application. Renders
go straight to their home now (`render._home()`), so what is left in `exports/` is a
backlog. This clears it:

  * a render labelled with an application (`..._001-grafana-labs.pdf`) moves into that
    application's export/ under the folder naming convention, keeping the date it was
    rendered on — unless an identical file is already there, in which case it is deleted
  * the newest .docx of each base CV moves to jobs/cv/export/
  * every other render is deleted: superseded base renders, unlabelled ones that cannot
    be attributed to any application, and the retired variant library
  * anything that is NOT a render this tool made is listed and left alone — `exports/`
    stays the home for documents belonging to no folder, like a career stocktake

Reports what it would do and changes nothing unless `--apply` is passed. Safe to re-run.

    manage.py prune_exports            # show the plan
    manage.py prune_exports --apply    # move and delete
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

import appfolder

# `<YYYY-MM-DD>_<body>.<ext>` is what every render was named; `<body>` ends in the
# application folder name when the render was given a --label.
RENDER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")
LABEL_RE = re.compile(r"^(.*)_(\d{3}-[a-z0-9-]+)$")
BASE_CVS = ("cv_functional", "cv_chronological")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Command(BaseCommand):
    help = "Move exports that belong somewhere into that place; delete the rest."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Actually move and delete (default: show the plan only).")

    def handle(self, *args, **options):
        data_root = Path(settings.DATA_ROOT)
        exports = data_root / "exports"
        apps_dir = data_root / "jobs" / "applications"
        cv_export = data_root / "jobs" / "cv" / "export"
        if not exports.is_dir():
            self.stdout.write(self.style.HTTP_NOT_MODIFIED(f"No exports tree at {exports}"))
            return

        files = sorted(p for p in exports.rglob("*")
                       if p.is_file() and not p.name.startswith("."))
        moves: list[tuple[Path, Path, str]] = []
        deletes: list[tuple[Path, str]] = []
        keeps: list[Path] = []
        base_renders: dict[tuple[str, str], list[tuple[str, Path]]] = defaultdict(list)

        for path in files:
            m = RENDER_RE.match(path.stem)
            if not m:
                keeps.append(path)          # not something a render wrote
                continue
            when, body = m.groups()
            ext = path.suffix.lstrip(".")

            labelled = LABEL_RE.match(body)
            if labelled:
                body, label = labelled.groups()
                folder = apps_dir / label
                if not folder.is_dir():
                    keeps.append(path)      # labelled for an application that isn't there
                    continue
                dest_dir = appfolder.export_dir(folder)
                already = {digest(q) for q in dest_dir.glob("*") if q.is_file()}
                if digest(path) in already:
                    deletes.append((path, f"identical copy already in {label}/export/"))
                else:
                    dest = dest_dir / appfolder.app_filename(
                        folder, body.replace("_", "-"), ext, when=date.fromisoformat(when))
                    moves.append((path, dest, label))
                continue

            if body in BASE_CVS:
                base_renders[(body, ext)].append((when, path))
                continue

            deletes.append((path, "no application, and nothing else references it"))

        # Of each base CV only the newest .docx is worth keeping: the others are earlier
        # renders of the same file, and jobs/cv/base/archive/ already keeps that history
        # as markdown. HTML and PDF of a base CV go entirely — .docx is the format that
        # gets sent.
        for (body, ext), renders in sorted(base_renders.items()):
            renders.sort()
            for when, path in renders:
                keep = ext == "docx" and (when, path) == renders[-1]
                if keep:
                    moves.append((path, cv_export / f"{body}-{when}.{ext}", "base CV"))
                else:
                    deletes.append((path, f"superseded {body} render"))

        self._report(moves, deletes, keeps, data_root, options["apply"])

    def _report(self, moves, deletes, keeps, data_root, apply):
        def rel(p: Path) -> str:
            return str(p.relative_to(data_root))

        if moves:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n{'MOVING' if apply else 'WOULD MOVE'} {len(moves)} file(s) to where they belong"))
            for src, dest, why in sorted(moves, key=lambda m: (m[2], m[0].name)):
                if dest.exists():
                    self.stdout.write(self.style.WARNING(f"  skip  {rel(src)}  ({rel(dest)} exists)"))
                    continue
                self.stdout.write(f"  {rel(src)}\n      -> {rel(dest)}")
                if apply:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    src.rename(dest)

        if deletes:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n{'DELETING' if apply else 'WOULD DELETE'} {len(deletes)} file(s)"))
            by_reason = defaultdict(list)
            for path, why in deletes:
                by_reason[why].append(path)
            for why, paths in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
                self.stdout.write(f"  {len(paths):3}  {why}")
                for path in sorted(paths)[:3]:
                    self.stdout.write(self.style.HTTP_NOT_MODIFIED(f"         e.g. {rel(path)}"))
                if apply:
                    for path in paths:
                        path.unlink()

        if keeps:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nLEAVING ALONE {len(keeps)} file(s) — not a render, so not this command's to move"))
            for path in sorted(keeps):
                self.stdout.write(f"  {rel(path)}")

        if apply:
            removed = self._prune_empty_dirs(data_root / "exports")
            self.stdout.write(self.style.SUCCESS(
                f"\n{len(moves)} moved, {len(deletes)} deleted, {len(keeps)} left alone"
                f"; {removed} empty director(ies) removed"))
        else:
            self.stdout.write(self.style.WARNING(
                f"\n{len(moves)} to move, {len(deletes)} to delete, {len(keeps)} to leave alone. "
                "Nothing was written — re-run with --apply."))

    def _prune_empty_dirs(self, root: Path) -> int:
        """Date folders emptied by the pass above, deepest first. `root` itself stays:
        it is still where a render with no home goes."""
        removed = 0
        for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
                removed += 1
        return removed
