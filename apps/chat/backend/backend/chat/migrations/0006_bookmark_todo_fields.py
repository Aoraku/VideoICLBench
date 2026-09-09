from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0005_user_ai_api_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='bookmark',
            name='archived_at',
            field=models.DateTimeField(blank=True, help_text='归档时间', null=True),
        ),
        migrations.AddField(
            model_name='bookmark',
            name='is_archived',
            field=models.BooleanField(default=False, help_text='是否已归档'),
        ),
        migrations.AddField(
            model_name='bookmark',
            name='position',
            field=models.PositiveIntegerField(default=0, help_text='待办排序位置，数值越小越靠前'),
        ),
        migrations.AddIndex(
            model_name='bookmark',
            index=models.Index(fields=['user', 'is_archived', 'position'], name='chat_bookma_user_id_ef3ff4_idx'),
        ),
    ]
