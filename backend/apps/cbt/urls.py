from django.urls import path

from .views import (
    CbtSetupView,
    ExaminationAssignmentView,
    ExaminationDetailView,
    ExaminationListCreateView,
    ExaminationPublishView,
    ExaminationPackageView,
    ExaminationStatusView,
    LocalServerCredentialView,
    LocalServerListView,
    LocalServerRevokeView,
    CbtSyncIngestView,
    CbtSyncDashboardView,
    QuestionArchiveView,
    QuestionDetailView,
    QuestionListCreateView,
    QuestionPublishView,
)

urlpatterns = [
    path("cbt/setup/", CbtSetupView.as_view(), name="cbt-setup"),
    path("cbt/questions/", QuestionListCreateView.as_view(), name="cbt-question-list"),
    path("cbt/questions/<uuid:id>/", QuestionDetailView.as_view(), name="cbt-question-detail"),
    path("cbt/questions/<uuid:question_id>/publish/", QuestionPublishView.as_view(), name="cbt-question-publish"),
    path("cbt/questions/<uuid:question_id>/archive/", QuestionArchiveView.as_view(), name="cbt-question-archive"),
    path("cbt/examinations/", ExaminationListCreateView.as_view(), name="cbt-examination-list"),
    path("cbt/examinations/<uuid:id>/", ExaminationDetailView.as_view(), name="cbt-examination-detail"),
    path("cbt/examinations/<uuid:examination_id>/publish/", ExaminationPublishView.as_view(), name="cbt-examination-publish"),
    path("cbt/examinations/<uuid:examination_id>/package/", ExaminationPackageView.as_view(), name="cbt-examination-package"),
    path("cbt/examinations/<uuid:examination_id>/status/", ExaminationStatusView.as_view(), name="cbt-examination-status"),
    path("cbt/examinations/<uuid:examination_id>/assignments/", ExaminationAssignmentView.as_view(), name="cbt-examination-assignments"),
    path("cbt/local-servers/", LocalServerListView.as_view(), name="cbt-local-server-list"),
    path("cbt/local-servers/credentials/", LocalServerCredentialView.as_view(), name="cbt-local-server-credential"),
    path("cbt/local-servers/<int:server_id>/revoke/", LocalServerRevokeView.as_view(), name="cbt-local-server-revoke"),
    path("cbt/sync/dashboard/", CbtSyncDashboardView.as_view(), name="cbt-sync-dashboard"),
    path("cbt/sync/ingest/", CbtSyncIngestView.as_view(), name="cbt-sync-ingest"),
]
