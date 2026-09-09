"""Transactional application databases with inspectable business tables."""

import json
from vic.store import WorkspaceStore
from vic.business import apply_mutation
from . import domain

TABLES = {
    "objects": "id TEXT PRIMARY KEY, kind TEXT, payload TEXT",
    "messages": "id TEXT PRIMARY KEY,sender TEXT,recipient TEXT,body TEXT,reference TEXT,attachment TEXT",
    "collection_entries": "collection TEXT,ordinal INTEGER,object_id TEXT,PRIMARY KEY(collection,object_id)",
    "memberships": "group_id TEXT,member_id TEXT,PRIMARY KEY(group_id,member_id)",
    "ledger": "transfer_id TEXT,account TEXT,cents INTEGER,counterparty TEXT,PRIMARY KEY(transfer_id,account)",
    "balances": "account TEXT PRIMARY KEY,cents INTEGER CHECK(cents>=0)",
    "domain_values": "name TEXT PRIMARY KEY,value TEXT",
}


class ApplicationStore(WorkspaceStore):
    def connect(self, run_id):
        return super().connect(run_id)

    def _schema(self, db):
        for name, columns in TABLES.items():
            db.execute(f"CREATE TABLE IF NOT EXISTS {name} ({columns})")

    def _write(self, db, state):
        self._schema(db)
        base = {k: v for k, v in state.items() if k != "domain"}
        db.execute("INSERT OR REPLACE INTO state VALUES (1,?)", (json.dumps(base),))
        for name in TABLES:
            db.execute(f"DELETE FROM {name}")
        d = state.get("domain")
        if d is None:
            return
        db.executemany(
            "INSERT INTO objects VALUES (?,?,?)",
            [(k, v["kind"], json.dumps(v)) for k, v in d["objects"].items()],
        )
        db.executemany(
            "INSERT INTO messages VALUES (?,?,?,?,?,?)",
            [
                (
                    m["id"],
                    m["sender"],
                    m["recipient"],
                    m["body"],
                    m["reference"],
                    m["attachment"],
                )
                for m in d["messages"]
            ],
        )
        db.executemany(
            "INSERT INTO collection_entries VALUES (?,?,?)",
            [
                (name, i, obj)
                for name, objects in d["collections"].items()
                for i, obj in enumerate(objects)
            ],
        )
        db.executemany(
            "INSERT INTO memberships VALUES (?,?)",
            [
                (name, obj)
                for name, objects in d["memberships"].items()
                for obj in objects
            ],
        )
        db.executemany(
            "INSERT INTO ledger VALUES (?,?,?,?)",
            [
                (x["transfer"], x["account"], x["cents"], x["counterparty"])
                for x in d["ledger"]
            ],
        )
        db.executemany("INSERT INTO balances VALUES (?,?)", list(d["balances"].items()))
        values = {
            k: v
            for k, v in d.items()
            if k
            not in (
                "objects",
                "messages",
                "collections",
                "memberships",
                "ledger",
                "balances",
            )
        }
        values["collection_names"] = list(d["collections"])
        db.executemany(
            "INSERT INTO domain_values VALUES (?,?)",
            [(k, json.dumps(v)) for k, v in values.items()],
        )

    def _read(self, db):
        row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
        if not row:
            raise ValueError("Application not initialized")
        state = json.loads(row[0])
        if state["task_id"] >= 66:
            return state
        d = {
            name: json.loads(value)
            for name, value in db.execute("SELECT name,value FROM domain_values")
        }
        d["objects"] = {
            id_: json.loads(body)
            for id_, body in db.execute("SELECT id,payload FROM objects ORDER BY id")
        }
        d["messages"] = [
            dict(
                zip(
                    ["id", "sender", "recipient", "body", "reference", "attachment"],
                    row,
                )
            )
            for row in db.execute("SELECT * FROM messages ORDER BY rowid")
        ]
        d["collections"] = {name: [] for name in d.pop("collection_names")}
        for name, _, obj in db.execute(
            "SELECT * FROM collection_entries ORDER BY collection,ordinal"
        ):
            d["collections"][name].append(obj)
        d["memberships"] = {}
        for name, obj in db.execute("SELECT * FROM memberships ORDER BY rowid"):
            d["memberships"].setdefault(name, []).append(obj)
        d["ledger"] = [
            dict(zip(["transfer", "account", "cents", "counterparty"], row))
            for row in db.execute("SELECT * FROM ledger ORDER BY rowid")
        ]
        d["balances"] = dict(db.execute("SELECT account,cents FROM balances"))
        state["domain"] = d
        return state

    def initialize(self, run_id, state):
        with self.connect(run_id) as db:
            self._write(db, state)
            db.execute("DELETE FROM events")

    def snapshot(self, run_id):
        with self.connect(run_id) as db:
            return self._read(db)

    def mutate(self, run_id, mutation):
        body = mutation.model_dump()
        with self.connect(run_id) as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT body FROM events WHERE action_id=?", (mutation.action_id,)
            ).fetchone()
            if prior:
                if json.loads(prior[0]) != body:
                    raise ValueError("Action id collision")
                return self._read(db)
            state = self._read(db)
            state = apply_mutation(
                state, mutation.op, mutation.target, mutation.value, mutation.ids
            )
            if state["task_id"] < 66:
                state = domain.apply(
                    state, mutation.op, mutation.target, mutation.value, mutation.ids
                )
            self._write(db, state)
            db.execute(
                "INSERT INTO events(action_id,body) VALUES (?,?)",
                (mutation.action_id, json.dumps(body)),
            )
            return state
