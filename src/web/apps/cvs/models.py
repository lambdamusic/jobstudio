"""CV models — the master CVs in jobs/cv/base/."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property


class BaseCv(models.Model):
    """A master CV in jobs/cv/base/ — chronological and functional, tailored per
    application on request (never stored as a pre-generated library)."""

    LABELS = {
        "cv_chronological": ("Chronological CV", 0),
        "cv_functional": ("Functional CV", 1),
    }

    slug = models.SlugField(max_length=100, unique=True)
    label = models.CharField(max_length=120)
    path = models.CharField(max_length=500, unique=True, help_text="Relative to the repo root")
    is_functional = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "slug"]
        verbose_name = "base CV"
        verbose_name_plural = "base CVs"

    def __str__(self):
        return self.label

    @property
    def full_path(self) -> Path:
        return Path(settings.DATA_ROOT) / self.path

    @cached_property
    def body_md(self) -> str:
        path = self.full_path
        return path.read_text() if path.is_file() else ""

    @cached_property
    def stats(self) -> dict:
        """What a master CV is, at a glance — for the cards on /cvs/.

        Read off the file rather than stored, because the file is the source of truth and a
        stored copy would be wrong the moment the CV is edited in an editor rather than
        through the app. Words rather than lines: a CV's length is what a reader feels, and
        markdown line counts mostly measure how it was wrapped.

        `sections` counts `##` headings — the competency clusters or the roles, depending
        on which base this is — which is the structural number worth seeing beside the
        length.
        """
        path = self.full_path
        if not path.is_file():
            return {"exists": False, "words": 0, "sections": 0, "modified": None}
        body = self.body_md
        return {
            "exists": True,
            "words": len(body.split()),
            "sections": sum(1 for line in body.splitlines() if line.startswith("## ")),
            "modified": dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc),
        }
