from django.contrib import admin

from tracker.admin import _file_links

from .models import BaseCv


@admin.register(BaseCv)
class BaseCvAdmin(admin.ModelAdmin):
    list_display = ("label", "slug", "is_functional", "open_links")
    readonly_fields = ("open_links",)

    @admin.display(description="file")
    def open_links(self, obj):
        return _file_links(obj.path)
