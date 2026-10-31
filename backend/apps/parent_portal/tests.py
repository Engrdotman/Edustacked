import re
from datetime import date, timedelta

from django.core import mail
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status

from apps.academics.models import AcademicSession, Term
from apps.attendance.models import AttendanceRecord, AttendanceRegister
from apps.parent_portal.models import Announcement, GuardianInvitation, PortalAuditEvent, PortalNotification
from apps.report_cards.models import ReportCard, ReportCardRevision
from apps.schools.models import School, SchoolMembership
from apps.academics.models import ClassArm, ClassLevel
from apps.students.models import Guardian, Student, StudentEnrollment, StudentGuardian
from rest_framework.test import APIClient


@override_settings(
    PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",),
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_BASE_URL="https://school.example.test",
)
class ParentPortalApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North Academy", slug="north-academy")
        self.other = School.objects.create(name="South Academy", slug="south-academy")
        self.admin = self.make_user("portal-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.receptionist = self.make_user("portal-reception", SchoolMembership.Role.RECEPTIONIST, self.school)
        self.teacher = self.make_user("portal-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.accountant = self.make_user("portal-accountant", SchoolMembership.Role.ACCOUNTANT, self.school)
        self.other_admin = self.make_user("portal-other-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        AcademicSession.objects.filter(pk=self.session.pk).update(status="active")
        self.session.refresh_from_db()
        self.level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1", category="junior_secondary")
        self.arm = ClassArm.objects.create(school=self.school, class_level=self.level, name="A")
        admitted = self.enrolled_admission("P-001")
        self.student = Student.objects.get(pk=admitted["id"])
        self.term = Term.objects.create(
            school=self.school, academic_session=self.session, name="First Term", sequence=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 20),
        )
        self.guardian = Guardian.objects.create(school=self.school, full_name="Grace Okafor", phone="555-0101", email="grace@example.test")
        self.link = StudentGuardian.objects.create(school=self.school, student=self.student, guardian=self.guardian, relationship_type="mother")
        self.parent = self.make_user("parent-grace", SchoolMembership.Role.MEMBER, self.school)
        self.guardian.user = self.parent
        self.guardian.save(update_fields=("user", "updated_at"))
        self.client.force_authenticate(self.parent)

    @staticmethod
    def make_user(username, role, school):
        user = get_user_model().objects.create_user(username=username, email=f"{username}@example.test", password="test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def api(self, method, path, data=None, school=None):
        return getattr(self.client, method)(path, data, HTTP_X_SCHOOL_ID=str((school or self.school).pk), format="json")

    def admission(self, admission_number="P-001", **extra):
        return self.api("post", "/api/v1/admissions/", {
            "student": {"admission_number": admission_number, "first_name": "Ada", "last_name": "Okafor"},
            **extra,
        })

    def enrolled_admission(self, admission_number="P-001"):
        response = self.admission(admission_number, enrollment={
            "academic_session": self.session.pk, "class_level": self.level.pk,
            "class_arm": self.arm.pk, "enrollment_date": "2026-09-01", "status": "active",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def test_profile_linked_students_multi_student_selection_and_idor_denial(self):
        profile = self.api("get", "/api/v1/parent/profile/")
        self.assertEqual(profile.status_code, status.HTTP_200_OK, profile.data)
        self.assertEqual(profile.data["email"], self.parent.email)
        overview = self.api("get", "/api/v1/parent/students/")
        self.assertEqual(overview.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in overview.data], [self.student.pk])
        self.assertEqual(overview.data[0]["enrollment"]["class_name"], self.level.name)

        another = Student.objects.create(school=self.school, admission_number="P-002", first_name="Tomi", last_name="Okafor")
        StudentEnrollment.objects.create(school=self.school, student=another, academic_session=self.session, class_level=self.level, class_arm=self.arm, enrollment_date=date(2026, 9, 1), status=StudentEnrollment.Status.ACTIVE)
        StudentGuardian.objects.create(school=self.school, student=another, guardian=self.guardian, relationship_type="mother")
        overview = self.api("get", "/api/v1/parent/students/")
        self.assertEqual({item["id"] for item in overview.data}, {self.student.pk, another.pk})
        self.assertEqual(self.api("get", f"/api/v1/parent/students/{another.pk}/").status_code, status.HTTP_200_OK)

        unlinked = Student.objects.create(school=self.school, admission_number="P-003", first_name="Private", last_name="Student")
        self.assertEqual(self.api("get", f"/api/v1/parent/students/{unlinked.pk}/").status_code, status.HTTP_404_NOT_FOUND)
        foreign = Student.objects.create(school=self.other, admission_number="X-001", first_name="Other", last_name="School")
        self.assertEqual(self.api("get", f"/api/v1/parent/students/{foreign.pk}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(PortalAuditEvent.objects.filter(actor=self.parent, action="unauthorized_student_access").exists())

    def test_link_revocation_immediately_removes_portal_access(self):
        self.assertEqual(self.api("get", f"/api/v1/parent/students/{self.student.pk}/").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.admin)
        revoked = self.api("delete", f"/api/v1/students/{self.student.pk}/guardians/{self.link.pk}/")
        self.assertEqual(revoked.status_code, status.HTTP_204_NO_CONTENT)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.api("get", f"/api/v1/parent/students/{self.student.pk}/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(PortalAuditEvent.objects.filter(student_link=self.link, action="guardian_student_link_revoked").exists())

    def test_attendance_uses_finalized_records_only_and_omits_staff_notes(self):
        finalized = AttendanceRegister.objects.create(school=self.school, academic_session=self.session, term=self.term, class_level=self.level, class_arm=self.arm, attendance_date=date(2026, 10, 5), status=AttendanceRegister.Status.FINALIZED, created_by=self.admin, finalized_by=self.admin)
        draft = AttendanceRegister.objects.create(school=self.school, academic_session=self.session, term=finalized.term, class_level=self.level, class_arm=self.arm, attendance_date=date(2026, 10, 6), status=AttendanceRegister.Status.DRAFT, created_by=self.admin)
        AttendanceRecord.objects.create(school=self.school, register=finalized, student=self.student, enrollment=self.student.enrollments.get(), status=AttendanceRecord.Status.LATE, note="Private staff note", recorded_by=self.admin, last_modified_by=self.admin)
        AttendanceRecord.objects.create(school=self.school, register=draft, student=self.student, enrollment=self.student.enrollments.get(), status=AttendanceRecord.Status.ABSENT, recorded_by=self.admin, last_modified_by=self.admin)
        report = self.api("get", f"/api/v1/parent/students/{self.student.pk}/attendance/?start_date=2026-10-01&end_date=2026-10-31")
        self.assertEqual(report.status_code, status.HTTP_200_OK, report.data)
        self.assertEqual(report.data["summary"]["total"], 1)
        self.assertEqual(report.data["summary"]["late"], 1)
        self.assertEqual(report.data["summary"]["attendance_percentage"], 100.0)
        self.assertEqual(len(report.data["results"]), 1)
        self.assertNotIn("note", report.data["results"][0])

    def create_report_card(self, student, enrollment, *, finalized):
        now = timezone.now()
        card = ReportCard.objects.create(
            school=student.school, student=student, enrollment=enrollment,
            academic_session=enrollment.academic_session, term=self.term,
            class_level=enrollment.class_level, class_arm=enrollment.class_arm,
            identifier=f"PORTAL-{student.pk}", created_by=self.admin,
            status=ReportCard.Status.FINALIZED if finalized else ReportCard.Status.DRAFT,
            finalized_by=self.admin if finalized else None,
            finalized_at=now if finalized else None,
        )
        snapshot = {
            "school": {"name": student.school.name, "primary_color": "#285744"},
            "academic": {"session": enrollment.academic_session.name, "term": self.term.name},
            "student": {"name": f"{student.first_name} {student.last_name}", "admission_number": student.admission_number, "class_name": enrollment.class_level.name, "arm_name": enrollment.class_arm.name},
            "subjects": [{"subject_id": 1, "subject_name": "Mathematics", "components": [], "total": "80", "maximum": "100", "percentage": "80", "grade": "A", "grade_description": "Excellent"}],
            "attendance": {"present": 4, "absent": 0, "late": 1, "excused": 0, "attendance_percentage": 100},
            "remarks": {"teacher": "Good effort", "head_teacher": "Keep it up", "conduct": "Good", "effort": "Excellent"},
            "signatures": {},
        }
        revision = ReportCardRevision.objects.create(
            report_card=card, revision_number=1,
            status=ReportCardRevision.Status.FINALIZED if finalized else ReportCardRevision.Status.DRAFT,
            snapshot=snapshot, generated_by=self.admin,
            finalized_by=self.admin if finalized else None,
            finalized_at=now if finalized else None,
        )
        return card, revision

    def test_only_finalized_report_cards_and_authorized_pdf_are_available(self):
        enrollment = self.student.enrollments.get()
        card, published = self.create_report_card(self.student, enrollment, finalized=True)
        other = Student.objects.create(school=self.school, admission_number="P-DRAFT", first_name="Draft", last_name="Child")
        other_enrollment = StudentEnrollment.objects.create(school=self.school, student=other, academic_session=self.session, class_level=self.level, class_arm=self.arm, enrollment_date=date(2026, 9, 1), status=StudentEnrollment.Status.ACTIVE)
        draft_card, draft = self.create_report_card(other, other_enrollment, finalized=False)
        reports = self.api("get", f"/api/v1/parent/students/{self.student.pk}/report-cards/")
        self.assertEqual(reports.status_code, status.HTTP_200_OK, reports.data)
        self.assertEqual([item["id"] for item in reports.data], [published.pk])
        detail = self.api("get", f"/api/v1/parent/report-cards/{published.pk}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        self.assertEqual(detail.data["snapshot"]["subjects"][0]["grade"], "A")
        pdf = self.api("get", f"/api/v1/parent/report-cards/{published.pk}/pdf/")
        self.assertEqual(pdf.status_code, status.HTTP_200_OK)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(self.api("get", f"/api/v1/parent/report-cards/{draft.pk}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.api("get", f"/api/v1/parent/report-cards/{draft.pk}/pdf/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.api("get", "/api/v1/parent/students/999999/report-cards/").status_code, status.HTTP_404_NOT_FOUND)

    def test_invitation_is_emailed_once_and_token_is_single_use(self):
        new_guardian = Guardian.objects.create(school=self.school, full_name="Musa Okafor", phone="555-0102", email="musa@example.test")
        link = StudentGuardian.objects.create(school=self.school, student=self.student, guardian=new_guardian, relationship_type="father")
        self.client.force_authenticate(self.admin)
        response = self.api("post", f"/api/v1/parent/staff/students/{self.student.pk}/guardians/{link.pk}/invite/", {})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        self.assertNotIn("token", response.data)
        invitation = GuardianInvitation.objects.get(guardian=new_guardian)
        token = re.search(r"token=([^\s]+)", mail.outbox[-1].body).group(1)
        self.assertNotEqual(invitation.token_hash, token)
        self.client.force_authenticate(user=None)
        activated = self.client.post("/api/v1/guardian/activate/", {"token": token, "password": "Strong-Parent-Password-42!"}, format="json")
        self.assertEqual(activated.status_code, status.HTTP_200_OK, activated.data)
        self.assertNotIn("token", activated.data)
        invitation.refresh_from_db()
        new_guardian.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)
        self.assertIsNotNone(new_guardian.user_id)
        again = self.client.post("/api/v1/guardian/activate/", {"token": token, "password": "Strong-Parent-Password-42!"}, format="json")
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_invitation_is_rejected(self):
        new_guardian = Guardian.objects.create(school=self.school, full_name="Expired Guardian", phone="555-0103", email="expired@example.test")
        link = StudentGuardian.objects.create(school=self.school, student=self.student, guardian=new_guardian, relationship_type="aunt")
        self.client.force_authenticate(self.admin)
        response = self.api("post", f"/api/v1/parent/staff/students/{self.student.pk}/guardians/{link.pk}/invite/", {})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        invitation = GuardianInvitation.objects.get(guardian=new_guardian)
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save(update_fields=("expires_at",))
        token = re.search(r"token=([^\s]+)", mail.outbox[-1].body).group(1)
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/v1/guardian/activate/", {"token": token, "password": "Strong-Parent-Password-42!"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(new_guardian.user_id)

    def test_announcements_are_published_school_scoped_and_notify_once(self):
        self.client.force_authenticate(self.admin)
        created = self.api("post", "/api/v1/parent/staff/announcements/", {"title": "Sports day", "message": "Families are invited."})
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.api("get", "/api/v1/parent/announcements/").data["results"], [])
        self.client.force_authenticate(self.admin)
        published = self.api("post", f"/api/v1/parent/staff/announcements/{created.data['id']}/publish/", {})
        self.assertEqual(published.status_code, status.HTTP_200_OK, published.data)
        self.client.force_authenticate(self.parent)
        visible = self.api("get", "/api/v1/parent/announcements/")
        self.assertEqual([item["title"] for item in visible.data["results"]], ["Sports day"])
        self.assertEqual(PortalNotification.objects.filter(user=self.parent, event_key=f"announcement:{created.data['id']}:published").count(), 1)
        notice = self.api("get", "/api/v1/parent/notifications/")
        self.assertEqual(notice.status_code, status.HTTP_200_OK)
        self.assertTrue(notice.data["results"])
        self.assertEqual(self.api("post", "/api/v1/parent/staff/announcements/", {"title": "No", "message": "No"}).status_code, status.HTTP_403_FORBIDDEN)

    def test_announcement_expiry_must_follow_publication(self):
        self.client.force_authenticate(self.admin)
        created = self.api("post", "/api/v1/parent/staff/announcements/", {
            "title": "Expired notice", "message": "This cannot be published.",
            "expires_at": (timezone.now() - timedelta(days=1)).isoformat(),
        })
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        published = self.api("post", f"/api/v1/parent/staff/announcements/{created.data['id']}/publish/", {})
        self.assertEqual(published.status_code, status.HTTP_400_BAD_REQUEST, published.data)
        self.assertEqual(Announcement.objects.get(pk=created.data["id"]).status, Announcement.Status.DRAFT)

    def test_guardian_cannot_access_staff_or_billing_operations(self):
        for path in ("/api/v1/students/", "/api/v1/attendance/registers/", "/api/v1/assessment-plans/", "/api/v1/billing/credits/"):
            response = self.api("get", path)
            self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND), (path, response.data))

