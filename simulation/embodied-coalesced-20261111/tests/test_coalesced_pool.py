from pathlib import Path
from types import SimpleNamespace
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime-overlay"))
from videoicl_isaaclab.pool_rpc import PoolRPCWorker, atomic_json


def test_ready_room_can_advance_while_peer_waits(tmp_path):
    now = [0.]
    batches = []
    rooms = {room: {"identity": {"run_id": room, "task_id": "E01", "variant": "C",
                                  "seed": 4201, "suite": "test", "epoch": "test"},
                    "fingerprints": {}}
             for room in ("ready", "waiting")}
    controllers = {
        room: SimpleNamespace(steps=0, validate_action=lambda **action: None)
        for room in rooms
    }

    def action_batch(batch):
        batches.append(set(batch))
        for room in batch:
            controllers[room].steps += 1
        return {room: {"step": controllers[room].steps} for room in batch}

    pool = SimpleNamespace(controllers=controllers, supports_partial_actions=True,
                           physics_ticks=0, action_batch=action_batch)
    worker = PoolRPCWorker(pool, tmp_path / "rpc", rooms,
                           lambda room: {"head": f"{room}-{controllers[room].steps}"},
                           barrier_timeout_seconds=5, barrier_policy="wait", coalesce_window_seconds=.05,
                           clock=lambda: now[0])
    request_id = "a" * 32
    atomic_json(worker.root / "requests" / "ready" / (request_id + ".json"), {
        "request_id": request_id, "room_id": "ready", "op": "action",
        "action": {"left": "STILL", "right": "STILL"},
    })
    worker.poll_once()
    assert batches == []
    now[0] = .049
    worker.poll_once()
    assert batches == []
    now[0] = .051
    worker.poll_once()
    assert batches == [{"ready"}]
    assert controllers["waiting"].steps == 0
    reply = worker.root / "responses" / "ready" / (request_id + ".json")
    assert json.loads(reply.read_text())["result"]["receipt"]["step"] == 1
