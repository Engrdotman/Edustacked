from datetime import timedelta
from hashlib import sha256
import hmac
import json
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    ImportedExamination,
    ImportLog,
    LocalExamSession,
    LocalLicenseVerification,
    LocalStudentAnswer,
    LocalSubmission,
    SyncOutbox,
)


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _parse_time(value, field):
    try:
        parsed = timezone.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({field: "Package contains an invalid timestamp."}) from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _verify_package(signed_payload):
    if not isinstance(signed_payload, str) or not signed_payload or len(signed_payload) > 50 * 1024 * 1024:
        raise ValidationError("Provide a signed package string no larger than 50 MB.")
    if not settings.CBT_PACKAGE_SIGNING_KEY:
        raise ValidationError("Configure CBT_PACKAGE_SIGNING_KEY before importing packages.")
    try:
        envelope = signing.loads(signed_payload, key=settings.CBT_PACKAGE_SIGNING_KEY, salt="edustacked.offline-cbt-package.v1")
    except signing.BadSignature as exc:
        raise ValidationError("Package signature is invalid or the package was modified.") from exc
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValidationError("Package has an invalid payload structure.")
    payload_hash = sha256(canonical_json(payload)).hexdigest()
    if not hmac.compare_digest(str(envelope.get("sha256", "")), payload_hash):
        raise ValidationError("Package integrity checksum is invalid.")
    required = ("package_id", "package_version", "school_id", "examination_id", "license", "assigned_student_ids", "assigned_students", "questions", "answer_key", "starts_at", "ends_at", "duration_minutes")
    if any(field not in payload for field in required):
        raise ValidationError("Package is missing required examination data.")
    if payload["package_version"] != 1 or not payload["assigned_student_ids"] or not payload["questions"]:
        raise ValidationError("Package version or assignment/question contents are invalid.")
    try:
        package_id = __import__("uuid").UUID(payload["package_id"])
        __import__("uuid").UUID(payload["examination_id"])
        expiry = _parse_time(payload["ends_at"], "ends_at")
    except (ValueError, TypeError) as exc:
        raise ValidationError("Package identifiers are invalid.") from exc
    if timezone.now() > expiry:
        raise ValidationError("This examination package has expired.")
    license_data = payload["license"]
    try:
        license_payload = signing.loads(
            license_data["signed_token"], key=settings.CBT_LICENSE_SIGNING_KEY,
            salt="edustacked.service-license.v1",
        )
    except (KeyError, signing.BadSignature) as exc:
        raise ValidationError("Offline CBT license signature is invalid.") from exc
    if license_payload != license_data.get("payload"):
        raise ValidationError("License data does not match its signature.")
    today = timezone.localdate()
    try:
        starts = timezone.datetime.fromisoformat(license_payload["starts_on"]).date()
        expires = timezone.datetime.fromisoformat(license_payload["expires_on"]).date()
        grace = int(license_payload["offline_grace_days"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValidationError("Offline CBT license fields are invalid.") from exc
    if license_payload.get("school_id") != payload["school_id"] or license_payload.get("service_code") != "offline_cbt":
        raise ValidationError("License does not authorize this school's CBT package.")
    if today < starts or today > expires + timedelta(days=grace):
        raise ValidationError("Offline CBT license is expired outside its grace period.")
    allowed_students = set(payload["assigned_student_ids"])
    mapped_students = {row.get("student_id") for row in payload["assigned_students"]}
    if allowed_students != mapped_students:
        raise ValidationError("Package student assignments are inconsistent.")
    question_ids = {item.get("question_id") for item in payload["questions"]}
    key_ids = {item.get("question_id") for item in payload["answer_key"]}
    if question_ids != key_ids or len(question_ids) != len(payload["questions"]):
        raise ValidationError("Package question snapshots and answer keys are inconsistent.")
    allowed_options = {
        question["question_id"]: {option["id"] for option in question.get("options", [])}
        for question in payload["questions"]
    }
    for key in payload["answer_key"]:
        if any(option_id not in allowed_options[key["question_id"]] for option_id in key.get("correct_option_ids", [])):
            raise ValidationError("Package answer key references an unknown option.")
    return package_id, payload_hash, payload


@transaction.atomic
def import_package(signed_payload):
    package_id, digest, payload = _verify_package(signed_payload)
    existing = ImportedExamination.objects.filter(package_id=package_id).first()
    if existing:
        if existing.payload_hash == digest:
            ImportLog.objects.create(package_id=package_id, examination_id=existing.examination_id, status="duplicate", detail="Identical package already imported.")
            return existing, False
        raise ValidationError("Package identifier already exists with different contents.")
    latest = ImportedExamination.objects.filter(examination_id=payload["examination_id"]).order_by("-version").first()
    if latest and payload["package_version"] <= latest.version:
        raise ValidationError("Package version is older than or equal to the imported examination version.")
    if latest and latest.sessions.filter(status=LocalExamSession.Status.IN_PROGRESS).exists():
        raise ValidationError("An updated package cannot replace an examination with active student sessions.")
    row = ImportedExamination.objects.create(
        package_id=package_id,
        school_id=payload["school_id"],
        examination_id=payload["examination_id"],
        version=payload["package_version"],
        payload_hash=digest,
        config={key: value for key, value in payload.items() if key != "answer_key"},
        answer_key=payload["answer_key"],
        assigned_student_ids=payload["assigned_student_ids"],
    )
    license_payload = payload["license"]["payload"]
    LocalLicenseVerification.objects.update_or_create(
        license_id=license_payload["license_id"],
        defaults={
            "school_id": payload["school_id"], "service_code": license_payload["service_code"],
            "expires_on": license_payload["expires_on"],
            "offline_grace_days": license_payload["offline_grace_days"], "payload_hash": sha256(canonical_json(license_payload)).hexdigest(),
        },
    )
    ImportLog.objects.create(package_id=package_id, examination_id=row.examination_id, status="imported")
    return row, True


def student_question_view(exam, answers=None):
    answers = answers or {}
    return {
        "package_id": str(exam.package_id),
        "examination_id": exam.examination_id,
        "title": exam.config.get("title"),
        "instructions": exam.config.get("instructions", ""),
        "subject": exam.config.get("subject", ""),
        "class_name": exam.config.get("class_name", ""),
        "duration_minutes": exam.config["duration_minutes"],
        "starts_at": exam.config["starts_at"],
        "ends_at": exam.config["ends_at"],
        "total_marks": exam.config.get("total_marks"),
        "questions": [{
            "question_id": question["question_id"],
            "position": question["position"],
            "prompt": question["prompt"],
            "type": question["type"],
            "marks": question["marks"],
            "options": question.get("options", []),
            "image_data": question.get("image_data", ""),
            "image_mime": question.get("image_mime", ""),
            "answer": answers.get(question["question_id"]),
        } for question in exam.config["questions"]],
    }


def submission_payload(session, submission):
    answers = [{
        "question_id": answer.question_id,
        "value": answer.value,
        "saved_at": answer.saved_at.isoformat(),
    } for answer in submission.session.answers.all().order_by("question_id")]
    return {
        "event_id": str(submission.event_id),
        "payload_version": 1,
        "event_type": "submission.finalized",
        "school_id": session.exam.school_id,
        "package_id": str(session.exam_id),
        "examination_id": session.exam.examination_id,
        "assignment_id": str(session.assignment_id),
        "student_id": session.student.central_student_id,
        "local_session_id": str(session.pk),
        "started_at": session.started_at.isoformat(),
        "submitted_at": submission.submitted_at.isoformat(),
        "status": session.status,
        "answers": answers,
    }


@transaction.atomic
def finalize_session(session, *, auto=False):
    session = LocalExamSession.objects.select_for_update().select_related("exam", "student").get(pk=session.pk)
    existing = LocalSubmission.objects.filter(session=session).first()
    if existing:
        return existing
    if session.status != LocalExamSession.Status.IN_PROGRESS:
        raise ValidationError("This examination session is already closed.")
    now = timezone.now()
    if not auto and now >= session.expires_at:
        auto = True
    session.status = LocalExamSession.Status.AUTO_SUBMITTED if auto else LocalExamSession.Status.SUBMITTED
    session.submitted_at = min(now, session.expires_at) if auto else now
    session.save(update_fields=("status", "submitted_at", "last_activity_at"))
    snapshot = [{
        "question_id": answer.question_id,
        "value": answer.value,
        "saved_at": answer.saved_at.isoformat(),
    } for answer in session.answers.all().order_by("question_id")]
    payload_hash = sha256(canonical_json(snapshot)).hexdigest()
    submission = LocalSubmission.objects.create(session=session, answers=snapshot, payload_hash=payload_hash, submitted_at=session.submitted_at)
    payload = submission_payload(session, submission)
    SyncOutbox.objects.create(event_id=submission.event_id, session=session, payload=payload, payload_hash=sha256(canonical_json(payload)).hexdigest())
    return submission


def maybe_auto_submit(session):
    if session.status == LocalExamSession.Status.IN_PROGRESS and timezone.now() >= session.expires_at:
        finalize_session(session, auto=True)
        session.refresh_from_db()
    return session
