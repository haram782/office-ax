from unittest.mock import patch

from django.test import SimpleTestCase


class HealthEndpointTest(SimpleTestCase):
    def test_liveness_does_not_touch_dependencies(self):
        with patch("config.health.connections") as databases, patch("config.health.Redis") as redis:
            response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        databases.assert_not_called()
        redis.assert_not_called()

    @patch("config.health.Redis.from_url")
    @patch("config.health.connections")
    def test_readiness_returns_200_when_dependencies_are_ready(self, connections, redis):
        connections.__getitem__.return_value.cursor.return_value.__enter__.return_value.execute.return_value = None
        redis.return_value.ping.return_value = True
        self.assertEqual(self.client.get("/readyz").status_code, 200)

    @patch("config.health.Redis.from_url", side_effect=RuntimeError("redis secret detail"))
    def test_readiness_returns_redacted_503(self, _redis):
        response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "secret detail", status_code=503)
        self.assertContains(response, "redis", status_code=503)
