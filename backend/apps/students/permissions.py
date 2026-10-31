from rest_framework.permissions import BasePermission
from django.http import Http404

from apps.schools.permissions import ROLE_PERMISSIONS, authorized_membership


class HasStudentPermission(BasePermission):
    """Resolve a student permission per HTTP method using the active school role."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        method_permissions = getattr(view, "student_permissions", {})
        required = method_permissions.get(request.method)
        if not required:
            return False
        try:
            membership = authorized_membership(request.user, request, view)
        except Http404:
            return False
        return required in ROLE_PERMISSIONS.get(membership.role, frozenset())
