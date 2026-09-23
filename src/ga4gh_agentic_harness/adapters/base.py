"""Shared adapter URL and result behavior."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..auth import OutboundCredential
from ..http import HttpResult, SafeHttpClient
from ..models import ServiceDescriptor


class AdapterError(RuntimeError):
    def __init__(self, message: str, result: HttpResult | None = None) -> None:
        super().__init__(message)
        self.result = result


def api_base(service: ServiceDescriptor) -> str:
    value = str(service.service_info_url or service.url).rstrip("/")
    if value.endswith("/service-info"):
        value = value[: -len("/service-info")]
    return value


def segment(value: str) -> str:
    # quote() leaves "." and ".." intact, and URL normalization then resolves them as dot
    # segments: run_id ".." would turn POST .../runs/../cancel into POST .../cancel.
    if value in {"", ".", ".."}:
        raise ValueError(f"identifier {value!r} is not a valid path segment")
    return quote(value, safe="")


def require_json(result: HttpResult) -> Any:
    if not result.ok:
        raise AdapterError(result.error or f"upstream returned HTTP {result.status}", result)
    if result.json is None:
        raise AdapterError("upstream returned a non-JSON response", result)
    return result.json


class BaseAdapter:
    def __init__(self, http: SafeHttpClient) -> None:
        self._http = http

    async def get(
        self,
        service: ServiceDescriptor,
        path: str,
        credential: OutboundCredential,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        result = await self._http.request(
            "GET", api_base(service) + path, credential=credential, params=params
        )
        return require_json(result)

