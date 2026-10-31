from django.urls import path

from .views import (
    AssessmentComponentDetailView, AssessmentComponentListCreateView,
    AssessmentPlanDetailView, AssessmentPlanListCreateView, AssessmentResultDetailView, AssessmentResultListView,
    EligiblePlanStudentsView, PlanActionView, PlanComponentDetailView, PlanComponentsView,
    PlanResultsView, ResultBatchActionView,
)

urlpatterns = [
    path("assessment-components/", AssessmentComponentListCreateView.as_view(), name="assessment-component-list"),
    path("assessment-components/<int:pk>/", AssessmentComponentDetailView.as_view(), name="assessment-component-detail"),
    path("assessment-plans/", AssessmentPlanListCreateView.as_view(), name="assessment-plan-list"),
    path("assessment-plans/<int:pk>/", AssessmentPlanDetailView.as_view(), name="assessment-plan-detail"),
    path("assessment-plans/<int:pk>/components/", PlanComponentsView.as_view(), name="assessment-plan-components"),
    path("assessment-plans/<int:pk>/components/<int:component_id>/", PlanComponentDetailView.as_view(), name="assessment-plan-component-detail"),
    path("assessment-plans/<int:pk>/eligible-students/", EligiblePlanStudentsView.as_view(), name="assessment-plan-eligible-students"),
    path("assessment-plans/<int:pk>/results/", PlanResultsView.as_view(), name="assessment-plan-results"),
    path("assessment-plans/<int:pk>/<str:action>/", PlanActionView.as_view(), name="assessment-plan-action"),
    path("assessment-plans/<int:plan_id>/results/<str:action>/", ResultBatchActionView.as_view(), name="assessment-result-batch-action"),
    path("assessment-results/", AssessmentResultListView.as_view(), name="assessment-result-list"),
    path("assessment-results/<int:pk>/", AssessmentResultDetailView.as_view(), name="assessment-result-detail"),
]
