from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, GradeBand, GradingScale, Subject, Term
from apps.schools.models import School, SchoolMembership
from apps.staff.models import StaffProfile, TeacherAssignment, TeacherProfile
from apps.students.models import Student, StudentEnrollment
from .models import AssessmentComponent, AssessmentPlan, AssessmentResult, ComponentScore, PlanComponent, ResultAuditEvent

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class AssessmentResultsApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Results North", slug="results-north")
        self.other_school = School.objects.create(name="Results South", slug="results-south")
        self.admin = self.make_user("result-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.manager = self.make_user("result-manager", SchoolMembership.Role.SCHOOL_MANAGER, self.school)
        self.teacher_user = self.make_user("result-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.accountant = self.make_user("result-accountant", SchoolMembership.Role.ACCOUNTANT, self.school)
        self.other_admin = self.make_user("result-other-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        AcademicSession.objects.filter(pk=self.session.pk).update(status=AcademicSession.Status.ACTIVE)
        self.session.refresh_from_db()
        self.term = Term.objects.create(school=self.school, academic_session=self.session, name="First Term", sequence=1, start_date=date(2026, 9, 1), end_date=date(2026, 12, 20))
        self.level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1")
        self.arm = ClassArm.objects.create(school=self.school, class_level=self.level, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        staff = StaffProfile.objects.create(school=self.school, user=self.teacher_user, staff_number="T-RES-1", first_name="Tari", last_name="Teacher", job_title="Teacher", employment_start_date=date(2026, 9, 1))
        teacher = TeacherProfile.objects.create(school=self.school, staff=staff)
        TeacherAssignment.objects.create(school=self.school, teacher=teacher, academic_session=self.session, class_level=self.level, class_arm=self.arm, subject=self.subject, start_date=date(2026, 9, 1))
        self.students = [self.make_student("R-001", "Ada"), self.make_student("R-002", "Bola")]
        self.scale = GradingScale.objects.create(school=self.school, name="Standard 100", maximum_score=Decimal("100.00"))
        GradeBand.objects.create(school=self.school, grading_scale=self.scale, label="F", min_score=Decimal("0.00"), max_score=Decimal("49.99"))
        GradeBand.objects.create(school=self.school, grading_scale=self.scale, label="C", min_score=Decimal("50.00"), max_score=Decimal("69.99"))
        GradeBand.objects.create(school=self.school, grading_scale=self.scale, label="A", min_score=Decimal("70.00"), max_score=Decimal("100.00"))
        self.scale.is_active = True
        self.scale.save()

    def make_user(self, username, role, school):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def make_student(self, admission, first):
        student = Student.objects.create(school=self.school, admission_number=admission, first_name=first, last_name="Learner")
        StudentEnrollment.objects.create(school=self.school, student=student, academic_session=self.session, class_level=self.level, class_arm=self.arm, enrollment_date=date(2026, 9, 1), status=StudentEnrollment.Status.ACTIVE)
        return student

    def api(self, method, path, data=None, school=None):
        return getattr(self.client, method)(path, data, HTTP_X_SCHOOL_ID=str((school or self.school).pk), format="json")

    def create_plan(self, *, owner=None, method="raw"):
        if owner:
            self.client.force_authenticate(owner)
        response = self.api("post", "/api/v1/assessment-plans/", {
            "academic_session": self.session.pk, "term": self.term.pk, "class_level": self.level.pk,
            "class_arm": self.arm.pk, "subject": self.subject.pk, "grading_scale": self.scale.pk,
            "name": "First Term Assessment", "calculation_method": method,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def add_components_and_publish(self, plan, *, weighted=False):
        parts = [("Continuous Assessment", 30, 30), ("Examination", 70, 70)] if weighted else [("Continuous Assessment", 30, None), ("Examination", 70, None)]
        ids = []
        for position, (name, maximum, weight) in enumerate(parts, start=1):
            component = AssessmentComponent.objects.create(school=self.school, name=name, max_score=Decimal(maximum))
            response = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/components/", {
                "component": component.pk, "max_score": maximum, "weight": weight, "position": position,
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            ids.append(response.data["id"])
        current_plan = AssessmentPlan.objects.get(pk=plan["id"])
        published = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/publish/", {"version": current_plan.version})
        self.assertEqual(published.status_code, status.HTTP_200_OK, published.data)
        return ids

    def test_component_validation_plan_duplicates_and_cross_school_relations(self):
        invalid = self.api("post", "/api/v1/assessment-components/", {"name": "Invalid", "max_score": "0"})
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        plan_data = self.create_plan()
        duplicate = self.api("post", "/api/v1/assessment-plans/", {
            "academic_session": self.session.pk, "term": self.term.pk, "class_level": self.level.pk,
            "class_arm": self.arm.pk, "subject": self.subject.pk, "grading_scale": self.scale.pk,
            "name": "first term assessment", "calculation_method": "raw",
        })
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        other_component = AssessmentComponent.objects.create(school=self.other_school, name="Other", max_score=Decimal("100.00"))
        cross_tenant = self.api("post", f"/api/v1/assessment-plans/{plan_data['id']}/components/", {"component": other_component.pk, "max_score": "100", "position": 1})
        self.assertEqual(cross_tenant.status_code, status.HTTP_400_BAD_REQUEST)

    def test_atomic_score_validation_calculation_submit_approve_and_audit(self):
        plan = self.create_plan(owner=self.manager)
        component_ids = self.add_components_and_publish(plan)
        self.client.force_authenticate(self.teacher_user)
        student_ids = [student.pk for student in self.students]
        invalid = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": [
            {"student_id": student_ids[0], "version": 0, "scores": [{"plan_component_id": component_ids[0], "score": "15"}]},
            {"student_id": student_ids[1], "version": 0, "scores": [{"plan_component_id": component_ids[0], "score": "31"}]},
        ]})
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AssessmentResult.objects.count(), 0)
        bad_student = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": [
            {"student_id": student_ids[0], "version": 0, "scores": [{"plan_component_id": component_ids[0], "score": "-1"}]},
        ]})
        self.assertEqual(bad_student.status_code, status.HTTP_400_BAD_REQUEST)
        entries = [{"student_id": sid, "version": 0, "scores": [
            {"plan_component_id": component_ids[0], "score": "27.50"},
            {"plan_component_id": component_ids[1], "score": "61.25"},
        ]} for sid in student_ids]
        saved = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": entries})
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.assertEqual(ComponentScore.objects.count(), 4)
        self.client.force_authenticate(self.manager)
        locked_component = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/components/{component_ids[0]}/", {"max_score": "29"})
        self.assertEqual(locked_component.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.teacher_user)
        listing = self.api("get", f"/api/v1/assessment-plans/{plan['id']}/results/")
        self.assertEqual(listing.status_code, status.HTTP_200_OK, listing.data)
        result = listing.data["results"][0]["result"]
        self.assertEqual(result["calculation"]["calculated_total"], "88.75")
        self.assertEqual(result["calculation"]["grade"], "A")
        stale = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": [
            {"student_id": student_ids[0], "version": 0, "scores": [{"plan_component_id": component_ids[0], "score": "20"}]},
        ]})
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        submit = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/results/submit/", {"entries": saved.data["results"]})
        self.assertEqual(submit.status_code, status.HTTP_200_OK, submit.data)
        self.client.force_authenticate(self.manager)
        unauthorized = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/results/approve/", {"entries": [{"student_id": student_ids[0], "version": 3}]})
        self.assertEqual(unauthorized.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        approved = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/results/approve/", {"entries": [{"student_id": student_ids[0], "version": 3}]})
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        result_obj = AssessmentResult.objects.get(plan_id=plan["id"], student_id=student_ids[0])
        self.assertEqual(result_obj.status, AssessmentResult.Status.APPROVED)
        self.assertEqual(result_obj.approved_total, Decimal("88.75"))
        self.assertTrue(result_obj.audit_events.filter(event_type=ResultAuditEvent.EventType.APPROVED).exists())
        approved_grade = result_obj.approved_grade
        band = GradeBand.objects.get(grading_scale=self.scale, label=approved_grade)
        band.label = "A2"
        band.save()
        result_obj.refresh_from_db()
        self.assertEqual(result_obj.approved_grade, approved_grade)
        self.assertEqual(result_obj.approved_calculation["grade"], approved_grade)
        blocked_edit = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": [
            {"student_id": student_ids[0], "version": result_obj.version, "scores": [{"plan_component_id": component_ids[0], "score": "20"}]},
        ]})
        self.assertEqual(blocked_edit.status_code, status.HTTP_400_BAD_REQUEST)
        no_reason = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/results/reopen/", {"entries": [{"student_id": student_ids[0], "version": result_obj.version}]})
        self.assertEqual(no_reason.status_code, status.HTTP_400_BAD_REQUEST)
        reopened = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/results/reopen/", {"entries": [{"student_id": student_ids[0], "version": result_obj.version}], "reason": "Verified a clerical error"})
        self.assertEqual(reopened.status_code, status.HTTP_200_OK, reopened.data)
        self.assertTrue(result_obj.audit_events.filter(event_type=ResultAuditEvent.EventType.REOPENED).exists())

    def test_weighted_plan_missing_results_and_teacher_tenant_scope(self):
        plan = self.create_plan(owner=self.manager, method="weighted")
        component_ids = self.add_components_and_publish(plan, weighted=True)
        self.client.force_authenticate(self.teacher_user)
        listing = self.api("get", f"/api/v1/assessment-plans/{plan['id']}/results/")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data["results"]), 2)
        student_id = self.students[0].pk
        partial = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": [
            {"student_id": student_id, "version": 0, "scores": [{"plan_component_id": component_ids[0], "score": "15"}]},
        ]})
        self.assertEqual(partial.status_code, status.HTTP_200_OK, partial.data)
        incomplete = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/results/submit/", {"entries": partial.data["results"]})
        self.assertEqual(incomplete.status_code, status.HTTP_400_BAD_REQUEST)
        partial_rows = self.api("get", f"/api/v1/assessment-plans/{plan['id']}/results/")
        partial_calc = next(row["result"]["calculation"] for row in partial_rows.data["results"] if row["student_id"] == student_id)
        self.assertFalse(partial_calc["complete"])
        self.assertIsNone(partial_calc["percentage"])
        completed = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": [
            {"student_id": student_id, "version": 2, "scores": [{"plan_component_id": component_ids[1], "score": "50"}]},
        ]})
        self.assertEqual(completed.status_code, status.HTTP_200_OK, completed.data)
        weighted_rows = self.api("get", f"/api/v1/assessment-plans/{plan['id']}/results/")
        weighted_calc = next(row["result"]["calculation"] for row in weighted_rows.data["results"] if row["student_id"] == student_id)
        self.assertEqual(weighted_calc["calculated_total"], "65.00")
        self.assertEqual(weighted_calc["percentage"], "65.00")
        self.assertEqual(weighted_calc["grade"], "C")
        unassigned_teacher = self.make_user("result-unassigned-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.client.force_authenticate(unassigned_teacher)
        unassigned_access = self.api("get", f"/api/v1/assessment-plans/{plan['id']}/results/")
        self.assertEqual(unassigned_access.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.other_admin)
        denied = self.api("get", f"/api/v1/assessment-plans/{plan['id']}/")
        self.assertIn(denied.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.client.force_authenticate(self.accountant)
        denied_write = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": []})
        self.assertEqual(denied_write.status_code, status.HTTP_403_FORBIDDEN)

    def test_weight_rules_and_scale_snapshot_survive_scale_edits(self):
        plan = self.create_plan(owner=self.manager, method="weighted")
        first_component = AssessmentComponent.objects.create(school=self.school, name="Test", max_score=Decimal("20"))
        bad = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/components/", {"component": first_component.pk, "max_score": "20", "weight": "90", "position": 1})
        self.assertEqual(bad.status_code, status.HTTP_201_CREATED, bad.data)
        second_component = AssessmentComponent.objects.create(school=self.school, name="Exam", max_score=Decimal("80"))
        self.api("post", f"/api/v1/assessment-plans/{plan['id']}/components/", {"component": second_component.pk, "max_score": "80", "weight": "5", "position": 2})
        current_plan = AssessmentPlan.objects.get(pk=plan["id"])
        response = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/publish/", {"version": current_plan.version})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        plan_obj = AssessmentPlan.objects.get(pk=plan["id"])
        self.assertEqual(plan_obj.grading_scale_snapshot["maximum_score"], "100.00")
        band = GradeBand.objects.get(grading_scale=self.scale, label="C")
        band.label = "B+"
        band.save()
        plan_obj.refresh_from_db()
        self.assertEqual(plan_obj.grading_scale_snapshot["maximum_score"], "100.00")

    def test_plan_creator_cannot_approve_their_own_results(self):
        plan = self.create_plan(owner=self.admin)
        component_ids = self.add_components_and_publish(plan)
        self.client.force_authenticate(self.teacher_user)
        student_id = self.students[0].pk
        saved = self.api("patch", f"/api/v1/assessment-plans/{plan['id']}/results/", {"entries": [{
            "student_id": student_id, "version": 0, "scores": [
                {"plan_component_id": component_ids[0], "score": "25"},
                {"plan_component_id": component_ids[1], "score": "70"},
            ],
        }]})
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        submitted = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/results/submit/", {"entries": saved.data["results"]})
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        self.client.force_authenticate(self.admin)
        rejected = self.api("post", f"/api/v1/assessment-plans/{plan['id']}/results/approve/", {"entries": [{"student_id": student_id, "version": 3}]})
        self.assertEqual(rejected.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(AssessmentResult.objects.get(plan_id=plan["id"], student_id=student_id).status, AssessmentResult.Status.SUBMITTED)
