"""CV page tests.

The tailored-CV list on /cvs/ has no database behind it — a tailored CV is a file in an
application folder, recognised by naming convention — so these run against the real
example-data/ tree, and will fail loudly if that convention drifts.
"""

from django.test import TestCase

from appfolder import cv_variant
from tracker.models import Application

from .models import BaseCv as BaseCvModel
from .views import tailored_cvs

FIXTURE = ["dump.json"]


class CvVariantTests(TestCase):
    """Pure filename logic — no fixture, no folder on disk."""

    def test_reads_the_area_slug_out_of_a_tailored_cv_name(self):
        self.assertEqual(
            cv_variant("004-incident-io-alex-rivera-cv-ai-knowledge-work-2026-06-23.md"),
            "ai-knowledge-work")

    def test_reads_the_target_out_of_the_old_naming(self):
        self.assertEqual(cv_variant("2026-06-07_cv_data_platform.md"), "data_platform")

    def test_matches_the_last_cv_not_the_first(self):
        """A company slug can contain 'cv-' (CV-Library is a real UK employer). Matching
        the leftmost occurrence would label every CV of theirs with the rest of the
        company's own name."""
        self.assertEqual(
            cv_variant("012-cv-library-alex-rivera-cv-data-platform-2026-09-15.md"),
            "data-platform")

    def test_no_variant_in_the_name_is_empty_not_a_guess(self):
        self.assertEqual(cv_variant("001-foo-alex-rivera-cv-2026-09-08.md"), "")


class TailoredCvListTests(TestCase):
    fixtures = FIXTURE

    def test_lists_tailored_cvs_but_not_the_untailored_base_copies(self):
        rows = tailored_cvs()
        self.assertTrue(rows, "example-data has at least one tailored CV")
        names = [r["name"] for r in rows]
        self.assertNotIn("cv_functional.md", names)
        self.assertNotIn("cv_chronological.md", names)

    def test_every_row_names_the_application_it_belongs_to(self):
        for row in tailored_cvs():
            with self.subTest(name=row["name"]):
                self.assertIsInstance(row["app"], Application)
                self.assertTrue(row["app"].company_name)

    def test_newest_first(self):
        dates = [r["date"] for r in tailored_cvs() if r["date"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_page_renders_each_cv_linked_to_its_application_cv_tab(self):
        r = self.client.get("/cvs/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        for row in tailored_cvs():
            with self.subTest(name=row["name"]):
                self.assertIn(f'/applications/{row["app"].num}/#cv', html)
                self.assertIn(row["name"], html)


class BaseCvParseTests(TestCase):
    """The shipped example CVs must actually parse.

    `render.py`'s parsers are hand-written regexes that discard what they cannot
    match, so a CV written to the wrong convention yields an *empty* CV rather
    than an error — and the renderer then produces a well-formed document with no
    work history in it. Both shipped examples were in that state until
    2026-09-29 (see log/2026-09-29-second-machine-findings.md): the functional
    one lost every role and date, the chronological one lost its entire history,
    and nothing caught it because no test read the parsed output and the smoke
    test asserted only a byte count.

    These assert content, not shape — and they run against `example-data/`, which
    is the file a new user copies and an agent reads to infer house style.
    """

    def _base(self, name):
        from django.conf import settings
        from pathlib import Path
        return Path(settings.SITE_ROOT) / "example-data" / "jobs" / "cv" / "base" / name

    def test_functional_example_parses_its_roles_and_dates(self):
        import render
        data = render.parse_functional(self._base("cv_functional.md"))
        self.assertTrue(data["career"], "no employers parsed")
        roles = [r for e in data["career"] for r in e["roles"]]
        self.assertTrue(roles, "employers parsed but every role line was dropped")
        titles = [r["role"] for r in roles]
        self.assertIn("Senior Data Platform Engineer", titles)
        self.assertTrue(any(r["dates"] for r in roles), "no role carries dates")

    def test_chronological_example_parses_its_experience(self):
        import render
        data = render.parse_variant(self._base("cv_chronological.md"))
        self.assertTrue(data["jobs"], "'## Experience' parsed to nothing")
        self.assertEqual(data["current_role"], "Senior Data Platform Engineer")
        self.assertTrue(data["jobs"][0]["bullets"], "newest role has no bullets")
        self.assertTrue(data["jobs"][0]["meta"], "newest role has no dates")
        self.assertIsNotNone(data["early_career"], "early-career block not recognised")

    def test_both_examples_parse_with_no_warnings(self):
        """The guard against the examples drifting back out of contract."""
        import render
        for name, mode in [("cv_functional.md", "functional"),
                           ("cv_chronological.md", "chronological")]:
            with self.subTest(cv=name):
                _, _, warnings = render.parse_check(self._base(name), mode)
                self.assertEqual(warnings, [])

    def test_rendered_html_carries_the_job_titles(self):
        """A rendered file existing is not evidence it has content in it."""
        import render
        html = render.render_functional(render.parse_functional(self._base("cv_functional.md")))
        self.assertIn("Senior Data Platform Engineer", html)
        self.assertIn("Kestrel Financial", html)
        html = render.render_html(render.parse_variant(self._base("cv_chronological.md")))
        self.assertIn("Senior Data Platform Engineer", html)
        self.assertIn("Meridian Retail Group", html)


class ParseCheckTests(TestCase):
    """`parse_check` must name the two mistakes that actually happened."""

    def _write(self, body):
        import tempfile
        from pathlib import Path
        p = Path(tempfile.mkdtemp()) / "cv.md"
        p.write_text(body)
        return p

    def test_flags_a_chronological_cv_using_the_functional_section_name(self):
        import render
        p = self._write(
            "# Test Person\n\n- **Email:** t@example.com\n\n"
            "## Career History\n\n### [Acme](https://example.com)\n\n"
            "**Engineer** | 2020 – 2024 | Bristol, UK\n\n- Did the work.\n")
        _, _, warnings = render.parse_check(p, "chronological")
        self.assertTrue(any("not read by the chronological parser" in w for w in warnings))
        self.assertTrue(any("Career History" in w for w in warnings))

    def test_flags_functional_roles_written_as_bold_pipe_lines(self):
        import render
        p = self._write(
            "# Test Person\n\n- **Email:** t@example.com\n\n"
            "## Career History\n\n### [Acme](https://example.com)\n\n"
            "**Engineer** | 2020 – 2024 | Bristol, UK\n")
        data, _, warnings = render.parse_check(p, "functional")
        self.assertTrue(data["career"], "the employer should still parse")
        self.assertTrue(any("no roles" in w for w in warnings),
                        f"expected a dropped-roles warning, got {warnings}")

    def test_a_section_present_but_empty_is_reported(self):
        import render
        p = self._write(
            "# Test Person\n\n- **Email:** t@example.com\n\n"
            "## Experience\n\n## Education\n\n**BSc**  \nSomewhere | 2015\n")
        _, _, warnings = render.parse_check(p, "chronological")
        self.assertTrue(any("'## Experience' is present but parsed to nothing" in w
                            for w in warnings))


class DerivedRowRefreshTests(TestCase):
    """A base CV written after `init` must show up without a manual import.

    `/cvs/` lists `BaseCv` rows, and `init` creates them by running `import_jobs`
    at the end of its own run — before on-ramp B (start from a CV) has written
    any base CV. On 2026-09-29 that left a first-time install with a correctly
    imported CV on disk and an empty CV page, with nothing anywhere saying why.
    """

    def setUp(self):
        import tempfile
        from pathlib import Path
        from tracker import derived
        derived._seen.clear()          # process-local cache, not test state
        # A whole data root, not just a CV dir: import_jobs stores paths relative
        # to DATA_ROOT, so a CV living outside it cannot be imported at all.
        self.data_root = Path(tempfile.mkdtemp())
        self.cv_dir = self.data_root / "jobs" / "cv"
        (self.cv_dir / "base").mkdir(parents=True)

    def _write_base_cv(self, name="cv_functional.md"):
        (self.cv_dir / "base" / name).write_text(
            "# Test Person\n\n- **Email:** t@example.com\n\n"
            "## Career History\n\n### Acme\n*2020 – 2024*\n\n- Engineer — *2020 – 2024*\n")

    def test_a_cv_written_after_init_appears_without_a_manual_import(self):
        from django.test import override_settings
        with override_settings(DATA_ROOT=str(self.data_root), CV_DIR=str(self.cv_dir)):
            # As init leaves it on on-ramp B: import has run, no base CVs existed.
            self.client.get("/cvs/")
            self.assertEqual(BaseCvModel.objects.count(), 0)

            # cv --import writes the file afterwards, outside any Django process.
            self._write_base_cv()

            r = self.client.get("/cvs/")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(
                BaseCvModel.objects.count(), 1,
                "the CV page did not pick up a base CV written after init")
            self.assertContains(r, "cv_functional")

    def test_a_removed_cv_stops_being_listed(self):
        from django.test import override_settings
        with override_settings(DATA_ROOT=str(self.data_root), CV_DIR=str(self.cv_dir)):
            self._write_base_cv()
            self.client.get("/cvs/")
            self.assertEqual(BaseCvModel.objects.count(), 1)

            (self.cv_dir / "base" / "cv_functional.md").unlink()
            self.client.get("/cvs/")
            self.assertEqual(BaseCvModel.objects.count(), 0)

    def test_an_unreadable_source_does_not_break_the_page(self):
        """Best-effort by design: the page renders the rows it has."""
        from django.test import override_settings
        with override_settings(DATA_ROOT=str(self.data_root),
                               CV_DIR="/nonexistent/path/for/this/test"):
            r = self.client.get("/cvs/")
            self.assertEqual(r.status_code, 200)


class HeaderLinkTests(TestCase):
    """Header links are optional; a way to be contacted is not.

    The format, the examples and the import questions all used to treat LinkedIn,
    a website, GitHub and Scholar as the normal case, so a CV with none of them
    read as incomplete rather than as a valid choice (TODO #47). The parsers and
    all three renderers were already generic — `_parse_contact` reads any
    `**Label:** value` line — so what needed fixing was what the system says, and
    which absence it actually cares about.
    """

    HEADER = "# Test Person\n\n{lines}\n\n---\n\n## Summary\n\nA summary.\n"

    def _write(self, lines):
        import tempfile
        from pathlib import Path
        p = Path(tempfile.mkdtemp()) / "cv.md"
        p.write_text(self.HEADER.format(lines=lines))
        return p

    def test_a_cv_with_no_links_is_not_a_finding(self):
        import render
        p = self._write("- **Location:** Bristol, UK  \n- **Email:** t@example.com  ")
        data, _, warnings = render.parse_check(p, "functional")
        self.assertEqual(len(data["contact"]), 2)
        self.assertEqual(warnings, [], "absence of header links should not warn")

    def test_an_email_alone_is_enough(self):
        import render
        p = self._write("- **Email:** t@example.com  ")
        _, _, warnings = render.parse_check(p, "functional")
        self.assertEqual(warnings, [])

    def test_a_link_alone_is_enough(self):
        import render
        p = self._write("- **LinkedIn:** [tp](https://example.com/tp)  ")
        _, _, warnings = render.parse_check(p, "functional")
        self.assertEqual(warnings, [])

    def test_no_contact_route_at_all_is_flagged(self):
        import render
        p = self._write("- **Location:** Bristol, UK  ")
        _, _, warnings = render.parse_check(p, "functional")
        self.assertTrue(any("no way to contact" in w for w in warnings), warnings)

    def test_unlisted_labels_are_read_too(self):
        """The labels are not a fixed set — a CV can carry whatever it needs."""
        import render
        p = self._write("- **ORCID:** [0000](https://orcid.org/0000)  \n"
                        "- **Phone:** +44 7700 900000  ")
        data, _, warnings = render.parse_check(p, "functional")
        self.assertEqual([c["label"] for c in data["contact"]], ["ORCID", "Phone"])
        self.assertEqual(warnings, [])

    def test_a_link_free_cv_renders_without_a_dangling_separator(self):
        import render
        p = self._write("- **Location:** Bristol, UK  \n- **Email:** t@example.com  ")
        html = render._r_contact_inline(render.parse_functional(p)["contact"])
        self.assertIn("Bristol, UK", html)
        self.assertIn("t@example.com", html)
        self.assertFalse(html.strip().endswith("·"), f"trailing separator: {html!r}")
        self.assertFalse(html.strip().startswith("·"), f"leading separator: {html!r}")
