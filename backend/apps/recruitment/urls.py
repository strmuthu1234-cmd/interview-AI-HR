from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("jobs", views.JobViewSet, basename="job")
router.register("candidates", views.CandidateViewSet, basename="candidate")
router.register("batches", views.BatchViewSet, basename="batch")
router.register("shortlists", views.ShortlistViewSet, basename="shortlist")

urlpatterns = [
    path("resumes/bulk-upload/", views.BulkUploadView.as_view(), name="bulk-upload"),
    path("resumes/analyze/", views.AnalyzeView.as_view(), name="analyze"),
    path("shortlists/approve/", views.ShortlistApproveView.as_view(), name="shortlist-approve"),
    path("files/resume/<str:token>/", views.ResumeFileView.as_view(), name="resume-file"),
    path("dashboard/stats/", views.DashboardView.as_view(), name="dashboard"),
    path("", include(router.urls)),
]
