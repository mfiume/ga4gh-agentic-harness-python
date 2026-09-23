"""Data Repository Service adapter."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..auth import OutboundCredential
from ..models import ServiceDescriptor
from .base import BaseAdapter, api_base, require_json, segment


class DrsAdapter(BaseAdapter):
    async def resolve_object(
        self,
        service: ServiceDescriptor,
        object_id: str,
        credential: OutboundCredential,
        *,
        expand: bool = False,
    ) -> dict[str, Any]:
        data = await self.get(
            service,
            f"/objects/{segment(object_id)}",
            credential,
            params={"expand": "true"} if expand else None,
        )
        if not isinstance(data, dict):
            raise ValueError("DRS object response must be an object")
        methods = data.get("access_methods")
        if isinstance(methods, list):
            # DRS permits an access_url inline in the object, so the object response carries
            # the same bearer capabilities as the access endpoint.
            data = dict(data)
            data["access_methods"] = [
                dict(method, access_url=_redact_access_url(method["access_url"]))
                if isinstance(method, dict) and isinstance(method.get("access_url"), dict)
                else method
                for method in methods
            ]
        return data

    async def resolve_access(
        self,
        service: ServiceDescriptor,
        object_id: str,
        access_id: str,
        credential: OutboundCredential,
    ) -> dict[str, Any]:
        result = await self._http.request(
            "GET",
            api_base(service) + f"/objects/{segment(object_id)}/access/{segment(access_id)}",
            credential=credential,
        )
        data = require_json(result)
        if not isinstance(data, dict):
            raise ValueError("DRS access response must be an object")
        return _redact_access_url(data)


def _redact_access_url(data: dict[str, Any]) -> dict[str, Any]:
    # Access headers can themselves be bearer capabilities. Keep them in the trusted result
    # only when no values are present; otherwise replace them with a non-secret marker.
    if data.get("headers"):
        data = dict(data)
        data["headers"] = {"redacted": True}
        data["access_headers_available"] = True
    access_url = data.get("url")
    if isinstance(access_url, str) and urlsplit(access_url).query:
        parts = urlsplit(access_url)
        data = dict(data)
        data["url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        data["access_url_query_redacted"] = True
    return data
