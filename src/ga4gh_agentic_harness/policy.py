"""Policy decision point contracts for canonical operations."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from .auth import AuthorityContext
from .models import Operation, ServiceDescriptor

OPERATION_SCOPES: dict[Operation, str] = {
    Operation.WES_RUN_SUBMIT: "ga4gh:workflow:submit",
    Operation.WES_RUN_CANCEL: "ga4gh:workflow:cancel",
}


class PolicyRequest(BaseModel):
    authority: AuthorityContext
    operation: Operation
    service: ServiceDescriptor | None = None
    side_effects: bool = False


class PolicyDecision(BaseModel):
    """A local decision. ``approval_required`` blocks the operation even when allowed."""

    allowed: bool
    reason: str
    decision_id: str | None = None
    approval_required: bool = False


class PolicyEvaluator(Protocol):
    async def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        """Return a local policy decision. Local service authorization remains final."""


class DefaultPolicyEvaluator:
    """Permit reads and require explicit authority scopes for mutations."""

    async def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        if not request.side_effects:
            return PolicyDecision(allowed=True, reason="read-only operation")
        required = OPERATION_SCOPES.get(request.operation, request.operation.value)
        scopes = request.authority.inbound_scopes
        if required in scopes or "ga4gh:*" in scopes:
            return PolicyDecision(allowed=True, reason="operation scope present")
        return PolicyDecision(
            allowed=False,
            reason=f"side-effecting operation requires inbound scope {required!r}",
        )
