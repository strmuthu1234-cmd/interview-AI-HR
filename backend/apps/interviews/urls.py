from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("interviews", views.InterviewViewSet, basename="interview")

urlpatterns = [
    # candidate (invitation token)
    path("interviews/access/", views.AccessView.as_view(), name="interview-access"),
    path("interviews/<uuid:pk>/accept-instructions/", views.AcceptInstructionsView.as_view(), name="interview-accept"),
    path("interviews/<uuid:pk>/question/", views.QuestionView.as_view(), name="interview-question"),
    path("interviews/<uuid:pk>/answer/", views.AnswerView.as_view(), name="interview-answer"),
    path("interviews/<uuid:pk>/voice-upload/", views.VoiceUploadView.as_view(), name="interview-voice"),
    path("interviews/<uuid:pk>/progress/", views.ProgressView.as_view(), name="interview-progress"),
    path("interviews/<uuid:pk>/complete/", views.CompleteView.as_view(), name="interview-complete"),
    path("interviews/<uuid:pk>/results/", views.ResultsView.as_view(), name="interview-results"),
    # HR
    path("interviews/create/", views.CreateInvitationView.as_view(), name="interview-create"),
    path("interviews/<uuid:pk>/generate-questions/", views.GenerateQuestionsView.as_view(), name="interview-generate"),
    path("interviews/<uuid:pk>/questions/<uuid:qid>/", views.EditQuestionView.as_view(), name="interview-edit-question"),
    path("interviews/<uuid:pk>/approve-questions/", views.ApproveQuestionsView.as_view(), name="interview-approve-questions"),
    path("interviews/<uuid:pk>/regenerate-link/", views.RegenerateLinkView.as_view(), name="interview-regenerate-link"),
    path("interviews/<uuid:pk>/revoke/", views.RevokeInvitationView.as_view(), name="interview-revoke"),
    path("interviews/<uuid:pk>/overrides/", views.OverrideView.as_view(), name="interview-override"),
    path("interviews/<uuid:pk>/report/", views.ReportView.as_view(), name="interview-report"),
    path("interviews/<uuid:pk>/report/regenerate/", views.ReportRegenerateView.as_view(), name="interview-report-regenerate"),
    path("interviews/<uuid:pk>/report/pdf/", views.ReportPdfView.as_view(), name="interview-report-pdf"),
    path("interviews/<uuid:pk>/answers/<uuid:aid>/audio-url/", views.AudioUrlView.as_view(), name="interview-audio-url"),
    path("files/audio/<str:token>/", views.AudioFileView.as_view(), name="audio-file"),
    path("hr/decisions/", views.DecisionView.as_view(), name="hr-decisions"),
    path("reports/compare/", views.CompareView.as_view(), name="report-compare"),
    path("reports/export/", views.ExportCsvView.as_view(), name="report-export"),
    path("", include(router.urls)),
]
