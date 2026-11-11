"""Static file URLs that change when the file does (see STORAGES in settings.py)."""

import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    """`/media/static/js/chat.js?v=1794403868`: the browser's cached copy goes stale the
    moment the file is saved. Looked up per URL — a stat per asset per page, which is
    nothing on a local app and saves remembering a hard reload after every edit."""

    def url(self, name):
        url = super().url(name)
        path = finders.find(name) if name else None
        return f"{url}?v={int(os.path.getmtime(path))}" if path else url
