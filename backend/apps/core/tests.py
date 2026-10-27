from django.urls import reverse
from unittest.mock import patch
from django.db import DatabaseError
from rest_framework import status
from rest_framework.test import APITestCase


class HealthCheckTests(APITestCase):
    def test_health_endpoint_returns_ok_without_authentication(self):
        response = self.client.get(reverse("health-check", kwargs={"version": "v1"}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_database_health_endpoint_reports_database_connectivity(self):
        response = self.client.get(
            reverse("database-health-check", kwargs={"version": "v1"})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    @patch("apps.core.views.connections")
    def test_database_health_endpoint_hides_database_errors(self, connections):
        connections.__getitem__.return_value.cursor.side_effect = DatabaseError(
            "private connection detail"
        )

        response = self.client.get(
            reverse("database-health-check", kwargs={"version": "v1"})
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json(), {"status": "error", "database": "unavailable"})
        self.assertNotIn("private connection detail", response.content.decode())
