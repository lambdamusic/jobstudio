"""One-off: give every application a `saved` entry, so the funnel starts where it should.

Applications logged before the status log existed, or logged straight into the status they
were already in, entered the tracker at `closed`, `applied`, `rejected` — anywhere. That is
what actually happened, and until 2026-09-28 the flow diagram drew it faithfully: one entry
ribbon per status. But it is an artefact of how the tracker was used while it was being
built, not a real difference between those applications and the rest. Every one of them was
saved first; nobody applies to a role they never looked at.

So this rewrites that history deliberately, once:

    for each application whose earliest recorded status is not `saved`
        insert a `saved` entry one day before it
        and point the old first change at it, so it becomes a transition

`--dry-run` first. This is the one command here that *edits* existing rows rather than
adding to them, so it prints every change and refuses to guess: an application with no
recorded history at all is reported and left alone, because there is nothing to date the
new row from.

Idempotent — an application whose earliest status is already `saved` is skipped — so
re-running it is a no-op.

    manage.py backfill_saved_entry --dry-run
    manage.py backfill_saved_entry
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from tracker.models import Application, ApplicationStatusChange


class Command(BaseCommand):
    help = "Give every application a `saved` entry, dated the day before its first status."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Print what would change and write nothing")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        fixed = skipped = empty = 0

        with transaction.atomic():
            for app in Application.objects.order_by("num"):
                changes = list(app.status_changes.order_by("changed_at", "pk"))
                if not changes:
                    empty += 1
                    self.stderr.write(self.style.WARNING(
                        f"  #{app.num} {app.company_name}: no recorded history — left alone"))
                    continue
                first = changes[0]
                if first.to_status == "saved":
                    skipped += 1
                    continue

                when = first.changed_at - timedelta(days=1)
                self.stdout.write(
                    f"  #{app.num} {app.company_name}: "
                    f"saved on {when:%Y-%m-%d} -> {first.to_status} on {first.changed_at:%Y-%m-%d}")
                if not dry:
                    ApplicationStatusChange.objects.create(
                        application=app, changed_at=when, from_status="", to_status="saved")
                    first.from_status = "saved"
                    first.save(update_fields=["from_status"])
                fixed += 1

            if dry:
                transaction.set_rollback(True)

        verb = "would gain" if dry else "gained"
        self.stdout.write(self.style.SUCCESS(
            f"\n{fixed} application(s) {verb} a `saved` entry; {skipped} already had one"
            + (f"; {empty} have no history at all" if empty else "")))
        if dry:
            self.stdout.write("Dry run — nothing was written.")
