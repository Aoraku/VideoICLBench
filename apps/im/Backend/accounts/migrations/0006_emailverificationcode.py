from django.db import migrations, models
import time


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_conversation_owner_conversationmember_is_admin_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailVerificationCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("code", models.CharField(max_length=6)),
                ("purpose", models.CharField(default="register", max_length=20)),
                ("expires_at", models.FloatField()),
                ("used_at", models.FloatField(blank=True, null=True)),
                ("created_at", models.FloatField(default=time.time)),
            ],
        ),
    ]
