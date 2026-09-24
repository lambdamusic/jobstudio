"""
Django settings — job-search front end.

Pattern: Django-as-static-site-generator (see the init-django-static-site skill's
reference/METHODOLOGY.md). Django is an authoring/templating tool only; the published
artifact is a wget mirror of the local dev server, rsynced into site/ and pushed to surge.

Layout deviation from the skill: the project lives at src/web/, not src/, because src/
already holds the pipeline scripts (render.py, appfolder.py, ...). src/ itself is
sys.path-appended so this app can reuse those parsers instead of duplicating them.
"""

import os, sys

# ---------------------------------------------------------------------------
# Tests run against the example data root, never against a real job search.
#
# This has to happen BEFORE local_settings is imported, because that is where
# config.data_root() is first called — and appfolder.py and render.py likewise read
# config.data_root() at module level. Setting $JOBSTUDIO_DATA here is the one place
# that reaches all of them, so the database rows (from the fixture) and the files on
# disk describe the same person.
#
# Learned the hard way: pointing FIXTURE_DIRS at the synthetic dump on its own leaves
# a suite where the database says one thing and the data root says another — 42 of 78
# tests failed that way, against 9 when both move together.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"
if RUNNING_TESTS:
    os.environ["JOBSTUDIO_DATA"] = os.path.join(_REPO_ROOT, "example-data")

try:
    from local_settings import *
except ImportError:
    print("Cannot find the local settings module — copy local_settings_example.py to local_settings.py")
    raise

# src/web/libs and src/web/apps are sys.path-appended (not installed packages) so apps
# can import each other and anything vendored into libs/ by bare name.
sys.path.append(os.path.join(SITE_ROOT, "src", "web", "libs"))
sys.path.append(os.path.join(SITE_ROOT, "src", "web", "apps"))
# src/ itself, so the Django code can `import appfolder` / `import render` and reuse the
# existing markdown parsers and CV renderer.
sys.path.append(os.path.join(SITE_ROOT, "src"))

DEBUG = ENVIRONMENT != "production"

INSTALLED_APPS = [
    "django_extensions",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # project apps
    "tracker",
    "cvs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(SITE_ROOT, "src", "web", "templates-global")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tracker.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tests load dump.json — since Phase 6 the database is the source of truth, so the
# committed fixture is what test data comes from. That fixture is the SYNTHETIC one in
# example-data/, rebuilt by tools/build-example-fixture: repo-anchored on purpose, so a
# fresh clone can run the suite without anyone's personal data root existing.
FIXTURE_DIRS = [os.path.join(SITE_ROOT, "example-data", "backups", "django")]

# The app's display name, in one place — it was "Job search" written out in 15 spots
# across 13 templates plus the admin header, so renaming it meant a find-and-replace.
# Two words with a space is the DISPLAY form only; the package, repo and command stay
# `jobstudio`, unhyphenated (plan §2e).
APP_NAME = "Job Studio"

# ---------------------------------------------------------------------------
# Project-specific paths — the markdown/data tree this app reads from.
# ---------------------------------------------------------------------------
JOBS_DIR = os.path.join(DATA_ROOT, "jobs")
AREAS_MD = os.path.join(JOBS_DIR, "areas.md")
COMPANY_NOTES_DIR = os.path.join(JOBS_DIR, "companies")
TARGETS_DIR = os.path.join(JOBS_DIR, "targets")
APPLICATIONS_DIR = os.path.join(JOBS_DIR, "applications")
CV_DIR = os.path.join(JOBS_DIR, "cv")
SCANS_DIR = os.path.join(JOBS_DIR, "scans")
NOTES_DIR = os.path.join(JOBS_DIR, "notes")
PROFILE_DIR = os.path.join(JOBS_DIR, "profile")
