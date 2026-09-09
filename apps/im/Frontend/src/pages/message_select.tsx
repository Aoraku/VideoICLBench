import React, { useEffect, useMemo, useState } from 'react';
import { Avatar, Button, DatePicker, Empty, Input, Layout, message, Spin, Typography } from 'antd';
import {
  ArrowLeftOutlined,
  CalendarOutlined,
  CheckOutlined,
  CloseCircleFilled,
  SearchOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useRouter } from 'next/router';
import Head from 'next/head';

const { Content } = Layout;
const { Text } = Typography;

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    background: 'linear-gradient(135deg, #f6fbff 0%, #edf6ff 48%, #ddf1ff 100%)',
  },
  panel: {
    width: 'min(760px, calc(100vw - 48px))',
    height: 'min(680px, calc(100vh - 48px))',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    borderRadius: 12,
    background: 'rgba(255, 255, 255, 0.94)',
    border: '1px solid #dbe8f8',
    boxShadow: '0 28px 72px rgba(38, 125, 208, 0.16)',
  },
  header: {
    height: 52,
    padding: '0 18px',
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    borderBottom: '1px solid #e4eef9',
    background: '#ffffff',
  },
  headerTitle: { flex: 1, minWidth: 0, textAlign: 'center', color: '#172033', fontWeight: 600 },
  searchWrap: { padding: '16px 20px 8px', background: '#ffffff' },
  searchInput: { height: 42, borderRadius: 8, background: '#f4f8fd', borderColor: '#dbe8f8' },
  tabs: {
    height: 42,
    padding: '0 20px',
    display: 'flex',
    alignItems: 'center',
    gap: 24,
    borderBottom: '1px solid #e4eef9',
    background: '#ffffff',
  },
  tabButton: {
    height: 42,
    padding: 0,
    border: 'none',
    color: '#6f7c8f',
    background: 'transparent',
    cursor: 'pointer',
  },
  activeTab: { color: '#118fff', fontWeight: 600, borderBottom: '2px solid #12a8ff' },
  filterPanel: {
    margin: '12px 20px 0',
    padding: 14,
    borderRadius: 10,
    background: '#f7fbff',
    border: '1px solid #dce9f8',
  },
  memberSearch: { height: 34, borderRadius: 8, background: '#ffffff' },
  memberList: { maxHeight: 216, overflowY: 'auto', marginTop: 10 },
  memberLetter: { padding: '10px 0 6px', color: '#8a95a6', fontSize: 12 },
  memberRow: {
    width: '100%',
    height: 46,
    padding: '0 8px',
    border: 'none',
    borderRadius: 8,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    background: 'transparent',
    cursor: 'pointer',
    textAlign: 'left',
  },
  selectedMemberRow: { background: '#eaf4ff' },
  results: { flex: 1, overflowY: 'auto', padding: '12px 20px 20px' },
  resultItem: {
    padding: '12px 8px',
    display: 'grid',
    gridTemplateColumns: '36px minmax(0, 1fr) auto',
    gap: 10,
    alignItems: 'start',
    borderRadius: 10,
    cursor: 'pointer',
  },
  resultMeta: { display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 },
  senderName: { color: '#6f7c8f', fontSize: 12 },
  content: { color: '#263244', lineHeight: 1.55, wordBreak: 'break-word' },
  time: { color: '#8a95a6', fontSize: 12, whiteSpace: 'nowrap' },
  activeFilter: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '4px 8px',
    borderRadius: 999,
    color: '#2377c7',
    background: '#eaf4ff',
    fontSize: 12,
  },
};

const getLetter = (name: string) => {
  const first = name.trim()[0]?.toUpperCase();
  return first && /^[A-Z]$/.test(first) ? first : '#';
};

const getQueryValue = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] : value;

const getMemberId = (member: any) => {
  const id = member?.user_id ?? member?.id;
  return typeof id === 'number' ? id : undefined;
};

const getMemberName = (member: any) => member?.username || member?.name || member?.nickname || '';

const formatMessageTime = (timestamp?: number) => {
  if (typeof timestamp !== 'number') return '';
  return new Date(timestamp * 1000).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

export default function MessageSelectPage() {
  const router = useRouter();
  const { conversation_id: conversationId, type, name } = router.query;
  const conversationIdValue = getQueryValue(conversationId);
  const conversationType = getQueryValue(type);
  const conversationName = getQueryValue(name);

  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);
  const [members, setMembers] = useState<any[]>([]);
  const [canFilterByMember, setCanFilterByMember] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [memberKeyword, setMemberKeyword] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'date' | 'member'>('all');
  const [timeRange, setTimeRange] = useState<any>(undefined);
  const [selectedSender, setSelectedSender] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (!conversationIdValue) return;
    let cancelled = false;
    const token = localStorage.getItem('token');
    setMembers([]);
    setSelectedSender(undefined);
    setCanFilterByMember(conversationType === 'group');

    fetch(`/api/conversations/${conversationIdValue}/group`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (cancelled) return;
        if (data.code === 0) {
          setMembers(data.members || []);
          setCanFilterByMember(true);
        } else {
          setCanFilterByMember(conversationType === 'group');
        }
      })
      .catch(() => {
        if (!cancelled) setCanFilterByMember(conversationType === 'group');
      });
    return () => { cancelled = true; };
  }, [conversationIdValue, conversationType]);

  const handleSearch = async (overrides?: { timeRange?: any; senderId?: number }) => {
    if (!conversationIdValue) return;
    setLoading(true);
    const token = localStorage.getItem('token');
    const params = new URLSearchParams({ limit: '100' });
    const effectiveTimeRange = overrides && 'timeRange' in overrides ? overrides.timeRange : timeRange;
    const effectiveSender = overrides && 'senderId' in overrides ? overrides.senderId : selectedSender;
    if (effectiveTimeRange?.[0]) params.append('start_time', String(effectiveTimeRange[0].valueOf() / 1000));
    if (effectiveTimeRange?.[1]) params.append('end_time', String(effectiveTimeRange[1].valueOf() / 1000));
    if (typeof effectiveSender === 'number') params.append('sender_id', String(effectiveSender));

    try {
      const res = await fetch(`/api/conversations/${conversationIdValue}/messages?${params.toString()}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.code === 0) {
        setMessages(data.messages || []);
        if ((data.messages || []).length === 0) message.info('未找到符合条件的消息');
      } else {
        message.error(`搜索失败: ${data.info}`);
      }
    } catch {
      message.error('搜索失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (router.isReady && conversationIdValue) handleSearch();
  }, [router.isReady, conversationIdValue]);

  const filteredMessages = useMemo(() => {
    const text = keyword.trim().toLowerCase();
    if (!text) return messages;
    return messages.filter((item) => (
      item.content?.toLowerCase().includes(text) ||
      item.sender_name?.toLowerCase().includes(text)
    ));
  }, [messages, keyword]);

  const memberOptions = useMemo(() => {
    if (members.length > 0) return members;

    const seen = new Set<number>();
    return messages.reduce<any[]>((result, item) => {
      if (typeof item.sender_id !== 'number' || seen.has(item.sender_id)) return result;
      seen.add(item.sender_id);
      result.push({
        user_id: item.sender_id,
        username: item.sender_name,
        avatar: item.sender_avatar,
      });
      return result;
    }, []);
  }, [members, messages]);

  const showMemberFilter = canFilterByMember || memberOptions.length > 0;

  useEffect(() => {
    if (!showMemberFilter && activeTab === 'member') setActiveTab('all');
  }, [activeTab, showMemberFilter]);

  const groupedMembers = useMemo(() => {
    const text = memberKeyword.trim().toLowerCase();
    const source = text
      ? memberOptions.filter((item) => getMemberName(item).toLowerCase().includes(text))
      : memberOptions;
    const grouped = new Map<string, any[]>();
    source.forEach((item) => {
      const letter = getLetter(getMemberName(item));
      grouped.set(letter, [...(grouped.get(letter) || []), item]);
    });
    return Array.from(grouped.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [memberOptions, memberKeyword]);

  const selectedMember = memberOptions.find((item) => getMemberId(item) === selectedSender);
  const memberSearchPlaceholder = conversationType === 'private' ? '搜索成员' : '搜索群成员';
  const emptyMemberText = conversationType === 'private' ? '暂无成员' : '暂无群成员';

  const handleJumpToMessage = (msgId: number) => {
    router.push(`/?conversation_id=${conversationIdValue}&scroll_to=${msgId}`);
  };

  const resetFilters = () => {
    setTimeRange(undefined);
    setSelectedSender(undefined);
    setActiveTab('all');
    handleSearch({ timeRange: undefined, senderId: undefined });
  };

  return (
    <Layout style={styles.page}>
      <Head><title>聊天记录 - {conversationName}</title></Head>
      <Content style={styles.panel}>
        <div style={styles.header}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => router.back()} />
          <Text ellipsis style={styles.headerTitle}>“{conversationName}” 的聊天记录</Text>
          <Button type="text" onClick={resetFilters}>重置</Button>
        </div>

        <div style={styles.searchWrap}>
          <Input
            prefix={<SearchOutlined style={{ color: '#8a95a6' }} />}
            placeholder="搜索"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onPressEnter={() => handleSearch()}
            style={styles.searchInput}
          />
        </div>

        <div style={styles.tabs}>
          {[
            { key: 'all', label: '全部' },
            { key: 'date', label: '日期' },
            ...(showMemberFilter ? [{ key: 'member', label: conversationType === 'private' ? '成员' : '群成员' }] : []),
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              style={{ ...styles.tabButton, ...(activeTab === item.key ? styles.activeTab : undefined) }}
              onClick={() => setActiveTab(item.key as 'all' | 'date' | 'member')}
            >
              {item.label}
            </button>
          ))}
          <Button type="primary" size="small" icon={<SearchOutlined />} loading={loading} onClick={() => handleSearch()} style={{ marginLeft: 'auto', borderRadius: 8 }}>
            开始筛选
          </Button>
        </div>

        {activeTab === 'date' && (
          <div style={styles.filterPanel}>
            <Text strong style={{ display: 'block', marginBottom: 10 }}>时间范围（精确到分钟）</Text>
            <DatePicker.RangePicker
              showTime={{ format: 'HH:mm' }}
              format="YYYY-MM-DD HH:mm"
              value={timeRange}
              onChange={(val) => setTimeRange(val)}
              style={{ width: '100%' }}
            />
          </div>
        )}

        {activeTab === 'member' && (
          <div style={styles.filterPanel}>
            <Input
              prefix={<SearchOutlined style={{ color: '#8a95a6' }} />}
              placeholder={memberSearchPlaceholder}
              value={memberKeyword}
              onChange={(event) => setMemberKeyword(event.target.value)}
              style={styles.memberSearch}
            />
            <div style={styles.memberList}>
              {groupedMembers.length > 0 ? groupedMembers.map(([letter, items]) => (
                <div key={letter}>
                  <div style={styles.memberLetter}>{letter}</div>
                  {items.map((item) => {
                    const memberId = getMemberId(item);
                    const selected = memberId === selectedSender;
                    return (
                      <button
                        key={memberId ?? getMemberName(item)}
                        type="button"
                        style={{ ...styles.memberRow, ...(selected ? styles.selectedMemberRow : undefined) }}
                        onClick={() => {
                          const nextSender = selected ? undefined : memberId;
                          setSelectedSender(nextSender);
                          handleSearch({ senderId: nextSender });
                        }}
                        disabled={typeof memberId !== 'number'}
                      >
                        <Avatar size={30} src={item.avatar} icon={<UserOutlined />} />
                        <Text ellipsis style={{ color: '#253143', flex: 1 }}>{getMemberName(item)}</Text>
                        {selected && <CheckOutlined style={{ color: '#07c160' }} />}
                      </button>
                    );
                  })}
                </div>
              )) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyMemberText} />
              )}
            </div>
          </div>
        )}

        {(timeRange || selectedSender) && (
          <div style={{ padding: '10px 20px 0', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {timeRange && (
              <span style={styles.activeFilter}>
                <CalendarOutlined />
                {timeRange[0]?.format('YYYY-MM-DD HH:mm')} - {timeRange[1]?.format('YYYY-MM-DD HH:mm')}
                <CloseCircleFilled onClick={() => setTimeRange(undefined)} style={{ cursor: 'pointer' }} />
              </span>
            )}
            {selectedMember && (
              <span style={styles.activeFilter}>
                <UserOutlined />
                {getMemberName(selectedMember)}
                <CloseCircleFilled
                  onClick={() => {
                    setSelectedSender(undefined);
                    handleSearch({ senderId: undefined });
                  }}
                  style={{ cursor: 'pointer' }}
                />
              </span>
            )}
          </div>
        )}

        <div style={styles.results}>
          <Spin spinning={loading}>
            {filteredMessages.length > 0 ? filteredMessages.map((msg) => (
              <div key={msg.msg_id} style={styles.resultItem} onClick={() => handleJumpToMessage(msg.msg_id)}>
                <Avatar size={36} src={msg.sender_avatar} icon={<UserOutlined />} />
                <div style={styles.resultMeta}>
                  <Text ellipsis style={styles.senderName}>{msg.sender_name}</Text>
                  <Text style={styles.content}>{msg.content}</Text>
                </div>
                <Text style={styles.time}>{formatMessageTime(msg.created_at)}</Text>
              </div>
            )) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无聊天记录" />
            )}
          </Spin>
        </div>
      </Content>
    </Layout>
  );
}
