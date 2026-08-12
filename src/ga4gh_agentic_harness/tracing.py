"""Structured, secret-free trace events and sinks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from .auth import AuthorityContext
from .models import Operation, ResultStatus

_SECRET_KEYS = {
    "access_token",
    "authorization",
    "client_secret",
    "cookie",
    "refresh_token",
    "token",
}


def _assert_secret_free(value: Any, path: str = "metadata") -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in _SECRET_KEYS:
                raise ValueError(f"secret-bearing field is prohibited in traces: {path}.{key}")
            _assert_secret_free(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_secret_free(item, f"{path}[{index}]")
    return value


class TraceEvent(BaseModel):
    trace_id: str
    request_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    phase: str
    operation: Operation
    authority: AuthorityContext
    service_id: str | None = None
    target_origin: str | None = None
    policy_decision: str | None = None
    status: ResultStatus | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        _assert_secret_free(value)
        return value


class TraceSink(Protocol):
    async def emit(self, event: TraceEvent) -> None:
        """Persist one structured trace event."""


class NullTraceSink:
    async def emit(self, event: TraceEvent) -> None:
        del event


class MemoryTraceSink:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def emit(self, event: TraceEvent) -> None:
        self.events.append(event)


class JsonLinesTraceSink:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def emit(self, event: TraceEvent) -> None:
        line = event.model_dump_json(exclude_none=True) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)
