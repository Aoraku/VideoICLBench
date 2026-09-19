"""SDL mouse intents use the same transactional game commands as the API."""

from pathlib import Path
from vic.schemas import Mutation


class GomokuBridge:
    def __init__(self, root, store, metadata):
        self.root, self.store, self.metadata = Path(root), store, metadata
        self.offsets = {}

    def export(self, run_id):
        state = self.store.snapshot(run_id)
        lines = [f"{state['task_id']} {state['color']} {int(state['selection'] is not None)}"]
        lines.extend(" ".join(map(str, row)) for row in state["board"])
        for key in ("candidates", "marks"):
            lines.append(str(len(state[key])))
            lines.extend(f"{r} {c}" for r, c in state[key])
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
                op, r, c = line.split()
                if op not in ("mark", "choose"):
                    raise ValueError("Unknown desktop command")
                self.store.mutate(run_id, Mutation(
                    op=op, target=f"{int(r)},{int(c)}", epoch=meta["epoch"],
                    action_id=f"sdl-{meta['epoch']}-{index}",
                ))
            except ValueError as exc:
                (self.root / run_id / "gomoku-error.txt").write_text(str(exc))
            self.offsets[run_id] = index + 1
        if len(lines) > start:
            self.export(run_id)
