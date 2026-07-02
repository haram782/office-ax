from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chat", "0005_rename_chat_ual_user_type_time_idx_chat_userac_user_id_1a005e_idx_and_more"),
        ("documents", "0010_restore_documentversion_artifact_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="UsageEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("document_analysis", "문서 분석"), ("chat_qa", "채팅 Q&A"), ("patch_plan_generation", "수정 계획 생성"), ("patch_artifact_generation", "수정본 생성")], db_index=True, max_length=40)),
                ("provider", models.CharField(blank=True, default="", max_length=50)),
                ("model", models.CharField(blank=True, default="", max_length=100)),
                ("input_tokens", models.PositiveIntegerField(default=0)),
                ("output_tokens", models.PositiveIntegerField(default=0)),
                ("token_source", models.CharField(choices=[("provider_reported", "공급자 보고"), ("estimated", "추정"), ("unavailable", "확인 불가")], default="unavailable", max_length=20)),
                ("estimated_cost", models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("status", models.CharField(choices=[("success", "성공"), ("failed", "실패")], default="success", max_length=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("chat_session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="usage_events", to="chat.chatsession")),
                ("document_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="usage_events", to="documents.documentversion")),
                ("upload_log", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="usage_events", to="documents.uploadlog")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="usage_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "사용량 이벤트",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="usageevent",
            index=models.Index(fields=["user", "created_at"], name="documents_u_user_id_d986dd_idx"),
        ),
        migrations.AddIndex(
            model_name="usageevent",
            index=models.Index(fields=["user", "event_type", "created_at"], name="documents_u_user_id_9b705d_idx"),
        ),
        migrations.AddIndex(
            model_name="usageevent",
            index=models.Index(fields=["user", "status", "created_at"], name="documents_u_user_id_b66615_idx"),
        ),
    ]
