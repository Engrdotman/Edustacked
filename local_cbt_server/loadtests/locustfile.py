"""Controlled school-LAN load test; requires a unique account per virtual student."""

import csv
import os
import uuid
from itertools import count
from pathlib import Path

from locust import HttpUser, between, task


credentials_path = Path(os.environ.get("LOCAL_CBT_STUDENT_CREDENTIALS", "student-credentials.csv"))
with credentials_path.open(newline="", encoding="utf-8-sig") as file:
    credentials = list(csv.DictReader(file))
if not credentials or not {"admission_number", "password"}.issubset(credentials[0]):
    raise RuntimeError("Credentials CSV must contain admission_number,password columns and at least one row.")
credential_index = count()


class ExaminationUser(HttpUser):
    wait_time = between(0, 0)

    def on_start(self):
        index = next(credential_index)
        if index >= len(credentials):
            self.environment.runner.quit()
            return
        credential = credentials[index]
        response = self.client.post("/local/api/v1/auth/login/", json={
            "admission_number": credential["admission_number"], "password": credential["password"],
        }, name="student login")
        if response.status_code != 200:
            self.stop(True)
            return
        self.client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
        response = self.client.get("/local/api/v1/exams/", name="load assigned exams")
        if response.status_code != 200 or not response.json():
            self.stop(True)
            return
        exam = response.json()[0]
        if exam.get("status") == "in_progress":
            session_id = exam.get("session_id")
            response = self.client.get(f"/local/api/v1/sessions/{session_id}/", name="resume exam")
        else:
            response = self.client.post(f"/local/api/v1/exams/{exam['package_id']}/start/", json={}, name="start exam")
        if response.status_code not in (200, 201):
            self.stop(True)
            return
        self.session = response.json()

    @task
    def save_and_submit(self):
        if not getattr(self, "session", None):
            self.stop()
            return
        session_id = self.session["session_id"]
        for question in self.session["questions"]:
            options = question.get("options", [])
            if question["type"] == "text":
                value = "Controlled load test response."
            elif question["type"] == "multiple_answer":
                value = [options[0]["id"]] if options else []
            else:
                value = options[0]["id"] if options else ""
            self.client.post(f"/local/api/v1/sessions/{session_id}/answers/", json={
                "request_id": str(uuid.uuid4()), "question_id": question["question_id"], "value": value,
            }, name="save answer")
        self.client.get(f"/local/api/v1/sessions/{session_id}/", name="recover saved answers")
        self.client.post(f"/local/api/v1/sessions/{session_id}/submit/", json={}, name="submit exam")
        self.stop()
