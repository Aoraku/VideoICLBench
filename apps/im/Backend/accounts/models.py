import time
from django.contrib.auth.models import User
from django.db import models

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=20, blank=True, default="")
    avatar = models.TextField(blank=True, default="")
    created_at = models.FloatField()

class RevokedToken(models.Model):
    jti = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="revoked_tokens")
    expires_at = models.FloatField()


class EmailVerificationCode(models.Model):
    email = models.EmailField(db_index=True)
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, default="register")
    expires_at = models.FloatField()
    used_at = models.FloatField(null=True, blank=True)
    created_at = models.FloatField(default=time.time)

class FriendGroup(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friend_groups")
    name = models.CharField(max_length=100)
    created_at = models.FloatField(default=time.time)

    class Meta:
        unique_together = (("user", "name"),)

class Friend(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friends")
    friend_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friend_of")
    group = models.ForeignKey(FriendGroup, on_delete=models.SET_NULL, null=True, blank=True)

class FriendRequest(models.Model):
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_friend_requests")
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_friend_requests")
    message = models.TextField(blank=True, default="")
    source = models.CharField(max_length=50, default="search")
    status = models.CharField(max_length=20, default="pending")
    created_at = models.FloatField()


class Conversation(models.Model):
    type = models.CharField(max_length=20)
    name = models.CharField(max_length=100, blank=True, default="")
    avatar = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_conversations")
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="owned_conversations",
        null=True,
        blank=True,
    )
    updated_at = models.FloatField(default=time.time)
    created_at = models.FloatField(default=time.time)


class ConversationMember(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conversation_memberships")
    is_admin = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)
    unread_count = models.IntegerField(default=0)
    joined_at = models.FloatField(default=time.time)

    class Meta:
        unique_together = (("conversation", "user"),)


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    content = models.TextField()
    reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    created_at = models.FloatField(default=time.time)

class DeletedMessage(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="deleted_by_users")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="deleted_messages")

    class Meta:
        unique_together = (("message", "user"),)
        indexes = [
            models.Index(fields=["user", "message"]),
        ]


class GroupInvitation(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="group_invitations")
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_group_invitations")
    invitee = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_group_invitations")
    status = models.CharField(max_length=20, default="pending")
    created_at = models.FloatField(default=time.time)

    class Meta:
        indexes = [
            models.Index(fields=["conversation", "status", "created_at"]),
        ]


class GroupAnnouncement(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="group_announcements")
    publisher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="published_group_announcements")
    content = models.TextField()
    created_at = models.FloatField(default=time.time)
