"""One-off: seed an ApplicationStatusChange row for applications that predate the model
(added 2026-09-08). Every save from now on logs itself via the post_save signal in
models.py — this just gives applications that already existed a starting point, dated
from Application.date (the day it was logged) rather than "now", since that's the closest
honest approximation of history we have.

Safe to re-run: skips any application that already has a status_changes row.

    manage.py backfill_status_history
"""

from datetime import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.models import Application, ApplicationStatusChange


class Command(BaseCommand):
    help = "Seed one ApplicationStatusChange per application that has no history yet."

    def handle(self, *args, **options):
        created = 0
        for app in Application.objects.all():
            if app.status_changes.exists():
                continue
            when = (timezone.make_aware(timezone.datetime.combine(app.date, time()))
                   if app.date else timezone.now())
            ApplicationStatusChange.objects.create(
                application=app, changed_at=when, from_status="", to_status=app.status)
            created += 1
        self.stdout.write(self.style.SUCCESS(
            f"Done. {created}/{Application.objects.count()} applications seeded."))
