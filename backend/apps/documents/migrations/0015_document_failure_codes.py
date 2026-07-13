# Django 5.0.6 기준으로 생성한 비파괴적 필드 추가 마이그레이션

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0014_documentversion_needs_confirmation_change_ids_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentchange",
            name="failure_code",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="documentversion",
            name="failure_code",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
    ]
