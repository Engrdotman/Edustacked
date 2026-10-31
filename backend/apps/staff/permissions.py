from django.http import Http404
from rest_framework.permissions import BasePermission

from apps.schools.permissions import ROLE_PERMISSIONS, authorized_membership


class HasStaffPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        required = getattr(view, "staff_permissions", {}).get(request.method)
        if not required:
            return False
        try:
            membership = authorized_membership(user, request, view)
        except Http404:
            return False
        return required in ROLE_PERMISSIONS.get(membership.role, frozenset())
