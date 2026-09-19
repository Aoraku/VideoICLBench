import {nativeFetch as fetch} from '../benchmark/bridge';
import React, { useEffect, useState } from 'react';
import { Avatar, Button, Empty, Input, Layout, message, Modal, Spin, Tag, Typography } from 'antd';
import { ArrowLeftOutlined, CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined, SearchOutlined, UserAddOutlined, UserOutlined } from '@ant-design/icons';
import Head from 'next/head';
import { useRouter } from 'next/router';

const { Header, Content } = Layout;
const { Text, Title } = Typography;

interface SearchUser {
  user_id: number;
  username: string;
  avatar?: string;
}

interface SentRequest {
  request_id: number;
  to_user: SearchUser;
  message?: string;
  status?: string;
  created_at?: number;
}

const getSentRequestsStorageKey = () => {
  if (typeof window === 'undefined') return 'im_sent_friend_requests:server';
  const userKey = localStorage.getItem('user_id') || localStorage.getItem('username') || 'current';
  return `im_sent_friend_requests:${userKey}`;
};

const getSentRequestTime = (request: SentRequest) => request.created_at || 0;

const normalizeSentRequests = (requests: SentRequest[]) => {
  const byUserId = new Map<number, SentRequest>();
  requests.forEach((item) => {
    const userId = item.to_user?.user_id;
    if (!userId) return;
    const current = byUserId.get(userId);
    const isRemoteFinalStatus = (item.status === 'accepted' || item.status === 'rejected') && item.request_id > 0;
    const isCurrentCachedPending = current?.status === 'pending' && current.request_id < 0;
    if (!current || getSentRequestTime(item) >= getSentRequestTime(current) || (isRemoteFinalStatus && isCurrentCachedPending)) {
      byUserId.set(userId, item);
    }
  });
  return Array.from(byUserId.values()).sort((a, b) => getSentRequestTime(b) - getSentRequestTime(a));
};

const readCachedSentRequests = (): SentRequest[] => {
  if (typeof window === 'undefined') return [];
  try {
    const cached = localStorage.getItem(getSentRequestsStorageKey());
    const parsed = cached ? JSON.parse(cached) : [];
    return Array.isArray(parsed) ? normalizeSentRequests(parsed) : [];
  } catch {
    return [];
  }
};

const writeCachedSentRequests = (requests: SentRequest[]) => {
  if (typeof window === 'undefined') return;
  localStorage.setItem(getSentRequestsStorageKey(), JSON.stringify(normalizeSentRequests(requests)));
};

const mergeSentRequests = (...requestGroups: SentRequest[][]) => normalizeSentRequests(requestGroups.flat());

const markAcceptedSentRequests = (requests: SentRequest[], friends: SearchUser[]) => {
  const friendIds = new Set(friends.map((friend) => friend.user_id));
  return normalizeSentRequests(requests.map((item) => (
    item.to_user?.user_id && friendIds.has(item.to_user.user_id)
      ? { ...item, status: 'accepted' }
      : item
  )));
};

const getSentRequestStatusMeta = (status?: string) => {
  if (status === 'accepted') {
    return { color: 'success', icon: <CheckCircleOutlined />, text: '已通过' };
  }
  if (status === 'rejected') {
    return { color: 'error', icon: <CloseCircleOutlined />, text: '已拒绝' };
  }
  return { color: 'processing', icon: <ClockCircleOutlined />, text: '待通过' };
};

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: 'linear-gradient(135deg, #f6fbff 0%, #edf6ff 48%, #ddf1ff 100%)',
  },
  header: {
    height: 72,
    padding: '0 28px',
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    background: 'rgba(255, 255, 255, 0.82)',
    borderBottom: '1px solid #dbe8f8',
    backdropFilter: 'blur(12px)',
  },
  backButton: {
    borderRadius: 14,
    color: '#2377c7',
  },
  content: {
    padding: 28,
    display: 'flex',
    justifyContent: 'center',
  },
  shell: {
    width: 'min(960px, 94vw)',
    minHeight: 620,
    display: 'grid',
    gridTemplateColumns: '300px 1fr',
    overflow: 'hidden',
    borderRadius: 28,
    background: 'rgba(255, 255, 255, 0.86)',
    border: '1px solid rgba(255, 255, 255, 0.88)',
    boxShadow: '0 28px 70px rgba(41, 124, 204, 0.14)',
  },
  side: {
    padding: 30,
    color: '#ffffff',
    background: 'linear-gradient(180deg, #17afff 0%, #078cf0 100%)',
  },
  sideIcon: {
    width: 72,
    height: 72,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 20,
    background: 'rgba(255, 255, 255, 0.18)',
    boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.24)',
  },
  sideTitle: {
    margin: '24px 0 8px',
    color: '#ffffff',
    letterSpacing: 0,
  },
  sideText: {
    color: 'rgba(255, 255, 255, 0.82)',
    lineHeight: 1.7,
  },
  sideCard: {
    marginTop: 34,
    padding: 16,
    borderRadius: 18,
    background: 'rgba(255, 255, 255, 0.16)',
  },
  main: {
    padding: 30,
    background: '#ffffff',
  },
  searchPanel: {
    padding: 18,
    borderRadius: 18,
    background: '#f6fbff',
    border: '1px solid #e1eefb',
  },
  searchRow: {
    display: 'flex',
    gap: 12,
  },
  input: {
    height: 44,
    borderRadius: 14,
    background: '#ffffff',
  },
  primaryButton: {
    height: 44,
    borderRadius: 14,
    fontWeight: 600,
    background: 'linear-gradient(135deg, #22b7ff, #0a8cff)',
    border: 'none',
    boxShadow: '0 10px 22px rgba(10, 140, 255, 0.18)',
  },
  resultHeader: {
    margin: '24px 0 12px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  resultList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  listItem: {
    padding: '16px 14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
    borderRadius: 18,
    background: '#f7fbff',
  },
  userMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    minWidth: 0,
  },
  emptyResult: {
    padding: '46px 0',
    borderRadius: 18,
    background: '#f7fbff',
  },
  avatar: {
    background: 'linear-gradient(135deg, #9bd7ff, #4aa9ff)',
  },
  actionButton: {
    borderRadius: 12,
  },
  modalHint: {
    marginBottom: 10,
    color: '#5b6b82',
  },
};

export default function AddFriendPage() {
  const router = useRouter();
  const [keyword, setKeyword] = useState('');
  const [results, setResults] = useState<SearchUser[]>([]);
  const [searched, setSearched] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [targetUser, setTargetUser] = useState<SearchUser | undefined>(undefined);
  const [requestMsg, setRequestMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [sentRequests, setSentRequests] = useState<SentRequest[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      message.warning('请先登录');
      router.push('/login');
      return;
    }
    const cached = readCachedSentRequests();
    if (cached.length > 0) setSentRequests(cached);
    fetchSentRequests();
    const interval = setInterval(fetchSentRequests, 5000);
    return () => clearInterval(interval);
  }, [router]);

  const fetchSentRequests = async () => {
    setRequestsLoading(true);
    const token = localStorage.getItem('token');
    try {
      const [requestsResponse, friendsResponse] = await Promise.all([
        fetch('/api/friends/request', {
          headers: { 'Authorization': `Bearer ${token}` },
        }),
        fetch('/api/friends', {
          headers: { 'Authorization': `Bearer ${token}` },
        }),
      ]);
      const requestsData = await requestsResponse.json();
      const friendsData = await friendsResponse.json();
      const cached = readCachedSentRequests();
      const remote = requestsData.code === 0 && Array.isArray(requestsData.sent_requests)
        ? requestsData.sent_requests
        : [];
      const friends = friendsData.code === 0 && Array.isArray(friendsData.friends)
        ? friendsData.friends
        : [];
      const next = markAcceptedSentRequests(mergeSentRequests(cached, remote), friends);
      setSentRequests(next);
      writeCachedSentRequests(next);
    } catch {
      message.error('获取已发送申请失败');
    } finally {
      setRequestsLoading(false);
    }
  };

  const upsertSentRequest = (user: SearchUser, messageText: string) => {
    const now = Math.floor(Date.now() / 1000);
    setSentRequests(prev => {
      const exists = prev.some(item => item.to_user?.user_id === user.user_id);
      if (exists) {
        const next = prev.map(item => (
          item.to_user?.user_id === user.user_id
            ? {
              ...item,
              request_id: -now,
              to_user: user,
              message: messageText,
              status: 'pending',
              created_at: now,
            }
            : item
        ));
        const normalized = normalizeSentRequests(next);
        writeCachedSentRequests(normalized);
        return normalized;
      }
      const next = [{
        request_id: -now,
        to_user: user,
        message: messageText,
        status: 'pending',
        created_at: now,
      }, ...prev];
      const normalized = normalizeSentRequests(next);
      writeCachedSentRequests(normalized);
      return normalized;
    });
  };

  const handleSearch = async () => {
    const searchText = keyword.trim();
    if (!searchText) {
      message.info('请输入用户名');
      return;
    }

    setSearchLoading(true);
    setSearched(true);
    const token = localStorage.getItem('token');
    try {
      const response = await fetch(`/api/user/search?keyword=${encodeURIComponent(searchText)}&page=1&page_size=20`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const data = await response.json();
      if (data.code === 0) {
        setResults(data.users || []);
        if ((data.users || []).length === 0) message.info('未找到相关用户');
      } else {
        message.error(data.info || '搜索失败');
      }
    } catch {
      message.error('网络错误');
    } finally {
      setSearchLoading(false);
    }
  };

  const handleSendRequest = async () => {
    if (!targetUser) return;
    const requestedUser = targetUser;
    const requestedMessage = requestMsg;
    setSending(true);
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          to_user_id: targetUser.user_id,
          message: requestMsg,
          source: 'search',
        }),
      });
      const data = await response.json();
      if (data.code === 0) {
        message.success('好友请求已发送');
        upsertSentRequest(requestedUser, requestedMessage);
        setTargetUser(undefined);
        setRequestMsg('');
        fetchSentRequests();
      } else if (data.code === 2) {
        message.warning('你们已经是好友啦');
        setTargetUser(undefined);
      } else if (data.code === 3) {
        message.warning('已发送过请求，请等待对方处理');
        upsertSentRequest(requestedUser, requestedMessage);
        setTargetUser(undefined);
        fetchSentRequests();
      } else {
        message.error(`发送失败: ${data.info}`);
      }
    } catch {
      message.error('网络错误');
    } finally {
      setSending(false);
    }
  };

  const pendingSentRequests = sentRequests.filter((item) => item.status === 'pending');

  return (
    <Layout style={styles.page}>
      <Head><title>添加好友 - IM System</title></Head>

      <Header style={styles.header}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => router.back()} style={styles.backButton}>
          返回
        </Button>
        <Title level={4} style={{ margin: 0, color: '#172033' }}>添加好友</Title>
      </Header>

      <Content style={styles.content}>
        <div style={styles.shell}>
          <aside style={styles.side}>
            <div style={styles.sideIcon}>
              <UserAddOutlined style={{ fontSize: 34, color: '#ffffff' }} />
            </div>
            <Title level={2} style={styles.sideTitle}>New Friend</Title>
            <Text style={styles.sideText}>
              通过用户名查找用户，发送验证申请，等待对方通过后即可开始聊天。
            </Text>
            <div style={styles.sideCard}>
              <Text style={{ color: '#ffffff', fontWeight: 600 }}>验证申请</Text>
              <Text style={{ ...styles.sideText, display: 'block', marginTop: 8 }}>
                申请信息会展示给对方，建议写清楚你的身份或来源。
              </Text>
            </div>
          </aside>

          <main style={styles.main}>
            <div style={styles.searchPanel}>
              <Text strong style={{ color: '#172033' }}>搜索用户</Text>
              <div style={styles.searchRow}>
                <Input
                  prefix={<SearchOutlined />}
                  placeholder="请输入用户名"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  onPressEnter={handleSearch}
                  style={styles.input}
                />
                <Button type="primary" onClick={handleSearch} loading={searchLoading} style={styles.primaryButton}>
                  搜索
                </Button>
              </div>
            </div>

            <div style={styles.resultHeader}>
              <Text strong>搜索结果</Text>
              {searched && <Text type="secondary">共 {results.length} 个结果</Text>}
            </div>

            <Spin spinning={searchLoading}>
              {results.length > 0 ? (
                <div style={styles.resultList}>
                  {results.map((item) => (
                    <div key={item.user_id} style={styles.listItem}>
                      <div style={styles.userMeta}>
                        <Avatar size={44} src={item.avatar} icon={<UserOutlined />} style={styles.avatar} />
                        <div style={{ minWidth: 0 }}>
                          <Text strong ellipsis style={{ display: 'block', maxWidth: 280 }}>{item.username}</Text>
                          <Text type="secondary">ID: {item.user_id}</Text>
                        </div>
                      </div>
                      <Button
                        icon={<UserAddOutlined />}
                        style={styles.actionButton}
                        onClick={() => setTargetUser(item)}
                      >
                        添加
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={styles.emptyResult}>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={searched ? '暂无匹配用户' : '输入用户名后开始搜索'}
                  />
                </div>
              )}
            </Spin>

            <div style={styles.resultHeader}>
              <Text strong>已发送申请</Text>
              <Text type="secondary">{pendingSentRequests.length} 个待通过</Text>
            </div>

            <Spin spinning={requestsLoading}>
              {sentRequests.length > 0 ? (
                <div style={styles.resultList}>
                  {sentRequests.map((item) => {
                    const statusMeta = getSentRequestStatusMeta(item.status);
                    return (
                    <div key={item.request_id} style={styles.listItem}>
                      <div style={styles.userMeta}>
                        <Avatar size={44} src={item.to_user?.avatar} icon={<UserOutlined />} style={styles.avatar} />
                        <div style={{ minWidth: 0 }}>
                          <Text strong ellipsis style={{ display: 'block', maxWidth: 280 }}>{item.to_user?.username}</Text>
                          <Text type="secondary">{item.message || '未填写验证信息'}</Text>
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                        <Tag color={statusMeta.color} icon={statusMeta.icon} style={{ marginInlineEnd: 0 }}>
                          {statusMeta.text}
                        </Tag>
                        <Text type="secondary">
                          {item.created_at ? new Date(item.created_at * 1000).toLocaleString() : '等待验证'}
                        </Text>
                      </div>
                    </div>
                    );
                  })}
                </div>
              ) : (
                <div style={styles.emptyResult}>
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已发送申请" />
                </div>
              )}
            </Spin>

          </main>
        </div>
      </Content>

      <Modal
        title={`添加好友：${targetUser?.username || ''}`}
        open={Boolean(targetUser)}
        onOk={handleSendRequest}
        onCancel={() => {
          setTargetUser(undefined);
          setRequestMsg('');
        }}
        okText="发送申请"
        cancelText="取消"
        confirmLoading={sending}
        destroyOnHidden
      >
        <div style={{ marginTop: 16 }}>
          <div style={styles.modalHint}>发送一条验证申请，等待对方通过：</div>
          <Input.TextArea
            rows={4}
            placeholder="请输入验证信息（选填）..."
            value={requestMsg}
            onChange={(event) => setRequestMsg(event.target.value)}
            maxLength={100}
            showCount
            style={{ borderRadius: 14 }}
          />
        </div>
      </Modal>
    </Layout>
  );
}
