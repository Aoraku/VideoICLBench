import React, { useEffect, useState } from 'react';
import { Layout, List, Avatar, Button, message, Typography, Spin, Tabs, Input, Modal, Popconfirm, Tag, Select } from 'antd';
import { UserOutlined, CheckOutlined, CloseOutlined, ArrowLeftOutlined, SearchOutlined, UserAddOutlined, TagOutlined, MessageOutlined, CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { useRouter } from 'next/router';
import Head from 'next/head';

const { Header, Content } = Layout;
const { Title, Text } = Typography;

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: 'linear-gradient(135deg, #f5fbff 0%, #eef5ff 48%, #dff2ff 100%)',
  },
  header: {
    height: 72,
    padding: '0 28px',
    display: 'flex',
    alignItems: 'center',
    gap: 18,
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
    width: 'min(1120px, 94vw)',
    minHeight: 640,
    display: 'grid',
    gridTemplateColumns: '280px 1fr',
    overflow: 'hidden',
    borderRadius: 28,
    background: 'rgba(255, 255, 255, 0.8)',
    border: '1px solid rgba(255, 255, 255, 0.86)',
    boxShadow: '0 28px 70px rgba(41, 124, 204, 0.14)',
  },
  summary: {
    position: 'relative',
    padding: 30,
    color: '#ffffff',
    background: 'linear-gradient(180deg, #17afff 0%, #078cf0 100%)',
    overflow: 'hidden',
    transition: 'background 0.18s ease-out',
  },
  summaryTitle: {
    margin: 0,
    color: '#ffffff',
    letterSpacing: 0,
  },
  summarySub: {
    display: 'block',
    marginTop: 10,
    color: 'rgba(255, 255, 255, 0.82)',
    lineHeight: 1.7,
  },
  metricGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 12,
    marginTop: 32,
  },
  metric: {
    padding: '16px 14px',
    borderRadius: 18,
    background: 'rgba(255, 255, 255, 0.18)',
    boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.2)',
    transition: 'transform 0.18s ease, background 0.18s ease, box-shadow 0.18s ease',
  },
  metricHover: {
    background: 'rgba(255, 255, 255, 0.28)',
    boxShadow: '0 18px 34px rgba(0, 104, 190, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.26)',
  },
  metricValue: {
    display: 'block',
    color: '#ffffff',
    fontSize: 26,
    fontWeight: 700,
  },
  metricLabel: {
    color: 'rgba(255, 255, 255, 0.76)',
    fontSize: 12,
  },
  mainPanel: {
    padding: '26px 30px',
    background: '#ffffff',
  },
  listItem: {
    padding: '16px 14px',
    borderRadius: 18,
    borderBlockEnd: 'none',
    marginBottom: 10,
    background: '#f7fbff',
  },
  avatar: {
    background: 'linear-gradient(135deg, #9bd7ff, #4aa9ff)',
  },
  actionButton: {
    borderRadius: 12,
  },
  primaryButton: {
    borderRadius: 12,
    background: 'linear-gradient(135deg, #22b7ff, #0a8cff)',
    border: 'none',
    boxShadow: '0 10px 22px rgba(10, 140, 255, 0.18)',
  },
  input: {
    height: 40,
    borderRadius: 14,
    background: '#f4f8fd',
  },
  searchRow: {
    display: 'flex',
    gap: 10,
    marginBottom: 18,
  },
  tagSelect: {
    width: 128,
  },
  statusText: {
    fontSize: 12,
  },
  modalHint: {
    marginBottom: 10,
    color: '#5b6b82',
  },
};

const getSentRequestsStorageKey = () => {
  if (typeof window === 'undefined') return 'im_sent_friend_requests:server';
  const userKey = localStorage.getItem('user_id') || localStorage.getItem('username') || 'current';
  return `im_sent_friend_requests:${userKey}`;
};

const getSentRequestTime = (request: any) => request.created_at || 0;

const normalizeSentRequests = (requests: any[]) => {
  const byUserId = new Map<number, any>();
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

const readCachedSentRequests = (): any[] => {
  if (typeof window === 'undefined') return [];
  try {
    const cached = localStorage.getItem(getSentRequestsStorageKey());
    const parsed = cached ? JSON.parse(cached) : [];
    return Array.isArray(parsed) ? normalizeSentRequests(parsed) : [];
  } catch {
    return [];
  }
};

const writeCachedSentRequests = (requests: any[]) => {
  if (typeof window === 'undefined') return;
  localStorage.setItem(getSentRequestsStorageKey(), JSON.stringify(normalizeSentRequests(requests)));
};

const mergeSentRequests = (...requestGroups: any[][]) => normalizeSentRequests(requestGroups.flat());

const markAcceptedSentRequests = (requests: any[], friends: any[]) => {
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
  return { color: 'processing', icon: <ClockCircleOutlined />, text: '等待验证' };
};

export default function FriendsPage() {
  const router = useRouter();
  
  // --- 基础状态 ---
  const [requests, setRequests] = useState<any[]>([]);
  const [sentRequests, setSentRequests] = useState<any[]>([]);
  const [friends, setFriends] = useState<any[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | undefined>(undefined);

  // --- 搜索与添加好友状态 ---
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [targetUser, setTargetUser] = useState<any>(undefined);
  const [requestMsg, setRequestMsg] = useState('');

  // --- 标签管理状态 ---
  const [newGroupName, setNewGroupName] = useState('');
  const [groupLoading, setGroupLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('my_friends');
  const [summaryPoint, setSummaryPoint] = useState({ x: 35, y: 28 });
  const [hoveredMetric, setHoveredMetric] = useState<string | undefined>(undefined);

  const parallaxX = (summaryPoint.x - 50) / 50;
  const parallaxY = (summaryPoint.y - 50) / 50;
  const summaryStyle = {
    ...styles.summary,
    background: `radial-gradient(circle at ${summaryPoint.x}% ${summaryPoint.y}%, rgba(255,255,255,0.42), rgba(255,255,255,0.08) 28%, transparent 48%), linear-gradient(180deg, #17afff 0%, #078cf0 100%)`,
  };
  const getMetricStyle = (key: string, strength: number) => ({
    ...styles.metric,
    ...(hoveredMetric === key ? styles.metricHover : undefined),
    cursor: 'pointer',
    transform: `translate(${parallaxX * strength}px, ${parallaxY * strength}px)${hoveredMetric === key ? ' translateY(-3px)' : ''}`,
  });
  const handleMetricKeyDown = (event: React.KeyboardEvent<HTMLDivElement>, key: string) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setActiveTab(key);
    }
  };

  const fetchRequests = async () => {
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends/request', { method: 'GET', headers: { 'Authorization': `Bearer ${token}` } });
      const data = await response.json();
      if (data.code === 0) {
        setRequests(data.received_requests || data.requests || []);
        const remote = Array.isArray(data.sent_requests) ? data.sent_requests : [];
        const cached = readCachedSentRequests();
        setSentRequests(prev => {
          const next = mergeSentRequests(cached, prev, remote);
          writeCachedSentRequests(next);
          return next;
        });
      }
    } catch { message.error('网络错误'); }
  };

  const fetchFriends = async () => {
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends', { method: 'GET', headers: { 'Authorization': `Bearer ${token}` } });
      const data = await response.json();
      if (data.code === 0) {
        const nextFriends = data.friends || [];
        setFriends(nextFriends);
        setSentRequests(prev => {
          const next = markAcceptedSentRequests(prev, nextFriends);
          writeCachedSentRequests(next);
          return next;
        });
      }
    } catch { message.error('网络错误'); }
  };

  const fetchGroups = async () => {
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends/groups', { method: 'GET', headers: { 'Authorization': `Bearer ${token}` } });
      const data = await response.json();
      if (data.code === 0) setGroups(data.groups || ['默认分组']);
    } catch { message.error('网络错误'); }
  };

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    setLoading(true);
    const cached = readCachedSentRequests();
    if (cached.length > 0) setSentRequests(cached);
    
    const refreshData = () => {
      fetchRequests();
      fetchFriends();
    };

    Promise.all([fetchRequests(), fetchFriends(), fetchGroups()])
      .finally(() => setLoading(false));

    const interval = setInterval(refreshData, 5000); // 5000ms = 5秒

    return () => clearInterval(interval);
  }, []);

  const handleRequest = async (requestId: number, action: 'accept' | 'reject') => {
    setActionLoading(requestId);
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends/request', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ request_id: requestId, action })
      });
      const data = await response.json();
      
      if (data.code === 0) {
        message.success(`已${action === 'accept' ? '同意' : '拒绝'}该申请`);
        
        const targetRequest = requests.find(r => r.request_id === requestId);
        
        // 2. 立即从申请列表中移除该请求项，界面会瞬间消失
        setRequests(prev => prev.filter(r => r.request_id !== requestId));
        
        // 3. 如果是同意操作，立刻在前端把它包装成好友塞进列表中
        if (action === 'accept' && targetRequest) {
          setFriends(prev => [
            {
              user_id: targetRequest.from_user.user_id,
              username: targetRequest.from_user.username,
              avatar: targetRequest.from_user.avatar,
              group: '默认分组', // 新增好友默认在这个分组
              online: true
            },
            ...prev
          ]);
        }
        fetchRequests();
        if (action === 'accept') fetchFriends();

      } else { 
        message.error(`操作失败: ${data.info}`); 
      }
    } catch { 
      message.error('网络错误'); 
    } finally { 
      setActionLoading(undefined); 
    }
  };

  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    setSearchLoading(true);
    const token = localStorage.getItem('token');
    try {
      const response = await fetch(`/api/user/search?keyword=${encodeURIComponent(searchKeyword)}&page=1&page_size=20`, {
        method: 'GET', headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      if (data.code === 0) {
        setSearchResults(data.users || []);
        if (data.users.length === 0) message.info('未找到相关用户');
      } else { message.error(data.info || '搜索失败'); }
    } catch { message.error('网络错误'); } finally { setSearchLoading(false); }
  };

  const handleSendRequest = async () => {
    if (!targetUser) return;
    const requestedUser = targetUser;
    const requestedMessage = requestMsg;
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ to_user_id: targetUser.user_id, message: requestMsg, source: 'search' })
      });
      const data = await response.json();
      if (data.code === 0) {
        message.success('好友请求已发送');
        upsertSentRequest(requestedUser, requestedMessage);
        setIsModalVisible(false);
        setRequestMsg('');
        setActiveTab('sent_requests');
        fetchRequests();
      } else if (data.code === 2) {
        message.warning('你们已经是好友啦');
        setIsModalVisible(false);
      } else if (data.code === 3) {
        message.warning('已发送过请求，请等待对方处理');
        upsertSentRequest(requestedUser, requestedMessage);
        setIsModalVisible(false);
        setRequestMsg('');
        setActiveTab('sent_requests');
        fetchRequests();
      } else { message.error(`发送失败: ${data.info}`); }
    } catch { message.error('网络错误'); }
  };

  const upsertSentRequest = (user: any, messageText: string) => {
    const now = Math.floor(Date.now() / 1000);
    setSentRequests(prev => {
      const exists = prev.some(item => item.to_user?.user_id === user.user_id);
      if (exists) {
        const next = prev.map(item => (
          item.to_user?.user_id === user.user_id
            ? {
              ...item,
              request_id: -now,
              to_user: {
                user_id: user.user_id,
                username: user.username,
                avatar: user.avatar,
              },
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
        to_user: {
          user_id: user.user_id,
          username: user.username,
          avatar: user.avatar,
        },
        message: messageText,
        status: 'pending',
        created_at: now,
      }, ...prev];
      const normalized = normalizeSentRequests(next);
      writeCachedSentRequests(normalized);
      return normalized;
    });
  };

  const handleDeleteFriend = async (friendId: number) => {
    const token = localStorage.getItem('token');
    try {
      const response = await fetch(`/api/friends/${friendId}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
      const data = await response.json();
      if (data.code === 0) {
        message.success('已解除好友关系');
        fetchFriends();
      } else { message.error(`删除失败: ${data.info}`); }
    } catch { message.error('网络错误'); }
  };

  const handleUpdateFriendTag = async (friendId: number, groupName: string) => {
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends/groups', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ friend_id: friendId, group_name: groupName })
      });
      const data = await response.json();
      if (data.code === 0) {
        message.success('已更新好友标签');
        fetchFriends();
      } else { message.error(`更新失败: ${data.info}`); }
    } catch { message.error('网络错误'); }
  };

  const handleCreateTag = async () => {
    if (!newGroupName.trim()) return;
    setGroupLoading(true);
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ group_name: newGroupName })
      });
      const data = await response.json();
      if (data.code === 0) {
        message.success('新标签创建成功');
        setNewGroupName('');
        fetchGroups();
      } else { message.error(`创建失败: ${data.info}`); }
    } catch { message.error('网络错误'); } finally { setGroupLoading(false); }
  };

  const handleDeleteTag = async (groupName: string) => {
    const token = localStorage.getItem('token');
    try {
      const response = await fetch('/api/friends/groups', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ group_name: groupName })
      });
      const data = await response.json();
      if (data.code === 0) {
        message.success('标签已删除');
        fetchGroups();
        fetchFriends();
      } else { message.error(`删除失败: ${data.info}`); }
    } catch { message.error('网络错误'); }
  };

  const pendingSentRequests = sentRequests.filter((item) => item.status === 'pending');

  return (
    <Layout style={styles.page}>
      <Head><title>通讯录 - IM System</title></Head>

      <Header style={styles.header}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => router.push('/')} style={styles.backButton}>
          返回主页
        </Button>
        <Title level={4} style={{ margin: 0, color: '#172033' }}>好友与通讯录</Title>
      </Header>

      <Content style={styles.content}>
        <div style={styles.shell}>
          <aside
            style={summaryStyle}
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              setSummaryPoint({
                x: Math.round(((event.clientX - rect.left) / rect.width) * 100),
                y: Math.round(((event.clientY - rect.top) / rect.height) * 100),
              });
            }}
          >
            <Title level={2} style={styles.summaryTitle}>Contacts</Title>
            <Text style={styles.summarySub}>管理好友、申请和分组，让会话从这里开始。</Text>
            <div style={styles.metricGrid}>
              <div
                role="button"
                tabIndex={0}
                style={getMetricStyle('friends', -6)}
                onMouseEnter={() => setHoveredMetric('friends')}
                onMouseLeave={() => setHoveredMetric(undefined)}
                onClick={() => setActiveTab('my_friends')}
                onKeyDown={(event) => handleMetricKeyDown(event, 'my_friends')}
              >
                <Text style={styles.metricValue}>{friends.length}</Text>
                <Text style={styles.metricLabel}>好友</Text>
              </div>
              <div
                role="button"
                tabIndex={0}
                style={getMetricStyle('requests', 5)}
                onMouseEnter={() => setHoveredMetric('requests')}
                onMouseLeave={() => setHoveredMetric(undefined)}
                onClick={() => setActiveTab('requests')}
                onKeyDown={(event) => handleMetricKeyDown(event, 'requests')}
              >
                <Text style={styles.metricValue}>{requests.length}</Text>
                <Text style={styles.metricLabel}>申请</Text>
              </div>
              <div
                role="button"
                tabIndex={0}
                style={getMetricStyle('sent_requests', -4)}
                onMouseEnter={() => setHoveredMetric('sent_requests')}
                onMouseLeave={() => setHoveredMetric(undefined)}
                onClick={() => setActiveTab('sent_requests')}
                onKeyDown={(event) => handleMetricKeyDown(event, 'sent_requests')}
              >
                <Text style={styles.metricValue}>{pendingSentRequests.length}</Text>
                <Text style={styles.metricLabel}>待通过</Text>
              </div>
              <div
                role="button"
                tabIndex={0}
                style={getMetricStyle('groups', 4)}
                onMouseEnter={() => setHoveredMetric('groups')}
                onMouseLeave={() => setHoveredMetric(undefined)}
                onClick={() => setActiveTab('tag_manage')}
                onKeyDown={(event) => handleMetricKeyDown(event, 'tag_manage')}
              >
                <Text style={styles.metricValue}>{groups.length}</Text>
                <Text style={styles.metricLabel}>标签</Text>
              </div>
            </div>
          </aside>

          <main style={styles.mainPanel}>
          <Spin spinning={loading}>
            <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
              {
                key: 'my_friends',
                label: `我的好友 (${friends.length})`,
                children: (
                  <List
                    itemLayout="horizontal"
                    dataSource={friends}
                    locale={{ emptyText: '暂无好友' }}
	                    renderItem={(item) => (
	                      <List.Item
	                        style={styles.listItem}
	                        actions={[
                          <Button 
                            key="chat" 
                            type="link" 
                            icon={<MessageOutlined />}
                            style={styles.actionButton}
                            onClick={() => router.push(`/?to_user_id=${item.user_id}&name=${encodeURIComponent(item.username)}`)}
                          >
                            发消息
                          </Button>,
                          <Select
                            key="tag"
                            size="small"
                            value={item.group || '默认分组'}
                            style={styles.tagSelect}
                            onChange={(val) => handleUpdateFriendTag(item.user_id, val)}
                            options={groups.map(g => ({ label: g, value: g }))}
                          />,
                          <Popconfirm
                            key="delete"
                            title="确定要删除该好友吗？"
                            onConfirm={() => handleDeleteFriend(item.user_id)}
                            okText="确定删除"
                            cancelText="取消"
                          >
                            <Button danger size="small" style={styles.actionButton}>删除</Button>
                          </Popconfirm>
                        ]}
                      >
                        <List.Item.Meta 
                          avatar={<Avatar src={item.avatar} icon={<UserOutlined />} style={styles.avatar} />}
                          title={item.username}
                          description={
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                              <Tag color={item.group && item.group !== '默认分组' ? 'blue' : 'default'} icon={<TagOutlined />}>
                                {item.group || '默认分组'}
                              </Tag>
                            </div>
                          } 
                        />
                      </List.Item>
                    )}
                  />
                )
              },
              {
                key: 'requests',
                label: `新的朋友 (${requests.length})`,
                children: (
                  <List
                    itemLayout="horizontal"
                    dataSource={requests}
                    locale={{ emptyText: '暂无新的好友申请' }}
                    renderItem={(item) => (
                      <List.Item
                        style={styles.listItem}
                        actions={[
                          <Button key="accept" type="primary" size="small" icon={<CheckOutlined />} loading={actionLoading === item.request_id} onClick={() => handleRequest(item.request_id, 'accept')} style={styles.primaryButton}>同意</Button>,
                          <Button key="reject" danger size="small" icon={<CloseOutlined />} loading={actionLoading === item.request_id} onClick={() => handleRequest(item.request_id, 'reject')} style={styles.actionButton}>拒绝</Button>
                        ]}
                      >
	                        <List.Item.Meta avatar={<Avatar src={item.from_user.avatar} icon={<UserOutlined />} style={styles.avatar} />} title={item.from_user.username} description={`附加消息: ${item.message || '无'}`} />
	                      </List.Item>
	                    )}
	                  />
	                )
	              },
              {
                key: 'sent_requests',
                label: `已发送 (${sentRequests.length})`,
                children: (
                  <List
                    itemLayout="horizontal"
                    dataSource={sentRequests}
                    locale={{ emptyText: '暂无已发送申请' }}
                    renderItem={(item) => {
                      const statusMeta = getSentRequestStatusMeta(item.status);
                      return (
                      <List.Item style={styles.listItem}>
                        <List.Item.Meta
                          avatar={<Avatar src={item.to_user?.avatar} icon={<UserOutlined />} style={styles.avatar} />}
                          title={item.to_user?.username}
                          description={
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                              <Text type="secondary">验证信息: {item.message || '无'}</Text>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <Tag color={statusMeta.color} icon={statusMeta.icon}>
                                  {statusMeta.text}
                                </Tag>
                                {item.created_at && (
                                  <Text type="secondary" style={styles.statusText}>
                                    {new Date(item.created_at * 1000).toLocaleString()}
                                  </Text>
                                )}
                              </div>
                            </div>
                          }
                        />
                      </List.Item>
                      );
                    }}
                  />
                )
              },
              {
                key: 'add_friend',
                label: '添加好友',
                children: (
                  <div>
                    <div style={styles.searchRow}>
                      <Input 
                        placeholder="请输入用户名查找用户" 
                        prefix={<SearchOutlined />} 
                        style={styles.input}
                        value={searchKeyword}
                        onChange={(e) => setSearchKeyword(e.target.value)}
                        onPressEnter={handleSearch}
                      />
                      <Button type="primary" onClick={handleSearch} loading={searchLoading} style={styles.primaryButton}>搜索</Button>
                    </div>
                    <List
                      itemLayout="horizontal"
                      dataSource={searchResults}
                      loading={searchLoading}
                      locale={{ emptyText: '请输入关键词进行搜索' }}
                      renderItem={(item) => (
                        <List.Item
                          style={styles.listItem}
                          actions={[
                            <Button key="add" type="default" size="small" icon={<UserAddOutlined />} onClick={() => { setTargetUser(item); setIsModalVisible(true); }} style={styles.actionButton}>
                              添加
                            </Button>
                          ]}
                        >
                          <List.Item.Meta avatar={<Avatar src={item.avatar} icon={<UserOutlined />} style={styles.avatar} />} title={item.username} description={`ID: ${item.user_id}`} />
                        </List.Item>
                      )}
                    />
                  </div>
                )
              },
              {
                key: 'tag_manage',
                label: '标签管理',
                children: (
                  <div>
                    <div style={styles.searchRow}>
                      <Input 
                        placeholder="输入新标签名称，例如：同事、亲戚" 
                        prefix={<TagOutlined />} 
                        style={styles.input}
                        value={newGroupName}
                        onChange={(e) => setNewGroupName(e.target.value)}
                        onPressEnter={handleCreateTag}
                        maxLength={15}
                      />
                      <Button type="primary" onClick={handleCreateTag} loading={groupLoading} style={styles.primaryButton}>添加标签</Button>
                    </div>
                    <List
                      bordered
                      dataSource={groups}
                      renderItem={(item) => (
                        <List.Item
                          style={styles.listItem}
                          actions={
                            item !== '默认分组' ? [
                              <Popconfirm key="del-tag" title="删除该标签后，已有该标签的好友将恢复为默认分组" onConfirm={() => handleDeleteTag(item)}>
                                <Button danger size="small" type="text" style={styles.actionButton}>删除</Button>
                              </Popconfirm>
                            ] : []
                          }
                        >
                          <Tag color={item === '默认分组' ? 'default' : 'blue'}>{item}</Tag>
                        </List.Item>
                      )}
                    />
                  </div>
                )
              }
            ]} />
          </Spin>
          </main>
        </div>
      </Content>

      <Modal 
        title={`添加好友：${targetUser?.username}`} 
        open={isModalVisible} 
        onOk={handleSendRequest} 
        onCancel={() => { setIsModalVisible(false); setRequestMsg(''); }}
        okText="发送申请" cancelText="取消" destroyOnClose
      >
        <div style={{ marginTop: 16 }}>
          <div style={styles.modalHint}>你需要发送验证申请，等对方通过：</div>
          <Input.TextArea rows={4} placeholder="请输入验证信息（选填）..." value={requestMsg} onChange={(e) => setRequestMsg(e.target.value)} maxLength={100} showCount style={{ borderRadius: 14 }} />
        </div>
      </Modal>
    </Layout>
  );
}
