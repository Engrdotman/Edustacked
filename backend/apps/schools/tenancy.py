"""Reusable, fail-closed helpers for school-scoped API views."""

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from .models import School


def authorized_schools_for(user):
    """Return active schools the authenticated user may access."""
    if not getattr(user, "is_authenticated", False):
        return School.objects.none()
    if getattr(user, "is_superuser", False):
        return School.objects.filter(is_active=True)

    return School.objects.filter(
        is_active=True,
        memberships__user=user,
        memberships__is_active=True,
    ).distinct()


def resolve_authorized_school(user, identifier, lookup_field="pk"):
    """Resolve a school only through the user's active membership.

    A uniform 404 for missing, malformed, inactive, or unauthorized school
    identifiers avoids revealing whether another school's record exists.
    """
    if not identifier or lookup_field not in {"pk", "slug"}:
        raise Http404

    try:
        return get_object_or_404(
            authorized_schools_for(user), **{lookup_field: identifier}
        )
    except (TypeError, ValueError, ValidationError):
        raise Http404 from None


class SchoolScopedQuerySetMixin:
    """Scope list and object queries to an authorized school URL parameter.

    Views must provide a queryset with a foreign key at ``school_field`` and
    include this mixin before their DRF generic view class. The school context
    is taken from the URL, then independently authorized against membership.
    """

    school_field = "school"
    school_url_kwarg = "school_id"
    school_lookup_field = "pk"

    def get_authorized_school(self):
        identifier = self.kwargs.get(self.school_url_kwarg) or self.request.headers.get(
            "X-School-ID"
        )
        return resolve_authorized_school(
            self.request.user, identifier, self.school_lookup_field
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        school = self.get_authorized_school()
        return queryset.filter(**{self.school_field: school})

    def perform_create(self, serializer):
        serializer.save(**{self.school_field: self.get_authorized_school()})

    def perform_update(self, serializer):
        serializer.save(**{self.school_field: self.get_authorized_school()})
