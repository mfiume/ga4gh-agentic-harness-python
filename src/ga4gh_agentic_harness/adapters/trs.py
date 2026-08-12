"""Tool Registry Service adapter."""

from __future__ import annotations

from typing import Any

from ..auth import OutboundCredential
from ..models import ServiceDescriptor
from .base import BaseAdapter, segment


class TrsAdapter(BaseAdapter):
    async def resolve_workflow(
        self,
        service: ServiceDescriptor,
        tool_id: str,
        credential: OutboundCredential,
        *,
        version: str | None = None,
        descriptor_type: str | None = None,
    ) -> dict[str, Any]:
        root = f"/tools/{segment(tool_id)}"
        if version is None:
            tool = await self.get(service, root, credential)
            if not isinstance(tool, dict):
                raise ValueError("TRS tool response must be an object")
            versions = tool.get("versions") or []
            if not versions:
                return {"tool": tool, "resolved_version": None}
            candidate = versions[-1]
            version = candidate.get("id") or candidate.get("name")
            if not version:
                raise ValueError("TRS version has no id or name")
        version_data = await self.get(
            service, root + f"/versions/{segment(str(version))}", credential
        )
        output: dict[str, Any] = {"version": version_data, "resolved_version": version}
        if descriptor_type:
            descriptor = await self.get(
                service,
                root
                + f"/versions/{segment(str(version))}/{segment(descriptor_type)}/descriptor",
                credential,
            )
            output["descriptor"] = descriptor
        return output

