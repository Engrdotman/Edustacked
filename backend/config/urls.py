from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/<str:version>/", include("apps.core.urls")),
    path("api/<str:version>/auth/", include("apps.accounts.urls")),
    path("api/<str:version>/schools/", include("apps.schools.urls")),
    path("api/<str:version>/academics/", include("apps.academics.urls")),
    path("api/<str:version>/", include("apps.students.urls")),
    path("api/<str:version>/", include("apps.staff.urls")),
    path("api/<str:version>/", include("apps.attendance.urls")),
    path("api/<str:version>/", include("apps.results.urls")),
    path("api/<str:version>/", include("apps.report_cards.urls")),
    path("api/<str:version>/", include("apps.billing.urls")),
    path("api/<str:version>/", include("apps.parent_portal.urls")),
    path("api/<str:version>/reports/", include("apps.reports.urls")),
]
