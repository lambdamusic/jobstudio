"""Refresh the parts of the database that are still derived from files on disk.

Since Phase 6 the database owns applications and companies — this command no longer
touches them. What it still imports is everything whose truth lives in the filesystem:

  * Area          <- jobs/targets/*.yaml (config the CV generator reads directly)
  * BaseCv        <- jobs/cv/base/*.md
  * Scan          <- jobs/scans/*.md

Cover letters and per-application CV snapshots are NOT imported — they are scanned
straight from each application folder by naming convention at request time.

Safe to run any time; idempotent.

    manage.py import_jobs            # upsert
    manage.py import_jobs --quiet    # counts only
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from appfolder import slug as slugify_name
from cvs.models import BaseCv
from tracker import parsers as P
from tracker.models import Area, Scan


def rel(path: Path) -> str:
    """Path relative to the data root — what we store, so the DB survives a move."""
    return str(Path(path).resolve().relative_to(Path(settings.DATA_ROOT).resolve()))


class Stats:
    def __init__(self):
        self.created = self.updated = self.unchanged = self.deleted = 0

    def record(self, verb: str):
        setattr(self, verb, getattr(self, verb) + 1)

    @property
    def changed(self) -> int:
        return self.created + self.updated + self.deleted

    def __str__(self):
        return (f"{self.created} created, {self.updated} updated, "
                f"{self.unchanged} unchanged, {self.deleted} deleted")


def upsert(model, lookup: dict, defaults: dict, stats: Stats):
    """Create or update one row, reporting whether anything actually changed."""
    obj = model.objects.filter(**lookup).first()
    if obj is None:
        obj = model.objects.create(**lookup, **defaults)
        stats.record("created")
        return obj
    dirty = [f for f, v in defaults.items() if getattr(obj, f) != v]
    if dirty:
        for field in dirty:
            setattr(obj, field, defaults[field])
        obj.save(update_fields=dirty)
        stats.record("updated")
    else:
        stats.record("unchanged")
    return obj


def prune(model, keep_ids: set, stats: Stats):
    """Delete rows that no longer exist in the markdown — it is the source of truth."""
    stale = model.objects.exclude(pk__in=keep_ids)
    stats.deleted += stale.count()
    stale.delete()


class Command(BaseCommand):
    help = "Import jobs/*.md and jobs/targets/*.yaml into the sqlite read model."

    def add_arguments(self, parser):
        parser.add_argument("--quiet", action="store_true", help="Summary counts only")

    def handle(self, *args, **options):
        self.quiet = options["quiet"]
        root = Path(settings.DATA_ROOT)

        with transaction.atomic():
            self.import_areas(root)
            self.import_base_cvs(root)
            self.import_scans(root)

    # -- output ------------------------------------------------------------
    def say(self, msg: str):
        if not self.quiet:
            self.stdout.write(msg)

    def report(self, label: str, stats: Stats):
        style = self.style.SUCCESS if stats.changed else self.style.HTTP_NOT_MODIFIED
        self.stdout.write(style(f"  {label:16} {stats}"))

    # -- importers ---------------------------------------------------------
    def import_areas(self, root: Path) -> dict[str, Area]:
        stats = Stats()
        md = P.parse_areas_md(Path(settings.AREAS_MD))
        keep, areas = set(), {}
        for order, target in enumerate(P.parse_targets(Path(settings.TARGETS_DIR))):
            extra = md.get(target["slug"], {})
            area = upsert(
                Area, {"slug": target["slug"]},
                {
                    "name": target["name"],
                    "heading": extra.get("heading", ""),
                    "fit": extra.get("fit", 0),
                    "description": target["description"],
                    "notes": extra.get("notes", ""),
                    "emphasis": target["emphasis"],
                    "key_terms": target["key_terms"],
                    "expand_sections": target["expand_sections"],
                    "condense_sections": target["condense_sections"],
                    "order": order,
                },
                stats,
            )
            keep.add(area.pk)
            areas[area.slug] = area
        prune(Area, keep, stats)
        self.report("areas", stats)
        return areas

    def import_scans(self, root: Path):
        stats = Stats()
        keep = set()
        for scan in P.find_scans(Path(settings.SCANS_DIR)):
            obj = upsert(
                Scan, {"path": rel(scan["path"])},
                {"date": scan["date"], "label": scan["label"]},
                stats,
            )
            keep.add(obj.pk)
        prune(Scan, keep, stats)
        self.report("scans", stats)

    def import_base_cvs(self, root: Path):
        stats = Stats()
        keep = set()
        for cv in P.find_base_cvs(Path(settings.CV_DIR) / "base"):
            label, order = BaseCv.LABELS.get(
                cv["slug"], (cv["slug"].replace("_", " ").title(), 9))
            obj = upsert(
                BaseCv, {"slug": cv["slug"]},
                {
                    "label": label,
                    "path": rel(cv["path"]),
                    "is_functional": cv["is_functional"],
                    "order": order,
                },
                stats,
            )
            keep.add(obj.pk)
        prune(BaseCv, keep, stats)
        self.report("base CVs", stats)
