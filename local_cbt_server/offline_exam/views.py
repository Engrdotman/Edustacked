from datetime import timedelta
from hashlib import sha256
import secrets
import sqlite3
import tempfile
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .models import (
    AnswerSaveRequest,
    ImportedExamination,
    ImportLog,
    LocalExamSession,
    LocalStudentAnswer,
    LocalStudentCredential,
    LocalLicenseVerification,
    LocalSubmission,
    StudentAccessToken,
    SyncLog,
    SyncOutbox,
)
from .sync import process_due_outbox
from .services import canonical_json, finalize_session, import_package, maybe_auto_submit, student_question_view


def student_credential(request):
    credential = getattr(getattr(request, "user", None), "credential", None)
    if credential is None:
        raise AuthenticationFailed("Sign in with your local student credentials.")
    return credential


def owned_session(request, session_id):
    credential = student_credential(request)
    session = LocalExamSession.objects.select_related("exam", "student").filter(pk=session_id, student=credential).first()
    if not session:
        raise Http404
    maybe_auto_submit(session)
    return session


def session_answers(session):
    return {row.question_id: row.value for row in session.answers.all()}


def session_response(session):
    exam_view = student_question_view(session.exam, session_answers(session))
    exam_view.update({
        "session_id": str(session.pk),
        "student_name": session.student.display_name,
        "admission_number": session.student.admission_number,
        "status": session.status,
        "server_now": timezone.now().isoformat(),
        "started_at": session.started_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "submitted_at": session.submitted_at.isoformat() if session.submitted_at else None,
        "saved_answers": session.answers.count(),
    })
    return exam_view


@staff_member_required
def local_admin_dashboard(request):
    return render(request, "offline_exam/dashboard.html")


class LocalLoginThrottle(AnonRateThrottle):
    scope = "anon"


class StudentLoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (LocalLoginThrottle,)

    def post(self, request):
        admission = str(request.data.get("admission_number", "")).strip()
        password = str(request.data.get("password", ""))
        credential = LocalStudentCredential.objects.filter(admission_number__iexact=admission).first()
        now = timezone.now()
        if not credential or not credential.is_active:
            raise AuthenticationFailed("Admission number or password is incorrect.")
        if credential.locked_until and credential.locked_until > now:
            raise AuthenticationFailed("This local account is temporarily locked. Contact the examination administrator.")
        if not credential.check_password(password):
            credential.failed_login_attempts += 1
            if credential.failed_login_attempts >= 8:
                credential.failed_login_attempts = 0
                credential.locked_until = now + timedelta(minutes=15)
            credential.save(update_fields=("failed_login_attempts", "locked_until"))
            raise AuthenticationFailed("Admission number or password is incorrect.")
        credential.failed_login_attempts = 0
        credential.locked_until = None
        credential.save(update_fields=("failed_login_attempts", "locked_until"))
        token = secrets.token_urlsafe(48)
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        StudentAccessToken.objects.create(
            student=credential,
            token_hash=token_hash,
            expires_at=now + timedelta(hours=settings.LOCAL_CBT_TOKEN_TTL_HOURS),
        )
        return Response({"token": token, "expires_at": (now + timedelta(hours=settings.LOCAL_CBT_TOKEN_TTL_HOURS)).isoformat(), "student": {"name": credential.display_name, "admission_number": credential.admission_number}})


class StudentLogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        auth_record = request.auth
        if isinstance(auth_record, StudentAccessToken):
            auth_record.revoked_at = timezone.now()
            auth_record.save(update_fields=("revoked_at",))
        return Response(status=status.HTTP_204_NO_CONTENT)


class StudentExamListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        credential = student_credential(request)
        now = timezone.now()
        packages = ImportedExamination.objects.filter(status=ImportedExamination.Status.READY).order_by("imported_at")
        results = []
        for exam in packages:
            if credential.central_student_id not in exam.assigned_student_ids:
                continue
            ends = timezone.datetime.fromisoformat(exam.config["ends_at"].replace("Z", "+00:00"))
            if ends < now:
                continue
            active = exam.sessions.filter(student=credential, status=LocalExamSession.Status.IN_PROGRESS).first()
            attempts = exam.sessions.filter(student=credential).count()
            results.append({
                "package_id": str(exam.package_id), "examination_id": exam.examination_id,
                "title": exam.config.get("title", "Examination"), "subject": exam.config.get("subject", ""),
                "class_name": exam.config.get("class_name", ""), "instructions": exam.config.get("instructions", ""),
                "starts_at": exam.config["starts_at"], "ends_at": exam.config["ends_at"],
                "duration_minutes": exam.config["duration_minutes"], "status": "in_progress" if active else exam.status,
                "session_id": str(active.pk) if active else None,
                "attempts_used": attempts, "maximum_attempts": exam.config["maximum_attempts"],
            })
        return Response(results)


class StudentExamStartView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, package_id):
        credential = student_credential(request)
        try:
            UUID(str(package_id))
        except ValueError as exc:
            raise Http404 from exc
        exam = ImportedExamination.objects.filter(package_id=package_id, status=ImportedExamination.Status.READY).first()
        if not exam:
            raise Http404
        if credential.central_student_id not in exam.assigned_student_ids:
            raise PermissionDenied("This examination is not assigned to this student.")
        now = timezone.now()
        starts = timezone.datetime.fromisoformat(exam.config["starts_at"].replace("Z", "+00:00"))
        ends = timezone.datetime.fromisoformat(exam.config["ends_at"].replace("Z", "+00:00"))
        if now < starts:
            return Response({"detail": "The examination has not started yet.", "starts_at": starts.isoformat()}, status=status.HTTP_409_CONFLICT)
        if now >= ends:
            return Response({"detail": "The examination has ended."}, status=status.HTTP_410_GONE)
        active = LocalExamSession.objects.filter(exam=exam, student=credential, status=LocalExamSession.Status.IN_PROGRESS).first()
        if active:
            maybe_auto_submit(active)
            if active.status == LocalExamSession.Status.IN_PROGRESS:
                return Response(session_response(active))
        attempts = exam.sessions.filter(student=credential).count()
        if attempts >= int(exam.config["maximum_attempts"]):
            return Response({"detail": "Maximum examination attempts have been used."}, status=status.HTTP_409_CONFLICT)
        assignment = next((row for row in exam.config["assigned_students"] if row["student_id"] == credential.central_student_id), None)
        if not assignment:
            raise PermissionDenied("The package has no assignment for this student.")
        duration_end = now + timedelta(minutes=int(exam.config["duration_minutes"]))
        session_end = min(duration_end, ends)
        try:
            with transaction.atomic():
                session = LocalExamSession.objects.create(
                    exam=exam, student=credential, assignment_id=assignment["assignment_id"],
                    started_at=now, expires_at=session_end,
                )
        except IntegrityError:
            session = LocalExamSession.objects.filter(exam=exam, student=credential, status=LocalExamSession.Status.IN_PROGRESS).first()
            if not session:
                return Response({"detail": "An examination session could not be opened. Contact the examination administrator."}, status=status.HTTP_409_CONFLICT)
        return Response(session_response(session), status=status.HTTP_201_CREATED)


class StudentSessionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, session_id):
        session = owned_session(request, session_id)
        return Response(session_response(session))


class StudentAnswerView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, session_id):
        session = owned_session(request, session_id)
        if session.status != LocalExamSession.Status.IN_PROGRESS:
            return Response({"detail": "Submitted examination answers are locked."}, status=status.HTTP_409_CONFLICT)
        try:
            request_id = UUID(str(request.data.get("request_id", "")))
        except ValueError as exc:
            return Response({"request_id": "Provide a unique UUID for this save."}, status=status.HTTP_400_BAD_REQUEST)
        question_id = str(request.data.get("question_id", ""))
        value = request.data.get("value")
        question = next((row for row in session.exam.config["questions"] if row["question_id"] == question_id), None)
        if not question:
            raise Http404
        if question["type"] == "single_choice":
            valid = isinstance(value, str) and value in {option["id"] for option in question.get("options", [])}
        elif question["type"] == "multiple_answer":
            valid = isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) == len(set(value)) and all(
                item in {option["id"] for option in question.get("options", [])} for item in value
            )
        else:
            valid = isinstance(value, str) and len(value) <= 12000
        if not valid:
            return Response({"value": "Answer format does not match this question."}, status=status.HTTP_400_BAD_REQUEST)
        digest = sha256(canonical_json(value)).hexdigest()
        prior_request = AnswerSaveRequest.objects.filter(session=session, request_id=request_id).first()
        if prior_request:
            if prior_request.question_id == question_id and prior_request.value_hash == digest:
                answer = LocalStudentAnswer.objects.filter(session=session, question_id=question_id).first()
                return Response({"saved": True, "duplicate": True, "saved_at": answer.saved_at.isoformat() if answer else prior_request.created_at.isoformat()})
            return Response({"detail": "This save request identifier was reused with different answer data."}, status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            AnswerSaveRequest.objects.create(session=session, request_id=request_id, question_id=question_id, value_hash=digest)
            answer, _ = LocalStudentAnswer.objects.update_or_create(
                session=session, question_id=question_id,
                defaults={"value": value, "last_request_id": request_id},
            )
        return Response({"saved": True, "duplicate": False, "saved_at": answer.saved_at.isoformat()})


class StudentSubmitView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, session_id):
        session = owned_session(request, session_id)
        try:
            submission = finalize_session(session)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_409_CONFLICT)
        return Response({
            "submission_id": str(submission.event_id), "submitted_at": submission.submitted_at.isoformat(),
            "status": LocalExamSession.objects.get(pk=session.pk).status,
            "message": "Your answers have been saved on this school server.",
        })


class PackageImportView(APIView):
    permission_classes = (IsAdminUser,)

    def post(self, request):
        signed_payload = request.data.get("signed_payload")
        if not signed_payload:
            return Response({"signed_payload": "Upload the signed package contents."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            package, created = import_package(signed_payload)
        except ValidationError as exc:
            ImportLog.objects.create(status="rejected", detail=" ".join(exc.messages)[:500])
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"package_id": str(package.package_id), "examination_id": package.examination_id, "version": package.version, "duplicate": not created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class LocalAdminOverviewView(APIView):
    permission_classes = (IsAdminUser,)

    def get(self, request):
        active = LocalExamSession.objects.filter(status=LocalExamSession.Status.IN_PROGRESS)
        outbox = SyncOutbox.objects.all()
        licenses = LocalLicenseVerification.objects.order_by("-expires_on")
        current_license = licenses.first()
        return Response({
            "server_time": timezone.now().isoformat(),
            "database": "sqlite",
            "package_count": ImportedExamination.objects.count(),
            "active_sessions": active.count(),
            "completed_sessions": LocalExamSession.objects.filter(status__in=(LocalExamSession.Status.SUBMITTED, LocalExamSession.Status.AUTO_SUBMITTED)).count(),
            "students": LocalStudentCredential.objects.filter(is_active=True).count(),
            "license_status": "not imported" if not current_license else ("valid" if current_license.valid_for_offline_use else "expired"),
            "license_expires_on": current_license.expires_on if current_license else None,
            "sync_pending": outbox.filter(status=SyncOutbox.Status.PENDING).count(),
            "sync_failed": outbox.filter(status=SyncOutbox.Status.FAILED).count(),
            "sync_complete": outbox.filter(status=SyncOutbox.Status.SYNCED).count(),
            "last_sync": SyncOutbox.objects.filter(synced_at__isnull=False).order_by("-synced_at").values_list("synced_at", flat=True).first(),
            "recent_sessions": [{
                "id": str(row.pk), "student": row.student.display_name,
                "admission_number": row.student.admission_number,
                "examination": row.exam.config.get("title"), "status": row.status,
                "started_at": row.started_at, "expires_at": row.expires_at,
            } for row in LocalExamSession.objects.select_related("exam", "student").order_by("-started_at")[:100]],
            "packages": [{"id": str(row.package_id), "title": row.config.get("title"), "exam_id": row.examination_id, "version": row.version, "status": row.status, "imported_at": row.imported_at} for row in ImportedExamination.objects.order_by("-imported_at")[:100]],
        })


class SyncDashboardView(APIView):
    permission_classes = (IsAdminUser,)

    def get(self, request):
        entries = SyncOutbox.objects.select_related("session__exam", "session__student").order_by("-created_at")[:200]
        return Response([{
            "event_id": str(row.event_id), "examination": row.session.exam.config.get("title"),
            "student": row.session.student.admission_number, "status": row.status,
            "retry_count": row.retry_count, "next_attempt_at": row.next_attempt_at,
            "last_attempt_at": row.last_attempt_at, "synced_at": row.synced_at,
            "error": row.error_detail,
        } for row in entries])

    def post(self, request):
        if request.data.get("action") == "sync_now":
            return Response(process_due_outbox())
        try:
            event_id = UUID(str(request.data.get("event_id", "")))
        except ValueError:
            event_id = None
        if event_id:
            row = SyncOutbox.objects.filter(event_id=event_id, status=SyncOutbox.Status.FAILED).first()
            rows = [row] if row else []
        else:
            rows = list(SyncOutbox.objects.filter(status=SyncOutbox.Status.FAILED).order_by("created_at")[:50])
        for row in rows:
            row.status = SyncOutbox.Status.PENDING
            row.retry_count = 0
            row.next_attempt_at = timezone.now()
            row.error_detail = ""
            row.save(update_fields=("status", "retry_count", "next_attempt_at", "error_detail"))
        return Response({"queued_for_retry": len(rows)})


class LocalDatabaseBackupView(APIView):
    permission_classes = (IsAdminUser,)

    def get(self, request):
        import os

        source_path = settings.DATABASE_PATH
        if not source_path.exists():
            return Response({"detail": "Local database file is not available."}, status=status.HTTP_404_NOT_FOUND)
        temporary = tempfile.NamedTemporaryFile(prefix="local-cbt-backup-", suffix=".sqlite3", delete=False)
        target_path = temporary.name
        temporary.close()
        try:
            source = sqlite3.connect(source_path)
            target = sqlite3.connect(target_path)
            with target:
                source.backup(target)
            target.close()
            source.close()
            stream = open(target_path, "rb")
            response = FileResponse(stream, as_attachment=True, filename=f"local-cbt-{timezone.localdate().isoformat()}.sqlite3")
            # FileResponse is streamed and is never rendered; clean up after
            # its file handle closes, including interrupted downloads.
            response._resource_closers.append(lambda: os.path.exists(target_path) and os.unlink(target_path))
            return response
        except Exception:
            if os.path.exists(target_path):
                os.unlink(target_path)
            raise
