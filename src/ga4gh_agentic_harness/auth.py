"""Two-leg authorization contracts.

Inbound authority is represented only as validated claims. Outbound credential values are
opaque trusted-runtime objects and cannot be serialized by Pydantic or returned in envelopes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from .models import Operation, ServiceDescriptor


class AuthorityContext(BaseModel):
    human_principal: str | None = None
    software_actor: str
    tenant: str | None = None
    purpose: str | None = None
    inbound_audience: str | None = None
    inbound_scopes: list[str] = Field(default_factory=list)
    delegation_id: str | None = None


class CredentialRequest(BaseModel):
    service: ServiceDescriptor
    operation: Operation
    resource: str
    scopes: list[str] = Field(default_factory=list)
    authority: AuthorityContext


@dataclass(slots=True)
class OutboundCredential:
    """Secret-bearing value restricted to the HTTP boundary."""

    headers: dict[str, str] = field(default_factory=dict, repr=False)
    issuer: str | None = None
    audience: str | None = None
    grant_type: str = "public"
    subject_fingerprint: str | None = None

    def audit_metadata(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "issuer": self.issuer,
                "audience": self.audience,
                "grant_type": self.grant_type,
                "subject_fingerprint": self.subject_fingerprint,
            }.items()
            if value is not None
        }


class CredentialProvider(Protocol):
    async def acquire(self, request: CredentialRequest) -> OutboundCredential:
        """Acquire a least-privilege credential for exactly one downstream resource."""


class PublicCredentialProvider:
    async def acquire(self, request: CredentialRequest) -> OutboundCredential:
        del request
        return OutboundCredential()


class EnvironmentBearerCredentialProvider:
    """Local-development provider with explicit service/audience pinning."""

    def __init__(self, *, variable: str, service_id: str, audience: str) -> None:
        self._variable = variable
        self._service_id = service_id
        self._audience = audience.rstrip("/")

    async def acquire(self, request: CredentialRequest) -> OutboundCredential:
        if request.service.id != self._service_id:
            raise PermissionError("credential is not pinned to this service")
        if request.resource.rstrip("/") != self._audience:
            raise PermissionError("credential audience does not match target resource")
        token = os.environ.get(self._variable)
        if not token:
            raise PermissionError(f"credential environment variable {self._variable!r} is unset")
        return OutboundCredential(
            headers={"Authorization": f"Bearer {token}"},
            audience=self._audience,
            grant_type="configured_bearer",
        )


class MappingCredentialProvider:
    """Select providers by exact service ID without sharing credentials between services."""

    def __init__(
        self,
        providers: dict[str, CredentialProvider],
        fallback: CredentialProvider | None = None,
    ) -> None:
        self._providers = providers
        self._fallback = fallback or PublicCredentialProvider()

    async def acquire(self, request: CredentialRequest) -> OutboundCredential:
        provider = self._providers.get(request.service.id, self._fallback)
        return await provider.acquire(request)

