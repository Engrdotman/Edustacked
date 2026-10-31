from django.db import migrations


def grandfather_finalized_cards(apps, schema_editor):
    Revision = apps.get_model("report_cards", "ReportCardRevision")
    Billing = apps.get_model("billing", "ReportCardBilling")
    alias = schema_editor.connection.alias
    seen = set()
    revisions = Revision.objects.using(alias).filter(status="finalized").select_related("report_card").order_by("created_at", "id")
    for revision in revisions.iterator():
        card = revision.report_card
        key = (card.school_id, card.student_id, card.academic_session_id, card.term_id)
        if key in seen:
            continue
        seen.add(key)
        Billing.objects.using(alias).get_or_create(
            school_id=key[0], student_id=key[1], academic_session_id=key[2], term_id=key[3],
            defaults={
                "report_card_id": card.pk,
                "revision_id": revision.pk,
                "charged_at": None,
                "legacy_waived": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
        ("report_cards", "0001_initial"),
    ]

    operations = [migrations.RunPython(grandfather_finalized_cards, migrations.RunPython.noop)]
