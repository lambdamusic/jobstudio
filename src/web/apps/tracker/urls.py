from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.home, name="home"),
    # The bare list is the active set (applied + interviewing) — the day-to-day view.
    path("applications/", views.application_list, name="application_list"),
    # Real paths, not querystrings, so the static build can publish them.
    path("applications/all/", views.application_list, {"show_all": True}, name="application_all"),
    path("applications/active/", views.application_list, {"active": True}, name="application_active"),
    path("applications/status/<str:status>/", views.application_list, name="application_by_status"),
    path("applications/area/<slug:area>/", views.application_list, name="application_by_area"),
    path("applications/<int:num>/", views.application_detail, name="application_detail"),
    path("companies/", views.company_list, name="company_list"),
    path("companies/<slug:slug>/", views.company_detail, name="company_detail"),
    # No /areas/<slug>/ detail page — folded into /areas/'s tabs (2026-09-14). Link to
    # a specific area with /areas/#<slug> instead.
    path("areas/", views.area_list, name="area_list"),
    path("notes/", views.note_list, name="note_list"),
    path("notes/<slug:slug>/", views.note_detail, name="note_detail"),
    path("profile/", views.profile_view, name="profile"),
    # Bare path defaults to the latest report (day-to-day view); "all" is the dated
    # index, same "default-active vs. /all/" split as /applications/.
    path("scans/", views.scan_detail, name="scan_latest"),
    path("scans/all/", views.scan_list, name="scan_list"),
    # <str:> not <slug:> — some scan filenames carry a version suffix with a dot
    # (2026-07-10-portal-scan-v0.0.md).
    path("scans/<str:slug>/", views.scan_detail, name="scan_detail"),
    # Local-only; not reachable from the published mirror.
    path("actions/reveal/<int:num>/", views.reveal_folder, name="reveal_folder"),
    path("actions/create-folder/<int:num>/", views.create_folder, name="create_folder"),
    path("actions/set-status/<int:num>/<slug:status>/", views.set_status, name="set_status"),
    path("actions/reveal-company/<slug:slug>/", views.reveal_company_notes, name="reveal_company_notes"),
]
