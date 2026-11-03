from rest_framework.permissions import BasePermission

from apps.schools.tenancy import resolve_authorized_school

from .services import service_is_active


class HasActiveServiceEntitlement(BasePermission):
    """Add to a future service endpoint after its normal role permission."""

    message = "This school does not have an active entitlement for this service."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        service_code = getattr(view, "required_service_code", None)
        if not service_code:
            return False
        school_id = request.headers.get("X-School-ID") or view.kwargs.get("school_id")
        school = resolve_authorized_school(request.user, school_id)
        return service_is_active(school, service_code)
