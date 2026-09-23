from django.conf import settings
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = f"{settings.APP_NAME} — admin"
admin.site.site_title = "jobstudio"
admin.site.index_title = "Tracker data"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cvs/", include("cvs.urls")),
    path("", include("tracker.urls")),
]
