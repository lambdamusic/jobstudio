"""Views.

Every page is a plain URL reachable by an <a> from somewhere else, because `wget --mirror`
only finds what it can follow. Filtering by querystring is a local-only convenience — the
default (unfiltered) view is the one that gets mirrored. See plan §4.
"""

import datetime as dt
import shlex
import subprocess
import sys
from pathlib import Path

import config

from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.text import slugify
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render

from appfolder import STATUS_SORT_ORDER

from . import parsers as P
from .models import (
    ACTIVE_STATUSES,
    Application,
    ApplicationStatusChange,
    Area,
    Category,
    Company,
    Scan,
)

# Browse surfaces sort newest-first: recency is the best proxy for what still matters.
# (The admin keeps Application.Meta.ordering — status order — because it is a triage
# surface, where grouping by status is what you want.)
BROWSE_ORDER = (F("date").desc(nulls_last=True), "-num")


def _status_summary():
    """Counts per status, in the TUI's order, with zeroes included."""
    counts = dict(
        Application.objects.values_list("status").annotate(n=Count("id"))
    )
    return [{"status": s, "count": counts.get(s, 0)} for s in STATUS_SORT_ORDER]


CHART_H = 132  # px — tallest stacked bar in the activity timeline


def _monday(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _activity_weeks():
    """Weekly counts of application events for the dashboard timeline.

    Three event types: `added` (Application.date), `applied` and `rejected` (from the
    ApplicationStatusChange log). Bucketed by ISO week (Monday), with empty weeks kept
    so the x-axis stays continuous. Segment pixel heights are precomputed against the
    busiest week so the template needs no arithmetic.
    """
    events: list[tuple[dt.date, str]] = []
    for d in Application.objects.exclude(date__isnull=True).values_list("date", flat=True):
        events.append((d, "added"))
    for changed_at, to_status in ApplicationStatusChange.objects.filter(
            to_status__in=("applied", "rejected")).values_list("changed_at", "to_status"):
        events.append((timezone.localtime(changed_at).date(), to_status))

    if not events:
        return [], 0

    start = _monday(min(d for d, _ in events))
    end = _monday(timezone.localdate())
    weeks: dict[dt.date, dict] = {}
    wk = start
    while wk <= end:
        weeks[wk] = {"start": wk, "added": 0, "applied": 0, "rejected": 0}
        wk += dt.timedelta(days=7)

    for d, kind in events:
        weeks[_monday(d)][kind] += 1

    rows = sorted(weeks.values(), key=lambda w: w["start"])
    for w in rows:
        w["total"] = w["added"] + w["applied"] + w["rejected"]
    busiest = max(w["total"] for w in rows) or 1

    prev_month = None
    for w in rows:
        for kind in ("added", "applied", "rejected"):
            w[f"h_{kind}"] = round(CHART_H * w[kind] / busiest)
        month = w["start"].strftime("%b")
        w["label"] = "" if month == prev_month else month
        prev_month = month
    return rows, busiest


def _recently_applied(limit=6):
    """Most recent 'applied' status transition per application, newest first, deduped
    so a re-applied application only shows its latest date. Powers the dashboard's
    "Recently applied" panel (see home())."""
    seen: set[int] = set()
    rows = []
    changes = (ApplicationStatusChange.objects
               .filter(to_status="applied")
               .select_related("application", "application__company", "application__area")
               .order_by("-changed_at"))
    for change in changes:
        app = change.application
        if app.id in seen:
            continue
        seen.add(app.id)
        rows.append({"application": app, "changed_at": change.changed_at})
        if len(rows) >= limit:
            break
    return rows


def _recent_companies(limit=10):
    """Most recently tracked companies, newest first — powers the dashboard's
    "Recently added companies" panel (see home()) and the CLI status report
    (jobsdb.py dashboard_summary()). Excludes companies that predate `date_added`."""
    return (Company.objects.exclude(date_added__isnull=True)
            .select_related("category")
            .annotate(n_apps=Count("applications"))
            .order_by("-date_added", "-num")[:limit])


def _recent_scans(limit=3):
    """Most recent scan reports, each annotated with its summary stats — powers the
    dashboard's "Latest portal scans" panel and the CLI status report."""
    scans = list(Scan.objects.all()[:limit])
    for s in scans:
        s.stats = P.scan_summary_stats(s.body_md)
    return scans


def home(request):
    applications = Application.objects.select_related("company", "area")
    active = applications.filter(status__in=ACTIVE_STATUSES)
    areas = (Area.objects.annotate(n=Count("applications"))
             .order_by("-n", "order"))
    activity, activity_max = _activity_weeks()
    scans = _recent_scans()
    return render(request, "tracker/home.html", {
        "page": "home",
        "total": applications.count(),
        "status_summary": _status_summary(),
        "areas": areas,
        "active": active,
        "recent": applications.order_by("-date")[:6],
        "recently_applied": _recently_applied(),
        "recent_companies": _recent_companies(),
        "scans": scans,
        "activity": activity,
        "activity_max": activity_max,
    })


def application_list(request, status=None, area=None, active=False, show_all=False):
    """Filtered views are real paths, not querystrings — wget/`build_static` can only
    publish a URL that exists as a path (plan §4).

    /applications/                     active by default (applied + interviewing)
    /applications/all/                 every application
    /applications/active/              alias of /applications/
    /applications/status/<status>/     one status
    /applications/area/<slug>/         one target area

    `?q=` search stays querystring-only: it is a local convenience and cannot be
    meaningfully published as static pages.
    """
    applications = Application.objects.select_related("company", "area").order_by(*BROWSE_ORDER)
    q = request.GET.get("q", "")

    # The bare list defaults to the active set — the day-to-day view. "All" is its own
    # path, reachable from the sidebar and the stat header.
    default_active = not (status or area or active or show_all or q)

    if status is not None:
        if status not in STATUS_SORT_ORDER:
            raise Http404("No such status")
        applications = applications.filter(status=status)
    if area is not None:
        get_object_or_404(Area, slug=area)
        applications = applications.filter(area__slug=area)
    if active or default_active:
        applications = applications.filter(status__in=ACTIVE_STATUSES)

    if q:
        applications = applications.filter(
            Q(company_name__icontains=q) | Q(role__icontains=q) | Q(notes__icontains=q))

    if show_all:
        nav_apps = "all"
    elif status == "reviewing":
        nav_apps = "reviewing"
    elif status == "saved":
        nav_apps = "saved"
    else:
        nav_apps = "applications"

    return render(request, "tracker/application_list.html", {
        "page": "applications",
        "nav_apps": nav_apps,
        "applications": applications,
        "status_summary": _status_summary(),
        "areas": Area.objects.all(),
        "filter_status": status or "",
        "filter_area": area or "",
        "filter_active": active or default_active,
        "show_all": show_all,
        "default_active": default_active,
        "query": q,
        "is_filtered": bool(status or area or active or q),
    })


def application_detail(request, num):
    app = get_object_or_404(
        Application.objects.select_related("company", "area"), num=num)
    return render(request, "tracker/application_detail.html", {
        "page": "applications",
        "nav_apps": "applications",
        "app": app,
        "cover_letters": app.cover_letter_files,
        # The status menu offers every status except the one it is already in.
        "other_statuses": [s for s in STATUS_SORT_ORDER if s != app.status],
        "siblings": (Application.objects.filter(company_name=app.company_name)
                     .exclude(pk=app.pk).order_by(*BROWSE_ORDER)),
    })


def company_list(request):
    companies = (Company.objects.select_related("category")
                 .annotate(n_apps=Count("applications")))
    categories = []
    for category in Category.objects.all():
        rows = [c for c in companies if c.category_id == category.id]
        if rows:
            categories.append({"category": category, "key": slugify(category.name), "companies": rows})
    return render(request, "tracker/company_list.html", {
        "page": "companies",
        "categories": categories,
        "total": companies.count(),
        # Coverage is uneven and worth stating up front: the per-row column answers
        # "this one?", this answers "how much of the tracker is actually watched?".
        "n_scanned": sum(1 for c in companies if c.scan_coverage["scanned"]),
    })


def company_detail(request, slug):
    company = get_object_or_404(Company.objects.select_related("category"), slug=slug)
    return render(request, "tracker/company_detail.html", {
        "page": "companies",
        "company": company,
        "applications": company.applications.select_related("area").order_by(*BROWSE_ORDER),
    })


def area_list(request):
    """One page, tabbed by area — folded together with what used to be the separate
    /areas/<slug>/ detail page (retired 2026-09-14): a landing page of five small
    summary cards wasn't pulling its weight next to five full detail pages, so now
    there's just the one page with the full picture per area, one click away."""
    areas = list(Area.objects.annotate(
        n_apps=Count("applications", distinct=True),
    ))
    for area in areas:
        area.apps_list = area.applications.select_related("company").order_by(*BROWSE_ORDER)
    return render(request, "tracker/area_list.html", {"page": "areas", "areas": areas})


# ---------------------------------------------------------------------------
# File-backed pages — no DB rows, just markdown on disk
# ---------------------------------------------------------------------------

def _notes_files():
    notes_dir = Path(settings.NOTES_DIR)
    if not notes_dir.is_dir():
        return []
    return sorted(notes_dir.glob("*.md"))


def note_list(request):
    notes = [{"slug": p.stem, "title": p.stem.replace("-", " ").title()}
             for p in _notes_files()]
    return render(request, "tracker/note_list.html", {"page": "notes", "notes": notes})


def note_detail(request, slug):
    match = next((p for p in _notes_files() if p.stem == slug), None)
    if match is None:
        raise Http404("No such note")
    return render(request, "tracker/note_detail.html", {
        "page": "notes",
        "title": slug.replace("-", " ").title(),
        "body": match.read_text(),
    })


def profile_view(request):
    """The career 'stocktake' profile — jobs/profile/stocktake.md + criteria.yaml."""
    profile_dir = Path(settings.PROFILE_DIR)
    stocktake = profile_dir / "stocktake.md"
    criteria = profile_dir / "criteria.yaml"
    return render(request, "tracker/profile.html", {
        "page": "profile",
        "title": "Career stocktake",
        "body": stocktake.read_text() if stocktake.is_file() else "",
        "criteria": criteria.read_text() if criteria.is_file() else "",
    })


def scan_list(request):
    return render(request, "tracker/scan_list.html", {
        "page": "scans",
        "nav_scans": "all",
        "scans": Scan.objects.all(),
    })


def scan_detail(request, slug=None):
    """`/scans/` (slug=None) shows the latest report directly — the day-to-day view,
    same "bare path defaults to the useful thing" pattern as `/applications/`. A
    specific report is still reachable at `/scans/<slug>/`; `/scans/all/` (scan_list,
    above) is the dated index of every report.
    """
    latest = Scan.objects.first()  # Meta.ordering = ["-date", "path"] -> newest
    if slug is None:
        scan = latest
    else:
        scan = get_object_or_404(Scan, path__endswith=f"{slug}.md")

    sections, unscored_likely, unscored_other = [], [], []
    if scan is not None:
        sections = P.split_scan_sections(scan.body_md)
        for section in sections:
            if section["key"] == "unscored":
                unscored_likely, unscored_other = P.split_unscored_by_location(section["body"])

    return render(request, "tracker/scan_detail.html", {
        "page": "scans",
        "nav_scans": "latest",
        "scan": scan,
        "is_latest": scan is not None and scan == latest,
        "sections": sections,
        "unscored_likely": unscored_likely,
        "unscored_other": unscored_other,
    })


# ---------------------------------------------------------------------------
# Local-only actions
#
# Chrome blocks file:// navigation from an http:// page, so the old "Open folder"
# link silently did nothing. The dev server runs on the user's own machine, so it can just
# run `open` itself. Gated on ENVIRONMENT=local and never linked from the published
# mirror, which is built with ENVIRONMENT=publish.
# ---------------------------------------------------------------------------

def _file_opener() -> list[str]:
    """The command that opens a file in the desktop's default application.

    `open_command` in ~/.jobstudio.ini wins, which is also how a platform this does not
    know about is supported without a code change. Otherwise macOS and Linux (§1
    blocker 10 — the supported set).
    """
    configured = config.setting("open_command")
    if configured:
        return shlex.split(configured)
    return ["open"] if sys.platform == "darwin" else ["xdg-open"]


def _open_locally(path: Path, reveal: bool = False) -> None:
    """Open a path in the desktop, refusing anything outside the data root.

    `reveal` means "show it in the file manager" rather than "open it". macOS has a
    flag for that; nothing else does, so elsewhere we open the containing folder, which
    is the same intent. Passing a raw `-R` through here used to make this call
    macOS-only by construction.
    """
    root = Path(settings.DATA_ROOT).resolve()
    target = path.resolve()
    if not target.is_relative_to(root):
        raise Http404("Refusing to open a path outside the data root")

    cmd = _file_opener()
    if reveal:
        if cmd == ["open"]:
            cmd = ["open", "-R"]
        else:
            target = target if target.is_dir() else target.parent
    try:
        subprocess.Popen([*cmd, str(target)])
    except FileNotFoundError:
        # Used to escape as a 500 and hand the user a stack trace.
        raise Http404(
            f"No file opener found ({' '.join(cmd)}). Set `open_command` in "
            f"{config.GLOBAL_SETTINGS_FILE}."
        )


def reveal_folder(request, num):
    if settings.ENVIRONMENT != "local":
        raise Http404("Local only")

    app = get_object_or_404(Application, num=num)
    folder = app.folder_path
    if folder is None:
        raise Http404("No folder on disk for this application")

    _open_locally(folder)
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", f"/applications/{num}/"))


def create_folder(request, num):
    """Local-only: an application with no folder yet shows a "Create folder" action
    instead of Open folder / Open in VS Code. Runs the same appfolder.ensure_folder()
    the jobstudio skill uses, then redirects back."""
    if settings.ENVIRONMENT != "local":
        raise Http404("Local only")

    app = get_object_or_404(Application, num=num)
    if not app.folder:
        import appfolder
        folder = appfolder.ensure_folder(
            {"num": app.num, "company": app.company_name, "role": app.role})
        rel = str(folder.relative_to(Path(settings.DATA_ROOT).resolve()))
        Application.objects.filter(pk=app.pk).update(folder=rel)
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", f"/applications/{num}/"))


def set_status(request, num, status):
    """Local-only: move an application to any status from the detail page's status menu,
    without a trip to the admin change form.

    Replaced a hardcoded one-click bump to 'reviewing' (2026-09-23) — the other six
    transitions were just as common and all of them meant opening the admin. `status` is
    checked against STATUS_SORT_ORDER rather than trusted: it arrives from the URL, so an
    unknown value must 404 rather than write a status nothing else in the app understands.
    `Application.save()` handles `status_order` and the status-change log (models.py's
    post_save signal) the same as any other save.
    """
    if settings.ENVIRONMENT != "local":
        raise Http404("Local only")
    if status not in STATUS_SORT_ORDER:
        raise Http404(f"Unknown status: {status}")

    app = get_object_or_404(Application, num=num)
    if app.status != status:
        app.status = status
        app.save(update_fields=["status"])
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", f"/applications/{num}/"))


def reveal_company_notes(request, slug):
    """Local-only: reveal jobs/companies/<slug>.md, selected, in Finder."""
    if settings.ENVIRONMENT != "local":
        raise Http404("Local only")

    company = get_object_or_404(Company, slug=slug)
    path = company.notes_path
    if path is None:
        raise Http404("No notes file on disk for this company")

    _open_locally(path, reveal=True)
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", f"/companies/{slug}/"))
