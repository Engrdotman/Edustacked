from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, ClassSubject, GradeBand, GradingScale, Subject, Term
from apps.attendance.models import AttendanceRecord, AttendanceRegister
from apps.billing.models import CreditAccount
from apps.results.models import AssessmentPlan, AssessmentResult
from apps.schools.models import School, SchoolMembership
from apps.staff.models import StaffProfile, TeacherAssignment, TeacherProfile
from apps.students.models import Student, StudentEnrollment

from .models import ReportCard, ReportCardAuditEvent, ReportCardRevision

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class ReportCardApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Report Card Academy", slug="report-card-academy", address="12 Learning Road", motto="Learn well")
        CreditAccount.objects.create(school=self.school, balance=20)
        self.other_school = School.objects.create(name="Another Academy", slug="another-academy")
        self.admin = self.make_user("report-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.manager = self.make_user("report-manager", SchoolMembership.Role.SCHOOL_MANAGER, self.school)
        self.teacher_user = self.make_user("report-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.receptionist = self.make_user("report-frontdesk", SchoolMembership.Role.RECEPTIONIST, self.school)
        self.other_admin = self.make_user("report-other-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        AcademicSession.objects.filter(pk=self.session.pk).update(status=AcademicSession.Status.ACTIVE)
        self.session.refresh_from_db()
        self.term = Term.objects.create(school=self.school, academic_session=self.session, name="First Term", sequence=1, start_date=date(2026, 9, 1), end_date=date(2026, 12, 20))
        self.level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1")
        self.arm = ClassArm.objects.create(school=self.school, class_level=self.level, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        ClassSubject.objects.create(school=self.school, class_level=self.level, subject=self.subject)
        staff = StaffProfile.objects.create(school=self.school, user=self.teacher_user, staff_number="T-RPT-1", first_name="Tola", last_name="Teacher", job_title="Teacher", employment_start_date=date(2026, 9, 1))
        teacher = TeacherProfile.objects.create(school=self.school, staff=staff)
        TeacherAssignment.objects.create(school=self.school, teacher=teacher, academic_session=self.session, class_level=self.level, class_arm=self.arm, subject=self.subject, start_date=date(2026, 9, 1))
        self.student = Student.objects.create(school=self.school, admission_number="RPT-001", first_name="Ada", last_name="Learner", gender=Student.Gender.FEMALE)
        self.enrollment = StudentEnrollment.objects.create(school=self.school, student=self.student, academic_session=self.session, class_level=self.level, class_arm=self.arm, enrollment_date=date(2026, 9, 1), status=StudentEnrollment.Status.ACTIVE)
        self.scale = self.create_scale()
        self.scale_snapshot = {"scale_id": self.scale.pk, "name": "Standard", "maximum_score": "100.00", "bands": [{"label": "F", "min_score": "0.00", "max_score": "69.99", "grade_point": "0.00"}, {"label": "A", "min_score": "70.00", "max_score": "100.00", "grade_point": "4.00"}]}
        self.plan = AssessmentPlan.objects.create(school=self.school, academic_session=self.session, term=self.term, class_level=self.level, class_arm=self.arm, subject=self.subject, grading_scale=self.scale, name="First Term Assessment", grading_scale_snapshot=self.scale_snapshot, status=AssessmentPlan.Status.PUBLISHED, created_by=self.admin)
        self.result = AssessmentResult.objects.create(school=self.school, plan=self.plan, student=self.student, enrollment=self.enrollment, status=AssessmentResult.Status.APPROVED, approved_total=Decimal("85.50"), approved_maximum=Decimal("100.00"), approved_percentage=Decimal("85.50"), approved_grade="A", approved_grade_point=Decimal("4.00"), approved_calculation={"complete": True, "components": [{"name": "Test", "score": "18.50", "max_score": "20.00"}, {"name": "Examination", "score": "67.00", "max_score": "80.00"}], "calculated_total": "85.50", "calculated_maximum": "100.00", "percentage": "85.50", "grade": "A", "grade_point": "4.00"})

    def create_scale(self):
        scale = GradingScale.objects.create(school=self.school, name="Standard", maximum_score=Decimal("100"), is_active=False)
        GradeBand.objects.create(school=self.school, grading_scale=scale, label="F", min_score=Decimal("0.00"), max_score=Decimal("69.99"), grade_point=Decimal("0.00"))
        GradeBand.objects.create(school=self.school, grading_scale=scale, label="A", min_score=Decimal("70.00"), max_score=Decimal("100.00"), grade_point=Decimal("4.00"))
        scale.is_active = True
        scale.save()
        return scale

    def make_user(self, username, role, school):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def api(self, method, path, data=None, school=None):
        return getattr(self.client, method)(path, data, HTTP_X_SCHOOL_ID=str((school or self.school).pk), format="json")

    def generate(self):
        response = self.api("post", "/api/v1/report-cards/generate/", {"enrollment": self.enrollment.pk, "term": self.term.pk})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data["report_card"]

    def test_generation_uses_approved_grade_and_finalized_attendance_only(self):
        register = AttendanceRegister.objects.create(school=self.school, academic_session=self.session, term=self.term, class_level=self.level, class_arm=self.arm, attendance_date=date(2026, 10, 5), status=AttendanceRegister.Status.FINALIZED, created_by=self.admin, finalized_by=self.admin)
        AttendanceRecord.objects.create(school=self.school, register=register, student=self.student, enrollment=self.enrollment, status=AttendanceRecord.Status.LATE, recorded_by=self.admin, last_modified_by=self.admin)
        AttendanceRegister.objects.create(school=self.school, academic_session=self.session, term=self.term, class_level=self.level, class_arm=self.arm, attendance_date=date(2026, 10, 6), status=AttendanceRegister.Status.DRAFT, created_by=self.admin)
        card = self.generate()
        snapshot = card["current"]["snapshot"]
        self.assertEqual(snapshot["subjects"][0]["total"], "85.50")
        self.assertEqual(snapshot["subjects"][0]["grade"], "A")
        self.assertEqual(snapshot["attendance"]["late"], 1)
        self.assertEqual(snapshot["attendance"]["register_days_with_record"], 1)
        self.assertIsNone(snapshot["overall"])

    def test_unapproved_results_block_review_and_bulk_generation_reports_issues(self):
        AssessmentResult.objects.filter(pk=self.result.pk).update(status=AssessmentResult.Status.DRAFT)
        card = self.generate()
        self.assertTrue(card["current"]["validation_errors"])
        review = self.api("post", f"/api/v1/report-cards/{card['id']}/review/", {})
        self.assertEqual(review.status_code, status.HTTP_400_BAD_REQUEST)
        batch = self.api("post", "/api/v1/report-cards/generate-class/", {"academic_session": self.session.pk, "term": self.term.pk, "class_level": self.level.pk, "class_arm": self.arm.pk})
        self.assertEqual(batch.status_code, status.HTTP_200_OK, batch.data)
        self.assertEqual(batch.data["generated"], 1)
        self.assertEqual(batch.data["failed"], 0)

    def test_lifecycle_final_snapshot_pdf_and_correction_revision(self):
        card = self.generate()
        remarks = self.api("patch", f"/api/v1/report-cards/{card['id']}/", {"teacher": "Good progress this term."})
        self.assertEqual(remarks.status_code, status.HTTP_200_OK, remarks.data)
        review = self.api("post", f"/api/v1/report-cards/{card['id']}/review/", {})
        self.assertEqual(review.status_code, status.HTTP_200_OK, review.data)
        approved = self.api("post", f"/api/v1/report-cards/{card['id']}/approve/", {})
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        finalized = self.api("post", f"/api/v1/report-cards/{card['id']}/finalize/", {})
        self.assertEqual(finalized.status_code, status.HTTP_200_OK, finalized.data)
        self.assertEqual(finalized.data["status"], ReportCard.Status.FINALIZED)
        original = finalized.data["current"]["snapshot"]
        pdf = self.api("get", f"/api/v1/report-cards/{card['id']}/pdf/")
        self.assertEqual(pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.result.approved_total = Decimal("99.00")
        self.result.approved_percentage = Decimal("99.00")
        self.result.approved_grade = "A+"
        self.result.approved_calculation = {**self.result.approved_calculation, "calculated_total": "99.00", "percentage": "99.00", "grade": "A+"}
        self.result.save()
        self.client.force_authenticate(self.admin)
        correction = self.api("post", f"/api/v1/report-cards/{card['id']}/correct/", {"reason": "Approved assessment result corrected"})
        self.assertEqual(correction.status_code, status.HTTP_200_OK, correction.data)
        self.assertEqual(correction.data["current_revision"], 2)
        self.assertEqual(correction.data["revisions"][1]["snapshot"], original)
        self.assertEqual(correction.data["current"]["snapshot"]["subjects"][0]["total"], "99.00")
        self.assertTrue(ReportCardAuditEvent.objects.filter(report_card_id=card["id"], action="correction_revision_started", reason="Approved assessment result corrected").exists())

    def test_permissions_teacher_scope_and_cross_tenant_access(self):
        card = self.generate()
        self.client.force_authenticate(self.teacher_user)
        permitted = self.api("get", f"/api/v1/report-cards/{card['id']}/")
        self.assertEqual(permitted.status_code, status.HTTP_200_OK, permitted.data)
        self.assertEqual(len(permitted.data["current"]["snapshot"]["subjects"]), 1)
        teacher_pdf = self.api("get", f"/api/v1/report-cards/{card['id']}/pdf/?preview=true")
        self.assertEqual(teacher_pdf.status_code, status.HTTP_200_OK)
        denied_finalize = self.api("post", f"/api/v1/report-cards/{card['id']}/finalize/", {})
        self.assertEqual(denied_finalize.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.other_admin)
        cross_school = self.api("get", f"/api/v1/report-cards/{card['id']}/", school=self.other_school)
        self.assertEqual(cross_school.status_code, status.HTTP_404_NOT_FOUND)
        cross_school_pdf = self.api("get", f"/api/v1/report-cards/{card['id']}/pdf/", school=self.other_school)
        self.assertEqual(cross_school_pdf.status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.receptionist)
        denied = self.api("get", f"/api/v1/report-cards/{card['id']}/")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        denied_pdf = self.api("get", f"/api/v1/report-cards/{card['id']}/pdf/")
        self.assertEqual(denied_pdf.status_code, status.HTTP_403_FORBIDDEN)

    def test_generation_prevents_duplicate_cards_and_source_changes_require_regeneration(self):
        card = self.generate()
        again = self.api("post", "/api/v1/report-cards/generate/", {"enrollment": self.enrollment.pk, "term": self.term.pk})
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(ReportCard.objects.count(), 1)
        self.result.approved_total = Decimal("90.00")
        self.result.save()
        review = self.api("post", f"/api/v1/report-cards/{card['id']}/review/", {})
        self.assertEqual(review.status_code, status.HTTP_400_BAD_REQUEST)
        refreshed = self.api("post", "/api/v1/report-cards/generate/", {"enrollment": self.enrollment.pk, "term": self.term.pk})
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        review = self.api("post", f"/api/v1/report-cards/{card['id']}/review/", {})
        self.assertEqual(review.status_code, status.HTTP_200_OK, review.data)

