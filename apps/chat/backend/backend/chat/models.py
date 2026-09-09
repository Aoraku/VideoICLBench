"""
即时通讯系统 - 数据模型定义
对应 API 文档 v3.0 全部功能

使用方式：
1. python manage.py startapp im
2. 将本文件内容复制到 im/models.py
3. 在 settings.py 的 INSTALLED_APPS 中添加 'im'
4. python manage.py makemigrations im
5. python manage.py migrate
"""

import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


# ============================================================
# 一、用户相关模型
# ============================================================

class User(AbstractUser):
    """
    用户模型，继承 Django 的 AbstractUser。
    AbstractUser 已自带：id, username, password, email, is_active, date_joined 等字段。
    我们在此基础上扩展 IM 系统所需的额外字段。

    对应接口：1.1 注册, 1.2 登录, 2.1-2.3 用户信息
    """

    phone = models.CharField(
        max_length=20, blank=True, default='',
        db_index=True,
        help_text="手机号"
    )
    avatar = models.URLField(
        max_length=500, blank=True, default='',
        help_text="头像 URL"
    )

    # ---- 自定义状态 (对应 2.8) ----
    PRESENCE_CHOICES = [
        ('online', '在线'),
        ('offline', '离线'),
        ('busy', '忙碌'),
        ('invisible', '隐身'),
    ]
    presence = models.CharField(
        max_length=10, choices=PRESENCE_CHOICES, default='offline',
        help_text="在线状态"
    )
    status_text = models.CharField(
        max_length=100, blank=True, default='',
        help_text="自定义状态文本"
    )
    status_emoji = models.CharField(
        max_length=10, blank=True, default='',
        help_text="状态 Emoji"
    )
    last_seen = models.DateTimeField(
        null=True, blank=True,
        help_text="最后在线时间"
    )
    ai_api_key = models.CharField(
        max_length=500, blank=True, default='',
        help_text="用户个人 AI API Key，仅用于本人 AI 调用"
    )

    class Meta:
        db_table = 'chat_user'

    def __str__(self):
        return f"User({self.id}: {self.username})"


class UserPrivacy(models.Model):
    """
    用户隐私设置，与 User 一对一关联。
    用户注册时自动创建默认隐私设置。

    对应接口：2.6, 2.7 隐私设置
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='privacy'
    )
    allow_search_by_username = models.BooleanField(
        default=True,
        help_text="是否允许通过用户名被搜索到"
    )
    allow_search_by_email = models.BooleanField(
        default=True,
        help_text="是否允许通过邮箱被搜索到"
    )
    allow_search_by_phone = models.BooleanField(
        default=True,
        help_text="是否允许通过手机号被搜索到"
    )
    allow_add_from_group = models.BooleanField(
        default=True,
        help_text="是否允许群聊内成员直接添加好友"
    )

    class Meta:
        db_table = 'chat_user_privacy'

    def __str__(self):
        return f"Privacy({self.user.username})"


# ============================================================
# 二、好友关系相关模型
# ============================================================

class FriendGroup(models.Model):
    """
    好友分组。每个用户可以创建多个分组。
    未分组的好友 group_id 为 null。

    对应接口：3.6-3.9 好友分组管理
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='friend_groups'
    )
    name = models.CharField(
        max_length=50,
        help_text="分组名称"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_friend_group'
        unique_together = ('user', 'name')  # 同一用户的分组名不可重复

    def __str__(self):
        return f"FriendGroup({self.user.username}/{self.name})"


class Friendship(models.Model):
    """
    好友关系。好友关系是双向的，A 和 B 成为好友后会创建两条记录：
    (user=A, friend=B) 和 (user=B, friend=A)。
    每条记录独立存储备注、分组信息（因为 A 对 B 的备注和 B 对 A 的备注不同）。

    对应接口：3.4 好友列表, 3.5 删除好友, 3.10 设置备注
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='friendships'
    )
    friend = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='friended_by'
    )
    remark = models.CharField(
        max_length=30, blank=True, default='',
        help_text="好友备注名"
    )
    group = models.ForeignKey(
        FriendGroup, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='friendships',
        help_text="所属好友分组，null 表示未分组"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_friendship'
        unique_together = ('user', 'friend')

    def __str__(self):
        return f"Friendship({self.user.username} -> {self.friend.username})"


class FriendRequest(models.Model):
    """
    好友申请。

    对应接口：3.1 发送好友申请, 3.2 获取列表, 3.3 处理申请
    """

    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('accepted', '已同意'),
        ('rejected', '已拒绝'),
    ]

    from_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='sent_friend_requests'
    )
    to_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='received_friend_requests'
    )
    message = models.CharField(
        max_length=200, blank=True, default='',
        help_text="验证消息"
    )
    source = models.CharField(
        max_length=100, blank=True, default='search',
        help_text="来源: search / group:{conv_id} / contact_card:{msg_id}"
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_friend_request'
        indexes = [
            models.Index(fields=['to_user', 'status']),
            models.Index(fields=['from_user', 'status']),
        ]

    def __str__(self):
        return f"FriendRequest({self.from_user.username} -> {self.to_user.username}, {self.status})"


class Blacklist(models.Model):
    """
    黑名单。单向关系：A 拉黑 B，B 不知道自己被拉黑。

    对应接口：3.11-3.13 黑名单管理
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='blacklist'
    )
    blocked_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='blocked_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_blacklist'
        unique_together = ('user', 'blocked_user')

    def __str__(self):
        return f"Blacklist({self.user.username} blocked {self.blocked_user.username})"


class Whitelist(models.Model):
    """
    白名单。白名单用户在好友申请时跳过隐私权限检查。
    优先级：黑名单 > 白名单 > 隐私设置。

    对应接口：3.14-3.16 白名单管理
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='whitelist'
    )
    whitelisted_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='whitelisted_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_whitelist'
        unique_together = ('user', 'whitelisted_user')


# ============================================================
# 三、会话相关模型
# ============================================================

class Conversation(models.Model):
    """
    会话（聊天窗口）。私聊和群聊统一用 conversation_id 标识。
    这是 IM 系统的核心模型之一。

    对应接口：4.1-4.7 会话模块, 6.1-6.16 群聊管理模块
    """

    TYPE_CHOICES = [
        ('private', '私聊'),
        ('group', '群聊'),
        ('ai', 'AI 对话'),
    ]

    type = models.CharField(
        max_length=10, choices=TYPE_CHOICES
    )
    name = models.CharField(
        max_length=50, blank=True, default='',
        help_text="会话名称（群聊使用，私聊为空）"
    )
    avatar = models.URLField(
        max_length=500, blank=True, default='',
        help_text="群头像 URL"
    )

    # ---- 群聊专属字段 ----
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_conversations',
        help_text="群主（仅群聊有值）"
    )
    is_dissolved = models.BooleanField(
        default=False,
        help_text="群聊是否已解散"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_conversation'
        indexes = [
            models.Index(fields=['type']),
            models.Index(fields=['updated_at']),
        ]

    def __str__(self):
        return f"Conversation({self.id}: {self.type}, {self.name or 'private'})"


class ConversationMember(models.Model):
    """
    会话成员表。记录每个用户在每个会话中的成员关系和个性化设置。
    私聊有 2 个成员，群聊有 N 个成员。

    核心字段 read_index 用于计算未读消息数：
    unread_count = 当前会话中 msg_id > read_index 且非本人发送的消息条数

    对应接口：4.4 置顶/免打扰, 4.6 标记已读, 6.4 群成员列表, 6.5 群昵称
    """

    ROLE_CHOICES = [
        ('owner', '群主'),
        ('admin', '管理员'),
        ('member', '普通成员'),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='members'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='conversation_memberships'
    )
    role = models.CharField(
        max_length=10, choices=ROLE_CHOICES, default='member',
        help_text="成员角色（仅群聊有意义）"
    )
    nickname = models.CharField(
        max_length=30, blank=True, default='',
        help_text="群昵称"
    )

    # ---- 个性化设置（每个用户独立） ----
    is_pinned = models.BooleanField(
        default=False,
        help_text="是否置顶该会话"
    )
    is_muted = models.BooleanField(
        default=False,
        help_text="是否设置免打扰"
    )
    is_deleted = models.BooleanField(
        default=False,
        help_text="用户是否删除了该会话（收到新消息时自动恢复）"
    )
    is_removed = models.BooleanField(
        default=False,
        help_text="群成员是否已退出或被移除（区别于用户主动删除会话）"
    )

    # ---- 已读状态 ----
    read_index = models.BigIntegerField(
        default=0,
        help_text="该用户在此会话中已读到的最新 msg_id"
    )
    read_at = models.DateTimeField(
        null=True, blank=True,
        help_text="最后一次标记已读的时间"
    )

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_conversation_member'
        unique_together = ('conversation', 'user')
        indexes = [
            models.Index(fields=['user', 'is_deleted']),
            models.Index(fields=['user', 'is_pinned']),
        ]

    def __str__(self):
        return f"Member({self.user.username} in Conv {self.conversation_id}, {self.role})"


# ============================================================
# 四、消息相关模型
# ============================================================

class Message(models.Model):
    """
    消息模型。IM 系统最核心的表，所有类型的消息统一存储。
    content 以 JSONField 存储，结构随 type 不同而不同（见 API 文档全局约定）。

    关键设计：
    - msg_id 使用自增主键，在同一会话内单调递增，用于 cursor 分页和已读计数。
    - client_msg_id 用于客户端幂等去重。
    - reply_to 实现消息回复链。

    对应接口：5.1 发送消息, 5.2 获取聊天记录, 5.5 删除, 5.6 撤回
    """

    TYPE_CHOICES = [
        ('text', '文本'),
        ('image', '图片'),
        ('video', '视频'),
        ('audio', '语音'),
        ('file', '文件'),
        ('code', '代码'),
        ('contact_card', '好友名片'),
        ('calendar_invite', '日程邀请'),
        ('forward', '合并转发'),
        ('system', '系统消息'),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages',
        db_index=True
    )
    sender = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='sent_messages',
        help_text="发送者（已注销用户为 null）"
    )
    client_msg_id = models.UUIDField(
        default=uuid.uuid4, db_index=True,
        help_text="客户端生成的消息 UUID，用于幂等去重"
    )

    type = models.CharField(
        max_length=15, choices=TYPE_CHOICES, default='text'
    )
    content = models.JSONField(
        default=dict,
        help_text="消息内容，JSON 格式，结构随 type 不同"
    )

    # ---- 回复关系 ----
    reply_to = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replies',
        help_text="回复的目标消息"
    )

    # ---- @提及 ----
    mentions = models.ManyToManyField(
        User, blank=True, related_name='mentioned_in_messages',
        help_text="被 @ 提及的用户列表"
    )

    # ---- 撤回 ----
    is_recalled = models.BooleanField(
        default=False,
        help_text="是否已撤回"
    )
    recalled_at = models.DateTimeField(
        null=True, blank=True
    )
    recalled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recalled_messages',
        help_text="执行撤回操作的用户"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_message'
        indexes = [
            # 聊天记录的核心查询：按会话 + 消息 ID 倒序（cursor 分页）
            models.Index(fields=['conversation', '-id']),
            # 幂等去重查询
            models.Index(fields=['conversation', 'sender', 'client_msg_id']),
        ]
        ordering = ['id']  # 默认按 msg_id 升序

    def __str__(self):
        sender_name = self.sender.username if self.sender else '[已注销]'
        return f"Message({self.id}: {sender_name} in Conv {self.conversation_id}, {self.type})"


class MessageDeletion(models.Model):
    """
    消息软删除记录。记录某个用户删除了某条消息（仅对该用户不可见）。
    查询聊天记录时 LEFT JOIN 此表排除已删除的消息。

    对应接口：5.5 删除消息
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='deleted_messages'
    )
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name='deletions'
    )
    deleted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_message_deletion'
        unique_together = ('user', 'message')

    def __str__(self):
        return f"Deletion({self.user.username} deleted Msg {self.message_id})"


class Reaction(models.Model):
    """
    消息的 Emoji 表情回应。
    每个用户对同一条消息的同一个 Emoji 只能发一次。

    对应接口：5.8 Emoji Reaction
    """

    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name='reactions'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='reactions'
    )
    emoji = models.CharField(
        max_length=10,
        help_text="Emoji 字符"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_reaction'
        unique_together = ('message', 'user', 'emoji')

    def __str__(self):
        return f"Reaction({self.user.username}: {self.emoji} on Msg {self.message_id})"


class ReactionEvent(models.Model):
    """
    Reaction 变更事件，用于离线增量同步补齐 add/remove。
    """

    ACTION_CHOICES = [
        ('add', '添加'),
        ('remove', '取消'),
    ]

    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name='reaction_events'
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='reaction_events'
    )
    emoji = models.CharField(max_length=10)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    current_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_reaction_event'
        indexes = [
            models.Index(fields=['message', 'created_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        username = self.user.username if self.user else '[已注销]'
        return f"ReactionEvent({self.action} {self.emoji} by {username} on Msg {self.message_id})"


class Bookmark(models.Model):
    """
    消息收藏。用户可以收藏任何自己可见的消息。

    对应接口：5.9 收藏消息
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='bookmarks'
    )
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name='bookmarks',
        null=True, blank=True,
    )
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="消息所在会话（冗余字段，方便查询）"
    )
    title = models.CharField(
        max_length=200, blank=True, default='',
        help_text="手动待办标题；消息待办可为空"
    )
    note = models.CharField(
        max_length=200, blank=True, default='',
        help_text="收藏备注"
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="待办排序位置，数值越小越靠前"
    )
    is_archived = models.BooleanField(
        default=False,
        help_text="是否已归档"
    )
    archived_at = models.DateTimeField(
        null=True, blank=True,
        help_text="归档时间"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_bookmark'
        unique_together = ('user', 'message')  # 同一条消息不可重复收藏
        indexes = [
            models.Index(fields=['user', 'is_archived', 'position']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"Bookmark({self.user.username} -> Msg {self.message_id})"


class CalendarEvent(models.Model):
    """
    日程事件。事件本身由创建者维护，参与者关系记录每个用户是否接受。
    """

    creator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='created_calendar_events'
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_calendar_event'
        indexes = [
            models.Index(fields=['creator', 'start_at']),
            models.Index(fields=['start_at', 'end_at']),
        ]

    def __str__(self):
        return f"CalendarEvent({self.id}: {self.title})"


class CalendarParticipant(models.Model):
    """
    日程参与者/邀请记录。status 为 accepted 时进入该用户日历。
    """

    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('accepted', '已接受'),
        ('rejected', '已拒绝'),
    ]
    ROLE_CHOICES = [
        ('creator', '创建者'),
        ('invitee', '受邀者'),
    ]

    event = models.ForeignKey(
        CalendarEvent, on_delete=models.CASCADE, related_name='participants'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='calendar_participations'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='invitee')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_calendar_participant'
        unique_together = ('event', 'user')
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['event', 'status']),
        ]

    def __str__(self):
        return f"CalendarParticipant({self.event_id}/{self.user_id}/{self.status})"


# ============================================================
# 五、群聊管理相关模型
# ============================================================

class GroupInvitation(models.Model):
    """
    群聊邀请。群成员邀请好友入群，需要群主/管理员审核。

    对应接口：6.11-6.13 入群邀请管理
    """

    STATUS_CHOICES = [
        ('pending', '待审核'),
        ('approved', '已通过'),
        ('rejected', '已拒绝'),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='invitations'
    )
    invitee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='group_invitations_received',
        help_text="被邀请者"
    )
    inviter = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='group_invitations_sent',
        help_text="邀请者"
    )
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_invitations',
        help_text="审核人（群主或管理员）"
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_group_invitation'
        indexes = [
            models.Index(fields=['conversation', 'status']),
        ]

    def __str__(self):
        return f"GroupInvitation({self.inviter.username} invited {self.invitee.username} to Conv {self.conversation_id})"


class GroupAnnouncement(models.Model):
    """
    群公告。群主和管理员可以发布公告。

    对应接口：6.14-6.15 群公告管理
    """

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='announcements'
    )
    publisher = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='published_announcements'
    )
    content = models.TextField(
        max_length=2000,
        help_text="公告内容"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_group_announcement'
        ordering = ['-created_at']  # 最新公告在前
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
        ]

    def __str__(self):
        return f"Announcement(Conv {self.conversation_id}: {self.content[:30]})"


# ============================================================
# 六、JWT Token 黑名单（用于登出时使 refresh_token 失效）
# ============================================================

class TokenBlacklist(models.Model):
    """
    Token 黑名单。用户登出时将 refresh_token 加入黑名单。
    刷新 Token 时检查是否在黑名单中。

    对应接口：1.4 用户登出
    """

    token = models.TextField(
        help_text="被拉黑的 refresh_token"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='blacklisted_tokens'
    )
    blacklisted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="Token 原始过期时间，过期后可以清理该记录"
    )

    class Meta:
        db_table = 'chat_token_blacklist'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]


# ============================================================
# 七、文件上传记录
# ============================================================

class UploadedFile(models.Model):
    """
    文件上传记录。记录用户上传的所有文件的元数据。
    实际文件存储在 MEDIA_ROOT 或 OSS/S3。

    对应接口：7.1 上传文件
    """

    PURPOSE_CHOICES = [
        ('message', '消息附件'),
        ('avatar', '头像'),
    ]

    uploader = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='uploaded_files'
    )
    file_id = models.CharField(
        max_length=50, unique=True, db_index=True,
        help_text="文件唯一标识"
    )
    url = models.URLField(
        max_length=500,
        help_text="文件访问 URL"
    )
    thumbnail_url = models.URLField(
        max_length=500, blank=True, default='',
        help_text="缩略图 URL（仅图片和视频）"
    )
    filename = models.CharField(
        max_length=255,
        help_text="原始文件名"
    )
    size = models.BigIntegerField(
        help_text="文件大小（字节）"
    )
    mime_type = models.CharField(
        max_length=100,
        help_text="MIME 类型"
    )
    width = models.IntegerField(
        null=True, blank=True,
        help_text="图片/视频宽度（像素）"
    )
    height = models.IntegerField(
        null=True, blank=True,
        help_text="图片/视频高度（像素）"
    )
    duration = models.IntegerField(
        null=True, blank=True,
        help_text="音频/视频时长（秒）"
    )
    purpose = models.CharField(
        max_length=10, choices=PURPOSE_CHOICES, default='message'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_uploaded_file'

    def __str__(self):
        return f"File({self.file_id}: {self.filename})"
