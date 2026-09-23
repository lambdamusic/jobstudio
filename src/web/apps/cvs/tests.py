"""CV page tests.

The tailored-CV list on /cvs/ has no database behind it — a tailored CV is a file in an
application folder, recognised by naming convention — so these run against the real
example-data/ tree, and will fail loudly if that convention drifts.
"""

from django.test import TestCase

from appfolder import cv_variant
from tracker.models import Application

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
