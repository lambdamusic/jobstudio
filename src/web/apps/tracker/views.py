"""Views.

Every page is a plain URL reachable by an <a> from somewhere else, because `wget --mirror`
only finds what it can follow. Filtering by querystring is a local-only convenience — the
default (unfiltered) view is the one that gets mirrored. See plan §4.
"""

import datetime as dt
import json
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path

import config

from django.conf import settings
from django.db.models import Count, F, Max, Q
from django.utils import timezone
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render

from appfolder import COMPANY_STATUSES, STATUS_SORT_ORDER

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


def _with_last_change(applications):
    """Annotate a queryset with the timestamp of each application's most recent status
    change — what "last moved" means everywhere it is shown.

    Not `Application.date`, which is when the row was logged and never changes again. An
    application logged in June and rejected last week last *moved* last week, and a list
    sorted the other way would put it at the top of "longest without moving".
    """
    return applications.annotate(last_change=Max("status_changes__changed_at"))


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
    applications = _with_last_change(Application.objects.select_related("company", "area"))
    active = applications.filter(status__in=ACTIVE_STATUSES)
    areas = (Area.objects.annotate(n=Count("applications"))
             .order_by("-n", "order"))
    activity, activity_max = _activity_weeks()
    scans = _recent_scans()
    return render(request, "tracker/home.html", {
        "page": "home",
        "total": applications.count(),
        "status_summary": _status_summary(),
        # For _statbar.html's note — see R-G3 there.
        "stale_applied": _stale_applied(),
        "stale_after_days": STALE_AFTER_DAYS,
        "areas": areas,
        "active": active,
        "recent": applications.order_by("-date")[:6],
        "recently_applied": _recently_applied(),
        "recent_companies": _recent_companies(),
        "scans": scans,
        "activity": activity,
        "activity_max": activity_max,
    })


# ---------------------------------------------------------------------------
# /stats/ — the charts page
#
# Deliberately not the dashboard. `/` is the page used daily and should not churn while
# chart designs are still being judged, and this one can carry the debugging affordances
# a finished dashboard should not: the raw numbers beside each chart, so a diagram can be
# checked rather than trusted. Promotion to the dashboard is a later decision, chart by
# chart. See backlog/dashboard-charts-plan.md §2a.
# ---------------------------------------------------------------------------


# R-G1: an application at `applied` that has not moved in this long has gone quiet. Not a
# deadline — a threshold for "worth a look", which is why the rows are listed rather than
# counted away.
STALE_AFTER_DAYS = 30


def _ageing_at_applied():
    """Applications sitting at `applied`, longest-quiet first, with how long each has sat.

    A list rather than a distribution (plan §7): every row is individually actionable in a
    way a histogram of ages is not, and the action is usually "chase it or close it".

    One function rather than a count here and a list there. Everything that shows
    staleness — this page, the stat bar's note, the CLI status report — counts these rows,
    so "stale" cannot come to mean two slightly different things in two places.

    `last_moved` is the most recent status change, falling back to `Application.date` for a
    row that predates the change log; a row with neither is kept with `days = None` rather
    than dropped or dated to today. It is a real state (an application logged with no date
    at all) and inventing an age for it would put it in the wrong half of the list.
    """
    today = timezone.localdate()
    rows = []
    for app in (Application.objects.filter(status="applied")
                .select_related("company", "area")
                .annotate(last_change=Max("status_changes__changed_at"))):
        moved = timezone.localtime(app.last_change).date() if app.last_change else app.date
        days = (today - moved).days if moved else None
        rows.append({
            "application": app,
            "last_moved": moved,
            "days": days,
            "stale": days is not None and days >= STALE_AFTER_DAYS,
            # R-G2: a stale row with nothing planned is the strongest signal here — the
            # field already exists and nothing else surfaces applications by staleness.
            "adrift": days is not None and days >= STALE_AFTER_DAYS and not app.next_action.strip(),
        })
    # Quietest first; an unknown age sorts last rather than pretending to be either end.
    rows.sort(key=lambda r: (r["days"] is None, -(r["days"] or 0)))
    return rows


def _stale_applied(rows=None) -> int:
    """How many of the `applied` applications have gone quiet — R-G3's consequence, which
    has to be sayable wherever the `applied` count is shown: a pipeline of 17 that holds
    several dead applications is not a pipeline of 17."""
    return sum(1 for r in (rows if rows is not None else _ageing_at_applied()) if r["stale"])


# ---------------------------------------------------------------------------
# Chart data — one helper per chart on /stats/ (plan §3-§7)
#
# Three rules hold across all of them. The server finishes the arithmetic and the client
# only draws (R2), so the numbers can be mirrored in the terminal and the static export
# stays inert. One helper per chart, used by every consumer rather than re-queried per
# surface (R1). And nothing is inferred: a transition that was never recorded is never
# drawn, and a chart with nothing honest to show says so instead (R3).
# ---------------------------------------------------------------------------

# The funnel's own order, which is deliberately **not** `STATUS_SORT_ORDER`. That is a
# triage order — most active first — and orienting the flow by it would make
# `saved -> applied` run backwards, so the DAG rule in R-S3 would drop the commonest
# transition in any tracker. This is the order §3's "full funnel" spells out; the three
# terminal statuses keep their `STATUS_SORT_ORDER` sequence relative to each other.
FUNNEL_ORDER = ["saved", "reviewing", "applied", "interviewing",
                "discarded", "closed", "rejected"]

# Over, one way or another: dropped by the candidate, closed by the employer, or refused.
# Everything else is still live, whether or not it has been submitted — which is a wider
# reading than ACTIVE_STATUSES (applied + interviewing), the one the stat bar counts.
ENDED_STATUSES = ["discarded", "closed", "rejected"]

# §3's second view: what happens from submission onward, without the pre-application
# attrition. An application that reached `applied` from anywhere enters the diagram there.
POST_APPLICATION_ORDER = ["applied", "interviewing", "discarded", "closed", "rejected"]

# Age bands for the ageing chart (§7). The boundary between the third and fourth band is
# STALE_AFTER_DAYS, so "past this line is quiet" is a property of the bands themselves
# rather than a threshold drawn on top of them — `test_the_bands_break_at_the_threshold`
# fails if the two drift apart.
AGE_BANDS = [(0, 7), (8, 14), (15, 30), (31, 60), (61, None)]


def _band_label(low, high) -> str:
    return f"{low}–{high}d" if high is not None else f"{low}d+"


def _ageing_bands(rows=None):
    """The ageing view as bands: how many applications at `applied` have sat for how long.

    Started as a table of rows and became a chart on 2026-09-28. The individual rows are
    better served by the applications list, which already tabulates them; what a separate
    page can say that a table cannot is the *shape* — whether the quiet end is growing.

    Bands rather than a histogram of raw ages: with a handful of applications a per-day
    distribution is noise, and the question is only ever "how much is past the line".
    """
    rows = _ageing_at_applied() if rows is None else rows
    bands = []
    for low, high in AGE_BANDS:
        matched = [r for r in rows
                  if r["days"] is not None and r["days"] >= low
                  and (high is None or r["days"] <= high)]
        bands.append({
            "label": _band_label(low, high),
            "count": len(matched),
            "stale": low > STALE_AFTER_DAYS,
            "adrift": sum(1 for r in matched if r["adrift"]),
            # The rows themselves, so the band can be opened rather than only counted.
            # `_ageing_at_applied()` already sorted them quietest-first.
            "applications": [{
                "num": r["application"].num,
                "company": r["application"].company_name,
                "role": r["application"].role,
                "days": r["days"],
                "adrift": r["adrift"],
            } for r in matched],
        })
    return {
        "bands": bands,
        "total": len(rows),
        # Kept out of the bands rather than bundled into the first one: an application
        # with no date at all has an unknown age, and putting it in "0–7d" would be a
        # guess dressed as data.
        "undated": sum(1 for r in rows if r["days"] is None),
        "stale": sum(1 for r in rows if r["stale"]),
        "adrift": sum(1 for r in rows if r["adrift"]),
    }


def _status_flow(order=None):
    """The status-flow diagram (§3): where applications go, and where they stop.

    Three things make this more than a `GROUP BY (from_status, to_status)`:

    **Entry stubs, for mid-funnel arrivals only (R-S1).** A change with a blank
    `from_status` is where an application was first logged. Entering at the funnel's first
    status is not worth drawing — that node is the start, and a stub in front of it only
    says "these applications exist". Entering anywhere *else* is worth drawing, because an
    application that appears at `closed` never passed through the statuses to its left and
    a diagram that quietly routed it through them would be lying. So the first status in
    the window is drawn as a source, and every other entry keeps its own ribbon.

    Until 2026-09-28 every status had one, because 24 of 57 applications had been logged
    straight into a later status while the tracker was being built. `backfill_saved_entry`
    fixed the data; this rule stays, so the next one that happens for real is still shown.

    **Two terminal nodes (R-S2).** An application sitting in a status has no outgoing edge
    and would vanish from a flow diagram, so each status's current occupancy flows on to
    one of two ends: `active` (anything not closed, discarded or rejected) or `inactive`.
    Seven "still here" stubs said the same thing seven times; two say where the tracker
    actually stands. Occupancy is taken from the *database* rather than from the
    arithmetic, which makes it a check as well as a shape: `entered + in - out` must equal
    the status count, and `reconciles` says whether it did.

    Note that `active` here is WIDER than `ACTIVE_STATUSES` (applied + interviewing), which
    is what the stat bar's "active" box counts. Two different questions — "still in play
    having submitted" and "not yet over" — and the note under the chart says which this is.

    **Backward edges are dropped, and counted (R-S3).** A Sankey is a DAG; real
    transitions go backwards when an application is re-opened. Dropping them silently is
    how a diagram starts lying, so `dropped` is reported and the page prints it.

    `order` narrows the window — see POST_APPLICATION_ORDER. A change arriving from
    outside the window counts as an entry (that is where it entered the diagram); one
    leaving is counted in `left` and reported, never quietly absorbed.
    """
    order = list(order or FUNNEL_ORDER)
    index = {s: i for i, s in enumerate(order)}

    entries, edges, left = Counter(), Counter(), Counter()
    for frm, to in ApplicationStatusChange.objects.values_list("from_status", "to_status"):
        if to not in index:
            if frm in index:
                left[frm] += 1
            continue
        if not frm or frm not in index:
            entries[to] += 1
        else:
            edges[(frm, to)] += 1

    current = dict(Application.objects.filter(status__in=order)
                   .values_list("status").annotate(n=Count("id")))

    nodes, links, dropped, reconciles = [], [], 0, True
    still, mid_funnel = Counter(), 0
    for status in order:
        into = entries[status] + sum(n for (f, t), n in edges.items() if t == status)
        out = sum(n for (f, t), n in edges.items() if f == status) + left[status]
        held = current.get(status, 0)
        # The reconciliation check, on the full edge set — before any backward edge is
        # dropped, because what is drawn is a view of the history, not the history.
        if into - out != held:
            reconciles = False
        if not (into or out or held):
            continue  # a status nothing ever touched is not a node

        nodes.append({"name": status, "status": status, "kind": "status"})
        # The window's first status is where the funnel starts; anything else arriving from
        # nowhere gets a visible stub. `entries` still counts both, because the
        # reconciliation is about the history, not about what is drawn.
        if entries[status] and status != order[0]:
            nodes.append({"name": f"entry:{status}", "status": status, "kind": "entry"})
            links.append({"source": f"entry:{status}", "target": status,
                         "value": entries[status], "kind": "entry"})
            mid_funnel += entries[status]
        if held:
            end = "inactive" if status in ENDED_STATUSES else "active"
            links.append({"source": status, "target": end, "value": held, "kind": "still"})
            still[end] += held

    # The two ends, appended last so they sit at the right of the diagram.
    for end in ("active", "inactive"):
        if still[end]:
            nodes.append({"name": end, "status": end, "kind": "end"})

    # R-S4: the `applied` node is the largest and includes applications that have had no
    # response for months. It says so on itself, rather than leaving the diagram to
    # overstate how much is in flight.
    quiet = _stale_applied()
    for node in nodes:
        if node["kind"] == "entry":
            # Not "logged" — that read as an eighth status. This is where an application
            # entered the tracker, which for a third of them is not `saved`: roles logged
            # after the deadline had passed, or after already applying.
            node["label"] = "added"
        elif node["kind"] == "end":
            node["label"] = node["name"]
        elif node["name"] == "applied" and quiet:
            node["label"] = f"applied · {quiet} quiet"
        else:
            node["label"] = node["name"]

    for (frm, to), n in sorted(edges.items()):
        if index[frm] < index[to]:
            links.append({"source": frm, "target": to, "value": n, "kind": "move"})
        else:
            dropped += n

    return {
        "nodes": nodes,
        "links": links,
        "dropped": dropped,
        "left": sum(left.values()),
        "reconciles": reconciles,
        "moves": sum(edges.values()),
        "statuses": [s for s in order if s in {n["name"] for n in nodes}],
        "active": still["active"],
        "inactive": still["inactive"],
        # How many applications appear part-way along rather than at the start — worth
        # stating under the chart, because their ribbons are the ones that look odd.
        "mid_funnel": mid_funnel,
        "entered": entries[order[0]],
    }


# R-T4: how many distinct weeks must carry organic (neither backfilled nor bulk-logged)
# transitions before the shape of a history means anything. Below this the chart says what
# it is waiting for — it gets there on its own as the tracker is used.
ORGANIC_WEEKS_MIN = 3

# A day holding this many transitions is a logging session, not a week's worth of events.
BULK_DAY_MIN = 5


def _status_stock():
    """Status stock over time (§4): how many applications sat in each status, week by week.

    **Both stock and flow, as two views (R-T1).** `counts` carries each application's state
    forward and says where they all *are* at the end of each week — the shape of the
    pipeline. `moves` counts what actually happened *in* that week: how many applications
    arrived in each status. The two are not the same chart with a different skin and the
    page says so, because a stock line that never moves and a flow line that reads zero
    mean opposite things. (The dashboard's Activity chart is flow too, but for three event
    types across the whole tracker rather than per status.)

    **Replayed, never back-filled (the "must not").** State begins at an application's
    first recorded change. An application is not assumed to have existed, in any status,
    before the tracker knew about it.

    **Reconstructed weeks are marked (R4, R-T2).** Two kinds of week are not observed
    history. The 2026-09-08 backfill dated its rows from `Application.date`, so they land
    at exactly local midnight — a precise signal, not a guess. And a bulk logging session
    puts a fortnight of real decisions on one afternoon. A week where those dominate is
    shaded and called reconstructed, because otherwise the chart shows a cliff and reads
    as a change in activity that did not happen.
    """
    changes = list(ApplicationStatusChange.objects
                   .order_by("changed_at", "pk")
                   .values_list("application_id", "changed_at", "to_status"))
    if not changes:
        return {"weeks": [], "statuses": [], "ready": False, "organic_weeks": 0,
                "needs_weeks": ORGANIC_WEEKS_MIN, "reconstructed": 0}

    # Bulk days are a property of the whole log, not of one week: a session that runs past
    # midnight is two days, and each is judged on its own volume.
    per_day = Counter(timezone.localtime(when).date() for _, when, _ in changes)

    def is_organic(when) -> bool:
        local = timezone.localtime(when)
        backfilled = local.time() == dt.time(0, 0)
        return not backfilled and per_day[local.date()] < BULK_DAY_MIN

    first = _monday(timezone.localtime(changes[0][1]).date())
    last = _monday(timezone.localdate())
    state: dict[int, str] = {}
    weeks, cursor, index = [], first, 0
    while cursor <= last:
        end = cursor + dt.timedelta(days=7)
        organic = reconstructed = 0
        moves: Counter = Counter()
        while index < len(changes) and timezone.localtime(changes[index][1]).date() < end:
            app_id, when, status = changes[index]
            state[app_id] = status
            moves[status] += 1
            organic += 1 if is_organic(when) else 0
            reconstructed += 0 if is_organic(when) else 1
            index += 1
        counts = Counter(state.values())
        weeks.append({
            "start": cursor.isoformat(),
            "label": cursor.strftime("%-d %b"),
            "counts": {s: counts.get(s, 0) for s in FUNNEL_ORDER},
            "moves": {s: moves.get(s, 0) for s in FUNNEL_ORDER},
            "total": sum(counts.values()),
            "moved": sum(moves.values()),
            # A week with no transitions at all is neither: it is just quiet, and shading
            # it would say something happened that did not.
            "reconstructed": reconstructed > organic,
            "organic": organic,
        })
        cursor = end

    organic_weeks = sum(1 for w in weeks if w["organic"])
    # Only statuses that were ever occupied: a band that is zero everywhere is a legend
    # entry for a series that does not exist (R3).
    statuses = [s for s in FUNNEL_ORDER if any(w["counts"][s] for w in weeks)]
    for week in weeks:
        # Aligned to `statuses`, so the table and the chart iterate the same list rather
        # than each looking the counts up their own way. `cells` is the stock view,
        # `flow` is what moved that week.
        week["cells"] = [week["counts"][s] for s in statuses]
        week["flow"] = [week["moves"][s] for s in statuses]
    return {
        "weeks": weeks,
        "statuses": statuses,
        "ready": organic_weeks >= ORGANIC_WEEKS_MIN,
        "organic_weeks": organic_weeks,
        "needs_weeks": ORGANIC_WEEKS_MIN,
        "reconstructed": sum(1 for w in weeks if w["reconstructed"]),
    }


def _company_coverage():
    """Where every tracked company stands (§5), from `Company.status`.

    Three states since 2026-09-28, because two could not tell "I have an application open
    with them" from "I have never done anything about them":

      applied    — an application actually submitted (COMPANY_APPLIED_TRIGGER_STATUSES)
      reviewing  — nothing submitted, but an application still live (`saved`/`reviewing`)
      watching   — nothing live at all

    R-C1 still applies and is sharper now: `watching` covers two different histories —
    never applied to, and every application closed or dropped without being sent. They mean
    the same thing about *now*, which is what this chart is about, but the chart says how
    many of each so the reading is not left to the reader.
    """
    counts = dict(Company.objects.values_list("status").annotate(n=Count("id")))
    total = Company.objects.count()
    return {
        "states": [{"status": status, "count": counts.get(status, 0)}
                  for status in COMPANY_STATUSES],
        "total": total,
        "submitted": counts.get("applied", 0),
        "reviewing": counts.get("reviewing", 0),
        "watching": counts.get("watching", 0),
        # Of the watched: how many were never acted on at all, versus tried and ended.
        "never": Company.objects.filter(applications__isnull=True).count(),
    }


def _applications_per_company():
    """How many companies carry 0, 1, 2, 3+ applications (§6).

    Replaces a companies-vs-applications pie, which charted two numbers that are not parts
    of a whole. R-A1: applications with no company are invisible to a per-company count,
    so the number excluded is returned with the buckets and shown whenever it is not zero.

    Each bucket carries the companies in it by name. A count answers "how many"; the names
    answer "which", which is the question anyone actually has next — and every bucket links
    into the companies list narrowed to itself, so the long ones are not truncated away.
    """
    rows = (Company.objects.annotate(n=Count("applications"))
            .order_by("-n", "name"))
    by_bucket: dict[str, list] = {"none": [], "1": [], "2": [], "3+": []}
    for company in rows:
        key = "none" if not company.n else "3+" if company.n >= 3 else str(company.n)
        by_bucket[key].append({"name": company.name, "slug": company.slug, "n": company.n})

    buckets = []
    # The short label is the axis tick; the phrase is what prose needs, because "none
    # application" is not a sentence and template pluralisation cannot rescue it.
    for key, phrase in (("none", "no applications"), ("1", "1 application"),
                        ("2", "2 applications"), ("3+", "3 or more applications")):
        companies = by_bucket[key]
        buckets.append({
            "label": key,
            "phrase": phrase,
            "count": len(companies),
            # Enough to recognise the bucket without turning the page into a directory.
            "companies": companies[:8],
            "more": max(0, len(companies) - 8),
        })
    return {
        "buckets": buckets,
        "companies": Company.objects.count(),
        "applications": Application.objects.count(),
        "unlinked": Application.objects.filter(company__isnull=True).count(),
    }


def _stats_volumes():
    """What there is to chart — the counts each chart's "can I draw this honestly?" turns on.

    One helper rather than a count per chart, because `/stats/` states these numbers
    beside the charts: a chart's refusal to draw and the readout that explains the
    refusal have to come from the same query or they will eventually disagree (plan R1,
    the same rule that keeps `/jobstudio status` and the dashboard in step).

    `transitions` is the sharp one, and it is not the number of status changes. A change
    with a blank `from_status` records where an application *entered* the tracker, not a
    move between two statuses. The example data root has three status changes and not one
    of them is a transition — so a flow diagram there has no ribbons at all and has to
    say so rather than draw something degenerate (plan R3, R-S1).
    """
    changes = ApplicationStatusChange.objects.count()
    entries = ApplicationStatusChange.objects.filter(from_status="").count()
    return {
        "applications": Application.objects.count(),
        "companies": Company.objects.count(),
        "status_changes": changes,
        "entries": entries,
        "transitions": changes - entries,
        # Nullable Application.company: a per-company chart covers fewer applications
        # than it claims unless it declares this one (plan R-A1).
        "unlinked": Application.objects.filter(company__isnull=True).count(),
        # What the ageing view (plan §7) has to work with.
        "at_applied": Application.objects.filter(status="applied").count(),
    }


def stats(request):
    """/stats/ — charts over the tracker's own history.

    A skeleton: no chart is built yet, and every slot renders the stated absence it will
    fall back to when there is nothing honest to draw. That is the part worth proving
    first — most people meet this page on a tracker with almost nothing in it, and a page
    that looks broken on day one is worse than one with fewer charts (plan R3).
    """
    rows = _ageing_at_applied()
    ageing = _ageing_bands(rows)
    flow = _status_flow()
    flow_post = _status_flow(POST_APPLICATION_ORDER)
    coverage = _company_coverage()
    per_company = _applications_per_company()
    stock = _status_stock()
    return render(request, "tracker/stats.html", {
        "page": "stats",
        "volumes": _stats_volumes(),
        "ageing": ageing,
        "flow": flow,
        "coverage": coverage,
        "per_company": per_company,
        "stock": stock,
        "flow_post": flow_post,
        "stale_applied": _stale_applied(rows),
        "stale_after_days": STALE_AFTER_DAYS,
        # One payload for the whole page: the view finishes every number and the client
        # only draws it (R2). `json_script` escapes it; nothing here is interpolated into
        # markup by hand.
        "chart_data": {
            "ageing": ageing,
            "flow": {"full": flow, "post": flow_post},
            "coverage": coverage,
            "perCompany": per_company,
            "stock": stock,
        },
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
    applications = _with_last_change(
        Application.objects.select_related("company", "area")).order_by(*BROWSE_ORDER)
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
        # Both are computed by scanning the folder, so resolve each once here
        # rather than letting the template re-walk it per access.
        "interviews": app.interview_files,
        # The status menu offers every status except the one it is already in.
        "other_statuses": [s for s in STATUS_SORT_ORDER if s != app.status],
        "siblings": (Application.objects.filter(company_name=app.company_name)
                     .exclude(pk=app.pk).order_by(*BROWSE_ORDER)),
    })


def company_list(request):
    """One table, not a tab per category (changed 2026-09-28).

    The tabs hid most of the tracker behind a click and made "which companies have I never
    applied to?" a question you had to ask nine times. Category became a column and a
    filter instead, which is what it always was: an attribute of a company, not a place
    where some companies live.
    """
    companies = (Company.objects.select_related("category")
                 .annotate(n_apps=Count("applications"))
                 .order_by("name"))
    return render(request, "tracker/company_list.html", {
        "page": "companies",
        "companies": companies,
        "categories": Category.objects.all(),
        "statuses": COMPANY_STATUSES,
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
        area.apps_list = _with_last_change(
            area.applications.select_related("company")).order_by(*BROWSE_ORDER)
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
