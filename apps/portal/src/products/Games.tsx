import { useEffect, useState } from "react";
import { Frame, PageHead, Notice, type ProductAPI } from "./kit";
export function Games({ api }: { api: ProductAPI }) {
  const { s } = api,
    [page, setPage] = useState("home"),
    [focus, setFocus] = useState("");
  const names: Record<string, string> = {
      "2048": "2048",
      reversi: "黑白棋",
      sudoku: "数独",
      mines: "扫雷",
    },
    name = names[s.game];
  const [instructions, setInstructions] = useState(false);
  const point = (r: number, c: number) => `${r},${c}`,
    candidate = (r: number, c: number) =>
      s.candidates.some((p: number[]) => p[0] === r && p[1] === c),
    marked = (r: number, c: number) =>
      s.marks.some((p: number[]) => p[0] === r && p[1] === c);
  useEffect(() => {
    function key(e: KeyboardEvent) {
      const map: Record<string, string> = {
        ArrowLeft: "left",
        ArrowUp: "up",
        ArrowRight: "right",
        ArrowDown: "down",
      };
      if (
        page === "play" &&
        s.game === "2048" &&
        map[e.key] &&
        !s.stopped &&
        !api.busy
      ) {
        e.preventDefault();
        void api.mutate("move", "", map[e.key]);
      }
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [page, s.stopped, api.busy]);
  function click(r: number, c: number) {
    const p = point(r, c);
    if ([70, 73].includes(s.task_id)) void api.mutate("mark", p);
    else if (s.task_id === 71) setFocus(p);
    else void api.mutate("choose", p);
  }
  return (
    <Frame
      brand="方寸游戏"
      accent="#566a53"
      page={page}
      navigate={setPage}
      tabs={[
        ["home", "游戏大厅"],
        ["play", "继续练习"],
      ]}
    >
      <main className={`product-main games-main game-${s.game}`}>
        <Notice api={api} />
        {page === "home" ? (
          <>
            <PageHead
              eyebrow="A LITTLE ROOM TO THINK"
              title="留一点时间，专注下一步。"
              description="经典棋盘与益智游戏，一个安静的练习空间。"
            />
            <section className="games-feature">
              <div className={`games-preview preview-${s.game}`}>
                {s.game === "2048" ? (
                  <>
                    <span>2</span>
                    <span>4</span>
                    <span>8</span>
                    <span>16</span>
                  </>
                ) : s.game === "reversi" ? (
                  <>
                    <span>●</span>
                    <span>○</span>
                    <span>○</span>
                    <span>●</span>
                  </>
                ) : s.game === "sudoku" ? (
                  <>
                    <span>1</span>
                    <span>3</span>
                    <span>2</span>
                    <span>4</span>
                  </>
                ) : (
                  <>
                    <span>1</span>
                    <span>⚑</span>
                    <span>2</span>
                    <span>·</span>
                  </>
                )}
              </div>
              <div>
                <span className="product-eyebrow">本次练习</span>
                <h1>{name}</h1>
                <p>
                  {s.game === "2048"
                    ? "移动数字方块，观察每一步的合并结果。"
                    : s.game === "reversi"
                      ? "观察棋盘局势，计算每个落点的翻转。"
                      : s.game === "sudoku"
                        ? "观察行、列与宫，寻找下一个可以确定的数字。"
                        : "根据已揭示的数字，判断相邻格子的状态。"}
                </p>
                <button
                  className="product-primary"
                  onClick={() => setPage("play")}
                >
                  打开练习棋盘 →
                </button>
              </div>
            </section>
            <section className="games-help">
              <h2>开始前</h2>
              <p>
                打开练习后查看完整棋盘。虚线框标出可操作位置，操作结果会自动保存。
              </p>
              <button onClick={() => setInstructions(!instructions)}>
                {instructions ? "收起操作说明" : "查看操作说明"}
              </button>
              {instructions && (
                <p>
                  2048
                  可使用键盘方向键或屏幕方向按钮。数独先选中格子，再点击候选数字；扫雷与黑白棋直接点击候选位置。
                </p>
              )}
            </section>
          </>
        ) : (
          <>
            <button className="product-back" onClick={() => setPage("home")}>
              ← 游戏大厅
            </button>
            <PageHead
              eyebrow="PRACTICE"
              title={name}
              description="练习棋盘 · 操作自动保存"
            />
            <div className="games-layout">
              <div
                className={`games-board board-${s.game}`}
                style={{ gridTemplateColumns: `repeat(${s.board.length},1fr)` }}
              >
                {s.board.map((row: any[], r: number) =>
                  row.map((cell: any, c: number) => (
                    <button
                      key={point(r, c)}
                      aria-label={`第${r + 1}行第${c + 1}列`}
                      className={`game-square tile-${cell || 0} ${candidate(r, c) ? "candidate" : ""} ${marked(r, c) ? "marked" : ""} ${focus === point(r, c) ? "focused" : ""}`}
                      disabled={
                        api.busy ||
                        s.stopped ||
                        s.game === "2048" ||
                        !candidate(r, c)
                      }
                      onClick={() => click(r, c)}
                    >
                      {s.game === "reversi" ? (
                        cell ? (
                          <span
                            className={
                              cell === 1 ? "stone black" : "stone white"
                            }
                          />
                        ) : marked(r, c) ? (
                          "●"
                        ) : (
                          ""
                        )
                      ) : s.game === "mines" ? (
                        marked(r, c) ? (
                          "⚑"
                        ) : (
                          (cell ?? "")
                        )
                      ) : (
                        cell || ""
                      )}
                      {s.game === "sudoku" && !cell && candidate(r, c) && (
                        <small>
                          {s.candidate_values[point(r, c)].join(" ")}
                        </small>
                      )}
                    </button>
                  )),
                )}
              </div>
              <aside className="games-controls">
                <h2>本局状态</h2>
                {s.game === "2048" ? (
                  <>
                    <div className="games-score">
                      <small>得分</small>
                      <b>{s.score}</b>
                    </div>
                    {s.task_id === 69 && (
                      <p>
                        目标数字 {s.target_number} · 目标分数 {s.target_score}
                      </p>
                    )}
                    <div className="games-directions">
                      {[
                        ["up", "↑"],
                        ["left", "←"],
                        ["down", "↓"],
                        ["right", "→"],
                      ].map(([v, icon]) => (
                        <button
                          key={v}
                          aria-label={v}
                          disabled={api.busy || s.stopped}
                          onClick={() => api.mutate("move", "", v)}
                        >
                          {icon}
                        </button>
                      ))}
                    </div>
                    <p>已移动 {s.moves.length} 步</p>
                    {s.task_id === 69 && (
                      <button
                        className="product-primary"
                        disabled={api.busy || s.stopped}
                        onClick={() => api.mutate("stop")}
                      >
                        {s.stopped ? "已结束练习" : "结束练习"}
                      </button>
                    )}
                  </>
                ) : s.task_id === 71 ? (
                  <>
                    <p>{focus ? "为选中的格子填入数字" : "点击一个候选格子"}</p>
                    <div className="games-numbers">
                      {(s.candidate_values[focus] || []).map((v: number) => (
                        <button
                          key={v}
                          disabled={api.busy}
                          onClick={() => api.mutate("fill", focus, String(v))}
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <>
                    <p>
                      {[70, 73].includes(s.task_id)
                        ? `已标记 ${s.marks.length} 个位置`
                        : "点击棋盘中的候选位置。"}
                    </p>
                    {s.selection !== null && (
                      <p className="product-ok">✓ 选择已保存</p>
                    )}
                  </>
                )}
                <hr />
                <p className="product-muted">
                  棋盘并列位置按行、列顺序；方向并列按左、上、右、下顺序。
                </p>
              </aside>
            </div>
          </>
        )}
      </main>
    </Frame>
  );
}
