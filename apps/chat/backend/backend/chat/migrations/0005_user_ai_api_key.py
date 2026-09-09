from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0004_recall_actor_reactionevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='ai_api_key',
            field=models.CharField(blank=True, default='', help_text='用户个人 AI API Key，仅用于本人 AI 调用', max_length=500),
        ),
    ]
