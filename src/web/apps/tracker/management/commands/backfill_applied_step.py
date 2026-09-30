"""One-off: give an `applied` step to applications that were rejected or interviewed
without ever being recorded as applied.

Applications logged before the status log existed were backfilled as `saved -> rejected`
or `saved -> interviewing`, skipping the submission in between. Nobody is interviewed or
rejected for a role they never applied to, so the step is certain, and without it the
"from applied onward" flow view leaves these applications out entirely (#56).

`closed` does not count: a role can be closed by the employer before or after applying,
so that one is Michele's call per application, not this command's.

The dates: the backfilled rows sit exactly one day apart at local midnight, which is how
the stock chart knows they are reconstructed. There is no free midnight between `saved`
and the next step, so the synthetic `saved` row (itself added by `backfill_saved_entry`)
moves back one day and `applied` takes its old moment, one day after the new `saved`:

    saved (D-1) -> rejected (D)   becomes   saved (D-2) -> applied (D-1) -> rejected (D)

Everything stays on a midnight, so the new row is still read as reconstructed history.

`--dry-run` first. It edits existing rows, so it refuses to guess: an application whose
step before the submission-implying status is not its very first, `saved` row is
reported and left alone. Idempotent — an application that already reached `applied` is
skipped.

    manage.py backfill_applied_step --dry-run
    manage.py backfill_applied_step
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import localtime

from tracker.models import Application, ApplicationStatusChange

# Statuses that cannot be reached without having applied first.
IMPLIES_APPLIED = ("interviewing", "rejected")


class Command(BaseCommand):
    help = "Insert the missing `applied` step before an interview or a rejection."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Print what would change and write nothing")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        fixed = unsure = 0

        with transaction.atomic():
            for app in Application.objects.order_by("num"):
                changes = list(app.status_changes.order_by("changed_at", "pk"))
                statuses = [c.to_status for c in changes]
                if "applied" in statuses:
                    continue
                first_implied = next((i for i, s in enumerate(statuses)
                                      if s in IMPLIES_APPLIED), None)
                if first_implied is None:
                    continue

                later = changes[first_implied]
                if first_implied != 1 or statuses[0] != "saved":
                    unsure += 1
                    self.stderr.write(self.style.WARNING(
                        f"  #{app.num} {app.company_name}: {' -> '.join(statuses)} — "
                        f"not a plain saved -> {later.to_status}, left alone"))
                    continue

                saved = changes[0]
                applied_at = saved.changed_at
                saved_at = applied_at - timedelta(days=1)
                self.stdout.write(
                    f"  #{app.num} {app.company_name}: saved {localtime(saved_at):%Y-%m-%d} -> "
                    f"applied {localtime(applied_at):%Y-%m-%d} -> {later.to_status} "
                    f"{localtime(later.changed_at):%Y-%m-%d}")
                if not dry:
                    saved.changed_at = saved_at
                    saved.save(update_fields=["changed_at"])
                    ApplicationStatusChange.objects.create(
                        application=app, changed_at=applied_at,
                        from_status="saved", to_status="applied")
                    later.from_status = "applied"
                    later.save(update_fields=["from_status"])
                fixed += 1

            if dry:
                transaction.set_rollback(True)

        verb = "would gain" if dry else "gained"
        self.stdout.write(self.style.SUCCESS(
            f"\n{fixed} application(s) {verb} an `applied` step"
            + (f"; {unsure} left alone, see above" if unsure else "")))
        if dry:
            self.stdout.write("Dry run — nothing was written.")
