# Generated manually 2026-06-15
# UserActionLog 확장: action_type, upload_log, meta 필드 추가
# FileType choices 확장 (image/docx/hwp/csv) — DB 컬럼 변경 없음(CharField)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_add_snippet_fields'),
        ('documents', '0002_add_file_fields'),
    ]

    operations = [
        # action_type: 기존 레코드는 모두 analysis_done (tasks.py에서만 생성됐음)
        migrations.AddField(
            model_name='useractionlog',
            name='action_type',
            field=models.CharField(
                choices=[
                    ('file_upload',     '파일 업로드'),
                    ('duplicate_hit',   '중복 파일 재사용'),
                    ('analysis_done',   'AI 분석 완료'),
                    ('analysis_failed', '분석 실패'),
                ],
                db_index=True,
                default='analysis_done',
                max_length=32,
            ),
            preserve_default=False,
        ),
        # upload_log FK — nullable (upload 없이 발생하는 액션 대비)
        migrations.AddField(
            model_name='useractionlog',
            name='upload_log',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='action_logs',
                to='documents.uploadlog',
            ),
        ),
        # meta JSON — 파인튜닝 학습 컨텍스트
        migrations.AddField(
            model_name='useractionlog',
            name='meta',
            field=models.JSONField(blank=True, default=dict),
        ),
        # action_tag — 기존엔 required였으나 blank 허용으로 완화
        migrations.AlterField(
            model_name='useractionlog',
            name='action_tag',
            field=models.CharField(blank=True, max_length=100),
        ),
        # FileType choices 확장 (image / docx / hwp / csv)
        migrations.AlterField(
            model_name='useractionlog',
            name='file_type',
            field=models.CharField(
                choices=[
                    ('xlsx',        '엑셀 (.xlsx)'),
                    ('pdf_digital', '디지털 PDF'),
                    ('pdf_image',   '스캔 PDF / 이미지'),
                    ('image',       '이미지 (PNG/JPG)'),
                    ('docx',        'Word 문서 (.docx)'),
                    ('hwp',         '한글 문서 (.hwp)'),
                    ('csv',         'CSV'),
                    ('unknown',     '알 수 없음'),
                ],
                default='unknown',
                max_length=20,
            ),
        ),
        # 복합 인덱스 추가
        migrations.AddIndex(
            model_name='useractionlog',
            index=models.Index(
                fields=['user', 'action_type', 'created_at'],
                name='chat_ual_user_type_time_idx',
            ),
        ),
    ]
