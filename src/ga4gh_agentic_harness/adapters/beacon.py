"""Beacon variant query adapter for Beacon v1 and v2.

The protocol is chosen from the Beacon version the service declares in its registry record
(``ServiceDescriptor.standard_version``), never by probing the service. v1 answers allele
queries at ``/query``; v2 at ``/{entry_type}``. A service that declares no version keeps the v2
behavior this adapter has always had; one that declares any other major version is refused.
"""

from __future__ import annotations

import re
from typing import Any

from ..auth import OutboundCredential
from ..models import ServiceDescriptor
from .base import BaseAdapter, require_json, segment


class BeaconVersionError(Exception):
    """The declared Beacon version, or the requested entry type, has no supported protocol."""


_MAJOR = re.compile(r"^\s*v?(\d+)(?:\.\d+)*\s*$", re.IGNORECASE)

# Beacon v1 GA4GH API: required BeaconAlleleRequest fields.
_V1_REQUIRED = ("referenceName", "referenceBases", "assemblyId")


def beacon_major_version(service: ServiceDescriptor) -> int | None:
    """Major Beacon version the service declares, or None when it declares none."""
    declared = service.standard_version
    if declared is None or not str(declared).strip():
        return None
    match = _MAJOR.match(str(declared))
    if not match:
        raise BeaconVersionError(f"Beacon version {declared!r} is not a recognised version")
    return int(match.group(1))


def _v1_params(query: dict[str, Any]) -> dict[str, Any]:
    """Map a flat query or a v2 request entity onto v1 BeaconAlleleRequest parameters.

    The coordinate fields share names and 0-based semantics across v1 and v2. What differs:
    v2 expresses a fuzzy range as a two-element ``start``/``end`` array, which v1 spells
    ``startMin``/``startMax`` and ``endMin``/``endMax``; and v2's ``includeResultsetResponses``
    is v1's ``includeDatasetResponses`` (same HIT/MISS/ALL/NONE values).
    """
    if "query" in query or "meta" in query:
        body = query.get("query") or {}
        params = dict(body.get("requestParameters") or {})
        if "includeResultsetResponses" in body:
            params.setdefault("includeResultsetResponses", body["includeResultsetResponses"])
    else:
        params = dict(query)
    for name in ("start", "end"):
        value = params.get(name)
        if isinstance(value, list):
            if len(value) != 2:
                raise ValueError(f"Beacon v1 {name} range needs exactly two positions")
            del params[name]
            params[f"{name}Min"], params[f"{name}Max"] = value
    if "includeResultsetResponses" in params:
        params.setdefault("includeDatasetResponses", params.pop("includeResultsetResponses"))
    missing = [field for field in _V1_REQUIRED if params.get(field) in (None, "")]
    if missing:
        raise ValueError(f"Beacon v1 query requires {', '.join(missing)}")
    return params


class BeaconAdapter(BaseAdapter):
    async def query_variant(
        self,
        service: ServiceDescriptor,
        query: dict[str, Any],
        credential: OutboundCredential,
        *,
        entry_type: str = "g_variants",
    ) -> dict[str, Any]:
        major = beacon_major_version(service)
        if major == 1:
            return await self._query_v1(service, query, credential, entry_type=entry_type)
        if major not in (None, 2):
            raise BeaconVersionError(
                f"Beacon {service.standard_version} is not supported; "
                "the Harness speaks Beacon v1 and v2"
            )
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

    async def _query_v1(
        self,
        service: ServiceDescriptor,
        query: dict[str, Any],
        credential: OutboundCredential,
        *,
        entry_type: str,
    ) -> dict[str, Any]:
        if entry_type != "g_variants":
            raise BeaconVersionError(
                f"Beacon v1 answers allele queries only (entry_type g_variants), not {entry_type!r}"
            )
        result = await self._http.request(
            "GET",
            str(service.url).rstrip("/") + "/query",
            credential=credential,
            params=_v1_params(query),
        )
        data = require_json(result)
        if not isinstance(data, dict):
            raise ValueError("Beacon response must be an object")
        # v1 returns a BeaconAlleleResponse: beaconId, apiVersion, exists, datasetAlleleResponses.
        return data
