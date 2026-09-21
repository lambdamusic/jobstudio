"""CV models — the master CVs in jobs/cv/base/."""

from __future__ import annotations

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
