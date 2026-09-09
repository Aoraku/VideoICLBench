from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversationmember',
            name='is_removed',
            field=models.BooleanField(default=False, help_text='群成员是否已退出或被移除（区别于用户主动删除会话）'),
        ),
    ]
