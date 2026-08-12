"""Workflow Execution Service adapter."""

from __future__ import annotations

import json
from typing import Any

from ..auth import OutboundCredential
from ..models import ServiceDescriptor
from .base import BaseAdapter, api_base, require_json, segment


class WesAdapter(BaseAdapter):
    async def describe_service(
        self, service: ServiceDescriptor, credential: OutboundCredential
    ) -> dict[str, Any]:
        data = await self.get(service, "/service-info", credential)
        if not isinstance(data, dict):
            raise ValueError("WES service-info response must be an object")
        return data

    async def submit(
        self,
        service: ServiceDescriptor,
        credential: OutboundCredential,
        *,
        workflow_url: str,
        workflow_type: str,
        workflow_type_version: str,
        workflow_params: dict[str, Any],
        tags: dict[str, Any] | None = None,
        workflow_engine_parameters: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        form = {
            "workflow_url": workflow_url,
            "workflow_type": workflow_type,
            "workflow_type_version": workflow_type_version,
            "workflow_params": json.dumps(workflow_params, separators=(",", ":")),
            "tags": json.dumps(tags or {}, separators=(",", ":")),
            "workflow_engine_parameters": json.dumps(
                workflow_engine_parameters or {}, separators=(",", ":")
            ),
        }
        result = await self._http.request(
            "POST",
            api_base(service) + "/runs",
            credential=credential,
            data=form,
            idempotency_key=idempotency_key,
        )
        data = require_json(result)
        if not isinstance(data, dict) or not data.get("run_id"):
            raise ValueError("WES submission response has no run_id")
        return data

    async def get_run(
        self, service: ServiceDescriptor, run_id: str, credential: OutboundCredential
    ) -> dict[str, Any]:
        data = await self.get(service, f"/runs/{segment(run_id)}", credential)
        if not isinstance(data, dict):
            raise ValueError("WES run response must be an object")
        return data

    async def cancel(
        self, service: ServiceDescriptor, run_id: str, credential: OutboundCredential
    ) -> dict[str, Any]:
        result = await self._http.request(
            "POST",
            api_base(service) + f"/runs/{segment(run_id)}/cancel",
            credential=credential,
        )
        data = require_json(result)
        if not isinstance(data, dict):
            raise ValueError("WES cancel response must be an object")
        return data
