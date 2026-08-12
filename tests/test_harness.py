from __future__ import annotations

import httpx
import respx

from ga4gh_agentic_harness.auth import AuthorityContext
from ga4gh_agentic_harness.harness import Harness
from ga4gh_agentic_harness.http import SafeHttpClient
from ga4gh_agentic_harness.models import ErrorCode, Operation, ResultStatus
from ga4gh_agentic_harness.registry import ServiceRegistry
from ga4gh_agentic_harness.tracing import MemoryTraceSink


def _harness(settings, traces=None) -> Harness:
    http = SafeHttpClient(settings)
    return Harness(
        settings=settings,
        http=http,
        registry=ServiceRegistry(http, settings),
        traces=traces,
    )


@respx.mock
async def test_describe_and_search_envelopes(settings, registry_items) -> None:
    respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=registry_items)
    )
    async with _harness(settings) as harness:
        described = await harness.harness_describe()
        searched = await harness.service_search(product="DRS", limit=1)
    assert described.status == ResultStatus.SUCCESS
    operations = {item["operation"] for item in described.data["capabilities"]}
    assert Operation.WES_RUN_SUBMIT.value in operations
    assert searched.page and searched.page.total == 1
    assert searched.data[0].id == "drs-1"


@respx.mock
async def test_service_probe_and_conformance(settings, registry_items) -> None:
    respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=registry_items)
    )
    respx.get("https://drs.test/ga4gh/drs/v1/service-info").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "drs-1",
                "name": "DRS",
                "type": {"artifact": "drs", "version": "1.4.0"},
                "organization": {"name": "Example"},
                "version": "1",
            },
        )
    )
    traces = MemoryTraceSink()
    async with _harness(settings, traces) as harness:
        probe = await harness.service_probe("drs-1")
        report = await harness.conformance_assess("drs-1")
    assert probe.data.status == "live"
    assert report.data["certification"] is False
    assert len(traces.events) == 4


@respx.mock
async def test_service_probe_uses_explicit_metadata_url(settings, registry_items) -> None:
    items = list(registry_items)
    items[2] = dict(items[2]) | {"serviceInfoUrl": "https://beacon.test/api/info"}
    respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=items)
    )
    route = respx.get("https://beacon.test/api/info").mock(
        return_value=httpx.Response(200, json={"meta": {"apiVersion": "v2.0"}})
    )
    async with _harness(settings) as harness:
        result = await harness.service_probe("beacon-1")
    assert result.status == ResultStatus.SUCCESS
    assert route.called


@respx.mock
async def test_drs_error_is_structured(settings, registry_items) -> None:
    respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=registry_items)
    )
    respx.get("https://drs.test/ga4gh/drs/v1/objects/missing").mock(
        return_value=httpx.Response(404, json={"msg": "missing"})
    )
    async with _harness(settings) as harness:
        result = await harness.drs_object_resolve("drs-1", "missing")
    assert result.status == ResultStatus.FAILURE
    assert result.errors[0].code == ErrorCode.NOT_FOUND


@respx.mock
async def test_wes_submit_policy_ledger_and_idempotency(settings, registry_items) -> None:
    respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=registry_items)
    )
    route = respx.post("https://wes.test/ga4gh/wes/v1/runs").mock(
        return_value=httpx.Response(200, json={"run_id": "remote-1"})
    )
    async with _harness(settings) as harness:
        denied = await harness.wes_run_submit(
            "wes-1",
            workflow_url="trs://workflow/1",
            workflow_type="CWL",
            workflow_type_version="v1.2",
            workflow_params={},
            idempotency_key="same",
        )
        authority = AuthorityContext(
            software_actor="test", inbound_scopes=["ga4gh:workflow:submit"]
        )
        accepted = await harness.wes_run_submit(
            "wes-1",
            workflow_url="trs://workflow/1",
            workflow_type="CWL",
            workflow_type_version="v1.2",
            workflow_params={},
            idempotency_key="same",
            authority=authority,
        )
        replay = await harness.wes_run_submit(
            "wes-1",
            workflow_url="trs://workflow/1",
            workflow_type="CWL",
            workflow_type_version="v1.2",
            workflow_params={},
            idempotency_key="same",
            authority=authority,
        )
    assert denied.errors[0].code == ErrorCode.POLICY_DENIED
    assert accepted.data["ledger"]["remote_run_id"] == "remote-1"
    assert replay.warnings[0].code == "IDEMPOTENT_REPLAY"
    assert route.call_count == 1


@respx.mock
async def test_wes_unknown_submission_is_not_retried(settings, registry_items) -> None:
    respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=registry_items)
    )
    route = respx.post("https://wes.test/ga4gh/wes/v1/runs").mock(
        side_effect=httpx.ReadTimeout("outcome unknown")
    )
    authority = AuthorityContext(
        software_actor="test", inbound_scopes=["ga4gh:workflow:submit"]
    )
    async with _harness(settings) as harness:
        first = await harness.wes_run_submit(
            "wes-1",
            workflow_url="trs://workflow/1",
            workflow_type="CWL",
            workflow_type_version="v1.2",
            workflow_params={},
            idempotency_key="unknown",
            authority=authority,
        )
        second = await harness.wes_run_submit(
            "wes-1",
            workflow_url="trs://workflow/1",
            workflow_type="CWL",
            workflow_type_version="v1.2",
            workflow_params={},
            idempotency_key="unknown",
            authority=authority,
        )
    assert first.status == ResultStatus.FAILURE
    assert second.status == ResultStatus.FAILURE
    assert "reconcile" in second.errors[0].message
    assert route.call_count == 1


async def test_dispatch_rejects_unknown_operation(settings) -> None:
    async with _harness(settings) as harness:
        try:
            await harness.dispatch("ga4gh.unknown", {})
        except ValueError as exc:
            assert "not a valid Operation" in str(exc)
        else:
            raise AssertionError("unknown operation was accepted")
