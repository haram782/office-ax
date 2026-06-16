# UserActionLog.FileType에 PPTX 추가
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0003_useractionlog_expand'),
    ]

    operations = [
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
                    ('pptx',        'PowerPoint (.pptx)'),
                    ('hwp',         '한글 문서 (.hwp)'),
                    ('csv',         'CSV'),
                    ('unknown',     '알 수 없음'),
                ],
                default='unknown',
                max_length=20,
            ),
        ),
    ]
