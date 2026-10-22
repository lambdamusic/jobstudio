"""Tests.

Since Phase 6 the database is the source of truth for applications and companies, so test
data comes from the committed synthetic fixture (example-data/backups/django/dump.json) rather than from parsing
markdown. The filesystem-derived parts — target YAMLs, CV files, cover letters, scans —
are still exercised against the real jobs/ tree, because the thing most likely to break
there is a file naming convention drifting.
"""

import datetime as dt
import re
import shutil
import tempfile
from io import StringIO
from unittest import mock
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db.models import Count
from django.test import TestCase
from django.utils import timezone
from django.utils.html import escape

import config
from appfolder import (COMPANY_APPLIED_TRIGGER_STATUSES,
                       COMPANY_REVIEWING_TRIGGER_STATUSES, COMPANY_STATUSES,
                       STATUS_SORT_ORDER, exported_file)
from tracker import parsers as P
from tracker.models import (Application, ApplicationStatusChange, Area, Category,
                            Company, Scan)

FIXTURE = ["dump.json"]


def start_from_empty():
    """Clear the loaded example so a test can state a whole-tracker property.

    Some assertions are only meaningful about a tracker whose entire contents the test
    controls: the *total* count of dropped edges, whether *anything* is stale, whether a
    status is occupied *at all*, whether the history is thin. Those used to lean on the
    shipped example being thin enough to supply the condition for free — and that is
    exactly what made the example impossible to improve. Filling it out for `#64` broke
    nine tests, every one of them really asserting "the example has no transitions"
    rather than the behaviour named in its own docstring.

    So the precondition gets stated rather than inherited. A test that needs an empty
    tracker says so here, and the example is then free to be as rich as a newcomer needs
    without the suite treating that as a regression.
    """
    Application.objects.all().delete()


class ParserTests(TestCase):
    """Only the filesystem parsers remain — the markdown tracker parsers went with
    applications.md and companies.md."""

    def test_split_scan_sections_and_unscored_location_split(self):
        sample = """# Portal Scan — 2026-01-01

## Summary
- Companies scanned: 1

## Matches

### data-platform

| Role | Location | CV Score | Ideal-Job Score | Notes |
|---|---|---|---|---|
| **Acme** — [Data Lead](https://example.com/a) | London (uk) | 4/5 | 4/5 | Good fit. |

## Unscored (no target profile for this category)

- **Foo Corp** — [Product Manager](https://example.com/foo) — London, UK
- **Bar Inc** — [Engineer](https://example.com/bar) — Seattle, WA, United States
- **Baz Ltd** — [Analyst](https://example.com/baz) — Mumbai, India

## Needs manual review (scoring failed)

_None._

## Not scanned

- **[Qux](https://example.com)** — bespoke career page
"""
        sections = P.split_scan_sections(sample)
        keys = [s["key"] for s in sections]
        self.assertIn("summary", keys)
        self.assertIn("unscored", keys)
        self.assertIn("not-scanned", keys)
        # An empty section body ("_None._") is dropped entirely — no dead tab.
        self.assertNotIn("needs-manual-review-scoring-failed", keys)
        # Matches is folded into Summary, not its own tab.
        self.assertNotIn("matches", keys)

        summary = next(s for s in sections if s["key"] == "summary")
        self.assertIn("Companies scanned: 1", summary["body"])
        self.assertIn("## Matches", summary["body"])
        self.assertIn("Acme", summary["body"])
        # Summary itself has no count of its own — it takes Matches' instead.
        self.assertEqual(summary["count"], 1)

        unscored = next(s for s in sections if s["key"] == "unscored")
        self.assertEqual(unscored["count"], 3)
        self.assertEqual(unscored["title"], "Unscored (no target profile for this category)")
        self.assertEqual(unscored["short_title"], "Unscored")

        likely, other = P.split_unscored_by_location(unscored["body"])
        self.assertEqual({e["company"] for e in likely}, {"Foo Corp"})
        self.assertEqual({e["company"] for e in other}, {"Bar Inc", "Baz Ltd"})

    def test_company_grouped_sections_get_short_titles_anchors_and_alpha_sort(self):
        sample = """# Portal Scan — 2026-01-01

## Strong matches

Grouped by company (alphabetical), sorted by combined score within each.

### Acme

*Data Platform → data-platform*

| Role | Location | Area Score | Ideal-Job Score | Notes |
|---|---|---|---|---|
| [Data Lead](https://example.com/a) | London (uk) | 4/5 | 4/5 | Good fit. |

### Strong matches — wrong location

- **Acme** — [Remote Lead](https://example.com/r) — Lagos, NG

## Filtered out before scoring

Grouped by company (alphabetical) with the full list.

### Acme (2)

*Data Platform*

- [Zulu Role](https://example.com/z)
- [Alpha Role](https://example.com/y)

### Beta Corp (1)

*Data Platform*

- [Only Role](https://example.com/w)
"""
        sections = P.split_scan_sections(sample)
        by_key = {s["key"]: s for s in sections}

        # Tab labels are shortened for the long headings, but the full heading survives
        # as `title` (rendered as the panel's own sub-heading).
        strong = by_key["strong-matches"]
        self.assertEqual(strong["short_title"], "Strong matches")
        filtered = by_key["filtered-out-before-scoring"]
        self.assertEqual(filtered["title"], "Filtered out before scoring")
        self.assertEqual(filtered["short_title"], "Filtered Out")

        # Strong matches: "Acme" is picked up as a company, the flat "wrong location"
        # bullet list is not, and postings keep their scan-portals.py order (score, not
        # alphabetised) since this isn't an ALPHA_SORT_KEYS section.
        self.assertEqual([c["name"] for c in strong["companies"]], ["Acme"])
        self.assertIn("### Strong matches — wrong location", strong["body"])

        # Filtered out: same company name as Strong matches, but anchors are unique
        # across the whole page (prefixed per section) and postings are alphabetised.
        self.assertEqual([c["name"] for c in filtered["companies"]], ["Acme", "Beta Corp"])
        anchors = {c["anchor"] for s in sections for c in s["companies"]}
        self.assertEqual(len(anchors), sum(len(s["companies"]) for s in sections))
        self.assertNotEqual(strong["companies"][0]["anchor"], filtered["companies"][0]["anchor"])
        alpha_idx = filtered["body"].index("Alpha Role")
        zulu_idx = filtered["body"].index("Zulu Role")
        self.assertLess(alpha_idx, zulu_idx)

        # Sections with no "### Company" grouping (Not scanned, Coverage notes, etc.)
        # get no jump-to-company summary.
        self.assertEqual(by_key["strong-matches"]["companies"][0]["count"], None)
        self.assertEqual(by_key["filtered-out-before-scoring"]["companies"][0]["count"], 2)

    def test_every_target_yaml_becomes_an_area(self):
        targets = P.parse_targets(Path(settings.TARGETS_DIR))
        self.assertGreater(len(targets), 0)
        for t in targets:
            self.assertTrue(t["name"])
            self.assertIsInstance(t["emphasis"], list)

    def test_target_yaml_has_no_unquoted_colon_entries(self):
        """Guards the source files, not just the parser.

        An unquoted list entry containing ': ' parses as a mapping rather than a
        string. `parsers._flatten_yaml_list()` normalises that back for the web app's
        target display, but relying on the normaliser instead of clean source data is
        fragile — quote such entries in the YAML itself.
        """
        import yaml
        for path in sorted(Path(settings.TARGETS_DIR).glob("*.yaml")):
            data = yaml.safe_load(path.read_text())
            for key in ("emphasis", "key_terms", "excludes",
                        "expand_sections", "condense_sections"):
                for item in (data.get(key) or []):
                    with self.subTest(file=path.name, key=key):
                        self.assertIsInstance(
                            item, str,
                            f"{path.name}: {key} entry parsed as {type(item).__name__} — "
                            f"wrap it in quotes: {item}")

    def test_yaml_list_entries_are_always_strings(self):
        """Unquoted 'Key: value' YAML entries parse as dicts; they must be rejoined."""
        self.assertEqual(P._flatten_yaml_list([{"SN SciGraph": "1B+ facts"}, "plain"]),
                         ["SN SciGraph: 1B+ facts", "plain"])
        for t in P.parse_targets(Path(settings.TARGETS_DIR)):
            for key in ("emphasis", "key_terms", "excludes",
                        "expand_sections", "condense_sections"):
                for item in t[key]:
                    self.assertIsInstance(item, str, f"{t['slug']}.{key}")


class ImportJobsTests(TestCase):
    fixtures = FIXTURE

    def test_import_is_idempotent(self):
        call_command("import_jobs", quiet=True, stdout=StringIO())
        out = StringIO()
        call_command("import_jobs", quiet=True, stdout=out)
        for line in out.getvalue().splitlines():
            for verb in (" created", " updated", " deleted"):
                self.assertNotIn(verb, line.replace(f" 0{verb}", ""), f"second run changed rows: {line}")

    def test_import_does_not_touch_applications_or_companies(self):
        """import_jobs refreshes only what is derived from files. Applications and
        companies are DB-owned now, and it must never prune them."""
        before = (Application.objects.count(), Company.objects.count())
        call_command("import_jobs", quiet=True, stdout=StringIO())
        self.assertEqual((Application.objects.count(), Company.objects.count()), before)


class DataTests(TestCase):
    fixtures = FIXTURE

    def test_applications_link_to_areas(self):
        self.assertEqual(list(Application.objects.filter(area__isnull=True)), [])

    def test_folders_resolve_on_disk(self):
        for app in Application.objects.exclude(folder=""):
            self.assertIsNotNone(app.folder_path, f"#{app.num} folder path does not resolve")

    def test_model_default_order_matches_status_order(self):
        ranks = [STATUS_SORT_ORDER.index(s)
                 for s in Application.objects.values_list("status", flat=True)]
        self.assertEqual(ranks, sorted(ranks))

    def test_area_abbreviations(self):
        """Derived from the slug's first two words, so any user's areas get a pill.

        This asserted a fixed table of five slugs until 2026-09-21 — which meant it
        only ever tested one person's areas, and passed vacuously for everyone else's.
        """
        self.assertEqual(Area(slug="data-platform").abbr, "DP")
        self.assertEqual(Area(slug="developer-advocacy").abbr, "DA")
        self.assertEqual(Area(slug="research").abbr, "R")
        self.assertEqual(Area(slug="ai-knowledge-work").abbr, "AK",
                         "only the first two words count, so a third is ignored")
        for area in Area.objects.all():
            self.assertTrue(1 <= len(area.abbr) <= 2, f"{area.slug} -> {area.abbr!r}")
            self.assertTrue(area.abbr.isupper(), area.abbr)


class CompanyStatusTests(TestCase):
    """Three states since 2026-09-28. `applied` requires an application that was actually
    submitted (COMPANY_APPLIED_TRIGGER_STATUSES) — not merely logged (decided 2026-09-08);
    `reviewing` is a live application that has not been sent; `watching` is everything
    else, which covers both "never applied to" and "every application ended without being
    sent"."""

    fixtures = FIXTURE

    def test_every_status_is_in_the_model(self):
        for company in Company.objects.all():
            self.assertIn(company.status, COMPANY_STATUSES, company.name)

    def test_status_matches_trigger_statuses(self):
        for company in Company.objects.all():
            if company.applications.filter(status__in=COMPANY_APPLIED_TRIGGER_STATUSES).exists():
                expected = "applied"
            elif company.applications.filter(status__in=COMPANY_REVIEWING_TRIGGER_STATUSES).exists():
                expected = "reviewing"
            else:
                expected = "watching"
            self.assertEqual(company.status, expected, company.name)

    def test_status_updates_when_a_submitted_application_is_added(self):
        company = Company.objects.filter(applications__isnull=True).first()
        self.assertEqual(company.status, "watching")
        Application.objects.create(
            num=9001, company=company, company_name=company.name,
            role="Test", status="applied")
        company.refresh_from_db()
        self.assertEqual(company.status, "applied")

    def test_saved_or_reviewing_makes_a_company_reviewing_not_applied(self):
        """A `saved`/`reviewing` row is a live application that has not been sent. It must
        not flip the company to `applied` — but it is not nothing either, which is what the
        two-state model used to say about it."""
        for num, status in [(9006, "saved"), (9007, "reviewing")]:
            with self.subTest(status=status):
                company = Company.objects.filter(applications__isnull=True).first()
                Application.objects.create(num=num, company=company,
                                           company_name=company.name,
                                           role="Test", status=status)
                company.refresh_from_db()
                self.assertEqual(company.status, "reviewing")

    def test_a_submitted_application_outranks_a_live_one(self):
        """A company with both keeps the stronger claim: it has been applied to."""
        company = Company.objects.filter(applications__isnull=True).first()
        Application.objects.create(num=9008, company=company, company_name=company.name,
                                   role="Saved one", status="saved")
        Application.objects.create(num=9009, company=company, company_name=company.name,
                                   role="Sent one", status="applied")
        company.refresh_from_db()
        self.assertEqual(company.status, "applied")

    def test_rejected_application_still_counts_as_applied(self):
        """A rejection does not revert a company to `watching` — the application still
        happened, and that is what the company row records."""
        company = Company.objects.filter(applications__isnull=True).first()
        Application.objects.create(num=9003, company=company, company_name=company.name,
                                   role="Test", status="rejected")
        company.refresh_from_db()
        self.assertEqual(company.status, "applied")

    def test_closed_and_discarded_leave_a_company_watching(self):
        """`closed` (deadline passed before applying) and `discarded` (dropped before
        applying) both mean no application was ever submitted and none is live — so the
        company reads the same as one that was never applied to, which is the truth about
        where it stands now."""
        for num, status in [(9004, "closed"), (9005, "discarded")]:
            with self.subTest(status=status):
                company = Company.objects.filter(applications__isnull=True).first()
                Application.objects.create(num=num, company=company,
                                           company_name=company.name,
                                           role="Test", status=status)
                company.refresh_from_db()
                self.assertEqual(company.status, "watching")

    def test_status_reverts_when_the_last_qualifying_application_goes(self):
        company = Company.objects.filter(applications__isnull=True).first()
        app = Application.objects.create(
            num=9002, company=company, company_name=company.name,
            role="Test", status="applied")
        company.refresh_from_db()
        self.assertEqual(company.status, "applied")
        app.delete()
        company.refresh_from_db()
        self.assertEqual(company.status, "watching")


class ApplicationStatusChangeTests(TestCase):
    """The History tab's data — written by the post_save signal in models.py, never by
    hand (decided 2026-09-08: status changes only, not document adds/edits)."""

    fixtures = FIXTURE

    def _make(self, num=9101, status="saved"):
        return Application.objects.create(num=num, company_name="Test Co",
                                          role="Test", status=status)

    def test_creating_an_application_logs_the_initial_status(self):
        app = self._make()
        changes = list(app.status_changes.all())
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].from_status, "")
        self.assertEqual(changes[0].to_status, "saved")

    def test_changing_status_appends_a_transition(self):
        app = self._make()
        app.status = "reviewing"
        app.save()
        app.status = "applied"
        app.save()
        changes = list(app.status_changes.all())  # newest first (Meta.ordering)
        self.assertEqual([(c.from_status, c.to_status) for c in changes],
                         [("reviewing", "applied"), ("saved", "reviewing"), ("", "saved")])

    def test_saving_without_a_status_change_does_not_duplicate(self):
        """Application.save() always fires (it recomputes status_order on every save),
        so a no-op status must not append a new row each time."""
        app = self._make()
        app.next_action = "Follow up"
        app.save()
        app.save()
        self.assertEqual(app.status_changes.count(), 1)

    def test_deleting_an_application_deletes_its_history(self):
        app = self._make()
        pk = app.pk
        app.delete()
        self.assertFalse(ApplicationStatusChange.objects.filter(application_id=pk).exists())


class AdminTests(TestCase):
    fixtures = FIXTURE

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        cls.user = User.objects.create_superuser("smoke_test", "smoke@example.com", "x")

    def setUp(self):
        self.client.force_login(self.user)

    def test_changelists_render(self):
        for url in ["/admin/", "/admin/tracker/application/", "/admin/tracker/company/",
                    "/admin/tracker/area/", "/admin/tracker/category/",
                    "/admin/tracker/scan/",
                    "/admin/cvs/basecv/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_change_pages_render(self):
        for model, obj in [("application", Application.objects.first()),
                           ("company", Company.objects.first()),
                           ("area", Area.objects.first())]:
            with self.subTest(model=model):
                r = self.client.get(f"/admin/tracker/{model}/{obj.pk}/change/")
                self.assertEqual(r.status_code, 200)

    def test_no_stage_a_banner(self):
        """The markdown-is-truth warning is gone — the admin is authoritative now."""
        html = self.client.get("/admin/tracker/application/").content.decode()
        self.assertNotIn("source of truth", html)

    def test_status_edit_persists(self):
        """The behaviour the whole flip was for: a status change made in the admin sticks,
        and is not undone by the next import."""
        app = Application.objects.get(num=1)
        original = app.status
        app.status = "interviewing"
        app.save()

        call_command("import_jobs", quiet=True, stdout=StringIO())

        app.refresh_from_db()
        self.assertEqual(app.status, "interviewing")
        self.assertNotEqual(app.status, original)
        self.assertEqual(app.status_order, STATUS_SORT_ORDER.index("interviewing"))


class MarkupTests(TestCase):
    """Every page's HTML nests correctly.

    Added 2026-09-23 after a stray `</div>` in base.html closed the sidebar early: the
    whole suite stayed green while the layout was visibly broken, because every other
    test asserts *content* — status codes and substrings — and an unbalanced tag changes
    neither. Only the browser caught it, and only because someone looked.
    """

    fixtures = FIXTURE

    # Tags with no closing form; anything else must be closed in the right order.
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}

    def assert_balanced(self, html, url):
        from html.parser import HTMLParser

        stack, errors = [], []

        class Checker(HTMLParser):
            def handle_starttag(inner, tag, attrs):
                if tag not in MarkupTests.VOID:
                    stack.append((tag, inner.getpos()[0]))

            def handle_startendtag(inner, tag, attrs):
                pass  # self-closing, e.g. <path .../> in the brand SVG

            def handle_endtag(inner, tag):
                if tag in MarkupTests.VOID:
                    return
                if not stack:
                    errors.append(f"line {inner.getpos()[0]}: </{tag}> with nothing open")
                elif stack[-1][0] != tag:
                    errors.append(
                        f"line {inner.getpos()[0]}: </{tag}> closes <{stack[-1][0]}> "
                        f"opened on line {stack[-1][1]}")
                    stack.pop()
                else:
                    stack.pop()

        Checker(convert_charrefs=True).feed(html)
        unclosed = [f"<{tag}> opened on line {line} and never closed" for tag, line in stack]
        self.assertEqual(errors + unclosed, [], f"malformed HTML on {url}")

    def test_every_page_nests_correctly(self):
        app = Application.objects.first()
        company = Company.objects.first()
        for url in ["/", "/applications/", "/applications/all/", f"/applications/{app.num}/",
                    "/companies/", f"/companies/{company.slug}/", "/areas/", "/stats/",
                    "/cvs/", "/notes/", "/profile/", "/scans/", "/scans/all/"]:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assert_balanced(r.content.decode(), url)


class BrandTests(TestCase):
    """The sidebar lockup (`#32`)."""

    fixtures = FIXTURE

    def test_the_wordmark_matches_the_app_name(self):
        """The lockup DRAWS the name rather than interpolating it — a fixed-width SVG
        cannot absorb a longer string without overrunning its viewBox. That is a
        deliberate exception to APP_NAME being the single definition, so this is the
        thing that stops the two drifting apart silently."""
        from django.conf import settings

        template = Path(settings.TEMPLATES[0]["DIRS"][0]) / "base.html"
        drawn = "".join(re.findall(r"<tspan[^>]*>([^<]*)</tspan>", template.read_text()))
        self.assertTrue(drawn, f"no <tspan> wordmark found in {template}")
        self.assertEqual(drawn.strip(), settings.APP_NAME)

    def test_every_nav_icon_points_at_a_symbol_that_exists(self):
        """`#31`. A typo in a <use href> renders precisely nothing — no error, no missing
        text, just a gap where a glyph should be. Nothing else in the suite would notice."""
        html = self.client.get("/").content.decode()
        used = set(re.findall(r'<use href="#([\w-]+)"', html))
        defined = set(re.findall(r'<g id="([\w-]+)"', html))
        self.assertTrue(used, "no nav icons rendered at all")
        self.assertEqual(used - defined, set(), "referenced icons that are not defined")

    def test_sub_items_carry_no_icon(self):
        """Sub-items are indented instead; a second column of glyphs would flatten the
        hierarchy the indent exists to show."""
        html = self.client.get("/").content.decode()
        for row in re.findall(r'<a[^>]*class="nav-sub[^"]*"[^>]*>(.*?)</a>', html, re.S):
            with self.subTest(row=row.strip()[:40]):
                self.assertNotIn("<use", row)

    def test_the_sidebar_renders_the_lockup_on_every_page(self):
        for url in ["/", "/applications/", "/companies/", "/cvs/"]:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertIn('class="brand-mark"', html)
                self.assertIn(f'aria-label="{settings.APP_NAME}"', html)


class ScanCoverageTests(TestCase):
    """`#30` — the companies list says whether `scan` picks each company up.

    Runs against example-data/jobs/scan-config.yaml, which the suite is pinned to, so
    these also guard the config file's shape.
    """

    fixtures = FIXTURE

    def test_an_override_makes_a_company_scanned(self):
        """Grafana Labs' tracked URL reveals no ATS; the override is what finds it."""
        import scan_sources
        cov = scan_sources.coverage("Grafana Labs", "https://grafana.com/about/careers/")
        self.assertTrue(cov["scanned"])
        self.assertEqual(cov["platform"], "greenhouse")

    def test_a_board_url_is_detected_without_any_config(self):
        import scan_sources
        cov = scan_sources.coverage("Unknown Co", "https://jobs.lever.co/unknownco")
        self.assertTrue(cov["scanned"])
        self.assertEqual(cov["platform"], "lever")

    def test_a_known_unsupported_company_reports_its_own_reason(self):
        """The hand-written reason is the point — it separates "no fetcher yet" from
        "nobody has looked", which the generic fallback cannot."""
        import scan_sources
        # The example's entry named BambooHR until 2026-10-01, which stopped being true
        # when the BambooHR fetcher landed — `known_unsupported` is only consulted when no
        # ATS resolves, so the example was teaching the opposite of the truth. Replaced
        # with an ATS that genuinely has no fetcher.
        cov = scan_sources.coverage("Meridian Civic Trust", "https://example.com/careers")
        self.assertFalse(cov["scanned"])
        self.assertIn("Oleeo", cov["reason"])

    def test_an_excluded_company_is_not_scanned_even_with_an_override(self):
        """`excluded_companies` is a decision, not a capability gap: it wins over a
        working override, and says so in its own words."""
        import scan_config
        import scan_sources
        with mock.patch.object(scan_config, "excluded_companies",
                               return_value={"Grafana Labs": "not interested"}):
            cov = scan_sources.coverage("Grafana Labs", "https://grafana.com/about/careers/")
        self.assertFalse(cov["scanned"])
        self.assertEqual(cov["reason"], "excluded from scans — not interested")

    def test_no_url_is_its_own_reason_not_the_bespoke_fallback(self):
        import scan_sources
        cov = scan_sources.coverage("Nobody Ltd", "")
        self.assertFalse(cov["scanned"])
        self.assertEqual(cov["reason"], scan_sources.NO_URL)

    def test_a_careers_link_appears_only_where_scanning_cannot_help(self):
        """`#34`. The shortcut belongs on the rows that have to be checked by hand. On a
        scanned row it would be noise, and a row with no URL has nothing to link to."""
        html = self.client.get("/companies/").content.decode()
        for company in Company.objects.all():
            with self.subTest(company=company.name):
                link = f'href="{escape(company.url)}" target="_blank"'
                wanted = bool(company.url) and not company.scan_coverage["scanned"]
                if wanted:
                    self.assertIn(link, html)
                else:
                    self.assertNotIn(link, html)

    def test_the_companies_page_shows_a_platform_or_a_reason_for_every_row(self):
        html = self.client.get("/companies/").content.decode()
        for company in Company.objects.all():
            with self.subTest(company=company.name):
                cov = company.scan_coverage
                expected = cov["platform"] if cov["scanned"] else cov["reason"]
                self.assertIn(escape(expected), html)

    def test_scan_state_keeps_the_missing_url_apart(self):
        """`#53`/`#54`. Three keys, not two: "no URL" is the one-minute fix."""
        cases = {
            "yes": Company(num=9400, name="Unknown Co", url="https://jobs.lever.co/unknownco"),
            "no": Company(num=9401, name="Bespoke Co", url="https://example.org/careers"),
            "no-url": Company(num=9402, name="Nobody Ltd", url=""),
        }
        for state, company in cases.items():
            with self.subTest(state=state):
                self.assertEqual(company.scan_state, state)

    def test_the_company_page_carries_a_scan_badge_for_every_state(self):
        """`#53`. Each state gets its own badge, linking into the filtered list; a company
        with no URL at all must render rather than crash the lede."""
        made = {
            "yes": ("https://jobs.lever.co/unknownco", "scanned · lever"),
            "no": ("https://example.org/careers", "not scanned"),
            "no-url": ("", "no careers URL"),
        }
        for i, (state, (url, text)) in enumerate(made.items()):
            company = Company.objects.create(num=9410 + i, name=f"Badge Co {i}",
                                             slug=f"badge-co-{i}", url=url)
            with self.subTest(state=state):
                html = self.client.get(f"/companies/{company.slug}/").content.decode()
                self.assertIn(f'class="badge scan-{state}" href="/companies/#scanned={state}"', html)
                self.assertIn(text, html)


class StatusActionTests(TestCase):
    """The local-only status menu on the application detail page (`#28`, 2026-09-23).

    Replaced a single hardcoded "Mark reviewing" link; these guard the two things that
    replacement could get wrong — accepting a status the rest of the app doesn't know,
    and losing the History log that the post_save signal writes.
    """

    fixtures = FIXTURE

    def test_every_status_can_be_set_from_the_url(self):
        for status in STATUS_SORT_ORDER:
            with self.subTest(status=status):
                r = self.client.get(f"/actions/set-status/1/{status}/")
                self.assertEqual(r.status_code, 302)
                self.assertEqual(Application.objects.get(num=1).status, status)

    def test_an_unknown_status_404s_rather_than_being_written(self):
        """The status arrives from the URL, so it is input, not a given."""
        before = Application.objects.get(num=1).status
        self.assertEqual(self.client.get("/actions/set-status/1/banana/").status_code, 404)
        self.assertEqual(Application.objects.get(num=1).status, before)

    def test_setting_a_status_keeps_status_order_and_logs_the_change(self):
        app = Application.objects.get(num=1)
        self.client.get(f"/actions/set-status/{app.num}/interviewing/")
        app.refresh_from_db()
        self.assertEqual(app.status_order, STATUS_SORT_ORDER.index("interviewing"))
        self.assertTrue(ApplicationStatusChange.objects.filter(
            application=app, to_status="interviewing").exists())

    def test_the_menu_offers_every_status_except_the_current_one(self):
        app = Application.objects.get(num=1)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        for status in STATUS_SORT_ORDER:
            with self.subTest(status=status):
                link = f"/actions/set-status/{app.num}/{status}/"
                if status == app.status:
                    self.assertNotIn(link, html)
                else:
                    self.assertIn(link, html)


def markdownify_path(md):
    from tracker.templatetags.jobs_extras import markdownify
    return markdownify(md)


class ViewTests(TestCase):
    fixtures = FIXTURE

    def test_index_pages(self):
        for url in ["/", "/applications/", "/applications/all/", "/applications/active/",
                    "/companies/", "/areas/", "/stats/", "/cvs/", "/notes/", "/scans/",
                    "/scans/all/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_every_application_detail_renders(self):
        for app in Application.objects.all():
            with self.subTest(num=app.num):
                r = self.client.get(f"/applications/{app.num}/")
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, escape(app.role))

    def test_every_company_detail_renders(self):
        for company in Company.objects.all():
            with self.subTest(slug=company.slug):
                self.assertEqual(self.client.get(f"/companies/{company.slug}/").status_code, 200)

    def test_areas_page_has_every_area_as_a_tab(self):
        """No more /areas/<slug>/ detail page (folded into /areas/'s tabs, 2026-09-14) —
        every area's full content (name, and each of its applications) should be on the
        one page instead."""
        r = self.client.get("/areas/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        for area in Area.objects.all():
            with self.subTest(slug=area.slug):
                self.assertIn(f'data-tab="{area.slug}"', html)
                self.assertIn(escape(area.name), html)
                for app in area.applications.all():
                    self.assertIn(f'/applications/{app.num}/', html)

    def test_every_cv_detail_renders(self):
        from cvs.models import BaseCv
        for cv in BaseCv.objects.all():
            with self.subTest(slug=cv.slug):
                self.assertEqual(self.client.get(f"/cvs/base/{cv.slug}/").status_code, 200)

    def test_every_scan_renders(self):
        for scan in Scan.objects.all():
            with self.subTest(label=scan.label):
                self.assertEqual(self.client.get(f"/scans/{scan.label}/").status_code, 200)

    def test_scan_bare_path_shows_latest_report(self):
        latest = Scan.objects.first()
        r = self.client.get("/scans/")
        self.assertEqual(r.status_code, 200)
        if latest is not None:
            self.assertEqual(r.context["scan"], latest)
            self.assertContains(r, latest.label)

    def test_scan_all_lists_every_report(self):
        r = self.client.get("/scans/all/")
        self.assertEqual(r.status_code, 200)
        for scan in Scan.objects.all():
            with self.subTest(label=scan.label):
                self.assertContains(r, scan.label)

    def test_notes_render(self):
        self.assertEqual(self.client.get("/notes/").status_code, 200)
        for slug in ["ideal-job-notes"]:
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(f"/notes/{slug}/").status_code, 200)

    # ---- /notes/ as one tab per group, each an index (2026-10-08, replacing `#73`) ----

    def test_notes_page_has_one_tab_per_group_indexing_its_notes(self):
        """A group is a subfolder of jobs/notes/. Each group's tab lists its notes, each
        linking the note's own page; the notes themselves are not rendered here."""
        from tracker.views import _note_group, _notes_files

        html = self.client.get("/notes/").content.decode()
        paths = _notes_files()
        self.assertTrue(paths, "no notes in the example data")
        for path in paths:
            group = _note_group(path) or "other"
            with self.subTest(slug=path.stem):
                self.assertIn(f'data-tab="{group}"', html)
                panel = html[html.index(f'data-panel="{group}"'):]
                self.assertIn(f'href="/notes/{path.stem}/"', panel[:panel.index("</section>")])

    def test_notes_in_group_folders_keep_flat_urls_and_show_what_they_were_written_for(self):
        """Grouping is the folder; the URL is the filename alone, so moving a note between
        groups never breaks a link. "First written for" is the first application the
        note's own opening links — not every folder that links back, a list that only grew."""
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        notes = root / "jobs" / "notes"
        (notes / "topics").mkdir(parents=True)
        (notes / "topics" / "graph-basics.md").write_text(
            "# Graph basics\n\n*Started for [a round](/applications/1/); kept for the next.*\n\n"
            "## One\n\nAlso used in [another](/applications/2/).\n")
        (notes / "loose.md").write_text("# Loose note\n\nNo group.\n")
        (notes / "interviewing").mkdir()
        (notes / "interviewing" / "answer-bank.md").write_text("# Answer bank\n\nAnswers.\n")
        (notes / "topics" / "data-architecture").mkdir()
        (notes / "topics" / "data-architecture" / "energy-markets.md").write_text("# Energy markets\n\nX.\n")
        (notes / "search" / "recruiter-leads").mkdir(parents=True)
        (notes / "search" / "recruiter-leads" / "agencies.md").write_text("# Agencies\n\nY.\n")
        (notes / "search" / "aims.md").write_text("# Aims\n\nZ.\n")
        folder = root / "jobs" / "applications" / "900-test-co"
        folder.mkdir(parents=True)
        (folder / "notes.md").write_text("# Test\n\nSee [graph basics](/notes/graph-basics/).\n")
        app = Application.objects.get(num=1)
        app.folder = "jobs/applications/900-test-co"
        app.save()
        with override_settings(DATA_ROOT=str(root), NOTES_DIR=str(notes)):
            listed = self.client.get("/notes/").content.decode()
            self.assertIn('data-tab="topics"', listed)
            self.assertIn('data-tab="other"', listed)
            # interviewing/ has no tab of its own: it opens the Topics tab (2026-10-13).
            self.assertNotIn('data-tab="interviewing"', listed)
            panel = listed[listed.index('data-panel="topics"'):]
            panel = panel[:panel.index("</section>")]
            # Sections by subfolder: the named ones in order, a note straight in topics/
            # last as "Other notes"; nested notes keep the flat URL.
            order = [panel.index(x) for x in (">Me: answers and my work ", 'href="/notes/answer-bank/"',
                                              ">Data architecture ", 'href="/notes/energy-markets/"',
                                              ">Other notes ", 'href="/notes/graph-basics/"')]
            self.assertEqual(order, sorted(order))
            # An unlisted subfolder of search/ is a section named after it; the notes
            # straight in search/ come after it, as "Other notes" (2026-10-22).
            search = listed[listed.index('data-panel="search"'):]
            search = search[:search.index("</section>")]
            order = [search.index(x) for x in (">Recruiter leads ", 'href="/notes/agencies/"',
                                               ">Other notes ", 'href="/notes/aims/"')]
            self.assertEqual(order, sorted(order))
            self.assertNotIn("Other search", search)
            self.assertEqual(self.client.get("/notes/energy-markets/").status_code, 200)
            self.assertIn("Started for a round; kept for the next.", listed)
            self.assertIn(f'href="/applications/{app.num}/"', listed)
            page = self.client.get("/notes/graph-basics/").content.decode()
            self.assertIn("First written for", page)
            head = page[page.index("First written for"):page.index("</p>", page.index("First written for"))]
            self.assertIn('href="/applications/1/"', head)
            self.assertNotIn('href="/applications/2/"', head)
            self.assertNotIn("First written for", self.client.get("/notes/energy-markets/").content.decode())
            self.assertIn('href="/notes/graph-basics/"',
                          markdownify_path("`jobs/notes/topics/graph-basics.md`"))
            self.assertIn('href="/notes/graph-basics/"', markdownify_path("`graph-basics.md`"))

    def test_note_images_are_served_from_beside_the_note_and_nowhere_else(self):
        """A relative image path in a note resolves against the note's folder. Only
        images, and only inside jobs/notes/: no markdown, no climbing out with `..`."""
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        notes = root / "jobs" / "notes"
        (notes / "topics" / "img").mkdir(parents=True)
        (notes / "topics" / "graph-basics.md").write_text(
            "# Graph basics\n\n![diagram](img/arch.png)\n")
        (notes / "topics" / "img" / "arch.png").write_bytes(b"\x89PNG\r\n")
        (root / "secret.png").write_bytes(b"\x89PNG\r\n")
        with override_settings(DATA_ROOT=str(root), NOTES_DIR=str(notes)):
            page = self.client.get("/notes/graph-basics/").content.decode()
            self.assertIn('src="img/arch.png"', page)
            self.assertEqual(self.client.get("/notes/graph-basics/img/arch.png").status_code, 200)
            self.assertEqual(self.client.get("/notes/graph-basics/graph-basics.md").status_code, 404)
            self.assertEqual(self.client.get("/notes/graph-basics/../../../secret.png").status_code, 404)
            self.assertEqual(self.client.get("/notes/graph-basics/img/missing.png").status_code, 404)

    def test_note_titles_come_from_the_file_not_the_filename(self):
        """`ai-safety-pivot`.title() is "Ai Safety Pivot". The file says what it is called;
        the slug is only the fallback."""
        self.assertEqual(P.first_heading("# AI safety pivot\n\nbody"), "AI safety pivot")
        self.assertEqual(P.first_heading("no heading here"), "")
        # A title's trailing description is cut for the tab, kept for the heading.
        self.assertEqual(P.short_title("Product Discovery — technique and evidence"),
                         "Product Discovery")
        self.assertEqual(P.short_title("Recruiter Leads"), "Recruiter Leads")

    def test_section_label_strips_emphasis_and_code_spans(self):
        """A note whose subheadings are written `### **Trend 1 — ...**` showed its
        asterisks in every pill. Paired delimiters only — a lone `*` stays a literal."""
        self.assertEqual(P.section_label("**Trend 1 — delivery mode**"),
                         "Trend 1 — delivery mode")
        self.assertEqual(P.section_label("4. *Performance* and `latency`"),
                         "Performance and latency")
        self.assertEqual(P.section_label("A 5 * 3 grid"), "A 5 * 3 grid")

    def test_every_id_on_the_notes_page_is_unique(self):
        """The coach tab stacks several documents on this page, so their anchors have to
        stay distinct — `tabs.js` resolves an inbound anchor by finding the panel holding
        it, so a collision would open the wrong one."""
        html = self.client.get("/notes/").content.decode()
        ids = re.findall(r'id="([^"]+)"', html)
        dupes = {i for i in ids if ids.count(i) > 1}
        self.assertEqual(dupes, set(), f"duplicate ids: {sorted(dupes)}")

    def test_a_notes_section_anchors_are_prefixed_by_its_slug(self):
        """Section ids on a note's page start `<slug>--`, so a link to a section stays
        unique wherever the note is shown, and survives a move between groups."""
        from tracker.views import _notes_files

        for path in _notes_files():
            single = self.client.get(f"/notes/{path.stem}/").content.decode()
            with self.subTest(slug=path.stem):
                self.assertTrue(re.findall(r'id="(%s--[^"]+)"' % re.escape(path.stem), single))

    def test_the_per_note_pages_survive(self):
        """`build_static` publishes one page per note: they are where a note is read, and
        the honest target for a link from outside the app."""
        from tracker.management.commands.build_static import site_urls
        from tracker.views import _notes_files

        urls = site_urls()
        for path in _notes_files():
            with self.subTest(slug=path.stem):
                self.assertIn(f"/notes/{path.stem}/", urls)
                self.assertEqual(self.client.get(f"/notes/{path.stem}/").status_code, 200)

    def test_profile_renders(self):
        r = self.client.get("/profile/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "criteria.yaml")

    def test_missing_pages_404(self):
        for url in ["/applications/9999/", "/notes/nope/", "/companies/nope/",
                    "/applications/status/nope/", "/applications/area/nope/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_filtered_views_are_real_paths(self):
        for status in STATUS_SORT_ORDER:
            with self.subTest(status=status):
                r = self.client.get(f"/applications/status/{status}/")
                self.assertEqual(r.status_code, 200)
                for app in r.context["applications"]:
                    self.assertEqual(app.status, status)
        for area in Area.objects.all():
            with self.subTest(area=area.slug):
                r = self.client.get(f"/applications/area/{area.slug}/")
                for app in r.context["applications"]:
                    self.assertEqual(app.area.slug, area.slug)

    def test_browse_lists_are_newest_first(self):
        for url in ["/applications/", "/applications/active/",
                    "/applications/status/applied/"]:
            with self.subTest(url=url):
                dates = [a.date for a in self.client.get(url).context["applications"]]
                self.assertEqual(dates, sorted(dates, reverse=True), url)

    def test_no_querystring_links_in_html(self):
        import re
        for url in ["/", "/applications/", "/applications/all/", "/companies/", "/areas/",
                    "/stats/", "/cvs/", "/scans/", "/scans/all/"]:
            html = self.client.get(url).content.decode()
            hrefs = re.findall(r'href="([^"]+)"', html)
            with self.subTest(url=url):
                self.assertEqual([h for h in hrefs if "?" in h and not h.startswith("http")], [])

    def test_markdown_is_rendered_not_escaped(self):
        app = Application.objects.exclude(folder="").first()
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        self.assertNotIn("&lt;h2&gt;", html)
        self.assertIn("<h2", html)

    def test_templates_have_no_leaked_comment_markup(self):
        """Django's `{# #}` is single-line only, so a multi-line one renders verbatim into
        the page. `#66` hit it in `base.html` and added this test; `#73` hit it again in
        `note_list.html` and this test did not fire, because it walked a hand-written list
        of nine URLs that never gained `/notes/`, `/profile/`, `/help/`, an application
        page or a round focus view.

        It now walks `build_static.site_urls()` — the enumeration the published site is
        built from, so a page that ships is a page this checks. Same reasoning as `#51`'s
        help page reading its command list from `SKILL.md`: a second copy of a list drifts,
        and the copy that drifts is the one nobody is looking at.
        """
        from tracker.management.commands.build_static import site_urls

        urls = site_urls()
        self.assertGreater(len(urls), 20, "site_urls() returned implausibly few pages")
        for url in urls:
            html = self.client.get(url).content.decode()
            with self.subTest(url=url):
                self.assertNotIn("{#", html)
                self.assertNotIn("{%", html)

    def test_company_notes_render_when_present(self):
        documented = [c for c in Company.objects.all() if c.notes_path]
        self.assertTrue(documented, "no company notes files found at all")
        for company in documented:
            with self.subTest(slug=company.slug):
                self.assertContains(self.client.get(f"/companies/{company.slug}/"), "Notes")

    def test_company_notes_filename_matches_slug(self):
        notes_dir = Path(settings.JOBS_DIR) / "companies"
        slugs = set(Company.objects.values_list("slug", flat=True))
        for md in notes_dir.glob("*.md"):
            if md.stem == "README":
                continue
            with self.subTest(file=md.name):
                self.assertIn(md.stem, slugs, f"{md.name} matches no company slug")

    def test_the_repo_link_survives_publishing(self):
        """`#33`. Every other sidebar link is local-only; this one is the exception, and
        the published mirror is precisely where it earns its place — a reader who likes
        the site has no other way to find out what built it. A future tidy-up that sweeps
        the footer behind {% if IS_LOCAL %} should fail here."""
        repo = "https://github.com/lambdamusic/jobstudio"
        with self.settings(ENVIRONMENT="publish"):
            self.assertIn(repo, self.client.get("/applications/").content.decode())
        self.assertIn(repo, self.client.get("/applications/").content.decode())

    def test_admin_links_hidden_when_publishing(self):
        with self.settings(ENVIRONMENT="publish"):
            html = self.client.get("/applications/").content.decode()
            self.assertNotIn("/admin/", html)
        html = self.client.get("/applications/").content.decode()
        self.assertIn("/admin/tracker/application/", html)


class StatsPageTests(TestCase):
    """`/stats/` — the charts page (backlog/plans/042-dashboard-charts.md §2a).

    What these pin is the frame every chart lands into rather than any one chart: the
    volume readout the charts get checked against, and R3's three data tiers — what a
    chart renders when it cannot draw honestly. Those states are a permanent requirement
    rather than scaffolding: most people meet this page on a tracker with almost nothing
    in it, and a page that looks broken on day one is worse than one with fewer charts.
    """

    fixtures = FIXTURE

    # Anchor -> the plan section that specifies it. One entry per chart the plan asks for,
    # built or not, so a chart nobody got to is visible on the page instead of forgotten.
    PLANNED = {"ageing": "§7", "flow": "§3", "companies": "§5",
               "per-company": "§6", "stock": "§4"}

    def sections(self, html=None):
        """The page split at its chart headings, keyed by anchor — so an assertion can be
        about one chart rather than about the whole page."""
        if html is None:
            html = self.client.get("/stats/").content.decode()
        parts = re.split(r'<h2 id="([\w-]+)"', html)
        return dict(zip(parts[1::2], parts[2::2]))

    def test_the_page_renders_and_the_nav_links_it(self):
        self.assertEqual(self.client.get("/stats/").status_code, 200)
        self.assertIn('href="/stats/"', self.client.get("/").content.decode())

    def test_every_planned_chart_has_a_section(self):
        self.assertEqual(set(self.sections()), set(self.PLANNED))

    def test_a_section_with_nothing_to_draw_names_its_plan_section(self):
        """However a slot fills its panel, it says where the chart is specified — the one
        thing that turns "this is blank" into "this is blank, and here is why"."""
        for anchor, body in self.sections().items():
            if "chart-plan" in body:
                with self.subTest(anchor=anchor):
                    self.assertIn(self.PLANNED[anchor], body)

    def test_an_entry_is_not_counted_as_a_transition(self):
        """The split the whole page turns on. A status change with a blank `from_status`
        records where an application was first logged; only a move between two statuses is
        an edge in a flow diagram or a step in a history."""
        from tracker.views import _stats_volumes

        volumes = _stats_volumes()
        self.assertEqual(volumes["entries"] + volumes["transitions"],
                         volumes["status_changes"])
        self.assertEqual(volumes["status_changes"], ApplicationStatusChange.objects.count())
        # The example used to have three applications and not one transition between
        # statuses, and this assertion pinned that — with a note saying it was the thing to
        # revisit if the fixture grew. `#64` grew it, for exactly the reason the charts
        # needed: an example with no transitions cannot demonstrate a flow diagram. What is
        # worth pinning now is the other direction — that the shipped example carries real
        # movement, so a newcomer meets charts with something in them.
        self.assertGreaterEqual(volumes["applications"], 9)
        self.assertGreater(volumes["transitions"], 0)
        self.assertGreater(volumes["entries"], 0)

    def test_at_example_volume_the_history_charts_actually_draw(self):
        """`#64`. This test asserted the opposite until 2026-10-01: that at example volume
        the history charts had nothing to plot and said so. That was true, and it was the
        bug — a first-time user installing the example met a status-flow diagram with no
        ribbons and a stock chart refusing to render, which reads as broken rather than as
        empty. The example now ships real transitions, so the charts draw; the
        say-why-you-cannot paths are still covered, by tests that build a thin tracker
        themselves instead of borrowing the example's thinness (see `start_from_empty`)."""
        sections = self.sections()
        self.assertNotIn("no ribbons to draw", sections["flow"])
        self.assertNotIn("needs transitions to replay", sections["stock"])
        # Ribbons between two real statuses, which is what the chart exists to show.
        self.assertIn("<td class=\"nowrap\">applied</td>", sections["flow"])

    def test_the_shipped_example_fills_the_funnel(self):
        """`#64`. The example is the first thing anyone sees, and the charts are the part
        that needs data to mean anything. This pins the shape rather than the counts: every
        status reached, outcomes present, and at least one application that moved backwards
        — because that is what makes the flow diagram, the stock chart and the cycle rule
        all demonstrate something instead of rendering an apology."""
        from tracker.views import FUNNEL_ORDER, _status_flow, _status_stock

        reached = set(ApplicationStatusChange.objects.values_list("to_status", flat=True))
        for status in FUNNEL_ORDER:
            with self.subTest(status=status):
                self.assertIn(status, reached,
                              f"no example application ever reaches {status}")

        flow = _status_flow()
        moves = [l for l in flow["links"] if l["kind"] == "move"]
        self.assertGreaterEqual(len(moves), 5,
                                "the Sankey needs several status-to-status ribbons to be a funnel")
        self.assertGreaterEqual(flow["dropped"], 1,
                                "no backward transition, so the cycle rule is never exercised")
        self.assertTrue(flow["reconciles"])
        self.assertTrue(_status_stock()["ready"],
                        "the stock chart still refuses to draw at example volume")

    def test_loading_the_example_invents_no_status_history(self):
        """`#65`. `loaddata` saves each Application before its ApplicationStatusChange
        rows, so without a `raw` guard on the post-save signal the log looks empty and a
        `(logged) -> <current>` row is appended, stamped at load time. That row then
        becomes the most recent change — so every restored application reads as moved
        today, and the staleness flagging silently stops working.

        Asserted against the fixture file rather than a count, because the number will
        change: whatever the dump holds is exactly what the database should hold."""
        import json
        from pathlib import Path as _Path

        from django.conf import settings as _settings

        dump = json.loads((_Path(_settings.DATA_ROOT) / "backups" / "django"
                           / "dump.json").read_text())
        in_file = sum(1 for o in dump if o["model"] == "tracker.applicationstatuschange")
        self.assertEqual(ApplicationStatusChange.objects.count(), in_file,
                         "loading the fixture created status changes that are not in it")

    def test_an_empty_tracker_states_the_absence_and_how_to_start(self):
        Application.objects.all().delete()
        Company.objects.all().delete()
        response = self.client.get("/stats/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("/jobstudio application", html)
        for anchor, body in self.sections(html).items():
            with self.subTest(anchor=anchor):
                self.assertIn("Nothing tracked yet", body)

    def test_companies_with_no_applications_says_which_of_the_two_is_missing(self):
        """The real cold-start state, not the truly empty one: `init` seeds a company
        watchlist, so the first thing anyone sees here has companies and nothing applied
        to. "Nothing tracked yet" on its own would be wrong about half of it."""
        Application.objects.all().delete()
        html = self.client.get("/stats/").content.decode()
        self.assertIn("tracked, but nothing applied to", html)

    def test_unlinked_applications_are_declared(self):
        """R-A1. `Application.company` is nullable, so a per-company chart covers fewer
        applications than it claims unless the number it excludes is stated."""
        self.assertTrue(Application.objects.filter(company__isnull=True).exists(),
                        "fixture needs an application with no company for this to mean anything")
        self.assertIn("no company linked", self.client.get("/stats/").content.decode())

        Application.objects.filter(company__isnull=True).delete()
        self.assertNotIn("no company linked", self.client.get("/stats/").content.decode())


class AgeingTests(TestCase):
    """Ageing at `applied` (plan §7) — which submitted applications have gone quiet.

    A list rather than a chart: every row is individually actionable, and the point of the
    view is that it changes how the rest of the site reads. An `applied` count that
    contains dead applications is not a pipeline of that size (R-G3).
    """

    fixtures = FIXTURE

    def applied(self, num, *, days_quiet, next_action=""):
        """An application at `applied` whose last status change was `days_quiet` ago."""
        app = Application.objects.create(num=num, company_name=f"Co {num}", role="Role",
                                         status="applied", next_action=next_action)
        moved = timezone.now() - dt.timedelta(days=days_quiet)
        ApplicationStatusChange.objects.filter(application=app).update(changed_at=moved)
        return app

    def test_stale_only_past_the_threshold(self):
        from tracker.views import STALE_AFTER_DAYS, _ageing_at_applied

        fresh = self.applied(9101, days_quiet=STALE_AFTER_DAYS - 1)
        stale = self.applied(9102, days_quiet=STALE_AFTER_DAYS + 1)
        rows = {r["application"].num: r for r in _ageing_at_applied()}
        self.assertFalse(rows[fresh.num]["stale"])
        self.assertTrue(rows[stale.num]["stale"])

    def test_the_quietest_are_listed_first(self):
        from tracker.views import _ageing_at_applied

        self.applied(9103, days_quiet=5)
        self.applied(9104, days_quiet=90)
        days = [r["days"] for r in _ageing_at_applied() if r["days"] is not None]
        self.assertEqual(days, sorted(days, reverse=True))

    def test_an_application_with_no_date_at_all_is_kept_and_sorted_last(self):
        """It is a real state — logged with no date, no recorded change — and inventing an
        age for it would put it in the wrong half of a list sorted by staleness."""
        from tracker.views import _ageing_at_applied

        app = Application.objects.create(num=9105, company_name="Undated Co",
                                         role="Role", status="applied")
        ApplicationStatusChange.objects.filter(application=app).delete()
        self.applied(9106, days_quiet=2)

        rows = _ageing_at_applied()
        self.assertEqual(rows[-1]["application"].num, app.num)
        self.assertIsNone(rows[-1]["days"])
        self.assertFalse(rows[-1]["stale"])
        self.assertEqual(self.client.get("/stats/").status_code, 200)

    def test_stale_with_nothing_planned_is_flagged(self):
        """R-G2. The strongest signal on the page is a row that has gone quiet and has no
        next action — `next_action` already exists and nothing else surfaced it."""
        from tracker.views import _ageing_at_applied

        adrift = self.applied(9107, days_quiet=60)
        planned = self.applied(9108, days_quiet=60, next_action="Chase the recruiter")
        rows = {r["application"].num: r for r in _ageing_at_applied()}
        self.assertTrue(rows[adrift.num]["adrift"])
        self.assertFalse(rows[planned.num]["adrift"])
        self.assertIn("no next action recorded", self.client.get("/stats/").content.decode())

    def test_the_bands_break_at_the_threshold(self):
        """The stale line is a property of the bands, not a rule drawn over them: no band
        may straddle it, or a bar would be half quiet and half not."""
        from tracker.views import AGE_BANDS, STALE_AFTER_DAYS

        ends = [high for _, high in AGE_BANDS]
        self.assertIn(STALE_AFTER_DAYS, ends, "no band ends at the staleness threshold")
        self.assertGreater(AGE_BANDS[ends.index(STALE_AFTER_DAYS) + 1][0], STALE_AFTER_DAYS,
                           "the band after the threshold starts inside it")

    def test_every_application_at_applied_lands_in_exactly_one_band(self):
        """The bands are the chart, so anything that falls between them is invisible. The
        undated are the one deliberate exception, and they are counted separately."""
        from tracker.views import _ageing_bands

        for num, days in ((9120, 0), (9121, 7), (9122, 8), (9123, 30), (9124, 31), (9125, 900)):
            self.applied(num, days_quiet=days)
        undated = Application.objects.create(num=9126, company_name="Undated Co",
                                             role="Role", status="applied")
        ApplicationStatusChange.objects.filter(application=undated).delete()

        bands = _ageing_bands()
        self.assertEqual(sum(b["count"] for b in bands["bands"]) + bands["undated"],
                         bands["total"])

    def test_the_chart_renders_and_the_dashboard_points_at_it(self):
        """R-G3's "done when": the view is reachable from the `applied` stat box, which is
        where the count that contains these applications is shown.

        The dashboard only. On the applications list the same sentence sat above a table
        that already sorts by longest-without-moving — telling someone looking at the rows
        what the rows say."""
        self.applied(9109, days_quiet=45)
        html = self.client.get("/stats/").content.decode()
        self.assertIn('data-chart="ageing"', html)
        self.assertIn("/applications/9109/", html)  # the row itself, linked from the band
        self.assertIn("45d", html)                  # and how long it has been quiet
        self.assertIn("/stats/#ageing", self.client.get("/").content.decode())
        self.assertNotIn("/stats/#ageing",
                         self.client.get("/applications/status/applied/").content.decode())

    def test_nothing_stale_says_nothing_on_the_stat_bar(self):
        """A note that is always there is furniture. This one only appears when something
        has actually gone quiet."""
        start_from_empty()
        self.applied(9110, days_quiet=1)
        self.assertNotIn("/stats/#ageing", self.client.get("/").content.decode())

    def test_the_cli_status_report_shows_the_same_rows(self):
        """R1 — one query layer. `/jobstudio status` and the page both count
        `_ageing_at_applied()`, so they cannot come to disagree about what "gone quiet"
        means."""
        import io
        from contextlib import redirect_stdout

        import jobsdb

        self.applied(9111, days_quiet=75)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            jobsdb.print_status_report(jobsdb.dashboard_summary())
        report = buffer.getvalue()
        self.assertIn("Gone quiet", report)
        self.assertIn("Co 9111", report)


class ChartDataTests(TestCase):
    """The four charts' data (plan §3–§6).

    These test the arithmetic, not the drawing — the drawing is ECharts' problem, and the
    page ships every one of these numbers as a table anyway. What is worth pinning is the
    part a chart cannot show you is wrong: that the ribbons balance, that a dropped edge is
    counted rather than lost, and that a count means what the label says it means.
    """

    fixtures = FIXTURE

    def history(self, num, path, **kwargs):
        """An application that walked `path`, one recorded change per step."""
        app = Application.objects.create(num=num, company_name=f"Co {num}", role="Role",
                                         status=path[-1], **kwargs)
        ApplicationStatusChange.objects.filter(application=app).delete()
        when = timezone.now() - dt.timedelta(days=7 * len(path))
        for i, status in enumerate(path):
            ApplicationStatusChange.objects.create(
                application=app, changed_at=when + dt.timedelta(days=7 * i),
                from_status=path[i - 1] if i else "", to_status=status)
        return app

    # ---------------------------------------------------------------- §3 flow
    def test_every_node_reconciles(self):
        """R-S2, and the reason the terminal stubs exist: for each status, what came in
        minus what went out is what is sitting there now. A Sankey whose nodes do not
        balance looks broken, and this is the check that catches it before anyone sees it."""
        from tracker.views import _status_flow

        self.history(9201, ["saved", "reviewing", "applied"])
        self.history(9202, ["saved", "discarded"])
        self.history(9203, ["applied", "rejected"])
        self.assertTrue(_status_flow()["reconciles"])

    def test_a_status_written_without_logging_the_change_fails_reconciliation(self):
        """The check has to be able to fail, or it is decoration. A status changed behind
        the signal's back is exactly the corruption it exists to catch."""
        from tracker.views import _status_flow

        app = self.history(9204, ["saved", "applied"])
        Application.objects.filter(pk=app.pk).update(status="interviewing")  # no signal
        self.assertFalse(_status_flow()["reconciles"])

    def test_backward_edges_are_dropped_and_counted(self):
        """R-S3. A Sankey is a DAG and a re-opened application runs against the funnel, so
        the edge cannot be drawn — but silently losing it is how a diagram starts lying."""
        from tracker.views import _status_flow

        start_from_empty()
        self.history(9205, ["saved", "applied", "reviewing"])  # the last step goes back
        flow = _status_flow()
        self.assertEqual(flow["dropped"], 1)
        drawn = [(l["source"], l["target"]) for l in flow["links"] if l["kind"] == "move"]
        self.assertNotIn(("applied", "reviewing"), drawn)
        self.assertIn(("saved", "applied"), drawn)

    def test_an_application_that_appears_mid_funnel_keeps_its_own_ribbon(self):
        """R-S1. An application logged straight into `closed` never passed through the
        statuses to its left, and a diagram that quietly routed it through them would be
        lying. Starting at `saved` needs no ribbon — that node *is* the start."""
        from tracker.views import _status_flow

        self.history(9206, ["closed"])
        self.history(9207, ["saved"])
        flow = _status_flow()
        entries = {l["target"]: l["value"] for l in flow["links"] if l["kind"] == "entry"}
        self.assertEqual(entries["closed"], 1)
        self.assertNotIn("saved", entries)
        # `mid_funnel` is exactly what is drawn as a stub — the fixture has its own
        # arrivals at `applied` and `reviewing`, and they are counted the same way.
        self.assertEqual(flow["mid_funnel"], sum(entries.values()))
        self.assertGreaterEqual(flow["entered"], 1)

    def test_the_applied_node_carries_the_stale_count(self):
        """R-S4: `applied` is the largest node and includes applications nobody has heard
        about in months. It says so on itself rather than letting the diagram overstate
        how much is in flight."""
        from tracker.views import STALE_AFTER_DAYS, _status_flow

        app = self.history(9208, ["saved", "applied"])
        ApplicationStatusChange.objects.filter(application=app).update(
            changed_at=timezone.now() - dt.timedelta(days=STALE_AFTER_DAYS + 5))
        label = next(n["label"] for n in _status_flow()["nodes"] if n["name"] == "applied")
        # `#56`: the total comes first, the quiet count after it.
        self.assertRegex(label, r"^applied \(\d+\) · \d+ quiet$")

    def test_the_post_application_view_treats_arrivals_as_entries(self):
        """§3's second view starts at `applied`, so an application that got there from
        `reviewing` entered the diagram at `applied` — the pre-application attrition is out
        of the window, not silently missing from it."""
        from tracker.views import POST_APPLICATION_ORDER, _status_flow

        self.history(9209, ["saved", "reviewing", "applied"])
        post = _status_flow(POST_APPLICATION_ORDER)
        self.assertNotIn("reviewing", [n["name"] for n in post["nodes"]])
        self.assertTrue(post["reconciles"])
        # `applied` is where this window starts, so the arrival is counted but not drawn as
        # a stub — the node itself is the entry point.
        self.assertGreaterEqual(post["entered"], 1)
        self.assertNotIn("applied", [l["target"] for l in post["links"]
                                     if l["kind"] == "entry"])

    def test_an_application_that_leaves_the_window_is_counted_not_absorbed(self):
        """Moving back out of the submitted set is a real thing that happens; the post
        view reports it rather than quietly losing an application."""
        from tracker.views import POST_APPLICATION_ORDER, _status_flow

        start_from_empty()
        self.history(9210, ["applied", "saved"])
        post = _status_flow(POST_APPLICATION_ORDER)
        self.assertEqual(post["left"], 1)
        self.assertTrue(post["reconciles"])

    def test_the_post_application_view_leaves_out_what_never_reached_applied(self):
        """`#56`(a). A role discarded straight from `saved` was never applied to, so the
        "from applied onward" view does not draw it — not even as an "added" stub — and
        says how many it left out."""
        from tracker.views import POST_APPLICATION_ORDER, _status_flow

        self.history(9230, ["saved", "discarded"])
        self.history(9231, ["saved", "applied", "rejected"])
        full = _status_flow()
        post = _status_flow(POST_APPLICATION_ORDER, population_from="applied")
        self.assertEqual([l for l in post["links"] if l["kind"] == "entry"], [])
        self.assertGreaterEqual(post["excluded"], 1)
        self.assertTrue(post["reconciles"])
        # The full funnel is unchanged: its entry-stub rule still stands.
        self.assertEqual(full["excluded"], 0)

    def test_the_post_application_view_starts_each_history_at_applied(self):
        """`#56`. Onward in time, not only in population: a role discarded and re-opened
        before it was ever applied to must not come back as an entry stub at `discarded`."""
        from tracker.views import POST_APPLICATION_ORDER, _status_flow

        self.history(9234, ["saved", "reviewing", "discarded", "reviewing", "applied"])
        post = _status_flow(POST_APPLICATION_ORDER, population_from="applied")
        self.assertNotIn("entry:discarded", [n["name"] for n in post["nodes"]])
        self.assertTrue(post["reconciles"])

    def test_status_labels_carry_how_many_ever_reached_them(self):
        """`#56`(b). Cumulative, so `rejected (N)` is every rejection whichever status it
        came from — the question that prompted it."""
        from tracker.views import _status_flow

        self.history(9232, ["saved", "rejected"])
        self.history(9233, ["saved", "applied", "rejected"])
        rejected = ApplicationStatusChange.objects.filter(to_status="rejected") \
            .values("application_id").distinct().count()
        labels = {n["name"]: n["label"] for n in _status_flow()["nodes"]}
        self.assertEqual(labels["rejected"], f"rejected ({rejected})")
        self.assertRegex(labels["inactive"], r"^inactive \(\d+\)$")

    # --------------------------------------------------------------- §4 stock
    def test_what_moved_in_a_week_is_not_what_sits_there(self):
        """The two views measure different things, which is the whole reason both exist: a
        quiet week has stock and no movement, and a chart that drew a flat line for both
        would be saying the same thing twice."""
        from tracker.views import _status_stock

        self.history(9214, ["saved", "applied"])
        weeks = _status_stock()["weeks"]
        self.assertTrue(any(w["total"] and not w["moved"] for w in weeks),
                        "no quiet week to tell the two views apart")
        for week in weeks:
            with self.subTest(week=week["label"]):
                self.assertEqual(sum(week["moves"].values()), week["moved"])
                self.assertEqual(len(week["flow"]), len(week["cells"]))

    def test_every_recorded_change_is_counted_once_as_movement(self):
        """Flow is the change log itself, bucketed — so the weeks must add up to it exactly,
        with nothing double-counted when an application moves twice in a week."""
        from tracker.views import _status_stock

        self.history(9215, ["saved", "reviewing", "applied"])
        stock = _status_stock()
        self.assertEqual(sum(w["moved"] for w in stock["weeks"]),
                         ApplicationStatusChange.objects.count())

    def test_the_bands_total_the_applications_that_existed(self):
        """Every application is in exactly one band at every point, so the top of the stack
        is the tracker's own size — including at the end, where it is today's count."""
        from tracker.views import _status_stock

        self.history(9211, ["saved", "applied"])
        self.history(9212, ["saved"])
        weeks = _status_stock()["weeks"]
        self.assertEqual(weeks[-1]["total"], Application.objects.count())
        for week in weeks:
            with self.subTest(week=week["label"]):
                self.assertEqual(sum(week["counts"].values()), week["total"])

    def test_backfilled_weeks_are_marked_reconstructed(self):
        """R-T2/R4. The 2026-09-08 backfill dated its rows from `Application.date`, so they
        land at exactly local midnight — which is what makes this detectable rather than
        guessed at. Unmarked, those weeks read as a burst of activity that never happened."""
        from tracker.views import _status_stock

        start_from_empty()
        app = self.history(9213, ["saved", "applied"])
        midnight = timezone.make_aware(
            dt.datetime.combine(timezone.localdate() - dt.timedelta(days=21), dt.time(0, 0)))
        ApplicationStatusChange.objects.filter(application=app).update(changed_at=midnight)
        marked = [w for w in _status_stock()["weeks"] if w["reconstructed"]]
        self.assertTrue(marked, "a week of midnight-stamped rows was not marked")

    def test_a_thin_history_says_so_instead_of_drawing(self):
        """R-T4. The chart needs several weeks of history that was lived rather than typed
        in one sitting; below that it says what it is waiting for, which is a legitimate
        outcome and improves on its own."""
        from tracker.views import _status_stock

        start_from_empty()
        self.history(9214, ["saved", "applied"])
        stock = _status_stock()
        self.assertFalse(stock["ready"])
        self.assertContains(self.client.get("/stats/"), "before the shape of a pipeline")

    def test_a_band_that_was_never_occupied_is_not_a_series(self):
        """R3: a legend entry for a series that does not exist is worse than one fewer
        band. The example tracker used to supply this condition for free by never having
        reached `interviewing`; since `#64` it does, so the test builds a tracker that has
        not rather than relying on the example staying thin."""
        from tracker.views import _status_stock

        start_from_empty()
        self.history(9215, ["saved", "reviewing", "applied"])
        statuses = _status_stock()["statuses"]
        self.assertIn("applied", statuses)
        self.assertNotIn("interviewing", statuses)

    # -------------------------------------------------------------- the page
    def test_the_flow_toggle_needs_no_page_load(self):
        """§3's "done when". Both views ship in the payload the page already carries, so
        the switch is a redraw. It could not be a link either way: a querystring cannot be
        published as a static page (see build_static)."""
        import json

        self.history(9220, ["saved", "reviewing", "applied"])
        html = self.client.get("/stats/").content.decode()
        self.assertIn('data-view="full"', html)
        self.assertIn('data-view="post"', html)
        self.assertNotIn("/stats/?", html)

        payload = re.search(r'id="chart-data"[^>]*>(.*?)</script>', html, re.S).group(1)
        flow = json.loads(payload.replace("\\u0022", '"'))["flow"]
        self.assertEqual(set(flow), {"full", "post"})

    def test_every_chart_ships_its_numbers_as_a_table(self):
        """R5, and §2a's debugging affordance, are the same markup: the table is in the
        page before the chart is. So it reads with no JavaScript, a screen reader gets
        values rather than a drawing, and the numbers can be checked against the shape."""
        for num, path in enumerate([["saved", "reviewing", "applied", "interviewing"],
                                    ["saved", "reviewing", "applied", "rejected"],
                                    ["saved", "discarded"]], start=9230):
            self.history(num, path)

        html = self.client.get("/stats/").content.decode()
        for key in ("ageing", "flow", "coverage", "perCompany", "stock"):
            with self.subTest(chart=key):
                self.assertIn('data-chart="%s"' % key, html)
        self.assertEqual(html.count('<details class="numbers"'), 5)

    # ----------------------------------------------------- §5 and §6 companies
    def test_the_donut_segments_sum_to_the_tracked_companies(self):
        from tracker.views import _company_coverage

        coverage = _company_coverage()
        self.assertEqual(sum(s["count"] for s in coverage["states"]), coverage["total"])
        self.assertEqual(coverage["total"], Company.objects.count())

    def test_a_company_with_only_unsent_applications_is_its_own_state(self):
        """The reason the donut went from two slices to three (2026-09-28): a company with
        an application open on the desk is not "not acted on", which is what the two-state
        model said about it."""
        from tracker.views import _company_coverage

        company = Company.objects.create(num=9300, name="Saved Only Co", slug="saved-only-co")
        Application.objects.create(num=9301, company=company, company_name=company.name,
                                   role="Role", status="saved")
        coverage = _company_coverage()
        self.assertGreaterEqual(coverage["reviewing"], 1)
        company.refresh_from_db()
        self.assertEqual(company.status, "reviewing")

    def test_watching_says_how_much_of_it_was_never_acted_on(self):
        """R-C1's descendant. `watching` covers both "never applied to" and "tried and it
        ended", which mean the same thing about now and different things about history —
        so the page states the split rather than leaving the reading to the reader."""
        from tracker.views import _company_coverage

        company = Company.objects.create(num=9302, name="Closed Only Co", slug="closed-only-co")
        Application.objects.create(num=9303, company=company, company_name=company.name,
                                   role="Role", status="closed")
        coverage = _company_coverage()
        self.assertLess(coverage["never"], coverage["watching"])
        self.assertContains(self.client.get("/stats/"), "never applied to")

    def test_the_buckets_plus_the_unlinked_account_for_every_application(self):
        """R-A1. `Application.company` is nullable, so a per-company chart covers fewer
        applications than it claims unless the number outside it is stated."""
        from tracker.views import _applications_per_company

        data = _applications_per_company()
        counted = Application.objects.exclude(company__isnull=True).count()
        self.assertEqual(counted + data["unlinked"], data["applications"])
        self.assertEqual(sum(b["count"] for b in data["buckets"]), data["companies"])

    def test_each_bucket_names_the_companies_in_it(self):
        """A count answers "how many"; the next question is always "which". The names are
        capped so the page does not become a directory, and `more` says how many were left
        for the link to the companies list."""
        from tracker.views import _applications_per_company

        for bucket in _applications_per_company()["buckets"]:
            with self.subTest(bucket=bucket["label"]):
                self.assertEqual(len(bucket["companies"]) + bucket["more"], bucket["count"])
                self.assertTrue(bucket["phrase"])
                for company in bucket["companies"]:
                    self.assertTrue(Company.objects.filter(slug=company["slug"]).exists())


class TableToolbarTests(TestCase):
    """The search / filter / sort bar on the two long lists (2026-09-28).

    It works in the browser, so what can be pinned here is the contract between the server
    and `tabletools.js`: the controls exist, and every row carries the attributes they
    filter and sort on. A row missing one of those is invisible to the toolbar — it does
    not error, it just never matches, which is the failure worth catching early.
    """

    fixtures = FIXTURE

    def test_the_applications_toolbar_replaced_the_area_chips(self):
        html = self.client.get("/applications/all/").content.decode()
        self.assertIn('class="toolbar" data-table="apps"', html)
        self.assertIn('class="tb-search"', html)
        self.assertIn('data-field="area"', html)
        self.assertIn('value="moved:asc"', html)  # longest without moving
        self.assertNotIn('class="chips"', html)

    def test_every_application_row_carries_what_the_toolbar_needs(self):
        html = self.client.get("/applications/all/").content.decode()
        rows = re.findall(r"<tr data-search=.*?</tr>", html, re.S)
        self.assertEqual(len(rows), Application.objects.count())
        for app in Application.objects.select_related("area"):
            row = next(r for r in rows if f'data-sort-num="{app.num}"' in r)
            with self.subTest(num=app.num):
                self.assertIn(escape(app.company_name), row)
                self.assertIn(f'data-status="{app.status}"', row)
                self.assertIn(f'data-area="{app.area.slug if app.area else ""}"', row)

    def test_last_moved_comes_from_the_change_log_not_the_logged_date(self):
        """The two differ for every application that has moved since it was logged, and
        sorting by the wrong one would put a long-dead application at the top of "longest
        without moving"."""
        app = Application.objects.get(num=1)
        ApplicationStatusChange.objects.filter(application=app).update(
            changed_at=timezone.now())
        response = self.client.get("/applications/all/")
        row = next(r for r in re.findall(r"<tr data-search=.*?</tr>",
                                         response.content.decode(), re.S)
                   if 'data-sort-num="1"' in r)
        self.assertIn("today", row)  # `ago` of the change, not of app.date
        self.assertGreater(int(re.search(r'data-sort-moved="(\d+)"', row).group(1)),
                           int(re.search(r'data-sort-date="(\d+)"', row).group(1)))

    def test_the_companies_page_is_one_table_with_category_as_a_column(self):
        html = self.client.get("/companies/").content.decode()
        self.assertNotIn("data-tabs", html)
        self.assertEqual(html.count('<table data-table="companies"'), 1)
        self.assertIn("<th class=\"nowrap\">Category</th>", html)
        self.assertIn("<th class=\"nowrap\">Added</th>", html)
        for category in Category.objects.all():
            with self.subTest(category=category.name):
                self.assertIn(f'<option value="{escape(category.name)}"', html)

    def test_every_company_row_carries_what_the_toolbar_needs(self):
        html = self.client.get("/companies/").content.decode()
        rows = re.findall(r"<tr data-search=.*?</tr>", html, re.S)
        self.assertEqual(len(rows), Company.objects.count())
        for company in Company.objects.annotate(n=Count("applications")):
            row = next(r for r in rows if f'/companies/{company.slug}/' in r)
            bucket = "none" if not company.n else "3+" if company.n >= 3 else str(company.n)
            with self.subTest(slug=company.slug):
                self.assertIn(f'data-apps="{bucket}"', row)
                self.assertIn(f'data-status="{company.status}"', row)

    def test_every_company_row_carries_its_scan_state(self):
        """`#54`. The filter matches `data-scanned` exactly, so a row without it would
        silently never match."""
        html = self.client.get("/companies/").content.decode()
        self.assertIn('data-field="scanned"', html)
        rows = re.findall(r"<tr data-search=.*?</tr>", html, re.S)
        for company in Company.objects.all():
            row = next(r for r in rows if f'/companies/{company.slug}/' in r)
            with self.subTest(slug=company.slug):
                self.assertIn(f'data-scanned="{company.scan_state}"', row)

    def test_the_companies_lede_links_into_the_scan_filter(self):
        html = self.client.get("/companies/").content.decode()
        lede = re.search(r'<p class="lede">.*?</p>', html, re.S).group(0)
        self.assertIn('href="#scanned=yes"', lede)
        self.assertNotIn("?", lede)

    def test_the_per_company_chart_links_into_the_companies_list(self):
        """A fragment, not a querystring: the static build can publish the one page the
        link lands on, and `tabletools.js` reads the fragment to preselect the filter. A
        `?apps=2` would fail the build's link check instead."""
        html = self.client.get("/stats/").content.decode()
        self.assertIn('href="/companies/#apps=', html)
        self.assertNotIn("/companies/?", html)

    def test_the_toolbar_is_hidden_until_the_script_says_otherwise(self):
        """Progressive enhancement, same as tabs.js and charts.js: with no JavaScript the
        table below is complete, and a row of controls that do nothing is worse than none."""
        css = (Path(settings.STATICFILES_DIRS[0]) / "css" / "site.css").read_text()
        self.assertIn(".toolbar { display: none;", css)
        self.assertIn(".toolbar.js-tools { display: flex; }", css)


class SavedEntryBackfillTests(TestCase):
    """`backfill_saved_entry` — every application starts at `saved` (2026-09-28).

    Applications logged straight into `closed` or `applied` are an artefact of how the
    tracker was used while it was being built, not a real difference: nobody applies to a
    role they never looked at. This is the one command that edits existing rows, so what is
    pinned here is that it edits exactly what it says and nothing else.
    """

    fixtures = FIXTURE

    def run_command(self, **options):
        out = StringIO()
        call_command("backfill_saved_entry", stdout=out, stderr=StringIO(), **options)
        return out.getvalue()

    def logged_at(self, num, status, when):
        app = Application.objects.create(num=num, company_name=f"Co {num}",
                                         role="Role", status=status)
        ApplicationStatusChange.objects.filter(application=app).update(changed_at=when)
        return app

    def test_an_application_logged_straight_into_a_late_status_gains_a_saved_entry(self):
        when = timezone.now() - dt.timedelta(days=10)
        app = self.logged_at(9401, "closed", when)

        self.run_command()

        changes = list(app.status_changes.order_by("changed_at", "pk"))
        self.assertEqual([(c.from_status, c.to_status) for c in changes],
                         [("", "saved"), ("saved", "closed")])
        # Dated the day before, so the order is unambiguous and the new row is not
        # pretending to have happened at the same moment.
        self.assertEqual(changes[0].changed_at, when - dt.timedelta(days=1))

    def test_an_application_that_already_starts_at_saved_is_untouched(self):
        app = self.logged_at(9402, "saved", timezone.now() - dt.timedelta(days=3))
        before = list(app.status_changes.values_list("pk", "from_status", "to_status"))

        self.run_command()

        self.assertEqual(list(app.status_changes.values_list("pk", "from_status", "to_status")),
                         before)

    def test_running_it_twice_changes_nothing_the_second_time(self):
        self.logged_at(9403, "rejected", timezone.now() - dt.timedelta(days=5))
        self.run_command()
        count = ApplicationStatusChange.objects.count()

        self.assertIn("0 application(s) gained", self.run_command())
        self.assertEqual(ApplicationStatusChange.objects.count(), count)

    def test_a_dry_run_writes_nothing(self):
        self.logged_at(9404, "applied", timezone.now() - dt.timedelta(days=5))
        count = ApplicationStatusChange.objects.count()

        output = self.run_command(dry_run=True)

        self.assertIn("would gain", output)
        self.assertEqual(ApplicationStatusChange.objects.count(), count)

    def test_an_application_with_no_history_is_reported_not_guessed_at(self):
        """There is nothing to date the new row from, and inventing one would be worse than
        leaving a gap someone can see."""
        app = self.logged_at(9405, "applied", timezone.now())
        app.status_changes.all().delete()

        self.run_command()

        self.assertFalse(app.status_changes.exists())

    def test_afterwards_the_flow_diagram_has_one_entry_point(self):
        """The point of the exercise: every application enters at `saved`, so the funnel
        starts where a funnel should — and the reconciliation still holds, which is what
        proves the rewrite was consistent rather than merely quiet."""
        from tracker.views import _status_flow

        self.logged_at(9406, "closed", timezone.now() - dt.timedelta(days=9))
        self.logged_at(9407, "applied", timezone.now() - dt.timedelta(days=8))
        self.run_command()

        flow = _status_flow()
        # Nothing arrives part-way along any more, so there is no entry stub left to draw:
        # `saved` is simply where the funnel starts.
        self.assertEqual([l for l in flow["links"] if l["kind"] == "entry"], [])
        self.assertEqual(flow["mid_funnel"], 0)
        self.assertEqual(flow["entered"], Application.objects.count())
        self.assertTrue(flow["reconciles"])


class HeadlineMetricsTests(TestCase):
    """The "At a glance" row (2026-09-30) on `/stats/` and in `/jobstudio status`.

    What is pinned is what each number is *out of*: submitted applications only, "ever
    reached" for the two outcomes, and the recent window measured from first submission.
    """

    fixtures = FIXTURE

    def setUp(self):
        Application.objects.all().delete()  # cascades to the status log

    def walked(self, num, path, days_ago):
        """`path`, one step a day, ending `days_ago` days back."""
        app = Application.objects.create(num=num, company_name=f"Co {num}", role="Role",
                                         status=path[-1])
        ApplicationStatusChange.objects.filter(application=app).delete()
        end = timezone.now().replace(hour=12) - dt.timedelta(days=days_ago)
        for i, status in enumerate(path):
            ApplicationStatusChange.objects.create(
                application=app, changed_at=end - dt.timedelta(days=len(path) - 1 - i),
                from_status=path[i - 1] if i else "", to_status=status)
        return app

    def test_rates_are_out_of_submitted_applications_only(self):
        from tracker.views import _headline_metrics

        self.walked(9601, ["saved", "applied", "interviewing", "rejected"], 5)
        self.walked(9602, ["saved", "applied", "rejected"], 5)
        self.walked(9603, ["saved", "applied"], 5)
        self.walked(9604, ["saved", "applied"], 5)
        self.walked(9605, ["saved", "discarded"], 5)  # never a bet: not in the base
        h = _headline_metrics()
        self.assertEqual(h["submitted"], 4)
        # Interviewed-then-rejected counts in both.
        self.assertEqual((h["interviewed"], h["pct_interviewed"]), (1, 25))
        self.assertEqual((h["rejected"], h["pct_rejected"]), (2, 50))
        self.assertEqual((h["awaiting"], h["pct_awaiting"]), (2, 50))
        self.assertEqual(h["resolved"], 2)

    def test_the_recent_pace_counts_first_submissions_in_the_window(self):
        from tracker.views import HEADLINE_RECENT_WEEKS, _headline_metrics

        self.walked(9611, ["saved", "applied"], 3)
        self.walked(9612, ["saved", "applied"], 3)
        self.walked(9613, ["saved", "applied"], 7 * HEADLINE_RECENT_WEEKS + 100)
        h = _headline_metrics()
        self.assertEqual(h["recent"], 2)
        self.assertEqual(h["per_week_recent"], round(2 / HEADLINE_RECENT_WEEKS, 1))
        self.assertLess(h["per_week_all"], h["per_week_recent"])

    def test_with_nothing_submitted_the_row_says_so_rather_than_showing_zeros(self):
        self.walked(9621, ["saved"], 1)
        html = self.client.get("/stats/").content.decode()
        self.assertIn("No application has reached", html)
        self.assertNotIn("reached interview</div>", html)

    def test_the_row_leads_the_stats_page_and_the_cli_report_but_not_the_dashboard(self):
        import io
        from contextlib import redirect_stdout

        import jobsdb

        self.walked(9631, ["saved", "applied", "rejected"], 2)
        stats = self.client.get("/stats/").content.decode()
        self.assertLess(stats.index("At a glance"), stats.index('id="ageing"'))
        self.assertNotIn("At a glance", self.client.get("/").content.decode())
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            jobsdb.print_status_report(jobsdb.dashboard_summary())
        self.assertIn("rejected          100%", buffer.getvalue())


class AppliedStepBackfillTests(TestCase):
    """`backfill_applied_step` — a rejection or an interview implies an application.

    Backfilled history ran `saved -> rejected` with the submission missing. The command
    edits existing rows, so what is pinned is that it inserts exactly one `applied` step,
    in the right order, on a midnight-preserving date, and leaves `closed` alone.
    """

    fixtures = FIXTURE

    def walked(self, num, path):
        app = Application.objects.create(num=num, company_name=f"Co {num}", role="Role",
                                         status=path[-1])
        ApplicationStatusChange.objects.filter(application=app).delete()
        start = timezone.now().replace(microsecond=0) - dt.timedelta(days=30)
        for i, status in enumerate(path):
            ApplicationStatusChange.objects.create(
                application=app, changed_at=start + dt.timedelta(days=i),
                from_status=path[i - 1] if i else "", to_status=status)
        return app, start

    def run_command(self, **options):
        out = StringIO()
        call_command("backfill_applied_step", stdout=out, stderr=StringIO(), **options)
        return out.getvalue()

    def history(self, app):
        return [(c.from_status, c.to_status, c.changed_at)
                for c in app.status_changes.order_by("changed_at", "pk")]

    def test_a_rejection_gains_an_applied_step_a_day_after_saved(self):
        app, start = self.walked(9501, ["saved", "rejected"])
        self.run_command()
        day = dt.timedelta(days=1)
        self.assertEqual(self.history(app), [
            ("", "saved", start - day),         # moved back one day
            ("saved", "applied", start),        # the old `saved` moment
            ("applied", "rejected", start + day),  # untouched date
        ])

    def test_an_interview_after_saved_gains_one_and_later_steps_are_untouched(self):
        app, start = self.walked(9502, ["saved", "interviewing", "rejected"])
        self.run_command()
        steps = [(f, t) for f, t, _ in self.history(app)]
        self.assertEqual(steps, [("", "saved"), ("saved", "applied"),
                                 ("applied", "interviewing"), ("interviewing", "rejected")])

    def test_closed_and_already_applied_are_left_alone_and_a_rerun_is_a_no_op(self):
        closed, _ = self.walked(9503, ["saved", "closed"])
        applied, _ = self.walked(9504, ["saved", "applied", "rejected"])
        target, _ = self.walked(9505, ["saved", "rejected"])
        before = {a.pk: self.history(a) for a in (closed, applied)}
        self.run_command()
        once = self.history(target)
        self.run_command()
        for a in (closed, applied):
            self.assertEqual(self.history(a), before[a.pk])
        self.assertEqual(self.history(target), once)

    def test_a_dry_run_writes_nothing(self):
        app, _ = self.walked(9506, ["saved", "rejected"])
        before = self.history(app)
        out = self.run_command(dry_run=True)
        self.assertIn("Dry run", out)
        self.assertEqual(self.history(app), before)


class CvPageTests(TestCase):
    """`/cvs/` — the master-CV cards and the tailored table (2026-09-28)."""

    fixtures = FIXTURE

    def test_each_master_cv_is_a_card_with_its_own_figures(self):
        from cvs.models import BaseCv

        html = self.client.get("/cvs/").content.decode()
        self.assertEqual(html.count('class="card"'), BaseCv.objects.count())
        for cv in BaseCv.objects.all():
            with self.subTest(slug=cv.slug):
                self.assertIn(f'href="/cvs/base/{cv.slug}/"', html)
                self.assertIn(str(cv.stats["words"]), html)

    def test_the_figures_are_read_off_the_file(self):
        """Not stored: the file is the source of truth, and a CV edited in an editor rather
        than through the app would leave a stored copy quietly wrong."""
        from cvs.models import BaseCv

        cv = BaseCv.objects.first()
        self.assertTrue(cv.stats["exists"])
        self.assertEqual(cv.stats["words"], len(cv.full_path.read_text().split()))
        self.assertIsNotNone(cv.stats["modified"])

    def test_a_row_whose_file_is_gone_reports_the_file_missing(self):
        """The model still has to describe a vanished file honestly rather than as a
        zero-word CV — the page below now clears such rows, but a file can always
        disappear between a refresh and a read."""
        from cvs.models import BaseCv

        cv = BaseCv.objects.create(slug="gone", label="Missing CV",
                                   path="jobs/cv/base/gone.md")
        self.assertFalse(cv.stats["exists"])

    def test_a_row_whose_file_is_gone_is_cleared_rather_than_listed(self):
        """Since 2026-09-29 the CV page re-syncs itself against jobs/cv/base/ (see
        tracker/derived.py), so a row with no file behind it is stale data and gets
        pruned — not rendered forever as 'file missing'."""
        from cvs.models import BaseCv
        from tracker import derived

        derived._seen.clear()
        BaseCv.objects.create(slug="gone", label="Missing CV", path="jobs/cv/base/gone.md")
        self.client.get("/cvs/")
        self.assertFalse(BaseCv.objects.filter(slug="gone").exists())

    def test_the_tailored_table_shows_each_application_status(self):
        from cvs.views import tailored_cvs

        rows = tailored_cvs()
        self.assertTrue(rows, "fixture has no tailored CVs to show a status for")
        html = self.client.get("/cvs/").content.decode()
        for row in rows:
            with self.subTest(num=row["app"].num):
                self.assertIn(f'st-{row["app"].status}', html)


class JobsDbTests(TestCase):
    """src/jobsdb.py is what the standalone pipeline scripts use instead of parsing
    markdown. It runs outside Django's test database, so only pure lookups are checked."""

    fixtures = FIXTURE

    def test_find_application_by_number_and_prefix(self):
        import jobsdb
        self.assertEqual(jobsdb.find_application("1")["company"], "Grafana Labs")
        self.assertTrue(jobsdb.find_application("Grafana")["role"])

    def test_known_job_urls_are_populated(self):
        import jobsdb
        self.assertTrue(all(u.startswith("http") for u in jobsdb.known_job_urls()))

    def test_update_company_touches_only_the_fields_passed(self):
        """`#41`. `add-company` existed and nothing could change a row afterwards, so an
        agent had to shell out to the Django admin. Only-what-you-pass is the whole
        contract: a command that reset the fields it was not given would be worse than no
        command, because the loss would be invisible."""
        import jobsdb
        from tracker.models import Company

        before = Company.objects.get(num=1)
        original = (before.name, before.notes, before.category_id, before.url)
        row = jobsdb.update_company("1", role_target="Analytics Engineer", fit=5)

        after = Company.objects.get(num=1)
        self.assertEqual(after.role_target, "Analytics Engineer")
        self.assertEqual(after.fit, 5)
        self.assertEqual((after.name, after.notes, after.category_id, after.url), original,
                         "a field that was not passed must not be touched")
        self.assertEqual(row["role_target"], "Analytics Engineer")

    def test_update_company_can_clear_a_field(self):
        """A stale careers URL has to be clearable, which is why the defaults are a
        sentinel rather than None — the second-person install pass found two tracked URLs
        gone bad (a 404 and a redirect to an acquirer) and had no command to fix either."""
        import jobsdb
        from tracker.models import Company

        self.assertTrue(Company.objects.get(num=1).url, "fixture company should have a URL")
        jobsdb.update_company("1", url="")
        self.assertEqual(Company.objects.get(num=1).url, "")

    def test_update_company_refuses_an_unknown_category(self):
        """Reuses `add-company`'s resolver rather than inventing a laxer rule: silently
        dropping an unknown name reports success and surfaces later as a company scored
        against the wrong target area."""
        import jobsdb
        from tracker.models import Company

        before = Company.objects.get(num=1).category_id
        with self.assertRaises(ValueError):
            jobsdb.update_company("1", category="No Such Category")
        self.assertEqual(Company.objects.get(num=1).category_id, before)

    def test_update_company_refuses_an_ambiguous_prefix(self):
        """The one place this resolver is deliberately stricter than `find_application`,
        which resolves a prefix to the lowest `num`. A read can afford that guess; an
        update cannot — editing the wrong company silently is worse than being asked to
        be specific."""
        import jobsdb
        from tracker.models import Category, Company

        cat = Category.objects.first()
        Company.objects.create(num=900, name="Grafana Clone", slug="grafana-clone",
                               category=cat, date_added=dt.date.today())
        with self.assertRaises(ValueError) as caught:
            jobsdb.update_company("Grafana", fit=1)
        self.assertIn("more than one", str(caught.exception))

    def test_update_company_resolves_by_number_name_and_prefix(self):
        import jobsdb

        self.assertEqual(jobsdb.update_company("1", fit=4)["num"], "1")
        name = jobsdb.update_company("1", fit=4)["name"]
        self.assertEqual(jobsdb.update_company(name, fit=3)["num"], "1")
        self.assertEqual(jobsdb.update_company(name[:6], fit=2)["num"], "1")

    def test_update_application_touches_only_the_fields_passed(self):
        """Discarding a role used to leave its next action saying "Review CV and apply" —
        `set-status` could change the status and nothing could change the rest. Status and
        next action in one call is the case it was built for."""
        import jobsdb
        from tracker.models import Application

        before = Application.objects.get(num=1)
        original = (before.role, before.summary, before.notes, before.contact, before.job_url)
        row = jobsdb.update_application(1, status="discarded", next_action="")

        after = Application.objects.get(num=1)
        self.assertEqual(after.status, "discarded")
        self.assertEqual(after.next_action, "", "an empty string must clear the field")
        self.assertEqual((after.role, after.summary, after.notes, after.contact, after.job_url),
                         original, "a field that was not passed must not be touched")
        self.assertEqual(row["status"], "discarded")

    def test_status_writes_refuse_an_unknown_status(self):
        """Same check as the web app's status menu: an unknown value would save, then sort
        last and match no status filter."""
        import jobsdb
        from tracker.models import Application

        before = Application.objects.get(num=1).status
        with self.assertRaises(ValueError):
            jobsdb.update_application(1, status="binned")
        with self.assertRaises(ValueError):
            jobsdb.set_status(1, "binned")
        self.assertEqual(Application.objects.get(num=1).status, before)

    def test_set_cv_base_changes_the_stored_base(self):
        """`#60` — a `cv --base` override deliberately leaves the stored value alone, so
        making a switch permanent needs its own command. Nothing on the agent-native path
        could change `cv_base` before this."""
        import jobsdb
        from tracker.models import Application
        row = jobsdb.set_cv_base(1, "chronological")
        self.assertEqual(row["cv_base"], "chronological")
        self.assertEqual(Application.objects.get(num=1).cv_base, "chronological")

    def test_set_cv_base_refuses_an_unknown_base(self):
        """An unknown value would save fine and then match no base CV on the next
        tailoring run — the same reason the web app checks statuses from the URL."""
        import jobsdb
        from tracker.models import Application
        before = Application.objects.get(num=1).cv_base
        with self.assertRaises(ValueError):
            jobsdb.set_cv_base(1, "reverse-chronological")
        self.assertEqual(Application.objects.get(num=1).cv_base, before)


class CategoryBootstrapTests(TestCase):
    """`#38` — a fresh tracker has no categories, and until now nothing outside the
    Django admin could make one. These guard the two halves of that fix: creating a
    category from the CLI layer, and refusing to write a company into one that isn't
    there rather than dropping the name on the floor."""

    fixtures = FIXTURE

    def test_a_category_can_be_created_and_re_creating_is_a_no_op(self):
        import jobsdb
        from tracker.models import Category

        first = jobsdb.add_category(name="Research Infrastructure", order=7)
        self.assertTrue(first["created"])

        again = jobsdb.add_category(name="Research Infrastructure", order=99)
        self.assertFalse(again["created"])
        self.assertEqual(again["order"], 7, "an existing category keeps its hand-set order")
        self.assertEqual(Category.objects.filter(name="Research Infrastructure").count(), 1)

    def test_an_unknown_category_is_refused_rather_than_silently_dropped(self):
        """The old behaviour reported success and wrote an uncategorised row — which
        also sends the company to scan-config's default_area instead of its own."""
        import jobsdb

        before = Company.objects.count()
        with self.assertRaises(ValueError) as caught:
            jobsdb.add_company(name="Ghost Ltd", category="Nope Not A Category")
        self.assertIn("add-category", str(caught.exception))
        self.assertEqual(Company.objects.count(), before, "nothing is written on a bad category")

    def test_a_company_lands_in_a_category_that_exists(self):
        import jobsdb

        jobsdb.add_category(name="Scientific Publishing")
        row = jobsdb.add_company(name="Ghost Ltd", category="Scientific Publishing",
                                 url="https://jobs.lever.co/ghostltd")
        self.assertEqual(row["category"], "Scientific Publishing")

    def test_no_category_at_all_is_still_allowed(self):
        """Not every company needs one, and `company.md` only requires a category when
        the user has confirmed a taxonomy — an empty string must not become an error."""
        import jobsdb
        row = jobsdb.add_company(name="Ghost Ltd")
        self.assertEqual(row["category"], "")


class ScanCoverageCliTests(TestCase):
    """`#38` — the same coverage answer, asked before a careers URL is written rather
    than after. Bootstrapping a tracker picks URLs from research, and one that resolves
    to no board makes the company invisible to `scan`."""

    fixtures = FIXTURE

    def test_the_cli_names_the_platform_for_a_readable_board(self):
        import scan_sources
        out = StringIO()
        with mock.patch("sys.stdout", out):
            scan_sources._main(["Unknown Co", "https://jobs.lever.co/unknownco"])
        self.assertIn("scanned via lever", out.getvalue())

    def test_the_cli_gives_the_specific_reason_when_it_cannot(self):
        import scan_sources
        out = StringIO()
        with mock.patch("sys.stdout", out):
            scan_sources._main(["Acme Ltd", "https://acme.com/careers"])
        self.assertIn("NOT scanned", out.getvalue())
        self.assertIn(scan_sources.BESPOKE, out.getvalue())

    def test_a_missing_url_is_its_own_reason(self):
        import scan_sources
        out = StringIO()
        with mock.patch("sys.stdout", out):
            scan_sources._main(["Nobody Ltd"])
        self.assertIn(scan_sources.NO_URL, out.getvalue())


class TargetAreaCheckTests(TestCase):
    """`#39` — `scan_config.check()` is what stops a scan that silently scores against
    nothing. Every failure it reports is one the scanner itself swallows: it does
    `profiles.get(area, {})` and carries on, emitting Area Scores that mean nothing."""

    fixtures = FIXTURE

    def setUp(self):
        import scan_config
        self.scan_config = scan_config
        self._saved_cache = scan_config._cache
        self.targets = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.targets, ignore_errors=True)

    def tearDown(self):
        self.scan_config._cache = self._saved_cache

    def _config(self, **kwargs):
        self.scan_config._cache = kwargs

    def _target(self, slug, body=None):
        (self.targets / f"{slug}.yaml").write_text(body if body is not None else (
            "name: Data Platform\n"
            "description: Platforms other engineers run their data on.\n"
            "key_terms:\n  - data platform\n  - dbt\n"))

    def _levels(self, **kwargs):
        return [(lvl, msg) for lvl, msg in
                self.scan_config.check(targets=self.targets, **kwargs)]

    def _errors(self, **kwargs):
        return [msg for lvl, msg in self._levels(**kwargs) if lvl == self.scan_config.ERROR]

    def test_an_empty_targets_dir_is_the_headline_error(self):
        """The fresh-data-root case: a scan runs, reports, and means nothing."""
        self._config()
        errors = self._errors()
        self.assertEqual(len(errors), 1)
        self.assertIn("nothing can be scored", errors[0])

    def test_a_target_missing_its_scoring_fields_is_reported(self):
        self._config()
        self._target("thin", "name: Thin\n")
        errors = self._errors()
        self.assertTrue(any("'description'" in e for e in errors))
        self.assertTrue(any("'key_terms'" in e for e in errors))

    def test_an_unquoted_colon_entry_is_caught_in_the_source_file(self):
        """`- SciGraph: a knowledge graph` parses as a mapping, not a string.
        `parsers._flatten_yaml_list` repairs that for the web app's display; nothing
        repairs it for the scorer, which gets a dict where a term should be."""
        self._config()
        self._target("colon",
                     "name: Colon\ndescription: x\nkey_terms:\n  - SciGraph: a graph\n")
        self.assertTrue(any("quote any entry" in e for e in self._errors()))

    def test_a_mapping_pointing_at_a_missing_area_is_an_error(self):
        self._config(category_to_area={"Fintech": "nonexistent"})
        self._target("data-platform")
        self.assertTrue(any("no nonexistent.yaml" in e for e in self._errors()))

    def test_a_default_area_pointing_at_a_missing_area_is_an_error(self):
        self._config(default_area="gone")
        self._target("data-platform")
        self.assertTrue(any("default_area" in e for e in self._errors()))

    def test_an_unmapped_category_is_fine_when_the_fallback_resolves(self):
        self._config(default_area="data-platform")
        self._target("data-platform")
        self.assertEqual(self._errors(tracked_categories=["Fintech"]), [])

    def test_an_unmapped_category_is_an_error_when_there_is_no_fallback(self):
        self._config()
        self._target("data-platform")
        errors = self._errors(tracked_categories=["Fintech"])
        self.assertTrue(any("no area at all" in e for e in errors))

    def test_a_mapping_for_a_category_nobody_tracks_is_only_a_warning(self):
        """Usually a renamed category. It does nothing, which is worth saying, but the
        scan still resolves every company it actually meets."""
        self._config(default_area="data-platform",
                     category_to_area={"Old Name": "data-platform"})
        self._target("data-platform")
        levels = self._levels(tracked_categories=["Fintech"])
        self.assertTrue(any(lvl == self.scan_config.WARN and "Old Name" in msg
                            for lvl, msg in levels))
        self.assertEqual(self._errors(tracked_categories=["Fintech"]), [])

    def test_the_example_data_root_passes_its_own_check(self):
        """The shipped example is what on-ramp A hands someone as a working search, and
        what the test suite is pinned to — its config must actually resolve."""
        self.scan_config._cache = None
        with mock.patch.object(self.scan_config, "targets_dir",
                               return_value=Path(settings.TARGETS_DIR)), \
             mock.patch.object(self.scan_config, "path",
                               return_value=Path(settings.JOBS_DIR) / "scan-config.yaml"):
            results = self.scan_config.check(
                tracked_categories=[c.name for c in Category.objects.all()])
        self.assertEqual([m for lvl, m in results if lvl == self.scan_config.ERROR], [])
        # No warnings either: until 2026-09-25 the example's `category_to_area` was keyed
        # on two category names its own fixture never had, so both entries were dead and
        # every example company fell through to `default_area` — which made
        # `developer-advocacy` unreachable in the dataset shipped to demonstrate it.
        self.assertEqual([m for lvl, m in results if lvl == self.scan_config.WARN], [])


class AreaPickingTests(TestCase):
    """`scan_match.pick_area` — which rubric a posting is judged against.

    The important property is the first test: for a company with one area this must be
    byte-identical to the old `is_plausible_match` gate, or multi-area support silently
    changes every existing scan."""

    PROFILES = {
        "ai-safety": {"key_terms": ["interpretability", "alignment", "red teaming"]},
        "ai-knowledge-work": {"key_terms": ["knowledge graph", "LLM orchestration", "product"]},
    }

    def test_one_area_behaves_exactly_like_the_old_gate(self):
        import scan_match
        role_target = "Head of Data Products"
        for title in ["Research Engineer, Interpretability", "Head of Data Products",
                      "Chef de Partie", "Alignment Scientist", "Warehouse Operative"]:
            with self.subTest(title=title):
                picked = scan_match.pick_area(title, role_target, ["ai-safety"], self.PROFILES)
                gate = scan_match.is_plausible_match(
                    title, role_target, self.PROFILES["ai-safety"]["key_terms"])
                self.assertEqual(picked is not None, gate)

    def test_a_posting_goes_to_the_area_its_title_matches(self):
        import scan_match
        self.assertEqual(
            scan_match.pick_area("Research Engineer, Interpretability", "Head of Data",
                                 ["ai-knowledge-work", "ai-safety"], self.PROFILES),
            "ai-safety")
        self.assertEqual(
            scan_match.pick_area("Product Manager, Knowledge Graph", "Head of Data",
                                 ["ai-safety", "ai-knowledge-work"], self.PROFILES),
            "ai-knowledge-work")

    def test_order_decides_a_tie(self):
        """Both areas' key terms match once, so the listed preference settles it."""
        import scan_match
        title = "Interpretability Product Lead"
        self.assertEqual(scan_match.pick_area(title, "", ["ai-safety", "ai-knowledge-work"],
                                              self.PROFILES), "ai-safety")
        self.assertEqual(scan_match.pick_area(title, "", ["ai-knowledge-work", "ai-safety"],
                                              self.PROFILES), "ai-knowledge-work")

    def test_a_role_target_only_match_falls_to_the_preferred_area(self):
        """The company's own role target has always been accepted by the pre-filter; a
        posting it describes must not be dropped just because no key term matched."""
        import scan_match
        self.assertEqual(
            scan_match.pick_area("Solutions Architect", "Solutions Architect",
                                 ["ai-safety", "ai-knowledge-work"], self.PROFILES),
            "ai-safety")

    def test_no_match_anywhere_drops_the_posting(self):
        import scan_match
        self.assertIsNone(scan_match.pick_area("Warehouse Operative", "Head of Data",
                                               ["ai-safety"], self.PROFILES))

    def test_an_area_with_no_profile_on_disk_does_not_crash(self):
        """The hollow-profile case from `#39` — it degrades to the role_target fallback."""
        import scan_match
        self.assertEqual(scan_match.pick_area("Head of Data", "Head of Data",
                                              ["gone"], {}), "gone")
        self.assertIsNone(scan_match.pick_area("Warehouse Operative", "Head of Data",
                                               ["gone"], {}))


class CompanyAreasConfigTests(TestCase):
    """`company_areas` — the per-company override that lets one company be scanned
    against more than one positioning."""

    fixtures = FIXTURE

    def setUp(self):
        import scan_config
        self.scan_config = scan_config
        self._saved = scan_config._cache
        self.targets = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.targets, ignore_errors=True)
        for slug in ("ai-safety", "ai-knowledge-work"):
            (self.targets / f"{slug}.yaml").write_text(
                f"name: {slug}\ndescription: x\nkey_terms:\n  - {slug}\n")

    def tearDown(self):
        self.scan_config._cache = self._saved

    def test_a_bare_slug_is_read_as_a_one_item_list(self):
        self.scan_config._cache = {"company_areas": {"Anthropic": "ai-safety"}}
        self.assertEqual(self.scan_config.company_areas(), {"Anthropic": ["ai-safety"]})

    def test_a_non_list_non_string_value_is_refused(self):
        self.scan_config._cache = {"company_areas": {"Anthropic": {"a": 1}}}
        with self.assertRaises(ValueError):
            self.scan_config.company_areas()

    def test_check_flags_an_area_with_no_target_file(self):
        self.scan_config._cache = {"company_areas": {"Anthropic": ["ai-safety", "nope"]}}
        results = self.scan_config.check(targets=self.targets)
        self.assertTrue(any(lvl == self.scan_config.ERROR and "nope" in msg
                            for lvl, msg in results))

    def test_check_warns_on_a_single_area_entry_that_buys_nothing(self):
        self.scan_config._cache = {"company_areas": {"Anthropic": ["ai-safety"]}}
        results = self.scan_config.check(targets=self.targets)
        self.assertTrue(any(lvl == self.scan_config.WARN and "single area" in msg
                            for lvl, msg in results))

    def test_check_warns_when_the_company_is_not_tracked(self):
        """Keyed by name, so a rename makes the entry do nothing — and the company
        silently reverts to its category's single area."""
        self.scan_config._cache = {
            "company_areas": {"Anthropik": ["ai-safety", "ai-knowledge-work"]}}
        results = self.scan_config.check(targets=self.targets,
                                         tracked_companies=["Anthropic"])
        self.assertTrue(any(lvl == self.scan_config.WARN and "Anthropik" in msg
                            for lvl, msg in results))

    def test_soft_negatives_reads_a_list_or_a_bare_string(self):
        self.scan_config._cache = {"soft_negatives": "Heavily political orgs"}
        self.assertEqual(self.scan_config.soft_negatives(), ["Heavily political orgs"])
        self.scan_config._cache = {}
        self.assertEqual(self.scan_config.soft_negatives(), [])

    def test_the_rubric_documents_soft_negatives(self):
        """An unread field is decoration — the scorer only applies what the rubric says."""
        import config
        rubric = config.REPO_ROOT / "src" / "prompts" / "scan_score_rubric.md"
        text = rubric.read_text()
        self.assertIn("soft_negatives", text)
        self.assertIn("never let one keep a strong role out of the report", text)


class MultiAreaReportTests(TestCase):
    """The report's one hard assumption was that a company's area never varies inside its
    group. It does now — but only for companies in `company_areas`, and the single-area
    output must be untouched."""

    def _cand(self, title, area, **kw):
        from scan_report import Candidate
        c = Candidate(company="Anthropic", title=title, url=f"https://x/{title}",
                      role_target="Head of Data", area=area, category="AI Safety",
                      location="London", **kw)
        c.cv_score, c.ideal_score, c.location_category = 4, 4, "uk"
        return c

    def test_a_single_area_company_keeps_the_old_shape(self):
        import scan_report
        lines = scan_report._match_table_by_company(
            [self._cand("Research Engineer", "ai-safety"),
             self._cand("Research Scientist", "ai-safety")])
        body = "\n".join(lines)
        self.assertIn("*AI Safety → ai-safety*", body)
        self.assertIn("| Role | Location | Area Score | Ideal-Job Score | Notes |", body)
        self.assertNotIn("| Area |", body)

    def test_a_multi_area_company_gets_an_area_column(self):
        import scan_report
        lines = scan_report._match_table_by_company(
            [self._cand("Research Engineer", "ai-safety"),
             self._cand("Product Manager", "ai-knowledge-work")])
        body = "\n".join(lines)
        self.assertIn("scored per role", body)
        self.assertIn("| Role | Area | Location | Area Score | Ideal-Job Score | Notes |", body)
        self.assertIn("ai-safety", body)
        self.assertIn("ai-knowledge-work", body)


class AtsDetectionTests(TestCase):
    """Ashby, SmartRecruiters and Teamtailor name their board in the URL as plainly as
    Lever does; until 2026-09-27 each needed a hand-written override anyway."""

    def test_self_describing_board_urls_are_detected(self):
        import scan_sources
        for url, platform, param, value in [
            ("https://jobs.ashbyhq.com/bluedot", "ashby", "token", "bluedot"),
            ("https://careers.smartrecruiters.com/AcmeCorp", "smartrecruiters", "token", "AcmeCorp"),
            ("https://jobs.smartrecruiters.com/AcmeCorp", "smartrecruiters", "token", "AcmeCorp"),
            ("https://acme.teamtailor.com/jobs", "teamtailor", "domain", "acme.teamtailor.com"),
        ]:
            with self.subTest(url=url):
                src = scan_sources.resolve_source("X", url)
                self.assertEqual(src["platform"], platform)
                self.assertEqual(src[param], value,
                                 "the key must be the one that platform's fetcher reads")

    def test_a_vendors_own_site_is_not_read_as_a_board(self):
        import scan_sources
        for url in ["https://www.teamtailor.com/en/", "https://www.bamboohr.com/"]:
            with self.subTest(url=url):
                self.assertIsNone(scan_sources.resolve_source("X", url))


class PipelineTests(TestCase):
    """The pipeline scripts the web app shares code with."""

    fixtures = FIXTURE

    def test_pick_cv_defaults_to_the_functional_cv(self):
        """The functional CV is the default format; the _no_vp seniority heuristic is gone."""
        import appfolder
        row = {"num": "9404", "company": "No Folder Co", "role": "Data Lead",
               "area": "data-platform", "status": "saved"}
        picked = appfolder.pick_cv(row)
        self.assertIsNotNone(picked)
        self.assertEqual(picked.name, "cv_functional.md")
        self.assertNotIn("_no_vp", picked.name)

    def test_pick_cv_prefers_the_copy_in_the_folder(self):
        import appfolder
        row = {"num": "1", "company": "Grafana Labs", "role": "Senior Developer Advocate",
               "area": "developer-advocacy", "status": "applied"}
        picked = appfolder.pick_cv(row)
        self.assertTrue(appfolder.is_app_cv(picked.name), picked.name)
        self.assertIn("001-grafana-labs", str(picked))

    def test_is_app_cv_recognises_area_named_cvs(self):
        """Per-application CVs are usually named after the target AREA, not the base CV.

        The previous implementation matched only cv-functional / cv-chronological /
        cv_functional, so any CV tailored to an area was invisible — 15 of the 30 in
        the author's job search — and pick_cv() silently fell back to the base. Pure
        filename logic on purpose: no fixture, no folder on disk, nothing that depends
        on whatever happens to be in one person's job search.
        """
        import appfolder
        tailored = [
            "004-incident-io-alex-rivera-cv-ai-knowledge-work-2026-06-23.md",
            "003-dbt-labs-alex-rivera-cv-data-platform-no-lead-2026-06-07.md",
            "002-acme-analytics-alex-rivera-cv-knowledge-graph-2026-06-07.md",
            "030-northwind-foundation-alex-rivera-cv-functional-2026-07-01.md",
            "001-grafana-labs-alex-rivera-cv-developer-advocacy-2026-09-15.md",
            "2026-06-07_cv_data_platform_dbt_labs.md",          # old naming
        ]
        for name in tailored:
            self.assertTrue(appfolder.is_app_cv(name), f"should belong to an app: {name}")

        not_tailored = [
            "cv_functional.md",                                  # the base CV itself
            "cv_chronological.md",
            "notes.md",
            "job.md",
            "004-incident-io-alex-rivera-cover-letter-2026-09-03.md",
        ]
        for name in not_tailored:
            self.assertFalse(appfolder.is_app_cv(name), f"should NOT belong to an app: {name}")

    def test_functional_cv_has_the_section_the_tailoring_splices(self):
        """generate_functional() splices on these markers — fail loudly if they move."""
        from django.conf import settings
        cv = (Path(settings.CV_DIR) / "base" / "cv_functional.md").read_text()
        self.assertIn("## Core Competencies", cv)
        start = cv.index("## Core Competencies")
        self.assertIn("\n## ", cv[start + 20:], "no section follows Core Competencies")


class MechanicalCvCopyTests(TestCase):
    """The per-application CV copy — TODO #55, 2026-10-01.

    Logging an application no longer tailors anything: the folder gets a mechanical
    copy of the base CV, named for the application, with the role in brackets stripped
    from every Core Competencies bullet. The copy is what gets refined by hand (or
    tailored later, on request), so these tests guard the two things that can go
    silently wrong — stripping roles where the role is the point, and a refresh
    overwriting work that has already been done.
    """

    fixtures = FIXTURE

    ROW = {"num": "900", "company": "Test Co", "role": "Data Lead",
           "area": "data-platform", "status": "saved"}

    def _folder(self):
        folder = Path(tempfile.mkdtemp()) / "900-test-co"
        folder.mkdir()
        return folder

    def test_the_copy_is_named_for_the_application_not_the_base(self):
        """Decided 2026-10-01: the standard name even when nothing was changed — the file a
        person edits and sends should be named for the job it is going to."""
        import appfolder
        folder = self._folder()
        dest = appfolder.copy_cv(self.ROW, folder)
        self.assertIsNotNone(dest)
        self.assertTrue(dest.name.startswith("900-test-co-"), dest.name)
        self.assertIn("-cv-functional-", dest.name)
        self.assertTrue(appfolder.is_app_cv(dest.name), dest.name)

    def test_the_copy_drops_the_role_in_brackets_from_the_competencies(self):
        import appfolder
        dest = appfolder.copy_cv(self.ROW, self._folder())
        body = dest.read_text()
        competencies = body[body.index("## Core Competencies"):]
        competencies = competencies[:competencies.index("\n## ")]
        self.assertIn("- **Kestrel Financial:**", competencies)
        self.assertNotIn("(Senior Data Platform Engineer):**", competencies)

    def test_career_history_keeps_its_role_titles(self):
        """The regex is scoped to one section for exactly this reason: in Career /
        Employment History the role title is the whole content of the line."""
        import appfolder
        dest = appfolder.copy_cv(self.ROW, self._folder())
        body = dest.read_text()
        self.assertIn("Senior Data Platform Engineer", body[body.index("## Career History"):])

    def test_a_bullet_with_no_employer_prefix_is_left_alone(self):
        import appfolder
        text = ("## Core Competencies\n\n### Community\n\n"
                "- Maintains **some-lib** (a small package) used by others.\n"
                "- **Acme (Head of Data):** did the work.\n\n"
                "## Career History\n\n- Head of Data (Acme) — *2020*\n")
        out = appfolder.strip_competency_roles(text)
        self.assertIn("- Maintains **some-lib** (a small package)", out)
        self.assertIn("- **Acme:** did the work.", out)
        self.assertIn("- Head of Data (Acme) — *2020*", out)

    def test_a_cv_with_no_competencies_section_is_copied_verbatim(self):
        """The chronological base has no Core Competencies at all — the transform must
        be a no-op there rather than a guess at the nearest thing."""
        import appfolder
        text = "# Someone\n\n## Experience\n\n**Engineer (Acme)** | 2020\n"
        self.assertEqual(appfolder.strip_competency_roles(text), text)

    def test_a_second_run_does_not_touch_the_cv_already_there(self):
        """`ensure_folder` is run again on every refresh. Before #55 that was safe
        because the copy was byte-identical; now the file in the folder is the one
        being worked on, so overwriting it would lose the work."""
        import appfolder
        folder = self._folder()
        dest = appfolder.copy_cv(self.ROW, folder)
        dest.write_text(dest.read_text() + "\n- A line I added by hand.\n")
        again = appfolder.copy_cv(self.ROW, folder)
        self.assertEqual(again, dest)
        self.assertIn("by hand", dest.read_text())
        self.assertEqual(len([p for p in folder.glob("*.md")]), 1)

    def test_an_older_folder_keeps_its_bare_cv_functional(self):
        """Folders scaffolded before #55 are not migrated — the same stance export/
        took in 2026-09-24."""
        import appfolder
        folder = self._folder()
        (folder / "cv_functional.md").write_text("# Someone\n")
        appfolder.copy_cv(self.ROW, folder)
        self.assertEqual([p.name for p in folder.glob("*.md")], ["cv_functional.md"])

    def test_untouched_is_content_not_filename(self):
        """The name says "this CV belongs to application 900" and nothing more, so
        "has anyone worked on it?" has to read the file."""
        import appfolder
        dest = appfolder.copy_cv(self.ROW, self._folder())
        self.assertTrue(appfolder.is_untouched_copy(dest))
        dest.write_text(dest.read_text().replace("## Summary", "## Summary\n\nTailored."))
        self.assertFalse(appfolder.is_untouched_copy(dest))

    def test_an_untouched_copy_is_not_counted_as_tailored(self):
        """/cvs/ lists the CVs actually written for a role. Every application has a
        file named like a tailored CV now, so an unedited copy must not inflate it."""
        import appfolder
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        folder = root / "jobs" / "applications" / "900-test-co"
        folder.mkdir(parents=True)
        dest = appfolder.copy_cv(self.ROW, folder)

        app = Application.objects.get(num=1)
        app.folder = "jobs/applications/900-test-co"
        with override_settings(DATA_ROOT=str(root)):
            self.assertEqual([c["name"] for c in app.cv_files], [dest.name])
            self.assertTrue(app.cv_files[0]["untouched"])
            self.assertEqual(app.tailored_cvs, [])

            dest.write_text(dest.read_text() + "\n- Rewritten for this role.\n")
            self.assertFalse(app.cv_files[0]["untouched"])
            self.assertEqual([c["name"] for c in app.tailored_cvs], [dest.name])

    def test_one_cv_per_base_coexists_and_each_gets_a_distinct_anchor(self):
        """`#60` — asking for the other base adds a CV rather than replacing one, so the
        tab indexes them. Distinct anchors are the whole point: two links to the same id
        would scroll to the same CV and the index would silently lie."""
        import appfolder
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        folder = root / "jobs" / "applications" / "900-test-co"
        folder.mkdir(parents=True)
        func = folder / "900-test-co-alex-rivera-cv-functional-2026-09-14.md"
        chron = folder / "900-test-co-alex-rivera-cv-chronological-2026-10-01.md"
        func.write_text("# Alex Rivera\n\nFunctional.\n")
        chron.write_text("# Alex Rivera\n\nChronological.\n")

        app = Application.objects.get(num=1)
        app.folder = "jobs/applications/900-test-co"
        with override_settings(DATA_ROOT=str(root)):
            cvs = app.cv_files
            self.assertEqual(len(cvs), 2, "both bases must survive; neither replaces the other")
            anchors = [c["anchor"] for c in cvs]
            self.assertEqual(len(set(anchors)), 2, f"anchors must be distinct, got {anchors}")
            self.assertTrue(all(a.startswith("cv-") for a in anchors))
            labels = {c["label"] for c in cvs}
            self.assertEqual(labels, {"Functional", "Chronological"})
            self.assertTrue(all(c["date"] for c in cvs), "the index shows a date per CV")

    def test_the_cv_index_appears_only_from_two_cvs_up(self):
        """Same rule the interview-round index follows — a list of one is noise."""
        import appfolder
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        folder = root / "jobs" / "applications" / "900-test-co"
        folder.mkdir(parents=True)
        appfolder.copy_cv(self.ROW, folder)

        app = Application.objects.get(num=1)
        app.folder = "jobs/applications/900-test-co"
        app.save()
        with override_settings(DATA_ROOT=str(root)):
            one = self.client.get(f"/applications/{app.num}/").content.decode()
            self.assertNotIn('aria-label="CVs for this application"', one)

            (folder / "900-test-co-alex-rivera-cv-chronological-2026-10-01.md").write_text(
                "# Alex Rivera\n\nChronological.\n")
            two = self.client.get(f"/applications/{app.num}/").content.decode()
            self.assertIn('aria-label="CVs for this application"', two)


class AdminViewOnSiteTests(TestCase):
    fixtures = FIXTURE

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        cls.user = User.objects.create_superuser("vos_test", "vos@example.com", "x")

    def setUp(self):
        self.client.force_login(self.user)

    def _view_on_site(self, obj, admin_path):
        """The admin renders a 'View on site' button linking to /admin/r/<ct>/<pk>/,
        which redirects to the model's get_absolute_url — assert the whole hop."""
        html = self.client.get(f"{admin_path}{obj.pk}/change/").content.decode()
        self.assertIn("viewsitelink", html)
        r = self.client.get(f"/admin/r/{ContentType.objects.get_for_model(obj).pk}/{obj.pk}/")
        self.assertIn(r.status_code, (301, 302))
        return r["Location"]

    def test_application_change_form_links_to_the_public_page(self):
        app = Application.objects.first()
        target = self._view_on_site(app, "/admin/tracker/application/")
        self.assertTrue(target.endswith(f"/applications/{app.num}/"), target)

    def test_company_change_form_links_to_the_public_page(self):
        company = Company.objects.first()
        target = self._view_on_site(company, "/admin/tracker/company/")
        self.assertTrue(target.endswith(f"/companies/{company.slug}/"), target)


class TabsTests(TestCase):
    """The application page's sections are tabs, but must degrade to a readable stack."""

    fixtures = FIXTURE

    def test_all_panels_are_present_in_the_html(self):
        """Panels are rendered visible; tabs.js hides the inactive ones. Without JS the
        whole page must still be there — the published site is a plain file mirror."""
        app = Application.objects.get(num=1)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        for panel in ("record", "notes", "letters", "job", "cv", "history"):
            with self.subTest(panel=panel):
                self.assertIn(f'data-panel="{panel}"', html)
                self.assertIn(f'data-tab="{panel}"', html)
        # no panel is server-side hidden
        self.assertNotIn("tabpanel\" data-panel=\"record\" role=\"tabpanel\" hidden", html)

    def test_history_tab_is_never_omitted(self):
        """Unlike the other tabs, History always has something to show — every
        application gets at least a "logged as" entry, backfilled or signal-written."""
        for app in Application.objects.all()[:5]:
            html = self.client.get(f"/applications/{app.num}/").content.decode()
            self.assertIn('data-tab="history"', html)

    def test_tabs_are_omitted_when_a_section_is_empty(self):
        app = Application.objects.filter(folder="").first()
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        self.assertNotIn('data-tab="job"', html)
        self.assertNotIn('data-tab="notes"', html)

    def test_tab_script_is_loaded(self):
        html = self.client.get("/applications/1/").content.decode()
        self.assertIn("js/tabs.js", html)

    def test_static_build_accepts_cross_page_tab_links(self):
        """Regression: /areas/ folded its per-area detail pages into tabs (2026-09-14),
        so other pages now link a specific area as /areas/#<slug> (tabs.js reads
        location.hash on load) rather than a real /areas/<slug>/ path. build_static's
        link checker used to resolve the href literally, including the "#slug" — which
        is never a file on disk — and failed the whole build. It must strip the
        fragment and check only the path.
        """
        self.assertTrue(Area.objects.filter(applications__isnull=False).exists(),
                         "fixture needs at least one area with an application, to " +
                         "produce a /areas/#<slug> link somewhere in the built site")
        # build_static.handle() sets settings.ENVIRONMENT = "publish" directly (not via
        # override_settings) and never resets it — self.settings() still restores
        # whatever it was before this block on exit, regardless of how it changed inside.
        with tempfile.TemporaryDirectory() as tmp, self.settings(ENVIRONMENT="local"):
            call_command("build_static", output=tmp, clean=True, stdout=StringIO())


class SidebarTests(TestCase):
    """The Applications sub-nav."""

    fixtures = FIXTURE

    def test_interviewing_is_listed_first_under_applications(self):
        """The sub-nav runs down the funnel, and Interviewing is the status where
        something is already in motion and needs preparing for."""
        html = self.client.get("/").content.decode()
        order = ["/applications/status/interviewing/",
                 "/applications/status/reviewing/",
                 "/applications/status/saved/",
                 "/applications/all/"]
        positions = [html.index(f'href="{h}"') for h in order]
        self.assertEqual(positions, sorted(positions), "sub-nav is out of funnel order")

    def test_the_interviewing_page_marks_its_own_sidebar_entry(self):
        html = self.client.get("/applications/status/interviewing/").content.decode()
        self.assertIn('href="/applications/status/interviewing/" class="nav-sub active"',
                      html.replace("  ", " "))


class FitSummaryTests(TestCase):
    """The pros/cons/unknowns boxes on the Record tab, driven by the Application fields."""

    fixtures = FIXTURE

    def test_renders_for_an_application_with_fit_data(self):
        # #1 is the fully-populated example application.
        app = Application.objects.get(num=1)
        self.assertTrue(app.has_fit_summary)
        html = self.client.get("/applications/1/").content.decode()
        self.assertIn("fit-grid", html)
        # Pin the banner-class convention, not one application's level — the old
        # assertion hardcoded "is-stretch" because that is what #30 happened to be
        # in the original pre-synthetic fixture.
        self.assertIn(f"fit-banner is-{app.fit_level}", html)
        for pro in app.fit_summary["pros"]:
            self.assertIn(escape(pro), html)

    def test_absent_when_no_fit_data(self):
        app = Application.objects.create(num=9600, company_name="NoFit Co",
                                        role="Test Role", notes="Just the record.")
        self.assertFalse(app.has_fit_summary)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        self.assertNotIn("fit-grid", html)
        self.assertIn('data-panel="record"', html)  # the Record tab still renders

    def test_lines_split_on_newlines_and_stripped(self):
        app = Application(num=9500, company_name="X", role="Y",
                          fit_pros="  - first\n* second\n\n  third  ")
        self.assertEqual(app.fit_summary["pros"], ["first", "second", "third"])


class ActivityTimelineTests(TestCase):
    """The dashboard activity timeline — weekly buckets of added/applied/rejected."""

    fixtures = FIXTURE

    def test_weeks_are_contiguous(self):
        weeks = self.client.get("/").context["activity"]
        self.assertGreater(len(weeks), 1)
        for earlier, later in zip(weeks, weeks[1:]):
            self.assertEqual((later["start"] - earlier["start"]).days, 7)

    def test_event_totals_match_the_database(self):
        weeks = self.client.get("/").context["activity"]
        self.assertEqual(
            sum(w["applied"] for w in weeks),
            ApplicationStatusChange.objects.filter(to_status="applied").count())
        self.assertEqual(
            sum(w["added"] for w in weeks),
            Application.objects.exclude(date__isnull=True).count())

    def test_timeline_markup_present(self):
        self.assertContains(self.client.get("/"), "tl-bars")


class StatBarTests(TestCase):
    """The boxed status header is shared between the dashboard and the list views."""

    fixtures = FIXTURE

    def test_present_on_dashboard_and_list(self):
        for url in ["/", "/applications/", "/applications/active/",
                    "/applications/status/applied/"]:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'class="stats"')

    def test_current_view_box_is_marked_active(self):
        html = self.client.get("/applications/status/applied/").content.decode()
        self.assertIn("stat is-active", html)
        active_html = self.client.get("/applications/active/").content.decode()
        self.assertIn("stat is-active", active_html)

    def test_dashboard_has_no_active_box(self):
        self.assertNotIn("stat is-active", self.client.get("/").content.decode())

    def test_statbar_links_are_real_paths(self):
        html = self.client.get("/applications/").content.decode()
        hrefs = re.findall(r'<a class="stat[^"]*" href="([^"]+)"', html)
        self.assertTrue(hrefs)
        for href in hrefs:
            self.assertFalse("?" in href, href)


class DefaultActiveListTests(TestCase):
    """/applications/ defaults to the active set; /applications/all/ is the full list."""

    fixtures = FIXTURE
    ACTIVE = ["applied", "interviewing"]

    def test_bare_list_shows_only_active(self):
        apps = self.client.get("/applications/").context["applications"]
        self.assertTrue(apps)
        self.assertTrue(all(a.status in self.ACTIVE for a in apps))

    def test_reviewing_is_not_active(self):
        apps = self.client.get("/applications/").context["applications"]
        self.assertFalse(any(a.status == "reviewing" for a in apps))

    def test_all_path_shows_everything(self):
        n = self.client.get("/applications/all/").context["applications"].count()
        self.assertEqual(n, Application.objects.count())

    def test_active_alias_matches_bare_list(self):
        a = [x.pk for x in self.client.get("/applications/").context["applications"]]
        b = [x.pk for x in self.client.get("/applications/active/").context["applications"]]
        self.assertEqual(a, b)

    def test_sidebar_groups_fold_and_open_where_the_page_is(self):
        """`#94`: Applications, Notes and Portal scans are <details> groups, not links.
        The group the page is in renders open; the others start closed. Applications lists
        only the three working statuses (2026-10-21)."""
        html = self.client.get("/companies/").content.decode()
        for name in ("applications", "notes", "scans"):
            with self.subTest(group=name):
                self.assertIn(f'<details class="nav-fold" data-fold="{name}">', html)
        self.assertNotIn('<a href="/notes/" class=', html)
        group = html[html.index('data-fold="applications"'):html.index('data-fold="notes"')]
        self.assertEqual(re.findall(r'href="(/applications/[^"]*)"', group),
                         ["/applications/status/interviewing/", "/applications/status/reviewing/",
                          "/applications/status/saved/"])

        listing = self.client.get("/applications/").content.decode()
        self.assertIn('<details class="nav-fold" data-fold="applications" open data-inside>',
                      listing)

    def test_notes_sub_items_are_the_notes_tabs(self):
        html = self.client.get("/").content.decode()
        group = html[html.index('data-fold="notes"'):html.index('data-fold="scans"')]
        self.assertIn('href="/notes/#search"', group)
        self.assertIn('href="/notes/#topics"', group)
        # Each carries its count, matching the Notes page's own tab counts.
        notes_page = self.client.get("/notes/").content.decode()
        for slug, count in re.findall(
                r'data-tab="([\w-]+)"[^>]*>[^<]*<span class="tab-count">(\d+)</span>', notes_page):
            with self.subTest(tab=slug):
                self.assertRegex(group, rf'data-tab-link="{slug}"[^>]*>\s*[^<]*'
                                        rf'<span class="nav-count">{count}</span>')

    def test_the_sidebar_can_collapse_to_an_icon_rail(self):
        """`#96`: a toggle collapses the sidebar to icons. It starts `hidden`, since it only
        works with nav.js; the saved choice is applied in <head>, before first paint; and
        every top-level entry has an icon plus a <span> label, which nav.js turns into the
        entry's tooltip in the rail."""
        html = self.client.get("/companies/").content.decode()
        self.assertRegex(html, r'<button type="button" class="side-toggle" hidden')
        head = html[:html.index("<body>")]
        self.assertIn('localStorage.getItem("jobstudio.nav.collapsed")', head)
        nav = html[html.index('<nav class="sidebar">'):html.index("</nav>")]
        entries = re.findall(r'<a href="[^"]*" class="(?!nav-sub)[^"]*"[^>]*>\s*(.*?)</a>'
                             r'|<summary class="nav-head[^"]*">\s*(.*?)</summary>', nav, re.S)
        self.assertGreater(len(entries), 5)
        for link, summary in entries:
            body = link or summary
            with self.subTest(entry=body[:60]):
                self.assertRegex(body, r'^<svg class="ico"[^>]*><use href="#i-[\w-]+"/></svg>'
                                       r'<span>[^<]+</span>')

    def test_sidebar_has_reviewing_link_not_active(self):
        html = self.client.get("/").content.decode()
        self.assertIn('href="/applications/status/reviewing/"', html)
        self.assertIn('href="/applications/all/"', html)

    def test_nav_counts_active_excludes_reviewing(self):
        html = self.client.get("/").content.decode()
        # context processor value
        from tracker.context_processors import site_context
        counts = site_context(self.client.get("/").wsgi_request)["nav_counts"]
        self.assertEqual(
            counts["active"],
            Application.objects.filter(status__in=self.ACTIVE).count())
        self.assertEqual(
            counts["reviewing"],
            Application.objects.filter(status="reviewing").count())


class ApplicationFolderTests(TestCase):
    """All application folders live directly under jobs/applications/ (no archive/ split
    by status, retired 2026-09-08) — the stored path must still resolve on disk."""

    fixtures = FIXTURE

    def test_stored_folder_path_resolves(self):
        for app in Application.objects.exclude(folder=""):
            with self.subTest(num=app.num):
                stored = Path(settings.DATA_ROOT) / app.folder
                self.assertTrue(stored.is_dir(), f"#{app.num} folder path is stale: {app.folder}")
                self.assertNotIn("/archive/", f"/{app.folder}/",
                                 f"#{app.num} still points into the retired archive/ tree")

    def test_cover_letters_on_disk_are_surfaced(self):
        """Cover letters are scanned from the application folder by naming convention
        (no DB row) — if a non-empty .md file is on disk it must appear in
        cover_letter_files. Catches a stale Application.folder hiding them."""
        import appfolder

        for app in Application.objects.exclude(folder=""):
            with self.subTest(num=app.num):
                on_disk = [p for p in app.folder_path.iterdir()
                           if appfolder.is_cover_letter_filename(p.name)
                           and p.suffix == ".md" and p.read_text().strip()]
                if on_disk:
                    self.assertTrue(app.cover_letter_files,
                                    f"#{app.num} has cover letters on disk but none surfaced")
                # A cover-letter file (even an empty ensure_folder() stub) must never
                # fall through to the "Other files" tab.
                leaked = [f["name"] for f in app.extra_files
                          if appfolder.is_cover_letter_filename(f["name"])]
                self.assertFalse(leaked, f"#{app.num}: cover letter(s) leaked into extra_files: {leaked}")


class ExportFolderTests(TestCase):
    """Rendered copies of an application's markdown live in `<folder>/export/` (2026-09-24),
    so the top level holds only what was authored. Folders written before that keep the
    .docx beside its markdown and are deliberately not migrated, so every reader here has
    to go on working against both shapes."""

    fixtures = FIXTURE

    def _cv_markdown(self):
        app = Application.objects.get(num=1)
        cvs = app.cv_snapshots
        self.assertTrue(cvs, "fixture app #1 needs a CV snapshot")
        return app, cvs[0]

    def _place(self, path: Path) -> Path:
        """Put a stand-in export on disk, and take it away again afterwards — including
        the `export/` directory itself when this test is what created it."""
        if not path.parent.is_dir():
            path.parent.mkdir(parents=True)
            self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_bytes(b"not really a .docx")
        self.addCleanup(path.unlink, True)
        return path

    def test_an_export_is_linked_from_its_tab_and_not_repeated_under_other_files(self):
        """The CV tab's "Open .docx" link and the Other files tab are the two halves of
        the same question — a file belongs to exactly one of them."""
        import appfolder

        app, cv_md = self._cv_markdown()
        docx = self._place(appfolder.export_dir(app.folder_path) / cv_md.with_suffix(".docx").name)

        linked = [c["docx"] for c in app.cv_files if c["name"] == cv_md.name]
        self.assertEqual([p.resolve() for p in linked if p], [docx.resolve()])
        self.assertNotIn(docx.name, [f["name"] for f in app.extra_files])

    def test_a_cover_letter_export_is_linked_from_its_tab(self):
        import appfolder

        app = Application.objects.get(num=1)
        letters = [p for p in app.folder_path.iterdir()
                   if appfolder.is_cover_letter_filename(p.name) and p.suffix == ".md"
                   and p.read_text().strip()]
        self.assertTrue(letters, "fixture app #1 needs a written cover letter")
        md = letters[0]
        docx = self._place(appfolder.export_dir(app.folder_path) / md.with_suffix(".docx").name)

        linked = [l["docx_path"] for l in app.cover_letter_files if l["name"] == md.name]
        self.assertEqual([p.resolve() for p in linked if p], [docx.resolve()])
        self.assertNotIn(docx.name, [f["name"] for f in app.extra_files])

    def test_an_export_opens_in_the_desktop_app_and_nothing_links_to_vs_code(self):
        """#81: a `vscode://` link can take over an open VS Code window, so none are left;
        an export opens through the same local opener as Open folder."""
        import appfolder
        from unittest import mock

        app, cv_md = self._cv_markdown()
        docx = self._place(appfolder.export_dir(app.folder_path) / cv_md.with_suffix(".docx").name)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        self.assertNotIn("vscode:", html)
        self.assertIn("/actions/open-file/?path=", html)

        rel = docx.resolve().relative_to(Path(settings.DATA_ROOT).resolve())
        with mock.patch("tracker.views._open_locally") as opened:
            self.assertEqual(self.client.get("/actions/open-file/", {"path": str(rel)}).status_code, 302)
            opened.assert_called_once()
            for bad in (str(cv_md.relative_to(Path(settings.DATA_ROOT).resolve())), "nope.docx"):
                with self.subTest(path=bad):
                    self.assertEqual(self.client.get("/actions/open-file/", {"path": bad}).status_code, 404)

    def test_a_docx_beside_its_markdown_is_still_found(self):
        """Pre-2026-09-24 folders are not migrated; dropping the flat lookup would make
        every .docx already on disk vanish from the tab that links it."""
        app, cv_md = self._cv_markdown()
        docx = cv_md.with_suffix(".docx")
        docx.write_bytes(b"not really a .docx")
        self.addCleanup(docx.unlink, True)

        linked = [c["docx"] for c in app.cv_files if c["name"] == cv_md.name]
        self.assertEqual([p.resolve() for p in linked if p], [docx.resolve()])
        self.assertNotIn(docx.name, [f["name"] for f in app.extra_files])

    def test_an_export_rendered_on_a_later_day_is_still_linked(self):
        """The copy is named with the date of the render, not of the markdown it renders,
        so a letter re-rendered a week later has a stem its source does not share. Nine
        of 34 exports in the real job search were orphaned this way."""
        import appfolder

        app, cv_md = self._cv_markdown()
        later = appfolder.export_dir(app.folder_path) / cv_md.name.replace(
            "2026-09-15", "2026-09-22").replace(".md", ".docx")
        self.assertNotEqual(later.stem, cv_md.stem, "this test needs mismatched stems")
        self._place(later)

        linked = [c["docx"] for c in app.cv_files if c["name"] == cv_md.name]
        self.assertEqual([p.resolve() for p in linked if p], [later.resolve()])
        self.assertNotIn(later.name, [f["name"] for f in app.extra_files])

    def test_a_superseded_render_stays_visible_rather_than_being_linked(self):
        """Two renders of one source: the newest is the current one. The older is not
        wrong, just stale — it keeps its place under Other files."""
        import appfolder

        app, cv_md = self._cv_markdown()
        export = appfolder.export_dir(app.folder_path)
        stem = cv_md.name.replace(".md", "")
        old = self._place(export / f"{stem.replace('2026-09-15', '2026-09-21')}.docx")
        new = self._place(export / f"{stem.replace('2026-09-15', '2026-09-22')}.docx")

        linked = [c["docx"] for c in app.cv_files if c["name"] == cv_md.name]
        self.assertEqual([p.resolve() for p in linked if p], [new.resolve()])
        rels = [f["rel"] for f in app.extra_files]
        self.assertIn(f"{appfolder.EXPORT_DIRNAME}/{old.name}", rels)
        self.assertNotIn(f"{appfolder.EXPORT_DIRNAME}/{new.name}", rels)

    def test_two_sources_of_one_kind_means_no_guess(self):
        """Folders scaffolded before 2026-10-01 carry a bare `cv_functional.md` beside
        the per-application CV. With two candidate sources, pairing an export with one of
        them is a guess — and linking the same file under two headings reads as two
        documents."""
        import appfolder

        app, cv_md = self._cv_markdown()
        scaffold = app.folder_path / "cv_functional.md"
        scaffold.write_text("# Base CV\n")
        self.addCleanup(scaffold.unlink, True)
        self._place(appfolder.export_dir(app.folder_path)
                    / cv_md.name.replace("2026-09-15", "2026-09-22").replace(".md", ".docx"))

        self.assertEqual([c["docx"] for c in app.cv_files if c["docx"]], [])

    def test_the_export_folder_is_not_read_as_a_round_of_cover_letters(self):
        """`find_cover_letters()` treats a `cover-letter-*/` directory as a folder of
        drafts. `export/` sits in the same place and holds a file whose name matches the
        cover-letter pattern — it must not be walked into as if it were one."""
        import appfolder

        app = Application.objects.get(num=1)
        folder = app.folder_path
        self._place(appfolder.export_dir(folder)
                    / appfolder.app_filename(folder, "cover-letter", "md"))

        inside_export = [l["path"] for l in P.find_cover_letters(folder)
                         if appfolder.EXPORT_DIRNAME in l["path"].parts]
        self.assertFalse(inside_export, f"export/ read as cover letters: {inside_export}")

    def test_anything_else_in_export_still_shows_under_other_files(self):
        """`extra_files` exists so nothing saved into an application folder goes invisible.
        Moving exports down one level must not turn `export/` into a blind spot."""
        import appfolder

        app = Application.objects.get(num=1)
        stray = self._place(appfolder.export_dir(app.folder_path) / "recruiter-brief.pdf")
        self.assertIn(f"{appfolder.EXPORT_DIRNAME}/{stray.name}",
                      [f["rel"] for f in app.extra_files])


class MigrateExportsCommandTests(TestCase):
    """`manage.py migrate_exports` tidies folders written before 2026-09-24, when a
    rendered .docx sat flat beside its markdown. Readers accept both shapes, so this is
    housekeeping, not a prerequisite — which is why it must be conservative about what
    it touches."""

    fixtures = FIXTURE

    def setUp(self):
        import appfolder

        self.app = Application.objects.get(num=1)
        self.folder = self.app.folder_path
        # Whatever this test creates, top level or below, goes away again.
        self.addCleanup(shutil.rmtree, appfolder.export_dir(self.folder), ignore_errors=True)

    def _flat(self, name: str) -> Path:
        path = self.folder / name
        path.write_bytes(b"not really a .docx")
        self.addCleanup(path.unlink, True)
        return path

    def _run(self, *args) -> str:
        out = StringIO()
        call_command("migrate_exports", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_a_flat_export_moves_and_is_then_linked_from_its_tab(self):
        import appfolder

        cv_md = self.app.cv_snapshots[0]
        flat = self._flat(cv_md.with_suffix(".docx").name)
        self.assertIsNotNone(exported_file(cv_md), "precondition: linked where it lies")

        self._run("--apply")

        moved = appfolder.export_dir(self.folder) / flat.name
        self.assertFalse(flat.exists(), "the flat copy should be gone, not duplicated")
        self.assertTrue(moved.is_file())
        self.assertEqual(exported_file(cv_md).resolve(), moved.resolve())

    def test_a_dry_run_writes_nothing(self):
        """The default. A migration that moves real files on a bare invocation is one
        you cannot look at before it happens."""
        import appfolder

        flat = self._flat("001-grafana-labs-alex-rivera-cv-functional-2026-09-15.docx")
        out = self._run()

        self.assertIn("--apply", out)
        self.assertTrue(flat.is_file(), "a dry run must leave the file where it is")
        self.assertFalse(appfolder.export_dir(self.folder).exists())

    def test_authored_and_hand_saved_files_stay_put(self):
        """Only files following the folder's own naming convention are renders. A JD or
        a recruiter's PDF dropped in by hand is someone's filing, and moving it would be
        this command deciding something it has no business deciding."""
        import appfolder

        by_hand = self._flat("JD Technology Lead Aug 2026.pdf")
        markdown = sorted(self.folder.glob("*.md"))
        self.assertTrue(markdown, "fixture app #1 needs markdown to leave alone")

        self._run("--apply")

        self.assertTrue(by_hand.is_file(), "a hand-saved file must not be swept up")
        for md in markdown:
            self.assertTrue(md.is_file(), f"{md.name} was moved — only renders should be")
        self.assertFalse(appfolder.export_dir(self.folder).exists())

    def test_re_running_is_safe_and_never_overwrites(self):
        import appfolder

        name = "001-grafana-labs-alex-rivera-cv-functional-2026-09-15.docx"
        self._flat(name)
        self._run("--apply")
        moved = appfolder.export_dir(self.folder) / name
        moved.write_bytes(b"the one that was already there")

        clash = self._flat(name)  # a second flat copy of a name export/ already holds
        out = self._run("--apply")

        self.assertIn("skip", out)
        self.assertTrue(clash.is_file(), "the clashing file is left for a human to sort out")
        self.assertEqual(moved.read_bytes(), b"the one that was already there")


class RenderDestinationTests(TestCase):
    """Since 2026-09-24 a render is written once, where its source lives (`render._home()`).
    Before that everything went to `exports/` and application .docx were copied back —
    two copies of each file, and a flat dated tree that named neither the source nor, for
    22 of them, any application at all."""

    fixtures = FIXTURE

    def setUp(self):
        import render

        self.render = render
        self.addCleanup(shutil.rmtree, render.CV_EXPORT_DIR, ignore_errors=True)

    def test_a_render_of_an_application_file_goes_to_that_folder(self):
        import appfolder

        app = Application.objects.get(num=1)
        src = app.cv_snapshots[0]
        dest = self.render._home(src, "cv-functional", "docx", stem="2026-09-24_cv_functional")
        self.addCleanup(shutil.rmtree, appfolder.export_dir(app.folder_path), ignore_errors=True)

        self.assertEqual(dest.parent.resolve(), appfolder.export_dir(app.folder_path).resolve())
        self.assertTrue(dest.name.startswith(app.folder_path.name), dest.name)
        self.assertTrue(dest.name.endswith(".docx"))

    def test_a_render_takes_its_sources_stem_and_date_not_todays(self):
        """#80: a CV tailored on one day and rendered on the next used to carry two
        dates. The .docx is named after the .md, so the two always pair exactly."""
        import appfolder

        app = Application.objects.get(num=1)
        src = app.folder_path / f"{app.folder_path.name}-alex-rivera-cv-functional-2020-01-02.md"
        dest = self.render._home(src, "cv-functional", "docx", stem="unused")
        self.addCleanup(shutil.rmtree, appfolder.export_dir(app.folder_path), ignore_errors=True)
        self.assertEqual(dest.name, f"{src.stem}.docx")
        self.assertEqual(appfolder.export_dir(app.folder_path) / dest.name, dest)

    def test_a_render_of_a_base_cv_goes_to_jobs_cv_export(self):
        """Named like jobs/cv/base/archive/, the other place a dated copy of a base CV
        lives, so the two read as one convention."""
        src = self.render.BASE_CV_DIR / "cv_functional.md"
        self.assertTrue(src.is_file(), "example data needs a base functional CV")

        dest = self.render._home(src, "cv-functional", "docx", stem="2026-09-24_cv_functional")

        self.assertEqual(dest.parent.resolve(), self.render.CV_EXPORT_DIR.resolve())
        self.assertRegex(dest.name, r"^cv_functional-\d{4}-\d{2}-\d{2}\.docx$")

    def test_a_source_with_no_home_falls_back_to_exports(self):
        """`exports/` is not dead — it is where a document belonging to no folder goes:
        a career stocktake, or an ad-hoc `--file` from outside the data root."""
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.render._home(Path(tmp) / "adhoc.md", "cover-letter", "docx",
                                     stem="2026-09-24_cover-letter")
        self.assertIn("exports", dest.parts)
        self.assertEqual(dest.name, "2026-09-24_cover-letter.docx")

    def test_nothing_is_written_twice(self):
        """The regression this replaced: a render landed in exports/ AND was copied to the
        application, so every file existed twice under two different names."""
        import inspect

        source = inspect.getsource(self.render)
        self.assertNotIn("_maybe_copy_to_app_folder", source)


class HighlightTests(TestCase):
    """#77: select text on a page and it becomes `==text==` in the markdown. The page
    shows rendered text, so the hard part is finding that text in the source without
    ever splitting a construct; these pin the cases that would."""

    fixtures = FIXTURE
    DOC = ("# Title\n\nGrafana sells **observability** software. See [the docs](https://x.y/z)"
           " for more.\n\n- [ ] Read three RFCs and have an opinion on one.\n- Keep the"
           " story to `three` minutes.\n\n| A | B |\n|---|---|\n| alpha one | beta two |\n\n"
           "Grafana sells software twice.\n\n```\nGrafana sells code\n```\n")

    def _add(self, selected, before="", after=""):
        from tracker.highlights import add
        return add(self.DOC, selected, before, after)

    def test_a_selection_never_splits_a_construct(self):
        self.assertIn("Grafana ==sells **observability**== software", self._add("sells observability"))
        self.assertIn("See ==[the docs](https://x.y/z) for== more", self._add("the docs for"))
        self.assertIn("==to `three` minutes==", self._add("to three minutes"))

    def test_a_selection_snaps_to_whole_words(self):
        self.assertIn("==Read three RFCs== and", self._add("ead three RF", "- [ ] R", "Cs and"))

    def test_line_markers_stay_outside_the_highlight(self):
        self.assertIn("- [ ] ==Read three RFCs== and", self._add("Read three RFCs"))

    def test_a_selection_across_lines_or_cells_is_one_highlight_each(self):
        out = self._add("opinion on one.\nKeep the")
        self.assertIn("have an ==opinion on one.==\n- ==Keep the== story", out)
        self.assertIn("| ==alpha one== | ==beta two== |", self._add("alpha one\tbeta two"))

    def test_repeated_text_is_placed_by_its_context_or_refused(self):
        from tracker.highlights import HighlightError
        with self.assertRaises(HighlightError):
            self._add("Grafana sells")
        self.assertIn("==Grafana sells== software twice", self._add("Grafana sells", "", " software twice"))

    def test_headings_code_and_overlaps_are_refused(self):
        from tracker.highlights import HighlightError, add
        for sel in ("Title", "not in the file"):
            with self.subTest(sel=sel), self.assertRaises(HighlightError):
                self._add(sel)
        with self.assertRaises(HighlightError):
            add(self._add("Read three RFCs"), "three RFCs and")

    def test_remove_undoes_add_and_marks_are_counted_outside_code(self):
        from tracker.highlights import mark_spans, remove
        out = self._add("Read three RFCs")
        self.assertEqual(remove(out, 0), self.DOC)
        self.assertEqual(mark_spans("`==code==` and ==real==\n```\n==fenced==\n```\n"), [(15, 23)])
        self.assertEqual(mark_spans("Title\n=====\n"), [])

    def test_marks_render_live_locally_and_read_only_when_published(self):
        from tracker.parsers import sectioned
        from tracker.templatetags.jobs_extras import markdownify
        live = sectioned("## A\n\nSome ==key line== here.\n", "n", source="jobs/x.md")
        self.assertIn('<mark class="hl" data-mark="0">key line</mark>', live["blocks"][0]["body_md"])
        self.assertEqual(live["source"], "jobs/x.md")
        self.assertIn('<mark class="hl">key line</mark>', markdownify("Some ==key line== here."))

    def test_the_endpoint_writes_the_file_and_keeps_the_task_rules(self):
        import tempfile
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as root:
            f = Path(root) / "jobs" / "r.md"
            f.parent.mkdir()
            f.write_text("One line to keep.\n")
            with override_settings(DATA_ROOT=root, ENVIRONMENT="local"):
                post = lambda **d: self.client.post("/actions/highlight/", {"source": "jobs/r.md", **d})
                self.assertEqual(post(text="line to keep", before="One ").status_code, 200)
                self.assertEqual(f.read_text(), "One ==line to keep==.\n")
                r = post(text="nowhere")
                self.assertEqual(r.status_code, 409)
                self.assertIn("Couldn't find", r.json()["error"])
                self.assertEqual(post(remove="0").status_code, 200)
                self.assertEqual(f.read_text(), "One line to keep.\n")
                self.assertEqual(post(remove="0").status_code, 409)
                r = self.client.post("/actions/highlight/", {"source": "../x.md", "text": "a"})
                self.assertEqual(r.status_code, 404)
            with override_settings(DATA_ROOT=root, ENVIRONMENT="publish"):
                r = self.client.post("/actions/highlight/", {"source": "jobs/r.md", "text": "One"})
                self.assertEqual(r.status_code, 404)

    def test_the_job_description_and_profile_take_highlights_locally(self):
        from django.test import override_settings
        from tracker.templatetags.jobs_extras import hl_marks
        self.assertEqual(hl_marks("# T\n\n==a b==\n", "jobs/x.md"),
                         '# T\n\n<mark class="hl" data-mark="0">a b</mark>\n')
        self.assertEqual(hl_marks("==a b==", None), "==a b==")
        pages = {"/applications/1/": 'data-hl-source="jobs/applications/001-grafana-labs/job.md"',
                 "/profile/": 'data-hl-source="jobs/profile/stocktake.md"'}
        for url, attr in pages.items():
            with self.subTest(url=url):
                with override_settings(ENVIRONMENT="local"):
                    self.assertIn(attr, self.client.get(url).content.decode())
                with override_settings(ENVIRONMENT="publish"):
                    self.assertNotIn("data-hl-source", self.client.get(url).content.decode())


class UnwrapTests(TestCase):
    """Hard-wrapped prose renders as one paragraph, not a `<br />` at every wrap (`nl2br`
    stays on for the line breaks that are layout)."""

    def test_wrapped_prose_joins_and_layout_breaks_stay(self):
        from tracker.templatetags.jobs_extras import markdownify
        html = markdownify(
            "If one comes, use the author-disambiguation turnaround — failure\n"
            "modes, how it was measured.\n\n"
            "Grafana Labs runs an open observability stack used by thousands of\n"
            "Teams across every industry.\n\n"
            "**Area:** data\n**Location:** London\n\n"
            "- a bullet long enough to wrap past the column edge in the source file\n"
            "  and carry on here.\n- next\n\n"
            "a highlight across a wrap, which is one mark per line in the\n"
            '  <mark class="hl">file</mark> and still one line on the page.\n\n'
            "> a quoted answer that was wrapped at the usual column, so the quote\n"
            "> carries on here.\n\n"
            "```\ncode that is long enough to look like a wrapped line of prose, yes\n"
            "continued\n```\n\nOne sentence.\nAnother.")
        self.assertIn("turnaround — failure modes", html)
        self.assertIn("thousands of Teams", html)
        self.assertIn("<strong>Area:</strong> data<br />", html)
        self.assertIn("column edge in the source file and carry on", html)
        self.assertIn('in the <mark class="hl">file</mark>', html)
        self.assertIn("so the quote carries on", html)
        self.assertIn("yes\ncontinued", html)
        self.assertIn("One sentence.<br />", html)


class CoverLetterFormatTests(TestCase):
    """`.docx` is the version that gets sent, and since TODO `#70` the only one written.
    HTML used to come out every time because the PDF path needed something for Chrome to
    print — once renders landed in the application folder (2026-09-24) every cover letter
    left an `.html` beside its `.docx` that nobody had asked for."""

    fixtures = FIXTURE

    def setUp(self):
        import appfolder
        import render

        self.render = render
        app = Application.objects.get(num=1)
        letters = [p for p in app.folder_path.iterdir()
                   if appfolder.is_cover_letter_filename(p.name) and p.suffix == ".md"]
        self.assertTrue(letters, "fixture app #1 needs a cover letter")
        self.letter = letters[0]
        self.export = appfolder.export_dir(app.folder_path)
        self.addCleanup(shutil.rmtree, self.export, ignore_errors=True)

    def _rendered(self, ext: str) -> list[str]:
        if not self.export.is_dir():
            return []
        return sorted(p.name for p in self.export.glob(f"*.{ext}"))

    def test_a_cover_letter_renders_to_the_docx_alone(self):
        self.render.export_cover_letter(self.letter)

        self.assertEqual(len(self._rendered("docx")), 1)
        self.assertEqual(self._rendered("html"), [])
        self.assertEqual(self._rendered("pdf"), [])


class PruneExportsCommandTests(TestCase):
    """`manage.py prune_exports` empties the backlog left in exports/ by the old
    write-then-copy behaviour. It deletes, so what it will not touch matters as much as
    what it will."""

    fixtures = FIXTURE

    def setUp(self):
        self.data_root = Path(settings.DATA_ROOT)
        self.exports = self.data_root / "exports"
        self.existed = self.exports.is_dir()
        self.made: list[Path] = []
        self.addCleanup(self._tidy)

    def _tidy(self):
        for path in self.made:
            if path.is_file():
                path.unlink()
        if not self.existed:
            shutil.rmtree(self.exports, ignore_errors=True)
        shutil.rmtree(self.data_root / "jobs" / "cv" / "export", ignore_errors=True)
        for app in Application.objects.exclude(folder=""):
            if app.folder_path:
                shutil.rmtree(app.folder_path / "export", ignore_errors=True)

    def _export(self, rel: str, body: bytes = b"a render") -> Path:
        path = self.exports / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        self.made.append(path)
        return path

    def _run(self, *args) -> str:
        out = StringIO()
        call_command("prune_exports", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_a_labelled_render_moves_to_its_application_keeping_its_own_date(self):
        """The date in the name is when it was rendered. Restamping it with today's would
        turn a June PDF into a September one — the tree's only record of when it was sent."""
        import appfolder

        app = Application.objects.get(num=1)
        src = self._export(f"pdf/2026-06-23/2026-06-23_cv_data-platform_{app.folder_path.name}.pdf")

        self._run("--apply")

        dest = appfolder.export_dir(app.folder_path)
        moved = list(dest.glob("*.pdf"))
        self.assertEqual(len(moved), 1, f"expected one moved pdf, got {moved}")
        self.assertIn("cv-data-platform", moved[0].name)
        self.assertIn("2026-06-23", moved[0].name)
        self.assertFalse(src.exists())

    def test_a_copy_already_in_the_application_is_deleted_not_duplicated(self):
        import appfolder

        app = Application.objects.get(num=1)
        dest_dir = appfolder.export_dir(app.folder_path)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "already-there.docx").write_bytes(b"identical")
        src = self._export(f"docx/2026-09-22/2026-09-22_cv_functional_{app.folder_path.name}.docx",
                           b"identical")

        self._run("--apply")

        self.assertFalse(src.exists())
        self.assertEqual([p.name for p in dest_dir.glob("*")], ["already-there.docx"])

    def test_only_the_newest_base_cv_docx_survives(self):
        """Older renders of the same base CV are not history — jobs/cv/base/archive/ keeps
        that, as markdown. And .docx is the format that gets sent."""
        old = self._export("docx/2026-09-03/2026-09-03_cv_functional.docx")
        new = self._export("docx/2026-09-22/2026-09-22_cv_functional.docx")
        as_pdf = self._export("pdf/2026-09-22/2026-09-22_cv_functional.pdf")

        self._run("--apply")

        kept = sorted(p.name for p in (self.data_root / "jobs" / "cv" / "export").glob("*"))
        self.assertEqual(kept, ["cv_functional-2026-09-22.docx"])
        for path in (old, new, as_pdf):
            self.assertFalse(path.exists(), f"{path.name} should have left exports/")

    def test_a_file_that_is_not_a_render_is_left_alone(self):
        """exports/ stays the home for documents belonging to no folder. Anything not
        named the way a render is named was put there by a person, and is not this
        command's to move or delete."""
        stocktake = self._export("docx/2026-09-18/career-stocktake-sections-1-5.docx")

        out = self._run("--apply")

        self.assertTrue(stocktake.is_file())
        self.assertIn("LEAVING ALONE", out)

    def test_a_dry_run_writes_nothing(self):
        unattributable = self._export("docx/2026-09-03/2026-09-03_cv_data-platform.docx")
        base = self._export("docx/2026-09-22/2026-09-22_cv_functional.docx")

        out = self._run()

        self.assertIn("--apply", out)
        self.assertTrue(unattributable.is_file())
        self.assertTrue(base.is_file())
        self.assertFalse((self.data_root / "jobs" / "cv" / "export").exists())


class InterviewRoundTests(TestCase):
    """Interview rounds are one file per round in the application folder (2026-09-24),
    not a `## Interview prep` heading inside notes.md. Files only — no database row."""

    fixtures = FIXTURE

    def test_filename_recognition_and_stage(self):
        import appfolder

        cases = [
            ("001-grafana-labs-alex-interview-hiring-manager-2026-09-24.md", "hiring-manager",
             "Hiring manager"),
            ("001-grafana-labs-alex-interview-hr-screen-2026-09-16.md", "hr-screen", "HR screen"),
            # A multi-word stage must survive intact — matching to the date, not to the
            # first hyphen, is the whole point.
            ("interview-technical-2026-10-01.md", "technical", "Technical"),
            # No stage at all is legal; it just labels generically.
            ("001-grafana-labs-alex-interview-2026-09-24.md", "", "Interview"),
        ]
        for name, stage, label in cases:
            with self.subTest(name=name):
                self.assertTrue(appfolder.is_interview_filename(name))
                self.assertEqual(appfolder.interview_stage(name), stage)
                self.assertEqual(appfolder.interview_label(stage), label)

    def test_other_folder_files_are_not_interviews(self):
        import appfolder

        for name in ("notes.md", "job.md", "cv_functional.md",
                     "001-grafana-labs-alex-rivera-cv-developer-advocacy-2026-09-15.md",
                     "001-grafana-labs-alex-rivera-cover-letter-2026-09-15.md"):
            with self.subTest(name=name):
                self.assertFalse(appfolder.is_interview_filename(name))

    def test_a_name_that_only_mentions_interviews_or_a_letter_is_neither(self):
        """`#82`: the recognisers were substring tests, so a study note called
        `...-research-interview-themes-<date>.md` was taken for a round with the stage
        "themes" and left Other files. The tokens now count only where the convention
        puts them — `interview-[<stage>-]<date>`, `cover-letter-<date>` — and every shape
        found in real folders still matches."""
        import appfolder

        for name in ("058-acme-alex-rivera-research-interview-themes-2026-10-07.md",
                     "058-acme-alex-rivera-interview-questions-bank.md",
                     "interview-technique.md",
                     "058-acme-alex-rivera-study-interview-prep-2026-10-07.md"):
            with self.subTest(round=name):
                self.assertFalse(appfolder.is_interview_filename(name))
        for name in ("058-acme-alex-rivera-cover-letter-notes.md",
                     "058-acme-alex-rivera-cover-letter-notes-2026-10-07.md",
                     "cover-letter-ideas.md"):
            with self.subTest(letter=name):
                self.assertFalse(appfolder.is_cover_letter_filename(name))

        for name in ("001-grafana-labs-alex-rivera-cover-letter-2026-09-15.md",
                     "001-grafana-labs-alex-rivera-cover-letter-2026-09-15-v2.md",
                     "001-grafana-labs-alex-rivera-cover-letter-2026-09-15.docx",
                     "001-grafana-labs-alex-rivera-cover-letter-2026-09-15.pdf",
                     "cover-letter-2026-09-15.md",
                     "2026-09-24_cover-letter.docx"):
            with self.subTest(letter=name):
                self.assertTrue(appfolder.is_cover_letter_filename(name))
        self.assertTrue(appfolder.is_interview_filename(
            "001-grafana-labs-alex-rivera-interview-hr-screen-2026-09-18-b.md"))

    def test_a_study_note_about_interviews_stays_under_other_files(self):
        """The `#82` misfire end to end: the file is listed under Other files and is not
        shown as a round."""
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        folder = root / "jobs" / "applications" / "900-test-co"
        folder.mkdir(parents=True)
        note = "900-test-co-alex-rivera-research-interview-themes-2026-10-07.md"
        (folder / note).write_text("# Themes\n\nWhat they tend to ask.\n")
        app = Application.objects.get(num=1)
        app.folder = "jobs/applications/900-test-co"
        with override_settings(DATA_ROOT=str(root)):
            self.assertIn(note, [f["name"] for f in app.extra_files])
            self.assertEqual(app.interview_files, [])

    def test_rounds_on_disk_are_surfaced_newest_first(self):
        import appfolder

        for app in Application.objects.exclude(folder=""):
            with self.subTest(num=app.num):
                on_disk = [p for p in app.folder_path.iterdir()
                           if appfolder.is_interview_filename(p.name)
                           and p.read_text().strip()]
                self.assertEqual(len(app.interview_files), len(on_disk))
                dates = [r["date"] for r in app.interview_files if r["date"]]
                self.assertEqual(dates, sorted(dates, reverse=True),
                                 "rounds must be newest first — the one being prepped "
                                 "for is the one at the top")

    def test_rounds_never_leak_into_extra_files(self):
        """Same bargain as cover letters: a file belonging to a tab must not also show
        up under "Other files"."""
        import appfolder

        for app in Application.objects.exclude(folder=""):
            with self.subTest(num=app.num):
                leaked = [f["name"] for f in app.extra_files
                          if appfolder.is_interview_filename(f["name"])]
                self.assertFalse(leaked, f"#{app.num}: rounds leaked into extra_files: {leaked}")

    def test_interviews_tab_renders(self):
        app = Application.objects.get(num=1)
        self.assertTrue(app.interview_files, "fixture app #1 needs a round file on disk")
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        self.assertIn('data-tab="interviews"', html)
        self.assertIn('data-panel="interviews"', html)
        self.assertIn("HR screen", html)

    # The tab strip runs in the order the process does — what the role is, what you
    # wrote about it, what you sent, then who you spoke to — with History closing it
    # (`#67`). Interviews sat third until 2026-10-01, on the argument that live rounds
    # are what gets reread; that is served by linking to a round, not by tab position.
    TAB_ORDER = ("record", "job", "notes", "cv", "letters", "files",
                 "interviews", "history", "siblings")

    def test_interviews_tab_sits_last_before_history(self):
        """Interviews comes after everything you produced for the application and
        immediately before History. Asserted on the panel order too: with JS off the
        panels are the reading order."""
        app = Application.objects.get(num=1)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        for attr in ("data-tab", "data-panel"):
            with self.subTest(attr=attr):
                positions = {t: html.index(f'{attr}="{t}"')
                             for t in self.TAB_ORDER if f'{attr}="{t}"' in html}
                self.assertIn("interviews", positions)
                self.assertLess(positions["files"], positions["interviews"])
                self.assertLess(positions["interviews"], positions["history"])

    def test_tab_order_and_panel_order_agree(self):
        """The one invariant that makes moving a tab a two-part edit: tabs.js hides
        panels, so with JS off (or failing to load) the panels ARE the page, in source
        order. A button moved without its panel reads correctly only while the script
        works. Checked across every application, since which tabs exist varies."""
        for app in Application.objects.all():
            html = self.client.get(f"/applications/{app.num}/").content.decode()
            seq = {attr: sorted((t for t in self.TAB_ORDER if f'{attr}="{t}"' in html),
                                key=lambda t: html.index(f'{attr}="{t}"'))
                   for attr in ("data-tab", "data-panel")}
            with self.subTest(num=app.num):
                self.assertEqual(seq["data-tab"], seq["data-panel"])

    # ---- the in-round jump index and the focus view (`#66`) ----

    def test_sections_are_indexed_in_document_order_and_numbered(self):
        """Not against a canonical list. Rounds come in two shapes — a prep round and a
        post-interview record — and the example data carries both, so indexing against
        one vocabulary would leave the other almost entirely unmatched.

        The numbering is what makes nesting visible: the index is a flat row of pills,
        where "Follow-ups" otherwise reads as a sibling of the section it sits inside.
        """
        body = ("preamble\n\n## Questions and answers\n\ntext\n\n"
                "### Follow-ups\n\ntext\n\n### Tangents\n\ntext\n\n"
                "## What to do differently\n\ntext\n")
        split = P.split_sections(body)
        self.assertEqual(split["preamble"], "preamble")

    def test_the_preamble_drops_the_title_and_is_empty_when_that_is_all_there_is(self):
        """Every round file opens with `# Title`, which the page renders itself. Left in
        the preamble it is shown twice; filtered in the template instead, the preamble
        is empty-but-truthy and renders an empty styled box on most rounds."""
        self.assertEqual(
            P.split_sections("# HR screen — Dana\n\n## Details\n\nx\n")["preamble"],
            "")
        self.assertEqual(
            P.split_sections("# T\n\nkept\n\n## Details\n\nx\n")["preamble"],
            "kept")

    def test_strip_h1_handles_a_title_with_nothing_after_it(self):
        """Latent before `#66`: the regex required a trailing newline, so a document
        that is only a title kept it."""
        from .templatetags.jobs_extras import strip_h1
        self.assertEqual(strip_h1("# Title only"), "")
        self.assertEqual(strip_h1("# Title\nbody"), "body")

    def test_section_numbers_follow_the_document(self):
        body = ("preamble\n\n## Questions and answers\n\ntext\n\n"
                "### Follow-ups\n\ntext\n\n### Tangents\n\ntext\n\n"
                "## What to do differently\n\ntext\n")
        split = P.split_sections(body)
        got = [(s["number"], s["level"], s["label"])
               for s in P.section_index(split["blocks"])]
        self.assertEqual(got, [("1", 2, "Questions and answers"),
                               ("1.1", 3, "Follow-ups"),
                               ("1.2", 3, "Tangents"),
                               ("2", 2, "What to do differently")])

    def test_a_subsection_stays_inside_its_own_block(self):
        """`1.1` has to belong to `1`, not to whichever block renders next — the pill
        opens its parent, so a subsection filed under the wrong one opens the wrong
        section and scrolls nowhere."""
        body = "## One\n\n### Inner\n\ntext\n\n## Two\n\ntext\n"
        blocks = P.split_sections(body)["blocks"]
        self.assertEqual([b["label"] for b in blocks], ["One", "Two"])
        self.assertEqual([s["label"] for s in blocks[0]["subsections"]], ["Inner"])
        self.assertEqual(blocks[1]["subsections"], [])

    def test_sections_ignore_headings_inside_fenced_code(self):
        body = "## Real\n\n```\n## Not a heading\n```\n\n## Also real\n"
        blocks = P.split_sections(body)["blocks"]
        self.assertEqual([b["label"] for b in blocks], ["Real", "Also real"])

    def test_section_anchors_are_unique_across_rounds_on_one_page(self):
        """Two rounds of one application both carry "## Questions and answers". The tab
        stacks them into a single page, so unscoped ids would collide and every link
        would land on whichever round rendered first."""
        app = Application.objects.get(num=4)
        rounds = app.interview_files
        self.assertGreater(len(rounds), 1, "fixture app #4 needs two rounds")
        anchors = [s["anchor"] for r in rounds for s in r["sections"]]
        self.assertEqual(len(anchors), len(set(anchors)), f"collision: {anchors}")

    def test_every_nav_href_has_a_heading_to_land_on(self):
        """The nav's hrefs and the rendered heading ids come from one slug function;
        this is the assertion that they actually meet in the HTML."""
        for app in Application.objects.exclude(folder=""):
            for round_ in app.interview_files:
                html = self.client.get(f"/applications/{app.num}/").content.decode()
                for sec in round_["sections"]:
                    with self.subTest(num=app.num, anchor=sec["anchor"]):
                        self.assertIn(f'id="{sec["anchor"]}"', html)

    def test_focus_view_renders_one_round(self):
        app = Application.objects.get(num=4)
        round_ = app.interview_files[0]
        r = self.client.get(f"/applications/{app.num}/rounds/{round_['anchor']}/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn(round_["label"], html)
        # The point of the page: none of the application chrome.
        self.assertNotIn('class="sidebar"', html)
        self.assertNotIn('data-tabs', html)

    def test_focus_view_404s_on_an_unknown_round(self):
        self.assertEqual(
            self.client.get("/applications/4/rounds/round-nope-2026-01-01/").status_code,
            404)

    def test_subsection_md_takes_one_subsection_and_ignores_fenced_headings(self):
        block = ("## To do\n\n### Application\n\n- [ ] research\n\n"
                 "### Final round — 2026-10-10\n\n- [ ] demo\n```\n### not a heading\n```\n"
                 "- [ ] slides\n\n### Later\n\n- [ ] thank-you note\n")
        self.assertEqual(P.subsection_md(block, "application"), "- [ ] research")
        final = P.subsection_md(block, "final-round-2026-10-10")
        self.assertIn("- [ ] slides", final, "a fenced ### must not end the subsection")
        self.assertNotIn("thank-you", final)
        self.assertIsNone(P.subsection_md(block, "panel-2026-10-10"))

    def test_focus_view_shows_the_rounds_tasks_from_notes(self):
        """`#84`: an application's tasks live in notes.md's `## To do`, one `###` per
        round, and the round's focus view — the page open during prep — shows its own.
        Checked for a stage whose label slugs back to the stage (Hiring manager) and one
        that does not (`final` → "Final round"). Ticks must still point at notes.md."""
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        folder = root / "jobs" / "applications" / "900-test-co"
        folder.mkdir(parents=True)
        (folder / "notes.md").write_text(
            "# Test Co\n\n## To do\n\n### Application\n\n- [x] read the posting\n\n"
            "### Hiring manager — 2026-09-24\n\n- [ ] HM-TASK-ONE\n- [ ] HM-TASK-TWO\n\n"
            "### Final round — 2026-10-10\n\n- [ ] FINAL-TASK\n\n## My notes\n\nPlain.\n")
        for stage, date in (("hiring-manager", "2026-09-24"), ("final", "2026-10-10"),
                            ("panel", "2026-10-01")):
            (folder / f"900-test-co-alex-rivera-interview-{stage}-{date}.md").write_text(
                f"# {stage}\n\n## Prep\n\n- **Q:** why?\n  **A:** because.\n")

        app = Application.objects.get(num=1)
        app.folder = "jobs/applications/900-test-co"
        app.save()
        with override_settings(DATA_ROOT=str(root)):
            def page(anchor):
                return self.client.get(
                    f"/applications/{app.num}/rounds/{anchor}/").content.decode()

            hm = page("round-hiring-manager-2026-09-24")
            self.assertIn('id="notes--hiring-manager-2026-09-24"', hm)
            self.assertIn("HM-TASK-TWO", hm)
            self.assertNotIn("FINAL-TASK", hm)
            self.assertNotIn("read the posting", hm, "Application tasks are not a round's")
            # File-wide index: HM-TASK-ONE is notes.md's second task, so data-task="1".
            self.assertRegex(hm, r'data-task="1"[^>]*>\s*HM-TASK-ONE')
            self.assertIn('data-source="jobs/applications/900-test-co/notes.md"', hm)

            final = page("round-final-2026-10-10")
            self.assertIn('id="notes--final-round-2026-10-10"', final)
            self.assertIn("FINAL-TASK", final)

            self.assertNotIn("To do for this round", page("round-panel-2026-10-01"),
                             "a round with no subsection shows no empty panel")

    def test_repeated_subheadings_get_distinct_anchors(self):
        """The same `###` under two `##` sections must not share an id: the first keeps
        the bare slug, the repeat is scoped by its section. A repeat inside one section
        is still indexed, so ids stamped by position stay in step with the headings."""
        from tracker.parsers import split_sections

        md = ("## Orgs\n\n### Stack\n\nA\n\n### Scale\n\nB\n\n"
              "## People\n\n### Stack\n\nC\n\n### Stack\n\nD\n")
        blocks = split_sections(md)["blocks"]
        anchors = [s["anchor"] for b in blocks for s in b["subsections"]]
        self.assertEqual(anchors, ["stack", "scale", "people-stack", "people-stack-2"])

    def test_tagged_md_keeps_tagged_items_under_their_themes(self):
        block = ("### Domain\n\n- [ ] DOM-HM long task\n  continued @hiring-manager\n"
                 "- [ ] DOM-UNTAGGED\n\n### Tech & Data\n\n- [x] TECH-HR @hr-screen\n"
                 "- [ ] TECH-HM @Hiring-Manager\n```\n- [ ] FENCED @hiring-manager\n```\n"
                 "- [ ] TECH-HM2 @hiring-managers\n")
        hm = P.tagged_md(block, "hiring-manager")
        self.assertIn("### Domain", hm)
        self.assertIn("continued @hiring-manager", hm, "an item's continuation lines go with it")
        self.assertIn("TECH-HM @Hiring-Manager", hm)
        for absent in ("DOM-UNTAGGED", "TECH-HR", "FENCED", "TECH-HM2"):
            self.assertNotIn(absent, hm)
        self.assertNotIn("### Tech & Data", P.tagged_md(block, "hr-screen").split("TECH-HR")[1])
        self.assertIsNone(P.tagged_md(block, "final"))

    def test_focus_view_collects_tagged_tasks_when_headings_are_themes(self):
        """Trial layout: `###` under `## To do` are themes, a task names its round with
        `@<label>`. The round page gathers them, one checkbox per notes.md line."""
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        folder = root / "jobs" / "applications" / "900-test-co"
        folder.mkdir(parents=True)
        (folder / "notes.md").write_text(
            "# Test Co\n\n## To do\n\n### Domain\n\n- [ ] GENERAL\n- [ ] HM-ONE @hiring-manager\n\n"
            "### Questions & Practicalities\n\n- [ ] HM-TWO @hiring-manager\n\n## My notes\n\nPlain.\n")
        (folder / "900-test-co-alex-rivera-interview-hiring-manager-2026-09-24.md").write_text(
            "# HM\n\n## To do\n\n→ [This round's tasks, in My notes](#notes--hiring-manager-2026-09-24)\n\n"
            "## Prep\n\n- **Q:** why?\n  **A:** because.\n")
        app = Application.objects.get(num=1)
        app.folder = "jobs/applications/900-test-co"
        app.save()
        with override_settings(DATA_ROOT=str(root)):
            hm = self.client.get(
                f"/applications/{app.num}/rounds/round-hiring-manager-2026-09-24/").content.decode()
            full = self.client.get(f"/applications/{app.num}/").content.decode()
        # No such subsection on My notes, so the round file's link goes to the focus page.
        self.assertIn(f'href="/applications/{app.num}/rounds/round-hiring-manager-2026-09-24/'
                      f'#notes--hiring-manager-2026-09-24"', full)
        self.assertIn('id="notes--hiring-manager-2026-09-24"', hm)
        self.assertIn("Questions &amp; Practicalities", hm)
        self.assertNotIn("GENERAL", hm)
        self.assertRegex(hm, r'data-task="1"[^>]*>\s*HM-ONE')
        self.assertRegex(hm, r'data-task="2"[^>]*>\s*HM-TWO')
        self.assertIn('<span class="task-tag">@hiring-manager</span>', hm,
                      "a round tag is shown as a badge")

    def test_focus_view_removes_a_private_section_from_the_page_source(self):
        """Removed, not hidden. A page open during a call can be visible to someone
        else, and a CSS-hidden section is still in the source, still findable with
        find-in-page, and still there if the stylesheet fails to load."""
        app = Application.objects.exclude(folder="").first()
        round_ = app.interview_files[0]
        secret = "DO-NOT-SAY-THIS-OUT-LOUD"
        body = (round_["body_md"]
                + f"\n\n## Private — not for the call\n\n{secret}\n")
        prefix = round_["anchor"]
        split = P.split_sections(body)
        blocks = [{**b, "anchor": f"{prefix}--{b['anchor']}",
                   "subsections": [{**s, "anchor": f"{prefix}--{s['anchor']}"}
                                   for s in b["subsections"]]}
                  for b in split["blocks"]]
        self.assertTrue(any(b["private"] for b in blocks),
                        "the planted section should be recognised as private")
        with mock.patch.object(Application, "interview_files",
                               new_callable=mock.PropertyMock) as files:
            files.return_value = [{**round_, "body_md": body,
                                   "preamble_md": split["preamble"],
                                   "blocks": blocks,
                                   "sections": P.section_index(blocks)}]
            html = self.client.get(
                f"/applications/{app.num}/rounds/{prefix}/").content.decode()
        self.assertNotIn(secret, html)
        # Absent from the index too — a pill pointing at a section that is not on the
        # page is its own bug, and it would also name the section in the nav.
        self.assertNotIn("not-for-the-call", html)
        # ...but the page says it dropped something, rather than silently shortening.
        self.assertIn("full round", html)

    def test_a_pill_can_open_the_block_its_target_sits_in(self):
        """Every pill names the block to open (`data-parent`) as well as the id to
        scroll to. A `###` target is inside a closed `<details>`, so without the parent
        the browser's own jump lands nowhere."""
        app = Application.objects.get(num=1)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        for round_ in app.interview_files:
            blocks = {b["anchor"] for b in round_["blocks"]}
            for sec in round_["sections"]:
                with self.subTest(anchor=sec["anchor"]):
                    self.assertIn(sec["parent"], blocks)
                    self.assertIn(f'data-parent="{sec["parent"]}"', html)

    def test_every_round_has_a_unique_anchor(self):
        for app in Application.objects.exclude(folder=""):
            rounds = app.interview_files
            if not rounds:
                continue
            with self.subTest(num=app.num):
                anchors = [r["anchor"] for r in rounds]
                self.assertEqual(len(anchors), len(set(anchors)), f"duplicate: {anchors}")
                for r in rounds:
                    self.assertTrue(r["anchor"].startswith("round-"))
                    self.assertNotIn(" ", r["anchor"])

    def test_anchor_collision_is_disambiguated(self):
        """Two rounds of the same stage on the same day would otherwise share an id, and
        an anchor that matches two elements jumps to the wrong one."""
        app = Application.objects.get(num=1)
        folder = app.folder_path
        clash = folder / "001-grafana-labs-alex-rivera-interview-hr-screen-2026-09-18-b.md"
        # Same stage and date as the existing round; the trailing -b keeps the filename
        # distinct while the derived anchor base collides.
        clash.write_text("# Second screen\n\nBody.\n")
        self.addCleanup(clash.unlink)

        anchors = [r["anchor"] for r in app.interview_files]  # a plain property, not cached
        self.assertEqual(len(anchors), len(set(anchors)), anchors)

    def test_round_index_appears_only_from_two_rounds_up(self):
        """A one-item index is noise."""
        app = Application.objects.get(num=1)
        self.assertEqual(len(app.interview_files), 1)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        self.assertNotIn("round-index", html)
        folder = app.folder_path
        second = folder / "001-grafana-labs-alex-rivera-interview-technical-2026-09-25.md"
        second.write_text("# Technical round\n\nBody.\n")
        self.addCleanup(second.unlink)

        html = self.client.get(f"/applications/{app.num}/").content.decode()
        self.assertIn("round-index", html)
        # Each index entry must point at an id that actually exists on the page.
        for r in Application.objects.get(num=1).interview_files:
            self.assertIn(f'href="#{r["anchor"]}"', html)
            self.assertIn(f'id="{r["anchor"]}"', html)

    # ---- the same index on My notes and Other files (`#72`) ----

    def test_section_label_drops_link_markup_and_the_authors_own_number(self):
        """Both found the moment the index stopped being interview-only. Interview rounds
        write plain headings; notes and study files written elsewhere do neither.

        A linked heading put the whole URL in the pill *and* in the anchor. A heading that
        numbers itself collided with the generated number and rendered as "4 4. ...".
        """
        self.assertEqual(
            P.section_label("[Multi-tenant](https://example.org/wiki/X) isolation"),
            "Multi-tenant isolation")
        self.assertEqual(P.section_label("4. Performance"), "Performance")
        self.assertEqual(P.section_label("2) Authorisation"), "Authorisation")
        # A plain heading is untouched, and a number that is not an enumerator stays.
        self.assertEqual(P.section_label("Outcome"), "Outcome")
        self.assertEqual(P.section_label("2026 in review"), "2026 in review")

    def test_sectioned_scopes_every_anchor_under_its_prefix(self):
        """The guarantee the whole page rests on. Two documents sharing a heading is
        ordinary — two files in one folder both carrying `## Notes` — and unprefixed they
        would mint the same id, sending every link to whichever rendered first.
        """
        body = "## Notes\n\ntext\n\n### Detail\n\ntext\n"
        a = P.sectioned(body, "file-one")
        b = P.sectioned(body, "file-two")
        self.assertEqual([s["anchor"] for s in a["sections"]],
                         ["file-one--notes", "file-one--detail"])
        self.assertFalse(set(s["anchor"] for s in a["sections"]) &
                         set(s["anchor"] for s in b["sections"]))

    def test_every_id_on_an_application_page_is_unique(self):
        """Across the whole page, not within one document. The notes tab, each extra file
        and every interview round now mint section ids into the same page, so this is the
        check that the prefixes actually hold — a duplicate id is silent in HTML and sends
        the pill to the wrong section.
        """
        for app in Application.objects.exclude(folder=""):
            html = self.client.get(f"/applications/{app.num}/").content.decode()
            ids = re.findall(r'id="([^"]+)"', html)
            dupes = {i for i in ids if ids.count(i) > 1}
            with self.subTest(num=app.num):
                self.assertEqual(dupes, set(), f"duplicate ids: {sorted(dupes)}")

    def test_my_notes_renders_through_the_shared_index(self):
        app = next((a for a in Application.objects.exclude(folder="")
                    if a.notes_doc and len(a.notes_doc["sections"]) > 1), None)
        self.assertIsNotNone(app, "no example application has a sectioned notes.md")
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        for s in app.notes_doc["sections"]:
            self.assertTrue(s["anchor"].startswith("notes--"), s["anchor"])
            self.assertIn(f'id="{s["anchor"]}"', html)

    def test_glossary_terms_link_to_their_entries(self):
        from tracker.parsers import sectioned
        doc = sectioned(
            "# Co\n\n## Products\n\nUses ***claims*** and ***EHR*** data, picks sites by "
            "***feasibility***, and has ***nothing defined***. Plain **bold** and *italic*.\n\n"
            "## Glossary\n\n- **EHR (Electronic Health Record).** The clinical record.\n"
            "- **Claims data.** Billing records.\n"
            "- **Site.** A clinic. **Site selection / feasibility** means choosing sites.\n",
            "co")
        body = doc["blocks"][0]["body_md"]
        gloss = doc["blocks"][1]["body_md"]
        self.assertIn('<a class="gloss" href="#co--gloss-claims-data"', body)
        self.assertIn('href="#co--gloss-ehr-electronic-health-record" data-def="The clinical record.">EHR</a>', body)
        self.assertIn('href="#co--gloss-site" data-def="A clinic. Site selection / feasibility '
                      'means choosing sites.">feasibility</a>', body)
        self.assertIn('data-def="Billing records."', body)
        self.assertIn("***nothing defined***", body)      # unmatched: left alone
        self.assertIn("**bold** and *italic*", body)     # ordinary emphasis untouched
        for anchor in ("co--gloss-claims-data", "co--gloss-site"):
            self.assertIn(f'id="{anchor}"', gloss)

    def test_a_glossary_entrys_reference_link_stays_out_of_the_tooltip(self):
        """`#83`: an entry ends on a link out (`[Wikipedia](…)`). It renders in the
        glossary, but in a tooltip it would read as the last word of the definition."""
        from tracker.parsers import glossary_of, sectioned
        doc_md = (
            "# Co\n\n## Products\n\nRuns ***attestations*** and ***KYC***.\n\n## Glossary\n\n"
            "- **Attestation.** A signed confirmation. [Wikipedia](https://en.wikipedia.org/wiki/Attestation)\n"
            "- **KYC.** Checks on [customers](https://example.org/c) before onboarding. "
            "[FCA](https://www.fca.org.uk/)\n"
            "- **Default.** Failing to pay. [Wikipedia](https://en.wikipedia.org/wiki/Default_(finance))\n")
        doc = sectioned(doc_md, "co")
        body, gloss = doc["blocks"][0]["body_md"], doc["blocks"][1]["body_md"]
        self.assertIn('data-def="A signed confirmation."', body)
        self.assertIn('data-def="Checks on customers before onboarding."', body)
        self.assertIn("[Wikipedia](https://en.wikipedia.org/wiki/Attestation)", gloss)
        self.assertEqual(glossary_of(doc_md, "co", "")[2]["definition"], "Failing to pay.")

    def test_a_document_falls_back_to_a_supplied_glossary(self):
        from tracker.parsers import glossary_of, sectioned
        company = glossary_of("## Glossary\n\n- **SEC (Securities and Exchange Commission).** "
                              "The US regulator.\n", "company", "/companies/acme/")
        doc = sectioned("## Prep\n\nThe ***SEC*** runs exams.\n", "notes", company)
        self.assertIn('<a class="gloss" href="/companies/acme/#company--gloss-sec-securities-'
                      'and-exchange-commission" data-def="The US regulator.">SEC</a>',
                      doc["blocks"][0]["body_md"])

    def test_a_documents_own_glossary_beats_the_supplied_one(self):
        from tracker.parsers import glossary_of, sectioned
        company = glossary_of("## Glossary\n\n- **Panel.** Company meaning.\n",
                              "company", "/companies/acme/")
        doc = sectioned("## A\n\nA ***panel***.\n\n## Glossary\n\n- **Panel.** Local meaning.\n",
                        "n", company)
        self.assertIn('href="#n--gloss-panel" data-def="Local meaning."', doc["blocks"][0]["body_md"])

    def test_a_long_paragraph_never_splits_inside_a_glossary_link(self):
        """A one-line paragraph over 500 characters is broken at sentence boundaries, and
        glossary links are already rendered by then. A definition of two sentences used to
        be split inside its data-def attribute, printing half the tag on the page."""
        from tracker.templatetags.jobs_extras import _paragraphize, markdownify
        link = ('<a class="gloss" href="#c--gloss-rating" data-def="An opinion of credit '
                'risk. Applies to an issuer or a bond.">rating</a>')
        text = f"Grafana Labs sells software. It has a {link} too. Customers pay for it."
        # target=1 breaks at every sentence boundary, so a boundary inside the tag would.
        out = _paragraphize(text, target=1, minimum=0)
        self.assertIn(link, out)
        self.assertEqual(out.count("\n\n"), 2)
        self.assertNotIn("&lt;a", markdownify(("Grafana Labs sells software. " * 20) + text))

    def test_a_mermaid_fence_reaches_the_page_as_diagram_source(self):
        """diagrams.js draws `pre > code.language-mermaid`, so the markdown filter has to
        hand the fence over untouched — no autolinking, no <br /> from nl2br."""
        from tracker.templatetags.jobs_extras import markdownify
        html = markdownify("```mermaid\nflowchart LR\n  A[\"x<br/>y\"] --> B\n```\n")
        self.assertIn('<code class="language-mermaid">flowchart LR\n', html)
        self.assertIn("A[&quot;x&lt;br/&gt;y&quot;] --&gt; B", html)
        page = self.client.get("/").content.decode()
        self.assertIn('js/diagrams.js" data-mermaid="', page)

    def test_a_reference_to_a_markdown_file_links_to_its_page(self):
        """#78: a path in prose, in backticks or not, links to the page that renders the
        file; a path with no page stays text rather than becoming a dead link."""
        from tracker.templatetags.jobs_extras import markdownify
        a = "001-grafana-labs-alex-rivera"
        cases = {
            "`jobs/notes/search/ideal-job-notes.md`": '<a href="/notes/ideal-job-notes/"><code>',
            "`ideal-job-notes.md`": '<a href="/notes/ideal-job-notes/"><code>',
            "see <DATA>/jobs/companies/grafana-labs.md now": 'href="/companies/grafana-labs/"',
            "`stocktake.md` §7": '<a href="/profile/"><code>stocktake.md</code></a>',
            "jobs/cv/base/cv_functional.md": 'href="/cvs/base/cv_functional/"',
            "`jobs/applications/001-grafana-labs/notes.md`": 'href="/applications/1/#notes"',
            f"`{a}-interview-hr-screen-2026-09-18.md`":
                'href="/applications/1/#round-hr-screen-2026-09-18"',
            f"`{a}-cv-developer-advocacy-2026-09-15.md`":
                'href="/applications/1/#cv-developer-advocacy-2026-09-15"',
            f"`{a}-study-plugin-architecture-2026-09-19.md`":
                f'href="/applications/1/#file-{a}-study-plugin-architecture-2026-09-19-md"',
            "[the note](jobs/notes/search/ideal-job-notes.md)": '<a href="/notes/ideal-job-notes/">the note',
        }
        for md, expected in cases.items():
            with self.subTest(md=md):
                self.assertIn(expected, markdownify(md))
        for md in ("`jobs/notes/no-such-note.md`", "`notes.md`", "README.md",
                   "`jobs/notes/ideal-job-notes.md`",  # wrong folder: not where the file is
                   "```\njobs/notes/ideal-job-notes.md\n```",
                   "https://example.com/jobs/notes/ideal-job-notes.md"):
            with self.subTest(md=md):
                self.assertNotIn('href="/notes/', markdownify(md))

    def test_a_linked_file_reference_lands_on_an_anchor_the_page_has(self):
        html = self.client.get("/applications/1/").content.decode()
        for anchor in ("round-hr-screen-2026-09-18", "cv-developer-advocacy-2026-09-15",
                       "file-001-grafana-labs-alex-rivera-study-plugin-architecture-2026-09-19-md"):
            with self.subTest(anchor=anchor):
                self.assertIn(f'id="{anchor}"', html)

    def test_task_markers_render_as_checkboxes_and_write_back(self):
        from tracker.parsers import render_tasks, set_task, task_spans
        text = ("## Study before\n\n- [ ] Watch the video\n- [x] Read the paper\n"
                "```\n- [ ] not a task, in a fence\n```\n1. [ ] Numbered task\n")
        self.assertEqual([c for _, _, c in task_spans(text)], [False, True, False])
        live = render_tasks(text, "jobs/x.md")
        self.assertIn('<input type="checkbox" class="task-box" data-task="0" '
                      'data-source="jobs/x.md"> Watch', live)
        self.assertIn('data-task="1" data-source="jobs/x.md" checked> Read', live)
        self.assertIn("- [ ] not a task, in a fence", live)
        self.assertIn('data-task="2"', live)
        self.assertIn(" disabled", render_tasks(text, None))          # published: read-only
        ticked = set_task(text, 2, True)
        self.assertIn("1. [x] Numbered task", ticked)
        self.assertIn("- [ ] not a task, in a fence", ticked)       # the fence is untouched
        self.assertIn("- [ ] Read the paper", set_task(text, 1, False))
        with self.assertRaises(IndexError):
            set_task(text, 3, True)

    def test_the_to_do_section_in_application_notes_is_checkboxes(self):
        """An application's tasks are `- [ ]` lists in notes.md's `## To do` (SKILL.md,
        "Lists of things to do are checklists"; `#84`, which replaced the gap analysis's
        `### Preparation steps`), so they reach the page as checkboxes — and the section
        comes first, so the first box on the page is the file's first task."""
        app = Application.objects.get(num=1)
        self.assertEqual(app.notes_doc["blocks"][0]["anchor"], "notes--to-do")
        html = self.client.get("/applications/1/").content.decode()
        todo = html[html.index('data-section="notes--to-do"'):]
        self.assertIn('class="task-box" data-task="0"', todo)
        self.assertIn('data-task="1"', todo)
        self.assertIn('<span class="task-tag">@hr-screen</span>', todo,
                      "a task's round tag is drawn as a pill (#91)")
        # The round file's link has no subsection to land on in My notes, so it goes to
        # the round's page, where the tagged tasks are gathered.
        self.assertIn('href="/applications/1/rounds/round-hr-screen-2026-09-18/'
                      '#notes--hr-screen-2026-09-18"', html)

    def test_toggle_task_endpoint_edits_the_file_and_refuses_outside_the_data_root(self):
        import tempfile
        from pathlib import Path
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as root:
            f = Path(root) / "jobs" / "r.md"
            f.parent.mkdir()
            f.write_text("- [ ] one\n- [ ] two\n")
            with override_settings(DATA_ROOT=root, ENVIRONMENT="local"):
                r = self.client.post("/actions/task/", {"source": "jobs/r.md", "index": "1",
                                                        "checked": "true"})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(f.read_text(), "- [ ] one\n- [x] two\n")
                r = self.client.post("/actions/task/", {"source": "../etc/passwd.md",
                                                        "index": "0", "checked": "true"})
                self.assertEqual(r.status_code, 404)
                r = self.client.post("/actions/task/", {"source": "jobs/r.md", "index": "9",
                                                        "checked": "true"})
                self.assertEqual(r.status_code, 409)
            with override_settings(DATA_ROOT=root, ENVIRONMENT="publish"):
                r = self.client.post("/actions/task/", {"source": "jobs/r.md", "index": "0",
                                                        "checked": "true"})
                self.assertEqual(r.status_code, 404)

    def test_a_document_without_a_glossary_is_unchanged(self):
        from tracker.parsers import sectioned
        doc = sectioned("## A\n\nSome ***term*** here.\n", "x")
        self.assertIn("***term***", doc["blocks"][0]["body_md"])

    def test_every_application_page_links_out_to_its_company(self):
        for app in Application.objects.all():
            html = self.client.get(f"/applications/{app.num}/").content.decode()
            with self.subTest(num=app.num):
                self.assertIn('class="company-cta"', html)
                if app.company_id:
                    self.assertIn(f'href="/companies/{app.company.slug}/">Open the', html)
                else:
                    self.assertIn("link-company", html)

    def test_company_research_renders_through_the_shared_index(self):
        co = next((c for c in Company.objects.all()
                   if c.notes_doc and len(c.notes_doc["sections"]) > 1), None)
        self.assertIsNotNone(co, "no example company has a sectioned research file")
        html = self.client.get(f"/companies/{co.slug}/").content.decode()
        self.assertIn("data-section-index", html)
        for s in co.notes_doc["sections"]:
            self.assertTrue(s["anchor"].startswith("company--"), s["anchor"])
            self.assertIn(f'id="{s["anchor"]}"', html)

    def test_my_notes_opens_expanded_and_other_files_collapsed(self):
        """A judgement per tab, not a global default, and the reason is in each include:
        notes.md is one document read with no clock running, while Other files stacks
        whole files and is the Interviews tab's problem instead.
        """
        app = next((a for a in Application.objects.exclude(folder="")
                    if a.notes_doc and len(a.notes_doc["sections"]) > 1), None)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        for s in app.notes_doc["sections"]:
            if s["level"] != 2:
                continue
            m = re.search(r'<details class="doc-section" data-section="%s"([^>]*)>'
                          % re.escape(s["anchor"]), html)
            self.assertIsNotNone(m, s["anchor"])
            self.assertIn("open", m.group(1))
        for app in Application.objects.exclude(folder=""):
            for f in app.extra_files:
                for s in (f.get("doc") or {}).get("sections", []):
                    m = re.search(r'<details class="doc-section" data-section="%s"([^>]*)>'
                                  % re.escape(s["anchor"]), html or "")
                    if m:
                        self.assertNotIn("open", m.group(1))

    def test_mark_qa_marks_questions_everywhere_but_headings_strictly_outside_rounds(self):
        """`**Q:**` is marked in every document since 2026-10-15 — the answer bank, study
        files and topic notes use it too, and the contents lists questions wherever they
        are. What differs outside a round is the heading rule: a note's headings are
        topics, so only one that opens with a quote or ends with "?" is a question."""
        from tracker.templatetags.jobs_extras import mark_qa
        text = "- **Q:** what is it?"
        self.assertIn("qa-q", mark_qa(text, True))
        self.assertIn("qa-q", mark_qa(text, False))
        topic = '### Why the "AI-ready" label matters'
        self.assertIn("qa-q", mark_qa(topic, True))
        self.assertNotIn("qa-q", mark_qa(topic, False))
        for asked in ['### "Tell me about yourself" — the 45-second version',
                      "### When is a graph the wrong answer?"]:
            with self.subTest(heading=asked):
                self.assertIn("qa-q", mark_qa(asked, False))

    def test_questions_are_numbered_under_their_heading_and_listed(self):
        """Each `**Q:**` is numbered under the heading it sits beneath — 1.1.1, 1.1.2 — with
        an anchor extending the heading's, and appears in the contents under it. One
        before the first `###` takes `n.0.k`, so it can't be read as the `n.1` below it."""
        src = (
            "# Round\n\n## Prep\n\n- **Q:** Before any subsection?\n  **A:** Yes.\n\n"
            "### Role / technical\n\n- **Q:** First question,\n  wrapped over two lines?\n"
            "  **A:** One.\n\n- **Q:** Second?\n  **A:** Two.\n\n"
            "### Why this role\n\n**Q:** A bare one?\n**A:** Three.\n"
        )
        doc = P.sectioned(src, "r")
        qs = doc["blocks"][0]["questions"]
        self.assertEqual([q["number"] for q in qs], ["1.0.1", "1.1.1", "1.1.2", "1.2.1"])
        self.assertEqual(qs[1]["label"], "First question, wrapped over two lines?")
        self.assertEqual(qs[1]["anchor"], "r--role-technical--q1")
        index = [(s["level"], s["number"]) for s in doc["sections"]]
        self.assertEqual(index, [(2, "1"), (4, "1.0.1"), (3, "1.1"), (4, "1.1.1"),
                                 (4, "1.1.2"), (3, "1.2"), (4, "1.2.1")])

    def test_each_question_folds_with_its_answer(self):
        """`qa_items` turns every question into a `<details>` that opens and closes, the
        question as its summary and the whole answer inside — including an answer's own
        bullets, which must stay bullets inside it rather than escape the block."""
        from tracker.templatetags.jobs_extras import mark_qa, markdownify, number_sections, qa_items
        src = (
            "# Round\n\n## Prep\n\n### Role / technical\n\n"
            "- **Q:** A bulleted question?\n  **A:**\n\n    **Phase one.**\n"
            "    - first step\n    - second step\n\n"
            "- **Q:** Another?\n  **A:** Short.\n\n"
            "### Why this role\n\n**Q:** A bare one?\n**A:** Its answer.\n\nMore of it.\n\n"
            '### "Tell me about yourself"\n\nThe heading is the question.\n'
        )
        doc = P.sectioned(src, "r")
        block = doc["blocks"][0]
        html = str(qa_items(number_sections(markdownify(mark_qa(block["body_md"], False)), block),
                            block))
        self.assertEqual(html.count('<details class="qa" id='), 3)
        self.assertIn('<details class="qa" id="r--role-technical--q1" open>', html)
        self.assertIn('data-n="1.1.1"', html)
        self.assertIn('data-n="1.2.1"', html)
        # The answer's bullets are inside the first question's block, before the second.
        first = html[html.index('id="r--role-technical--q1"'):html.index('id="r--role-technical--q2"')]
        self.assertIn("<li>second step</li>", first)
        # A bare-paragraph answer runs on to the next heading, and no further.
        bare = html[html.index('id="r--why-this-role--q1"'):]
        self.assertLess(bare.index("More of it."), bare.index("Tell me about yourself"))
        # The heading that asks folds too, keeping its own number and id.
        self.assertIn('<details class="qa qa-h" open><summary class="qa-sum"><h3', html)
        self.assertEqual(html.count("<details"), html.count("</details>"))

    def test_extra_files_carry_unique_anchors_rendered_as_ids(self):
        """Prose in a folder needs a target for a specific file. Without an id the only
        honest link is the tab, and a bare `<name>.md` link is broken on the published
        site — these render into the page, they are not shipped as files."""
        app = Application.objects.get(num=1)
        files = app.extra_files
        self.assertTrue(files, "fixture app #1 needs a file under Other files")
        anchors = [f["anchor"] for f in files]
        self.assertEqual(len(anchors), len(set(anchors)), f"duplicate anchors: {anchors}")

        html = self.client.get(f"/applications/{app.num}/").content.decode()
        for f in files:
            with self.subTest(rel=f["rel"]):
                self.assertTrue(f["anchor"].startswith("file-"))
                self.assertIn(f'id="{f["anchor"]}"', html)

    def test_other_files_index_appears_from_two_files_up_and_links_each_one(self):
        """`#87`: the Interviews and CV tabs' index, on Other files — a list of one is
        noise, and from two up every file, markdown or not, gets a line linking its id."""
        from django.test import override_settings

        root = Path(tempfile.mkdtemp())
        folder = root / "jobs" / "applications" / "900-test-co"
        folder.mkdir(parents=True)
        (folder / "900-test-co-alex-rivera-study-sql-2026-10-08.md").write_text("# SQL\n\nJoins.\n")

        app = Application.objects.get(num=1)
        app.folder = "jobs/applications/900-test-co"
        app.save()
        label = 'aria-label="Files in this folder"'
        with override_settings(DATA_ROOT=str(root)):
            one = self.client.get(f"/applications/{app.num}/").content.decode()
            self.assertNotIn(label, one)

            (folder / "salary-benchmarks.xlsx").write_bytes(b"x" * 2048)
            html = self.client.get(f"/applications/{app.num}/").content.decode()
            self.assertIn(label, html)
            index = html[html.index(label):html.index("</nav>", html.index(label))]
            for f in app.extra_files:
                with self.subTest(rel=f["rel"]):
                    self.assertIn(f'href="#{f["anchor"]}"', index)
            self.assertIn("2 KB", index, "a non-markdown file shows its size")

    def test_no_folder_markdown_links_a_bare_md_file(self):
        """Regression, twice over. A relative `.md` link inside an application folder
        resolves to nothing in the web view and fails build_static's link checker — the
        file is rendered into a tab, not published. Link the anchor instead.

        Note this only covers the example data the suite runs against; the real guard for
        a user's own data root is running build_static before publishing.
        """
        bad_link = re.compile(r"\]\((?!https?://|#|mailto:)([^)]*\.md)\)")
        for app in Application.objects.exclude(folder=""):
            for md in sorted(app.folder_path.rglob("*.md")):
                with self.subTest(file=md.name):
                    hits = bad_link.findall(md.read_text())
                    self.assertFalse(hits, f"{md.name} links bare markdown: {hits}")

    def test_tabs_js_resolves_an_in_panel_anchor(self):
        """A hash naming a round (not a tab) must open the panel holding it — otherwise a
        shared link to one round reloads onto the first tab with its target hidden."""
        js = (Path(settings.SITE_ROOT) / "src/web/static/js/tabs.js").read_text()
        self.assertIn("activateContaining", js)
        self.assertIn('closest("[data-panel]")', js)

    def test_tab_is_omitted_when_there_are_no_rounds(self):
        app = Application.objects.get(num=2)
        self.assertFalse(app.interview_files)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        self.assertNotIn('data-tab="interviews"', html)

    def test_notes_stub_no_longer_scaffolds_an_interview_heading(self):
        """Retired 2026-09-24 — an empty heading in every folder is what invited packing
        rounds into notes.md in the first place."""
        import appfolder

        stub = appfolder.notes_stub({"company": "Test Co", "role": "Architect"})
        self.assertNotIn("## Interview prep", stub)
        for heading in ("## To do", "## My notes", "## Contacts", "## Timeline"):
            self.assertIn(heading, stub)
        # `#91`: the to-do section explains itself, then the four themes in their order.
        self.assertIn(appfolder.TODO_GUIDE, stub)
        positions = [stub.index(f"### {t}\n") for t in appfolder.TODO_THEMES]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("### Application", stub)
        from tracker.parsers import _TASK_TAG
        self.assertIsNone(_TASK_TAG.search(appfolder.TODO_GUIDE),
                          "no line of the guide may end in something drawn as a tag")

    def test_todo_guide_is_classed_as_a_how_to_note(self):
        """The guide is for whoever edits notes.md by hand: on the page it is styled
        apart from the tasks, and the paragraph after it is left alone."""
        import appfolder
        from tracker.templatetags.jobs_extras import markdownify

        doc = P.sectioned(f"## To do\n\n{appfolder.TODO_GUIDE}\n\nPlain para.\n", "notes")
        html = markdownify(doc["body_md"])
        self.assertIn('<p class="howto-note"><em>How this list works.</em>', html)
        self.assertIn("<p>Plain para.</p>", html)

    def test_answer_bank_intro_is_boxed_as_a_how_to_note(self):
        """`#95`: under a heading that asks, the plain paragraphs before the quoted answer
        are a note on using it, boxed like the to-do guide. A bold-led paragraph is the
        answer starting, and an entry with no quoted answer is left alone."""
        from tracker.templatetags.jobs_extras import markdownify, mark_qa, qa_items

        def render(body):
            doc = P.sectioned(f"## About me\n\n{body}", "n")
            block = doc["blocks"][0]
            return str(qa_items(markdownify(mark_qa(block["body_md"], False)), block))

        html = render('### "Tell me about yourself"\n\n*Tested: worked.*\n\nKeep it short.\n\n'
                      '> "I build data foundations."\n')
        self.assertRegex(html, r'<div class="howto-note">\s*<p><em>Tested: worked\.</em></p>')
        self.assertRegex(html, r'Keep it short\.(<br />)?</p>\s*</div>\s*<blockquote>')

        bold = render('### "What are the trends?"\n\n**Trend 1 — delivery.** More text.\n\n'
                      '> "The question changed."\n')
        self.assertNotIn("howto-note", bold)

        unquoted = render('### "Why this role?"\n\nA plain answer, no quote.\n')
        self.assertNotIn("howto-note", unquoted)

    def test_filename_is_built_from_the_shared_convention(self):
        """app_filename() stays the single implementation — and the date is the date of
        the interview, not the day the file was written."""
        import appfolder
        from datetime import date

        name = appfolder.app_filename(Path("001-grafana-labs"), "interview-hiring-manager",
                                      "md", when=date(2026, 9, 24))
        self.assertTrue(name.startswith("001-grafana-labs-"))
        self.assertTrue(name.endswith("-interview-hiring-manager-2026-09-24.md"))
        self.assertTrue(appfolder.is_interview_filename(name))
        self.assertEqual(appfolder.interview_stage(name), "hiring-manager")

    def test_questions_are_marked_up_for_colouring(self):
        """`mark_qa` wraps each `**Q:** …` in a span so the Interviews tab can colour the
        questions. Both source forms matter — a bullet (`- **Q:**`) and a bare paragraph —
        and a question hard-wrapped over two lines must stay inside ONE span, or the colour
        stops mid-sentence and reads as a rendering bug."""
        from apps.tracker.templatetags.jobs_extras import mark_qa, markdownify

        src = (
            "### Role / technical\n\n"
            "- **Q:** A bulleted question?\n"
            "  **A:** Its answer, which is not coloured.\n\n"
            "### Why this role\n\n"
            "**Q:** A bare question that wraps over\n"
            "two source lines, ending here.\n"
            "**A:** And its answer.\n"
        )
        marked = mark_qa(src)
        self.assertEqual(marked.count('<span class="qa-q">'), 2)
        self.assertEqual(marked.count("</span>"), 2)
        # The wrapped question's continuation is inside the span, the answer is outside.
        self.assertIn("ending here.</span>", marked)
        self.assertNotIn('<span class="qa-q">**A:**', marked)
        # The marker stays markdown, so it still renders bold inside the span.
        html = markdownify(marked)
        self.assertIn('<span class="qa-q"><strong>Q:</strong>', html)
        self.assertNotIn('<span class="qa-q"><strong>A:</strong>', html)

    def test_question_headings_are_marked_up_too(self):
        """Rounds written before the `**Q:**` convention (2026-09-24) put the question in the
        heading. Those are still questions, so a heading that asks something or quotes what
        was asked is coloured too — while a heading naming a topic stays plain."""
        from apps.tracker.templatetags.jobs_extras import mark_qa, markdownify

        coloured = [
            "#### Why do you want to leave / why Grafana Labs?",
            '### A0. "Why are you applying for a role below your last level?" — the one to nail',
            '### A1. "Walk me through a data platform you architected end to end."',
        ]
        plain = [
            "### A2. AWS — say it first, unprompted",
            "## Questions to ask them",
            "### Why this role",
            "## Outcome",
        ]
        for line in coloured:
            with self.subTest(line=line):
                self.assertIn('<span class="qa-q">', mark_qa(line))
        for line in plain:
            with self.subTest(line=line):
                self.assertNotIn("qa-q", mark_qa(line))

        # The hashes must stay at the line start, or it stops being a heading.
        html = markdownify(mark_qa("#### Why do you want to leave?"))
        self.assertIn('<h4><span class="qa-q">Why do you want to leave?</span></h4>', html)

    def test_interviews_panel_colours_the_questions(self):
        """The filter is wired into the Interviews panel, and only there — `**Q:**` is the
        round file's convention, not the whole site's."""
        app = Application.objects.get(num="1")
        r = self.client.get(f"/applications/{app.num}/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('class="qa-q"', r.content.decode())


class CreateFolderActionTests(TestCase):
    """The application page's "Create folder" action (added 2026-09-09, for applications
    logged without one) — appfolder.ensure_folder() run through the view. Writes to the
    real jobs/applications/ tree, so clean up after."""

    fixtures = FIXTURE

    def setUp(self):
        self.app = Application.objects.create(
            num=9201, company_name="Create Folder Test Co", role="Test", status="saved")
        self.addCleanup(self._cleanup_folder)

    def _cleanup_folder(self):
        self.app.refresh_from_db()
        if self.app.folder:
            folder = Path(settings.DATA_ROOT) / self.app.folder
            if folder.is_dir():
                shutil.rmtree(folder)

    def test_creates_folder_with_a_cv_copy_and_an_empty_cover_letter(self):
        with self.settings(ENVIRONMENT="local"):
            resp = self.client.get(f"/actions/create-folder/{self.app.num}/")
        self.assertEqual(resp.status_code, 302)

        self.app.refresh_from_db()
        self.assertTrue(self.app.folder)
        folder = Path(settings.DATA_ROOT) / self.app.folder
        self.assertTrue((folder / "notes.md").is_file())
        # Named for the application even though nothing has been tailored (#55) — the
        # bare cv_functional.md copy was retired on 2026-10-01.
        cvs = [p.name for p in folder.glob("*-cv-functional-*.md")]
        self.assertEqual(len(cvs), 1, f"expected one CV copy, got {sorted(folder.iterdir())}")
        self.assertFalse((folder / "cv_functional.md").exists())

        cover_letters = list(folder.glob("*cover-letter*.md"))
        self.assertEqual(len(cover_letters), 1)
        self.assertEqual(cover_letters[0].stat().st_size, 0,
                         "cover-letter stub should be empty — content is a follow-up step")

    def test_local_only(self):
        with self.settings(ENVIRONMENT="publish"):
            resp = self.client.get(f"/actions/create-folder/{self.app.num}/")
        self.assertEqual(resp.status_code, 404)
        self.app.refresh_from_db()
        self.assertEqual(self.app.folder, "")


class ScanConfigTests(TestCase):
    """`<DATA>/jobs/scan-config.yaml` — the company-specific half of scanning.

    These four settings were module constants in `scan-portals.py` until 2026-09-21,
    which meant one person's target list was sitting in shared code and the toolkit
    could not be published without it. The tests that matter here are the two that
    would let it creep back: that the code reads the data root rather than a literal,
    and that a data root with no such file still works.
    """

    def _scan_config(self):
        import importlib
        import scan_config                  # settings.py already put src/ on sys.path
        importlib.reload(scan_config)       # drop the module-level cache between tests
        return scan_config

    def test_reads_the_example_data_root(self):
        sc = self._scan_config()
        self.assertTrue(sc.path().is_file(), f"{sc.path()} should ship with example-data")
        self.assertTrue(sc.company_overrides(), "example config should carry some overrides")
        self.assertIn(sc.default_area(), {a.stem for a in Path(settings.TARGETS_DIR).glob("*.yaml")},
                      "default_area must name a real target area")

    def _criteria_root(self, criteria):
        """A throwaway data root whose criteria.yaml is exactly `criteria`."""
        import tempfile

        import yaml as _yaml

        root = Path(tempfile.mkdtemp())
        (root / "jobs" / "profile").mkdir(parents=True)
        (root / "jobs" / "targets").mkdir(parents=True)
        if criteria is not None:
            (root / "jobs" / "profile" / "criteria.yaml").write_text(_yaml.safe_dump(criteria))
        return root

    def test_the_ideal_job_score_knows_when_it_has_nothing_to_score_against(self):
        """`#62`. On a fresh data root `criteria.yaml` is a draft with no motivators, so
        every Ideal-Job Score comes back low whatever the role — the empty profile
        talking, not the postings. The number renders beside the Area Score in the same
        column shape, so it has to be able to say it is not ready."""
        import config

        sc = self._scan_config()
        orig = config.data_root
        try:
            for label, criteria, ready in [
                ("no file at all", None, False),
                ("file with nothing in it", {}, False),
                ("dealbreakers but no motivators",
                 {"hard_filters": {"exclude": ["pure people-management"]}}, False),
                ("motivators present",
                 {"weighted_motivators": [{"name": "hands-on", "weight": 5}]}, True),
            ]:
                with self.subTest(case=label):
                    root = self._criteria_root(criteria)
                    config.data_root = lambda root=root: root
                    self.assertEqual(sc.ideal_score_inputs()["ready"], ready)
        finally:
            config.data_root = orig

    def test_dealbreakers_alone_do_not_make_the_score_ready(self):
        """Dealbreakers can only push a score down; they never establish that a role is
        wanted. So a profile carrying only those is still not something to rank on, and
        `check` says which part is missing rather than only that something is."""
        import config

        sc = self._scan_config()
        orig = config.data_root
        try:
            root = self._criteria_root({"hard_filters": {"exclude": ["backstage pipeline work"]}})
            config.data_root = lambda: root
            inputs = sc.ideal_score_inputs()
            self.assertEqual(inputs["dealbreakers"], 1)
            self.assertEqual(inputs["motivators"], 0)
            self.assertFalse(inputs["ready"])
            messages = [m for _, m in sc.check(targets=root / "jobs" / "targets",
                                               tracked_categories=[], tracked_companies=[])]
            self.assertTrue(any("weighted_motivators" in m for m in messages), messages)
        finally:
            config.data_root = orig

    def test_the_report_warns_at_the_top_when_the_ideal_score_is_not_ready(self):
        """`#62`. The banner is the whole fix, so it has to appear before the tables and
        say the two things a reader cannot work out from the column: that the number is
        about the empty profile rather than the role, and that the Strong-matches cut is
        on the combined score, so the bar has moved too."""
        import importlib
        import config
        import scan_report

        orig = config.data_root
        try:
            root = self._criteria_root({"weighted_motivators": []})
            (root / "jobs" / "scans").mkdir(parents=True)
            config.data_root = lambda: root
            importlib.reload(scan_report)

            c = scan_report.Candidate(
                company="Acme", title="Developer Advocate", url="https://example.com/1",
                role_target="Developer Advocate", area="developer-advocacy",
                category="Developer tools", location="London, UK")
            c.cv_score, c.ideal_score, c.location_category, c.notes = 5, 2, "uk", "Note."
            out = scan_report.write_report(
                scanned_count=1, not_scanned=[], matches=[c], discarded_by_location=[],
                needs_review=[], no_roles=[], total_found=1, total_skipped_dedup=0,
                coverage_notes=[], prefiltered={}, location_prefiltered={})
            text = out.read_text()

            self.assertIn("not yet meaningful", text)
            self.assertIn("stocktake", text)
            self.assertIn("combined", text, "the ranking consequence must be stated")
            self.assertLess(text.index("not yet meaningful"), text.index("## Strong matches"),
                            "the warning has to come before the tables, not after")
        finally:
            config.data_root = orig
            importlib.reload(scan_report)

    def test_the_example_profile_is_ready_so_no_banner_is_shown(self):
        """The shipped example must not carry the warning — a newcomer meeting it would
        reasonably read the example as broken (`#64`'s lesson, one file over)."""
        sc = self._scan_config()
        self.assertTrue(sc.ideal_score_inputs()["ready"],
                        "example-data's criteria.yaml should have weighted_motivators")

    def test_every_mapped_area_exists(self):
        """A category pointing at a missing target area scores against nothing."""
        sc = self._scan_config()
        areas = {a.stem for a in Path(settings.TARGETS_DIR).glob("*.yaml")}
        for category, area in sc.category_to_area().items():
            self.assertIn(area, areas, f"category {category!r} maps to unknown area {area!r}")

    def test_missing_file_is_not_an_error(self):
        """A brand-new data root has no scan-config.yaml. Scanning must still run —
        URL detection alone — rather than crashing on a file nobody has written yet."""
        sc = self._scan_config()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "jobs").mkdir()
            with self.settings(DATA_ROOT=tmp):
                import config
                orig, config.data_root = config.data_root, lambda: Path(tmp)
                try:
                    sc._cache = None
                    self.assertEqual(sc.company_overrides(), {})
                    self.assertEqual(sc.known_unsupported(), {})
                    self.assertEqual(sc.category_to_area(), {})
                    self.assertEqual(sc.default_area(), "")
                finally:
                    config.data_root = orig
                    sc._cache = None

    def _scan_portals(self):
        """`scan-portals.py` cannot be imported normally — the hyphen in the filename."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "scan_portals_under_test", Path(settings.SITE_ROOT) / "src" / "scan-portals.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_a_posting_with_no_title_or_no_link_is_skipped_and_counted(self):
        """`#63` generalised to every fetcher. A posting needs a title and a link to be
        worth anything, and a row that has neither must cost that row rather than the
        whole company — counted, not silently dropped (`#44`)."""
        sp = self._scan_portals()
        out = sp._Postings("test/board")

        out.add("Data Scientist", "https://example.com/1", "London")
        out.add(None, "https://example.com/2", "London")          # the `#63` row
        out.add("No link here", None, "London")                   # the quieter hazard
        out.add("", "https://example.com/4")                      # empty, not missing
        out.add("Blank link", "")

        self.assertEqual([j["title"] for j in out.jobs], ["Data Scientist"])
        self.assertEqual(out.unusable, 4)
        jobs, truncated = out.done(total=5)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(truncated, 5, "the board's own total survives the skipping")

    def test_every_surviving_posting_has_the_three_fields_the_scan_relies_on(self):
        """The caller does `_normalize(j["url"])` and the report renders a title and a
        location, so a row that reaches either without them crashes the scan downstream
        rather than at the fetcher. Location is the one that may legitimately be absent."""
        sp = self._scan_portals()
        out = sp._Postings("test/board")
        out.add("  Padded Title  ", "https://example.com/1")
        out.add("Located", "https://example.com/2", "Bristol, UK")
        jobs, _ = out.done()
        self.assertEqual([j["title"] for j in jobs], ["Padded Title", "Located"])
        self.assertEqual([j["location"] for j in jobs], ["unknown", "Bristol, UK"])
        self.assertTrue(all(j["title"] and j["url"] and j["location"] for j in jobs))

    def test_no_fetcher_reads_a_posting_field_with_a_hard_subscript(self):
        """The regression guard for `#63`'s general form. Every branch funnels rows
        through `_Postings.add()` with `.get()`, so one malformed row cannot take a
        company's whole scan down. A new fetcher written the old way reintroduces it."""
        src = (Path(settings.SITE_ROOT) / "src" / "scan-portals.py").read_text()
        # Bounded to fetch_jobs itself. Past its last line the caller does
        # `_normalize(j["url"])`, which is fine: by then `_Postings.add` has guaranteed
        # every row has a url, which is the whole point of routing through it.
        body = src.split("def fetch_jobs(", 1)[1].split("unknown platform", 1)[0]
        offenders = re.findall(r'^\s*(?!#).*\b(?:j|it|e|item)\["[a-zA-Z_]+"\]', body, re.M)
        self.assertEqual([o.strip() for o in offenders], [],
                         "a fetcher reads a posting field with a hard subscript; route it "
                         "through _Postings.add() with .get() instead")

    def test_workday_skips_postings_with_no_title_instead_of_aborting(self):
        """A real Workday board returned one posting carrying only `bulletFields` among
        125. `j["title"]` raised KeyError, the generic handler turned it into "unexpected
        response shape", and the whole company came back NOT SCANNED — 124 usable
        postings lost to one unusable row. Found 2026-10-01 by the second-person install
        pass (`#2` M1.8)."""
        import importlib.util
        import httpx

        spec = importlib.util.spec_from_file_location(
            "scan_portals_under_test", Path(settings.SITE_ROOT) / "src" / "scan-portals.py")
        sp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sp)

        page = {"total": 3, "jobPostings": [
            {"title": "Data Scientist", "externalPath": "/job/1", "locationsText": "London"},
            {"bulletFields": ["JR123"]},                      # the row that used to crash
            {"title": "No path here", "locationsText": "Remote"},   # unusable too
        ]}

        class _Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return page

        class _Client:
            calls = 0
            def post(self, *a, **kw):
                _Client.calls += 1
                # Second page empty, so the paging loop terminates.
                if _Client.calls > 1:
                    page["jobPostings"] = []
                return _Resp()

        source = {"platform": "workday", "tenant": "acme", "wd": "wd3", "site": "AcmeJobs"}
        jobs, truncated = sp.fetch_jobs(source, "data scientist", _Client())

        self.assertEqual([j["title"] for j in jobs], ["Data Scientist"],
                         "the one usable posting must survive the two that are not")
        self.assertTrue(jobs[0]["url"].endswith("/job/1"))
        self.assertEqual(truncated, 3, "the board's own total is still reported")

    def test_no_company_names_left_in_the_scanner(self):
        """The regression guard. `scan-portals.py` may name PLATFORMS (greenhouse,
        workday…) but never a company or its endpoint — that is data, and it lives in
        the data root now."""
        src = (Path(settings.SITE_ROOT) / "src" / "scan-portals.py").read_text()
        for literal in ("COMPANY_OVERRIDES", "KNOWN_UNSUPPORTED_REASONS"):
            self.assertNotIn(literal, src,
                             f"{literal!r} is back in scan-portals.py — it belongs in scan-config.yaml")

        # The first-party fetcher must take its endpoint from the override, never a
        # literal. Naming the company's domain here would only move the disclosure from
        # the scanner into the test, so assert the shape instead: no absolute http(s)
        # URL in that branch that isn't built from `source`.
        self.assertIn('source["url"]', src,
                      "the firstparty_entries branch should read its endpoint from the override")
        branch = src.split('if platform == "firstparty_entries":', 1)[-1].split("\n        if ")[0]
        self.assertNotRegex(branch, r'"https?://[^"]+"',
                            "a company endpoint is hardcoded in the firstparty_entries branch")


class PlatformFetcherTests(TestCase):
    """The fetchers added for `#10` on 2026-10-08 — Pinpoint, SuccessFactors career-site
    RSS, Hireserve, UKG, Radancy, and the sitemap + JSON-LD fallback.

    Each response below is trimmed from a live board, keeping only the fields the
    fetcher reads, plus one row it must skip rather than fail on (`#63`). No network.
    """

    def _scan_portals(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "scan_portals_under_test", Path(settings.SITE_ROOT) / "src" / "scan-portals.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    class _Resp:
        def __init__(self, body=None, text=""):
            self._body, self.text = body, text
            self.content = text.encode()
        def raise_for_status(self): pass
        def json(self): return self._body

    def _client(self, respond):
        """A client whose get/post hand (url, params, json) to `respond`; it records calls."""
        resp_cls = self._Resp
        class _Client:
            calls = []
            def get(self, url, params=None, **kw):
                _Client.calls.append(("GET", url, params))
                return respond(url, params, None, resp_cls)
            def post(self, url, json=None, **kw):
                _Client.calls.append(("POST", url, json))
                return respond(url, None, json, resp_cls)
        return _Client()

    def test_pinpoint(self):
        sp = self._scan_portals()
        body = {"data": [
            {"title": "Data Scientist", "url": "https://acme.pinpointhq.com/en/postings/abc",
             "location": {"name": "Madrid ", "province": "Madrid"}, "workplace_type": "hybrid",
             "workplace_type_text": "Hybrid"},
            {"title": "No link", "location": {}},
        ]}
        client = self._client(lambda url, p, j, R: R(body))
        jobs, _ = sp.fetch_jobs({"platform": "pinpoint", "token": "acme"}, "", client)
        self.assertEqual(client.calls[0][1], "https://acme.pinpointhq.com/postings.json")
        self.assertEqual(jobs, [{"title": "Data Scientist", "url": "https://acme.pinpointhq.com/en/postings/abc",
                                 "location": "Madrid (Hybrid)"}],
                         "padded duplicate place names collapse; hybrid is said")

    def test_pinpoint_is_detected_from_the_board_url(self):
        import scan_sources
        self.assertEqual(scan_sources.resolve_source("X", "https://acme.pinpointhq.com/en/postings"),
                         {"platform": "pinpoint", "token": "acme"})
        self.assertIsNone(scan_sources.resolve_source("X", "https://www.pinpointhq.com/customers"),
                          "a link to the vendor's own site is not a board called 'www'")

    def test_recruitee(self):
        """`#90`. A remote offer's own `location` is only "Remote job"; the country has to
        survive, or a US-only remote role reads as one a UK search could take."""
        sp = self._scan_portals()
        body = {"offers": [
            {"title": "Account Manager", "careers_url": "https://careers.acme.com/o/account-manager",
             "location": "Farringdon, England, United Kingdom", "city": "Farringdon",
             "country": "United Kingdom", "remote": False, "hybrid": True},
            {"title": "Data Engineer", "careers_url": "https://careers.acme.com/o/data-engineer",
             "location": "Remote job", "city": "East Coast, Remote", "country": "United States",
             "remote": True, "hybrid": False},
            {"title": "No link", "location": "Gent, Belgium"},
        ]}
        client = self._client(lambda url, p, j, R: R(body))
        jobs, _ = sp.fetch_jobs({"platform": "recruitee", "token": "acme"}, "", client)
        self.assertEqual(client.calls[0][1], "https://acme.recruitee.com/api/offers/")
        self.assertEqual(jobs, [
            {"title": "Account Manager", "url": "https://careers.acme.com/o/account-manager",
             "location": "Farringdon, England, United Kingdom (hybrid)"},
            {"title": "Data Engineer", "url": "https://careers.acme.com/o/data-engineer",
             "location": "East Coast, Remote, United States (remote)"},
        ])

    def test_recruitee_is_detected_from_the_board_url(self):
        import scan_sources
        self.assertEqual(scan_sources.resolve_source("X", "https://acme.recruitee.com/"),
                         {"platform": "recruitee", "token": "acme"})
        self.assertIsNone(scan_sources.resolve_source("X", "https://www.recruitee.com/"),
                          "a link to the vendor's own site is not a board called 'www'")

    _RSS = """<?xml version="1.0" encoding="UTF-8" ?><rss version="2.0"><channel>
      <item><title><![CDATA[Data Lead (London, GB, W12 7FA)]]></title>
        <description><![CDATA[<p>DEPARTMENT: Acme Studios</p>]]></description>
        <link>https://careers.acme.example/job/London-Data-Lead/101/?feedId=null&amp;utm_source=J2WRSS</link></item>
      <item><title><![CDATA[News Producer (Delhi, IN)]]></title>
        <description><![CDATA[<p>DEPARTMENT: Acme News</p>]]></description>
        <link>https://careers.acme.example/job/Delhi-News-Producer/102/</link></item>
      <item><title></title><description>Acme Studios</description><link>https://careers.acme.example/job/x/103/</link></item>
    </channel></rss>"""

    def test_successfactors_rss_splits_the_location_off_the_title_and_asks_for_every_row(self):
        sp = self._scan_portals()
        client = self._client(lambda url, p, j, R: R(text=self._RSS))
        jobs, _ = sp.fetch_jobs({"platform": "successfactors", "domain": "careers.acme.example"}, "", client)
        self.assertEqual(client.calls[0][1], "https://careers.acme.example/services/rss/job/")
        self.assertIn("rows", client.calls[0][2], "without `rows` the feed stops at 20")
        self.assertEqual(jobs[0], {"title": "Data Lead", "location": "London, GB, W12 7FA",
                                   "url": "https://careers.acme.example/job/London-Data-Lead/101/"})
        self.assertEqual(len(jobs), 2)

    def test_successfactors_filter_keeps_one_organisation_off_a_shared_site(self):
        sp = self._scan_portals()
        client = self._client(lambda url, p, j, R: R(text=self._RSS))
        jobs, _ = sp.fetch_jobs({"platform": "successfactors", "domain": "careers.acme.example",
                                 "filter": "acme studios"}, "", client)
        self.assertEqual([j["title"] for j in jobs], ["Data Lead"],
                         "the sibling's posting is dropped; matching ignores case")

    def test_hireserve_reads_the_location_classification(self):
        sp = self._scan_portals()
        body = {"total": 2, "jobs": [
            {"title": "Data Analyst", "weblink": "https://jobs.acme.example/vacancy/data-analyst-1.html",
             "classifications": {"class_1": {"name": "Location", "values": [{"class_val": "Hybrid"},
                                                                            {"class_val": "Bristol"}]},
                                 "class_2": {"name": "Department", "values": [{"class_val": "Data"}]}}},
            {"title": "No link", "classifications": {}},
        ]}
        client = self._client(lambda url, p, j, R: R(body))
        jobs, truncated = sp.fetch_jobs({"platform": "hireserve", "domain": "jobs.acme.example",
                                         "site_id": 99}, "", client)
        self.assertEqual(client.calls[0][2]["p_format"], "MOBILE",
                         "the one format carrying both the link and the location")
        self.assertEqual(jobs[0]["location"], "Hybrid; Bristol")
        self.assertEqual(truncated, 2)

    def test_ukg_pages_and_marks_remote(self):
        sp = self._scan_portals()
        page = {"totalCount": 2, "opportunities": [
            {"Id": "a1", "Title": "Data Engineer", "JobLocationType": 0,
             "Locations": [{"Address": {"City": "Columbus", "State": {"Code": "OH"},
                                        "Country": {"Name": "United States"}}}]},
            {"Id": "b2", "Title": "Account Manager", "JobLocationType": 2,
             "Locations": [{"LocalizedName": "Anywhere", "Address": {}}]},
        ]}
        client = self._client(lambda url, p, j, R: R(page if j["opportunitySearch"]["Skip"] == 0
                                                      else {"opportunities": []}))
        jobs, _ = sp.fetch_jobs({"platform": "ukg", "tenant": "ACME1", "board": "guid-1"}, "", client)
        self.assertEqual(len(client.calls), 1, "stops once the total is reached")
        self.assertEqual(jobs[0]["location"], "Columbus, OH, United States")
        self.assertEqual(jobs[1]["location"], "Anywhere (remote)")
        self.assertTrue(jobs[0]["url"].endswith("/ACME1/JobBoard/guid-1/OpportunityDetail?opportunityId=a1"))

    def test_ukg_links_do_not_all_normalise_to_the_same_key(self):
        """`_normalize` keys a posting on its last path segment, and every UKG link ends
        `/OpportunityDetail` — one tracked application would hide the whole board."""
        sp = self._scan_portals()
        base = "https://recruiting.ultipro.com/ACME1/JobBoard/guid-1/OpportunityDetail?opportunityId="
        self.assertNotEqual(sp._normalize(base + "a1"), sp._normalize(base + "b2"))
        self.assertEqual(sp._normalize("https://jobs.lever.co/acme/abc-123?lever-source=x"), "abc-123",
                         "other platforms' keys are unchanged")

    def test_radancy_parses_the_results_fragment_and_pages(self):
        sp = self._scan_portals()
        def li(n):
            return (f'<li><a href="/en/job/london/role-{n}/1/{n}" data-job-id="{n}">'
                    f'<h2>Role {n} &amp; Co</h2><span class="job-location">London, England</span></a></li>')
        pages = {1: f'<section data-total-results="3">{li(1)}{li(2)}</section>',
                 2: f'<section data-total-results="3">{li(3)}</section>'}
        client = self._client(lambda url, p, j, R: R({"results": pages.get(p["CurrentPage"], "")}))
        jobs, _ = sp.fetch_jobs({"platform": "radancy", "domain": "careers.acme.example"},
                                "Head of Data", client)
        self.assertEqual([j["title"] for j in jobs], ["Role 1 & Co", "Role 2 & Co", "Role 3 & Co"])
        self.assertEqual(jobs[0]["url"], "https://careers.acme.example/en/job/london/role-1/1/1")
        self.assertEqual(jobs[0]["location"], "London, England")
        self.assertEqual(len(client.calls), 2, "stops at the reported total, not on an empty page")
        self.assertEqual(client.calls[0][2]["Keywords"], "Head")

    def test_sitemap_reads_each_postings_json_ld(self):
        sp = self._scan_portals()
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc> https://jobs.acme.example/jobs/job/Data-Lead/1 </loc></url>
          <url><loc>https://jobs.acme.example/jobs/job/Gone/2</loc></url>
          <url><loc>https://jobs.acme.example/about</loc></url></urlset>"""
        posting = """<script type="application/ld+json">{"@context": "https://schema.org",
          "@graph": [{"@type": "Organization"}, {"@type": "JobPosting", "title": "Data Lead",
          "jobLocation": {"address": {"addressLocality": "London", "addressCountry": {"name": "UK"}}}}]}
          </script>"""
        def respond(url, p, j, R):
            if url.endswith("/sitemap/1"):
                return R(text=sitemap)
            return R(text=posting if url.endswith("/1") else "<html>no markup</html>")
        client = self._client(respond)
        jobs, total = sp.fetch_jobs({"platform": "sitemap", "sitemap": "https://jobs.acme.example/sitemap/1",
                                     "path": "/jobs/job/"}, "", client)
        self.assertEqual(jobs, [{"title": "Data Lead", "url": "https://jobs.acme.example/jobs/job/Data-Lead/1",
                                 "location": "London, UK"}])
        self.assertEqual(len(client.calls), 3, "the sitemap, then only the posting URLs")
        self.assertEqual(total, 2, "a posting with no JobPosting markup is counted, not hidden")


class JobBoardTests(TestCase):
    """`#8` — searching Adzuna and Reed for roles at companies nobody has tracked.

    All offline: the boards are stubbed with responses trimmed from their documented
    shapes. Company names are invented.
    """

    PROFILES = {"data-platform": {"key_terms": ["data platform", "data engineering"]},
                "knowledge-graph": {"key_terms": ["knowledge graph", "ontology"]}}
    QUERIES = {"queries": ['"Data Platform" OR "Data Engineering"']}

    def setUp(self):
        # Keys may really be in this machine's ~/.jobstudio.ini; none of these tests may
        # see them, or "no credentials" stops meaning that.
        patcher = mock.patch("config.setting", lambda key, default="": default)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _client(self, adzuna=(), reed=(), fail=()):
        class _Resp:
            def __init__(self, body): self.body = body
            def raise_for_status(self): pass
            def json(self): return self.body

        class _Client:
            calls = []
            def get(self, url, params=None, **kw):
                _Client.calls.append((url, params, kw))
                if any(f in url for f in fail):
                    raise RuntimeError("HTTP 401")
                if "adzuna" in url:
                    return _Resp({"results": list(adzuna)})
                return _Resp({"results": list(reed)})
        return _Client()

    @staticmethod
    def _adzuna(title, company, url):
        return {"title": title, "redirect_url": url, "company": {"display_name": company},
                "location": {"display_name": "London, UK"}, "description": "<b>Own</b> the platform",
                "salary_min": 70000, "salary_max": 90000}

    @staticmethod
    def _reed(title, company, url, posted=None):
        # Today, not a fixed date: Reed postings are age-filtered against the real clock.
        return {"jobTitle": title, "jobUrl": url, "employerName": company,
                "locationName": "Bristol", "jobDescription": "Build pipelines",
                "date": posted or dt.date.today().strftime("%d/%m/%Y")}

    def _discover(self, client, settings, **kw):
        import job_boards
        kw.setdefault("skip_company_keys", set())
        kw.setdefault("known", set())
        return job_boards.discover(client, settings, self.PROFILES, ["data-platform", "knowledge-graph"],
                                   "data-platform", normalize=lambda u: u.rsplit("/", 1)[-1], **kw)

    def test_no_credentials_means_no_board_and_no_request(self):
        import job_boards
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(job_boards.credentials({}), {})
            self.assertEqual(job_boards.credentials({"adzuna": {"app_id": "x"}}), {},
                             "half a credential is no credential")
            client = self._client()
            postings, stats = self._discover(client, {})
        self.assertEqual((postings, client.calls), ([], []))

    def test_credentials_can_come_from_the_environment(self):
        import job_boards
        env = {"ADZUNA_APP_ID": "a", "ADZUNA_APP_KEY": "b", "REED_API_KEY": "c"}
        with mock.patch.dict("os.environ", env, clear=True):
            self.assertEqual(sorted(job_boards.credentials({})), ["adzuna", "reed"])

    def test_queries_split_on_or_and_dedupe(self):
        import job_boards
        self.assertEqual(job_boards.queries({"queries": ['"Head of Data" OR "VP Data"', "knowledge graph",
                                                         "head of data"]}),
                         ["Head of Data", "VP Data", "knowledge graph"])
        self.assertEqual(job_boards.queries({"queries": "knowledge graph"}), ["knowledge graph"])
        self.assertEqual(job_boards.queries({}), [], "no fallback to the areas' key terms")

    def test_a_title_must_carry_every_word_of_the_phrase(self):
        import job_boards
        self.assertTrue(job_boards.title_matches("Head of Data & Analytics", "Head of Data"))
        self.assertTrue(job_boards.title_matches("VP, Data Products", "VP Data"))
        self.assertFalse(job_boards.title_matches("Head of Training", "Head of Data"))

    def test_keys_but_no_queries_searches_nothing(self):
        client = self._client(adzuna=[self._adzuna("Data Platform Lead", "Acme", "https://a.example/1")])
        with mock.patch.dict("os.environ", {}, clear=True):
            postings, stats = self._discover(client, {"adzuna": {"app_id": "i", "app_key": "k"}})
        self.assertEqual((postings, client.calls, stats["queries"]), ([], [], 0))

    def test_discovery_filters_dedups_and_labels(self):
        """Every drop is counted under its own reason, and nothing is dropped twice."""
        adzuna = [
            self._adzuna("Data Platform Lead", "Acme Ltd", "https://adzuna.example/land/1"),
            self._adzuna("Data Barista", "Cafe", "https://adzuna.example/land/2"),       # loose match
            self._adzuna("Data Engineering Manager", "Tracked Co", "https://adzuna.example/land/3"),
            self._adzuna("Data Platform Engineer", "Northwind Recruitment", "https://adzuna.example/land/4"),
            self._adzuna("Data Platform Analyst", "Initech", "https://adzuna.example/land/known"),
        ]
        reed = [
            self._reed("Data Platform Lead", "ACME Limited", "https://reed.example/jobs/9"),  # same job
            self._reed("Data Engineering Lead", "Globex", "https://reed.example/jobs/10"),
            self._reed("Data Platform Owner", "Globex", "https://reed.example/jobs/11", posted="01/01/2020"),
        ]
        settings = {"adzuna": {"app_id": "i", "app_key": "k"}, "reed": {"api_key": "r"},
                    "results_per_query": 20, **self.QUERIES}
        client = self._client(adzuna, reed)
        with mock.patch.dict("os.environ", {}, clear=True):
            postings, stats = self._discover(client, settings,
                                             skip_company_keys={"tracked"}, known={"known"})

        self.assertEqual([(p["company"], p["title"]) for p in postings], [
            ("Acme Ltd", "Data Platform Lead"),
            ("Northwind Recruitment", "Data Platform Engineer"),
            ("Globex", "Data Engineering Lead"),
        ], "Reed's 'ACME Limited' is Adzuna's 'Acme Ltd'; the 2020 posting is too old")
        self.assertEqual([p["agency"] for p in postings], [False, True, False])
        self.assertEqual([p["area"] for p in postings], ["data-platform"] * 3)
        self.assertEqual(postings[0]["salary"], "£70,000–£90,000")
        self.assertEqual(postings[0]["snippet"], "Own the platform", "HTML is stripped")

        # Two phrases (one line split on OR) on each board, each stub answering the same list.
        self.assertEqual(stats["queries"], 4)
        self.assertEqual(stats["found"], 5 * 2 + 2 * 2, "Reed's stale posting is never counted as found")
        # A title must carry every word of the phrase that found it, so most rows fail one
        # of the two phrases ("Data Platform Engineer" is not "Data Engineering").
        self.assertEqual(stats["title_filtered"], 8)
        self.assertEqual(stats["covered_by_company_scan"], 1)
        self.assertEqual(stats["already_tracked"], 1)
        self.assertEqual(stats["duplicates"], 1)

        adzuna_call = next(c for c in client.calls if "adzuna" in c[0])
        self.assertIn("title_only", adzuna_call[1], "Adzuna searches titles, not whole adverts")
        reed_call = next(c for c in client.calls if "reed" in c[0])
        self.assertEqual(reed_call[2]["auth"], ("r", ""), "Reed: the key is the Basic-auth username")

    def test_only_advertised_annual_salaries_are_shown(self):
        import job_boards
        predicted = {**self._adzuna("Data Platform Lead", "Acme", "https://a.example/1"),
                     "salary_is_predicted": "1"}
        junk = {**self._adzuna("Data Platform Owner", "Acme", "https://a.example/2"),
                "salary_min": 5, "salary_max": 5}
        client = self._client(adzuna=[predicted, junk])
        found = job_boards.search_adzuna(client, {"app_id": "i", "app_key": "k"}, "data platform",
                                         max_days_old=7, results=10)
        self.assertEqual([p["salary"] for p in found], ["", ""])

    def test_a_failing_board_costs_its_queries_not_the_run(self):
        settings = {"adzuna": {"app_id": "i", "app_key": "k"}, "reed": {"api_key": "r"}, **self.QUERIES}
        client = self._client(reed=[self._reed("Data Platform Lead", "Globex", "https://reed.example/jobs/1")],
                              fail=("adzuna",))
        with mock.patch.dict("os.environ", {}, clear=True):
            postings, stats = self._discover(client, settings)
        self.assertEqual([p["company"] for p in postings], ["Globex"])
        self.assertEqual(len(stats["errors"]), 2)
        self.assertIn("HTTP 401", stats["errors"][0])

    def test_an_excluded_company_is_dropped_tracked_or_not(self):
        settings = {"adzuna": {"app_id": "i", "app_key": "k"}, **self.QUERIES}
        client = self._client(adzuna=[self._adzuna("Data Platform Lead", "Initech Ltd", "https://a.example/1"),
                                      self._adzuna("Data Platform Lead", "Globex", "https://a.example/2")])
        with mock.patch.dict("os.environ", {}, clear=True):
            postings, stats = self._discover(client, settings, excluded_company_keys={"initech"})
        self.assertEqual([p["company"] for p in postings], ["Globex"])
        self.assertEqual(stats["excluded"], 1, "once — the second phrase's title filter drops the rest")

    def test_agency_and_company_matching(self):
        import job_boards
        self.assertTrue(job_boards.is_agency("Harnham"))
        self.assertTrue(job_boards.is_agency("Michael Page Technology"), "agencies post under divisions")
        self.assertFalse(job_boards.is_agency("Reedsy"), "a prefix match is on whole words")
        self.assertTrue(job_boards.is_agency("Northwind Resourcing Ltd"))
        self.assertTrue(job_boards.is_agency("Acme Partners", extra=["Acme Partners Ltd"]))
        self.assertFalse(job_boards.is_agency("Acme Analytics"))
        self.assertFalse(job_boards.is_agency(""))
        self.assertEqual(job_boards.company_keys("Initech Data (Globex Analytics)"),
                         {"initech data globex analytics", "initech data", "globex analytics"})

    def test_discovered_postings_get_their_own_section_and_stay_out_of_the_match_counts(self):
        """The vetted/unvetted line is the point of the section: a job-board hit is never
        ranked among tracked-company matches, and the dashboard's match counts — read off
        the Summary bullets — stay about tracked companies."""
        import importlib
        import config
        import scan_report
        from tracker import parsers

        orig = config.data_root
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "jobs" / "scans").mkdir(parents=True)
            config.data_root = lambda: tmp
            importlib.reload(scan_report)

            def cand(company, title, **kw):
                c = scan_report.Candidate(company=company, title=title, url=f"https://x.example/{title}",
                                          role_target="", area="data-platform", location="London", **kw)
                c.cv_score, c.ideal_score, c.location_category, c.notes = 4, 4, "uk", "Fits."
                return c

            tracked = cand("Tracked Co", "Data Lead")
            found = cand("Northwind Recruitment", "Platform Lead", source="adzuna", agency=True,
                         salary="£80,000")
            discovery = {"boards": ["adzuna"], "queries": 2, "found": 9, "title_filtered": 3,
                         "covered_by_company_scan": 1, "already_tracked": 0, "duplicates": 4,
                         "errors": ["reed 'x': HTTPStatusError: 401"]}
            text = scan_report.write_report(
                scanned_count=1, not_scanned=[], matches=[tracked, found], discarded_by_location=[],
                needs_review=[], no_roles=[], total_found=1, total_skipped_dedup=0,
                coverage_notes=[], prefiltered={}, location_prefiltered={},
                discovery=discovery).read_text()
        finally:
            config.data_root = orig
            importlib.reload(scan_report)
            shutil.rmtree(tmp)

        strong = text.split("## Strong matches", 1)[1].split("## Discovered on job boards", 1)[0]
        self.assertIn("Tracked Co", strong)
        self.assertNotIn("Northwind", strong)
        board = text.split("## Discovered on job boards", 1)[1].split("\n## ", 1)[0]
        self.assertIn("**Northwind Recruitment** *(agency)*", board)
        self.assertIn("£80,000", board)
        self.assertIn("- Scored matches: 1 (1 strong, 0 other)", text)
        self.assertIn("- Discovered matches: 1 (1 strong)", text)
        self.assertIn("**Search failed** — reed", text)

        tabs = {s["key"]: s for s in parsers.split_scan_sections(text)}
        self.assertEqual(tabs["discovered-on-job-boards"]["short_title"], "Job boards")
        self.assertEqual(tabs["discovered-on-job-boards"]["count"], 1)

    def test_a_scan_without_job_boards_renders_as_before(self):
        """No `job_boards` config, no section and no Job boards block — an existing
        user's report is unchanged."""
        import importlib
        import config
        import scan_report
        orig = config.data_root
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "jobs" / "scans").mkdir(parents=True)
            config.data_root = lambda: tmp
            importlib.reload(scan_report)
            text = scan_report.write_report(
                scanned_count=0, not_scanned=[], matches=[], discarded_by_location=[],
                needs_review=[], no_roles=[], total_found=0, total_skipped_dedup=0,
                coverage_notes=[], prefiltered={}, location_prefiltered={}).read_text()
        finally:
            config.data_root = orig
            importlib.reload(scan_report)
            shutil.rmtree(tmp)
        self.assertNotIn("Discovered on job boards", text)
        self.assertNotIn("### Job boards", text)


class HelpPageTests(TestCase):
    """The in-app help page (TODO #51).

    The app shows a job search but never said how to work it — the commands lived
    in the docs and the skill, neither of which is open while you are looking at a
    page. The descriptions are read from the skill's own help table rather than
    retyped, because a hand-copied list drifts: `render-html-pdf` became `render`
    the same week this was written.
    """

    fixtures = FIXTURE

    def test_the_page_renders(self):
        r = self.client.get("/help/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "How to use this")

    def test_it_lists_the_commands_from_the_skill(self):
        from pathlib import Path
        from django.conf import settings
        from tracker.parsers import parse_skill_commands

        skill = (Path(settings.SITE_ROOT) / ".claude" / "skills" / "jobstudio"
                 / "SKILL.md")
        commands = parse_skill_commands(skill)
        self.assertTrue(commands, "the skill's help table parsed to nothing")

        html = self.client.get("/help/").content.decode()
        for c in commands:
            with self.subTest(command=c["name"]):
                self.assertIn(f"/jobstudio {c['name']}", html)

    def test_every_command_named_in_a_step_exists_in_the_skill(self):
        """A step naming a command the skill doesn't have would silently vanish."""
        from pathlib import Path
        from django.conf import settings
        from tracker.parsers import parse_skill_commands
        from tracker.views import HELP_STEPS

        skill = (Path(settings.SITE_ROOT) / ".claude" / "skills" / "jobstudio"
                 / "SKILL.md")
        known = {c["name"] for c in parse_skill_commands(skill)}
        for step in HELP_STEPS:
            for name in step["commands"]:
                with self.subTest(step=step["heading"], command=name):
                    self.assertIn(name, known)

    def test_the_faq_says_why_docx_is_the_only_export(self):
        """#70: the help page is where someone looking at an export is standing."""
        html = self.client.get("/help/").content.decode()
        self.assertIn('id="faq"', html)
        self.assertIn("Why only .docx", html)
        self.assertIn("Word or Pages", html)

    def test_it_is_linked_from_the_sidebar_under_its_own_label(self):
        """Its own nav group, at the level of Tracker / Material / Local — not tucked
        inside Material, where it read as another piece of job-search content."""
        html = self.client.get("/").content.decode()
        self.assertIn('href="/help/"', html)
        group = html[html.index('<div class="nav-label">Help</div>'):]
        group = group[:group.index("</div>", group.index('href="/help/"'))]
        self.assertIn('href="/help/"', group)
        # and not still sitting in Material
        material = html[html.index('<div class="nav-label">Material</div>'):]
        material = material[:material.index('<div class="nav-group">')]
        self.assertNotIn('href="/help/"', material)

    def test_a_missing_skill_leaves_a_usable_page(self):
        """A published mirror or a checkout without the skill still gets a page."""
        from django.test import override_settings
        with override_settings(SITE_ROOT="/nonexistent/for/this/test"):
            r = self.client.get("/help/")
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "/jobstudio help")


class CareerCoachTabTests(TestCase):
    """The career-coach folder as a tab on /notes/: dictated session notes render, the
    material the coach hands over is listed, and opening it is local-only and limited to
    documents."""

    fixtures = FIXTURE

    def setUp(self):
        # Inside the data root, because that is the only place `open_file` will open from.
        tmp = tempfile.TemporaryDirectory(dir=settings.DATA_ROOT)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "2026-01-10_session-1.md").write_text("# Session one\n\n## Actions\n\n- first\n")
        (self.root / "2026-02-14_session-2.md").write_text("# Session two\n\n## Actions\n\n- second\n")
        (self.root / "materials").mkdir()
        (self.root / "materials" / "reading.md").write_text("# Reading\n\nA handout.\n")
        (self.root / "materials" / "STAR template.pdf").write_bytes(b"%PDF-1.4")
        (self.root / "materials" / ".DS_Store").write_bytes(b"x")
        (self.root / "run-me.sh").write_text("echo no\n")
        override = self.settings(COACH_DIR=str(self.root))
        override.enable()
        self.addCleanup(override.disable)

    def _tab(self) -> str:
        html = self.client.get("/notes/").content.decode()
        self.assertIn('data-tab="career-coach"', html)
        return html[html.index('data-panel="career-coach"'):]

    def test_markdown_renders_newest_session_first_then_subfolders(self):
        tab = self._tab()
        order = [tab.index(t) for t in ("Session two", "Session one", "Reading")]
        self.assertEqual(order, sorted(order))
        self.assertIn("second", tab)
        self.assertIn('href="#career-coach--2026-02-14-session-2"', tab)

    def test_other_files_are_listed_by_folder_and_hidden_files_skipped(self):
        tab = self._tab()
        self.assertIn("STAR template.pdf", tab)
        self.assertIn("materials/", tab)
        self.assertNotIn(".DS_Store", tab)
        self.assertIn("/actions/open-file/?path=", tab)

    def test_open_file_opens_documents_only(self):
        rel = lambda p: str(p.relative_to(Path(settings.DATA_ROOT).resolve()))
        root = self.root.resolve()
        with mock.patch("tracker.views._open_locally") as opened:
            r = self.client.get("/actions/open-file/", {"path": rel(root / "materials" / "STAR template.pdf")})
            self.assertEqual(r.status_code, 302)
            opened.assert_called_once()
            for bad in (rel(root / "run-me.sh"), rel(root / "missing.pdf")):
                with self.subTest(path=bad):
                    self.assertEqual(self.client.get("/actions/open-file/", {"path": bad}).status_code, 404)

    def test_no_folder_no_tab(self):
        with self.settings(COACH_DIR=str(self.root / "nope")):
            html = self.client.get("/notes/").content.decode()
        self.assertNotIn('data-tab="career-coach"', html)

    def test_every_id_is_still_unique(self):
        html = self.client.get("/notes/").content.decode()
        ids = re.findall(r'id="([^"]+)"', html)
        self.assertEqual({i for i in ids if ids.count(i) > 1}, set())
