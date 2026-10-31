from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.schools.models import School, SchoolMembership

from .models import AcademicSession, ClassArm, ClassLevel, ClassSubject, GradeBand, GradingScale, Subject, Term

User = get_user_model()


@override_settings(PASSWORD_HASHERS=("django.contrib.auth.hashers.MD5PasswordHasher",))
class AcademicSetupApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North Academy", slug="north-academy")
        self.other_school = School.objects.create(name="South Academy", slug="south-academy")
        self.admin = self.user_with_role("academic-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.school)
        self.manager = self.user_with_role("academic-manager", SchoolMembership.Role.SCHOOL_MANAGER, self.school)
        self.teacher = self.user_with_role("academic-teacher", SchoolMembership.Role.TEACHER, self.school)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @staticmethod
    def user_with_role(username, role, school):
        user = User.objects.create_user(username=username, password="academic-test-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def api(self, method, path, data=None, school=None, **kwargs):
        return getattr(self.client, method)(
            path, data, HTTP_X_SCHOOL_ID=str((school or self.school).pk), **kwargs
        )

    @staticmethod
    def session_payload(name="2026/2027", start="2026-09-01", end="2027-06-30", status_value="draft"):
        return {"name": name, "start_date": start, "end_date": end, "status": status_value}

    def create_session(self, school=None, **overrides):
        payload = self.session_payload(**overrides)
        response = self.api("post", "/api/v1/academics/academic-sessions/", payload, school=school, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def test_session_unique_per_school_dates_and_single_active_lifecycle(self):
        first = self.create_session(name="Autumn 2026")
        self.assertEqual(first["school"], self.school.pk)
        duplicate = self.api("post", "/api/v1/academics/academic-sessions/", self.session_payload(name="Autumn 2026"), format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        duplicate_case = self.api("post", "/api/v1/academics/academic-sessions/", self.session_payload(name="autumn 2026"), format="json")
        self.assertEqual(duplicate_case.status_code, status.HTTP_400_BAD_REQUEST)

        other_admin = self.user_with_role("other-academic-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client.force_authenticate(other_admin)
        same_name_other_school = self.api(
            "post", "/api/v1/academics/academic-sessions/", self.session_payload(name="Autumn 2026"),
            school=self.other_school, format="json"
        )
        self.assertEqual(same_name_other_school.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.admin)

        invalid_dates = self.api(
            "post", "/api/v1/academics/academic-sessions/",
            self.session_payload(name="Invalid", start="2027-06-30", end="2026-09-01"), format="json"
        )
        self.assertEqual(invalid_dates.status_code, status.HTTP_400_BAD_REQUEST)

        activate = self.api("patch", f"/api/v1/academics/academic-sessions/{first['id']}/", {"status": "active"}, format="json")
        self.assertEqual(activate.status_code, status.HTTP_200_OK, activate.data)
        second = self.create_session(name="2027/2028", start="2027-09-01", end="2028-06-30")
        conflict = self.api("patch", f"/api/v1/academics/academic-sessions/{second['id']}/", {"status": "active"}, format="json")
        self.assertEqual(conflict.status_code, status.HTTP_400_BAD_REQUEST)

        locked = self.api("patch", f"/api/v1/academics/academic-sessions/{first['id']}/", {"name": "Renamed"}, format="json")
        self.assertEqual(locked.status_code, status.HTTP_400_BAD_REQUEST)

    def test_terms_validate_parent_dates_uniqueness_overlap_and_lifecycle(self):
        session = self.create_session()
        path = "/api/v1/academics/terms/"
        payload = {
            "academic_session": session["id"], "name": "First Term", "sequence": 1,
            "start_date": "2026-09-01", "end_date": "2026-12-20", "status": "draft",
        }
        first = self.api("post", path, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        duplicate = self.api("post", path, {**payload, "name": "FIRST TERM", "sequence": 2}, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        outside = self.api("post", path, {**payload, "name": "Outside", "sequence": 2, "end_date": "2027-07-01"}, format="json")
        self.assertEqual(outside.status_code, status.HTTP_400_BAD_REQUEST)
        overlap = self.api("post", path, {**payload, "name": "Second Term", "sequence": 2, "start_date": "2026-12-20", "end_date": "2027-03-01"}, format="json")
        self.assertEqual(overlap.status_code, status.HTTP_400_BAD_REQUEST)

        session_response = self.api("patch", f"/api/v1/academics/academic-sessions/{session['id']}/", {"status": "active"}, format="json")
        self.assertEqual(session_response.status_code, status.HTTP_200_OK, session_response.data)
        active = self.api("patch", f"/api/v1/academics/terms/{first.data['id']}/", {"status": "active"}, format="json")
        self.assertEqual(active.status_code, status.HTTP_200_OK, active.data)
        second_term = self.api("post", path, {**payload, "name": "Second Term", "sequence": 2, "start_date": "2027-01-01", "end_date": "2027-03-01"}, format="json")
        self.assertEqual(second_term.status_code, status.HTTP_201_CREATED, second_term.data)
        other_active = self.api("patch", f"/api/v1/academics/terms/{second_term.data['id']}/", {"status": "active"}, format="json")
        self.assertEqual(other_active.status_code, status.HTTP_400_BAD_REQUEST)
        immutable = self.api("patch", f"/api/v1/academics/terms/{first.data['id']}/", {"start_date": "2026-09-02"}, format="json")
        self.assertEqual(immutable.status_code, status.HTTP_400_BAD_REQUEST)

        incomplete = self.api("patch", f"/api/v1/academics/academic-sessions/{session['id']}/", {"status": "completed"}, format="json")
        self.assertEqual(incomplete.status_code, status.HTTP_400_BAD_REQUEST)
        closed = self.api("patch", f"/api/v1/academics/terms/{first.data['id']}/", {"status": "completed"}, format="json")
        self.assertEqual(closed.status_code, status.HTTP_200_OK, closed.data)
        activate_second = self.api("patch", f"/api/v1/academics/terms/{second_term.data['id']}/", {"status": "active"}, format="json")
        self.assertEqual(activate_second.status_code, status.HTTP_200_OK, activate_second.data)
        complete_second = self.api("patch", f"/api/v1/academics/terms/{second_term.data['id']}/", {"status": "completed"}, format="json")
        self.assertEqual(complete_second.status_code, status.HTTP_200_OK, complete_second.data)
        completed = self.api("patch", f"/api/v1/academics/academic-sessions/{session['id']}/", {"status": "completed"}, format="json")
        self.assertEqual(completed.status_code, status.HTTP_200_OK, completed.data)
        denied_edit = self.api("patch", f"/api/v1/academics/academic-sessions/{session['id']}/", {"name": "Historical rewrite"}, format="json")
        self.assertEqual(denied_edit.status_code, status.HTTP_400_BAD_REQUEST)

    def test_class_arms_subjects_and_assignments_are_school_scoped_and_deactivated_safely(self):
        class_response = self.api("post", "/api/v1/academics/classes/", {"name": "Primary 1", "code": "P1", "category": "primary", "school": self.other_school.pk}, format="json")
        self.assertEqual(class_response.status_code, status.HTTP_201_CREATED, class_response.data)
        self.assertEqual(class_response.data["school"], self.school.pk)
        class_id = class_response.data["id"]
        duplicate_class = self.api("post", "/api/v1/academics/classes/", {"name": "primary 1"}, format="json")
        self.assertEqual(duplicate_class.status_code, status.HTTP_400_BAD_REQUEST)
        duplicate_code = self.api("post", "/api/v1/academics/classes/", {"name": "Primary One", "code": "p1"}, format="json")
        self.assertEqual(duplicate_code.status_code, status.HTTP_400_BAD_REQUEST)
        other_admin = self.user_with_role("other-class-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client.force_authenticate(other_admin)
        same_class_other_school = self.api("post", "/api/v1/academics/classes/", {"name": "Primary 1"}, school=self.other_school, format="json")
        self.assertEqual(same_class_other_school.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.admin)

        arm_path = f"/api/v1/academics/classes/{class_id}/arms/"
        arm = self.api("post", arm_path, {"name": "A"}, format="json")
        self.assertEqual(arm.status_code, status.HTTP_201_CREATED, arm.data)
        duplicate_arm = self.api("post", arm_path, {"name": "a"}, format="json")
        self.assertEqual(duplicate_arm.status_code, status.HTTP_400_BAD_REQUEST)
        other_class_id = same_class_other_school.data["id"]
        wrong_parent = self.api("get", f"/api/v1/academics/classes/{other_class_id}/arms/")
        self.assertEqual(wrong_parent.status_code, status.HTTP_404_NOT_FOUND)

        subject = self.api("post", "/api/v1/academics/subjects/", {"name": "Mathematics", "code": "MATH"}, format="json")
        self.assertEqual(subject.status_code, status.HTTP_201_CREATED, subject.data)
        duplicate_subject = self.api("post", "/api/v1/academics/subjects/", {"name": "mathematics"}, format="json")
        self.assertEqual(duplicate_subject.status_code, status.HTTP_400_BAD_REQUEST)
        duplicate_subject_code = self.api("post", "/api/v1/academics/subjects/", {"name": "Maths", "code": "math"}, format="json")
        self.assertEqual(duplicate_subject_code.status_code, status.HTTP_400_BAD_REQUEST)
        assignment_path = f"/api/v1/academics/classes/{class_id}/subjects/"
        assignment = self.api("post", assignment_path, {"subject": subject.data["id"]}, format="json")
        self.assertEqual(assignment.status_code, status.HTTP_201_CREATED, assignment.data)
        duplicate_assignment = self.api("post", assignment_path, {"subject": subject.data["id"]}, format="json")
        self.assertEqual(duplicate_assignment.status_code, status.HTTP_400_BAD_REQUEST)
        other_admin = self.user_with_role("other-subject-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client.force_authenticate(other_admin)
        other_subject = self.api("post", "/api/v1/academics/subjects/", {"name": "Foreign Subject"}, school=self.other_school, format="json")
        self.assertEqual(other_subject.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.admin)
        cross_school_assignment = self.api("post", assignment_path, {"subject": other_subject.data["id"]}, format="json")
        self.assertEqual(cross_school_assignment.status_code, status.HTTP_400_BAD_REQUEST)

        deactivated = self.api("delete", f"/api/v1/academics/subjects/{subject.data['id']}/")
        self.assertEqual(deactivated.status_code, status.HTTP_204_NO_CONTENT)
        subject_obj = Subject.objects.get(pk=subject.data["id"])
        self.assertFalse(subject_obj.is_active)
        self.assertTrue(ClassSubject.objects.filter(pk=assignment.data["id"]).exists())

    def test_grading_scale_requires_valid_nonoverlapping_complete_bands(self):
        bad_active = self.api("post", "/api/v1/academics/grading-scales/", {"name": "Invalid", "is_active": True}, format="json")
        self.assertEqual(bad_active.status_code, status.HTTP_400_BAD_REQUEST)
        scale = self.api("post", "/api/v1/academics/grading-scales/", {"name": "Senior Secondary", "maximum_score": "100.00"}, format="json")
        self.assertEqual(scale.status_code, status.HTTP_201_CREATED, scale.data)
        bands_path = f"/api/v1/academics/grading-scales/{scale.data['id']}/bands/"

        too_high = self.api("post", bands_path, {"label": "X", "min_score": "95", "max_score": "101"}, format="json")
        self.assertEqual(too_high.status_code, status.HTTP_400_BAD_REQUEST)
        first = self.api("post", bands_path, {"label": "F", "min_score": "0", "max_score": "39.99"}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        overlap = self.api("post", bands_path, {"label": "E", "min_score": "39.99", "max_score": "59.99"}, format="json")
        self.assertEqual(overlap.status_code, status.HTTP_400_BAD_REQUEST)
        bands = (
            ("E", "40.00", "59.99"), ("D", "60.00", "69.99"),
            ("C", "70.00", "79.99"), ("B", "80.00", "89.99"), ("A", "90.00", "100.00"),
        )
        for label, minimum, maximum in bands:
            response = self.api("post", bands_path, {"label": label, "min_score": minimum, "max_score": maximum}, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        activate = self.api("patch", f"/api/v1/academics/grading-scales/{scale.data['id']}/", {"is_active": True}, format="json")
        self.assertEqual(activate.status_code, status.HTTP_200_OK, activate.data)
        gap = self.api("post", bands_path, {"label": "Extra", "min_score": "50.00", "max_score": "55.00"}, format="json")
        self.assertEqual(gap.status_code, status.HTTP_400_BAD_REQUEST)
        deactivate_band = self.api("patch", f"{bands_path}{first.data['id']}/", {"is_active": False}, format="json")
        self.assertEqual(deactivate_band.status_code, status.HTTP_400_BAD_REQUEST)

        gap_scale = self.api("post", "/api/v1/academics/grading-scales/", {"name": "Gap policy", "maximum_score": "100"}, format="json")
        gap_bands = f"/api/v1/academics/grading-scales/{gap_scale.data['id']}/bands/"
        partial = self.api("post", gap_bands, {"label": "Below", "min_score": "0", "max_score": "49.99"}, format="json")
        self.assertEqual(partial.status_code, status.HTTP_201_CREATED, partial.data)
        gap_activation = self.api("patch", f"/api/v1/academics/grading-scales/{gap_scale.data['id']}/", {"is_active": True}, format="json")
        self.assertEqual(gap_activation.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cross_school_parent_ids_unauthenticated_and_rbac_are_rejected(self):
        other_admin = self.user_with_role("other-session-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client.force_authenticate(other_admin)
        other_session = self.api(
            "post", "/api/v1/academics/academic-sessions/", self.session_payload(),
            school=self.other_school, format="json"
        )
        self.assertEqual(other_session.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.admin)
        term_payload = {
            "academic_session": other_session.data["id"], "name": "Foreign term", "sequence": 1,
            "start_date": "2026-09-01", "end_date": "2026-12-01",
        }
        denied_parent = self.api("post", "/api/v1/academics/terms/", term_payload, format="json")
        self.assertEqual(denied_parent.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.manager)
        manager_can_manage = self.api("post", "/api/v1/academics/classes/", {"name": "JSS 1"}, format="json")
        self.assertEqual(manager_can_manage.status_code, status.HTTP_201_CREATED)
        for role in (SchoolMembership.Role.TEACHER, SchoolMembership.Role.ACCOUNTANT, SchoolMembership.Role.RECEPTIONIST, SchoolMembership.Role.MEMBER):
            user = self.user_with_role(f"denied-{role}", role, self.school)
            self.client.force_authenticate(user)
            role_denied = self.api("get", "/api/v1/academics/classes/")
            self.assertEqual(role_denied.status_code, status.HTTP_403_FORBIDDEN)
        root = User.objects.create_superuser(username="academic-platform-root", email="academic-root@example.test", password="academic-test-password")
        self.client.force_authenticate(root)
        platform_access = self.api("post", "/api/v1/academics/classes/", {"name": "Platform-managed", "school": self.school.pk}, school=self.other_school, format="json")
        self.assertEqual(platform_access.status_code, status.HTTP_201_CREATED, platform_access.data)
        self.assertEqual(platform_access.data["school"], self.other_school.pk)
        self.client.force_authenticate(user=None)
        anonymous_denied = self.client.get("/api/v1/academics/classes/", HTTP_X_SCHOOL_ID=str(self.school.pk))
        self.assertEqual(anonymous_denied.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_multi_school_membership_scopes_collections_and_query_filters(self):
        SchoolMembership.objects.create(
            user=self.admin, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.create_session(name="North 2026", start="2026-09-01", end="2027-06-30")
        self.create_session(school=self.other_school, name="South 2026", start="2026-09-01", end="2027-06-30")
        north = self.api("get", "/api/v1/academics/academic-sessions/")
        south = self.api("get", "/api/v1/academics/academic-sessions/", school=self.other_school)
        self.assertEqual([row["name"] for row in north.data["results"]], ["North 2026"])
        self.assertEqual([row["name"] for row in south.data["results"]], ["South 2026"])
        invalid_filter = self.api("get", "/api/v1/academics/terms/?academic_session=not-an-id")
        self.assertEqual(invalid_filter.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manual_acceptance_checklist_end_to_end(self):
        session = self.create_session(name="2026/2027", start="2026-09-01", end="2027-06-30")
        duplicate_session = self.api(
            "post", "/api/v1/academics/academic-sessions/",
            self.session_payload(name="2026/2027"), format="json"
        )
        self.assertEqual(duplicate_session.status_code, status.HTTP_400_BAD_REQUEST)

        term_rows = (
            ("First Term", 1, "2026-09-01", "2026-12-18"),
            ("Second Term", 2, "2027-01-04", "2027-03-26"),
            ("Third Term", 3, "2027-04-12", "2027-06-30"),
        )
        for name, sequence, start, end in term_rows:
            created = self.api("post", "/api/v1/academics/terms/", {
                "academic_session": session["id"], "name": name, "sequence": sequence,
                "start_date": start, "end_date": end,
            }, format="json")
            self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)

        class_ids = {}
        for name, code, category in (("JSS 1", "JSS1", "junior_secondary"), ("SS 1", "SS1", "senior_secondary")):
            response = self.api("post", "/api/v1/academics/classes/", {
                "name": name, "code": code, "category": category,
            }, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            class_ids[name] = response.data["id"]

        arms_path = f"/api/v1/academics/classes/{class_ids['JSS 1']}/arms/"
        for arm_name in ("A", "B"):
            response = self.api("post", arms_path, {"name": arm_name}, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        subject_ids = {}
        for subject_name in ("Mathematics", "English Language"):
            response = self.api("post", "/api/v1/academics/subjects/", {"name": subject_name}, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            subject_ids[subject_name] = response.data["id"]

        for class_name, class_id in class_ids.items():
            assignment_path = f"/api/v1/academics/classes/{class_id}/subjects/"
            for subject_name, subject_id in subject_ids.items():
                assignment = self.api("post", assignment_path, {"subject": subject_id}, format="json")
                self.assertEqual(assignment.status_code, status.HTTP_201_CREATED, assignment.data)
            duplicate_assignment = self.api("post", assignment_path, {"subject": subject_ids["Mathematics"]}, format="json")
            self.assertEqual(duplicate_assignment.status_code, status.HTTP_400_BAD_REQUEST, class_name)

        scale = self.api("post", "/api/v1/academics/grading-scales/", {
            "name": "2026/2027 School Scale", "maximum_score": "100.00",
        }, format="json")
        self.assertEqual(scale.status_code, status.HTTP_201_CREATED, scale.data)
        band_path = f"/api/v1/academics/grading-scales/{scale.data['id']}/bands/"
        for label, minimum, maximum in (("F", "0.00", "39.99"), ("C", "40.00", "69.99"), ("A", "70.00", "100.00")):
            response = self.api("post", band_path, {
                "label": label, "min_score": minimum, "max_score": maximum,
            }, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        invalid_range = self.api("post", band_path, {"label": "Invalid", "min_score": "80", "max_score": "70"}, format="json")
        self.assertEqual(invalid_range.status_code, status.HTTP_400_BAD_REQUEST)
        overlapping = self.api("post", band_path, {"label": "B", "min_score": "69.99", "max_score": "79.99"}, format="json")
        self.assertEqual(overlapping.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.teacher)
        teacher_change = self.api("post", "/api/v1/academics/classes/", {"name": "Teacher Class"}, format="json")
        self.assertEqual(teacher_change.status_code, status.HTTP_403_FORBIDDEN)

        other_admin = self.user_with_role("acceptance-other-school-admin", SchoolMembership.Role.SCHOOL_ADMIN, self.other_school)
        self.client.force_authenticate(other_admin)
        foreign_class = self.api("post", "/api/v1/academics/classes/", {"name": "Foreign Class"}, school=self.other_school, format="json")
        self.assertEqual(foreign_class.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.admin)
        foreign_read = self.api("get", f"/api/v1/academics/classes/{foreign_class.data['id']}/")
        self.assertEqual(foreign_read.status_code, status.HTTP_404_NOT_FOUND)
