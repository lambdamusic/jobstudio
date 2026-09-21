"""Recompute every company's derived status from its applications.

refresh_company_status() normally runs off Application post_save/post_delete signals, so
this is only needed after the derivation rule itself changes (as it did 2026-09-08 — see
COMPANY_APPLIED_TRIGGER_STATUSES in appfolder.py) or after a bulk edit that bypassed
signals (e.g. a raw QuerySet.update()).

    manage.py refresh_company_status
"""

from django.core.management.base import BaseCommand

from tracker.models import Company, refresh_company_status


class Command(BaseCommand):
    help = "Recompute Company.status for every company from its applications."

    def handle(self, *args, **options):
        changed = 0
        for company in Company.objects.all():
            before = company.status
            refresh_company_status(company)
            after = Company.objects.get(pk=company.pk).status
            if after != before:
                changed += 1
                self.stdout.write(f"  {company.name}: {before} -> {after}")
        self.stdout.write(self.style.SUCCESS(
            f"Done. {changed}/{Company.objects.count()} companies changed."))
