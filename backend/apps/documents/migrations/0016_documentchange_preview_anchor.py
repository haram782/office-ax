# Django 5.0.6 기준으로 생성한 비파괴적 필드 추가 마이그레이션

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0015_document_failure_codes"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentchange",
            name="preview_anchor",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
