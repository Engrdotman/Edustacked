from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, ClassSubject, Subject
from apps.schools.models import School, SchoolMembership
from .models import StaffProfile, TeacherAssignment, TeacherProfile

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class StaffManagementApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North Staff School", slug="north-staff-school")
        self.other = School.objects.create(name="South Staff School", slug="south-staff-school")
        self.admin = self.make_user("staff-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.manager = self.make_user("staff-manager", SchoolMembership.Role.SCHOOL_MANAGER, self.school)
        self.receptionist = self.make_user("staff-receptionist", SchoolMembership.Role.RECEPTIONIST, self.school)
        self.teacher_user = self.make_user("staff-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.outsider = self.make_user("staff-outsider", SchoolMembership.Role.SCHOOL_ADMIN, self.other)
        self.unlinked = User.objects.create_user(username="unlinked-staff", email="unlinked@example.test", password="test-password")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        self.level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1", category="junior_secondary")
        self.arm = ClassArm.objects.create(school=self.school, class_level=self.level, name="A")
        self.math = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        self.english = Subject.objects.create(school=self.school, name="English", code="ENG")

    @staticmethod
    def make_user(username, role, school):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def api(self, method, path, data=None, school=None):
        return getattr(self.client, method)(path, data, HTTP_X_SCHOOL_ID=str((school or self.school).pk), format="json")

    def staff_payload(self, number="T-001", **extra):
        return {"staff_number": number, "first_name": "Ada", "last_name": "Okafor", "job_title": "Teacher", "employment_type": "full_time", "employment_start_date": "2026-09-01", **extra}

    def make_teacher(self, number="T-001", user=None):
        profile = StaffProfile.objects.create(school=self.school, staff_number=number, first_name="Ada", last_name="Okafor", job_title="Teacher", employment_start_date=date(2026, 9, 1), user=user)
        return TeacherProfile.objects.create(school=self.school, staff=profile)

    def assignment_payload(self, teacher, subject=None, **extra):
        return {"teacher": teacher.pk, "academic_session": self.session.pk, "class_level": self.level.pk, "class_arm": self.arm.pk, "subject": (subject or self.math).pk, "start_date": "2026-09-01", **extra}

    def test_staff_number_scope_dates_status_and_linkage_rules(self):
        created = self.api("post", "/api/v1/staff/", self.staff_payload())
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        duplicate = self.api("post", "/api/v1/staff/", self.staff_payload("t-001"))
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        invalid_dates = self.api("post", "/api/v1/staff/", self.staff_payload("T-002", employment_end_date="2026-08-31"))
        self.assertEqual(invalid_dates.status_code, status.HTTP_400_BAD_REQUEST)
        former_without_end = self.api("post", "/api/v1/staff/", self.staff_payload("T-003", status="former"))
        self.assertEqual(former_without_end.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.outsider)
        same_number_other_school = self.api("post", "/api/v1/staff/", self.staff_payload(), school=self.other)
        self.assertEqual(same_number_other_school.status_code, status.HTTP_201_CREATED, same_number_other_school.data)
        self.client.force_authenticate(self.admin)
        link_without_membership = self.api("post", "/api/v1/staff/", self.staff_payload("T-004", user=self.unlinked.pk))
        self.assertEqual(link_without_membership.status_code, status.HTTP_400_BAD_REQUEST)
        linked = self.api("post", "/api/v1/staff/", self.staff_payload("T-005", user=self.teacher_user.pk))
        self.assertEqual(linked.status_code, status.HTTP_201_CREATED, linked.data)
        self.assertTrue(linked.data["has_login"])
        self.assertEqual(SchoolMembership.objects.get(user=self.teacher_user, school=self.school).role, SchoolMembership.Role.TEACHER)
        foreign_user = self.make_user("staff-foreign-account", SchoolMembership.Role.SCHOOL_ADMIN, self.other)
        foreign_link = self.api("post", "/api/v1/staff/", self.staff_payload("T-006", user=foreign_user.pk))
        self.assertEqual(foreign_link.status_code, status.HTTP_400_BAD_REQUEST)

        deactivate = self.api("patch", f"/api/v1/staff/{created.data['id']}/", {"status": "inactive"})
        self.assertEqual(deactivate.status_code, status.HTTP_200_OK, deactivate.data)
        reactivate = self.api("patch", f"/api/v1/staff/{created.data['id']}/", {"status": "active"})
        self.assertEqual(reactivate.status_code, status.HTTP_200_OK, reactivate.data)
        former = self.api("patch", f"/api/v1/staff/{created.data['id']}/", {"status": "former", "employment_end_date": "2027-01-01"})
        self.assertEqual(former.status_code, status.HTTP_200_OK, former.data)
        cannot_reactivate = self.api("patch", f"/api/v1/staff/{created.data['id']}/", {"status": "active", "employment_end_date": None})
        self.assertEqual(cannot_reactivate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_designation_and_assignments_preserve_history(self):
        teacher = self.make_teacher(user=self.teacher_user)
        designation = self.api("post", f"/api/v1/staff/{teacher.staff_id}/teacher/", {"specialization": "Mathematics"})
        self.assertEqual(designation.status_code, status.HTTP_400_BAD_REQUEST)
        # A profile may only be designated once.
        existing = TeacherProfile.objects.get(pk=teacher.pk)
        self.assertEqual(existing.staff_id, teacher.staff_id)
        first = self.api("post", "/api/v1/assignments/", self.assignment_payload(teacher))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        duplicate = self.api("post", "/api/v1/assignments/", self.assignment_payload(teacher))
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        invalid_dates = self.api("post", "/api/v1/assignments/", self.assignment_payload(teacher, end_date="2026-08-31"))
        self.assertEqual(invalid_dates.status_code, status.HTTP_400_BAD_REQUEST)

        second_teacher = self.make_teacher("T-002")
        parallel_teacher = self.api("post", "/api/v1/assignments/", self.assignment_payload(second_teacher))
        self.assertEqual(parallel_teacher.status_code, status.HTTP_201_CREATED, parallel_teacher.data)
        wrong_arm = ClassArm.objects.create(school=self.school, class_level=ClassLevel.objects.create(school=self.school, name="JSS 2", code="JSS2"), name="A")
        invalid_arm = self.api("post", "/api/v1/assignments/", self.assignment_payload(second_teacher, class_arm=wrong_arm.pk))
        self.assertEqual(invalid_arm.status_code, status.HTTP_400_BAD_REQUEST)

        ended = self.api("post", f"/api/v1/assignments/{first.data['id']}/transition/", {"status": "ended", "end_date": "2026-12-31"})
        self.assertEqual(ended.status_code, status.HTTP_200_OK, ended.data)
        replacement = self.api("post", f"/api/v1/assignments/{first.data['id']}/replace/", {**self.assignment_payload(teacher, self.english, start_date="2027-01-01"), "reason": "Term change"})
        self.assertEqual(replacement.status_code, status.HTTP_400_BAD_REQUEST)
        # Ended records remain immutable; create a replacement via an active source.
        active = self.api("post", "/api/v1/assignments/", self.assignment_payload(teacher, self.english))
        self.assertEqual(active.status_code, status.HTTP_201_CREATED, active.data)
        next_assignment = self.api("post", f"/api/v1/assignments/{active.data['id']}/replace/", {**self.assignment_payload(second_teacher, self.english, start_date="2027-01-01"), "reason": "Reassignment"})
        self.assertEqual(next_assignment.status_code, status.HTTP_201_CREATED, next_assignment.data)
        self.assertEqual(next_assignment.data["previous_assignment_id"], active.data["id"])
        self.assertEqual(next_assignment.data["change_reason"], "Reassignment")
        self.assertEqual(TeacherAssignment.objects.get(pk=active.data["id"]).status, TeacherAssignment.Status.ENDED)

    def test_role_boundaries_own_assignments_and_tenant_isolation(self):
        teacher = self.make_teacher(user=self.teacher_user)
        assignment = self.api("post", "/api/v1/assignments/", self.assignment_payload(teacher))
        self.assertEqual(assignment.status_code, status.HTTP_201_CREATED, assignment.data)
        self.client.force_authenticate(self.receptionist)
        self.assertEqual(self.api("get", "/api/v1/staff/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.api("post", "/api/v1/staff/", self.staff_payload("R-1")).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.api("post", "/api/v1/assignments/", self.assignment_payload(teacher)).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.teacher_user)
        own = self.api("get", "/api/v1/staff/me/")
        self.assertEqual(own.status_code, status.HTTP_200_OK, own.data)
        listed = self.api("get", "/api/v1/assignments/")
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data["results"]), 1)
        self.assertEqual(self.api("post", f"/api/v1/assignments/{assignment.data['id']}/transition/", {"status": "cancelled", "end_date": "2026-12-31"}).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.api("get", f"/api/v1/assignments/{assignment.data['id']}/", school=self.other).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.api("get", f"/api/v1/staff/{teacher.staff_id}/", school=self.other).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.admin)
        former = self.api("patch", f"/api/v1/staff/{teacher.staff_id}/", {"status": "former", "employment_end_date": "2026-10-28"})
        self.assertEqual(former.status_code, status.HTTP_200_OK, former.data)
        self.assertEqual(TeacherAssignment.objects.get(pk=assignment.data["id"]).status, TeacherAssignment.Status.ENDED)
        self.assertTrue(self.teacher_user.is_active)
        self.assertTrue(SchoolMembership.objects.get(user=self.teacher_user, school=self.school).is_active)

    def test_unauthenticated_and_foreign_academic_objects_are_rejected(self):
        teacher = self.make_teacher()
        self.client.force_authenticate(None)
        self.assertEqual(self.api("get", "/api/v1/staff/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.admin)
        foreign_user = self.make_user("foreign-teacher", SchoolMembership.Role.TEACHER, self.other)
        foreign_staff = StaffProfile.objects.create(school=self.other, user=foreign_user, staff_number="F-1", first_name="Foreign", last_name="Teacher", job_title="Teacher", employment_start_date=date(2026, 9, 1))
        foreign_teacher = TeacherProfile.objects.create(school=self.other, staff=foreign_staff)
        foreign_subject = Subject.objects.create(school=self.other, name="Foreign subject")
        invalid_teacher = self.api("post", "/api/v1/assignments/", self.assignment_payload(foreign_teacher))
        self.assertEqual(invalid_teacher.status_code, status.HTTP_400_BAD_REQUEST)
        invalid_subject = self.api("post", "/api/v1/assignments/", self.assignment_payload(teacher, foreign_subject))
        self.assertEqual(invalid_subject.status_code, status.HTTP_400_BAD_REQUEST)

