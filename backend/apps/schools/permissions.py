"""Reusable platform and school-role permission checks."""

from django.http import Http404
from django.conf import settings
from rest_framework.permissions import BasePermission

from .models import SchoolMembership
from .tenancy import resolve_authorized_school


ROLE_PERMISSIONS = {
    SchoolMembership.Role.SCHOOL_ADMIN: frozenset(
        {
            "school.view",
            "school.manage",
            "integrations.manage",
            "memberships.manage",
            "academics.manage",
            "students.view",
            "students.manage",
            "students.enroll",
            "students.guardians.view",
            "students.guardians.manage",
            "attendance.view",
            "attendance.manage",
            "attendance.record",
            "results.view",
            "results.enter",
            "results.approve",
            "report_cards.view", "report_cards.generate", "report_cards.review", "report_cards.approve", "report_cards.finalize",
            "finance.view",
            "finance.manage",
            "billing.view", "billing.purchase",
            "announcements.manage",
            "frontdesk.manage",
            "staff.view", "staff.manage", "teacher_assignments.view", "teacher_assignments.manage",
            "reports.dashboard", "reports.enrollment", "reports.attendance", "reports.academics", "reports.report_cards", "reports.finance",
        }
    ),
    SchoolMembership.Role.SCHOOL_MANAGER: frozenset(
        {
            "school.view",
            "academics.manage",
            "students.view",
            "students.manage",
            "students.enroll",
            "students.guardians.view",
            "students.guardians.manage",
            "attendance.view",
            "attendance.manage",
            "attendance.record",
            "results.view",
            "results.enter",
            "report_cards.view", "report_cards.generate", "report_cards.review",
            "announcements.manage",
            "frontdesk.manage",
            "staff.view", "staff.manage", "teacher_assignments.view", "teacher_assignments.manage",
            "reports.dashboard", "reports.enrollment", "reports.attendance", "reports.academics", "reports.report_cards",
        }
    ),
    SchoolMembership.Role.PRINCIPAL: frozenset(
        {
            "school.view", "academics.manage", "memberships.manage",
            "students.view", "students.manage", "students.enroll",
            "students.guardians.view", "students.guardians.manage",
            "attendance.view", "attendance.manage", "attendance.record",
            "results.view", "results.enter", "report_cards.view", "report_cards.generate",
            "report_cards.review", "announcements.manage", "frontdesk.manage",
            "staff.view", "staff.manage", "teacher_assignments.view", "teacher_assignments.manage",
            "reports.dashboard", "reports.enrollment", "reports.attendance", "reports.academics", "reports.report_cards",
        }
    ),
    SchoolMembership.Role.TEACHER: frozenset(
        {"school.view", "students.view", "attendance.view", "attendance.record", "results.view", "results.enter", "report_cards.view", "teacher.profile.view", "teacher_assignments.view", "reports.dashboard", "reports.attendance", "reports.academics", "reports.report_cards"}
    ),
    SchoolMembership.Role.ACCOUNTANT: frozenset({"school.view", "finance.view", "finance.manage", "billing.view", "billing.purchase", "reports.dashboard", "reports.finance"}),
    SchoolMembership.Role.RECEPTIONIST: frozenset(
        {
            "school.view", "students.view", "students.enroll",
            "students.guardians.view", "students.guardians.manage", "frontdesk.manage", "staff.view",
            "reports.dashboard", "reports.enrollment",
        }
    ),
    SchoolMembership.Role.MEMBER: frozenset(),
}
ROLE_PERMISSIONS[SchoolMembership.Role.SCHOOL_OWNER] = ROLE_PERMISSIONS[SchoolMembership.Role.SCHOOL_ADMIN]


def school_allows_capability(school, capability):
    """Central policy gate for capabilities reserved for verified schools."""
    required = getattr(settings, "SCHOOL_VERIFIED_REQUIRED_CAPABILITIES", frozenset({"integrations.manage"}))
    return capability not in required or school.verification_status == school.VerificationStatus.VERIFIED


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
        return (
            required_permission in ROLE_PERMISSIONS.get(membership.role, frozenset())
            and school_allows_capability(membership.school, required_permission)
        )

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


class HasSchoolProfileAccess(BasePermission):
    """Allow profile reads to school staff and edits to school admins only."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        required = "school.view" if request.method in {"GET", "HEAD", "OPTIONS"} else "school.manage"
        if user.is_superuser:
            return True
        try:
            membership = authorized_membership(user, request, view)
        except Http404:
            return False
        return required in ROLE_PERMISSIONS.get(membership.role, frozenset()) and school_allows_capability(membership.school, required)
