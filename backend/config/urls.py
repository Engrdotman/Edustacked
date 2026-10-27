from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/<str:version>/", include("apps.core.urls")),
    path("api/<str:version>/auth/", include("apps.accounts.urls")),
    path("api/<str:version>/schools/", include("apps.schools.urls")),
]
