# FileStructure.source_type: max_length 10→20, SourceType choices 확장
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_add_file_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='filestructure',
            name='source_type',
            field=models.CharField(
                choices=[
                    ('excel', 'Excel (.xlsx)'),
                    ('pdf',   'PDF'),
                    ('csv',   'CSV'),
                    ('docx',  'Word (.docx)'),
                    ('pptx',  'PowerPoint (.pptx)'),
                    ('hwp',   '한글 (.hwp/.hwpx)'),
                    ('image', '이미지 (PNG/JPG)'),
                ],
                max_length=20,
            ),
        ),
    ]
