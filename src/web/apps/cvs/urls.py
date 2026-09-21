from django.urls import path

from . import views

app_name = "cvs"

urlpatterns = [
    path("", views.cv_list, name="list"),
    path("base/<slug:slug>/", views.base_cv_detail, name="base_detail"),
]
