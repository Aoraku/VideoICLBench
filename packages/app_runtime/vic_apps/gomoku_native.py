"""SDL mouse intents use the same transactional game commands as the API."""

from pathlib import Path
from vic.schemas import Mutation


class GomokuBridge:
    def __init__(self, root, store, metadata):
        self.root, self.store, self.metadata = Path(root), store, metadata
        self.offsets = {}

    def reset(self, run_id):
        """Discard the previous board's input before the next board is readable."""
        self.offsets.pop(run_id, None)
        directory = self.root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "gomoku-intents.txt").write_text("")
        (directory / "gomoku-error.txt").unlink(missing_ok=True)

    def export(self, run_id):
        state = self.store.snapshot(run_id)
        documents=state.get('board_documents',{})
        view=state.get('board_view','board-1')
        if documents:
            from .board_collection import project
            state=project(state,view)
        lines = [f"{state['task_id']} {state['color']} {int(state['selection'] is not None)}"]
        lines.extend(" ".join(map(str, row)) for row in state["board"])
        for key in ("candidates", "marks"):
            lines.append(str(len(state[key])))
            lines.extend(f"{r} {c}" for r, c in state[key])
        lines.append(f"{len(documents)} {list(documents).index(view) if documents else 0}")
        path = self.root / run_id / "gomoku-state.txt"
        temporary = path.with_suffix(".tmp")
        temporary.write_text("\n".join(lines) + "\n")
        temporary.replace(path)

    def drain(self, run_id):
        meta = self.metadata(run_id)
        if meta["app"] != "gomoku" or meta["status"] != "active":
            return
        path = self.root / run_id / "gomoku-intents.txt"
        if not path.exists():
            return
        raw = path.read_text()
        lines = raw.splitlines() if raw.endswith("\n") else raw.splitlines()[:-1]
        start = self.offsets.get(run_id, 0)
        for index, line in enumerate(lines[start:], start):
            try:
                parts=line.split();op,r,c=parts[:3]
                documents=self.store.snapshot(run_id).get('board_documents')
                ids=[];target=f"{int(r)},{int(c)}"
                if documents:
                    if op=='view':op='board.view';target=f'board-{int(r)+1}'
                    elif op in ('mark','choose') and len(parts)==4:
                        ids=[target];target=f'board-{int(parts[3])+1}';op='board.'+op
                    else:raise ValueError('Choose a board document')
                elif op not in ('mark','choose'):raise ValueError('Unknown desktop command')
                self.store.mutate(run_id, Mutation(
                    op=op, target=target, ids=ids, epoch=meta["epoch"],
                    action_id=f"sdl-{meta['epoch']}-{index}",
                ))
            except ValueError as exc:
                (self.root / run_id / "gomoku-error.txt").write_text(str(exc))
            self.offsets[run_id] = index + 1
        if len(lines) > start:
            self.export(run_id)
