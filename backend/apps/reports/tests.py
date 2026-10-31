from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, GradeBand, GradingScale, Subject, Term
from apps.attendance.models import AttendanceRecord, AttendanceRegister
from apps.billing.models import CreditAccount, CreditPayment, CreditTransaction
from apps.report_cards.models import ReportCard
from apps.results.models import AssessmentPlan, AssessmentResult
from apps.schools.models import School, SchoolMembership
from apps.staff.models import StaffProfile, TeacherAssignment, TeacherProfile
from apps.students.models import Student, StudentEnrollment

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class SchoolReportsApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Reports North", slug="reports-north")
        self.other_school = School.objects.create(name="Reports South", slug="reports-south")
        self.admin = self.make_user("reports-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.manager = self.make_user("reports-manager", SchoolMembership.Role.SCHOOL_MANAGER, self.school)
        self.teacher_user = self.make_user("reports-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.accountant = self.make_user("reports-accountant", SchoolMembership.Role.ACCOUNTANT, self.school)
        self.receptionist = self.make_user("reports-frontdesk", SchoolMembership.Role.RECEPTIONIST, self.school)
        self.other_admin = self.make_user("reports-other-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client = APIClient()
        self.session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        self.session.status = AcademicSession.Status.ACTIVE
        self.session.save()
        self.term = Term.objects.create(school=self.school, academic_session=self.session, name="First Term", sequence=1, start_date=date(2026, 9, 1), end_date=date(2026, 12, 20))
        self.term.status = Term.Status.ACTIVE
        self.term.save()
        self.level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1")
        self.arm_a = ClassArm.objects.create(school=self.school, class_level=self.level, name="A")
        self.arm_b = ClassArm.objects.create(school=self.school, class_level=self.level, name="B")
        self.subject = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        self.scale = GradingScale.objects.create(school=self.school, name="Default", maximum_score=Decimal("100"))
        GradeBand.objects.create(school=self.school, grading_scale=self.scale, label="A", min_score=Decimal("0"), max_score=Decimal("100"))
        self.scale.is_active = True
        self.scale.save()
        self.students_a = [self.make_student("RP-001", "Ada", self.arm_a), self.make_student("RP-002", "=SUM(1,1)", self.arm_a)]
        self.student_b = self.make_student("RP-003", "Bola", self.arm_b)
        staff = StaffProfile.objects.create(school=self.school, user=self.teacher_user, staff_number="RPT-1", first_name="Teacher", last_name="One", job_title="Teacher", employment_start_date=date(2026, 9, 1))
        teacher = TeacherProfile.objects.create(school=self.school, staff=staff)
        TeacherAssignment.objects.create(school=self.school, teacher=teacher, academic_session=self.session, class_level=self.level, class_arm=self.arm_a, subject=self.subject, start_date=date(2026, 9, 1))

    def make_user(self, username, role, school):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def make_student(self, admission, first_name, arm):
        student = Student.objects.create(school=self.school, admission_number=admission, first_name=first_name, last_name="Learner", admission_date=date(2026, 9, 2))
        StudentEnrollment.objects.create(school=self.school, student=student, academic_session=self.session, class_level=self.level, class_arm=arm, enrollment_date=date(2026, 9, 2), status=StudentEnrollment.Status.ACTIVE)
        return student

    def api(self, method, path, user=None, school=None):
        self.client.force_authenticate(user or self.admin)
        return getattr(self.client, method)(path, HTTP_X_SCHOOL_ID=str((school or self.school).pk))

    def test_dashboard_uses_current_session_and_separates_available_sections_by_role(self):
        response = self.api("get", "/api/v1/reports/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["metrics"]["currently_enrolled"], 3)
        self.assertIn("attendance", response.data["available_sections"])
        self.assertIn("finance", response.data["available_sections"])
        accounting = self.api("get", "/api/v1/reports/dashboard/", user=self.accountant)
        self.assertEqual(accounting.status_code, status.HTTP_200_OK)
        self.assertEqual(accounting.data["available_sections"], ["finance"])
        self.assertNotIn("currently_enrolled", accounting.data["metrics"])
        teacher = self.api("get", "/api/v1/reports/dashboard/", user=self.teacher_user)
        self.assertNotIn("enrollment", teacher.data["available_sections"])
        self.assertEqual(teacher.data["metrics"]["currently_enrolled"], 2)
        self.assertNotIn("new_admissions", teacher.data["metrics"])

    def test_enrollment_historical_status_filters_and_csv_formula_protection(self):
        enrollment = StudentEnrollment.objects.get(student=self.students_a[0])
        enrollment.status = StudentEnrollment.Status.WITHDRAWN
        enrollment.withdrawal_date = date(2026, 10, 5)
        enrollment.save()
        response = self.api("get", "/api/v1/reports/enrollment/?session=1&start_date=2026-10-01&end_date=2026-10-31")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["outcomes"]["withdrawn"], 1)
        students = self.api("get", "/api/v1/reports/enrollment/?view=students&page_size=1")
        self.assertEqual(students.status_code, status.HTTP_200_OK)
        self.assertEqual(students.data["students"]["count"], 3)
        self.assertEqual(len(students.data["students"]["results"]), 1)
        exported = self.api("get", "/api/v1/reports/enrollment/?view=students&export=csv")
        body = b"".join(exported.streaming_content).decode("utf-8")
        self.assertIn("'=SUM(1,1)", body)
        self.assertNotIn("\n=SUM(1,1)", body)

    def test_attendance_counts_only_finalized_marked_records_and_teacher_assignment_scope(self):
        for arm, students in ((self.arm_a, self.students_a), (self.arm_b, [self.student_b])):
            register = AttendanceRegister.objects.create(school=self.school, academic_session=self.session, term=self.term, class_level=self.level, class_arm=arm, attendance_date=date(2026, 10, 5), status=AttendanceRegister.Status.FINALIZED, created_by=self.admin)
            for student, state in zip(students, (AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.ABSENT)):
                AttendanceRecord.objects.create(school=self.school, register=register, student=student, enrollment=student.enrollments.get(), status=state, recorded_by=self.admin)
            draft = AttendanceRegister.objects.create(school=self.school, academic_session=self.session, term=self.term, class_level=self.level, class_arm=arm, attendance_date=date(2026, 10, 6), status=AttendanceRegister.Status.DRAFT, created_by=self.admin)
            AttendanceRecord.objects.create(school=self.school, register=draft, student=students[0], enrollment=students[0].enrollments.get(), status=AttendanceRecord.Status.ABSENT, recorded_by=self.admin)
        response = self.api("get", "/api/v1/reports/attendance/?start_date=2026-10-01&end_date=2026-10-31")
        self.assertEqual(response.data["summary"]["total"], 3)
        self.assertEqual(response.data["summary"]["attendance_percentage"], 66.67)
        teacher = self.api("get", "/api/v1/reports/attendance/?start_date=2026-10-01&end_date=2026-10-31", user=self.teacher_user)
        self.assertEqual(teacher.data["summary"]["total"], 2)
        by_student = self.api("get", "/api/v1/reports/attendance/?view=students&page_size=1&start_date=2026-10-01&end_date=2026-10-31")
        self.assertEqual(by_student.data["count"], 3)

    def test_academic_performance_uses_only_approved_result_totals(self):
        plan = AssessmentPlan.objects.create(school=self.school, academic_session=self.session, term=self.term, class_level=self.level, class_arm=self.arm_a, subject=self.subject, grading_scale=self.scale, grading_scale_snapshot={"maximum_score": "100", "bands": [{"label": "A", "min_score": "0", "max_score": "100"}]}, name="Mathematics assessment", created_by=self.admin)
        approved = AssessmentResult.objects.create(school=self.school, plan=plan, student=self.students_a[0], enrollment=self.students_a[0].enrollments.get(), status=AssessmentResult.Status.APPROVED, approved_percentage=Decimal("80"), approved_grade="A")
        AssessmentResult.objects.create(school=self.school, plan=plan, student=self.students_a[1], enrollment=self.students_a[1].enrollments.get(), status=AssessmentResult.Status.DRAFT)
        response = self.api("get", "/api/v1/reports/academics/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["plans"][0]["average_approved_percentage"], 80.0)
        self.assertEqual(response.data["plans"][0]["approved"], 1)
        self.assertEqual(response.data["plans"][0]["draft"], 1)

    def test_report_card_completion_includes_classes_with_no_generated_cards(self):
        enrollment = self.students_a[0].enrollments.get()
        ReportCard.objects.create(school=self.school, student=self.students_a[0], enrollment=enrollment, academic_session=self.session, term=self.term, class_level=self.level, class_arm=self.arm_a, identifier="RC-001", status=ReportCard.Status.FINALIZED, created_by=self.admin)
        response = self.api("get", "/api/v1/reports/report-cards/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rows = {row["arm_name"]: row for row in response.data["classes"]}
        self.assertEqual(rows["A"]["expected_students"], 2)
        self.assertEqual(rows["A"]["publication_percentage"], 50.0)
        self.assertEqual(rows["B"]["published"], 0)
        self.assertEqual(rows["B"]["publication_percentage"], 0.0)

    def test_financial_reports_are_school_scoped_and_use_only_successful_payment_revenue(self):
        CreditAccount.objects.create(school=self.school, balance=7)
        payment = CreditPayment.objects.create(school=self.school, package_name="Test pack", credits=10, amount_minor=100000, currency="NGN", reference="REPORT-OK", status=CreditPayment.Status.SUCCESS, customer_email="payer@example.test", created_by=self.admin)
        CreditPayment.objects.create(school=self.school, package_name="Pending pack", credits=5, amount_minor=50000, currency="NGN", reference="REPORT-PENDING", status=CreditPayment.Status.PENDING, customer_email="payer@example.test", created_by=self.admin)
        CreditTransaction.objects.create(school=self.school, kind=CreditTransaction.Kind.PURCHASE, amount=10, description="Verified purchase", payment=payment, reference_key="reports:purchase")
        manager = self.api("get", "/api/v1/reports/finance/", user=self.manager)
        self.assertEqual(manager.status_code, status.HTTP_403_FORBIDDEN)
        report = self.api("get", "/api/v1/reports/finance/", user=self.accountant)
        self.assertEqual(report.status_code, status.HTTP_200_OK)
        self.assertEqual(report.data["gross_successful_purchases_ngn"], 1000.0)
        hidden = self.api("get", "/api/v1/reports/finance/", user=self.other_admin, school=self.other_school)
        self.assertEqual(hidden.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden.data["successful_purchases"], 0)
        export = self.api("get", "/api/v1/reports/finance/?export=csv", user=self.accountant)
        self.assertIn("REPORT-OK", b"".join(export.streaming_content).decode("utf-8"))

    def test_cross_school_filters_and_unauthorized_export_are_denied(self):
        other_session = AcademicSession.objects.create(school=self.other_school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        response = self.api("get", f"/api/v1/reports/enrollment/?session={other_session.pk}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        denied = self.api("get", "/api/v1/reports/finance/?export=csv", user=self.manager)
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        guardian = self.make_user("reports-guardian", SchoolMembership.Role.MEMBER, self.school)
        parent_denied = self.api("get", "/api/v1/reports/dashboard/", user=guardian)
        self.assertEqual(parent_denied.status_code, status.HTTP_403_FORBIDDEN)
        not_member = self.api("get", "/api/v1/reports/dashboard/", user=self.other_admin)
        self.assertEqual(not_member.status_code, status.HTTP_403_FORBIDDEN)
