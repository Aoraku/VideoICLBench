export type Board = (0 | 1)[][];

/**
 * @note 用于前后端交互的 Board 数据格式
 */
export interface BoardMetaData {
    id: number;
    boardName: string;
    createdAt: number;
    userName: string;
}


export interface UserSearchItem {
    user_id: number;
    username: string;
    avatar: string;
}

export interface FriendItem {
    user_id: number;
    username: string;
    avatar: string;
    group: string;
    online: boolean;
}

export interface FriendRequestItem {
    request_id: number;
    from_user: UserSearchItem;
    message: string;
    source: string;
    created_at: number;
}

export interface ConversationItem {
    conversation_id: number;
    type: string;
    name: string;
    avatar: string;
    unread_count: number;
    last_message?: {
        msg_id: number;
        content: string;
        sender_id: number;
        sender_name: string;
        created_at: number;
    };
    is_pinned: boolean;
    is_muted: boolean;
    updated_at: number;
}

export interface MessageItem {
    msg_id: number;
    sender_id: number;
    sender_name: string;
    sender_avatar: string;
    content: string;
    created_at: number;
    reply_to?: any;
    reply_count: number;
}