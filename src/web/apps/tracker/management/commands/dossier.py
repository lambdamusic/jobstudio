"""Everything in an application's Documents index, as one .docx to read (`#98`).

    manage.py dossier 1                   # into the application's export/ folder
    manage.py dossier 1 4 --out ~/tmp     # one file each, somewhere else

The file is named like the folder's other documents, with the time of the export
added (`001-grafana-labs-<you>-dossier-2026-11-09-1042.docx`), so a rerun never
overwrites an earlier dossier.
See `tracker/dossier.py` for what goes in.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

import appfolder
from tracker import dossier
from tracker.models import Application


class Command(BaseCommand):
    help = "Write an application's documents into one .docx for reading."

    def add_arguments(self, parser):
        parser.add_argument("nums", nargs="+", help="Application numbers (1 or #1).")
        parser.add_argument("--out", help="Folder to write to (default: the application's export/).")

    def handle(self, *args, **options):
        for ref in options["nums"]:
            num = ref.lstrip("#")
            app = Application.objects.filter(num=num).first() if num.isdigit() else None
            if app is None:
                raise CommandError(f"No application {ref}")
            folder = app.folder_path
            if folder is None:
                raise CommandError(f"{app} has no folder")
            out_dir = Path(options["out"]).expanduser() if options["out"] else appfolder.export_dir(folder)
            now = datetime.now()
            name = appfolder.app_filename(folder, "dossier", "docx", when=now.date())
            out = out_dir / name.replace(".docx", f"-{now:%H%M}.docx")
            titles = dossier.build(app, out)
            self.stdout.write(f"{out} ({len(titles)} sections)")
            for title in titles:
                self.stdout.write(f"  {title}")
