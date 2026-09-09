const now = new Date().toISOString()

export const mockSearchUsers = {
  total: 3,
  page: 1,
  page_size: 20,
  results: [
    {
      user_id: 1002,
      username: 'bob',
      avatar: '',
      status: { presence: 'online', status_text: '', status_emoji: '' },
    },
    {
      user_id: 1003,
      username: 'charlie',
      avatar: '',
      status: { presence: 'busy', status_text: '', status_emoji: '' },
    },
    {
      user_id: 1004,
      username: 'diana',
      avatar: '',
      status: { presence: 'offline', status_text: '', status_emoji: '' },
    },
  ],
}

export const mockUserProfiles = {
  1002: {
    user_id: 1002,
    username: 'bob',
    avatar: '',
    status: { presence: 'online', status_text: '', status_emoji: '' },
    is_friend: true,
    is_blocked: false,
    remark: 'Bob同学',
    created_at: now,
  },
  1003: {
    user_id: 1003,
    username: 'charlie',
    avatar: '',
    status: { presence: 'busy', status_text: '', status_emoji: '' },
    is_friend: false,
    is_blocked: false,
    remark: null,
    created_at: now,
  },
  1004: {
    user_id: 1004,
    username: 'diana',
    avatar: '',
    status: { presence: 'offline', status_text: '', status_emoji: '' },
    is_friend: false,
    is_blocked: false,
    remark: null,
    created_at: now,
  },
  1005: {
    user_id: 1005,
    username: 'eve',
    avatar: '',
    status: { presence: 'offline', status_text: '', status_emoji: '' },
    is_friend: true,
    is_blocked: false,
    remark: null,
    created_at: now,
  },
}

export const mockFriendRequests = {
  received: {
    total: 1,
    page: 1,
    page_size: 20,
    results: [
      {
        request_id: 5002,
        from_user: { user_id: 1003, username: 'charlie', avatar: '' },
        message: '你好，我是项目组同学',
        source: 'search',
        status: 'pending',
        created_at: now,
      },
    ],
  },
  sent: {
    total: 1,
    page: 1,
    page_size: 20,
    results: [
      {
        request_id: 5003,
        from_user: { user_id: 1001, username: 'alice', avatar: '' },
        to_user: { user_id: 1004, username: 'diana', avatar: '' },
        message: '加个好友吧',
        source: 'search',
        status: 'pending',
        created_at: now,
      },
    ],
  },
}

export const mockFriends = {
  total: 2,
  page: 1,
  page_size: 50,
  results: [
    {
      user_id: 1002,
      username: 'bob',
      avatar: '',
      remark: 'Bob同学',
      status: { presence: 'online', status_text: 'Working', status_emoji: '💻' },
      group_id: 101,
      group_name: '同事',
      is_blocked: false,
      added_at: now,
    },
    {
      user_id: 1005,
      username: 'eve',
      avatar: '',
      remark: null,
      status: { presence: 'offline', status_text: '', status_emoji: '' },
      group_id: null,
      group_name: '未分组',
      is_blocked: false,
      added_at: now,
    },
  ],
}

export const mockGroups = {
  groups: [
    { group_id: null, name: '未分组', friend_count: 1 },
    { group_id: 101, name: '同事', friend_count: 1 },
    { group_id: 102, name: '同学', friend_count: 0 },
  ],
}

/** 会话列表 mock（通讯录「群聊」仅用 type=group 项） */
export const mockConversations = {
  total: 2,
  page: 1,
  page_size: 30,
  results: [
    {
      conversation_id: 2002,
      type: 'group',
      name: '项目讨论组',
      avatar: null,
      peer_user: null,
      last_message: {
        msg_id: 9050,
        sender_id: 1003,
        sender_name: 'charlie',
        type: 'text',
        content: { text: '明天下午开会' },
        created_at: now,
      },
      unread_count: 0,
      is_pinned: true,
      is_muted: false,
      updated_at: now,
    },
    {
      conversation_id: 2001,
      type: 'private',
      name: null,
      avatar: null,
      peer_user: {
        user_id: 1002,
        username: 'bob',
        remark: 'Bob同学',
        avatar: '',
        status: { presence: 'online', status_text: '', status_emoji: '' },
      },
      last_message: null,
      unread_count: 0,
      is_pinned: false,
      is_muted: false,
      updated_at: now,
    },
  ],
}
