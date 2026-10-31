from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.academics.models import AcademicSession, ClassArm, ClassLevel
from apps.schools.models import School, SchoolMembership
from .models import Student, StudentEnrollment, StudentGuardian

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class StudentManagementApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North Academy", slug="north-academy")
        self.other = School.objects.create(name="South Academy", slug="south-academy")
        self.admin = self.make_user("student-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.receptionist = self.make_user("student-reception", SchoolMembership.Role.RECEPTIONIST, self.school)
        self.teacher = self.make_user("student-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.accountant = self.make_user("student-accountant", SchoolMembership.Role.ACCOUNTANT, self.school)
        self.other_admin = self.make_user("other-student-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.session = AcademicSession.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        AcademicSession.objects.filter(pk=self.session.pk).update(status="active")
        self.session.refresh_from_db()
        self.level = ClassLevel.objects.create(school=self.school, name="JSS 1", code="JSS1", category="junior_secondary")
        self.arm = ClassArm.objects.create(school=self.school, class_level=self.level, name="A")

    @staticmethod
    def make_user(username, role, school):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def api(self, method, path, data=None, school=None):
        return getattr(self.client, method)(path, data, HTTP_X_SCHOOL_ID=str((school or self.school).pk), format="json")

    def admission(self, admission_number="N-001", **extra):
        return self.api("post", "/api/v1/admissions/", {
            "student": {"admission_number": admission_number, "first_name": "Ada", "last_name": "Okafor"},
            **extra,
        })

    def enrolled_admission(self, admission_number="N-001"):
        response = self.admission(admission_number, enrollment={
            "academic_session": self.session.pk, "class_level": self.level.pk,
            "class_arm": self.arm.pk, "enrollment_date": "2026-09-01", "status": "active",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def test_admission_guardians_and_enrollment_are_atomic_and_school_scoped(self):
        result = self.admission("N-001", guardians=[{
            "full_name": "Grace Okafor", "phone": "555-0100", "relationship_type": "mother", "is_primary_contact": True,
        }], enrollment={
            "academic_session": self.session.pk, "class_level": self.level.pk,
            "class_arm": self.arm.pk, "enrollment_date": "2026-09-01", "status": "active",
        })
        self.assertEqual(result.status_code, status.HTTP_201_CREATED, result.data)
        student = Student.objects.get(pk=result.data["id"])
        self.assertEqual(student.enrollments.count(), 1)
        self.assertEqual(student.guardian_links.count(), 1)
        duplicate = self.admission("n-001")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

        foreign_session = AcademicSession.objects.create(school=self.other, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 6, 30))
        foreign = self.admission("N-002", enrollment={"academic_session": foreign_session.pk, "class_level": self.level.pk, "class_arm": self.arm.pk})
        self.assertEqual(foreign.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Student.objects.filter(admission_number="N-002").exists())
        invalid_after_student_create = self.admission("N-003", enrollment={
            "academic_session": self.session.pk, "class_level": self.level.pk,
            "class_arm": self.arm.pk, "enrollment_date": "2027-07-01", "status": "active",
        })
        self.assertEqual(invalid_after_student_create.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Student.objects.filter(admission_number="N-003").exists())

    def test_roles_tenant_scope_filters_and_soft_deactivation(self):
        student = self.enrolled_admission()
        detail = f"/api/v1/students/{student['id']}/"
        guardian_link = self.api("post", f"/api/v1/students/{student['id']}/guardians/", {
            "full_name": "Parent One", "phone": "555-0101", "relationship_type": "parent",
        })
        self.assertEqual(guardian_link.status_code, status.HTTP_201_CREATED, guardian_link.data)
        enrollment_id = Student.objects.get(pk=student["id"]).enrollments.get().pk
        from apps.academics.models import Subject
        from apps.staff.models import StaffProfile, TeacherAssignment, TeacherProfile
        staff = StaffProfile.objects.create(school=self.school, user=self.teacher, staff_number="ST-1", first_name="Teacher", last_name="One", job_title="Teacher", employment_start_date=date(2026, 9, 1))
        teacher_profile = TeacherProfile.objects.create(school=self.school, staff=staff)
        subject = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        TeacherAssignment.objects.create(school=self.school, teacher=teacher_profile, academic_session=self.session, class_level=self.level, class_arm=self.arm, subject=subject, start_date=date(2026, 9, 1))
        self.client.force_authenticate(self.teacher)
        response = self.api("get", detail)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("date_of_birth", response.data)
        self.assertNotIn("phone", response.data)
        self.client.force_authenticate(self.accountant)
        self.assertEqual(self.api("get", "/api/v1/students/").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.other_admin)
        self.assertEqual(self.api("get", detail, school=self.other).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.api("get", f"/api/v1/guardians/{guardian_link.data['guardian_id']}/", school=self.other).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.api("get", f"/api/v1/enrollments/{enrollment_id}/", school=self.other).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.admin)
        filtered = self.api("get", f"/api/v1/students/?class_level={self.level.pk}")
        self.assertEqual(filtered.status_code, status.HTTP_200_OK)
        deactivate = self.api("patch", detail, {"status": "inactive"})
        self.assertEqual(deactivate.status_code, status.HTTP_200_OK, deactivate.data)
        self.assertEqual(Student.objects.get(pk=student["id"]).status, Student.Status.INACTIVE)

    def test_receptionist_can_admit_but_cannot_manage_student_profile(self):
        self.client.force_authenticate(self.receptionist)
        admitted = self.admission("R-001")
        self.assertEqual(admitted.status_code, status.HTTP_201_CREATED, admitted.data)
        self.assertNotIn("address", admitted.data)
        denied = self.api("patch", f"/api/v1/students/{admitted.data['id']}/", {"status": "inactive"})
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_guardian_link_duplicate_primary_and_sibling_support(self):
        first = self.admission("N-001")
        second = self.admission("N-002")
        body = {"full_name": "Grace Okafor", "phone": "555-0100", "relationship_type": "mother", "is_primary_contact": True}
        link = self.api("post", f"/api/v1/students/{first.data['id']}/guardians/", body)
        self.assertEqual(link.status_code, status.HTTP_201_CREATED, link.data)
        guardian_id = link.data["guardian_id"]
        sibling = self.api("post", f"/api/v1/students/{second.data['id']}/guardians/", {"guardian_id": guardian_id, "relationship_type": "mother", "is_primary_contact": True})
        self.assertEqual(sibling.status_code, status.HTTP_201_CREATED, sibling.data)
        duplicate = self.api("post", f"/api/v1/students/{first.data['id']}/guardians/", {"guardian_id": guardian_id, "relationship_type": "mother"})
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transfer_preserves_history_and_rolls_back_invalid_destination(self):
        student = self.enrolled_admission()
        second_level = ClassLevel.objects.create(school=self.school, name="JSS 2", code="JSS2", category="junior_secondary")
        second_arm = ClassArm.objects.create(school=self.school, class_level=second_level, name="A")
        old = student["id"]
        enrollment_id = Student.objects.get(pk=old).enrollments.get().pk
        failed = self.api("post", f"/api/v1/enrollments/{enrollment_id}/transfer/", {"class_level": second_level.pk, "class_arm": self.arm.pk, "transfer_date": "2026-10-01", "reason": "Class change"})
        self.assertEqual(failed.status_code, status.HTTP_400_BAD_REQUEST)
        current = StudentEnrollment.objects.get(pk=enrollment_id)
        self.assertEqual(current.status, StudentEnrollment.Status.ACTIVE)
        moved = self.api("post", f"/api/v1/enrollments/{enrollment_id}/transfer/", {"class_level": second_level.pk, "class_arm": second_arm.pk, "transfer_date": "2026-10-01", "reason": "Class change"})
        self.assertEqual(moved.status_code, status.HTTP_201_CREATED, moved.data)
        current.refresh_from_db()
        self.assertEqual(current.status, StudentEnrollment.Status.TRANSFERRED)
        self.assertEqual(moved.data["previous_enrollment_id"], enrollment_id)
        self.assertEqual(Student.objects.get(pk=old).enrollments.count(), 2)
