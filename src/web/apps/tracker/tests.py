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

    def test_the_rubric_and_the_api_scorer_agree_on_placeholders(self):
        """The rubric file is shared by both scoring paths, but only the API path
        substitutes it with `str.format()` — so a `{placeholder}` added to the rubric
        without a matching kwarg in `score-candidates.py` raises KeyError, and only
        when someone runs `--api`. The agent-native default would never notice."""
        import string
        rubric = (Path(config.REPO_ROOT) / "src/prompts/scan_score_rubric.md").read_text()
        in_rubric = {f for _, f, _, _ in string.Formatter().parse(rubric) if f}
        source = (Path(config.REPO_ROOT) / "src/score-candidates.py").read_text()
        call = source.split("prompt = rubric.format(", 1)[1].split("\n    )", 1)[0]
        supplied = {line.split("=", 1)[0].strip() for line in call.splitlines()
                    if "=" in line and not line.strip().startswith(("#", '"', "or "))}
        self.assertEqual(in_rubric - supplied, set(),
                         "rubric placeholder with no value in score-candidates.py")

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
        for url in ["/", "/applications/", "/applications/all/", "/companies/", "/areas/",
                    "/stats/", "/cvs/", "/scans/", "/scans/all/"]:
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
    """`/stats/` — the charts page (backlog/dashboard-charts-plan.md §2a).

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
        # The example tier, and the sharp case in R3: three status changes and not one of
        # them a transition. If the fixture grows past this, the example-tier assertions
        # below are the ones to revisit.
        self.assertEqual(volumes["applications"], 3)
        self.assertEqual(volumes["transitions"], 0)

    def test_at_example_volume_the_history_charts_say_why_they_cannot_draw(self):
        """R3's example tier: there is data, but nothing has moved between statuses, so
        the charts built from transitions have nothing to plot and say so. The ones that
        do not need history are not held back by it."""
        sections = self.sections()
        self.assertIn("no ribbons to draw", sections["flow"])
        self.assertIn("needs transitions to replay", sections["stock"])
        for anchor in ("ageing", "companies", "per-company"):
            with self.subTest(anchor=anchor):
                self.assertNotIn("transitions", sections[anchor])

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

        stock = _status_stock()
        self.assertFalse(stock["ready"])
        self.assertContains(self.client.get("/stats/"), "before the shape of a pipeline")

    def test_a_band_that_was_never_occupied_is_not_a_series(self):
        """R3: a legend entry for a series that does not exist is worse than one fewer
        band. The example tracker has never had an application at `interviewing`."""
        from tracker.views import _status_stock

        self.assertNotIn("interviewing", _status_stock()["statuses"])

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
        self.assertIn('<span class="qa-q">', r.content.decode())


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
