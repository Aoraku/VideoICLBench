import type { CSSProperties } from "react";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import { DELETE_SUCCESS, FAILURE_PREFIX } from "../constants/string";
import { request } from "../utils/network";
import { BoardMetaData } from "../utils/types";

const styles: Record<string, CSSProperties> = {
    page: {
        minHeight: "calc(100vh - 24px)",
        padding: 28,
        background: "linear-gradient(135deg, #f6fbff 0%, #eef5ff 48%, #dff2ff 100%)",
    },
    shell: {
        width: "min(1120px, 94vw)",
        minHeight: 640,
        margin: "0 auto",
        display: "grid",
        gridTemplateColumns: "280px 1fr",
        overflow: "hidden",
        borderRadius: 28,
        background: "rgba(255, 255, 255, 0.84)",
        border: "1px solid rgba(255, 255, 255, 0.88)",
        boxShadow: "0 28px 72px rgba(38, 125, 208, 0.15)",
    },
    side: {
        padding: 34,
        color: "#ffffff",
        background: "linear-gradient(180deg, #18afff 0%, #078cf0 100%)",
    },
    sideTitle: {
        margin: 0,
        fontSize: 34,
        lineHeight: 1.18,
        letterSpacing: 0,
    },
    sideText: {
        display: "block",
        marginTop: 12,
        color: "rgba(255, 255, 255, 0.82)",
        lineHeight: 1.7,
    },
    metric: {
        marginTop: 32,
        padding: 18,
        borderRadius: 20,
        background: "rgba(255, 255, 255, 0.18)",
        boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.22)",
    },
    metricValue: {
        display: "block",
        fontSize: 34,
        fontWeight: 700,
    },
    main: {
        padding: "34px 38px",
        background: "#ffffff",
    },
    toolbar: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        marginBottom: 24,
    },
    title: {
        margin: 0,
        color: "#172033",
        fontSize: 26,
    },
    subtitle: {
        marginTop: 6,
        color: "#73839a",
    },
    buttonRow: {
        display: "flex",
        gap: 10,
        flexWrap: "wrap",
    },
    button: {
        height: 38,
        padding: "0 16px",
        border: "1px solid #d4e4f5",
        borderRadius: 13,
        color: "#2377c7",
        background: "#f5faff",
        cursor: "pointer",
    },
    primaryButton: {
        color: "#ffffff",
        border: "none",
        background: "linear-gradient(135deg, #22b7ff, #0a8cff)",
        boxShadow: "0 10px 22px rgba(10, 140, 255, 0.18)",
    },
    dangerButton: {
        color: "#ff4d4f",
        borderColor: "#ffd6d8",
        background: "#fff7f7",
    },
    list: {
        display: "grid",
        gap: 14,
    },
    card: {
        padding: 18,
        borderRadius: 20,
        background: "#f7fbff",
        border: "1px solid #edf4fb",
    },
    cardHeader: {
        display: "flex",
        justifyContent: "space-between",
        gap: 16,
        marginBottom: 10,
    },
    boardName: {
        margin: 0,
        color: "#172033",
        fontSize: 18,
    },
    meta: {
        color: "#697586",
        fontSize: 13,
        lineHeight: 1.8,
    },
    empty: {
        padding: "90px 24px",
        textAlign: "center",
        color: "#7b8ba1",
        borderRadius: 24,
        background: "#f7fbff",
    },
    loading: {
        minHeight: "calc(100vh - 24px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#2377c7",
        background: "linear-gradient(135deg, #f6fbff 0%, #eef5ff 48%, #dff2ff 100%)",
    },
};

const ListScreen = () => {
    /**
     * @todo [Step 5] 请在下述一处代码缺失部分填写合适的代码，完成游戏记录列表页面 UI
     * @todo [Step 6] 请在下述一处代码缺失部分填写合适的代码，完成网络请求的管理
     */
    const [refreshing, setRefreshing] = useState(true);
    const [selectedUserName, setSelectedUserName] = useState<string | undefined>(undefined);
    const [boardList, setBoardList] = useState<BoardMetaData[]>([]);

    const router = useRouter();
    const query = router.query;

    useEffect(() => {
        if (!router.isReady) {
            return;
        }

        const name = router.query.name ? String(router.query.name) : undefined;
        setSelectedUserName(name);
        fetchList(name);
    }, [router, query]);

    const fetchList = (name?: string) => {
        setRefreshing(true);
        request(name ? `/api/user/${encodeURIComponent(name)}` : "/api/boards", "GET", false)
            .then((res) => setBoardList(res.boards))
            .catch((err) => alert(FAILURE_PREFIX + err))
            .finally(() => setRefreshing(false));
    };

    const deleteBoard = (id: number) => {
        // Step 6 BEGIN
        request(`/api/boards/${id}`, "DELETE", true)
            .then(() => {
                alert(DELETE_SUCCESS);
                // refresh the list after deletion
                fetchList(selectedUserName);
            })
            .catch((err) => {
                // if the user isn't logged in, redirect to login page
                // reuse logic from other pages if needed
                alert(FAILURE_PREFIX + err);
            });
        // Step 6 END
    };

    if (refreshing) {
        return <div style={styles.loading}>Loading records...</div>;
    }

    return (
        <div style={styles.page}>
            <div style={styles.shell}>
                <aside style={styles.side}>
                    <h1 style={styles.sideTitle}>Board Records</h1>
                    <span style={styles.sideText}>
                        浏览、打开和管理已经保存的记录。
                    </span>
                    <div style={styles.metric}>
                        <span style={styles.metricValue}>{boardList.length}</span>
                        <span>当前列表记录</span>
                    </div>
                </aside>

                <main style={styles.main}>
                    <div style={styles.toolbar}>
                        <div>
                            <h2 style={styles.title}>
                                {selectedUserName !== undefined ? `Boards of ${selectedUserName}` : "All Boards"}
                            </h2>
                            <div style={styles.subtitle}>按记录选择、删除或查看用户列表。</div>
                        </div>
                        <div style={styles.buttonRow}>
                            <button style={{ ...styles.button, ...styles.primaryButton }} onClick={() => router.push("/")}>
                                Go back
                            </button>
                            {selectedUserName !== undefined && (
                                <button style={styles.button} onClick={() => router.push("/list")}>
                                    Full list
                                </button>
                            )}
                        </div>
                    </div>

                    {boardList.length === 0 ? (
                        <div style={styles.empty}>Empty list.</div>
                    ) : (
                        <div style={styles.list}>
                            {boardList.map((board) => (
                                <section key={board.id} style={styles.card}>
                                    <div style={styles.cardHeader}>
                                        <h3 style={styles.boardName}>{board.boardName}</h3>
                                        <span style={styles.meta}>{`#${board.id}`}</span>
                                    </div>
                                    <div style={styles.meta}>{`Created by: ${board.userName}`}</div>
                                    <div style={styles.meta}>
                                        {`Created at: ${new Date(board.createdAt * 1000).toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" })}`}
                                    </div>
                                    <div style={{ ...styles.buttonRow, marginTop: 14 }}>
                                        <button style={{ ...styles.button, ...styles.primaryButton }} onClick={() => router.push(`/?id=${board.id}`)}>
                                            Play it
                                        </button>
                                        <button style={styles.button} onClick={() => router.push(`/list?name=${encodeURIComponent(board.userName)}`)}>
                                            View user
                                        </button>
                                        <button style={{ ...styles.button, ...styles.dangerButton }} onClick={() => deleteBoard(board.id)}>
                                            Delete it
                                        </button>
                                    </div>
                                </section>
                            ))}
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
};

export default ListScreen;
