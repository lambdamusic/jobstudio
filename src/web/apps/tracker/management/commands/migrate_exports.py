"""One-off: move rendered exports into each application folder's export/ subfolder.

Since 2026-09-24 a .docx rendered from a tailored CV or a cover letter is written to
`jobs/applications/NNN-<company>/export/` rather than flat beside the markdown it came
from (TODO #35). Readers accept both shapes — `appfolder.exported_file()` checks
`export/` and then the flat location — so folders written before that date keep working
untouched. This tidies them anyway, so one data root has one layout.

What moves: top-level files following the application-folder naming convention that are
not markdown (`appfolder.is_rendered_export()`). What stays: every .md, dotfiles, files
already in a subfolder, and anything saved into the folder by hand — a JD, a recruiter's
PDF — which doesn't carry the folder's own name as a prefix.

Reports what it would do and changes nothing unless `--apply` is passed; a name already
taken in export/ is reported and skipped rather than overwritten. Safe to re-run.

    manage.py migrate_exports            # show the plan
    manage.py migrate_exports --apply    # move the files
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

import appfolder


class Command(BaseCommand):
    help = "Move flat rendered exports into each application folder's export/ subfolder."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Actually move the files (default: show the plan only).")

    def handle(self, *args, **options):
        apply = options["apply"]
        apps_dir = Path(settings.DATA_ROOT) / "jobs" / "applications"
        if not apps_dir.is_dir():
            self.stderr.write(self.style.ERROR(f"No application folders at {apps_dir}"))
            return

        moved = skipped = 0
        folders = 0
        for folder in sorted(p for p in apps_dir.iterdir() if p.is_dir()):
            pending = sorted(p for p in folder.iterdir()
                             if p.is_file() and appfolder.is_rendered_export(folder, p.name))
            if not pending:
                continue
            folders += 1
            self.stdout.write(f"  {folder.name}/")
            dest_dir = appfolder.export_dir(folder)
            for src in pending:
                dest = dest_dir / src.name
                if dest.exists():
                    self.stdout.write(self.style.WARNING(
                        f"      skip  {src.name}  (already in {appfolder.EXPORT_DIRNAME}/)"))
                    skipped += 1
                    continue
                if apply:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    src.rename(dest)
                self.stdout.write(f"      {'move' if apply else 'would move'}  {src.name}")
                moved += 1

        if not folders:
            self.stdout.write(self.style.HTTP_NOT_MODIFIED(
                "Nothing to migrate — every export is already in an export/ subfolder."))
            return

        summary = (f"{moved} file(s) {'moved' if apply else 'to move'} "
                   f"across {folders} folder(s)"
                   + (f", {skipped} skipped" if skipped else ""))
        if apply:
            self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.WARNING(
                f"{summary}. Nothing was written — re-run with --apply."))
