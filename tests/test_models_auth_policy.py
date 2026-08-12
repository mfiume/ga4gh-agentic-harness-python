from __future__ import annotations

import pytest
from pydantic import ValidationError

from ga4gh_agentic_harness.auth import (
    AuthorityContext,
    CredentialRequest,
    EnvironmentBearerCredentialProvider,
    OutboundCredential,
)
from ga4gh_agentic_harness.models import Operation
from ga4gh_agentic_harness.policy import DefaultPolicyEvaluator, PolicyRequest
from ga4gh_agentic_harness.tracing import TraceEvent


def test_credential_repr_does_not_reveal_headers() -> None:
    credential = OutboundCredential(headers={"Authorization": "Bearer secret"})
    assert "secret" not in repr(credential)
    assert credential.audit_metadata() == {"grant_type": "public"}


async def test_environment_provider_is_service_and_audience_pinned(
    monkeypatch: pytest.MonkeyPatch, drs_service
) -> None:
    monkeypatch.setenv("TEST_DRS_TOKEN", "top-secret")
    provider = EnvironmentBearerCredentialProvider(
        variable="TEST_DRS_TOKEN", service_id="drs-1", audience=str(drs_service.url).rstrip("/")
    )
    request = CredentialRequest(
        service=drs_service,
        operation=Operation.DRS_OBJECT_RESOLVE,
        resource=str(drs_service.url).rstrip("/"),
        authority=AuthorityContext(software_actor="test"),
    )
    credential = await provider.acquire(request)
    assert credential.headers["Authorization"] == "Bearer top-secret"
    bad = request.model_copy(update={"resource": "https://other.test"})
    with pytest.raises(PermissionError):
        await provider.acquire(bad)


async def test_default_policy_denies_unscoped_mutation(wes_service) -> None:
    evaluator = DefaultPolicyEvaluator()
    decision = await evaluator.evaluate(
        PolicyRequest(
            authority=AuthorityContext(software_actor="agent"),
            operation=Operation.WES_RUN_SUBMIT,
            service=wes_service,
            side_effects=True,
        )
    )
    assert not decision.allowed


async def test_default_policy_accepts_exact_operation_scope(wes_service) -> None:
    evaluator = DefaultPolicyEvaluator()
    decision = await evaluator.evaluate(
        PolicyRequest(
            authority=AuthorityContext(
                software_actor="agent", inbound_scopes=["ga4gh:workflow:submit"]
            ),
            operation=Operation.WES_RUN_SUBMIT,
            service=wes_service,
            side_effects=True,
        )
    )
    assert decision.allowed


def test_trace_rejects_secret_bearing_metadata() -> None:
    with pytest.raises(ValidationError):
        TraceEvent(
            trace_id="trace",
            request_id="request",
            phase="completed",
            operation=Operation.HARNESS_DESCRIBE,
            authority=AuthorityContext(software_actor="test"),
            metadata={"authorization": "Bearer secret"},
        )
