"""Tests.

Since Phase 6 the database is the source of truth for applications and companies, so test
data comes from the committed synthetic fixture (example-data/backups/django/dump.json) rather than from parsing
markdown. The filesystem-derived parts — target YAMLs, CV files, cover letters, scans —
are still exercised against the real jobs/ tree, because the thing most likely to break
there is a file naming convention drifting.
"""

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
from django.test import TestCase
from django.utils.html import escape

from appfolder import (COMPANY_APPLIED_TRIGGER_STATUSES, COMPANY_STATUSES,
                       STATUS_SORT_ORDER, exported_file)
from tracker import parsers as P
from tracker.models import (Application, ApplicationStatusChange, Area, Category,
                            Company, Scan)

FIXTURE = ["dump.json"]


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
            for key in ("emphasis", "key_terms", "expand_sections", "condense_sections"):
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
            for key in ("emphasis", "key_terms", "expand_sections", "condense_sections"):
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
    """Two states. `applied` requires an application that was actually submitted
    (COMPANY_APPLIED_TRIGGER_STATUSES) — not merely logged (decided 2026-09-08)."""

    fixtures = FIXTURE

    def test_every_status_is_in_the_two_state_model(self):
        for company in Company.objects.all():
            self.assertIn(company.status, COMPANY_STATUSES, company.name)

    def test_status_matches_trigger_statuses(self):
        for company in Company.objects.all():
            expected = ("applied"
                       if company.applications.filter(
                           status__in=COMPANY_APPLIED_TRIGGER_STATUSES).exists()
                       else "watching")
            self.assertEqual(company.status, expected, company.name)

    def test_status_updates_when_a_submitted_application_is_added(self):
        company = Company.objects.filter(applications__isnull=True).first()
        self.assertEqual(company.status, "watching")
        Application.objects.create(
            num=9001, company=company, company_name=company.name,
            role="Test", status="applied")
        company.refresh_from_db()
        self.assertEqual(company.status, "applied")

    def test_saved_or_reviewing_does_not_trigger_applied(self):
        """A `saved`/`reviewing` row is a placeholder before submission — it must not
        flip the company to `applied` on its own."""
        for num, status in [(9006, "saved"), (9007, "reviewing")]:
            with self.subTest(status=status):
                company = Company.objects.filter(applications__isnull=True).first()
                Application.objects.create(num=num, company=company,
                                           company_name=company.name,
                                           role="Test", status=status)
                company.refresh_from_db()
                self.assertEqual(company.status, "watching")

    def test_rejected_application_still_counts_as_applied(self):
        """A rejection does not revert a company to `watching` — the application still
        happened, and that is what the company row records."""
        company = Company.objects.filter(applications__isnull=True).first()
        Application.objects.create(num=9003, company=company, company_name=company.name,
                                   role="Test", status="rejected")
        company.refresh_from_db()
        self.assertEqual(company.status, "applied")

    def test_closed_and_discarded_do_not_count(self):
        """`closed` (deadline passed before applying) and `discarded` (dropped before
        applying) both mean no application was ever submitted."""
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
                    "/companies/", f"/companies/{company.slug}/", "/areas/", "/cvs/",
                    "/notes/", "/profile/", "/scans/", "/scans/all/"]:
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
        cov = scan_sources.coverage("Example Analytics Ltd", "https://example.com/careers")
        self.assertFalse(cov["scanned"])
        self.assertIn("BambooHR", cov["reason"])

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


class ViewTests(TestCase):
    fixtures = FIXTURE

    def test_index_pages(self):
        for url in ["/", "/applications/", "/applications/all/", "/applications/active/",
                    "/companies/", "/areas/", "/cvs/", "/notes/", "/scans/", "/scans/all/"]:
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
        for url in ["/", "/applications/", "/applications/all/", "/companies/", "/areas/", "/cvs/",
                    "/scans/", "/scans/all/"]:
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
        for url in ["/", "/applications/", "/applications/all/", "/companies/", "/areas/", "/cvs/",
                    "/scans/", "/scans/all/"]:
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

    def test_pick_cv_prefers_a_tailored_copy_in_the_folder(self):
        import appfolder
        row = {"num": "1", "company": "Grafana Labs", "role": "Senior Developer Advocate",
               "area": "developer-advocacy", "status": "applied"}
        picked = appfolder.pick_cv(row)
        self.assertTrue(appfolder.is_tailored_cv(picked.name), picked.name)
        self.assertIn("001-grafana-labs", str(picked))

    def test_is_tailored_cv_recognises_area_named_cvs(self):
        """Tailored CVs are named after the target AREA, not after the base CV.

        The previous implementation matched only cv-functional / cv-chronological /
        cv_functional, so any CV tailored to an area was invisible — 15 of the 30 in
        the author's job search — and pick_cv() silently fell back to the untailored
        base. Pure filename logic on purpose: no fixture, no folder on disk, nothing
        that depends on whatever happens to be in one person's job search.
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
            self.assertTrue(appfolder.is_tailored_cv(name), f"should be tailored: {name}")

        not_tailored = [
            "cv_functional.md",                                  # untailored base copy
            "cv_chronological.md",
            "notes.md",
            "job.md",
            "004-incident-io-alex-rivera-cover-letter-2026-09-03.md",
        ]
        for name in not_tailored:
            self.assertFalse(appfolder.is_tailored_cv(name), f"should NOT be tailored: {name}")

    def test_functional_cv_has_the_section_the_tailoring_splices(self):
        """generate_functional() splices on these markers — fail loudly if they move."""
        from django.conf import settings
        cv = (Path(settings.CV_DIR) / "base" / "cv_functional.md").read_text()
        self.assertIn("## Core Competencies", cv)
        start = cv.index("## Core Competencies")
        self.assertIn("\n## ", cv[start + 20:], "no section follows Core Competencies")


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
        """`ensure_folder()` scaffolds an untailored `cv_functional.md` beside the
        tailored CV. With two candidate sources, pairing an export with one of them is a
        guess — and linking the same file under two headings reads as two documents."""
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


class CoverLetterFormatTests(TestCase):
    """`.docx` is the version that gets sent, so it is the only one written by default.
    HTML used to come out every time because the PDF path needs something for Chrome to
    print — harmless while renders went to `exports/`, but once they landed in the
    application folder (2026-09-24) every cover letter left an `.html` beside its `.docx`
    that nobody had asked for."""

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

    def test_the_default_is_the_docx_alone(self):
        self.render.export_cover_letter(self.letter)

        self.assertEqual(len(self._rendered("docx")), 1)
        self.assertEqual(self._rendered("html"), [])
        self.assertEqual(self._rendered("pdf"), [])

    def test_html_is_written_only_when_it_is_asked_for(self):
        self.render.export_cover_letter(self.letter, fmt="html")

        self.assertEqual(len(self._rendered("html")), 1)
        self.assertEqual(len(self._rendered("docx")), 1, "the .docx comes out either way")

    def test_a_pdf_render_prints_from_a_temp_file_and_keeps_no_html(self):
        seen = {}

        def fake_print(html_path, pdf_path):
            seen["readable"] = html_path.is_file()
            seen["parent"] = html_path.parent
            pdf_path.write_bytes(b"%PDF-1.4 not really")

        with mock.patch.object(self.render, "_chrome_print_pdf", fake_print):
            self.render.export_cover_letter(self.letter, fmt="pdf")

        self.assertTrue(seen["readable"], "Chrome still needs real HTML to print")
        self.assertNotEqual(seen["parent"].resolve(), self.export.resolve())
        self.assertEqual(self._rendered("html"), [])
        self.assertEqual(len(self._rendered("pdf")), 1)


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

    def test_interviews_tab_sits_between_job_description_and_notes(self):
        """Once a process is live the rounds are what gets reread, and the JD is what
        they're read against — so Interviews follows Job description, ahead of My notes.
        Asserted on the panel order too: with JS off the panels are the reading order."""
        app = Application.objects.get(num=1)
        html = self.client.get(f"/applications/{app.num}/").content.decode()
        for attr in ("data-tab", "data-panel"):
            with self.subTest(attr=attr):
                order = [t for t in ("record", "job", "interviews", "notes", "cv",
                                     "letters", "files", "history")
                         if f'{attr}="{t}"' in html]
                positions = {t: html.index(f'{attr}="{t}"') for t in order}
                self.assertLess(positions["job"], positions["interviews"])
                self.assertLess(positions["interviews"], positions["notes"])

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
        for heading in ("## My notes", "## Contacts", "## Timeline"):
            self.assertIn(heading, stub)

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

    def test_creates_folder_with_untailored_cv_and_empty_cover_letter(self):
        with self.settings(ENVIRONMENT="local"):
            resp = self.client.get(f"/actions/create-folder/{self.app.num}/")
        self.assertEqual(resp.status_code, 302)

        self.app.refresh_from_db()
        self.assertTrue(self.app.folder)
        folder = Path(settings.DATA_ROOT) / self.app.folder
        self.assertTrue((folder / "notes.md").is_file())
        self.assertTrue((folder / "cv_functional.md").is_file())

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
