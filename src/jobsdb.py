"""Database access for the standalone pipeline scripts.

sqlite is the source of truth for applications and companies (see
log/2026-09-07-django-frontend-plan.md, Phase 6). Scripts that used to parse
jobs/applications.md and jobs/companies.md import this module instead.

Django is bootstrapped lazily on first use, so importing this module stays cheap and
`appfolder.py` can keep its Django-free constants importable *by* the Django app without
a circular import.

Rows are returned as plain dicts with the same keys the old markdown parsers produced,
so callers did not have to change shape.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import config

# Code, not data — this module only ever locates the Django project, which ships with
# the repo. Data paths belong to config.data_root(); see config.py.
REPO_ROOT = config.REPO_ROOT

_ready = False


def setup() -> None:
    """Bootstrap Django once. Safe to call repeatedly."""
    global _ready
    if _ready:
        return
    web = str(REPO_ROOT / "src" / "web")
    if web not in sys.path:
        sys.path.insert(0, web)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    os.environ.setdefault("ENVIRONMENT", "local")
    import django
    django.setup()
    _ready = True


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _app_dict(a) -> dict:
    return {
        "num": str(a.num),
        "date": a.date.isoformat() if a.date else "",
        "company": a.company_name,
        "role": a.role,
        "job_url": a.job_url,
        "area": a.area.slug if a.area else "",
        "cv_base": a.cv_base,
        "status": a.status,
        "next_action": a.next_action,
        "summary": a.summary,
        "notes": a.notes,
        "contact": a.contact,
        "folder": a.folder,
    }


def _company_dict(c) -> dict:
    return {
        "num": str(c.num),
        "name": c.name,
        "slug": c.slug,
        "url": c.url,
        "role_target": c.role_target,
        "fit": c.fit,
        "status": c.status,
        "category": c.category.name if c.category else "",
        "notes": c.notes,
    }


def applications(status: str | None = None) -> list[dict]:
    setup()
    from tracker.models import Application
    qs = Application.objects.select_related("company", "area")
    if status:
        qs = qs.filter(status=status)
    return [_app_dict(a) for a in qs]


def companies() -> list[dict]:
    setup()
    from tracker.models import Company
    return [_company_dict(c) for c in Company.objects.select_related("category")]


def categories() -> list[dict]:
    """Every tracked category, with how many companies sit in each.

    Categories are the user's own taxonomy, built up as they track companies — the
    toolkit ships none. `/jobstudio company` reads this to reuse an existing category
    rather than inventing one per company.
    """
    setup()
    from django.db.models import Count
    from tracker.models import Category
    return [
        {"name": c.name, "order": c.order, "companies": c.n}
        for c in Category.objects.annotate(n=Count("companies")).order_by("order", "name")
    ]


def find_application(ref: str) -> dict | None:
    """Look up by row number or company-name prefix — the old find_app_row contract."""
    setup()
    from tracker.models import Application
    ref = str(ref).strip().lstrip("#")
    a = Application.objects.filter(num=ref).first() if ref.isdigit() else None
    if a is None:
        a = Application.objects.filter(company_name__istartswith=ref).order_by("num").first()
    return _app_dict(a) if a else None


def find_company(name: str) -> dict | None:
    setup()
    from tracker.models import Company
    c = Company.objects.filter(name__iexact=name).first()
    return _company_dict(c) if c else None


def known_job_urls() -> list[str]:
    setup()
    from tracker.models import Application
    return [u for u in Application.objects.values_list("job_url", flat=True) if u]


def dashboard_summary(activity_weeks: int = 8) -> dict:
    """The same aggregates the web dashboard (`/`) shows, queried straight from the
    same models via the same helper functions (`tracker.views`) — so `jobsdb.py
    status` can never drift from what the dashboard displays. See
    src/web/apps/tracker/views.py::home() and docs/workflow.md "Any time"."""
    setup()
    from tracker.models import ACTIVE_STATUSES, Application
    from tracker.views import (
        STALE_AFTER_DAYS, _activity_weeks, _ageing_at_applied, _headline_metrics,
        _recent_companies,
        _recent_scans, _recently_applied, _status_summary,
    )

    applications = Application.objects.select_related("company", "area")
    activity, _ = _activity_weeks()

    return {
        "total": applications.count(),
        "active": applications.filter(status__in=ACTIVE_STATUSES).count(),
        "status_summary": _status_summary(),
        # Pace and outcome rates — the dashboard's "At a glance" row, same helper.
        "headline": _headline_metrics(),
        "activity": activity[-activity_weeks:],
        "recent": [_app_dict(a) for a in applications.order_by("-date")[:6]],
        "recently_applied": [
            {**_app_dict(row["application"]), "changed_at": row["changed_at"]}
            for row in _recently_applied()
        ],
        "recent_companies": [
            {**_company_dict(c), "n_apps": c.n_apps, "date_added": c.date_added}
            for c in _recent_companies()
        ],
        "scans": [{"label": s.label or s.path, "date": s.date, "stats": s.stats}
                 for s in _recent_scans()],
        # Applications sitting at `applied`, quietest first — the same rows /stats/ lists,
        # from the same helper, so the two cannot come to disagree about what "gone quiet"
        # means (see docs/dashboard-status.md, "One function, two consumers").
        "ageing": [{**_app_dict(row["application"]), "days": row["days"],
                   "stale": row["stale"], "adrift": row["adrift"]}
                  for row in _ageing_at_applied()],
        "stale_after_days": STALE_AFTER_DAYS,
    }


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def set_status(num: int | str, status: str) -> dict:
    setup()
    from tracker.models import Application
    a = Application.objects.get(num=int(num))
    a.status = status
    a.save()
    return _app_dict(a)


def set_cv_base(num: int | str, cv_base: str) -> dict:
    """Change which base CV an application tailors from.

    Settable at creation (`add-application --cv-base`) and in the Django admin, and by
    nothing on the agent-native path before this (TODO `#60`) — which is where every
    other tracker write happens. So "use the chronological base for this role from now
    on" had no command behind it, and a `--base` override deliberately does not change
    the stored value: it adds a CV for that base and leaves the default alone. This is
    what makes the switch permanent when the user actually asks for that.

    Same gap, and the same argument, as `#41`'s missing `update-company`: the admin is
    the editing surface for a person, not for an agent mid-flow.
    """
    setup()
    from tracker.models import Application, CV_BASE_CHOICES
    valid = [c[0] for c in CV_BASE_CHOICES]
    if cv_base not in valid:
        # Checked rather than trusted, same as the web app's set_status: an unknown value
        # would save fine and then quietly match no base CV on the next tailoring run.
        raise ValueError(f"unknown cv_base {cv_base!r} — expected one of {', '.join(valid)}")
    a = Application.objects.get(num=int(num))
    a.cv_base = cv_base
    a.save()
    return _app_dict(a)


def set_fit(num: int | str, *, level: str, pros: str = "", cons: str = "",
           unknowns: str = "") -> dict:
    """Write the scannable pros/cons/unknowns fit summary shown on the Record tab —
    derived from (not a replacement for) the long-form gap analysis in notes.md."""
    setup()
    from tracker.models import Application
    a = Application.objects.get(num=int(num))
    a.fit_level = level
    a.fit_pros = pros
    a.fit_cons = cons
    a.fit_unknowns = unknowns
    a.save()
    return _app_dict(a)


def link_company(num: int | str) -> dict:
    """Re-link an application to its Company row by exact name match — for applications
    logged before the company was tracked."""
    setup()
    from tracker.models import Application, Company
    a = Application.objects.get(num=int(num))
    company = Company.objects.filter(name__iexact=a.company_name).first()
    if company:
        a.company = company
        a.save()
    return _app_dict(a)


def set_folder(num: int | str, folder: str) -> None:
    """Record where an application's folder ended up, relative to the repo root."""
    setup()
    from tracker.models import Application
    Application.objects.filter(num=int(num)).update(folder=folder)


def next_application_number() -> int:
    setup()
    from tracker.models import Application
    from django.db.models import Max
    return (Application.objects.aggregate(m=Max("num"))["m"] or 0) + 1


def add_application(*, company: str, role: str, area: str = "", job_url: str = "",
                    date: str = "", status: str = "saved", next_action: str = "",
                    summary: str = "", notes: str = "", contact: str = "",
                    cv_base: str = "") -> dict:
    """Create an application. Links to a Company row when the name matches one."""
    setup()
    from datetime import date as _date, datetime
    from tracker.models import Application, Area, Company

    # A str here would be stored fine but left on the in-memory instance, so _app_dict()
    # would then call .isoformat() on a string.
    when = datetime.strptime(date, "%Y-%m-%d").date() if date else _date.today()

    num = next_application_number()
    a = Application.objects.create(
        num=num,
        date=when,
        company=Company.objects.filter(name__iexact=company).first(),
        company_name=company,
        role=role,
        job_url=job_url,
        area=Area.objects.filter(slug=area).first(),
        cv_base=cv_base or "functional",
        status=status,
        next_action=next_action,
        summary=summary,
        notes=notes,
        contact=contact,
    )
    return _app_dict(a)


def add_category(*, name: str, order: int = 0) -> dict:
    """Create a tracked category, or return the existing one untouched.

    Categories are the user's own taxonomy and the toolkit ships none (see
    `categories()`), but until `#38` nothing outside the Django admin could create one.
    That made a cold start worse than it looked: `add_company` resolves a category by
    name, so on an empty tracker every `--category` silently resolved to nothing and the
    companies landed uncategorised — and an uncategorised company falls to
    `scan-config.yaml`'s `default_area` rather than the area its category maps to.

    Idempotent, because bootstrapping a tracker means proposing a small set of
    categories and then adding companies into them; re-running must not duplicate or
    renumber. An existing category keeps its `order` — that is a hand-set display
    preference, not something a later add should quietly rewrite.
    """
    setup()
    from tracker.models import Category

    name = name.strip()
    if not name:
        raise ValueError("A category needs a name.")
    c, created = Category.objects.get_or_create(name=name, defaults={"order": order})
    return {"name": c.name, "order": c.order, "created": created}


def _resolve_category(name: str):
    """Look a category up by name, or say clearly that it does not exist.

    Deliberately strict. Silently dropping an unknown name is the worst of the three
    options: the command reports success, the row is written, and the mistake only
    surfaces later as a company missing from its category on the web app and scored
    against the wrong target area. Auto-creating it is no better — it turns a typo into
    a permanent second category with one company in it, which is exactly the
    one-category-per-company sprawl `/jobstudio company` tells the agent to avoid.
    """
    from tracker.models import Category

    if not name:
        return None
    cat = Category.objects.filter(name=name).first()
    if cat is not None:
        return cat
    known = ", ".join(c.name for c in Category.objects.order_by("order", "name"))
    raise ValueError(
        f"No such category: {name!r}. "
        + (f"Tracked categories: {known}." if known else "The tracker has no categories yet.")
        + f"\nCreate it first:  jobsdb.py add-category --name {name!r}"
    )


def add_company(*, name: str, url: str = "", role_target: str = "", fit: int = 3,
                category: str = "", notes: str = "") -> dict:
    setup()
    import datetime as dt
    from django.db.models import Max
    from tracker.models import Company
    from appfolder import slug as slugify

    cat = _resolve_category(category)
    num = (Company.objects.aggregate(m=Max("num"))["m"] or 0) + 1
    c = Company.objects.create(
        num=num,
        name=name,
        slug=slugify(name) or f"company-{num}",
        url=url,
        role_target=role_target,
        fit=fit,
        category=cat,
        notes=notes,
        date_added=dt.date.today(),
    )
    return _company_dict(c)


_UNSET = object()


def _resolve_company(ref: str):
    """A company by row number or name, or a message saying which it was not.

    Number first, then exact name, then a unique prefix — the same widening
    `find_application` does, with one difference that matters for a *write*: a prefix
    matching more than one company is refused rather than resolved to the lowest `num`.
    Editing the wrong company silently is worse than being asked to be specific, and a
    read can afford a guess where an update cannot.
    """
    from tracker.models import Company

    ref = str(ref).strip().lstrip("#")
    if ref.isdigit():
        c = Company.objects.filter(num=ref).first()
        if c is not None:
            return c
        raise ValueError(f"no company numbered {ref}.")
    c = Company.objects.filter(name__iexact=ref).first()
    if c is not None:
        return c
    matches = list(Company.objects.filter(name__istartswith=ref).order_by("num")[:6])
    if not matches:
        raise ValueError(f"no company matching {ref!r}. `jobsdb.py show-company <name>` "
                         "takes an exact name; this takes a number, a name or a prefix.")
    if len(matches) > 1:
        names = ", ".join(f"#{m.num} {m.name}" for m in matches)
        raise ValueError(f"{ref!r} matches more than one company ({names}) — name one "
                         "exactly, or use its number.")
    return matches[0]


def update_company(ref: str, *, url=_UNSET, role_target=_UNSET, fit=_UNSET,
                   category=_UNSET, notes=_UNSET) -> dict:
    """Change a tracked company. Only the fields passed are touched (`#41`).

    `add-company` existed from the start and nothing could change a row afterwards, so
    editing a `role_target`, `fit`, `category`, `url` or `notes` meant the Django admin
    or a `manage.py shell -c` one-liner. That is fine for a person — the admin is the
    editing surface by design — and wrong for an agent, which is how every other tracker
    write happens. The case that made it worth building is a change of direction: one
    pivot re-pointed three fields across two companies, as three shell calls; a pivot
    across twenty rows would be unbearable. The second-person install pass then hit the
    same wall for a plainer reason — two careers URLs had gone stale (a 404 and a
    redirect to an acquirer) and there was no command to correct them.

    **Deliberately not a general-purpose field setter**, and deliberately no `--name`:
    renaming changes the slug, and the company page URL plus the `company_overrides`,
    `company_areas` and `known_unsupported` keys in scan-config.yaml are all keyed on
    name or slug. A rename is its own job, with those call sites to update.

    `_UNSET` rather than `None` as the default, because "" is a meaningful value here:
    clearing a stale URL or emptying the notes has to be possible, and `None` would make
    that indistinguishable from leaving the field alone.
    """
    setup()
    c = _resolve_company(ref)
    if category is not _UNSET:
        # Reused so an unknown category is refused here exactly as `add-company` refuses
        # it, rather than this command inventing a second, laxer rule.
        c.category = _resolve_category(category)
    if url is not _UNSET:
        c.url = url
    if role_target is not _UNSET:
        c.role_target = role_target
    if fit is not _UNSET:
        c.fit = int(fit)
    if notes is not _UNSET:
        c.notes = notes
    c.save()
    return _company_dict(c)


# ---------------------------------------------------------------------------
# Status report — terminal mirror of the web dashboard
# ---------------------------------------------------------------------------

def print_status_report(data: dict) -> None:
    from datetime import date as _date

    from tracker.templatetags.jobs_extras import ago as _ago

    print(f"Job Search Status — {_date.today().isoformat()}")
    print(f"{data['total']} applications tracked, {data['active']} active\n")

    h = data.get("headline") or {}
    if h.get("submitted"):
        print(f"At a glance ({h['submitted']} submitted since {h['since'].isoformat()}):")
        print(f"  {'applied / week':<18}{h['per_week_recent']} last {h['recent_weeks']} weeks, "
              f"{h['per_week_all']} all time")
        for label, key in (("reached interview", "interviewed"), ("rejected", "rejected"),
                           ("no answer yet", "awaiting")):
            print(f"  {label:<18}{h['pct_' + key]}%  ({h[key]})")
        print()

    print("Status counts:")
    for row in data["status_summary"]:
        print(f"  {row['status']:<14} {row['count']}")

    if data["activity"]:
        print("\nActivity (recent weeks):")
        for w in data["activity"]:
            if not w["total"]:
                continue
            print(f"  {w['start'].strftime('%-d %b')}: {w['added']} added, "
                  f"{w['applied']} applied, {w['rejected']} rejected")

    stale = [a for a in data.get("ageing", []) if a["stale"]]
    if stale:
        print(f"\nGone quiet ({data['stale_after_days']}+ days at applied):")
        for a in stale:
            # R-G2: quiet AND nothing planned is the row worth acting on first.
            tail = f"next: {a['next_action']}" if a["next_action"] else "nothing planned"
            print(f"  #{a['num']} {a['company']} — {a['role']}  {a['days']}d  ({tail})")

    print("\nRecently logged:")
    if data["recent"]:
        for a in data["recent"]:
            print(f"  #{a['num']} {a['company']} — {a['role']}  [{a['status']}]  {a['date']}")
    else:
        print("  (none)")

    print("\nRecently applied:")
    if data["recently_applied"]:
        for a in data["recently_applied"]:
            print(f"  #{a['num']} {a['company']} — {a['role']}  {_ago(a['changed_at'])}")
    else:
        print("  (none yet)")

    print("\nRecently added companies:")
    if data["recent_companies"]:
        for c in data["recent_companies"]:
            print(f"  {c['name']}  ({c['n_apps']} apps)  added {_ago(c['date_added'])}")
    else:
        print("  (none)")

    print("\nLatest portal scans:")
    if data["scans"]:
        for s in data["scans"]:
            stats = s["stats"] or {}
            line = f"  {s['label']}  {_ago(s['date'])}"
            if stats:
                line += (f" — {stats.get('companies_scanned', '—')} companies scanned, "
                        f"{stats.get('roles_found', '—')} roles found, "
                        f"{stats.get('scored_matches', '—')} scored matches")
                if stats.get("strong_matches") is not None:
                    line += f" ({stats['strong_matches']} strong, {stats.get('other_matches', 0)} other)"
            print(line)
    else:
        print("  (none)")


# ---------------------------------------------------------------------------
# CLI — how the jobstudio skill writes to the tracker
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Query and update the job tracker database.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add-application", help="Log a new application")
    p_add.add_argument("--company", required=True)
    p_add.add_argument("--role", required=True)
    p_add.add_argument("--area", default="")
    p_add.add_argument("--url", default="")
    p_add.add_argument("--date", default="")
    p_add.add_argument("--status", default="saved")
    p_add.add_argument("--next-action", default="")
    p_add.add_argument("--summary", default="", help="One-line description for list views")
    p_add.add_argument("--notes", default="", help="The full record")
    p_add.add_argument("--contact", default="")

    p_cat = sub.add_parser("add-category", help="Create a company category (idempotent)")
    p_cat.add_argument("--name", required=True)
    p_cat.add_argument("--order", type=int, default=0,
                       help="Display position; ignored for a category that already exists")

    p_co = sub.add_parser("add-company", help="Track a new company")
    p_co.add_argument("--name", required=True)
    p_co.add_argument("--url", default="")
    p_co.add_argument("--role-target", default="")
    p_co.add_argument("--fit", type=int, default=3)
    p_co.add_argument("--category", default="")
    p_co.add_argument("--notes", default="")

    p_upco = sub.add_parser("update-company",
                            help="Change a tracked company (only the flags you pass)")
    p_upco.add_argument("ref", help="Company number, exact name, or a unique name prefix")
    # `default=None` plus an explicit None check, so passing `--url ""` clears the field
    # while omitting the flag leaves it alone. A stale careers URL needs to be clearable.
    p_upco.add_argument("--url", default=None)
    p_upco.add_argument("--role-target", default=None)
    p_upco.add_argument("--fit", type=int, default=None, choices=[1, 2, 3, 4, 5])
    p_upco.add_argument("--category", default=None)
    p_upco.add_argument("--notes", default=None)

    p_st = sub.add_parser("set-status", help="Change an application's status")
    p_st.add_argument("num")
    p_st.add_argument("status")

    p_cvb = sub.add_parser("set-cv-base", help="Change which base CV an application tailors from")
    p_cvb.add_argument("num")
    p_cvb.add_argument("cv_base", choices=["functional", "chronological"])

    p_fit = sub.add_parser("set-fit", help="Set an application's fit summary (pros/cons/unknowns)")
    p_fit.add_argument("num")
    p_fit.add_argument("--level", required=True, choices=["strong", "moderate", "stretch", "weak"])
    p_fit.add_argument("--pros", default="", help="One point per line")
    p_fit.add_argument("--cons", default="", help="One point per line")
    p_fit.add_argument("--unknowns", default="", help="One point per line")

    p_link = sub.add_parser("link-company", help="Re-link an application to its Company row by name")
    p_link.add_argument("num")

    p_show = sub.add_parser("show", help="Print one application as JSON")
    p_show.add_argument("ref", help="Row number or company-name prefix")

    p_showco = sub.add_parser("show-company", help="Print one company as JSON (exact name match)")
    p_showco.add_argument("name")

    sub.add_parser("list", help="Print all applications as JSON")

    sub.add_parser("categories", help="Print the tracked company categories, with counts")

    p_status = sub.add_parser("status", help="Terminal mirror of the web dashboard")
    p_status.add_argument("--json", action="store_true", help="Print raw JSON instead of the formatted report")

    args = parser.parse_args()

    try:
        _dispatch(args, json)
    except ValueError as exc:
        # A named category that does not exist is a normal typo, not a crash. The
        # message already says how to fix it; a traceback would bury it.
        raise SystemExit(str(exc))


def _dispatch(args, json) -> None:
    if args.cmd == "add-application":
        row = add_application(
            company=args.company, role=args.role, area=args.area, job_url=args.url,
            date=args.date, status=args.status, next_action=args.next_action,
            summary=args.summary, notes=args.notes, contact=args.contact)
        print(row["num"])
    elif args.cmd == "add-category":
        row = add_category(name=args.name, order=args.order)
        print(f"{row['name']}  ({'created' if row['created'] else 'already tracked'})")
    elif args.cmd == "add-company":
        row = add_company(name=args.name, url=args.url, role_target=args.role_target,
                          fit=args.fit, category=args.category, notes=args.notes)
        print(row["num"])
    elif args.cmd == "update-company":
        fields = {k: v for k, v in (("url", args.url), ("role_target", args.role_target),
                                    ("fit", args.fit), ("category", args.category),
                                    ("notes", args.notes)) if v is not None}
        if not fields:
            raise SystemExit("update-company: nothing to change — pass at least one of "
                             "--url, --role-target, --fit, --category, --notes.")
        row = update_company(args.ref, **fields)
        print(f"#{row['num']} {row['name']} -> " +
              ", ".join(f"{k}={row.get(k)!r}" for k in sorted(fields)))
    elif args.cmd == "set-status":
        row = set_status(args.num, args.status)
        print(f"#{row['num']} {row['company']} -> {row['status']}")
    elif args.cmd == "set-cv-base":
        row = set_cv_base(args.num, args.cv_base)
        print(f"#{row['num']} {row['company']} -> cv_base: {row['cv_base']}")
    elif args.cmd == "set-fit":
        row = set_fit(args.num, level=args.level, pros=args.pros, cons=args.cons,
                      unknowns=args.unknowns)
        print(f"#{row['num']} {row['company']} -> fit: {args.level}")
    elif args.cmd == "link-company":
        row = link_company(args.num)
        print(f"#{row['num']} {row['company']}")
    elif args.cmd == "show":
        row = find_application(args.ref)
        if row is None:
            raise SystemExit(f"No application found for {args.ref!r}")
        print(json.dumps(row, indent=2, ensure_ascii=False))
    elif args.cmd == "show-company":
        row = find_company(args.name)
        if row is None:
            raise SystemExit(f"No company found for {args.name!r}")
        print(json.dumps(row, indent=2, ensure_ascii=False))
    elif args.cmd == "list":
        print(json.dumps(applications(), indent=2, ensure_ascii=False))
    elif args.cmd == "categories":
        rows = categories()
        if not rows:
            print("No categories yet — create one with:  jobsdb.py add-category --name '<name>'")
        for c in rows:
            print(f"  {c['name']}  ({c['companies']})")
    elif args.cmd == "status":
        data = dashboard_summary()
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        else:
            print_status_report(data)


if __name__ == "__main__":
    _main()
