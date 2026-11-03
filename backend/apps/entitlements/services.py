from django.utils import timezone

from .models import ServiceEntitlement


def service_is_active(school, service_code):
    today = timezone.localdate()
    return ServiceEntitlement.objects.filter(
        school=school,
        service_code=service_code,
        status=ServiceEntitlement.Status.ACTIVE,
        starts_on__lte=today,
        expires_on__gte=today,
    ).exists()
