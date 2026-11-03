from decimal import Decimal
from hashlib import sha256
import base64
import hmac
import json
import mimetypes
from uuid import uuid4
from random import SystemRandom

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.students.models import Student, StudentEnrollment

from .models import (
    CbtResult,
    CbtResultCorrection,
    CbtExaminationPackage,
    CbtSyncConflict,
    CbtSyncedSubmission,
    Examination,
    ExaminationAssignment,
    ExaminationQuestion,
    LocalCbtServerCredential,
    LocalCbtSyncEvent,
    Question,
)


def _calculate_result_values(examination, details, *, pass_mark=None):
    objective_score = Decimal("0")
    final_score = Decimal("0")
    pending_manual = False
    correct = incorrect = 0
    for item in details:
        marks = Decimal(str(item["marks_possible"]))
        awarded = item.get("marks_awarded")
        if item["question_type"] != Question.Type.TEXT:
            objective_score += Decimal(str(awarded or "0"))
        if awarded is None:
            pending_manual = True
        else:
            final_score += Decimal(str(awarded))
        if item.get("correct") is True:
            correct += 1
        if item.get("incorrect") is True:
            incorrect += 1
    maximum = sum((Decimal(str(item["marks_possible"])) for item in details), Decimal("0"))
    finalized = not pending_manual
    percentage = (final_score * Decimal("100") / maximum).quantize(Decimal("0.01")) if finalized and maximum else Decimal("0.00") if finalized else None
    return {
        "status": CbtResult.Status.FINALIZED if finalized else CbtResult.Status.NEEDS_MARKING,
        "objective_score": objective_score.quantize(Decimal("0.01")),
        "score": final_score.quantize(Decimal("0.01")) if finalized else None,
        "maximum_score": maximum.quantize(Decimal("0.01")),
        "percentage": percentage,
        "passed": (final_score >= (pass_mark if pass_mark is not None else examination.pass_mark)) if finalized else None,
        "correct_answers": correct,
        "incorrect_answers": incorrect,
    }


def process_synced_submission(submission, *, calculated_by="system:offline-cbt-auto-mark-v1"):
    """Mark an accepted raw submission using only frozen central snapshots."""
    existing = CbtResult.objects.filter(event=submission.event).first()
    if existing:
        return existing, False
    examination = submission.examination
    answers = {str(row.get("question_id")): row.get("value") for row in submission.answers}
    questions = list(examination.exam_questions.filter(is_snapshot=True).order_by("position"))
    if not questions:
        raise ValidationError("The examination has no frozen question snapshots to mark.")
    details = []
    attempted = unanswered = 0
    for question in questions:
        question_id = str(question.source_question_id)
        response = answers.get(question_id)
        question_type = question.type_snapshot
        if question_type == Question.Type.TEXT:
            attempted_answer = isinstance(response, str) and bool(response.strip())
        elif question_type == Question.Type.MULTIPLE_ANSWER:
            attempted_answer = isinstance(response, list) and bool(response)
        else:
            attempted_answer = isinstance(response, str) and bool(response)
        attempted += int(attempted_answer)
        unanswered += int(not attempted_answer)
        correct_ids = [
            f"{question_id}:{position}"
            for position, option in enumerate(question.options_snapshot or [])
            if option.get("is_correct")
        ]
        if question_type == Question.Type.TEXT:
            is_correct = None
            awarded = None if attempted_answer else "0.00"
            is_incorrect = False
        else:
            if question_type == Question.Type.MULTIPLE_ANSWER:
                is_correct = set(response or []) == set(correct_ids) if attempted_answer else False
            else:
                is_correct = response == correct_ids[0] if attempted_answer and correct_ids else False
            awarded = str(question.marks_snapshot if is_correct else Decimal("0.00"))
            is_incorrect = attempted_answer and not is_correct
        details.append({
            "question_id": question_id,
            "position": question.position,
            "prompt": question.prompt_snapshot,
            "question_type": question_type,
            "response": response,
            "options": [
                {"id": f"{question_id}:{position}", "text": option.get("text", "")}
                for position, option in enumerate(question.options_snapshot or [])
            ],
            "attempted": attempted_answer,
            "marks_possible": str(question.marks_snapshot),
            "marks_awarded": awarded,
            "correct": is_correct,
            "incorrect": is_incorrect,
            "correct_option_ids": correct_ids,
            "explanation": question.explanation_snapshot,
        })
    values = _calculate_result_values(examination, details)
    result = CbtResult.objects.create(
        school=submission.school,
        examination=examination,
        assignment=submission.assignment,
        event=submission.event,
        local_session_id=submission.local_session_id,
        submitted_at=submission.submitted_at,
        synchronized_at=submission.event.received_at,
        total_questions=len(questions),
        attempted_questions=attempted,
        unanswered_questions=unanswered,
        pass_mark=examination.pass_mark,
        mark_details=details,
        calculated_by=calculated_by,
        **values,
    )
    return result, True


@transaction.atomic
def apply_result_correction(result, *, marks, reason, actor):
    """Apply manual marks/corrections and retain a before/after audit snapshot."""
    if not isinstance(marks, dict) or not marks:
        raise ValidationError({"marks": "Provide at least one question mark."})
    if not reason or len(reason.strip()) < 5:
        raise ValidationError({"reason": "Explain the correction (at least 5 characters)."})
    examination = result.examination
    before = result.mark_details
    details = [dict(item) for item in before]
    by_id = {item["question_id"]: item for item in details}
    for question_id, raw_mark in marks.items():
        item = by_id.get(str(question_id))
        if item is None:
            raise ValidationError({"marks": f"Question {question_id} is not part of this result."})
        try:
            mark = Decimal(str(raw_mark))
        except Exception as exc:
            raise ValidationError({"marks": f"Question {question_id} has an invalid mark."}) from exc
        maximum = Decimal(item["marks_possible"])
        if not mark.is_finite() or mark < 0 or mark > maximum:
            raise ValidationError({"marks": f"Question {question_id} must be between 0 and {maximum}."})
        if not item["attempted"] and mark != 0:
            raise ValidationError({"marks": f"Question {question_id} was unanswered and cannot receive marks."})
        item["marks_awarded"] = str(mark.quantize(Decimal("0.01")))
        item["correct"] = bool(item["attempted"] and mark == maximum)
        item["incorrect"] = bool(item["attempted"] and mark == 0)
    values = _calculate_result_values(examination, details, pass_mark=result.pass_mark)
    CbtResultCorrection.objects.create(
        result=result, corrected_by=actor, reason=reason.strip(),
        previous_details=before, corrected_details=details,
    )
    CbtResult.objects.filter(pk=result.pk).update(mark_details=details, updated_at=timezone.now(), **values)
    result.refresh_from_db()
    return result


def _eligible_question_queryset(examination):
    queryset = Question.objects.filter(
        school_id=examination.school_id,
        subject_id=examination.subject_id,
        class_level_id=examination.class_level_id,
        status=Question.Status.PUBLISHED,
    )
    criteria = examination.question_criteria or {}
    if criteria.get("difficulty"):
        queryset = queryset.filter(difficulty=criteria["difficulty"])
    if criteria.get("topic"):
        queryset = queryset.filter(topic__iexact=criteria["topic"])
    return queryset


@transaction.atomic
def publish_examination(examination_id, school, actor):
    examination = Examination.objects.select_for_update().get(pk=examination_id, school=school)
    if examination.status != Examination.Status.DRAFT or examination.published_at:
        raise ValidationError("Only a draft examination can be published.")
    if (examination.ends_at - examination.starts_at).total_seconds() < examination.duration_minutes * 60:
        raise ValidationError({"duration_minutes": "The scheduled window must be at least as long as the examination."})

    if examination.selection_method == Examination.SelectionMethod.RANDOM:
        count = examination.random_question_count or 0
        candidates = list(_eligible_question_queryset(examination).values_list("pk", flat=True))
        if count < 1 or len(candidates) < count:
            raise ValidationError({"random_question_count": "There are not enough published matching questions in this school's bank."})
        selected_ids = SystemRandom().sample(candidates, count)
    else:
        selected_ids = list(
            examination.exam_questions.filter(is_snapshot=False).order_by("position").values_list("source_question_id", flat=True)
        )
        if not selected_ids:
            raise ValidationError({"questions": "Select at least one published question before publishing."})

    questions = list(_eligible_question_queryset(examination).filter(pk__in=selected_ids).prefetch_related("options"))
    by_id = {question.pk: question for question in questions}
    if len(by_id) != len(selected_ids):
        raise ValidationError({"questions": "Every selected question must be published and match this examination's school, subject, and class."})
    for question in questions:
        options = list(question.options.all())
        option_count = len(options)
        correct_count = sum(option.is_correct for option in options)
        if question.question_type == Question.Type.TEXT:
            if option_count:
                raise ValidationError({"questions": f"Text question {question.pk} must not have answer options."})
        elif option_count < 2:
            raise ValidationError({"questions": f"Question {question.pk} needs at least two answer options."})
        elif question.question_type == Question.Type.SINGLE_CHOICE and correct_count != 1:
            raise ValidationError({"questions": f"Single-choice question {question.pk} must have exactly one correct answer."})
        elif question.question_type == Question.Type.MULTIPLE_ANSWER and correct_count < 1:
            raise ValidationError({"questions": f"Multiple-answer question {question.pk} needs at least one correct answer."})

    ExaminationQuestion.objects.filter(examination=examination).delete()
    total = Decimal("0")
    for position, question_id in enumerate(selected_ids):
        question = by_id[question_id]
        selection = ExaminationQuestion.objects.create(examination=examination, source_question=question, position=position)
        selection.snapshot()
        total += question.marks
    if examination.pass_mark > total:
        raise ValidationError({"pass_mark": "The pass mark cannot exceed the calculated total marks."})

    now = timezone.now()
    examination.total_marks = total
    examination.published_at = now
    examination.status = Examination.Status.SCHEDULED if examination.starts_at > now else Examination.Status.PUBLISHED
    examination.save(update_fields=("total_marks", "published_at", "status", "updated_at"))
    return examination


@transaction.atomic
def change_examination_status(examination_id, school, next_status):
    examination = Examination.objects.select_for_update().get(pk=examination_id, school=school)
    allowed = {
        Examination.Status.SCHEDULED: {Examination.Status.ACTIVE, Examination.Status.COMPLETED, Examination.Status.ARCHIVED},
        Examination.Status.PUBLISHED: {Examination.Status.ACTIVE, Examination.Status.COMPLETED, Examination.Status.ARCHIVED},
        Examination.Status.ACTIVE: {Examination.Status.COMPLETED},
        Examination.Status.COMPLETED: {Examination.Status.ARCHIVED},
    }
    if next_status not in allowed.get(examination.status, set()):
        raise ValidationError({"status": f"Cannot move an examination from {examination.status} to {next_status}."})
    examination.status = next_status
    examination.save(update_fields=("status", "updated_at"))
    return examination


@transaction.atomic
def assign_examination(examination_id, school, actor, *, student_ids=None, all_students=False):
    examination = Examination.objects.select_for_update().get(pk=examination_id, school=school)
    if not examination.published_at or examination.status not in {
        Examination.Status.PUBLISHED,
        Examination.Status.SCHEDULED,
        Examination.Status.ACTIVE,
    }:
        raise ValidationError("Publish the examination before assigning it to students.")
    eligible = StudentEnrollment.objects.filter(
        school=school,
        academic_session_id=examination.academic_session_id,
        class_level_id=examination.class_level_id,
        status=StudentEnrollment.Status.ACTIVE,
        student__status=Student.Status.ACTIVE,
    ).values_list("student_id", flat=True)
    if all_students:
        selected_ids = list(eligible)
    else:
        submitted_ids = student_ids or []
        if not submitted_ids:
            raise ValidationError({"student_ids": "Choose at least one eligible student or assign the whole class."})
        unique_submitted = set(submitted_ids)
        eligible_ids = set(eligible.filter(student_id__in=unique_submitted))
        if len(eligible_ids) != len(unique_submitted):
            raise ValidationError({"student_ids": "Every selected student must be actively enrolled in this examination's class and session."})
        selected_ids = list(dict.fromkeys(submitted_ids))

    existing_ids = set(ExaminationAssignment.objects.filter(examination=examination, student_id__in=selected_ids).values_list("student_id", flat=True))
    new_ids = [student_id for student_id in selected_ids if student_id not in existing_ids]
    student_map = {student.pk: student for student in Student.objects.filter(school=school, pk__in=new_ids)}
    created = [
        ExaminationAssignment(examination=examination, student=student_map[student_id], assigned_by=actor)
        for student_id in new_ids if student_id in student_map
    ]
    before_count = len(existing_ids)
    ExaminationAssignment.objects.bulk_create(created, ignore_conflicts=True)
    after_count = ExaminationAssignment.objects.filter(examination=examination, student_id__in=selected_ids).count()
    actual_created = after_count - before_count
    return {
        "assigned": actual_created,
        "already_assigned": len(selected_ids) - actual_created,
        "total_assignments": ExaminationAssignment.objects.filter(examination=examination, status=ExaminationAssignment.Status.ASSIGNED).count(),
    }


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@transaction.atomic
def create_examination_package(examination_id, school, actor):
    if not settings.CBT_PACKAGE_SIGNING_KEY:
        raise ValidationError("CBT_PACKAGE_SIGNING_KEY must be configured before packages can be generated.")
    examination = Examination.objects.select_for_update().filter(pk=examination_id, school=school).first()
    if not examination:
        raise Examination.DoesNotExist
    if not examination.published_at or examination.status in {Examination.Status.DRAFT, Examination.Status.ARCHIVED}:
        raise ValidationError("Publish the examination before preparing an offline package.")
    existing = CbtExaminationPackage.objects.filter(examination=examination).first()
    if existing:
        return existing
    assignments = list(
        ExaminationAssignment.objects.filter(examination=examination, status=ExaminationAssignment.Status.ASSIGNED)
        .select_related("student").order_by("student_id")
    )
    if not assignments:
        raise ValidationError("Assign the examination to at least one eligible student before packaging.")
    questions = list(examination.exam_questions.filter(is_snapshot=True).order_by("position"))
    if not questions:
        raise ValidationError("The published examination has no frozen question snapshot.")
    student_ids = [assignment.student_id for assignment in assignments]
    entitlement = school.service_entitlements.filter(
        service_code="offline_cbt", status="active", starts_on__lte=timezone.localdate(), expires_on__gte=timezone.localdate()
    ).order_by("-expires_on").first()
    if not entitlement:
        raise ValidationError("The school needs an active Offline CBT license to generate a package.")
    if len(student_ids) > entitlement.student_capacity:
        raise ValidationError({"assignments": "Assigned student count exceeds the active CBT license capacity."})

    student_questions = []
    answer_keys = []
    for question in questions:
        option_rows = question.options_snapshot or []
        student_options = []
        correct_option_ids = []
        for position, option in enumerate(option_rows):
            option_id = f"{question.source_question_id}:{position}"
            student_options.append({"id": option_id, "text": option["text"]})
            if option.get("is_correct"):
                correct_option_ids.append(option_id)
        image_data = ""
        image_mime = ""
        source = Question.objects.filter(pk=question.source_question_id).first()
        if source and source.image:
            try:
                image_mime = mimetypes.guess_type(source.image.name)[0] or "application/octet-stream"
                source.image.open("rb")
                image_data = base64.b64encode(source.image.read()).decode("ascii")
            finally:
                source.image.close()
        student_questions.append({
            "question_id": str(question.source_question_id),
            "position": question.position,
            "prompt": question.prompt_snapshot,
            "type": question.type_snapshot,
            "marks": str(question.marks_snapshot),
            "options": student_options,
            "image_data": image_data,
            "image_mime": image_mime,
        })
        answer_keys.append({
            "question_id": str(question.source_question_id),
            "correct_option_ids": correct_option_ids,
        })
    payload = {
        "package_id": str(uuid4()),
        "package_version": 1,
        "school_id": school.pk,
        "school_name": school.name,
        "license_id": str(entitlement.license_id),
        "license": {"payload": entitlement.license_payload(), "signed_token": entitlement.signed_license},
        "examination_id": str(examination.pk),
        "title": examination.title,
        "description": examination.description,
        "instructions": examination.instructions,
        "subject": examination.subject.name,
        "class_name": examination.class_level.name,
        "academic_session_id": examination.academic_session_id,
        "academic_session": examination.academic_session.name,
        "term": examination.term.name if examination.term_id else "",
        "starts_at": examination.starts_at.isoformat(),
        "ends_at": examination.ends_at.isoformat(),
        "duration_minutes": examination.duration_minutes,
        "maximum_attempts": examination.maximum_attempts,
        "total_marks": str(examination.total_marks),
        "assigned_student_ids": student_ids,
        "assigned_students": [{
            "student_id": assignment.student_id,
            "admission_number": assignment.student.admission_number,
            "assignment_id": str(assignment.pk),
        } for assignment in assignments],
        "questions": student_questions,
        "answer_key": answer_keys,
        "created_at": timezone.now().isoformat(),
    }
    payload_hash = sha256(_canonical_json(payload)).hexdigest()
    signed_payload = signing.dumps(
        {"payload": payload, "sha256": payload_hash},
        key=settings.CBT_PACKAGE_SIGNING_KEY,
        salt="edustacked.offline-cbt-package.v1",
        compress=True,
    )
    return CbtExaminationPackage.objects.create(
        package_id=payload["package_id"], school=school, examination=examination,
        version=1, payload_hash=payload_hash, signed_payload=signed_payload, created_by=actor,
    )


def issue_local_server_credential(school, name):
    return LocalCbtServerCredential.issue(school, name)


def ingest_local_submission(credential, envelope, bearer_token):
    payload = envelope.get("payload")
    supplied_hash = envelope.get("payload_hash", "")
    supplied_signature = envelope.get("signature", "")
    if not isinstance(payload, dict):
        raise ValidationError({"payload": "A submission payload object is required."})
    canonical = _canonical_json(payload)
    payload_hash = sha256(canonical).hexdigest()
    if not supplied_hash or supplied_hash != payload_hash:
        raise ValidationError({"payload_hash": "Submission payload integrity check failed."})
    expected_signature = hmac.new(bearer_token.encode("utf-8"), canonical, "sha256").hexdigest()
    if not supplied_signature or not hmac.compare_digest(expected_signature, supplied_signature):
        raise ValidationError({"signature": "Submission authentication signature is invalid."})
    if payload.get("payload_version") != 1 or payload.get("event_type") != "submission.finalized":
        raise ValidationError({"payload_version": "Unsupported synchronization event type or version."})
    if payload.get("school_id") != credential.school_id:
        raise ValidationError({"school_id": "Submission belongs to another school."})
    today = timezone.localdate()
    # A package was issued under a signed license and may be used during its
    # explicitly licensed offline grace window while the school is disconnected.
    active_license = credential.school.service_entitlements.filter(
        service_code="offline_cbt", status="active", starts_on__lte=today,
        expires_on__gte=today - timezone.timedelta(days=settings.CBT_OFFLINE_GRACE_DAYS),
    ).exists()
    if not active_license:
        raise ValidationError("The school has no active Offline CBT entitlement.")
    try:
        from uuid import UUID
        event_id = UUID(payload["event_id"])
        local_session_id = UUID(payload["local_session_id"])
        package_id = UUID(payload["package_id"])
        examination = Examination.objects.get(pk=payload["examination_id"], school=credential.school)
        package = CbtExaminationPackage.objects.get(package_id=package_id, school=credential.school, examination=examination)
        assignment = ExaminationAssignment.objects.select_related("student").get(
            pk=payload["assignment_id"], examination=examination,
        )
    except (KeyError, ValueError, Examination.DoesNotExist, ExaminationAssignment.DoesNotExist, CbtExaminationPackage.DoesNotExist) as exc:
        raise ValidationError("The examination assignment or synchronization identifier is invalid.") from exc
    try:
        student_id = int(payload["student_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError({"student_id": "A valid student identifier is required."}) from exc
    if assignment.student_id != student_id:
        raise ValidationError({"student_id": "The submission student does not match the exam assignment."})
    if assignment.status != ExaminationAssignment.Status.ASSIGNED:
        raise ValidationError({"assignment_id": "This examination assignment is no longer active."})
    signed_package = signing.loads(package.signed_payload, key=settings.CBT_PACKAGE_SIGNING_KEY, salt="edustacked.offline-cbt-package.v1")
    assignment_ids = {str(item["assignment_id"]): item["student_id"] for item in signed_package["payload"].get("assigned_students", [])}
    if assignment_ids.get(str(assignment.pk)) != student_id:
        raise ValidationError({"assignment_id": "The assignment is not part of the downloaded examination package."})
    answers = payload.get("answers")
    if not isinstance(answers, list) or len(answers) > 500:
        raise ValidationError({"answers": "Submission answers must be a list of at most 500 rows."})
    allowed_questions = {
        str(row.source_question_id): row.options_snapshot or []
        for row in examination.exam_questions.filter(is_snapshot=True)
    }
    seen_questions = set()
    for answer in answers:
        if not isinstance(answer, dict) or not isinstance(answer.get("question_id"), str) or answer.get("question_id") not in allowed_questions:
            raise ValidationError({"answers": "A response references an unrelated question."})
        if answer["question_id"] in seen_questions:
            raise ValidationError({"answers": "Duplicate answers for a question are not allowed."})
        seen_questions.add(answer["question_id"])
        value = answer.get("value")
        qtype = examination.exam_questions.get(source_question_id=answer["question_id"], is_snapshot=True).type_snapshot
        options = allowed_questions[answer["question_id"]]
        allowed_option_ids = {f"{answer['question_id']}:{i}" for i in range(len(options))}
        if qtype == Question.Type.SINGLE_CHOICE and (not isinstance(value, str) or value not in allowed_option_ids):
            raise ValidationError({"answers": "A single choice answer does not match the question snapshot."})
        if qtype == Question.Type.MULTIPLE_ANSWER and (
            not isinstance(value, list) or not all(isinstance(item, str) for item in value)
            or len(value) != len(set(value)) or any(item not in allowed_option_ids for item in value)
        ):
            raise ValidationError({"answers": "A multiple answer response does not match the question snapshot."})
        if qtype == Question.Type.TEXT and (not isinstance(value, str) or len(value) > 12000):
            raise ValidationError({"answers": "A written response is invalid or too long."})
        if len(json.dumps(answer.get("value"), ensure_ascii=False)) > 12000:
            raise ValidationError({"answers": "An answer exceeds the maximum size."})
    if not payload.get("submitted_at"):
        raise ValidationError({"submitted_at": "A submission timestamp is required."})

    existing_event = LocalCbtSyncEvent.objects.filter(event_id=event_id).first()
    if existing_event:
        if existing_event.school_id != credential.school_id:
            raise ValidationError({"event_id": "This event identifier is already owned by another school."})
        if existing_event.payload_hash == payload_hash:
            if hasattr(existing_event, "submission") and not hasattr(existing_event, "result"):
                process_synced_submission(existing_event.submission)
            return existing_event, False, False
        CbtSyncConflict.objects.create(
            event=existing_event, attempted_hash=payload_hash, attempted_payload=payload,
            reason="An existing event identifier was replayed with different content.",
        )
        existing_event.status = LocalCbtSyncEvent.Status.CONFLICT
        existing_event.resolution_note = "Event id replayed with different content; administrator review required."
        existing_event.save(update_fields=("status", "resolution_note"))
        return existing_event, False, True
    existing_submission = CbtSyncedSubmission.objects.filter(school=credential.school, local_session_id=local_session_id).first()
    if existing_submission:
        if existing_submission.event.payload_hash == payload_hash:
            if not hasattr(existing_submission.event, "result"):
                process_synced_submission(existing_submission)
            return existing_submission.event, False, False
        CbtSyncConflict.objects.create(
            event=existing_submission.event, attempted_hash=payload_hash, attempted_payload=payload,
            reason="A completed local session was replayed with different content.",
        )
        existing_submission.event.status = LocalCbtSyncEvent.Status.CONFLICT
        existing_submission.event.resolution_note = "Completed session replayed with different content; administrator review required."
        existing_submission.event.save(update_fields=("status", "resolution_note"))
        return existing_submission.event, False, True

    from django.utils.dateparse import parse_datetime
    submitted_at = parse_datetime(payload["submitted_at"])
    if not submitted_at or timezone.is_naive(submitted_at):
        raise ValidationError({"submitted_at": "Submission time must include a valid timezone."})
    from django.db import transaction
    with transaction.atomic():
        event = LocalCbtSyncEvent.objects.create(
            event_id=event_id, school=credential.school, examination=examination, assignment=assignment,
            local_session_id=local_session_id, payload_version=1, payload_hash=payload_hash, payload=payload,
            status=LocalCbtSyncEvent.Status.ACCEPTED,
        )
        CbtSyncedSubmission.objects.create(
            school=credential.school, examination=examination, assignment=assignment,
            local_session_id=local_session_id, event=event, submitted_at=submitted_at, answers=answers,
        )
        process_synced_submission(CbtSyncedSubmission.objects.select_related("examination", "assignment", "event").get(event=event))
    return event, True, False
