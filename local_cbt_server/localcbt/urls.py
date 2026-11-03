from django.contrib import admin
from django.urls import include, path
from offline_exam.views import local_admin_dashboard

urlpatterns = [path("operations/", local_admin_dashboard, name="local-cbt-dashboard"), path("admin/", admin.site.urls), path("local/api/v1/", include("offline_exam.urls"))]
