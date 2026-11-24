from datetime import date
import hashlib
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Subject, Term
from apps.schools.models import School, SchoolMembership
from apps.staff.models import StaffProfile, TeacherAssignment, TeacherProfile
from apps.students.models import Student, StudentEnrollment
from .models import AttendanceAuditEvent, AttendanceRecord, AttendanceRegister, OfflineAttendanceGrant

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class AttendanceApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Attendance North", slug="attendance-north")
        self.other_school = School.objects.create(name="Attendance South", slug="attendance-south")
        self.admin = self.make_user("att-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.manager = self.make_user("att-manager", SchoolMembership.Role.SCHOOL_MANAGER, self.school)
        self.teacher_user = self.make_user("att-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.receptionist = self.make_user("att-frontdesk", SchoolMembership.Role.RECEPTIONIST, self.school)
        self.other_admin = self.make_user("att-other-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

        self.session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        AcademicSession.objects.filter(pk=self.session.pk).update(status=AcademicSession.Status.ACTIVE)
        self.session.refresh_from_db()
        self.term = Term.objects.create(school=self.school, academic_session=self.session, name="First Term", sequence=1, start_date=date(2026, 9, 1), end_date=date(2026, 12, 20))
        self.level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1")
        self.arm = ClassArm.objects.create(school=self.school, class_level=self.level, name="A")
        self.other_level = ClassLevel.objects.create(school=self.school, name="JSS 2", code="JSS2")
        self.other_arm = ClassArm.objects.create(school=self.school, class_level=self.other_level, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        staff = StaffProfile.objects.create(school=self.school, user=self.teacher_user, staff_number="T-ATT-1", first_name="Tari", last_name="Teacher", job_title="Teacher", employment_start_date=date(2026, 9, 1))
        self.teacher = TeacherProfile.objects.create(school=self.school, staff=staff)
        TeacherAssignment.objects.create(school=self.school, teacher=self.teacher, academic_session=self.session, class_level=self.level, class_arm=self.arm, subject=self.subject, start_date=date(2026, 9, 1))
        self.student_a = self.make_student("A-001", "Ada")
        self.student_b = self.make_student("A-002", "Bola")

    @staticmethod
    def make_user(username, role, school):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def make_student(self, admission_number, first_name):
        student = Student.objects.create(school=self.school, admission_number=admission_number, first_name=first_name, last_name="Student")
        StudentEnrollment.objects.create(school=self.school, student=student, academic_session=self.session, class_level=self.level, class_arm=self.arm, enrollment_date=date(2026, 9, 1), status=StudentEnrollment.Status.ACTIVE)
        return student

    def api(self, method, path, data=None, school=None):
        return getattr(self.client, method)(path, data, HTTP_X_SCHOOL_ID=str((school or self.school).pk), format="json")

    def create_register(self, *, user=None, attendance_date="2026-10-15", class_level=None, class_arm=None):
        if user:
            self.client.force_authenticate(user)
        response = self.api("post", "/api/v1/attendance/registers/create/", {
            "academic_session": self.session.pk, "term": self.term.pk,
            "class_level": (class_level or self.level).pk, "class_arm": (class_arm or self.arm).pk,
            "attendance_date": attendance_date,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def test_register_freezes_roster_bulk_save_and_finalized_report_policy(self):
        register = self.create_register()
        self.assertEqual(register["total_students"], 2)
        duplicate_entries = self.api("patch", f"/api/v1/attendance/registers/{register['id']}/records/", {
            "version": 1, "records": [
                {"student_id": self.student_a.pk, "status": "present"},
                {"student_id": self.student_a.pk, "status": "absent"},
            ],
        })
        self.assertEqual(duplicate_entries.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AttendanceRegister.objects.get(pk=register["id"]).version, 1)

        saved = self.api("patch", f"/api/v1/attendance/registers/{register['id']}/records/", {
            "version": 1, "records": [
                {"student_id": self.student_a.pk, "status": "present"},
                {"student_id": self.student_b.pk, "status": "late"},
            ],
        })
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.assertEqual(saved.data["version"], 2)
        self.assertEqual(AttendanceAuditEvent.objects.filter(event_type=AttendanceAuditEvent.EventType.RECORDED).count(), 2)
        stale = self.api("patch", f"/api/v1/attendance/registers/{register['id']}/records/", {"version": 1, "records": [{"student_id": self.student_a.pk, "status": "absent"}]})
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        incomplete_submit = self.api("post", f"/api/v1/attendance/registers/{register['id']}/submit/", {"version": 2})
        self.assertEqual(incomplete_submit.status_code, status.HTTP_200_OK, incomplete_submit.data)
        finalized = self.api("post", f"/api/v1/attendance/registers/{register['id']}/finalize/", {"version": 3})
        self.assertEqual(finalized.status_code, status.HTTP_200_OK, finalized.data)
        report = self.api("get", "/api/v1/attendance/reports/summary/?date_from=2026-10-01&date_to=2026-10-31")
        self.assertEqual(report.status_code, status.HTTP_200_OK, report.data)
        self.assertEqual(report.data["totals"]["total"], 2)
        self.assertEqual(report.data["totals"]["attendance_percentage"], 100.0)
        self.assertEqual(report.data["included_register_statuses"], [AttendanceRegister.Status.FINALIZED])

    def test_teacher_scope_cross_school_future_dates_and_duplicates(self):
        teacher_register = self.create_register(user=self.teacher_user)
        self.client.force_authenticate(self.other_admin)
        forbidden = self.api("get", f"/api/v1/attendance/registers/{teacher_register['id']}/", school=self.other_school)
        self.assertEqual(forbidden.status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.teacher_user)
        wrong_class = self.api("get", f"/api/v1/attendance/eligible-students/?academic_session={self.session.pk}&class_level={self.other_level.pk}&class_arm={self.other_arm.pk}&date=2026-10-15")
        self.assertEqual(wrong_class.status_code, status.HTTP_404_NOT_FOUND)
        future = self.api("post", "/api/v1/attendance/registers/create/", {
            "academic_session": self.session.pk, "term": self.term.pk,
            "class_level": self.level.pk, "class_arm": self.arm.pk, "attendance_date": "2027-06-30",
        })
        self.assertEqual(future.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.admin)
        duplicate = self.api("post", "/api/v1/attendance/registers/create/", {
            "academic_session": self.session.pk, "term": self.term.pk,
            "class_level": self.level.pk, "class_arm": self.arm.pk, "attendance_date": "2026-10-15",
        })
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.receptionist)
        denied = self.api("get", "/api/v1/attendance/registers/")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_reopen_correction_audit_and_teacher_cannot_edit_submitted_register(self):
        register = self.create_register(user=self.teacher_user)
        save = self.api("patch", f"/api/v1/attendance/registers/{register['id']}/records/", {
            "version": 1, "records": [
                {"student_id": self.student_a.pk, "status": "present"},
                {"student_id": self.student_b.pk, "status": "excused"},
            ],
        })
        submitted = self.api("post", f"/api/v1/attendance/registers/{register['id']}/submit/", {"version": save.data["version"]})
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        self.client.force_authenticate(self.teacher_user)
        denied_correction = self.api("patch", f"/api/v1/attendance/registers/{register['id']}/records/", {"version": submitted.data["version"], "records": [{"student_id": self.student_a.pk, "status": "absent", "reason": "Correction"}]})
        self.assertEqual(denied_correction.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        finalized = self.api("post", f"/api/v1/attendance/registers/{register['id']}/finalize/", {"version": submitted.data["version"]})
        self.assertEqual(finalized.status_code, status.HTTP_200_OK)
        no_reason = self.api("post", f"/api/v1/attendance/registers/{register['id']}/reopen/", {"version": finalized.data["version"]})
        self.assertEqual(no_reason.status_code, status.HTTP_400_BAD_REQUEST)
        reopened = self.api("post", f"/api/v1/attendance/registers/{register['id']}/reopen/", {"version": finalized.data["version"], "reason": "Corrected a data entry error"})
        self.assertEqual(reopened.status_code, status.HTTP_200_OK, reopened.data)
        corrected = self.api("patch", f"/api/v1/attendance/registers/{register['id']}/records/", {
            "version": reopened.data["version"], "records": [{"student_id": self.student_a.pk, "status": "absent", "reason": "Teacher confirmed absence"}],
        })
        self.assertEqual(corrected.status_code, status.HTTP_200_OK, corrected.data)
        events = AttendanceAuditEvent.objects.filter(register_id=register["id"])
        self.assertTrue(events.filter(event_type=AttendanceAuditEvent.EventType.REOPENED, reason="Corrected a data entry error").exists())
        self.assertTrue(events.filter(event_type=AttendanceAuditEvent.EventType.CORRECTED, reason="Teacher confirmed absence").exists())

    def test_historical_enrollment_eligibility_and_atomic_foreign_student_rejection(self):
        register = self.create_register(attendance_date="2026-10-15")
        foreign = Student.objects.create(school=self.other_school, admission_number="S-001", first_name="Foreign", last_name="Student")
        before = self.api("patch", f"/api/v1/attendance/registers/{register['id']}/records/", {
            "version": 1, "records": [
                {"student_id": self.student_a.pk, "status": "present"},
                {"student_id": foreign.pk, "status": "absent"},
            ],
        })
        self.assertEqual(before.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(AttendanceRecord.objects.filter(register_id=register["id"], status__isnull=True).count() == 2)

        old_enrollment = self.student_a.enrollments.get()
        old_enrollment.status = StudentEnrollment.Status.TRANSFERRED
        old_enrollment.transfer_date = date(2026, 10, 16)
        old_enrollment.transfer_reason = "Class move"
        old_enrollment.save()
        self.assertEqual(AttendanceRecord.objects.get(register_id=register["id"], student=self.student_a).enrollment_id, old_enrollment.pk)
        # The new placement starts on the transfer date, so it is not eligible in the old class on the prior register date.
        self.assertEqual(AttendanceRecord.objects.filter(register__attendance_date=date(2026, 10, 16), student=self.student_a).count(), 0)

    def test_offline_grant_is_scoped_short_lived_and_stored_as_a_digest(self):
        register = self.create_register()
        grant_response = self.api("post", "/api/v1/attendance/offline/grants/", {"register_id": register["id"]})

        self.assertEqual(grant_response.status_code, status.HTTP_201_CREATED, grant_response.data)
        grant = OfflineAttendanceGrant.objects.get(pk=grant_response.data["grant_id"])
        self.assertNotEqual(grant.token_digest, grant_response.data["token"])
        self.assertEqual(grant.token_digest, hashlib.sha256(grant_response.data["token"].encode()).hexdigest())
        self.assertGreaterEqual((grant.expires_at - timezone.now()).total_seconds(), 23 * 60 * 60)

        second_grant = self.api("post", "/api/v1/attendance/offline/grants/", {"register_id": register["id"]})
        self.assertEqual(second_grant.status_code, status.HTTP_201_CREATED, second_grant.data)
        grant.refresh_from_db()
        self.assertIsNotNone(grant.revoked_at)

    def test_offline_sync_revalidates_access_and_is_safe_to_retry(self):
        register = self.create_register(user=self.teacher_user)
        self.client.force_authenticate(self.teacher_user)
        prepared = self.api("post", "/api/v1/attendance/offline/grants/", {"register_id": register["id"]})
        self.assertEqual(prepared.status_code, status.HTTP_201_CREATED, prepared.data)
        token = prepared.data["token"]
        sync_id = str(uuid4())
        payload = {
            "version": 1,
            "sync_id": sync_id,
            "records": [
                {"student_id": self.student_a.pk, "status": "present", "note": ""},
                {"student_id": self.student_b.pk, "status": "late", "note": ""},
            ],
        }
        self.client.force_authenticate(user=None)

        saved = self.client.post(
            "/api/v1/attendance/offline/sync/", payload, format="json",
            HTTP_AUTHORIZATION=f"Offline {token}",
        )
        replay = self.client.post(
            "/api/v1/attendance/offline/sync/", payload, format="json",
            HTTP_AUTHORIZATION=f"Offline {token}",
        )

        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.assertEqual(replay.status_code, status.HTTP_200_OK, replay.data)
        self.assertEqual(replay.data["version"], 2)
        self.assertEqual(AttendanceRecord.objects.filter(register_id=register["id"], status__isnull=False).count(), 2)
        self.assertEqual(AttendanceAuditEvent.objects.filter(register_id=register["id"], event_type=AttendanceAuditEvent.EventType.RECORDED).count(), 2)

        changed_replay = {**payload, "records": [{"student_id": self.student_a.pk, "status": "absent"}]}
        conflict = self.client.post(
            "/api/v1/attendance/offline/sync/", changed_replay, format="json",
            HTTP_AUTHORIZATION=f"Offline {token}",
        )
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(AttendanceRecord.objects.get(register_id=register["id"], student=self.student_a).status, "present")

    def test_offline_sync_cannot_be_used_after_membership_revocation(self):
        register = self.create_register(user=self.teacher_user)
        self.client.force_authenticate(self.teacher_user)
        prepared = self.api("post", "/api/v1/attendance/offline/grants/", {"register_id": register["id"]})
        self.assertEqual(prepared.status_code, status.HTTP_201_CREATED, prepared.data)
        SchoolMembership.objects.filter(user=self.teacher_user, school=self.school).update(is_active=False)
        self.client.force_authenticate(user=None)

        denied = self.client.post(
            "/api/v1/attendance/offline/sync/",
            {"version": 1, "sync_id": str(uuid4()), "records": [{"student_id": self.student_a.pk, "status": "present"}]},
            format="json", HTTP_AUTHORIZATION=f"Offline {prepared.data['token']}",
        )

        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIsNone(AttendanceRecord.objects.get(register_id=register["id"], student=self.student_a).status)

