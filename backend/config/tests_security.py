from django.conf import settings
from django.test import SimpleTestCase


class ProductionSecuritySettingsTest(SimpleTestCase):
    def test_proxy_cookie_and_transport_settings_are_explicit(self):
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")
        self.assertGreaterEqual(settings.SECURE_HSTS_SECONDS, 0)
