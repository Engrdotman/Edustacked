from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import School, SchoolOnboardingProgress, SchoolSettings


@receiver(post_save, sender=School)
def ensure_school_settings(sender, instance, created, **kwargs):
    if created:
        SchoolSettings.objects.get_or_create(school=instance)
        SchoolOnboardingProgress.objects.get_or_create(school=instance)
