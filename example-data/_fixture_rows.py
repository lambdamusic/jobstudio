"""Create the example tracker rows, then let `tools/build-example-fixture` dump them.

Run through `manage.py shell` against a throwaway data root — never against a real one.

Why a script rather than hand-written JSON: since Phase 6 companies and applications
live only in the database, so the example's tracker content has to come from somewhere,
and a fixture typed by hand is only as valid as the typist's memory of the models. Built
through the ORM it is correct by construction, and it stays correct when the models
change — re-run this instead of editing JSON.

Areas and BaseCvs are NOT created here: `import_jobs` derives them from
jobs/targets/*.yaml and jobs/cv/base/*.md, which the example already ships.
"""

from datetime import date, datetime, time

from tracker.models import Application, Category, Company

# --- categories -------------------------------------------------------------
cats = {}
for order, name in enumerate(["Developer tools", "Data infrastructure", "Fintech"]):
    cats[name], _ = Category.objects.get_or_create(name=name, defaults={"order": order})

# --- companies --------------------------------------------------------------
# Real companies with public ATS boards, so `scan` works on a first run (§4).
COMPANIES = [
    dict(num=1, name="Grafana Labs", slug="grafana-labs",
         url="https://grafana.com/careers/", role_target="Developer Advocate",
         fit=4, category="Developer tools", date_added=date(2026, 9, 10),
         notes="Open-source observability. Real DevRel function, not marketing."),
    dict(num=2, name="dbt Labs", slug="dbt-labs",
         url="https://www.getdbt.com/careers", role_target="Solutions Engineer",
         fit=4, category="Data infrastructure", date_added=date(2026, 9, 12),
         notes="The enablement programme was teaching dbt for a year."),
    dict(num=3, name="Monzo", slug="monzo",
         url="https://monzo.com/careers/", role_target="Data Platform Engineer",
         fit=3, category="Fintech", date_added=date(2026, 9, 14),
         notes="Closest to the current job — the appeal and the problem."),
    # Watched, not applied to. More than one of these is load-bearing: several tests
    # need a company with no applications, and parametrised ones consume a fresh
    # company per subtest — with only one, the second subtest gets None.
    dict(num=4, name="Elastic", slug="elastic",
         url="https://www.elastic.co/careers/", role_target="Developer Advocate",
         fit=3, category="Developer tools", date_added=date(2026, 9, 16),
         notes="Search and observability. Watching for a UK-eligible DevRel opening."),
    dict(num=5, name="PostHog", slug="posthog",
         url="https://posthog.com/careers", role_target="Customer Success Engineer",
         fit=3, category="Developer tools", date_added=date(2026, 9, 17),
         notes="Open-source product analytics; unusually public engineering culture."),
    dict(num=6, name="Snowplow", slug="snowplow",
         url="https://snowplow.io/careers/", role_target="Solutions Architect",
         fit=2, category="Data infrastructure", date_added=date(2026, 9, 19),
         notes="Behavioural data pipelines — close to the Meridian event work."),
    # Added 2026-10-01 for `#64`. The example needs enough applications to fill a funnel
    # — one per status, with outcomes — and an application needs a company. Every board
    # token in scan-config.yaml was verified live against the real API when these were
    # added, so a first `scan` on the example actually fetches something.
    dict(num=7, name="Honeycomb", slug="honeycomb",
         url="https://www.honeycomb.io/careers", role_target="Developer Advocate",
         fit=4, category="Developer tools", date_added=date(2026, 7, 11),
         notes="Observability with a strong writing culture — the closest thing to the target role."),
    dict(num=8, name="Temporal", slug="temporal",
         url="https://temporal.io/careers", role_target="Developer Advocate",
         fit=3, category="Developer tools", date_added=date(2026, 8, 14),
         notes="Durable execution. Interesting product, small advocacy team."),
    dict(num=9, name="Supabase", slug="supabase",
         url="https://supabase.com/careers", role_target="Solutions Engineer",
         fit=3, category="Data infrastructure", date_added=date(2026, 8, 28),
         notes="Postgres as a platform. Mostly US hours, which is the open question."),
    dict(num=10, name="Fastly", slug="fastly",
         url="https://www.fastly.com/about/careers", role_target="Solutions Engineer",
         fit=3, category="Data infrastructure", date_added=date(2026, 7, 24),
         notes="Edge compute. Wrote it off once on scope, then the role was re-posted."),
    dict(num=11, name="Railway", slug="railway",
         url="https://railway.app/careers", role_target="Developer Advocate",
         fit=2, category="Developer tools", date_added=date(2026, 7, 18),
         notes="Deployment platform with a loud community. Small team, unclear seniority."),
]
for c in COMPANIES:
    cat = cats[c.pop("category")]
    Company.objects.update_or_create(num=c["num"], defaults={**c, "category": cat})

# --- applications -----------------------------------------------------------
APPLICATIONS = [
    dict(num=1, date=date(2026, 9, 15), company_name="Grafana Labs",
         role="Senior Developer Advocate",
         job_url="https://grafana.com/careers/", area_slug="developer-advocacy",
         status="applied", cv_base="functional", fit_level="strong",
         folder="jobs/applications/001-grafana-labs",
         summary="The target role: advocacy at a company whose product is already in the stack.",
         fit_pros="Real DevRel function\nOpen-source core\nSpeaking and writing count as work",
         fit_cons="Go is reading-level only\nObservability is adjacent, not held",
         fit_unknowns="Whether they want a Go engineer who speaks, or a speaker who reads Go",
         next_action="Follow up if nothing by 2026-09-29",
         history=[(date(2026, 9, 8), time(10, 12), "saved"),
                  (date(2026, 9, 11), time(9, 40), "reviewing"),
                  (date(2026, 9, 15), time(16, 22), "applied")]),
    dict(num=2, date=date(2026, 9, 18), company_name="dbt Labs",
         role="Solutions Engineer",
         job_url="https://www.getdbt.com/careers", area_slug="developer-advocacy",
         status="saved", cv_base="functional", fit_level="moderate",
         folder="jobs/applications/002-dbt-labs",
         summary="Closest to what I already do, but the role leans build-the-tool rather than teach-it.",
         fit_pros="Already in the ecosystem\nMaintain a package in their community",
         fit_cons="Solutions engineering is adjacent — paired on three onboardings, never owned one",
         fit_unknowns="How much of the role is pre-sales versus enablement",
         next_action="Decide by 2026-09-24",
         history=[(date(2026, 9, 18), time(11, 5), "saved")]),
    # No folder on disk and no company row: something spotted and logged in a hurry,
    # before `application` scaffolded anything. Realistic, and load-bearing — the tabs
    # test needs an application whose sections are genuinely empty, and leaving the
    # company FK null keeps three application-free companies for the status tests.
    dict(num=3, date=date(2026, 9, 20), company_name="Incident.io",
         role="Developer Advocate", job_url="https://incident.io/careers",
         area_slug="developer-advocacy", status="reviewing", cv_base="functional",
         fit_level="stretch", folder="",
         summary="Spotted on a scan — not yet looked at properly.",
         next_action="Read the posting",
         history=[(date(2026, 9, 20), time(8, 50), "saved"),
                  (date(2026, 9, 24), time(17, 30), "reviewing")]),

    # ---- added 2026-10-01 for `#64` ----------------------------------------
    # The six below exist to give the charts something true to draw. Before them the
    # example had three applications in three early statuses and no transitions at all,
    # so the status-flow Sankey had no status-to-status link, the post-applied view was
    # one node to one node, and the stock chart never reached `ready`. The shape that
    # matters is not the count — it is that every status in STATUS_SORT_ORDER is reached,
    # that outcomes exist (rejected, closed, discarded), and that one application moves
    # backwards.
    dict(num=4, date=date(2026, 8, 11), company_name="Monzo",
         role="Data Platform Engineer",
         job_url="https://monzo.com/careers/", area_slug="data-platform",
         status="interviewing", cv_base="functional", fit_level="moderate",
         folder="jobs/applications/004-monzo",
         summary="The sideways move: same work as now, better platform, no advocacy in it.",
         fit_pros="Platform at real scale\nStrong engineering culture\nLondon-based, hybrid",
         fit_cons="No writing or speaking in the role\nWould park the advocacy switch for two years",
         fit_unknowns="Whether the DX part of the remit is real or aspirational",
         next_action="Round 2 is booked — prep the SLO story and a view on their event schema",
         history=[(date(2026, 8, 3), time(9, 15), "saved"),
                  (date(2026, 8, 6), time(14, 20), "reviewing"),
                  (date(2026, 8, 11), time(10, 5), "applied"),
                  (date(2026, 8, 27), time(15, 45), "interviewing")]),
    dict(num=5, date=date(2026, 7, 20), company_name="Honeycomb",
         role="Developer Advocate",
         job_url="https://www.honeycomb.io/careers", area_slug="developer-advocacy",
         status="rejected", cv_base="functional", fit_level="strong",
         folder="jobs/applications/005-honeycomb",
         summary="The one that got away: right role, right company, too early in the switch.",
         fit_pros="Writing culture is the product\nObservability overlaps the SLO work",
         fit_cons="They wanted someone already speaking at conferences every month",
         fit_unknowns="Whether to ask what tipped it — worth doing, they were generous with feedback",
         next_action="Reapply when the talk count is higher — they said to",
         history=[(date(2026, 7, 14), time(9, 30), "saved"),
                  (date(2026, 7, 20), time(11, 15), "applied"),
                  (date(2026, 8, 5), time(8, 40), "rejected")]),
    # Discarded before applying, which is the case the post-applied Sankey view has to
    # exclude from its population rather than route through `applied` (`#56`).
    dict(num=6, date=date(2026, 8, 17), company_name="Temporal",
         role="Developer Advocate",
         job_url="https://temporal.io/careers", area_slug="developer-advocacy",
         status="discarded", cv_base="functional", fit_level="weak", folder="",
         summary="Read it properly and it is a conference-circuit job with a product attached.",
         fit_cons="Travel-heavy\nAdvocacy team of one, reporting into marketing",
         next_action="",
         history=[(date(2026, 8, 17), time(12, 40), "saved"),
                  (date(2026, 8, 20), time(9, 55), "reviewing"),
                  (date(2026, 8, 25), time(16, 10), "discarded")]),
    # Closed, not discarded: the deadline passed while it sat. A role can close before
    # you apply, which is why `closed` is deliberately outside the post-applied view.
    dict(num=7, date=date(2026, 9, 1), company_name="Supabase",
         role="Solutions Engineer",
         job_url="https://supabase.com/careers", area_slug="data-platform",
         status="closed", cv_base="functional", fit_level="moderate", folder="",
         summary="Sat on it over a fortnight deciding about the time zones, and it closed.",
         fit_cons="US hours\nThe deciding took longer than the posting lasted",
         next_action="",
         history=[(date(2026, 9, 1), time(10, 20), "saved"),
                  (date(2026, 9, 12), time(13, 35), "closed")]),
    # The backward move. Written off on scope, then re-posted with a wider remit and
    # picked back up — so its history runs `discarded -> reviewing`, against FUNNEL_ORDER.
    # That is what exercises the Sankey's cycle rule and the count of dropped edges; with
    # only forward histories that code path never runs on the example.
    dict(num=8, date=date(2026, 9, 22), company_name="Fastly",
         role="Senior Solutions Engineer",
         job_url="https://www.fastly.com/about/careers", area_slug="data-platform",
         status="applied", cv_base="chronological", fit_level="moderate", folder="",
         summary="Written off in July on scope; re-posted in September with the DX half added.",
         fit_pros="Edge compute is genuinely interesting\nThe new scope includes enablement",
         fit_cons="Still a pre-sales title\nSecond time reading it, so less sure of the read",
         fit_unknowns="Whether the DX half survives contact with a quota",
         next_action="Follow up if nothing by 2026-10-06",
         history=[(date(2026, 7, 28), time(9, 5), "saved"),
                  (date(2026, 7, 31), time(15, 10), "reviewing"),
                  (date(2026, 8, 4), time(11, 50), "discarded"),
                  (date(2026, 9, 2), time(10, 30), "reviewing"),
                  (date(2026, 9, 22), time(14, 15), "applied")]),
    # Applied and then nothing, long enough ago to be past STALE_AFTER_DAYS — so the
    # ageing list has a row that is actually flagged rather than a single fresh bar.
    dict(num=9, date=date(2026, 7, 27), company_name="Railway",
         role="Developer Advocate",
         job_url="https://railway.app/careers", area_slug="developer-advocacy",
         status="applied", cv_base="functional", fit_level="stretch", folder="",
         summary="Applied on a whim, heard nothing, and never chased it.",
         fit_pros="Loud community, real product",
         fit_cons="Small team\nNo stated seniority, which usually means junior",
         next_action="Chase or close it — it has been quiet too long",
         history=[(date(2026, 7, 21), time(10, 40), "saved"),
                  (date(2026, 7, 27), time(9, 25), "applied")]),
    # A second role at a company already applied to, which is both ordinary and the only
    # thing that puts anything in the applications-per-company histogram's "2" bucket —
    # with one application each, that chart is a single bar and says nothing.
    dict(num=10, date=date(2026, 9, 9), company_name="Honeycomb",
         role="Senior Technical Writer",
         job_url="https://www.honeycomb.io/careers", area_slug="developer-advocacy",
         status="discarded", cv_base="functional", fit_level="weak", folder="",
         summary="Came up a month after the advocacy rejection. Writing without the speaking.",
         fit_pros="Same company, same writing culture\nThey invited the application",
         fit_cons="Pure documentation role — a step away from the switch, not towards it",
         next_action="",
         history=[(date(2026, 9, 9), time(11, 30), "saved"),
                  (date(2026, 9, 16), time(9, 20), "discarded")]),
]

from django.utils import timezone

from tracker.models import Area, ApplicationStatusChange


def walk(app, history):
    """Drive one application through its transitions, then backdate each one.

    The `from_status -> to_status` pairing is produced by the real post-save signal
    (`models._log_status_change`), not re-implemented here — the same reason this whole
    file goes through the ORM rather than being typed as JSON. Only `changed_at` is set
    afterwards, which is exactly what that field is a plain `DateTimeField` for: its
    docstring says so, because the 2026-09-08 backfill needed the same thing.

    Why real timestamps and not midnight: `_status_stock` treats a change landing at
    exactly local midnight as reconstructed rather than observed, and a week whose
    changes are mostly reconstructed is shaded and excluded from the organic-week count
    the chart needs to render at all (`ORGANIC_WEEKS_MIN`). A fixture dated at midnight
    would therefore produce a chart that correctly refuses to draw itself. Each entry
    also sits on its own day, well under `BULK_DAY_MIN`, so no week reads as a bulk
    logging session.
    """
    for when, at, status in history:
        app.status = status
        app.save()
        stamped = timezone.make_aware(datetime.combine(when, at))
        # The row the signal just wrote for this transition.
        latest = app.status_changes.order_by("-pk").first()
        ApplicationStatusChange.objects.filter(pk=latest.pk).update(changed_at=stamped)


for a in APPLICATIONS:
    slug = a.pop("area_slug")
    history = a.pop("history", [])
    area = Area.objects.filter(slug=slug).first()
    company = Company.objects.filter(name=a["company_name"]).first()
    # Created at its FIRST status, then walked forward, so the stored `status` and the
    # company's derived status are both arrived at the way they would be in real use
    # rather than asserted.
    first_status = history[0][2] if history else a["status"]
    app, _ = Application.objects.update_or_create(
        num=a["num"], defaults={**a, "status": first_status, "area": area, "company": company})
    app.status_changes.all().delete()
    walk(app, history or [(a["date"], time(9, 0), a["status"])])

print(f"categories={Category.objects.count()} companies={Company.objects.count()} "
      f"applications={Application.objects.count()} areas={Area.objects.count()}")
