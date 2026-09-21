"""Template context shared by every page."""

import config
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
        "owner_name": who.full_name if who else "",
        # One definition for the whole UI. Was ten `vscode://file/` literals across
        # eight templates and admin.py, which hardcoded one editor for every user
        # (§1 blocker 10). `editor_url_scheme` in ~/.jobstudio.ini overrides it.
        "EDITOR_URL_SCHEME": config.setting("editor_url_scheme", "vscode://file/"),
        "ENVIRONMENT": settings.ENVIRONMENT,
        "IS_LOCAL": settings.ENVIRONMENT == "local",
        "nav_counts": {
            "applications": Application.objects.count(),
            "active": Application.objects.filter(status__in=ACTIVE_STATUSES).count(),
            "reviewing": Application.objects.filter(status="reviewing").count(),
            "saved": Application.objects.filter(status="saved").count(),
            "companies": Company.objects.count(),
            "areas": Area.objects.count(),
            "cvs": BaseCv.objects.count(),
            "scans": Scan.objects.count(),
        },
        "request_path": request.path,
    }
