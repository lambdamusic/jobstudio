"""Tracker models.

**This database is the source of truth** for applications and companies (Phase 6 of
log/2026-09-07-django-frontend-plan.md). jobs/applications.md and jobs/companies.md are
gone; the admin is the editing surface and the committed fixture in example-data/ is the portable record.

Still derived from files on disk, and refreshed by `manage.py import_jobs`: Area (from
jobs/targets/*.yaml, which the CV generator reads directly), BaseCv and Scan.

Long-form prose — job.md, notes.md, company notes — is NOT copied into the database. Only
its path is stored, and it is rendered from disk at request time. CV snapshots and cover
letters are not stored at all: both are scanned from the application folder by naming
convention (`is_cv_filename` / `is_cover_letter_filename`) at request time.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.db import models
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property

# Reuse the pipeline's single source of truth for status handling rather than retyping it.
from appfolder import (
    COMPANY_APPLIED_TRIGGER_STATUSES,
    COMPANY_STATUSES,
    STATUS_SORT_ORDER,
    cv_variant,
    exported_file,
    is_cover_letter_filename,
    is_interview_filename,
    is_cv_filename,
    is_tailored_cv,
    slug as slugify_name,
)

STATUS_CHOICES = [(s, s.title()) for s in STATUS_SORT_ORDER]
# "Active" = applications actually in play — submitted and not yet closed out. `reviewing`
# (a placeholder still being sized up before applying) is deliberately excluded; it lives
# behind its own /applications/status/reviewing/ view and sidebar link instead.
ACTIVE_STATUSES = ["applied", "interviewing"]
FIT_LEVEL_CHOICES = [
    ("strong", "Strong match"),
    ("moderate", "Moderate match"),
    ("stretch", "Stretch"),
    ("weak", "Weak match"),
]
CV_BASE_CHOICES = [
    ("functional", "Functional"),
    ("chronological", "Chronological"),
]
# Two states only — watched, or applied to. Maintained by refresh_company_status()
# below, off Application save/delete signals.
COMPANY_STATUS_CHOICES = [(s, s.title()) for s in COMPANY_STATUSES]


def _read(path: Path | None) -> str:
    """Read a markdown file off disk, or return '' if it isn't there."""
    if path and path.is_file():
        return path.read_text()
    return ""


class Area(models.Model):
    """A target area — one jobs/targets/<slug>.yaml, optionally described in jobs/areas.md."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    heading = models.CharField(max_length=200, blank=True, help_text="Section heading in areas.md")
    fit = models.PositiveSmallIntegerField(default=0, help_text="Stars, 0-5")
    description = models.TextField(blank=True, help_text="From the target YAML")
    notes = models.TextField(blank=True, help_text="From areas.md")
    emphasis = models.JSONField(default=list, blank=True)
    key_terms = models.JSONField(default=list, blank=True)
    expand_sections = models.JSONField(default=list, blank=True)
    condense_sections = models.JSONField(default=list, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "slug"]

    def __str__(self):
        return self.name or self.slug

    @property
    def yaml_path(self) -> Path:
        return Path(settings.TARGETS_DIR) / f"{self.slug}.yaml"

    @property
    def abbr(self) -> str:
        """Two letters for the pill on application tables, derived from the slug —
        `data-platform` → DP. Until 2026-09-21 a lookup table overrode five specific
        slugs with hand-picked pairs; it was one person's area taxonomy sitting in
        shared code, and it did nothing for anyone else's slugs. Areas and categories
        are defined by whoever uses the toolkit — in `jobs/targets/*.yaml` and the
        tracker — so their labels are derived here rather than enumerated."""
        return "".join(w[0] for w in self.slug.split("-")[:2]).upper()


class Category(models.Model):
    """A '##' section in companies.md."""

    name = models.CharField(max_length=200, unique=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Company(models.Model):
    """A row in companies.md."""

    num = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    url = models.URLField(blank=True)
    role_target = models.CharField(max_length=200, blank=True)
    fit = models.PositiveSmallIntegerField(default=0, help_text="Stars, 0-5")
    status = models.CharField(max_length=20, choices=COMPANY_STATUS_CHOICES, default="watching",
                              help_text="Derived automatically: 'applied' if the company has an "
                                        "application actually submitted (applied/interviewing/"
                                        "rejected), else 'watching'")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="companies")
    notes = models.TextField(blank=True)
    date_added = models.DateField(null=True, blank=True,
                                  help_text="When the company was added to the tracker. Blank "
                                            "for rows that predate this field — only new "
                                            "additions (via jobsdb.py add-company) set it.")

    class Meta:
        ordering = ["num"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"/companies/{self.slug}/"

    @property
    def stars(self) -> str:
        return "★" * self.fit + "☆" * (5 - self.fit)

    @cached_property
    def scan_coverage(self) -> dict:
        """Whether `scan` picks this company up automatically, and on what — or the
        specific reason it doesn't. See src/scan_sources.py.

        Calls the same function the scanner acts on rather than re-deriving it, so the
        column cannot quietly disagree with the report. Config plus a regex, no network.
        """
        import scan_sources
        return scan_sources.coverage(self.name, self.url)

    @property
    def notes_path(self) -> Path | None:
        """jobs/companies/<slug>.md — long-form research, rendered at request time.

        Derived from the slug rather than stored, because unlike an application folder
        the location is deterministic. Mirrors the applications convention:
        companies.md is the index, companies/ holds the prose. Absent file = no notes.
        """
        path = Path(settings.JOBS_DIR) / "companies" / f"{self.slug}.md"
        return path if path.is_file() else None

    @cached_property
    def notes_md(self) -> str:
        return _read(self.notes_path)


class Application(models.Model):
    """A row in applications.md, plus its detail block and jobs/applications/NNN-*/ folder."""

    num = models.PositiveIntegerField(unique=True)
    date = models.DateField(null=True, blank=True)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="applications",
                                help_text="Matched to companies.md where possible")
    company_name = models.CharField(max_length=200, help_text="As written in applications.md")
    role = models.CharField(max_length=300)
    job_url = models.URLField(max_length=1000, blank=True)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="applications")
    cv_base = models.CharField(max_length=20, choices=CV_BASE_CHOICES, default="functional",
                               help_text="Which base CV this application tailors from")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="saved")
    next_action = models.TextField(blank=True)
    summary = models.TextField(blank=True,
                               help_text="One-line scannable description, shown in list views")
    notes = models.TextField(blank=True,
                             help_text="The full record — shown on the detail page")
    contact = models.CharField(max_length=300, blank=True)
    # Fit summary — a scannable pros/cons/unknowns read shown as coloured boxes at the
    # top of the Record tab. Structured, hand-maintained data (unlike the long-form gap
    # analysis in notes.md, which stays on disk); one bullet per line.
    fit_level = models.CharField(
        max_length=10, blank=True, choices=FIT_LEVEL_CHOICES,
        help_text="Overall alignment — drives the banner colour")
    fit_pros = models.TextField(blank=True, help_text="One point per line")
    fit_cons = models.TextField(blank=True, help_text="One point per line")
    fit_unknowns = models.TextField(blank=True, help_text="One point per line")
    folder = models.CharField(max_length=500, blank=True,
                              help_text="Path relative to the repo root, or '' if no folder yet")
    status_order = models.PositiveSmallIntegerField(
        default=len(STATUS_SORT_ORDER),
        help_text="Rank of `status` in STATUS_SORT_ORDER — lets the DB sort the way the TUI does",
    )

    class Meta:
        # Same default order as the dashboard TUI: by status, then by number.
        ordering = ["status_order", "num"]

    def __str__(self):
        return f"#{self.num} {self.company_name} — {self.role}"

    def get_absolute_url(self):
        """Gives the admin change form its "View on site" button."""
        return f"/applications/{self.num}/"

    # -- fit summary -----------------------------------------------------
    @staticmethod
    def _lines(text: str) -> list[str]:
        return [ln.strip(" -*\t") for ln in (text or "").splitlines() if ln.strip(" -*\t")]

    @cached_property
    def fit_summary(self) -> dict:
        return {
            "level": self.fit_level,
            "level_label": dict(FIT_LEVEL_CHOICES).get(self.fit_level, ""),
            "pros": self._lines(self.fit_pros),
            "cons": self._lines(self.fit_cons),
            "unknowns": self._lines(self.fit_unknowns),
        }

    @property
    def has_fit_summary(self) -> bool:
        s = self.fit_summary
        return bool(s["level"] or s["pros"] or s["cons"] or s["unknowns"])

    # -- status helpers ----------------------------------------------------
    @staticmethod
    def rank_for(status: str) -> int:
        try:
            return STATUS_SORT_ORDER.index(status)
        except ValueError:
            return len(STATUS_SORT_ORDER)

    def save(self, *args, **kwargs):
        self.status_order = self.rank_for(self.status)
        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"status_order"}
        super().save(*args, **kwargs)

    # -- on-disk markdown, read at request time ----------------------------
    @property
    def folder_path(self) -> Path | None:
        if not self.folder:
            return None
        # `folder` is stored relative to the data root by appfolder.ensure_folder,
        # so it must be rejoined against the same root, not SITE_ROOT.
        path = Path(settings.DATA_ROOT) / self.folder
        return path if path.is_dir() else None

    def _folder_file(self, name: str) -> Path | None:
        folder = self.folder_path
        if folder is None:
            return None
        path = folder / name
        return path if path.is_file() else None

    @cached_property
    def job_md(self) -> str:
        return _read(self._folder_file("job.md"))

    @cached_property
    def notes_md(self) -> str:
        return _read(self._folder_file("notes.md"))

    @property
    def cv_snapshots(self) -> list[Path]:
        folder = self.folder_path
        if folder is None:
            return []
        return sorted(p for p in folder.glob("*.md") if is_cv_filename(p.name))

    @property
    def cv_files(self) -> list[dict]:
        """CV snapshots for the CV tab, newest first, with their markdown body and the
        .docx rendered from it, if one has been. The export lives in the folder's
        `export/` subfolder, or beside the markdown in folders written before
        2026-09-24 — `exported_file()` accepts both."""
        out = []
        for path in reversed(self.cv_snapshots):
            out.append({
                "name": path.name,
                "path": path,
                "body_md": _read(path),
                "docx": exported_file(path),
            })
        return out

    @property
    def tailored_cvs(self) -> list[dict]:
        """The CVs actually written for this role, newest first — `cv_snapshots` minus
        the untailored base copy `ensure_folder()` scaffolds every folder with.

        Feeds the all-CVs list on /cvs/, so unlike `cv_files` it carries a label and a
        date rather than the markdown body: the body is rendered on this application's
        own CV tab, which is where the list links to.
        """
        from .parsers import parse_date

        out = []
        for path in self.cv_snapshots:
            if not is_tailored_cv(path.name):
                continue
            variant = cv_variant(path.name)
            out.append({
                "name": path.name,
                "path": path,
                "date": parse_date(path.name),
                "label": variant.replace("_", " ").replace("-", " ") or "Tailored CV",
            })
        out.sort(key=lambda c: (c["date"].toordinal() if c["date"] else 0, c["name"]),
                 reverse=True)
        return out

    @property
    def cover_letter_files(self) -> list[dict]:
        """Cover letters for the Cover letters tab, newest first. Scanned from the
        application folder by naming convention (like cv_files) — no database row."""
        folder = self.folder_path
        if folder is None:
            return []
        from .parsers import find_cover_letters

        out = []
        for letter in find_cover_letters(folder):
            path = letter["path"]
            body = _read(path)
            if not body.strip():
                continue  # an empty stub from ensure_folder() — not a real letter yet
            out.append({
                "name": path.name,
                "path": path,
                "label": letter["label"],
                "date": letter["date"],
                "body_md": body,
                "docx_path": exported_file(path),
            })
        out.sort(key=lambda l: (l["date"].toordinal() if l["date"] else 0, l["label"]),
                 reverse=True)
        return out

    @property
    def interview_files(self) -> list[dict]:
        """Interview rounds for the Interviews tab, newest first — one file per round,
        scanned from the application folder by naming convention (like cover letters),
        with no database row.

        Files-only was a deliberate choice (2026-09-24): prose lives on disk, the tracker
        keeps status. A round gets a DB model the day scheduling or reminders need one.
        """
        folder = self.folder_path
        if folder is None:
            return []
        from .parsers import find_interviews

        out = []
        for round_ in find_interviews(folder):
            body = _read(round_["path"])
            if not body.strip():
                continue  # a scaffolded round that hasn't been written yet
            out.append({
                "name": round_["path"].name,
                "path": round_["path"],
                "label": round_["label"],
                "stage": round_["stage"],
                "date": round_["date"],
                "body_md": body,
            })
        out.sort(key=lambda r: (r["date"].toordinal() if r["date"] else 0, r["name"]),
                 reverse=True)

        # Anchor id for the index at the top of the tab. Stage + date reads as a URL
        # ("#round-hiring-manager-2026-09-24") where the filename stem would not; a
        # counter keeps it unique if a stage ever repeats on one day.
        seen: dict[str, int] = {}
        for round_ in out:
            base = f"round-{round_['stage'] or 'interview'}"
            if round_["date"]:
                base = f"{base}-{round_['date'].isoformat()}"
            seen[base] = seen.get(base, 0) + 1
            round_["anchor"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
        return out

    @property
    def extra_files(self) -> list[dict]:
        """Anything in the folder not already surfaced by another tab — job.md, notes.md,
        CV snapshots, cover letters, or interview rounds (any .docx export included). Markdown
        files render inline; anything else is listed with a local open link, so nothing
        saved into an application folder goes invisible on the page."""
        folder = self.folder_path
        if folder is None:
            return []

        # Paths, not bare names: a rendered .docx sits in `export/` rather than beside
        # its markdown (2026-09-24), so "already on another tab" is a question about a
        # location, and a name alone can no longer answer it.
        # Resolved, because `exported_file()` builds its answer from appfolder.APPS_DIR
        # while everything here is rooted at settings.DATA_ROOT — two spellings of the
        # same directory would compare unequal and let every export through.
        known: set[Path] = {(folder / "job.md").resolve(), (folder / "notes.md").resolve()}

        def claim(md: Path) -> None:
            known.add(md.resolve())
            docx = exported_file(md)
            if docx:
                known.add(docx.resolve())

        for p in self.cv_snapshots:
            claim(p)
        # Any cover-letter- or interview-named file belongs to its own tab, even a
        # still-empty one that tab chooses not to render — it must not leak in here.
        for p in folder.iterdir():
            if p.is_file() and (is_cover_letter_filename(p.name) or is_interview_filename(p.name)):
                claim(p)

        out = []
        for path in sorted(folder.rglob("*")):
            if path.is_dir() or path.name.startswith("."):
                continue
            rel = path.relative_to(folder)
            if path.resolve() in known:
                continue
            if path.suffix == ".md":
                out.append({"rel": str(rel), "name": path.name, "path": path,
                           "is_md": True, "body_md": _read(path)})
            else:
                out.append({"rel": str(rel), "name": path.name, "path": path,
                           "is_md": False,
                           "size_kb": max(1, path.stat().st_size // 1024)})

        # An id per file, so prose elsewhere in the folder can link a specific one —
        # `#file-<slug>`, resolved by tabs.js the same way a round anchor is. Without it
        # the only honest target is the tab, and a bare `<name>.md` link is a broken link
        # on the published site, where these render into the page rather than ship as
        # files.
        for f in out:
            f["anchor"] = "file-" + re.sub(r"[^a-z0-9]+", "-", f["rel"].lower()).strip("-")
        return out


class ApplicationStatusChange(models.Model):
    """One recorded status transition for an Application — powers the History tab.

    Written automatically by the post_save signal below (compares against the most
    recent row, if any); never created by hand. `changed_at` is a plain field rather
    than auto_now_add so the one-off backfill (2026-09-08, for applications that predate
    this model) can date each seed entry from Application.date instead of "now".
    """

    application = models.ForeignKey(Application, on_delete=models.CASCADE,
                                    related_name="status_changes")
    changed_at = models.DateTimeField(default=timezone.now)
    from_status = models.CharField(max_length=20, blank=True,
                                   help_text="Blank for the first recorded status")
    to_status = models.CharField(max_length=20)

    class Meta:
        ordering = ["-changed_at", "-pk"]

    def __str__(self):
        return f"#{self.application_id}: {self.from_status or '(logged)'} -> {self.to_status}"


class Scan(models.Model):
    """A portal-scan report in jobs/scans/."""

    date = models.DateField()
    path = models.CharField(max_length=500, unique=True, help_text="Relative to the repo root")
    label = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date", "path"]

    def __str__(self):
        return self.label or self.path

    @cached_property
    def body_md(self) -> str:
        return _read(Path(settings.DATA_ROOT) / self.path)


# ---------------------------------------------------------------------------
# Derived company status
# ---------------------------------------------------------------------------

def refresh_company_status(company: "Company | None") -> None:
    """A company is `applied` if it has an application that was actually submitted
    (`applied`, `interviewing`, or `rejected` — see COMPANY_APPLIED_TRIGGER_STATUSES),
    otherwise `watching`. A `saved`/`reviewing` placeholder row doesn't count, and neither
    does `closed` (deadline passed before applying) or `discarded` (dropped before
    applying) — see docs/workflow.md "Application statuses" for the definitions.

    Replaces appfolder.sync_company_status(), which maintained an equivalent rule by
    rewriting companies.md back when that file was the source of truth.
    """
    if company is None:
        return
    wanted = ("applied"
             if company.applications.filter(status__in=COMPANY_APPLIED_TRIGGER_STATUSES).exists()
             else "watching")
    # Compare against the database, not company.status — the caller may be holding an
    # instance loaded before an earlier signal updated the row, and a stale value here
    # silently skips the write.
    current = Company.objects.filter(pk=company.pk).values_list("status", flat=True).first()
    if current != wanted:
        Company.objects.filter(pk=company.pk).update(status=wanted)


@receiver(models.signals.post_save, sender=Application)
def _application_saved(sender, instance, **kwargs):
    refresh_company_status(instance.company)
    _log_status_change(instance)


def _log_status_change(application: Application) -> None:
    """Append an ApplicationStatusChange row if `status` differs from the last one
    recorded — including the very first save, where "last" is None. Compares against the
    log itself (rather than a pre_save snapshot) so it works the same whether the change
    came from the admin, a script, or a fixture load."""
    last = application.status_changes.first()
    if last is not None and last.to_status == application.status:
        return
    ApplicationStatusChange.objects.create(
        application=application,
        from_status=last.to_status if last else "",
        to_status=application.status,
    )


@receiver(models.signals.post_delete, sender=Application)
def _application_deleted(sender, instance, **kwargs):
    refresh_company_status(instance.company)
