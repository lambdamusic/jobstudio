"""
Copy this file to local_settings.py (gitignored) and adjust as needed.
"""

import os
import sys

import django

SECRET_KEY = "CHANGE-ME-generate-a-real-secret-key"

DJANGO_ROOT = os.path.dirname(os.path.realpath(django.__file__))

# settings.py lives in src/web/, so the repo root is TWO levels up.
# (Deviation from the init-django-static-site skill, which puts the project at src/ —
# here src/ already holds the pipeline scripts, so the Django project is namespaced
# under src/web/. See log/2026-09-07-django-frontend-plan.md §2.4.)
SITE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

# Where this user's data lives (jobs/, db.sqlite3, exports/, backups/). Defaults to
# SITE_ROOT, so this is currently the same directory. See src/config.py.
# NOTE: settings.py imports local_settings at its line 16, BEFORE src/ joins sys.path
# at line 27 — hence the explicit insert here.
sys.path.insert(0, os.path.join(SITE_ROOT, "src"))
import config  # noqa: E402
DATA_ROOT = str(config.data_root())

ENVIRONMENT = "local"

# stderr, not stdout — `manage.py dumpdata > file.json` redirects stdout, and a
# banner printed there corrupts the fixture.
print("Environment: %s" % ENVIRONMENT, file=sys.stderr)

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Static files — sourced from src/web/static, collected into collectstatic/ for local use
STATIC_URL = "/media/static/"
STATIC_ROOT = os.path.join(SITE_ROOT, "collectstatic")
STATICFILES_DIRS = (os.path.join(SITE_ROOT, "src", "web", "static"),)

# sqlite always — see the init-django-static-site skill's METHODOLOGY.md for why.
# Portability comes from `tools/db-dump` (JSON fixtures in backups/django/),
# not from committing this file — db.sqlite3 stays gitignored.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(DATA_ROOT, "db.sqlite3"),
    }
}
