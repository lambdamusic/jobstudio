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

from datetime import date

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
         next_action="Follow up if nothing by 2026-09-29"),
    dict(num=2, date=date(2026, 9, 18), company_name="dbt Labs",
         role="Solutions Engineer",
         job_url="https://www.getdbt.com/careers", area_slug="developer-advocacy",
         status="saved", cv_base="functional", fit_level="moderate",
         folder="jobs/applications/002-dbt-labs",
         summary="Closest to what I already do, but the role leans build-the-tool rather than teach-it.",
         fit_pros="Already in the ecosystem\nMaintain a package in their community",
         fit_cons="Solutions engineering is adjacent — paired on three onboardings, never owned one",
         fit_unknowns="How much of the role is pre-sales versus enablement",
         next_action="Decide by 2026-09-24"),
    # No folder on disk and no company row: something spotted and logged in a hurry,
    # before `application` scaffolded anything. Realistic, and load-bearing — the tabs
    # test needs an application whose sections are genuinely empty, and leaving the
    # company FK null keeps three application-free companies for the status tests.
    dict(num=3, date=date(2026, 9, 20), company_name="Incident.io",
         role="Developer Advocate", job_url="https://incident.io/careers",
         area_slug="developer-advocacy", status="reviewing", cv_base="functional",
         fit_level="stretch", folder="",
         summary="Spotted on a scan — not yet looked at properly.",
         next_action="Read the posting"),
]

from tracker.models import Area

for a in APPLICATIONS:
    slug = a.pop("area_slug")
    area = Area.objects.filter(slug=slug).first()
    company = Company.objects.filter(name=a["company_name"]).first()
    Application.objects.update_or_create(
        num=a["num"], defaults={**a, "area": area, "company": company})

print(f"categories={Category.objects.count()} companies={Company.objects.count()} "
      f"applications={Application.objects.count()} areas={Area.objects.count()}")
