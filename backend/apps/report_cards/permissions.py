from django.http import Http404
from rest_framework.permissions import BasePermission

from apps.schools.permissions import ROLE_PERMISSIONS, authorized_membership


class HasReportCardPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        action = view.kwargs.get("action")
        required = getattr(view, "report_action_permissions", {}).get(action) if action else None
        if required is None:
            required = getattr(view, "report_permissions", {}).get(request.method)
        if not required:
            return False
        try:
            membership = authorized_membership(request.user, request, view)
        except Http404:
            return False
        return required in ROLE_PERMISSIONS.get(membership.role, frozenset())
