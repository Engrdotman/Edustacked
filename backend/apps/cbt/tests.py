from datetime import timedelta
from decimal import Decimal
import hashlib
import hmac
import json
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import AcademicSession, ClassArm, ClassLevel, Subject
from apps.entitlements.models import ServiceEntitlement
from apps.schools.models import School, SchoolMembership
from apps.students.models import Student, StudentEnrollment

from .models import CbtSyncConflict, CbtSyncedSubmission, Examination, ExaminationAssignment, ExaminationQuestion, Question, QuestionOption
from .services import create_examination_package, ingest_local_submission, issue_local_server_credential


User = get_user_model()


class CbtApiTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.school = School.objects.create(name="CBT North School")
        self.other_school = School.objects.create(name="CBT South School")
        self.admin = User.objects.create_user(username="cbt-admin", email="cbt-admin@example.test", password="test-pass")
        self.teacher = User.objects.create_user(username="cbt-teacher", email="cbt-teacher@example.test", password="test-pass")
        self.other_admin = User.objects.create_user(username="other-admin", email="other-admin@example.test", password="test-pass")
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.other_admin, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        ServiceEntitlement.objects.create(
            school=self.school, service_code="offline_cbt", package_type="school", student_capacity=100,
            starts_on=today - timedelta(days=1), expires_on=today + timedelta(days=365),
        )
        self.session = AcademicSession.objects.create(
            school=self.school, name="2026/2027", start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=300),
        )
        self.session.status = AcademicSession.Status.ACTIVE
        self.session.save()
        self.class_level = ClassLevel.objects.create(school=self.school, name="JSS 1", is_active=True)
        self.class_arm = ClassArm.objects.create(school=self.school, class_level=self.class_level, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.client = APIClient()

    def authenticate(self, user=None, school=None):
        self.client.force_authenticate(user or self.admin)
        self.client.defaults["HTTP_X_SCHOOL_ID"] = str((school or self.school).pk)

    def create_question(self, *, user=None, question_type=Question.Type.SINGLE_CHOICE, text="What is 2 + 2?", marks="5.00", status_value=Question.Status.PUBLISHED):
        question = Question.objects.create(
            school=self.school, subject=self.subject, class_level=self.class_level,
            text=text, question_type=question_type, difficulty=Question.Difficulty.EASY,
            marks=Decimal(marks), created_by=user or self.admin, status=status_value,
        )
        if question_type != Question.Type.TEXT:
            correct_positions = {1} if question_type == Question.Type.SINGLE_CHOICE else {0, 1}
            QuestionOption.objects.bulk_create([
                QuestionOption(question=question, text=f"Option {i + 1}", position=i, is_correct=i in correct_positions)
                for i in range(3)
            ])
        return question

    def create_exam(self, question_ids, *, user=None, selection_method="manual", pass_mark="5.00", start_delta=1):
        start = timezone.now() + timedelta(hours=start_delta)
        payload = {
            "title": "JSS Mathematics CBT",
            "description": "Term practice",
            "instructions": "Read each question carefully.",
            "subject": self.subject.pk,
            "class_level": self.class_level.pk,
            "academic_session": self.session.pk,
            "duration_minutes": 30,
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=45)).isoformat(),
            "pass_mark": pass_mark,
            "maximum_attempts": 1,
            "selection_method": selection_method,
            "question_ids": [str(item) for item in question_ids],
        }
        if selection_method == "random":
            payload["random_question_count"] = len(question_ids)
            payload["question_ids"] = []
        self.authenticate(user)
        return self.client.post("/api/v1/cbt/examinations/", payload, format="json")

    def test_single_and_multiple_answer_question_creation_and_validation(self):
        self.authenticate()
        single = self.client.post("/api/v1/cbt/questions/", {
            "subject": self.subject.pk, "class_level": self.class_level.pk,
            "text": "Select the value of 2 + 2", "question_type": "single_choice",
            "difficulty": "easy", "marks": "2", "options": [
                {"text": "3", "is_correct": False}, {"text": "4", "is_correct": True},
            ],
        }, format="json")
        self.assertEqual(single.status_code, 201, single.data)
        self.assertEqual(sum(option["is_correct"] for option in single.data["options"]), 1)
        multiple = self.client.post("/api/v1/cbt/questions/", {
            "subject": self.subject.pk, "class_level": self.class_level.pk,
            "text": "Select all even numbers", "question_type": "multiple_answer",
            "difficulty": "medium", "marks": "3", "options": [
                {"text": "2", "is_correct": True}, {"text": "3", "is_correct": False}, {"text": "4", "is_correct": True},
            ],
        }, format="json")
        self.assertEqual(multiple.status_code, 201, multiple.data)
        invalid = self.client.post("/api/v1/cbt/questions/", {
            "subject": self.subject.pk, "class_level": self.class_level.pk,
            "text": "Invalid", "question_type": "single_choice", "marks": "1",
            "options": [{"text": "Only one", "is_correct": True}],
        }, format="json")
        self.assertEqual(invalid.status_code, 400)

    def test_text_question_has_no_options_and_questions_require_active_entitlement(self):
        self.authenticate()
        response = self.client.post("/api/v1/cbt/questions/", {
            "subject": self.subject.pk, "class_level": self.class_level.pk,
            "text": "Explain your method", "question_type": "text", "marks": "4", "options": [],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        ServiceEntitlement.objects.filter(school=self.school).delete()
        denied = self.client.get("/api/v1/cbt/questions/")
        self.assertEqual(denied.status_code, 403)

    def test_question_bank_is_tenant_scoped_and_correct_answers_are_staff_only(self):
        question = self.create_question()
        self.authenticate(self.other_admin, self.other_school)
        response = self.client.get("/api/v1/cbt/questions/")
        self.assertEqual(response.status_code, 403)
        self.authenticate()
        response = self.client.get(f"/api/v1/cbt/questions/{question.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sum(option["is_correct"] for option in response.data["options"]), 1)

    def test_teacher_can_create_questions_but_cannot_publish_an_examination(self):
        question = self.create_question(user=self.teacher)
        self.authenticate(self.teacher)
        question.status = Question.Status.DRAFT
        question.save(update_fields=("status", "updated_at"))
        response = self.client.post(f"/api/v1/cbt/questions/{question.pk}/publish/")
        self.assertEqual(response.status_code, 200)
        exam = self.create_exam([question.pk], user=self.teacher)
        self.assertEqual(exam.status_code, 201, exam.data)
        denied = self.client.post(f"/api/v1/cbt/examinations/{exam.data['id']}/publish/")
        self.assertEqual(denied.status_code, 403)

    def test_exam_publishing_calculates_marks_and_freezes_question_snapshot(self):
        question = self.create_question(text="Original prompt", marks="7.50")
        exam = self.create_exam([question.pk], pass_mark="7.00")
        self.assertEqual(exam.status_code, 201, exam.data)
        exam_id = exam.data["id"]
        self.authenticate()
        response = self.client.post(f"/api/v1/cbt/examinations/{exam_id}/publish/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data["total_marks"]), Decimal("7.50"))
        self.assertEqual(response.data["status"], Examination.Status.SCHEDULED)
        snapshot = ExaminationQuestion.objects.get(examination_id=exam_id)
        self.assertTrue(snapshot.is_snapshot)
        Question.objects.filter(pk=question.pk).update(text="Edited bank prompt")
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.prompt_snapshot, "Original prompt")
        self.assertNotIn("options_snapshot", response.data["selected_questions"][0])

    def test_exam_rejects_bad_schedule_and_pass_mark_above_calculated_total(self):
        question = self.create_question(marks="2.00")
        bad_exam = self.create_exam([question.pk], pass_mark="3.00")
        self.authenticate()
        rejected = self.client.post(f"/api/v1/cbt/examinations/{bad_exam.data['id']}/publish/")
        self.assertEqual(rejected.status_code, 400)
        self.assertTrue(Examination.objects.get(pk=bad_exam.data["id"]).published_at is None)

        start = timezone.now() + timedelta(hours=1)
        payload = {
            "title": "Bad schedule", "subject": self.subject.pk, "class_level": self.class_level.pk,
            "academic_session": self.session.pk, "duration_minutes": 60,
            "starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=30)).isoformat(),
            "pass_mark": "1", "selection_method": "manual", "question_ids": [str(question.pk)],
        }
        response = self.client.post("/api/v1/cbt/examinations/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        invalid_publish = self.client.post(f"/api/v1/cbt/examinations/{response.data['id']}/publish/")
        self.assertEqual(invalid_publish.status_code, 400)

    def test_exam_publishing_rejects_malformed_published_question_data(self):
        question = Question.objects.create(
            school=self.school, subject=self.subject, class_level=self.class_level,
            text="Malformed question", question_type=Question.Type.SINGLE_CHOICE,
            difficulty=Question.Difficulty.EASY, marks=Decimal("2"), created_by=self.admin,
            status=Question.Status.PUBLISHED,
        )
        QuestionOption.objects.create(question=question, text="Only option", position=0, is_correct=True)
        exam = self.create_exam([question.pk])
        self.authenticate()
        response = self.client.post(f"/api/v1/cbt/examinations/{exam.data['id']}/publish/")
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Examination.objects.get(pk=exam.data["id"]).published_at)

    def test_random_question_selection_uses_only_published_matching_questions(self):
        first = self.create_question(text="Published 1")
        second = self.create_question(text="Published 2")
        self.create_question(text="Draft question", status_value=Question.Status.DRAFT)
        exam = self.create_exam([first.pk, second.pk], selection_method="random")
        self.assertEqual(exam.status_code, 201, exam.data)
        self.authenticate()
        response = self.client.post(f"/api/v1/cbt/examinations/{exam.data['id']}/publish/")
        self.assertEqual(response.status_code, 200, response.data)
        selected = set(ExaminationQuestion.objects.filter(examination_id=exam.data["id"]).values_list("source_question_id", flat=True))
        self.assertEqual(selected, {first.pk, second.pk})

    def test_assignment_requires_active_enrollment_and_is_idempotent(self):
        question = self.create_question()
        exam = self.create_exam([question.pk])
        self.authenticate()
        self.client.post(f"/api/v1/cbt/examinations/{exam.data['id']}/publish/")
        student = Student.objects.create(school=self.school, admission_number="CBT-001", first_name="Ada", last_name="Student")
        StudentEnrollment.objects.create(
            school=self.school, student=student, academic_session=self.session, class_level=self.class_level,
            class_arm=self.class_arm, enrollment_date=timezone.localdate(), status=StudentEnrollment.Status.ACTIVE,
        )
        url = f"/api/v1/cbt/examinations/{exam.data['id']}/assignments/"
        first = self.client.post(url, {"student_ids": [student.pk]}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["assigned"], 1)
        second = self.client.post(url, {"student_ids": [student.pk]}, format="json")
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data["assigned"], 0)
        self.assertEqual(ExaminationAssignment.objects.filter(examination_id=exam.data["id"]).count(), 1)

    def test_assignment_rejects_student_from_another_school(self):
        question = self.create_question()
        exam = self.create_exam([question.pk])
        self.authenticate()
        self.client.post(f"/api/v1/cbt/examinations/{exam.data['id']}/publish/")
        other_student = Student.objects.create(school=self.other_school, admission_number="OTHER-001", first_name="Other", last_name="Student")
        response = self.client.post(f"/api/v1/cbt/examinations/{exam.data['id']}/assignments/", {"student_ids": [other_student.pk]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ExaminationAssignment.objects.count(), 0)

    @override_settings(CBT_PACKAGE_SIGNING_KEY="test-package-key-long-enough-123456")
    def test_local_submission_ingest_is_signed_tenant_scoped_and_idempotent(self):
        question = self.create_question()
        exam_response = self.create_exam([question.pk])
        self.authenticate()
        self.client.post(f"/api/v1/cbt/examinations/{exam_response.data['id']}/publish/")
        student = Student.objects.create(school=self.school, admission_number="SYNC-001", first_name="Ada", last_name="Student")
        StudentEnrollment.objects.create(
            school=self.school, student=student, academic_session=self.session, class_level=self.class_level,
            class_arm=self.class_arm, enrollment_date=timezone.localdate(), status=StudentEnrollment.Status.ACTIVE,
        )
        assign_response = self.client.post(
            f"/api/v1/cbt/examinations/{exam_response.data['id']}/assignments/",
            {"student_ids": [student.pk]}, format="json",
        )
        self.assertEqual(assign_response.status_code, 201, assign_response.data)
        package = create_examination_package(exam_response.data["id"], self.school, self.admin)
        credential, token = issue_local_server_credential(self.school, "Test LAN server")
        assignment = ExaminationAssignment.objects.get(examination_id=exam_response.data["id"], student=student)
        payload = {
            "event_id": str(uuid4()), "payload_version": 1, "event_type": "submission.finalized",
            "school_id": self.school.pk, "package_id": str(package.package_id), "examination_id": str(package.examination_id),
            "assignment_id": str(assignment.pk), "student_id": student.pk, "local_session_id": str(uuid4()),
            "started_at": timezone.now().isoformat(), "submitted_at": timezone.now().isoformat(),
            "status": "submitted", "answers": [{"question_id": str(question.pk), "value": f"{question.pk}:1", "saved_at": timezone.now().isoformat()}],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        envelope = {
            "payload": payload, "payload_hash": hashlib.sha256(canonical).hexdigest(),
            "signature": hmac.new(token.encode(), canonical, "sha256").hexdigest(),
        }
        first, created, conflict = ingest_local_submission(credential, envelope, token)
        self.assertTrue(created)
        self.assertFalse(conflict)
        repeated, created_again, conflict_again = ingest_local_submission(credential, envelope, token)
        self.assertEqual(first.pk, repeated.pk)
        self.assertFalse(created_again)
        self.assertFalse(conflict_again)
        self.assertEqual(CbtSyncedSubmission.objects.count(), 1)

        altered = dict(payload, event_id=str(uuid4()), answers=[])
        altered_bytes = json.dumps(altered, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        altered_envelope = {
            "payload": altered, "payload_hash": hashlib.sha256(altered_bytes).hexdigest(),
            "signature": hmac.new(token.encode(), altered_bytes, "sha256").hexdigest(),
        }
        _, _, detected_conflict = ingest_local_submission(credential, altered_envelope, token)
        self.assertTrue(detected_conflict)
        self.assertEqual(CbtSyncConflict.objects.count(), 1)
