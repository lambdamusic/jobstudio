"""Recompute every company's derived status for the three-state model.

`Company.status` is maintained by a signal on Application save/delete, so it only
changes when an application does. Rows written under the old two-state rule therefore
stayed `watching` even when the company had a live application — the new `reviewing`
state would have appeared one company at a time, whenever each next happened to be
touched, which is indistinguishable from a bug while it is happening.

Reimplemented against the historical model rather than importing
`refresh_company_status()`: a data migration has to keep working when the code it was
written beside has moved on.
"""

from django.db import migrations

SUBMITTED = ["applied", "interviewing", "rejected"]   # COMPANY_APPLIED_TRIGGER_STATUSES
LIVE = ["saved", "reviewing"]                         # COMPANY_REVIEWING_TRIGGER_STATUSES


def recompute(apps, schema_editor):
    Company = apps.get_model("tracker", "Company")
    for company in Company.objects.all():
        statuses = set(company.applications.values_list("status", flat=True))
        if statuses & set(SUBMITTED):
            wanted = "applied"
        elif statuses & set(LIVE):
            wanted = "reviewing"
        else:
            wanted = "watching"
        if company.status != wanted:
            Company.objects.filter(pk=company.pk).update(status=wanted)


class Migration(migrations.Migration):

    dependencies = [("tracker", "0012_alter_company_status")]

    # Nothing to undo: the field is unchanged, and the signal recomputes each row the next
    # time its applications move either way.
    operations = [migrations.RunPython(recompute, migrations.RunPython.noop)]
