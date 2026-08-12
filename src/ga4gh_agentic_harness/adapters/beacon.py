"""Beacon v2 variant query adapter."""

from __future__ import annotations

from typing import Any

from ..auth import OutboundCredential
from ..models import ServiceDescriptor
from .base import BaseAdapter, require_json, segment


class BeaconAdapter(BaseAdapter):
    async def query_variant(
        self,
        service: ServiceDescriptor,
        query: dict[str, Any],
        credential: OutboundCredential,
        *,
        entry_type: str = "g_variants",
    ) -> dict[str, Any]:
        # Beacon permits both query-parameter GETs and request-entity POSTs. A flat mapping is
        # the portable GET form used by several public Beacons; structured request entities use
        # POST so their nested shape is preserved.
        structured = "query" in query or "meta" in query
        result = await self._http.request(
            "POST" if structured else "GET",
            str(service.url).rstrip("/") + f"/{segment(entry_type)}",
            credential=credential,
            json_body=query if structured else None,
            params=None if structured else query,
        )
        data = require_json(result)
        if not isinstance(data, dict):
            raise ValueError("Beacon response must be an object")
        return data
