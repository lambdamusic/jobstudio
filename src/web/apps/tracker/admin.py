"""Admin — the editing surface for the tracker.

Since Phase 6 this is authoritative: applications and companies live here, not in
markdown. Edits stick. Back them up with `tools/db-dump`.
"""

from pathlib import Path

import config

from django.conf import settings
from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html, format_html_join

from .models import Application, ApplicationStatusChange, Area, Category, Company, Scan

STATUS_COLOURS = {
    "applied": "#1a7f37",
    "interviewing": "#8250df",
    "reviewing": "#0969da",
    "saved": "#57606a",
    "discarded": "#8c959f",
    "closed": "#953800",
    "rejected": "#cf222e",
}


def _abs(rel_path: str) -> Path:
    # Stored paths are relative to the data root (see src/config.py).
    return Path(settings.DATA_ROOT) / rel_path


def _file_links(rel_path: str, label: str = ""):
    """Open-in-Finder and open-in-VSCode links for a path relative to the repo root."""
    if not rel_path:
        return "—"
    target = _abs(rel_path)
    return format_html(
        '<code>{}</code><br>'
        '<a href="file://{}">Finder</a> &middot; '
        '<a href="{}{}">VS Code</a>',
        label or rel_path, target,
        config.setting("editor_url_scheme", "vscode://file/"), target,
    )


class ApplicationStatusChangeInline(admin.TabularInline):
    """Read-only — rows are written by the post_save signal in models.py, never by hand."""
    model = ApplicationStatusChange
    extra = 0
    fields = ("changed_at", "from_status", "to_status")
    readonly_fields = fields
    can_delete = False
    ordering = ("-changed_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("num", "company_name", "role", "area_abbr", "status_badge",
                    "status", "next_action", "date")
    # status and next_action are editable straight from the list — this is the workflow
    # that replaced the TUI's inline status cycling.
    list_display_links = ("num", "company_name")
    list_editable = ("status", "next_action")
    list_filter = ("status", "area", "cv_base", "company__category", "date")
    search_fields = ("company_name", "role", "notes", "next_action", "detail_md")
    date_hierarchy = "date"
    list_per_page = 50
    inlines = [ApplicationStatusChangeInline]
    autocomplete_fields = ("company",)
    readonly_fields = ("status_order", "folder_links", "job_md_preview", "notes_md_preview")
    fieldsets = (
        (None, {"fields": ("num", "date", "company_name", "company", "role", "job_url",
                           "area", "cv_base", "status", "next_action")}),
        ("Notes", {"fields": ("summary", "notes", "contact")}),
        ("Fit summary", {
            "description": "Scannable pros/cons/unknowns shown as coloured boxes on the "
                           "Record tab. One point per line.",
            "fields": ("fit_level", "fit_pros", "fit_cons", "fit_unknowns"),
        }),
        ("On disk", {"fields": ("folder", "folder_links", "job_md_preview", "notes_md_preview")}),
        ("Internal", {"classes": ("collapse",), "fields": ("status_order",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("company", "area")

    @admin.display(description="area", ordering="area__slug")
    def area_abbr(self, obj):
        return obj.area.abbr if obj.area else "—"

    @admin.display(description="", ordering="status_order")
    def status_badge(self, obj):
        return format_html(
            '<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            'background:{}"></span>',
            STATUS_COLOURS.get(obj.status, "#999"),
        )

    @admin.display(description="folder")
    def folder_links(self, obj):
        return _file_links(obj.folder)

    @admin.display(description="job.md")
    def job_md_preview(self, obj):
        return self._preview(obj.job_md)

    @admin.display(description="notes.md")
    def notes_md_preview(self, obj):
        return self._preview(obj.notes_md)

    @staticmethod
    def _preview(text: str):
        if not text:
            return "—"
        head = text[:600] + ("…" if len(text) > 600 else "")
        return format_html('<pre style="white-space:pre-wrap;max-width:60em;'
                           'font-size:12px;margin:0">{}</pre>', head)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("num", "name", "stars", "role_target", "status", "category",
                    "application_count", "link")
    list_display_links = ("num", "name")
    list_filter = ("status", "category", "fit")
    search_fields = ("name", "role_target", "notes")
    list_per_page = 60
    ordering = ("-fit", "num")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("category").annotate(
            _applications=Count("applications"))

    @admin.display(description="fit", ordering="fit")
    def stars(self, obj):
        return obj.stars

    @admin.display(description="apps", ordering="_applications")
    def application_count(self, obj):
        return obj._applications or ""

    @admin.display(description="site")
    def link(self, obj):
        if not obj.url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">↗</a>', obj.url)


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "fit", "application_count")
    search_fields = ("slug", "name", "description", "notes")
    readonly_fields = ("emphasis_list", "key_terms_list", "emphasis", "key_terms",
                       "expand_sections", "condense_sections")
    fieldsets = (
        (None, {"fields": ("slug", "name", "heading", "fit", "order")}),
        ("From the target YAML", {"fields": ("description", "emphasis_list", "key_terms_list")}),
        ("Raw", {"classes": ("collapse",),
                 "fields": ("emphasis", "key_terms", "expand_sections", "condense_sections")}),
        ("From areas.md", {"fields": ("notes",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _applications=Count("applications", distinct=True),
        )

    @admin.display(description="apps", ordering="_applications")
    def application_count(self, obj):
        return obj._applications

    @admin.display(description="emphasis")
    def emphasis_list(self, obj):
        return self._bullets(obj.emphasis)

    @admin.display(description="key terms")
    def key_terms_list(self, obj):
        return self._bullets(obj.key_terms)

    @staticmethod
    def _bullets(items):
        if not items:
            return "—"
        return format_html("<ul style='margin:0;padding-left:1.1em'>{}</ul>",
                           format_html_join("", "<li>{}</li>", ((i,) for i in items)))


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "company_count")
    ordering = ("order",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_companies=Count("companies"))

    @admin.display(description="companies", ordering="_companies")
    def company_count(self, obj):
        return obj._companies


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("date", "label", "open_links")
    ordering = ("-date",)

    @admin.display(description="file")
    def open_links(self, obj):
        return _file_links(obj.path)
