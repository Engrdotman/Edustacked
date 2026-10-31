from rest_framework.permissions import BasePermission

from .services import linked_student_queryset


class HasGuardianPortalAccess(BasePermission):
    message = "A linked parent or guardian account is required."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and linked_student_queryset(request.user).exists()
        )
