from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.students.models import StudentEnrollment

from .models import FeeSchedule
from .services import issue_fee_schedule


@receiver(post_save, sender=StudentEnrollment)
def issue_existing_fees_for_new_enrollment(sender, instance, created, **kwargs):
    if instance.status != StudentEnrollment.Status.ACTIVE:
        return
    schedules = FeeSchedule.objects.filter(
        school=instance.school, academic_session=instance.academic_session,
        class_level=instance.class_level, status=FeeSchedule.Status.ACTIVE,
    ).filter(Q(class_arm__isnull=True) | Q(class_arm=instance.class_arm))
    for schedule in schedules:
        transaction.on_commit(lambda row=schedule: issue_fee_schedule(row, row.created_by))
