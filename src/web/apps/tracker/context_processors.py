"""Template context shared by every page."""

from pathlib import Path

import identity
from django.conf import settings

from cvs.models import BaseCv

from .models import ACTIVE_STATUSES, Application, Area, Company, Scan


def site_context(request):
    """Environment flag (so templates can hide local-only UI from the published mirror)
    plus the sidebar counts — the reference UI puts a live count against every section.

    `owner_name` comes from the data root's identity (config.yaml, or the base CV's
    heading), not from the template: the sidebar used to render one person's name on
    every page of everyone's install.
    """
    who = identity.load()
    return {
        "nav_notes": _nav_notes(),
        "owner_name": who.full_name if who else "",
        "APP_NAME": settings.APP_NAME,
        "ENVIRONMENT": settings.ENVIRONMENT,
        "IS_LOCAL": settings.ENVIRONMENT == "local",
        "nav_counts": {
            "applications": Application.objects.count(),
            "active": Application.objects.filter(status__in=ACTIVE_STATUSES).count(),
            "interviewing": Application.objects.filter(status="interviewing").count(),
            "reviewing": Application.objects.filter(status="reviewing").count(),
            "saved": Application.objects.filter(status="saved").count(),
            "companies": Company.objects.count(),
            "areas": Area.objects.count(),
            "cvs": BaseCv.objects.count(),
            "scans": Scan.objects.count(),
        },
        "request_path": request.path,
    }


def _nav_notes() -> list[dict]:
    """The Notes page's tabs, as the sidebar's sub-items under Notes (`#94`): one per known
    group, then Career coach when its folder exists, each with its count. Each links `/notes/#<slug>`, which
    `tabs.js` opens. Groups the page invents for unknown subfolders are left out: the
    sidebar lists the fixed places, the page shows everything."""
    from .views import COACH_TAB, NOTE_GROUPS, nav_note_counts

    counts = nav_note_counts()
    items = [{"slug": slug, "label": label, "count": counts.get(slug, 0)}
             for slug, label, _, _ in NOTE_GROUPS]
    if Path(settings.COACH_DIR).is_dir():
        items.append({"slug": COACH_TAB, "label": "Career coach",
                      "count": counts.get(COACH_TAB, 0)})
    return items
