"""SQLite persistence. One row per scan holds the data, the issues and the audit log as JSON."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Iterator

from .models import Dataset, Issue

DB_PATH = os.environ.get("DB_PATH", "data/ledger_checkup.db")


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS scans (
            id TEXT PRIMARY KEY, name TEXT, created_at TEXT,
            dataset TEXT, issues TEXT, audit TEXT, chat TEXT)""")


class Scan:
    def __init__(self, id: str, name: str, created_at: str, dataset: Dataset, issues: list[Issue],
                 audit: list[dict], chat: list[dict]):
        self.id, self.name, self.created_at = id, name, created_at
        self.dataset, self.issues, self.audit, self.chat = dataset, issues, audit, chat

    def issue(self, issue_id: str) -> Issue | None:
        return next((i for i in self.issues if i.id == issue_id), None)


def create(name: str, created_at: str, dataset: Dataset, issues: list[Issue]) -> Scan:
    scan = Scan(uuid.uuid4().hex[:12], name, created_at, dataset, issues, [], [])
    save(scan)
    return scan


def save(scan: Scan) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO scans VALUES (?,?,?,?,?,?,?)", (
            scan.id, scan.name, scan.created_at, json.dumps(scan.dataset.to_dict()),
            json.dumps([i.to_dict() for i in scan.issues]), json.dumps(scan.audit), json.dumps(scan.chat)))


def get(scan_id: str) -> Scan | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if not row:
        return None
    return Scan(row["id"], row["name"], row["created_at"], Dataset.from_dict(json.loads(row["dataset"])),
                [Issue.from_dict(i) for i in json.loads(row["issues"])],
                json.loads(row["audit"]), json.loads(row["chat"]))


def list_scans() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT id, name, created_at, issues FROM scans ORDER BY created_at DESC").fetchall()
    return [{"id": r["id"], "name": r["name"], "created_at": r["created_at"],
             "open_issues": sum(1 for i in json.loads(r["issues"]) if i["status"] == "open")} for r in rows]


def delete(scan_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
