"""Small helpers shared by workflow realizations."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

from ..models import ResultEnvelope, ResultStatus


def value(item: Any) -> Any:
    if isinstance(item, Enum):
        return item.value
    return item


def succeeded(result: ResultEnvelope[Any]) -> bool:
    return result.status == ResultStatus.SUCCESS


def data_as_dict(result: ResultEnvelope[Any]) -> dict[str, Any]:
    data = result.data
    if data is None:
        return {}
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json", exclude_none=True)
    return data if isinstance(data, dict) else {}


def first_error_code(result: ResultEnvelope[Any]) -> str:
    if not result.errors:
        return "unknown_error"
    return str(value(result.errors[0].code))


def evidence_ids(result: ResultEnvelope[Any]) -> list[str]:
    output: list[str] = []
    for item in result.evidence:
        if isinstance(item, dict):
            identifier = item.get("id") or item.get("uri") or item.get("digest")
        else:
            identifier = getattr(item, "uri", None) or getattr(item, "digest", None)
        if identifier:
            output.append(str(identifier))
    if not output and result.trace_id:
        output.append(result.trace_id)
    return output
