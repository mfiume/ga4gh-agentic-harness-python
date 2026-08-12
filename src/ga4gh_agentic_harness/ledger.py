"""SQLite-backed local workflow run ledger for restart-safe reconciliation."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class WorkflowRunRecord(BaseModel):
    local_run_id: str
    service_id: str
    authority_key: str
    request_id: str
    idempotency_key: str
    state: str
    remote_run_id: str | None = None
    details: dict[str, Any]
    created_at: str
    updated_at: str


class WorkflowRunLedger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    local_run_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    authority_key TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    remote_run_id TEXT,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(service_id, authority_key, idempotency_key)
                )
                """
            )

    async def create_submission(
        self,
        *,
        service_id: str,
        authority_key: str,
        request_id: str,
        idempotency_key: str,
        details: dict[str, Any] | None = None,
    ) -> tuple[WorkflowRunRecord, bool]:
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(
                self._create_sync,
                service_id,
                authority_key,
                request_id,
                idempotency_key,
                details or {},
            )

    def _create_sync(
        self,
        service_id: str,
        authority_key: str,
        request_id: str,
        idempotency_key: str,
        details: dict[str, Any],
    ) -> tuple[WorkflowRunRecord, bool]:
        now = datetime.now(timezone.utc).isoformat()
        local_run_id = str(uuid.uuid4())
        with self._connect() as connection:
            existing = connection.execute(
                """SELECT * FROM workflow_runs
                   WHERE service_id = ? AND authority_key = ? AND idempotency_key = ?""",
                (service_id, authority_key, idempotency_key),
            ).fetchone()
            if existing:
                return self._record(existing), False
            connection.execute(
                """
                INSERT INTO workflow_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    local_run_id,
                    service_id,
                    authority_key,
                    request_id,
                    idempotency_key,
                    "submitting",
                    None,
                    json.dumps(details, sort_keys=True),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE local_run_id = ?", (local_run_id,)
            ).fetchone()
            assert row is not None
            return self._record(row), True

    async def update(
        self,
        local_run_id: str,
        *,
        state: str,
        remote_run_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> WorkflowRunRecord:
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(
                self._update_sync, local_run_id, state, remote_run_id, details
            )

    def _update_sync(
        self,
        local_run_id: str,
        state: str,
        remote_run_id: str | None,
        details: dict[str, Any] | None,
    ) -> WorkflowRunRecord:
        with self._connect() as connection:
            current = connection.execute(
                "SELECT * FROM workflow_runs WHERE local_run_id = ?", (local_run_id,)
            ).fetchone()
            if not current:
                raise KeyError(local_run_id)
            merged = json.loads(current["details_json"])
            merged.update(details or {})
            remote = remote_run_id if remote_run_id is not None else current["remote_run_id"]
            connection.execute(
                """
                UPDATE workflow_runs
                SET state = ?, remote_run_id = ?, details_json = ?, updated_at = ?
                WHERE local_run_id = ?
                """,
                (
                    state,
                    remote,
                    json.dumps(merged, sort_keys=True),
                    datetime.now(timezone.utc).isoformat(),
                    local_run_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE local_run_id = ?", (local_run_id,)
            ).fetchone()
            assert row is not None
            return self._record(row)

    async def get(self, local_run_id: str) -> WorkflowRunRecord:
        await self.initialize()
        async with self._lock:
            record = await asyncio.to_thread(self._get_sync, local_run_id)
        if record is None:
            raise KeyError(local_run_id)
        return record

    def _get_sync(self, local_run_id: str) -> WorkflowRunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE local_run_id = ?", (local_run_id,)
            ).fetchone()
            return self._record(row) if row else None

    @staticmethod
    def _record(row: sqlite3.Row) -> WorkflowRunRecord:
        return WorkflowRunRecord(
            local_run_id=row["local_run_id"],
            service_id=row["service_id"],
            authority_key=row["authority_key"],
            request_id=row["request_id"],
            idempotency_key=row["idempotency_key"],
            state=row["state"],
            remote_run_id=row["remote_run_id"],
            details=json.loads(row["details_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
