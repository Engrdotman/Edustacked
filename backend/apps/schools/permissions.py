"""Reusable platform and school-role permission checks."""

from django.http import Http404
from rest_framework.permissions import BasePermission

from .models import SchoolMembership
from .tenancy import resolve_authorized_school


ROLE_PERMISSIONS = {
    SchoolMembership.Role.SCHOOL_ADMIN: frozenset(
        {
            "school.manage",
            "memberships.manage",
            "academics.manage",
            "students.view",
            "students.manage",
            "attendance.view",
            "attendance.manage",
            "attendance.record",
            "results.view",
            "results.enter",
            "results.approve",
            "finance.view",
            "finance.manage",
            "frontdesk.manage",
        }
    ),
    SchoolMembership.Role.SCHOOL_MANAGER: frozenset(
        {
            "academics.manage",
            "students.view",
            "students.manage",
            "attendance.view",
            "attendance.manage",
            "attendance.record",
            "results.view",
            "results.enter",
            "frontdesk.manage",
        }
    ),
    SchoolMembership.Role.TEACHER: frozenset(
        {"students.view", "attendance.view", "attendance.record", "results.view", "results.enter"}
    ),
    SchoolMembership.Role.ACCOUNTANT: frozenset({"finance.view", "finance.manage"}),
    SchoolMembership.Role.RECEPTIONIST: frozenset(
        {"students.view", "students.enroll", "frontdesk.manage"}
    ),
    SchoolMembership.Role.MEMBER: frozenset(),
}


def school_identifier(request, view):
    return (
        view.kwargs.get(getattr(view, "school_url_kwarg", "school_id"))
        or request.headers.get("X-School-ID")
    )


def authorized_membership(user, request, view):
    identifier = school_identifier(request, view)
    school = resolve_authorized_school(user, identifier)
    try:
        return SchoolMembership.objects.get(
            user=user, school=school, is_active=True
        )
    except SchoolMembership.DoesNotExist:
        raise Http404 from None


class IsPlatformSuperadmin(BasePermission):
    """Only Django superusers receive platform-wide authority."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class HasSchoolPermission(BasePermission):
    """Require an explicit permission granted by the active school role."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        required_permission = getattr(view, "required_school_permission", None)
        if not required_permission:
            return False
        try:
            membership = authorized_membership(user, request, view)
        except Http404:
            return False
        return required_permission in ROLE_PERMISSIONS.get(membership.role, frozenset())

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        try:
            membership = authorized_membership(request.user, request, view)
        except Http404:
            return False
        object_school_id = getattr(obj, "school_id", None)
        if object_school_id is None and hasattr(obj, "school"):
            object_school_id = obj.school.pk
        return (
            object_school_id == membership.school_id
            and self.has_permission(request, view)
        )
