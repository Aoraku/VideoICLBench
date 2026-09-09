"""Each workspace owns an independent SQLite file and durable event sequence."""

import contextlib
import json
import sqlite3
from pathlib import Path
from .business import apply_mutation


class WorkspaceStore:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def connect(self, run_id):
        path = self.directory / run_id / "app.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=30) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT UNIQUE, body TEXT NOT NULL)"
            )
            yield db

    def initialize(self, run_id, state):
        with self.connect(run_id) as db:
            db.execute(
                "INSERT OR REPLACE INTO state VALUES (1,?)", (json.dumps(state),)
            )
            db.execute("DELETE FROM events")

    def snapshot(self, run_id):
        with self.connect(run_id) as db:
            row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
            if not row:
                raise ValueError("Workspace has not been initialized")
            return json.loads(row[0])

    def events(self, run_id):
        with self.connect(run_id) as db:
            return [
                dict(seq=seq, **json.loads(body))
                for seq, body in db.execute("SELECT seq,body FROM events ORDER BY seq")
            ]

    def mutate(self, run_id, mutation):
        body = mutation.model_dump()
        with self.connect(run_id) as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT body FROM events WHERE action_id=?", (mutation.action_id,)
            ).fetchone()
            if prior:
                if json.loads(prior[0]) != body:
                    raise ValueError("Action ID was reused with different content")
                return json.loads(
                    db.execute("SELECT body FROM state WHERE id=1").fetchone()[0]
                )
            state = json.loads(
                db.execute("SELECT body FROM state WHERE id=1").fetchone()[0]
            )
            state = apply_mutation(
                state, mutation.op, mutation.target, mutation.value, mutation.ids
            )
            db.execute("UPDATE state SET body=? WHERE id=1", (json.dumps(state),))
            db.execute(
                "INSERT INTO events(action_id,body) VALUES (?,?)",
                (mutation.action_id, json.dumps(body)),
            )
            return state
