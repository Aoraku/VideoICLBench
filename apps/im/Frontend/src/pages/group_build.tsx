import {nativeFetch as fetch, nativeIM} from '../benchmark/bridge';
import React, { useEffect, useMemo, useState } from 'react';
import { Button, Empty, Input, Layout, message, Spin, Typography } from 'antd';
import { CheckOutlined, CloseCircleFilled, RightOutlined, SearchOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons';
import { useRouter } from 'next/router';
import Head from 'next/head';

const { Content } = Layout;
const { Text } = Typography;

interface FriendItem {
  key: string;
  user_id: number;
  title: string;
  description: string;
  avatar?: string;
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    height: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    background: 'linear-gradient(135deg, #f6fbff 0%, #edf6ff 48%, #ddf1ff 100%)',
    color: '#172033',
  },
  shell: {
    position: 'relative',
    width: 'min(704px, calc(100vw - 48px))',
    height: 'min(544px, calc(100vh - 48px))',
    display: 'grid',
    gridTemplateColumns: '320px 1fr',
    overflow: 'hidden',
    border: '1px solid rgba(218, 232, 248, 0.95)',
    borderRadius: 10,
    background: 'rgba(255, 255, 255, 0.92)',
    boxShadow: '0 28px 72px rgba(38, 125, 208, 0.16)',
  },
  accentBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: 4,
    background: 'linear-gradient(90deg, #12a8ff 0%, #07c160 48%, #8fb8ff 100%)',
    zIndex: 2,
  },
  leftPane: { minWidth: 0, display: 'flex', flexDirection: 'column', borderRight: '1px solid #dce9f8', background: '#ffffff' },
  rightPane: { minWidth: 0, display: 'flex', flexDirection: 'column', padding: '24px 28px 20px', background: '#f7fbff' },
  searchWrap: { padding: '20px 20px 10px' },
  searchInput: { height: 34, border: '1px solid #e0ebf7', borderRadius: 8, color: '#253143', background: '#f3f7fc' },
  listBody: { flex: 1, overflowY: 'auto', paddingBottom: 18 },
  sectionButton: {
    width: '100%',
    height: 44,
    padding: '0 22px',
    border: 'none',
    borderBottom: '1px solid #edf3fa',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    color: '#253143',
    background: 'transparent',
    cursor: 'pointer',
    textAlign: 'left',
  },
  groupRow: {
    height: 58,
    padding: '0 20px 0 52px',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    borderBottom: '1px solid #edf3fa',
    cursor: 'pointer',
    background: '#f8fbff',
  },
  letter: { padding: '16px 0 8px 56px', color: '#8a95a6', fontSize: 12 },
  contactRow: {
    width: '100%',
    height: 50,
    padding: '0 20px 0 28px',
    border: 'none',
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    color: '#253143',
    background: 'transparent',
    cursor: 'pointer',
    textAlign: 'left',
  },
  checkCircle: {
    width: 16,
    height: 16,
    borderRadius: '50%',
    border: '1px solid #c2cfdd',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    color: '#ffffff',
    fontSize: 10,
  },
  selectedCheck: { borderColor: '#07c160', background: '#07c160' },
  selectedHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 },
  selectedList: { flex: 1, overflowY: 'auto' },
  selectedRow: { height: 52, display: 'flex', alignItems: 'center', gap: 12, color: '#253143' },
  selectedCount: {
    padding: '3px 9px',
    borderRadius: 999,
    color: '#5b6b82',
    background: '#eaf4ff',
    fontSize: 12,
  },
  removeIcon: { marginLeft: 'auto', color: '#9aa8b8', cursor: 'pointer' },
  footer: { display: 'flex', justifyContent: 'flex-end', gap: 62, paddingTop: 18 },
  doneButton: { width: 122, height: 32, borderRadius: 6, background: '#07c160', border: 'none' },
  cancelButton: { width: 122, height: 32, borderRadius: 6, color: '#253143', background: '#eef4fb', border: 'none' },
};

const renderSquareAvatar = (avatar: string | undefined, icon: React.ReactNode, background: string) => (
  <span
    style={{
      width: 32,
      height: 32,
      borderRadius: 4,
      flexShrink: 0,
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#ffffff',
      background,
      backgroundImage: avatar ? `url("${avatar}")` : undefined,
      backgroundPosition: 'center',
      backgroundSize: 'cover',
      backgroundRepeat: 'no-repeat',
    }}
  >
    {!avatar && icon}
  </span>
);

const getLetter = (name: string) => {
  const first = name.trim()[0]?.toUpperCase();
  return first && /^[A-Z]$/.test(first) ? first : '#';
};

const buildGroupName = (names: string[]) => {
  const cleaned = names
    .slice(0, 4)
    .join(' ')
    .replace(/[^\u4e00-\u9fa5\w -]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return cleaned.slice(0, 30) || '群聊';
};

export default function GroupBuildPage() {
  const router = useRouter();
  const [friends, setFriends] = useState<FriendItem[]>([]);
  const [groups, setGroups] = useState<any[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [keyword, setKeyword] = useState('');
  const [groupsOpen, setGroupsOpen] = useState(true);
  const [contactsOpen, setContactsOpen] = useState(true);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      const token = localStorage.getItem('token');
      if (!token) {
        message.warning('请先登录');
        router.push('/login');
        return;
      }

      try {
        const [friendsRes, conversationsRes] = await Promise.all([
          fetch('/api/friends', { headers: { 'Authorization': `Bearer ${token}` } }),
          fetch('/api/conversations', { headers: { 'Authorization': `Bearer ${token}` } }),
        ]);
        const friendsData = await friendsRes.json();
        const conversationsData = await conversationsRes.json();

        if (friendsData.code === 0) {
          setFriends((friendsData.friends || []).map((item: any) => ({
            key: String(item.user_id),
            user_id: item.user_id,
            title: item.username,
            description: item.group || '默认分组',
            avatar: item.avatar,
          })));
        }
        if (conversationsData.code === 0) {
          setGroups((conversationsData.conversations || []).filter((item: any) => item.type === 'group'));
        }
      } catch {
        message.error('加载联系人失败');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [router]);

  const selectedFriends = useMemo(
    () => friends.filter((item) => selectedKeys.includes(item.key)),
    [friends, selectedKeys]
  );
  const filteredFriends = useMemo(() => {
    const text = keyword.trim().toLowerCase();
    return text ? friends.filter((item) => item.title.toLowerCase().includes(text)) : friends;
  }, [friends, keyword]);
  const filteredGroups = useMemo(() => {
    const text = keyword.trim().toLowerCase();
    return text ? groups.filter((item) => item.name?.toLowerCase().includes(text)) : groups;
  }, [groups, keyword]);
  const groupedFriends = useMemo(() => {
    const grouped = new Map<string, FriendItem[]>();
    filteredFriends.forEach((item) => {
      const letter = getLetter(item.title);
      grouped.set(letter, [...(grouped.get(letter) || []), item]);
    });
    return Array.from(grouped.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredFriends]);

  const toggleFriend = (key: string) => {
    setSelectedKeys(prev => (
      prev.includes(key) ? prev.filter(item => item !== key) : [...prev, key]
    ));
  };

  const handleDone = async () => {
    if (selectedFriends.length === 0) return;
    if (selectedFriends.length === 1) {
      const friend = selectedFriends[0];
      router.push(`/?to_user_id=${friend.user_id}&name=${encodeURIComponent(friend.title)}`);
      return;
    }

    setSubmitting(true);
    const token = localStorage.getItem('token');
    try {
      const res = await fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          name: buildGroupName(selectedFriends.map(item => item.title)),
          member_ids: selectedFriends.map(item => item.user_id),
        }),
      });
      const data = await res.json();
      if (data.code === 0) {
        message.success('群聊创建成功');
        router.push(`/?conversation_id=${data.conversation_id}`);
      } else {
        message.error(`创建失败: ${data.info}`);
      }
    } catch {
      message.error('网络错误');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Layout style={styles.page}>
      <Head><title>发起群聊 - IM System</title></Head>
      <Content style={styles.shell}>
        <div style={styles.accentBar} />
        <section style={styles.leftPane}>
          <div style={styles.searchWrap}>
            <Input
              prefix={<SearchOutlined style={{ color: '#8a8a8a' }} />}
              placeholder="搜索"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              style={styles.searchInput}
            />
          </div>
          <Spin spinning={loading}>
            <div style={styles.listBody}>
              <button type="button" style={styles.sectionButton} onClick={() => setGroupsOpen(prev => !prev)}>
                <RightOutlined rotate={groupsOpen ? 90 : 0} style={{ fontSize: 11, color: '#8a95a6' }} />
                <Text style={{ color: '#253143' }}>选择一个已有群</Text>
              </button>
              {groupsOpen && filteredGroups.map((item) => (
                <button
                  key={item.conversation_id}
                  type="button"
                  style={styles.groupRow}
                  onClick={() => router.push(`/?conversation_id=${item.conversation_id}`)}
                >
                  {renderSquareAvatar(item.avatar, <TeamOutlined />, '#8fb8ff')}
                  <Text ellipsis style={{ color: '#253143', maxWidth: 156 }}>{item.name}</Text>
                  <Text style={{ marginLeft: 'auto', color: '#7b8ba1', fontSize: 12 }}>进入群聊</Text>
                </button>
              ))}
              <button type="button" style={styles.sectionButton} onClick={() => setContactsOpen(prev => !prev)}>
                <RightOutlined rotate={contactsOpen ? 90 : 0} style={{ fontSize: 11, color: '#8a95a6' }} />
                <Text style={{ color: '#253143' }}>联系人</Text>
              </button>
              {contactsOpen && (groupedFriends.length > 0 ? groupedFriends.map(([letter, items]) => (
                <div key={letter}>
                  <div style={styles.letter}>{letter}</div>
                  {items.map((item) => {
                    const selected = selectedKeys.includes(item.key);
                    return (
                      <button key={item.key} type="button" style={styles.contactRow} onClick={() => toggleFriend(item.key)}>
                        <span style={{ ...styles.checkCircle, ...(selected ? styles.selectedCheck : undefined) }}>
                          {selected && <CheckOutlined />}
                        </span>
                        {renderSquareAvatar(item.avatar, <UserOutlined />, '#9bd7ff')}
                        <span style={{display:"flex",flexDirection:"column",textAlign:"left"}}><Text ellipsis style={{ color: '#253143', maxWidth: 190 }}>{item.title}</Text>{nativeIM&&<small style={{fontSize:10,color:"#8a95a6"}}>{item.description}</small>}</span>
                      </button>
                    );
                  })}
                </div>
              )) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span style={{ color: '#8a8a8a' }}>暂无联系人</span>} />
              ))}
            </div>
          </Spin>
        </section>

        <section style={styles.rightPane}>
          <div style={styles.selectedHeader}>
            <Text style={{ color: '#172033', fontWeight: 600 }}>发起群聊</Text>
            <Text style={styles.selectedCount}>已选择{selectedFriends.length}个联系人</Text>
          </div>
          <div style={styles.selectedList}>
            {selectedFriends.map((item) => (
              <div key={item.key} style={styles.selectedRow}>
                {renderSquareAvatar(item.avatar, <UserOutlined />, '#9bd7ff')}
                <Text ellipsis style={{ color: '#253143', maxWidth: 220 }}>{item.title}</Text>
                <CloseCircleFilled style={styles.removeIcon} onClick={() => toggleFriend(item.key)} />
              </div>
            ))}
          </div>
          <div style={styles.footer}>
            <Button
              type="primary"
              loading={submitting}
              disabled={selectedFriends.length === 0}
              style={styles.doneButton}
              onClick={handleDone}
            >
              完成
            </Button>
            <Button style={styles.cancelButton} onClick={() => router.back()}>
              取消
            </Button>
          </div>
        </section>
      </Content>
    </Layout>
  );
}
