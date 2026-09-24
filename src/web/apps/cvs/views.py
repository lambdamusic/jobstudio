from django.shortcuts import get_object_or_404, render

from .models import BaseCv


def tailored_cvs() -> list[dict]:
    """Every per-application tailored CV across the whole job search, newest first, each
    carrying the application it was written for.

    There is no database row for these — a tailored CV is a file in an application
    folder, recognised by naming convention — so this scans one folder per application
    that has one. Fine at the scale of a real job search (tens of applications), but it
    is a filesystem walk rather than a query: if this page ever feels slow, this is why.
    """
    from tracker.models import Application

    rows = []
    apps = (Application.objects.select_related("company")
            .exclude(folder="").order_by("-num"))
    for app in apps:
        for cv in app.tailored_cvs:
            rows.append({**cv, "app": app})
    rows.sort(key=lambda c: (c["date"].toordinal() if c["date"] else 0, c["name"]),
              reverse=True)
    return rows


def cv_list(request):
    return render(request, "cvs/cv_list.html", {
        "page": "cvs",
        "base_cvs": BaseCv.objects.all(),
        "tailored": tailored_cvs(),
    })


def base_cv_detail(request, slug):
    """A master CV from jobs/cv/base/ — chronological or functional."""
    cv = get_object_or_404(BaseCv, slug=slug)
    return render(request, "cvs/base_cv_detail.html", {
        "page": "cvs",
        "cv": cv,
        "others": BaseCv.objects.exclude(pk=cv.pk),
    })
