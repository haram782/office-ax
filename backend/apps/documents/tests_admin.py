"""
UsageEventAdmin 설정 검증.

커버 범위:
  1. list_display에 event_type/provider/model/total_tokens/estimated_cost 노출
  2. list_filter에 event_type/provider/status/token_source/생성일 노출
"""
from django.contrib import admin
from django.test import SimpleTestCase

from apps.documents.models import UsageEvent


class UsageEventAdminConfigTest(SimpleTestCase):
    def setUp(self):
        self.admin_instance = admin.site._registry[UsageEvent]

    def test_list_display_shows_required_fields(self):
        for field in ["event_type", "provider", "model", "total_tokens", "estimated_cost"]:
            self.assertIn(field, self.admin_instance.list_display)

    def test_list_filter_includes_token_source_and_period(self):
        for field in ["event_type", "provider", "status", "token_source", "created_at"]:
            self.assertIn(field, self.admin_instance.list_filter)
