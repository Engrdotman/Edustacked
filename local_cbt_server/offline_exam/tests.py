import json
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from offline_exam.models import ImportedExamination, LocalExamSession, LocalStudentCredential, LocalSubmission, SyncOutbox
from offline_exam.services import canonical_json, import_package
from offline_exam.sync import process_due_outbox


PACKAGE_KEY = 'package-test-key-1234567890'
LICENSE_KEY = 'license-test-key-1234567890'


@override_settings(CBT_PACKAGE_SIGNING_KEY=PACKAGE_KEY, CBT_LICENSE_SIGNING_KEY=LICENSE_KEY, LOCAL_CBT_TOKEN_TTL_HOURS=12)
class LocalExamFlowTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(username='local-admin', email='admin@example.test', password='very-long-admin-password')
        self.student = LocalStudentCredential(central_student_id=101, admission_number='ST-101', display_name='Ada Student')
        self.student.set_password('temporary-student-password')
        self.student.save()
        self.second_student = LocalStudentCredential(central_student_id=102, admission_number='ST-102', display_name='Ben Student')
        self.second_student.set_password('second-student-password')
        self.second_student.save()
        now = timezone.now()
        license_payload = {
            'license_id': str(uuid4()), 'school_id': 55, 'service_code': 'offline_cbt',
            'starts_on': timezone.localdate().isoformat(), 'expires_on': (timezone.localdate() + timedelta(days=10)).isoformat(),
            'offline_grace_days': 7,
        }
        license_token = signing.dumps(license_payload, key=LICENSE_KEY, salt='edustacked.service-license.v1')
        payload = {
            'package_id': str(uuid4()), 'package_version': 1, 'school_id': 55, 'examination_id': str(uuid4()),
            'license': {'payload': license_payload, 'signed_token': license_token},
            'assigned_student_ids': [101, 102], 'assigned_students': [
                {'student_id': 101, 'assignment_id': str(uuid4()), 'admission_number': 'ST-101'},
                {'student_id': 102, 'assignment_id': str(uuid4()), 'admission_number': 'ST-102'},
            ],
            'title': 'Offline Mathematics', 'subject': 'Math', 'class_name': 'JSS 1', 'instructions': 'Read carefully.',
            'starts_at': (now - timedelta(minutes=1)).isoformat(), 'ends_at': (now + timedelta(hours=2)).isoformat(),
            'duration_minutes': 30, 'maximum_attempts': 1,
            'questions': [{'question_id': 'q1', 'position': 0, 'prompt': '2 + 2?', 'type': 'single_choice', 'marks': '2', 'options': [{'id': 'q1:0', 'text': '3'}, {'id': 'q1:1', 'text': '4'}]}],
            'answer_key': [{'question_id': 'q1', 'correct_option_ids': ['q1:1']}],
        }
        self.package_token = signing.dumps({'payload': payload, 'sha256': sha256(canonical_json(payload)).hexdigest()}, key=PACKAGE_KEY, salt='edustacked.offline-cbt-package.v1', compress=True)
        self.package, _ = import_package(self.package_token)
        self.client = APIClient()

    def login(self):
        response = self.client.post('/local/api/v1/auth/login/', {'admission_number': 'ST-101', 'password': 'temporary-student-password'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['token']}")

    def start(self):
        response = self.client.post(f'/local/api/v1/exams/{self.package.package_id}/start/', {}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_package_signature_and_duplicate_import(self):
        duplicate, created = import_package(self.package_token)
        self.assertFalse(created)
        self.assertEqual(duplicate.pk, self.package.pk)
        with self.assertRaises(Exception):
            import_package(self.package_token + 'tampered')

    def test_student_session_answer_refresh_and_idempotent_submission(self):
        self.login()
        started = self.start()
        self.assertNotIn('answer_key', started)
        session_id = started['session_id']
        answer = {'request_id': str(uuid4()), 'question_id': 'q1', 'value': 'q1:1'}
        first = self.client.post(f'/local/api/v1/sessions/{session_id}/answers/', answer, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        duplicate = self.client.post(f'/local/api/v1/sessions/{session_id}/answers/', answer, format='json')
        self.assertTrue(duplicate.data['duplicate'])
        recovered = self.client.get(f'/local/api/v1/sessions/{session_id}/')
        self.assertEqual(recovered.data['questions'][0]['answer'], 'q1:1')
        submitted = self.client.post(f'/local/api/v1/sessions/{session_id}/submit/', {}, format='json')
        self.assertEqual(submitted.status_code, 200, submitted.data)
        second_submit = self.client.post(f'/local/api/v1/sessions/{session_id}/submit/', {}, format='json')
        self.assertEqual(second_submit.data['submission_id'], submitted.data['submission_id'])
        self.assertEqual(LocalSubmission.objects.count(), 1)
        self.assertEqual(SyncOutbox.objects.count(), 1)
        locked = self.client.post(f'/local/api/v1/sessions/{session_id}/answers/', {'request_id': str(uuid4()), 'question_id': 'q1', 'value': 'q1:0'}, format='json')
        self.assertEqual(locked.status_code, 409)

    def test_unassigned_student_cannot_start_package(self):
        self.login()
        self.student.central_student_id = 999
        self.student.save(update_fields=['central_student_id'])
        response = self.client.post(f'/local/api/v1/exams/{self.package.package_id}/start/', {}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_multiple_students_can_hold_simultaneous_sessions(self):
        self.login()
        first = self.start()
        second_client = APIClient()
        login = second_client.post('/local/api/v1/auth/login/', {'admission_number': 'ST-102', 'password': 'second-student-password'}, format='json')
        second_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")
        second = second_client.post(f"/local/api/v1/exams/{self.package.package_id}/start/", {}, format='json')
        self.assertEqual(second.status_code, 201, second.data)
        self.assertNotEqual(first['session_id'], second.data['session_id'])
        self.assertEqual(LocalExamSession.objects.filter(status=LocalExamSession.Status.IN_PROGRESS).count(), 2)

    def test_answer_endpoint_requires_student_authentication(self):
        response = self.client.get('/local/api/v1/exams/')
        self.assertEqual(response.status_code, 401)

    def test_sync_outage_keeps_submission_pending_and_retry_can_succeed(self):
        self.login()
        started = self.start()
        self.client.post(f"/local/api/v1/sessions/{started['session_id']}/submit/", {}, format='json')
        row = SyncOutbox.objects.get()
        with override_settings(CENTRAL_SYNC_URL='https://central.example.test', CENTRAL_SYNC_TOKEN='trusted-server-token'):
            with patch('offline_exam.sync.urlopen', side_effect=URLError('offline')):
                result = process_due_outbox()
            row.refresh_from_db()
            self.assertEqual(result['synced'], 0)
            self.assertEqual(row.status, SyncOutbox.Status.PENDING)
            self.assertEqual(row.retry_count, 1)
            SyncOutbox.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())

            class AcceptedResponse:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self): return b'{"accepted": true, "duplicate": false}'

            with patch('offline_exam.sync.urlopen', return_value=AcceptedResponse()):
                result = process_due_outbox()
            row.refresh_from_db()
            self.assertEqual(result['synced'], 1)
            self.assertEqual(row.status, SyncOutbox.Status.SYNCED)

    def test_sync_worker_finalizes_expired_sessions_without_student_request(self):
        self.login()
        started = self.start()
        LocalExamSession.objects.filter(pk=started['session_id']).update(expires_at=timezone.now() - timedelta(seconds=1))
        result = process_due_outbox()
        session = LocalExamSession.objects.get(pk=started['session_id'])
        self.assertEqual(result['expired_submissions'], 1)
        self.assertEqual(session.status, LocalExamSession.Status.AUTO_SUBMITTED)
        self.assertTrue(SyncOutbox.objects.filter(session=session).exists())
