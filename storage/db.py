"""
SQLite storage for plans, source hits, device profiles, and follow-up state.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


def _default_db_path() -> str:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Zora"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "zora_multi_agent.db")


class ZoraMemoryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get("ZORA_DB_PATH") or _default_db_path()
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Using a plain ``with sqlite3.connect(...)`` only commits on exit — the
        # connection stays open, which on Windows keeps a file handle on zora.db
        # and prevents TemporaryDirectory cleanup. Wrap with an explicit close.
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS device_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    manufacturer TEXT,
                    model TEXT,
                    serial_number TEXT,
                    bios_version TEXT,
                    detected_at TEXT,
                    payload_json TEXT
                );
                CREATE TABLE IF NOT EXISTS oem_tools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor TEXT,
                    name TEXT,
                    status TEXT,
                    path TEXT,
                    executable TEXT,
                    payload_json TEXT
                );
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_id TEXT PRIMARY KEY,
                    message TEXT,
                    route TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    plan_json TEXT
                );
                CREATE TABLE IF NOT EXISTS solution_hits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    title TEXT,
                    url TEXT,
                    officialness TEXT,
                    confidence REAL,
                    chosen INTEGER,
                    payload_json TEXT
                );
                CREATE TABLE IF NOT EXISTS case_records (
                    case_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    status TEXT,
                    ticket_number TEXT,
                    portal_url TEXT,
                    payload_json TEXT
                );
                CREATE TABLE IF NOT EXISTS consent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    step_id TEXT,
                    status TEXT,
                    reason TEXT,
                    created_at TEXT
                );
                """
            )

    def save_profile(self, profile: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM device_profiles")
            conn.execute("DELETE FROM oem_tools")
            conn.execute(
                """
                INSERT INTO device_profiles (manufacturer, model, serial_number, bios_version, detected_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.get("manufacturer", ""),
                    profile.get("model", ""),
                    profile.get("serial_number", ""),
                    profile.get("bios_version", ""),
                    profile.get("detected_at", ""),
                    json.dumps(profile),
                ),
            )
            for tool in profile.get("tools", []):
                conn.execute(
                    """
                    INSERT INTO oem_tools (vendor, name, status, path, executable, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tool.get("vendor", ""),
                        tool.get("name", ""),
                        tool.get("status", ""),
                        tool.get("path", ""),
                        tool.get("executable", ""),
                        json.dumps(tool),
                    ),
                )

    def save_plan(self, task_id: str, message: str, route: str, status: str, created_at: str, plan: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_runs (task_id, message, route, status, created_at, updated_at, plan_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    message=excluded.message,
                    route=excluded.route,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    plan_json=excluded.plan_json
                """,
                (task_id, message, route, status, created_at, created_at, json.dumps(plan)),
            )

            conn.execute("DELETE FROM solution_hits WHERE task_id = ?", (task_id,))
            for index, source in enumerate(plan.get("sources", [])):
                conn.execute(
                    """
                    INSERT INTO solution_hits (task_id, title, url, officialness, confidence, chosen, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        source.get("title", ""),
                        source.get("url", ""),
                        source.get("officialness", ""),
                        float(source.get("confidence", 0.0)),
                        1 if index == 0 else 0,
                        json.dumps(source),
                    ),
                )
            if plan.get("case_record"):
                case = plan["case_record"]
                conn.execute(
                    """
                    INSERT INTO case_records (case_id, task_id, status, ticket_number, portal_url, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(case_id) DO UPDATE SET
                        status=excluded.status,
                        ticket_number=excluded.ticket_number,
                        portal_url=excluded.portal_url,
                        payload_json=excluded.payload_json
                    """,
                    (
                        case.get("case_id", ""),
                        task_id,
                        case.get("status", ""),
                        case.get("ticket_number", ""),
                        case.get("portal_url", ""),
                        json.dumps(case),
                    ),
                )

    def load_plan(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT plan_json FROM task_runs WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            return json.loads(row["plan_json"])

    def record_consent(self, task_id: str, step_id: str, status: str, reason: str, created_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO consent_events (task_id, step_id, status, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, step_id, status, reason, created_at),
            )

    # --- Phase 4b: follow-up scheduler -----------------------------------
    # Follow-ups live inside the case_records.payload_json (not a separate
    # table) because the existing FollowUp dataclass is already persisted
    # through CaseRecord.to_dict. We rehydrate cases as needed rather than
    # duplicating schema.

    def list_open_cases(self) -> list[Dict[str, Any]]:
        """Return every case_record whose status is 'open' or 'draft'."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT case_id, task_id, status, payload_json
                FROM case_records
                WHERE status IN ('open', 'draft')
                ORDER BY case_id DESC
                """,
            ).fetchall()
        cases: list[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            except Exception:
                payload = {}
            payload.setdefault("case_id", row["case_id"])
            payload.setdefault("status", row["status"])
            payload["_task_id"] = row["task_id"]
            cases.append(payload)
        return cases

    def update_case(self, case_id: str, payload: Dict[str, Any]) -> None:
        """Overwrite a case_record payload (used when adding/resolving follow-ups)."""
        status = payload.get("status", "open")
        ticket_number = payload.get("ticket_number", "")
        portal_url = payload.get("portal_url", "")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE case_records
                SET status = ?, ticket_number = ?, portal_url = ?, payload_json = ?
                WHERE case_id = ?
                """,
                (status, ticket_number, portal_url, json.dumps(payload), case_id),
            )

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT case_id, task_id, status, payload_json FROM case_records WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        except Exception:
            payload = {}
        payload.setdefault("case_id", row["case_id"])
        payload.setdefault("status", row["status"])
        payload["_task_id"] = row["task_id"]
        return payload
