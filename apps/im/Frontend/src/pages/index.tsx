import React, { useEffect, useState, useRef } from 'react';
import {Layout, List, Avatar, Typography, message, Spin, Dropdown, type MenuProps, Badge, Input, Button, Empty, Modal, Drawer, Divider, Select, Switch, Upload } from 'antd';

import { 
  CloseOutlined, ContactsOutlined, LogoutOutlined, MessageOutlined, 
  SearchOutlined, SendOutlined, TeamOutlined, UserOutlined,
  PushpinOutlined, AudioMutedOutlined, MoreOutlined, DeleteOutlined,
  UsergroupAddOutlined, SoundOutlined, UserAddOutlined,
  PlusOutlined, RightOutlined, EditOutlined
} from '@ant-design/icons';
import { useRouter } from 'next/router';
import Head from 'next/head';

const { Content } = Layout;
const { Text,Title} = Typography;

const styles: Record<string, React.CSSProperties> = {
  appShell: { height: '100vh', display: 'flex', flexDirection: 'row', background: '#eaf5ff' },
  loadingShell: { height: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center' },
  sidebar: {
    width: 352,
    height: '100vh',
    flexShrink: 0,
    display: 'flex',
    background: '#ffffff',
    borderRight: '1px solid #d6e6f7',
    overflow: 'hidden',
  },
  rail: { width: 96, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '20px 0', background: 'linear-gradient(180deg, #16adff 0%, #078df2 100%)' },
  listPane: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', background: '#ffffff' },
  sidebarHeader: {
    height: 72,
    padding: '18px 14px 12px',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    background: '#ffffff',
  },
  createButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    color: '#2f3b4d',
    background: '#f3f6fb',
    flexShrink: 0,
  },
  iconButton: {
    width: 54,
    height: 54,
    margin: '12px auto 0',
    borderRadius: '50%',
    color: '#ffffff',
    fontSize: 22,
    background: 'rgba(255, 255, 255, 0.16)',
    boxShadow: '0 10px 22px rgba(0, 111, 206, 0.18)',
  },
  accountButton: {
    width: 56,
    height: 56,
    margin: '8px auto 14px',
    padding: 0,
    borderRadius: '50%',
    background: 'rgba(255, 255, 255, 0.18)',
    boxShadow: '0 10px 22px rgba(0, 111, 206, 0.2)',
    cursor: 'pointer',
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchInput: {
    flex: 1,
    height: 32,
    border: 'none',
    borderRadius: 6,
    color: '#202936',
    background: '#f3f6fb',
  },
  listWrap: { flex: 1, overflowY: 'auto' },
  conversationItem: {
    padding: '13px 14px',
    cursor: 'pointer',
    borderBottom: '1px solid #edf3fa',
  },
  conversationActive: { background: '#cfeeff' },
  conversationTitleRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  conversationName: { maxWidth: 136, fontSize: 15, fontWeight: 600, color: '#202936' },
  conversationTime: { fontSize: 11, color: '#8492a6', flexShrink: 0 },
  conversationPreview: { maxWidth: 178, fontSize: 13, color: '#697586' },
  chatPane: {
    display: 'flex',
    flexDirection: 'column',
    background: 'linear-gradient(135deg, #fbf5ff 0%, #eaf2ff 48%, #d8eeff 100%)',
    minWidth: 0,
  },
  chatHeader: {
    height: 56,
    padding: '0 18px 0 24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    background: 'rgba(255, 255, 255, 0.72)',
    borderBottom: '1px solid #dbe8f8',
    backdropFilter: 'blur(10px)',
  },
  chatTitleWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
    minWidth: 0,
  },
  chatTitle: { fontSize: 16, fontWeight: 600, color: '#1f2937', maxWidth: 520 },
  chatMeta: { fontSize: 12, color: '#5b6b82' },
  messageArea: {
    flex: 1,
    padding: '28px 40px 24px',
    overflowY: 'auto',
    background: 'transparent',
  },
  messagesEmpty: {
    minHeight: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    paddingBottom: 80,
  },
  messageRow: {
    width: '100%',
    maxWidth: 920,
    display: 'flex',
    alignItems: 'flex-end',
    margin: '0 auto 16px',
    gap: 10,
  },
  messageStack: { display: 'flex', flexDirection: 'column', maxWidth: 'min(68%, 620px)' },
  messageAvatar: {
    flexShrink: 0,
    boxShadow: '0 8px 18px rgba(52, 112, 182, 0.16)',
    border: '2px solid rgba(255, 255, 255, 0.82)',
  },
  messageMeta: { marginBottom: 6, padding: '0 2px', fontSize: 11, lineHeight: 1.2, color: '#7a8aa0' },
  bubble: {
    padding: '11px 14px',
    borderRadius: 18,
    lineHeight: 1.55,
    wordBreak: 'break-word',
    whiteSpace: 'pre-wrap',
    cursor: 'context-menu',
    display: 'flex',
    flexDirection: 'column',
    fontSize: 14,
    boxShadow: '0 12px 26px rgba(65, 126, 194, 0.14)',
  },
  myBubble: {
    background: 'linear-gradient(135deg, #20b5ff 0%, #0b88f0 100%)',
    color: '#ffffff',
    borderRadius: '18px 18px 6px 18px',
  },
  otherBubble: {
    background: 'rgba(255, 255, 255, 0.94)',
    color: '#1f2937',
    border: '1px solid rgba(202, 220, 242, 0.8)',
    borderRadius: '18px 18px 18px 6px',
  },
  quoteBlock: {
    marginTop: 9,
    padding: '7px 9px',
    borderRadius: 10,
    fontSize: 12,
    lineHeight: 1.45,
    display: 'flex',
    flexDirection: 'column',
    cursor: 'pointer',
  },
  myQuote: { background: 'rgba(255, 255, 255, 0.24)', borderLeft: '3px solid rgba(255, 255, 255, 0.58)', color: 'rgba(255, 255, 255, 0.92)' },
  otherQuote: { background: '#f3f7fc', borderLeft: '3px solid #9fcdf7', color: '#5a6b7f' },
  replyCount: { marginTop: 5, fontSize: 11, color: '#8a99ad' },
  composer: {
    minHeight: 146,
    display: 'flex',
    flexDirection: 'column',
    background: 'rgba(247, 251, 255, 0.94)',
    borderTop: '1px solid #cae0f7',
    boxShadow: '0 -12px 30px rgba(63, 126, 194, 0.08)',
  },
  replyBar: {
    minHeight: 36,
    padding: '8px 24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    background: 'rgba(255, 255, 255, 0.62)',
  },
  composerBody: {
    flex: 1,
    padding: '16px 24px 20px',
    display: 'flex',
    gap: 14,
    alignItems: 'stretch',
  },
  textArea: {
    flex: 1,
    border: '1px solid #dbe8f8',
    borderRadius: 12,
    boxShadow: '0 8px 22px rgba(70, 123, 184, 0.08)',
    resize: 'none',
    fontSize: 15,
    lineHeight: 1.55,
    color: '#1f2937',
    background: '#ffffff',
    padding: '10px 12px',
  },
  sendButton: {
    minWidth: 84,
    height: 44,
    alignSelf: 'flex-end',
    borderRadius: 12,
    background: '#12a8ff',
    borderColor: '#12a8ff',
    boxShadow: '0 10px 22px rgba(18, 168, 255, 0.24)',
  },
  emptyState: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
    color: '#9fc7ef',
    background: 'transparent',
  },
  privateActionPanel: {
    width: 280,
    padding: 8,
    borderRadius: 12,
    background: '#f0f0f0',
  },
  privateActionGroup: {
    overflow: 'hidden',
    marginBottom: 12,
    borderRadius: 8,
    background: '#ffffff',
  },
  privateActionGroupLast: {
    marginBottom: 0,
  },
  privateActionRow: {
    minHeight: 36,
    padding: '0 14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  privateActionDivider: {
    borderTop: '1px solid #edf0f3',
  },
  privateActionLabel: {
    color: '#111827',
    fontSize: 14,
  },
  privateActionButton: {
    height: 36,
    padding: '0 14px',
    borderRadius: 0,
    textAlign: 'left',
    justifyContent: 'flex-start',
    color: '#111827',
  },
  privateDangerButton: {
    height: 36,
    padding: '0 14px',
    borderRadius: 0,
    justifyContent: 'center',
    color: '#ff3b30',
  },
  privateSettingBody: {
    minHeight: '100%',
    padding: 20,
    background: '#f7fbff',
  },
  privateMemberGrid: {
    display: 'flex',
    gap: 18,
    marginBottom: 22,
  },
  privateMemberTile: {
    width: 56,
    border: 'none',
    padding: 0,
    background: 'transparent',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 6,
    cursor: 'pointer',
  },
  privateMemberName: {
    width: '100%',
    textAlign: 'center',
    fontSize: 12,
    color: '#6f7c8f',
  },
  privateClearButton: {
    height: 44,
    borderRadius: 0,
    justifyContent: 'center',
    color: '#ff3b30',
  },
  profileCard: {
    padding: '4px 2px 0',
  },
  profileHeader: {
    display: 'flex',
    gap: 16,
    alignItems: 'center',
    paddingBottom: 18,
  },
  profileAvatar: {
    flexShrink: 0,
    background: 'linear-gradient(135deg, #8ad7ff, #118fff)',
    objectFit: 'cover',
  },
  profileName: {
    display: 'block',
    maxWidth: 220,
    color: '#172033',
    fontSize: 18,
    fontWeight: 700,
  },
  profileMeta: {
    display: 'block',
    marginTop: 4,
    color: '#6b7280',
    fontSize: 13,
  },
  profileInfoRow: {
    minHeight: 44,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 14,
    borderTop: '1px solid #edf2f7',
  },
  profileInfoLabel: {
    color: '#8a95a6',
  },
  profileInfoValue: {
    maxWidth: 220,
    color: '#263244',
  },
  profileActionBar: {
    paddingTop: 18,
    borderTop: '1px solid #edf2f7',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  profilePrimaryButton: {
    height: 42,
    borderRadius: 12,
    background: '#12a8ff',
    borderColor: '#12a8ff',
  },
  profileSecondaryButton: {
    height: 42,
    borderRadius: 12,
  },
  profileDangerButton: {
    height: 42,
    borderRadius: 12,
  },
  groupSettingBlock: {
    marginBottom: 18,
    overflow: 'hidden',
    borderRadius: 10,
    background: '#f7fbff',
    border: '1px solid #e4eef9',
  },
  groupSettingRow: {
    minHeight: 44,
    padding: '0 14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  groupSettingDivider: {
    borderTop: '1px solid #e4eef9',
  },
  groupSettingLabel: {
    color: '#253143',
  },
  groupSettingValue: {
    maxWidth: 180,
    color: '#6f7c8f',
  },
  groupAvatarButton: {
    position: 'relative',
    display: 'inline-flex',
    borderRadius: '50%',
    cursor: 'pointer',
  },
  groupAvatarEdit: {
    position: 'absolute',
    right: -2,
    bottom: -2,
    width: 24,
    height: 24,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#ffffff',
    background: '#12a8ff',
    boxShadow: '0 6px 14px rgba(18, 168, 255, 0.28)',
  },
  groupMemberTile: {
    width: 48,
    border: 'none',
    padding: 0,
    background: 'transparent',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 4,
    cursor: 'pointer',
  },
  groupInvitePlus: {
    width: 40,
    height: 40,
    borderRadius: '50%',
    border: '1px dashed #aab6c6',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#6f7c8f',
    background: '#ffffff',
  },
};

interface UserProfileCard {
  user_id: number;
  username: string;
  avatar?: string;
  isFriend?: boolean;
}

interface AddFriendTarget {
  id: number;
  name: string;
  avatar?: string;
}

interface SentFriendRequest {
  request_id: number;
  to_user: {
    user_id: number;
    username: string;
    avatar?: string;
  };
  message?: string;
  status?: string;
  created_at?: number;
}

const formatChatTime = (timestamp?: number) => {
  if (typeof timestamp !== 'number') return '';
  return new Date(timestamp * 1000).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getClearedConversationsStorageKey = () => {
  if (typeof window === 'undefined') return 'im_cleared_conversations:server';
  const userKey = localStorage.getItem('user_id') || localStorage.getItem('username') || 'current';
  return `im_cleared_conversations:${userKey}`;
};

const readClearedConversationTimes = (): Record<string, number> => {
  if (typeof window === 'undefined') return {};
  try {
    const cached = localStorage.getItem(getClearedConversationsStorageKey());
    const parsed = cached ? JSON.parse(cached) : {};
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
};

const writeClearedConversationTimes = (clearedTimes: Record<string, number>) => {
  if (typeof window === 'undefined') return;
  localStorage.setItem(getClearedConversationsStorageKey(), JSON.stringify(clearedTimes));
};

const markConversationCleared = (conversationId: number, clearedAt: number) => {
  const clearedTimes = readClearedConversationTimes();
  writeClearedConversationTimes({
    ...clearedTimes,
    [conversationId]: clearedAt,
  });
};

const getLastConversationStorageKey = () => {
  if (typeof window === 'undefined') return 'im_last_conversation:server';
  const userKey = localStorage.getItem('user_id') || localStorage.getItem('username') || 'current';
  return `im_last_conversation:${userKey}`;
};

const readLastConversationId = () => {
  if (typeof window === 'undefined') return undefined;
  const rawId = sessionStorage.getItem(getLastConversationStorageKey());
  if (!rawId) return undefined;
  const parsedId = Number(rawId);
  return Number.isNaN(parsedId) ? undefined : parsedId;
};

const writeLastConversationId = (conversationId: number) => {
  if (typeof window === 'undefined' || conversationId === -1) return;
  sessionStorage.setItem(getLastConversationStorageKey(), String(conversationId));
};

const clearLastConversationId = () => {
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem(getLastConversationStorageKey());
};

const getSentRequestsStorageKey = () => {
  if (typeof window === 'undefined') return 'im_sent_friend_requests:server';
  const userKey = localStorage.getItem('user_id') || localStorage.getItem('username') || 'current';
  return `im_sent_friend_requests:${userKey}`;
};

const getSentRequestTime = (request: SentFriendRequest) => request.created_at || 0;

const normalizeSentRequests = (requests: SentFriendRequest[]) => {
  const byUserId = new Map<number, SentFriendRequest>();
  requests.forEach((item) => {
    const userId = item.to_user?.user_id;
    if (!userId) return;
    const current = byUserId.get(userId);
    if (!current || getSentRequestTime(item) >= getSentRequestTime(current)) {
      byUserId.set(userId, item);
    }
  });
  return Array.from(byUserId.values()).sort((a, b) => getSentRequestTime(b) - getSentRequestTime(a));
};

const readCachedSentRequests = (): SentFriendRequest[] => {
  if (typeof window === 'undefined') return [];
  try {
    const cached = localStorage.getItem(getSentRequestsStorageKey());
    const parsed = cached ? JSON.parse(cached) : [];
    return Array.isArray(parsed) ? normalizeSentRequests(parsed) : [];
  } catch {
    return [];
  }
};

const writeCachedSentRequests = (requests: SentFriendRequest[]) => {
  if (typeof window === 'undefined') return;
  localStorage.setItem(getSentRequestsStorageKey(), JSON.stringify(normalizeSentRequests(requests)));
};

const upsertCachedSentRequest = (target: AddFriendTarget, messageText: string) => {
  const now = Math.floor(Date.now() / 1000);
  const cached = readCachedSentRequests();
  const exists = cached.some(item => item.to_user?.user_id === target.id);
  const next = exists
    ? cached.map(item => (
      item.to_user?.user_id === target.id
        ? {
          ...item,
          request_id: -now,
          to_user: {
            user_id: target.id,
            username: target.name,
            avatar: target.avatar,
          },
          message: messageText,
          status: 'pending',
          created_at: now,
        }
        : item
    ))
    : [{
      request_id: -now,
      to_user: {
        user_id: target.id,
        username: target.name,
        avatar: target.avatar,
      },
      message: messageText,
      status: 'pending',
      created_at: now,
    }, ...cached];

  writeCachedSentRequests(next);
};

export default function Home() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [initialFetched, setInitialFetched] = useState(false);
  const [userName, setUserName] = useState<string | undefined>('');
  const [userAvatar, setUserAvatar] = useState<string | undefined>('');
  const [userId, setUserId] = useState<number | undefined>(undefined);
  // 标记 userId 已从后端 profile 接口确认，避免用 localStorage 旧值误判气泡方向
  const [userIdConfirmed, setUserIdConfirmed] = useState(false);

  const [conversations, setConversations] = useState<any[]>([]);
  const [activeConv, setActiveConv] = useState<any>(undefined);
  const [messages, setMessages] = useState<any[]>([]);
  const [inputText, setInputText] = useState('');
  const [loadingMsg, setLoadingMsg] = useState(false);
  const [privateActionsOpen, setPrivateActionsOpen] = useState(false);
  const [privateActionLoading, setPrivateActionLoading] = useState<'clear' | 'friend' | undefined>(undefined);
  const [profileCardOpen, setProfileCardOpen] = useState(false);
  const [profileCardUser, setProfileCardUser] = useState<UserProfileCard | undefined>(undefined);
  const [profileCardLoading, setProfileCardLoading] = useState(false);

  const [replyingTo, setReplyingTo] = useState<any>(undefined);

  const [isAnnouncementModalVisible, setIsAnnouncementModalVisible] = useState(false);
  const [announcementText, setAnnouncementText] = useState('');

  const [groupDrawerOpen, setGroupDrawerOpen] = useState(false);
  const [groupInfo, setGroupInfo] = useState<any>(undefined);
  const [loadingGroupInfo, setLoadingGroupInfo] = useState(false);
  const [isAddFriendVisible, setIsAddFriendVisible] = useState(false);
  const [addFriendTarget, setAddFriendTarget] = useState<AddFriendTarget | undefined>(undefined);
  const [addFriendMessage, setAddFriendMessage] = useState('');

  // 处理过 URL ?to_user_id=...&name=... 之后置位，防止轮询触发的 conversations 变更
  // 反复把当前会话强行拉回到 URL 指定对象上
  const routerParamHandledRef = useRef(false);
  const restoredConversationRef = useRef(false);

  // eslint-disable-next-line no-restricted-syntax
  const messagesEndRef = useRef<HTMLDivElement>(null);



  const fetchGroupInfo = async () => {
    if (!activeConv || activeConv.type !== 'group') return;
    setLoadingGroupInfo(true);
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.code === 0) setGroupInfo(data);
    } catch {
      message.error('获取群信息失败');
    } finally {
      setLoadingGroupInfo(false);
    }
  };

  const handleOpenGroupInfo = () => {
    setGroupDrawerOpen(true);
    fetchGroupInfo();
  };

  const updateGroupProfile = async (payload: { name?: string; avatar?: string }) => {
    if (!activeConv || activeConv.type !== 'group' || activeConv.conversation_id === -1) return false;

    const token = localStorage.getItem('token');
    try {
      const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.code !== 0) {
        message.error(`更新失败: ${data.info}`);
        return false;
      }

      setGroupInfo((prev: any) => prev ? { ...prev, ...payload } : prev);
      setActiveConv((prev: any) => (
        prev?.conversation_id === activeConv.conversation_id ? { ...prev, ...payload } : prev
      ));
      setConversations(prev => prev.map((item) => (
        item.conversation_id === activeConv.conversation_id ? { ...item, ...payload } : item
      )));
      fetchConversations(token as string);
      return true;
    } catch {
      message.error('网络请求异常，无法更新群资料');
      return false;
    }
  };

  const handleEditGroupName = () => {
    let nextName = groupInfo?.name || '';
    Modal.confirm({
      title: '修改群聊名称',
      content: (
        <Input
          defaultValue={nextName}
          maxLength={30}
          placeholder="输入群聊名称"
          onChange={(event) => { nextName = event.target.value; }}
        />
      ),
      okText: '保存',
      cancelText: '取消',
      onOk: async () => {
        const trimmedName = nextName.trim();
        if (!trimmedName) {
          message.warning('群聊名称不能为空');
          return Promise.reject();
        }
        const updated = await updateGroupProfile({ name: trimmedName });
        if (!updated) return Promise.reject();
        message.success('群聊名称已更新');
      },
    });
  };

  const handleGroupAvatarChange = (info: any) => {
    const file = info.file.originFileObj || info.file;
    if (!file) return;

    const isJpgOrPng = file.type === 'image/jpeg' || file.type === 'image/png';
    if (!isJpgOrPng) {
      message.error('只能上传 JPG 或 PNG 格式的图片');
      return;
    }

    const isLt2M = file.size / 1024 / 1024 < 2;
    if (!isLt2M) {
      message.error('图片必须小于 2MB');
      return;
    }

    const reader = new FileReader();
    reader.onload = async (event) => {
      const avatar = event.target?.result;
      if (typeof avatar !== 'string') return;
      const updated = await updateGroupProfile({ avatar });
      if (updated) message.success('群头像已更新');
    };
    reader.readAsDataURL(file);
  };

  const openMessageSearch = () => {
    if (!activeConv || activeConv.conversation_id === -1) return;
    router.push({
      pathname: '/message_select',
      query: {
        conversation_id: activeConv.conversation_id,
        type: activeConv.type,
        name: activeConv.name
      }
    });
  };

  const openChatHistorySearch = () => {
    setPrivateActionsOpen(false);
    setGroupDrawerOpen(false);
    openMessageSearch();
  };

  const openAddFriendModal = (id: number, name: string, avatar?: string) => {
    setAddFriendTarget({ id, name, avatar });
    setAddFriendMessage('');
    setIsAddFriendVisible(true);
  };

  const handleSendFriendRequest = async () => {
    if (!addFriendTarget) return;
    const requestedTarget = addFriendTarget;
    const requestedMessage = addFriendMessage;
    const token = localStorage.getItem('token');
    try {
      const res = await fetch('/api/friends/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          to_user_id: requestedTarget.id,
          message: requestedMessage,
          source: 'profile'
        })
      });
      const data = await res.json();
      
      if (data.code === 0) {
        message.success('好友请求已发送，等待对方通过');
        upsertCachedSentRequest(requestedTarget, requestedMessage);
        setIsAddFriendVisible(false);
        setAddFriendMessage('');
      } else if (data.code === 2) {
        message.warning('你们已经是好友啦，无需重复添加');
        setIsAddFriendVisible(false);
      } else if (data.code === 3) {
        message.warning('已发送过请求，请耐心等待对方审核');
        upsertCachedSentRequest(requestedTarget, requestedMessage);
        setIsAddFriendVisible(false);
        setAddFriendMessage('');
      } else {
        message.error(`发送失败: ${data.info}`);
      }
    } catch {
      message.error('网络请求异常');
    }
  };

  const handleGroupAdminAction = async (targetUserId: number, action: 'set_admin' | 'remove_admin' | 'transfer_owner') => {
    if (!activeConv || activeConv.conversation_id === -1) return;
    const token = localStorage.getItem('token');
    
    try {
      const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group/admin`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ user_id: targetUserId, action })
      });
      const data = await res.json();
      
      if (data.code === 0) {
        message.success('权限设置成功');
        fetchGroupInfo(); 
        if (action === 'transfer_owner') fetchConversations(token as string);
      } else {
        message.error(`设置失败: ${data.info}`);
      }
    } catch {
      message.error('网络请求异常');
    }
  };

  const confirmTransferOwner = (targetUserId: number, targetUsername: string) => {
    Modal.confirm({
      title: '转让群主',
      content: `确定要将群主转让给 ${targetUsername} 吗？转让后你将降级为普通成员。`,
      okText: '确认转让',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => handleGroupAdminAction(targetUserId, 'transfer_owner'),
    });
  };


  useEffect(() => {
    const token = localStorage.getItem('token');
    const storedName = localStorage.getItem('username');
    const storedUserId = localStorage.getItem('user_id');

    if (!token) {
      message.warning('请先登录！');
      router.push('/login');
      return;
    }


    const { conversation_id } = router.query;
    if (conversation_id) {
      routerParamHandledRef.current = true;
      const targetConvId = Number(conversation_id);
      const existing = conversations.find(c => c.conversation_id === targetConvId);
      if (existing) {
        handleSelectConv(existing);
      }
      router.replace('/', undefined, { shallow: true });
      return;
    }

    setUserName(storedName ?? undefined);
    if (storedUserId) {
      const parsedId = Number(storedUserId);
      if (!Number.isNaN(parsedId)) setUserId(parsedId);
    }

    // 兜底：登录前的会话或老 token 没存 user_id 时，从后端 profile 拉一次
    // 同时用 profile 接口的返回值覆盖 localStorage 旧值，确保 userId 准确
    fetch('/api/user/profile', { headers: { 'Authorization': `Bearer ${token}` } })
      .then(res => res.json())
      .then(data => {
        if (data && data.code === 0) {
          if (typeof data.user_id === 'number') {
            setUserId(data.user_id);
            localStorage.setItem('user_id', String(data.user_id));
          }
          if (typeof data.username === 'string') {
            setUserName(data.username);
            localStorage.setItem('username', data.username);
          }
          if (typeof data.avatar === 'string') {
            setUserAvatar(data.avatar);
          }
        }
        setUserIdConfirmed(true);
      })
      .catch(() => { setUserIdConfirmed(true); });

    fetchConversations(token);

    const interval = setInterval(() => fetchConversations(token), 5000);
    return () => clearInterval(interval);
  }, [router]);

  const fetchConversations = (token: string) => {
    fetch('/api/conversations', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (data.code === 0) {
          const clearedTimes = readClearedConversationTimes();
          const rawConvs = (data.conversations || []).map((conv: any) => {
            const clearedAt = clearedTimes[String(conv.conversation_id)];
            if (conv.last_message?.created_at && conv.last_message.created_at <= clearedAt) {
              return { ...conv, last_message: undefined };
            }
            return conv;
          });
          const sortedConvs = rawConvs.sort((a: any, b: any) => {
            if (a.is_pinned && !b.is_pinned) return -1;
            if (!a.is_pinned && b.is_pinned) return 1;
            return b.conversation_id - a.conversation_id; 
          });
          setConversations(sortedConvs);
        }
      })
      .catch(() => {})
      .finally(() => {
        setLoading(false);
        setInitialFetched(true);
      });
  };

  useEffect(() => {
    if (!router.isReady || !initialFetched) return;
    if (routerParamHandledRef.current) return;

    const { to_user_id: toUserId, name } = router.query;
    if (!toUserId || !name) return;

    routerParamHandledRef.current = true;

    const targetId = Number(toUserId);
    const targetName = Array.isArray(name) ? name[0] : name;
    // 严格按 target_user_id 匹配私聊（后端在私聊会话上才返回 target_user_id）。
    // 故意不做 name 回退：避免命中同名群聊，把消息群发给跟我无关的陌生人。
    const existing = conversations.find(
      (c: any) => c.type === 'private' && c.target_user_id === targetId
    );

    if (existing) {
      handleSelectConv(existing);
    } else {
      setActiveConv({
        conversation_id: -1,
        name: targetName,
        type: 'private',
        unread_count: 0,
        target_user_id: targetId,
        avatar: ''
      });
      setMessages([]);
    }

    // 处理完后清掉 URL 上的 to_user_id / name，避免轮询导致 conversations 引用变化
    // 时这个 effect 又重新把会话强行拉回到 URL 指定的人。
    router.replace('/', undefined, { shallow: true });
  }, [router.isReady, router.query, initialFetched, conversations, router]);

  useEffect(() => {
    if (!router.isReady || !initialFetched || activeConv || restoredConversationRef.current) return;

    const { conversation_id: conversationId, to_user_id: toUserId, name } = router.query;
    if (conversationId || toUserId || name) return;

    const lastConversationId = readLastConversationId();
    if (!lastConversationId) {
      restoredConversationRef.current = true;
      return;
    }

    const existing = conversations.find((conv: any) => conv.conversation_id === lastConversationId);
    restoredConversationRef.current = true;

    if (existing) {
      handleSelectConv(existing);
    } else {
      clearLastConversationId();
    }
  }, [router.isReady, router.query, initialFetched, conversations, activeConv]);

  
  const handleDeleteMessage = (msgId: number) => {
    if (!activeConv || activeConv.conversation_id === -1) return;

    Modal.confirm({
      title: '确定删除这条消息吗？',
      content: '删除后将无法在当前设备查看此消息。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const token = localStorage.getItem('token');
        try {
          // 假设后端的删除接口为 DELETE /conversations/<conv_id>/messages/<msg_id>
          const res = await fetch(`/api/conversations/${activeConv.conversation_id}/messages/${msgId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          const data = await res.json();
          
          if (data.code === 0) {
            message.success('删除成功');
            fetchMessages(activeConv.conversation_id, true);
          } else {
            message.error(`删除失败: ${data.info}`);
          }
        } catch {
          message.error('网络请求异常，无法删除');
        }
      }
    });
  };

  const fetchMessages = async (convId: number, silent = false) => {
    const token = localStorage.getItem('token');
    if (!silent) setLoadingMsg(true);
    try {
      const res = await fetch(`/api/conversations/${convId}/messages?limit=50`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.code === 0) {
        const msgs = (data.messages || []).reverse();
        setMessages(msgs);
        scrollToBottom();
      }
    } catch {
      if (!silent) message.error('消息同步失败');
    } finally {
      if (!silent) setLoadingMsg(false);
    }
  };

  useEffect(() => {
    if (!activeConv || activeConv.conversation_id === -1) return;

    const updatedConv = conversations.find(c => c.conversation_id === activeConv.conversation_id);
    
    if (updatedConv && updatedConv.unread_count > 0) {
      fetchMessages(activeConv.conversation_id, true);
      
      const token = localStorage.getItem('token');
      fetch(`/api/conversations/${activeConv.conversation_id}/read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ last_read_id: 99999999 })
      }).then(() => fetchConversations(token as string)); 
    }
  }, [conversations, activeConv]);

  const handleSend = async () => {
    if (!inputText.trim() || !activeConv) return;
    
    const content = inputText;
    setInputText('');
    const token = localStorage.getItem('token');
    let currentConvId = activeConv.conversation_id;

    if (currentConvId === -1) {
      try {
        const createRes = await fetch('/api/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ 
            name: activeConv.name, 
            member_ids: [activeConv.target_user_id] 
          })
        });
        const createData = await createRes.json();
        if (createData.code === 0) {
          currentConvId = createData.conversation_id;
          writeLastConversationId(currentConvId);
          setActiveConv((prev: any) => ({ ...prev, conversation_id: currentConvId }));
        } else {
          message.error(`创建会话失败: ${createData.info}`);
          return;
        }
      } catch {
        message.error('网络错误，无法创建会话');
        return;
      }
    }

    try {
      const res = await fetch(`/api/conversations/${currentConvId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ 
          content,
          reply_to_id : replyingTo ? replyingTo.msg_id : undefined 
        })
      });
      const data = await res.json();
      if (data.code === 0) {
        setReplyingTo(undefined);
        fetchMessages(currentConvId);
        fetchConversations(token as string);
      } else if (data.code === 3) {
        message.warning('对方已不是你的好友，无法发送消息');
      } else if (data.code === 4) {
        message.warning('对方账号已注销，无法发送消息');
      } else {
        message.error(`发送失败: ${data.info}`);
      }
    } catch {
      message.error('网络错误');
    }
  };

  // --- 新增：退出群聊逻辑 ---
  const handleLeaveGroup = () => {
    Modal.confirm({
      title: '退出群聊',
      content: '确定要退出该群聊吗？退出后将无法查看群消息。',
      okText: '确认退出',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        if (!activeConv) return;
        const token = localStorage.getItem('token');
        try {
          const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group/leave`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          const data = await res.json();
          if (data.code === 0) {
            message.success('已退出群聊');
            setGroupDrawerOpen(false);
            clearLastConversationId();
            setActiveConv(undefined); // 清空当前聊天窗口
            fetchConversations(token as string); // 刷新左侧列表
          } else if (data.code === 3) {
            message.error('你是群主，请先转让群主身份后再退出！');
          } else {
            message.error(`退出失败: ${data.info}`);
          }
        } catch {
          message.error('网络请求异常');
        }
      }
    });
  };

  // --- 新增：邀请好友逻辑 ---
  const [isInviteVisible, setIsInviteVisible] = useState(false);
  const [inviteFriends, setInviteFriends] = useState<any[]>([]);
  const [selectedFriendId, setSelectedFriendId] = useState<number | undefined>(undefined);

  const openInviteModal = async () => {
    setIsInviteVisible(true);
    const token = localStorage.getItem('token');
    try {
      const res = await fetch('/api/friends', { headers: { 'Authorization': `Bearer ${token}` } });
      const data = await res.json();
      if (data.code === 0 && groupInfo) {
        // 过滤掉已经在群里的好友
        const existingIds = groupInfo.members.map((m: any) => m.user_id);
        const selectable = (data.friends || []).filter((f: any) => !existingIds.includes(f.user_id));
        setInviteFriends(selectable);
      }
    } catch {
      message.error('获取好友列表失败');
    }
  };

  const handleSendInvite = async () => {
    if (!selectedFriendId) return message.warning('请先选择要邀请的好友');
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ user_id: selectedFriendId })
      });
      const data = await res.json();
      if (data.code === 0) {
        message.success('邀请已发送，请等待管理员审核');
        setIsInviteVisible(false);
        setSelectedFriendId(undefined);
      } else {
        message.error(`邀请失败: ${data.info}`);
      }
    } catch {
      message.error('网络请求异常');
    }
  };

  // --- 新增：审核邀请逻辑 ---
  const [isAuditVisible, setIsAuditVisible] = useState(false);
  const [pendingInvites, setPendingInvites] = useState<any[]>([]);

  const fetchPendingInvites = async () => {
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group/invite`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.code === 0) setPendingInvites(data.invitations || []);
    } catch {
      message.error('获取审核列表失败');
    }
  };

  const openAuditModal = () => {
    setIsAuditVisible(true);
    fetchPendingInvites();
  };

  const handleAudit = async (invitationId: number, action: 'accept' | 'reject') => {
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group/invite`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ invitation_id: invitationId, action })
      });
      const data = await res.json();
      if (data.code === 0) {
        message.success(action === 'accept' ? '已同意入群' : '已拒绝邀请');
        fetchPendingInvites(); // 刷新待审核列表
        fetchGroupInfo(); // 刷新群成员列表
      } else {
        message.error(`操作失败: ${data.info}`);
      }
    } catch {
      message.error('网络请求异常');
    }
  };

  const handleSelectConv = async (conv: any) => {
    setActiveConv(conv);
    writeLastConversationId(conv.conversation_id);
    fetchMessages(conv.conversation_id);
    setReplyingTo(undefined); 
    setPrivateActionsOpen(false);
    
    if (conv.unread_count > 0) {
      const token = localStorage.getItem('token');
      fetch(`/api/conversations/${conv.conversation_id}/read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ last_read_id: 99999999 })
      }).then(() => fetchConversations(token as string));
    }
  };

  const openUserProfileCard = async (user: UserProfileCard) => {
    if (user.user_id === userId) return;

    setProfileCardUser(user);
    setProfileCardOpen(true);
    setProfileCardLoading(true);

    const token = localStorage.getItem('token');
    if (!token) {
      setProfileCardLoading(false);
      return;
    }

    try {
      const [detailRes, friendsRes] = await Promise.all([
        fetch(`/api/user/${user.user_id}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch('/api/friends', {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ]);
      const detailData = await detailRes.json();
      const friendsData = await friendsRes.json();
      const detail = detailData.code === 0 ? detailData : {};
      const friends = friendsData.code === 0 && Array.isArray(friendsData.friends)
        ? friendsData.friends
        : [];

      setProfileCardUser({
        user_id: user.user_id,
        username: typeof detail.username === 'string' ? detail.username : user.username,
        avatar: typeof detail.avatar === 'string' ? detail.avatar : user.avatar,
        isFriend: friends.some((friend: any) => friend.user_id === user.user_id),
      });
    } catch {
      message.error('获取用户信息失败');
    } finally {
      setProfileCardLoading(false);
    }
  };

  const handleProfileSendMessage = () => {
    if (!profileCardUser || !profileCardUser.isFriend) return;

    const existing = conversations.find((conv: any) => (
      conv.type === 'private' && conv.target_user_id === profileCardUser.user_id
    ));

    if (existing) {
      handleSelectConv(existing);
    } else {
      setActiveConv({
        conversation_id: -1,
        name: profileCardUser.username,
        type: 'private',
        unread_count: 0,
        target_user_id: profileCardUser.user_id,
        avatar: profileCardUser.avatar || ''
      });
      setMessages([]);
      setReplyingTo(undefined);
    }

    setGroupDrawerOpen(false);
    setProfileCardOpen(false);
  };

  const handleProfileAddFriend = () => {
    if (!profileCardUser) return;
    setProfileCardOpen(false);
    openAddFriendModal(profileCardUser.user_id, profileCardUser.username, profileCardUser.avatar);
  };

  const handleProfileDeleteFriend = () => {
    if (!profileCardUser?.isFriend) return;

    const targetUser = profileCardUser;
    Modal.confirm({
      title: '删除好友',
      content: `确定删除 ${targetUser.username} 吗？删除后你们将不再是好友。`,
      okText: '删除好友',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const token = localStorage.getItem('token');
        if (!token) {
          message.warning('请先登录');
          return;
        }

        try {
          const res = await fetch(`/api/friends/${targetUser.user_id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          const data = await res.json();
          if (data.code === 0) {
            message.success('已删除好友');
            setProfileCardUser(prev => (
              prev?.user_id === targetUser.user_id ? { ...prev, isFriend: false } : prev
            ));
            setConversations(prev => prev.filter((conv) => (
              !(conv.type === 'private' && conv.target_user_id === targetUser.user_id)
            )));
            if (activeConv?.type === 'private' && activeConv.target_user_id === targetUser.user_id) {
              clearLastConversationId();
              setActiveConv(undefined);
              setMessages([]);
            }
            fetchConversations(token);
          } else {
            message.error(`删除好友失败: ${data.info}`);
          }
        } catch {
          message.error('网络请求异常，无法删除好友');
        }
      }
    });
  };

  const toggleConversationSetting = async (settingKey: 'is_pinned' | 'is_muted', nextValue?: boolean) => {
    if (!activeConv || activeConv.conversation_id === -1) {
      message.warning('请先发送一条消息以创建会话');
      return;
    }
    
    const token = localStorage.getItem('token');
    const newValue = typeof nextValue === 'boolean' ? nextValue : !activeConv[settingKey];

    try {
      const res = await fetch(`/api/conversations/${activeConv.conversation_id}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ [settingKey]: newValue })
      });
      const data = await res.json();
      
      if (data.code === 0) {
        message.success(`已${newValue ? '开启' : '关闭'}${settingKey === 'is_pinned' ? '置顶' : '免打扰'}`);
        setActiveConv((prev: any) => ({ ...prev, [settingKey]: newValue }));
        fetchConversations(token as string);
      } else {
        message.error(`设置失败: ${data.info}`);
      }
    } catch {
      message.error('网络请求异常，无法保存设置');
    }
  };

  const handleClearConversationMessages = () => {
    if (!activeConv || activeConv.conversation_id === -1) return;

    const conversationId = activeConv.conversation_id;
    Modal.confirm({
      title: '删除聊天记录',
      content: '确定删除当前会话的聊天记录吗？删除后仅你自己不可见。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const token = localStorage.getItem('token');
        if (!token) {
          message.warning('请先登录');
          return;
        }

        setPrivateActionLoading('clear');
        try {
          let deletedCount = 0;

          for (let page = 0; page < 50; page += 1) {
            const listRes = await fetch(`/api/conversations/${conversationId}/messages?limit=100`, {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            const listData = await listRes.json();
            if (listData.code !== 0) throw new Error(listData.info || '获取聊天记录失败');

            const batch = listData.messages || [];
            if (batch.length === 0) break;

            const deleteResults = await Promise.all(batch.map((item: any) => (
              fetch(`/api/conversations/${conversationId}/messages/${item.msg_id}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
              }).then(res => res.json())
            )));
            const failed = deleteResults.find((result: any) => result.code !== 0);
            if (failed) throw new Error(failed.info || '删除聊天记录失败');

            deletedCount += batch.length;
            if (batch.length < 100) break;
          }

          markConversationCleared(conversationId, Date.now() / 1000);
          setMessages([]);
          setConversations(prev => prev.map((item) => (
            item.conversation_id === conversationId ? { ...item, last_message: undefined } : item
          )));
          setPrivateActionsOpen(false);
          message.success(deletedCount > 0 ? '聊天记录已删除' : '暂无聊天记录');
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除聊天记录失败');
        } finally {
          setPrivateActionLoading(undefined);
        }
      }
    });
  };

  const handleDeleteFriendFromChat = () => {
    if (!activeConv || activeConv.type !== 'private') return;
    const targetUserId = activeConv.target_user_id;
    if (typeof targetUserId !== 'number') {
      message.warning('未找到好友信息');
      return;
    }

    Modal.confirm({
      title: '删除好友',
      content: `确定删除 ${activeConv.name} 吗？删除后你们将不再是好友。`,
      okText: '删除好友',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const token = localStorage.getItem('token');
        if (!token) {
          message.warning('请先登录');
          return;
        }

        setPrivateActionLoading('friend');
        try {
          const res = await fetch(`/api/friends/${targetUserId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          const data = await res.json();
          if (data.code === 0) {
            message.success('已删除好友');
            setPrivateActionsOpen(false);
            setProfileCardUser(prev => (
              prev?.user_id === targetUserId ? { ...prev, isFriend: false } : prev
            ));
            setConversations(prev => prev.filter((conv) => (
              !(conv.type === 'private' && conv.target_user_id === targetUserId)
            )));
            if (activeConv?.type === 'private' && activeConv.target_user_id === targetUserId) {
              clearLastConversationId();
              setActiveConv(undefined);
              setMessages([]);
            }
            fetchConversations(token);
          } else {
            message.error(`删除好友失败: ${data.info}`);
          }
        } catch {
          message.error('网络请求异常，无法删除好友');
        } finally {
          setPrivateActionLoading(undefined);
        }
      }
    });
  };

  const scrollToBottom = () => {
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };


  const handlePublishAnnouncement = async () => {
    if (!announcementText.trim() || !activeConv) return;
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group/announcement`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ content: announcementText })
      });
      const data = await res.json();
      if (data.code === 0) {
        message.success('发布公告成功');
        setIsAnnouncementModalVisible(false);
        setAnnouncementText('');
        fetchGroupInfo(); // 刷新群资料，拉取最新公告
      } else {
        message.error(`发布失败: ${data.info}`);
      }
    } catch {
      message.error('网络请求异常');
    }
  };

  // --- 新增：移出群聊的逻辑 ---
  const handleRemoveMember = (targetUserId: number, targetUsername: string) => {
    Modal.confirm({
      title: '移出群聊',
      content: `确定要将 ${targetUsername} 移出群聊吗？`,
      okText: '确定移除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        if (!activeConv || activeConv.conversation_id === -1) return;
        const token = localStorage.getItem('token');
        try {
          const res = await fetch(`/api/conversations/${activeConv.conversation_id}/group/members`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ user_id: targetUserId })
          });
          const data = await res.json();
          if (data.code === 0) {
            message.success(`已将 ${targetUsername} 移出群聊`);
            fetchGroupInfo(); // 刷新群成员列表
          } else {
            message.error(`移除失败: ${data.info}`);
          }
        } catch {
          message.error('网络请求异常');
        }
      }
    });
  };

  const handleScrollToMessage = (msgId: number) => {
    const element = document.getElementById(`msg-${msgId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      element.style.transition = 'background-color 0.5s';
      element.style.backgroundColor = '#ffffb8';
      setTimeout(() => { element.style.backgroundColor = 'transparent'; }, 1500);
    } else {
      message.warning('原消息已不在可视范围内');
    }
  };

  const handleLogout = () => {
    clearLastConversationId();
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    localStorage.removeItem('user_id');
    message.success('已安全退出登录');
    router.push('/login');
  };

  const userMenu: MenuProps = {
    items: [
      { key: 'profile', label: '个人主页', icon: <UserOutlined />, onClick: () => router.push('/profile') },
      { type: 'divider' },
      { key: 'friends', label: '通讯录', icon: <ContactsOutlined />, onClick: () => router.push('/friends') },
      { key: 'logout', label: '退出登录', icon: <LogoutOutlined />, danger: true, onClick: handleLogout },
    ],
  };

  const quickActionMenu: MenuProps = {
    items: [
      { key: 'add-friend', label: '添加好友', icon: <UserAddOutlined />, onClick: () => router.push('/add_friend') },
      { key: 'start-group', label: '发起群聊', icon: <UsergroupAddOutlined />, onClick: () => router.push('/group_build') },
    ],
  };

  const privateTargetId = typeof activeConv?.target_user_id === 'number'
    ? activeConv.target_user_id
    : undefined;

  const openPrivateProfileCard = () => {
    if (!activeConv || typeof privateTargetId !== 'number') return;
    openUserProfileCard({
      user_id: privateTargetId,
      username: activeConv.name,
      avatar: activeConv.avatar,
      isFriend: true,
    });
  };

  const privateSettingsContent = (
    <div style={styles.privateSettingBody}>
      <div style={styles.privateMemberGrid}>
        <button type="button" style={styles.privateMemberTile} onClick={openPrivateProfileCard}>
          <Avatar
            size={48}
            src={activeConv?.avatar}
            icon={<UserOutlined />}
            style={{ backgroundColor: '#8bc8ff' }}
          />
          <Text ellipsis style={styles.privateMemberName}>{activeConv?.name}</Text>
        </button>
      </div>

      <Divider style={{ margin: '0 0 14px' }} />

      <div style={styles.groupSettingBlock}>
        <button
          type="button"
          onClick={openChatHistorySearch}
          style={{
            ...styles.groupSettingRow,
            width: '100%',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
            textAlign: 'left',
          }}
        >
          <Text style={styles.groupSettingLabel}>查找聊天内容</Text>
          <RightOutlined style={{ color: '#8a95a6' }} />
        </button>
        <div style={{ ...styles.groupSettingRow, ...styles.groupSettingDivider }}>
          <Text style={styles.groupSettingLabel}>消息免打扰</Text>
          <Switch
            size="small"
            checked={Boolean(activeConv?.is_muted)}
            disabled={Boolean(privateActionLoading)}
            onChange={(checked) => toggleConversationSetting('is_muted', checked)}
          />
        </div>
        <div style={{ ...styles.groupSettingRow, ...styles.groupSettingDivider }}>
          <Text style={styles.groupSettingLabel}>置顶聊天</Text>
          <Switch
            size="small"
            checked={Boolean(activeConv?.is_pinned)}
            disabled={Boolean(privateActionLoading)}
            onChange={(checked) => toggleConversationSetting('is_pinned', checked)}
          />
        </div>
      </div>

      <div style={styles.privateActionGroup}>
        <Button
          type="text"
          block
          loading={privateActionLoading === 'clear'}
          disabled={privateActionLoading === 'friend'}
          style={styles.privateClearButton}
          onClick={handleClearConversationMessages}
        >
          清空聊天记录
        </Button>
      </div>

      <div style={{ ...styles.privateActionGroup, ...styles.privateActionGroupLast }}>
        <Button
          type="text"
          danger
          block
          loading={privateActionLoading === 'friend'}
          disabled={privateActionLoading === 'clear'}
          style={styles.privateDangerButton}
          onClick={handleDeleteFriendFromChat}
        >
          删除好友
        </Button>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div style={styles.loadingShell}>
        <Spin size="large" description="系统初始化中..." />
      </div>
    );
  }

  return (
    <Layout style={styles.appShell}>
      <Head><title>聊天 - IM System</title></Head>

      <div style={styles.sidebar}>
        <div style={styles.rail}>
          <Dropdown menu={userMenu} placement="bottomRight" arrow>
            <div title={userName || '账号'} style={styles.accountButton}>
              <Avatar
                size={56}
                src={userAvatar || undefined}
                icon={<UserOutlined />}
                style={{
                  background: 'linear-gradient(135deg, #8ad7ff, #118fff)',
                  objectFit: 'cover',
                }}
              />
            </div>
          </Dropdown>
          <Button type="text" title="消息" icon={<MessageOutlined />} style={{ ...styles.iconButton, background: 'rgba(255, 255, 255, 0.28)', color: '#ffffff' }} />
          <Button type="text" title="通讯录" icon={<ContactsOutlined />} style={styles.iconButton} onClick={() => router.push('/friends')} />
        </div>

        <div style={styles.listPane}>
          <div style={styles.sidebarHeader}>
            <Input prefix={<SearchOutlined />} placeholder="搜索" style={styles.searchInput} />
            <Dropdown menu={quickActionMenu} placement="bottomRight" trigger={['click']} arrow>
              <Button
                type="text"
                icon={<PlusOutlined style={{ fontSize: 18 }} />}
                title="新建"
                style={styles.createButton}
              />
            </Dropdown>
          </div>
          <div style={styles.listWrap}>
            <List
              itemLayout="horizontal"
              dataSource={conversations}
              locale={{
                emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无会话" />,
              }}
              renderItem={(item) => {
                const isActive = activeConv?.conversation_id === item.conversation_id;
                return (
                  <List.Item
                    style={{
                      ...styles.conversationItem,
                      ...(isActive ? styles.conversationActive : undefined),
                    }}
                    onClick={() => handleSelectConv(item)}
                  >
                    <List.Item.Meta
                      avatar={
                        // [修改]：免打扰时，气泡变成浅灰色
                        <Badge 
                          count={item.unread_count} 
                          overflowCount={99} 
                          size="small"
                          color={item.is_muted ? '#bfbfbf' : undefined}
                        >
                          <Avatar
                            size={44}
                            src={item.avatar}
                            icon={item.type === 'group' ? <TeamOutlined /> : <UserOutlined />}
                            style={{ backgroundColor: item.type === 'group' ? '#b99cff' : '#8bc8ff' }}
                          />
                        </Badge>
                      }
                      title={
                        <div style={styles.conversationTitleRow}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
                            {/* [新增]：置顶图钉图标 */}
                            {item.is_pinned && <PushpinOutlined style={{ color: '#8492a6', fontSize: 13, transform: 'rotate(-45deg)' }} />}
                            <Text ellipsis style={styles.conversationName}>{item.name}</Text>
                          </div>
                          <Text style={styles.conversationTime}>
                            {formatChatTime(item.last_message?.created_at || item.updated_at)}
                          </Text>
                        </div>
                      }
                      description={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                           {/* [新增]：免打扰状态的小喇叭 */}
                           {item.is_muted && <AudioMutedOutlined style={{ color: '#b5c0d0', fontSize: 12 }} />}
                           <Text type="secondary" ellipsis style={styles.conversationPreview}>
                             {item.last_message?.content || '暂无消息'}
                           </Text>
                        </div>
                      }
                    />
                  </List.Item>
                );
              }}
            />
          </div>
        </div>
      </div>

      <Content style={styles.chatPane}>
          {activeConv ? (
            <>
              <div style={styles.chatHeader}>
                <div style={styles.chatTitleWrap}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Text ellipsis style={styles.chatTitle}>{activeConv.name}</Text>
                    {/* [新增]：标题旁的静音提示 */}
                    {activeConv.is_muted && <AudioMutedOutlined style={{ color: '#b5c0d0' }} title="消息免打扰" />}
                  </div>
                  <Text style={styles.chatMeta}>{activeConv.type === 'group' ? '群聊' : '私聊'}</Text>
                  
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {activeConv.conversation_id !== -1 && (
                    <Button 
                      type="text" 
                      icon={<MessageOutlined style={{ fontSize: 18, color: '#5b6b82' }} />}
                      onClick={openChatHistorySearch}
                      title="查找聊天记录"
                    />
                  )}

                  {activeConv.conversation_id !== -1 && activeConv.type === 'private' && (
                    <Button
                      type="text"
                      icon={<MoreOutlined style={{ fontSize: 20, color: '#5b6b82' }} />}
                      onClick={() => setPrivateActionsOpen(true)}
                      title="聊天设置"
                    />
                  )}

                  {activeConv.conversation_id !== -1 && activeConv.type === 'group' && (
                    <Button
                      type="text"
                      icon={<MoreOutlined style={{ fontSize: 20, color: '#5b6b82' }} />}
                      onClick={handleOpenGroupInfo}
                      title="群聊设置"
                    />
                  )}
                </div>
              </div>

              <div style={styles.messageArea}>
                <Spin spinning={loadingMsg || !userIdConfirmed}>
                  {userIdConfirmed && messages.length === 0 && !loadingMsg ? (
                    <div style={styles.messagesEmpty}>
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无聊天记录" />
                    </div>
                  ) : userIdConfirmed && messages.map((msg: any) => {
                    // 用稳定的数字 user_id 判定，避免 sender_name 与 localStorage.username
                    // 不一致（改名、跨标签、未存 user_id 等）造成左右气泡错位。
                    // userIdConfirmed 确保 userId 已从后端 profile 接口确认，不使用 localStorage 旧值。
                    const isMe = typeof userId === 'number'
                      ? msg.sender_id === userId
                      : msg.sender_name === userName;
                    
                    const messageMenu: MenuProps = {
                      items: [
                        { key: 'reply', label: '回复', onClick: () => setReplyingTo(msg) },
                        { type: 'divider' },
                        { 
                          key: 'delete', 
                          label: '删除', 
                          icon: <DeleteOutlined />, 
                          danger: true,
                          onClick: () => handleDeleteMessage(msg.msg_id) 
                        },
                      ],
                    };
                    const openSenderProfile = () => openUserProfileCard({
                      user_id: msg.sender_id,
                      username: msg.sender_name,
                      avatar: msg.sender_avatar,
                    });

                    return (
                      <div
                        id={`msg-${msg.msg_id}`}
                        key={msg.msg_id}
                        style={{
                          ...styles.messageRow,
                          justifyContent: isMe ? 'flex-end' : 'flex-start',
                        }}
                      >
                        {!isMe && (
                          <button
                            type="button"
                            onClick={openSenderProfile}
                            style={{ padding: 0, border: 'none', background: 'transparent', cursor: 'pointer', borderRadius: '50%' }}
                          >
                            <Avatar
                              size={36}
                              src={msg.sender_avatar}
                              icon={<UserOutlined />}
                              style={{ ...styles.messageAvatar, backgroundColor: '#8bc8ff' }}
                            />
                          </button>
                        )}
                        
                        <div
                          style={{
                            ...styles.messageStack,
                            alignItems: isMe ? 'flex-end' : 'flex-start',
                          }}
                        >
                          <Text style={styles.messageMeta}>
                            {isMe
                              ? new Date(msg.created_at * 1000).toLocaleString()
                              : `${msg.sender_name} · ${new Date(msg.created_at * 1000).toLocaleString()}`}
                          </Text>
                          
                          <Dropdown menu={messageMenu} trigger={['contextMenu']} placement={isMe ? "bottomRight" : "bottomLeft"}>
                            <div
                              style={{
                                ...styles.bubble,
                                ...(isMe ? styles.myBubble : styles.otherBubble),
                              }}
                            >
                              <div>{msg.content}</div>

                              {msg.reply_to && (
                                <div 
                                  role="button"
                                  tabIndex={0}
                                  onClick={(e) => {
                                    e.stopPropagation(); 
                                    handleScrollToMessage(msg.reply_to.msg_id);
                                  }}
                                  style={{
                                    ...styles.quoteBlock,
                                    ...(isMe ? styles.myQuote : styles.otherQuote),
                                  }}
                                >
                                  <span style={{ 
                                    display: 'block', // 确保省略号生效
                                    whiteSpace: 'nowrap', 
                                    overflow: 'hidden', 
                                    textOverflow: 'ellipsis', 
                                    maxWidth: '220px',
                                    opacity: 0.85
                                  }}>
                                    <span style={{ fontWeight: 600 }}>{msg.reply_to.sender_name}</span>：{msg.reply_to.content}
                                  </span>
                                </div>
                              )}
                            </div>
                          </Dropdown>

                          {/* --- [新增/修复] 在气泡下方渲染被回复的计数 --- */}
                          {msg.reply_count > 0 && (
                            <div style={{ marginTop: 4, width: '100%', textAlign: isMe ? 'right' : 'left' }}>
                              <Text style={styles.replyCount}>
                                被回复 {msg.reply_count} 次
                              </Text>
                            </div>
                          )}

                          
                        </div>
                        {isMe && (
                          <Avatar
                            size={36}
                            src={msg.sender_avatar}
                            icon={<UserOutlined />}
                            style={{ ...styles.messageAvatar, backgroundColor: '#8bc8ff' }}
                          />
                        )}
                      </div>
                    );
                  })}
                  <div ref={messagesEndRef} />
                </Spin>
              </div>

              <div style={styles.composer}>
                {replyingTo && (
                  <div style={styles.replyBar}>
                    <Text type="secondary" ellipsis style={{ maxWidth: '90%', fontSize: 12 }}>
                      正在回复 {replyingTo.sender_name}: {replyingTo.content}
                    </Text>
                    <CloseOutlined
                      title="取消回复"
                      onClick={() => setReplyingTo(undefined)}
                      style={{ cursor: 'pointer', color: '#7a7a7a' }}
                    />
                  </div>
                )}

                <div style={styles.composerBody}>
                  <Input.TextArea
                    value={inputText}
                    onChange={e => setInputText(e.target.value)}
                    placeholder="输入消息..."
                    style={styles.textArea}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    onPressEnter={e => {
                      if (!e.shiftKey) { e.preventDefault(); handleSend(); }
                    }}
                  />
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    style={styles.sendButton}
                    disabled={!inputText.trim()}
                    onClick={handleSend}
                  >
                    发送
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div style={styles.emptyState}>
              <MessageOutlined style={{ fontSize: 72, color: '#b7d7f7' }} />
            </div>
          )}
      <Drawer
        title="聊天信息"
        placement="right"
        width={320}
        onClose={() => setPrivateActionsOpen(false)}
        open={privateActionsOpen && activeConv?.type === 'private'}
        styles={{ body: { padding: 0 } }}
      >
        {privateSettingsContent}
      </Drawer>
      <Drawer
        title="群聊信息"
        placement="right"
        width={340}
        onClose={() => setGroupDrawerOpen(false)}
        open={groupDrawerOpen}
        styles={{ body: { padding: 0 } }}
      >
        <Spin spinning={loadingGroupInfo}>
          {groupInfo && (() => {
            // [核心]：计算我自己在群里的角色
            const myRole = groupInfo.members.find((m: any) => m.user_id === userId)?.role || 'member';
            const canEditGroupInfo = myRole === 'owner' || myRole === 'admin';

            return (
            <div style={{ padding: 20 }}>
              <div style={{ textAlign: 'center', marginBottom: 24 }}>
                <Upload
                  showUploadList={false}
                  beforeUpload={() => false}
                  disabled={!canEditGroupInfo}
                  onChange={handleGroupAvatarChange}
                >
                  <span
                    style={{
                      ...styles.groupAvatarButton,
                      cursor: canEditGroupInfo ? 'pointer' : 'default',
                      marginBottom: 12,
                    }}
                  >
                    <Avatar
                      size={64}
                      src={groupInfo.avatar || activeConv?.avatar}
                      icon={<TeamOutlined />}
                      style={{ backgroundColor: '#b99cff' }}
                    />
                    {canEditGroupInfo && (
                      <span style={styles.groupAvatarEdit}>
                        <EditOutlined style={{ fontSize: 13 }} />
                      </span>
                    )}
                  </span>
                </Upload>
                <Title level={4} style={{ margin: 0 }}>{groupInfo.name}</Title>
                <Text type="secondary">创建于 {new Date(groupInfo.created_at * 1000).toLocaleDateString()}</Text>
              </div>

              <Divider />

              <div style={styles.groupSettingBlock}>
                <button
                  type="button"
                  onClick={canEditGroupInfo ? handleEditGroupName : undefined}
                  style={{
                    ...styles.groupSettingRow,
                    width: '100%',
                    border: 'none',
                    background: 'transparent',
                    cursor: canEditGroupInfo ? 'pointer' : 'default',
                    textAlign: 'left',
                  }}
                >
                  <Text style={styles.groupSettingLabel}>群聊名称</Text>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <Text ellipsis style={styles.groupSettingValue}>{groupInfo.name}</Text>
                    {canEditGroupInfo && <RightOutlined style={{ color: '#8a95a6' }} />}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={openChatHistorySearch}
                  style={{
                    ...styles.groupSettingRow,
                    ...styles.groupSettingDivider,
                    width: '100%',
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  <Text style={styles.groupSettingLabel}>查找聊天内容</Text>
                  <SearchOutlined style={{ color: '#8a95a6' }} />
                </button>
                <div style={{ ...styles.groupSettingRow, ...styles.groupSettingDivider }}>
                  <Text style={styles.groupSettingLabel}>设为置顶</Text>
                  <Switch
                    size="small"
                    checked={Boolean(activeConv?.is_pinned)}
                    onChange={(checked) => toggleConversationSetting('is_pinned', checked)}
                  />
                </div>
                <div style={{ ...styles.groupSettingRow, ...styles.groupSettingDivider }}>
                  <Text style={styles.groupSettingLabel}>消息免打扰</Text>
                  <Switch
                    size="small"
                    checked={Boolean(activeConv?.is_muted)}
                    onChange={(checked) => toggleConversationSetting('is_muted', checked)}
                  />
                </div>
              </div>

              <div style={{ marginBottom: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <Text strong>群成员 ({groupInfo.members.length})</Text>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {canEditGroupInfo && (
                      <Button type="link" size="small" style={{ padding: 0 }} onClick={openAuditModal}>审核邀请</Button>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                  {groupInfo.members.map((m: any) => {
                    const isMe = m.user_id === userId;
                    const canManageGroup = myRole === 'owner' || myRole === 'admin';
                    const menuItems: MenuProps['items'] = [];
                    const openMemberProfile = () => {
                      openUserProfileCard({
                        user_id: m.user_id,
                        username: m.username,
                        avatar: m.avatar,
                      });
                    };

                    if (canManageGroup && !isMe) {
                      menuItems.push({
                        key: 'profile',
                        label: '查看资料',
                        icon: <UserOutlined />,
                        onClick: openMemberProfile,
                      });
                    }

                    if (myRole === 'owner' && !isMe) {
                      menuItems.push({ type: 'divider' });
                      if (m.role === 'admin') {
                        menuItems.push({ key: 'remove_admin', label: '取消管理员', onClick: () => handleGroupAdminAction(m.user_id, 'remove_admin') });
                      } else {
                        menuItems.push({ key: 'set_admin', label: '设为管理员', onClick: () => handleGroupAdminAction(m.user_id, 'set_admin') });
                      }
                      menuItems.push({ key: 'transfer', label: '转让群主', danger: true, onClick: () => confirmTransferOwner(m.user_id, m.username) });
                    }

                    if (!isMe) {
                      const canKick = (myRole === 'owner') || (myRole === 'admin' && m.role === 'member');
                      if (canKick) {
                        if (menuItems.length > 0) menuItems.push({ type: 'divider' });
                        menuItems.push({ key: 'kick', label: '移出群聊', danger: true, onClick: () => handleRemoveMember(m.user_id, m.username) });
                      }
                    }

                    const badgeText = m.role === 'owner' ? '群主' : (m.role === 'admin' ? '管理员' : 0);
                    const badgeColor = m.role === 'owner' ? '#ff4d4f' : '#faad14';
                    const shouldOpenProfile = !isMe && menuItems.length === 0;

                    const memberNode = (
                      <div 
                        key={m.user_id} 
                        style={{ 
                          display: 'flex', flexDirection: 'column', alignItems: 'center', width: 48,
                          cursor: !isMe || menuItems.length > 0 ? 'pointer' : 'default'
                        }}
                      >
                        <div
                          role={!isMe ? 'button' : undefined}
                          tabIndex={!isMe ? 0 : undefined}
                          onClick={shouldOpenProfile ? openMemberProfile : undefined}
                          onKeyDown={!isMe ? (event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              if (shouldOpenProfile) openMemberProfile();
                            }
                          } : undefined}
                        >
                          <Badge count={badgeText} style={{ backgroundColor: badgeColor, transform: 'scale(0.7)' }}>
                            <Avatar src={m.avatar} icon={<UserOutlined />} />
                          </Badge>
                        </div>
                        <Text ellipsis style={{ fontSize: 11, width: '100%', textAlign: 'center', marginTop: 4 }}>
                          {m.username}
                        </Text>
                      </div>
                    );

                    if (menuItems.length > 0) {
                      return (
                        <Dropdown key={m.user_id} menu={{ items: menuItems }} trigger={['click']}>
                          {memberNode}
                        </Dropdown>
                      );
                    }
                    return memberNode;
                  })}
                  <button type="button" style={styles.groupMemberTile} onClick={openInviteModal}>
                    <span style={styles.groupInvitePlus}>
                      <PlusOutlined />
                    </span>
                    <Text ellipsis style={{ fontSize: 11, width: '100%', textAlign: 'center' }}>
                      添加
                    </Text>
                  </button>
                </div>
              </div>

              <Divider />

              <div>
                {/* [修改]：公告头部增加发布按钮 */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <Text strong>历史群公告</Text>
                  {(myRole === 'owner' || myRole === 'admin') && (
                    <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setIsAnnouncementModalVisible(true)}>
                      发布公告
                    </Button>
                  )}
                </div>
                
                {groupInfo.announcements.length === 0 ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无公告" />
                ) : (
                  <List
                    size="small"
                    dataSource={groupInfo.announcements}
                    renderItem={(item: any) => (
                      <List.Item>
                        <List.Item.Meta
                          avatar={<SoundOutlined style={{ color: '#faad14' }} />}
                          title={<Text style={{ fontSize: 13 }}>{item.content}</Text>}
                          description={`${item.publisher_name} · ${new Date(item.created_at * 1000).toLocaleString()}`}
                        />
                      </List.Item>
                    )}
                  />
                )}
              </div>

              <Divider />
              <Button danger block size="large" onClick={handleLeaveGroup} style={{ borderRadius: 8 }}>
                退出群聊
              </Button>
            </div>
            );
          })()}
        </Spin>
      </Drawer>
      <Modal
        title="发布群公告"
        open={isAnnouncementModalVisible}
        onOk={handlePublishAnnouncement}
        onCancel={() => {
          setIsAnnouncementModalVisible(false);
          setAnnouncementText('');
        }}
        okText="发布"
        cancelText="取消"
        destroyOnClose
      >
        <div style={{ marginTop: 16 }}>
          <Input.TextArea
            rows={4}
            placeholder="请输入公告内容，所有人可见..."
            value={announcementText}
            onChange={(e) => setAnnouncementText(e.target.value)}
            maxLength={300}
            showCount
          />
        </div>
      </Modal>
      <Modal
        open={profileCardOpen}
        onCancel={() => setProfileCardOpen(false)}
        footer={false}
        width={360}
        destroyOnClose
      >
        <Spin spinning={profileCardLoading}>
          {profileCardUser && (
            <div style={styles.profileCard}>
              <div style={styles.profileHeader}>
                <Avatar
                  size={64}
                  src={profileCardUser.avatar}
                  icon={<UserOutlined />}
                  style={styles.profileAvatar}
                />
                <div style={{ minWidth: 0 }}>
                  <Text ellipsis style={styles.profileName}>{profileCardUser.username}</Text>
                  <Text style={styles.profileMeta}>ID: {profileCardUser.user_id}</Text>
                </div>
              </div>

              <div style={styles.profileInfoRow}>
                <Text style={styles.profileInfoLabel}>用户名</Text>
                <Text ellipsis style={styles.profileInfoValue}>{profileCardUser.username}</Text>
              </div>
              <div style={styles.profileInfoRow}>
                <Text style={styles.profileInfoLabel}>关系</Text>
                <Text style={styles.profileInfoValue}>
                  {profileCardUser.isFriend ? '已添加到通讯录' : '未添加到通讯录'}
                </Text>
              </div>

              <div style={styles.profileActionBar}>
                {profileCardUser.isFriend ? (
                  <>
                    <Button
                      type="primary"
                      block
                      icon={<MessageOutlined />}
                      onClick={handleProfileSendMessage}
                      disabled={profileCardLoading}
                      style={styles.profilePrimaryButton}
                    >
                      发消息
                    </Button>
                    <Button
                      danger
                      block
                      icon={<DeleteOutlined />}
                      onClick={handleProfileDeleteFriend}
                      disabled={profileCardLoading}
                      style={styles.profileDangerButton}
                    >
                      删除好友
                    </Button>
                  </>
                ) : (
                  <Button
                    block
                    icon={<UserAddOutlined />}
                    onClick={handleProfileAddFriend}
                    disabled={profileCardLoading}
                    style={styles.profileSecondaryButton}
                  >
                    添加到通讯录
                  </Button>
                )}
              </div>
            </div>
          )}
        </Spin>
      </Modal>
      {/* 邀请好友弹窗 */}
      <Modal
        title="邀请好友加入群聊"
        open={isInviteVisible}
        onOk={handleSendInvite}
        onCancel={() => { setIsInviteVisible(false); setSelectedFriendId(undefined); }}
        okText="发送邀请"
        cancelText="取消"
        destroyOnClose
      >
        <div style={{ padding: '20px 0' }}>
          <Select
            showSearch
            placeholder="请选择要邀请的好友"
            style={{ width: '100%' }}
            value={selectedFriendId}
            onChange={(val) => setSelectedFriendId(val)}
            options={inviteFriends.map(f => ({ value: f.user_id, label: `${f.username} (${f.group || '默认分组'})` }))}
            optionFilterProp="label"
            notFoundContent="没有可邀请的好友"
          />
        </div>
      </Modal>
      
      {/* 通过群聊添加好友的弹窗 */}
      <Modal
        title={`添加 ${addFriendTarget?.name} 为好友`}
        open={isAddFriendVisible}
        onOk={handleSendFriendRequest}
        onCancel={() => {
          setIsAddFriendVisible(false);
          setAddFriendMessage('');
        }}
        okText="发送请求"
        cancelText="取消"
        destroyOnClose
      >
        <div style={{ padding: '10px 0' }}>
          <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>发送验证申请：</Text>
          <Input.TextArea
            rows={3}
            value={addFriendMessage}
            onChange={(e) => setAddFriendMessage(e.target.value)}
            placeholder="请输入验证信息..."
            maxLength={50}
            showCount
          />
        </div>
      </Modal>

      {/* 审核邀请弹窗 */}
      <Modal
        title="入群邀请审核"
        open={isAuditVisible}
        onCancel={() => setIsAuditVisible(false)}
        footer={undefined}
        destroyOnClose
        bodyStyle={{ maxHeight: 400, overflowY: 'auto', padding: '10px 0' }}
      >
        <List
          dataSource={pendingInvites}
          locale={{ emptyText: '暂无待审核的邀请' }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button key="accept" type="primary" size="small" onClick={() => handleAudit(item.invitation_id, 'accept')}>同意</Button>,
                <Button key="reject" danger size="small" onClick={() => handleAudit(item.invitation_id, 'reject')}>拒绝</Button>
              ]}
            >
              <List.Item.Meta
                avatar={<Avatar icon={<UserOutlined />} style={{ backgroundColor: '#8bc8ff' }} />}
                title={<Text strong>{item.invitee.username}</Text>}
                description={
                  <>
                    <Text type="secondary" style={{ fontSize: 12 }}>由 {item.inviter.username} 邀请</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>{new Date(item.created_at * 1000).toLocaleString()}</Text>
                  </>
                }
              />
            </List.Item>
          )}
        />
      </Modal>
      </Content>
    </Layout>
  );
}
