from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0006_bookmark_todo_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='presence',
            field=models.CharField(choices=[('online', '在线'), ('offline', '离线'), ('busy', '忙碌'), ('invisible', '隐身')], default='offline', help_text='在线状态', max_length=10),
        ),
        migrations.AlterField(
            model_name='message',
            name='type',
            field=models.CharField(choices=[('text', '文本'), ('image', '图片'), ('video', '视频'), ('audio', '语音'), ('file', '文件'), ('code', '代码'), ('contact_card', '好友名片'), ('calendar_invite', '日程邀请'), ('forward', '合并转发'), ('system', '系统消息')], default='text', max_length=15),
        ),
        migrations.AlterField(
            model_name='bookmark',
            name='conversation',
            field=models.ForeignKey(blank=True, help_text='消息所在会话（冗余字段，方便查询）', null=True, on_delete=django.db.models.deletion.CASCADE, to='chat.conversation'),
        ),
        migrations.AlterField(
            model_name='bookmark',
            name='message',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='bookmarks', to='chat.message'),
        ),
        migrations.AddField(
            model_name='bookmark',
            name='title',
            field=models.CharField(blank=True, default='', help_text='手动待办标题；消息待办可为空', max_length=200),
        ),
        migrations.CreateModel(
            name='CalendarEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, default='')),
                ('start_at', models.DateTimeField(db_index=True)),
                ('end_at', models.DateTimeField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_calendar_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'chat_calendar_event',
            },
        ),
        migrations.CreateModel(
            name='CalendarParticipant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('creator', '创建者'), ('invitee', '受邀者')], default='invitee', max_length=10)),
                ('status', models.CharField(choices=[('pending', '待处理'), ('accepted', '已接受'), ('rejected', '已拒绝')], default='pending', max_length=10)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participants', to='chat.calendarevent')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calendar_participations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'chat_calendar_participant',
                'unique_together': {('event', 'user')},
            },
        ),
        migrations.AddIndex(
            model_name='calendarevent',
            index=models.Index(fields=['creator', 'start_at'], name='chat_calend_creator_40aa80_idx'),
        ),
        migrations.AddIndex(
            model_name='calendarevent',
            index=models.Index(fields=['start_at', 'end_at'], name='chat_calend_start_a_e69814_idx'),
        ),
        migrations.AddIndex(
            model_name='calendarparticipant',
            index=models.Index(fields=['user', 'status'], name='chat_calend_user_id_1a7594_idx'),
        ),
        migrations.AddIndex(
            model_name='calendarparticipant',
            index=models.Index(fields=['event', 'status'], name='chat_calend_event_i_fde51b_idx'),
        ),
    ]
