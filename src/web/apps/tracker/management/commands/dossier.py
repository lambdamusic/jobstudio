"""Everything in an application's Documents index, as one .docx to read (`#98`).

    manage.py dossier 1                   # into the application's export/ folder
    manage.py dossier 1 4 --out ~/tmp     # one file each, somewhere else

The file is named like the folder's other documents
(`001-grafana-labs-<you>-dossier-2026-11-09.docx`), so a rerun the same day replaces it.
See `tracker/dossier.py` for what goes in.
"""

from __future__ import annotations

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
            out = out_dir / appfolder.app_filename(folder, "dossier", "docx")
            titles = dossier.build(app, out)
            self.stdout.write(f"{out} ({len(titles)} sections)")
            for title in titles:
                self.stdout.write(f"  {title}")
