from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Job search — admin"
admin.site.site_title = "jobstudio"
admin.site.index_title = "Tracker data"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cvs/", include("cvs.urls")),
    path("", include("tracker.urls")),
]
