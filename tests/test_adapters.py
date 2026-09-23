from __future__ import annotations

import httpx
import pytest
import respx

from ga4gh_agentic_harness.adapters import BeaconAdapter, DrsAdapter, TrsAdapter, WesAdapter
from ga4gh_agentic_harness.auth import OutboundCredential
from ga4gh_agentic_harness.http import SafeHttpClient
from ga4gh_agentic_harness.models import ServiceDescriptor


@respx.mock
async def test_drs_object_and_access_redaction(settings, drs_service) -> None:
    respx.get("https://drs.test/ga4gh/drs/v1/objects/object%2F1").mock(
        return_value=httpx.Response(200, json={"id": "object/1", "size": 1})
    )
    respx.get("https://drs.test/ga4gh/drs/v1/objects/object%2F1/access/s3").mock(
        return_value=httpx.Response(
            200,
            json={
                "url": "https://bucket.test/object?X-Amz-Signature=secret",
                "headers": {"Authorization": "Bearer secret"},
            },
        )
    )
    http = SafeHttpClient(settings)
    adapter = DrsAdapter(http)
    credential = OutboundCredential()
    obj = await adapter.resolve_object(drs_service, "object/1", credential)
    access = await adapter.resolve_access(drs_service, "object/1", "s3", credential)
    assert obj["id"] == "object/1"
    assert access["url"] == "https://bucket.test/object"
    assert access["headers"] == {"redacted": True}
    assert "secret" not in str(access)
    await http.aclose()


@respx.mock
async def test_trs_resolves_version_and_descriptor(settings) -> None:
    service = ServiceDescriptor(
        id="trs-1", product="TRS", url="https://trs.test/ga4gh/trs/v2"
    )
    root = "https://trs.test/ga4gh/trs/v2/tools/github.com%2Facme%2Fworkflow"
    respx.get(root + "/versions/1.0").mock(
        return_value=httpx.Response(200, json={"id": "1.0"})
    )
    respx.get(root + "/versions/1.0/CWL/descriptor").mock(
        return_value=httpx.Response(200, json={"content": "cwlVersion: v1.2"})
    )
    http = SafeHttpClient(settings)
    result = await TrsAdapter(http).resolve_workflow(
        service,
        "github.com/acme/workflow",
        OutboundCredential(),
        version="1.0",
        descriptor_type="CWL",
    )
    assert result["resolved_version"] == "1.0"
    assert "content" in result["descriptor"]
    await http.aclose()


@respx.mock
async def test_beacon_query(settings) -> None:
    service = ServiceDescriptor(id="b", product="Beacon", url="https://beacon.test/api")
    route = respx.post("https://beacon.test/api/g_variants").mock(
        return_value=httpx.Response(200, json={"response": {"exists": True}})
    )
    http = SafeHttpClient(settings)
    result = await BeaconAdapter(http).query_variant(
        service, {"query": {"requestParameters": {}}}, OutboundCredential()
    )
    assert result["response"]["exists"] is True
    assert route.calls[0].request.method == "POST"
    await http.aclose()


@respx.mock
async def test_beacon_flat_query_uses_get(settings) -> None:
    service = ServiceDescriptor(id="b", product="Beacon", url="https://beacon.test/api")
    route = respx.get("https://beacon.test/api/g_variants").mock(
        return_value=httpx.Response(200, json={"responseSummary": {"exists": False}})
    )
    http = SafeHttpClient(settings)
    result = await BeaconAdapter(http).query_variant(
        service,
        {"assemblyId": "GRCh38", "referenceName": "1", "start": 100000},
        OutboundCredential(),
    )
    assert result["responseSummary"]["exists"] is False
    assert route.calls[0].request.method == "GET"
    await http.aclose()


@respx.mock
async def test_wes_submit_get_cancel(settings, wes_service) -> None:
    submit = respx.post("https://wes.test/ga4gh/wes/v1/runs").mock(
        return_value=httpx.Response(200, json={"run_id": "run-1"})
    )
    respx.get("https://wes.test/ga4gh/wes/v1/runs/run-1").mock(
        return_value=httpx.Response(200, json={"run_id": "run-1", "state": "COMPLETE"})
    )
    respx.post("https://wes.test/ga4gh/wes/v1/runs/run-1/cancel").mock(
        return_value=httpx.Response(200, json={"run_id": "run-1"})
    )
    http = SafeHttpClient(settings)
    adapter = WesAdapter(http)
    credential = OutboundCredential()
    created = await adapter.submit(
        wes_service,
        credential,
        workflow_url="trs://workflow/1",
        workflow_type="CWL",
        workflow_type_version="v1.2",
        workflow_params={"message": "hello"},
        idempotency_key="idem-1",
    )
    assert created["run_id"] == "run-1"
    assert submit.calls[0].request.headers["Idempotency-Key"] == "idem-1"
    assert (await adapter.get_run(wes_service, "run-1", credential))["state"] == "COMPLETE"
    assert (await adapter.cancel(wes_service, "run-1", credential))["run_id"] == "run-1"
    await http.aclose()


@pytest.mark.parametrize("run_id", ["..", "."])
@respx.mock
async def test_dot_segment_identifiers_cannot_escape_the_resource_path(
    settings, wes_service, run_id
) -> None:
    escaped = respx.post(url__regex=r"https://wes\.test/ga4gh/wes/v1(/runs)?/cancel").mock(
        return_value=httpx.Response(200, json={"run_id": "other"})
    )
    http = SafeHttpClient(settings)
    with pytest.raises(ValueError):
        await WesAdapter(http).cancel(wes_service, run_id, OutboundCredential())
    assert not escaped.called
    await http.aclose()


@respx.mock
async def test_drs_object_inline_access_urls_are_redacted(settings, drs_service) -> None:
    respx.get("https://drs.test/ga4gh/drs/v1/objects/object-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "object-1",
                "access_methods": [
                    {"type": "s3", "access_id": "s3"},
                    {
                        "type": "https",
                        "access_url": {
                            "url": "https://bucket.test/object?X-Amz-Signature=secret",
                            "headers": ["Authorization: Bearer secret"],
                        },
                    },
                ],
            },
        )
    )
    http = SafeHttpClient(settings)
    obj = await DrsAdapter(http).resolve_object(drs_service, "object-1", OutboundCredential())
    assert "secret" not in str(obj)
    assert obj["access_methods"][0] == {"type": "s3", "access_id": "s3"}
    inline = obj["access_methods"][1]["access_url"]
    assert inline["url"] == "https://bucket.test/object"
    assert inline["access_url_query_redacted"] is True
    assert inline["headers"] == {"redacted": True}
    await http.aclose()
