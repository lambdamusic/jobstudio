from django.shortcuts import get_object_or_404, render

from .models import BaseCv


def cv_list(request):
    return render(request, "cvs/cv_list.html", {
        "page": "cvs",
        "base_cvs": BaseCv.objects.all(),
    })


def base_cv_detail(request, slug):
    """A master CV from jobs/cv/base/ — chronological or functional."""
    cv = get_object_or_404(BaseCv, slug=slug)
    return render(request, "cvs/base_cv_detail.html", {
        "page": "cvs",
        "cv": cv,
        "others": BaseCv.objects.exclude(pk=cv.pk),
    })
