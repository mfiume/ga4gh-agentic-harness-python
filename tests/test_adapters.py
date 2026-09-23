from __future__ import annotations

import httpx
import pytest
import respx

from ga4gh_agentic_harness.adapters import BeaconAdapter, DrsAdapter, TrsAdapter, WesAdapter
from ga4gh_agentic_harness.adapters.beacon import BeaconVersionError
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


# ---- Beacon v1: selected by the version the service declares, never by probing it

def _beacon(version: str | None) -> ServiceDescriptor:
    return ServiceDescriptor(id="b1", product="Beacon", standard_version=version,
                             url="https://beacon1.test/api")


V1_QUERY = {"referenceName": "1", "start": 100000, "referenceBases": "A",
            "alternateBases": "T", "assemblyId": "GRCh37"}


@pytest.mark.parametrize("version", ["v1.0", "1.0.1", "1.1.0", "v1"])
@respx.mock
async def test_beacon_v1_declared_version_uses_query_endpoint(settings, version) -> None:
    route = respx.get("https://beacon1.test/api/query").mock(return_value=httpx.Response(
        200, json={"beaconId": "org.b1", "apiVersion": "v1.0.1", "exists": True}))
    http = SafeHttpClient(settings)
    result = await BeaconAdapter(http).query_variant(_beacon(version), dict(V1_QUERY),
                                                     OutboundCredential())
    await http.aclose()
    assert result["exists"] is True
    sent = dict(route.calls[0].request.url.params)
    assert sent == {"referenceName": "1", "start": "100000", "referenceBases": "A",
                    "alternateBases": "T", "assemblyId": "GRCh37"}


@respx.mock
async def test_beacon_v1_translates_v2_request_entity(settings) -> None:
    route = respx.get("https://beacon1.test/api/query").mock(
        return_value=httpx.Response(200, json={"exists": False}))
    entity = {"meta": {"apiVersion": "2.0"}, "query": {
        "requestParameters": {"referenceName": "X", "start": [100, 200], "end": [300, 400],
                              "referenceBases": "N", "variantType": "DEL",
                              "assemblyId": "GRCh38"},
        "includeResultsetResponses": "HIT"}}
    http = SafeHttpClient(settings)
    await BeaconAdapter(http).query_variant(_beacon("v1.0"), entity, OutboundCredential())
    await http.aclose()
    assert dict(route.calls[0].request.url.params) == {
        "referenceName": "X", "startMin": "100", "startMax": "200", "endMin": "300",
        "endMax": "400", "referenceBases": "N", "variantType": "DEL", "assemblyId": "GRCh38",
        "includeDatasetResponses": "HIT"}


@respx.mock
async def test_beacon_v1_renames_resultset_flag_in_flat_query(settings) -> None:
    route = respx.get("https://beacon1.test/api/query").mock(
        return_value=httpx.Response(200, json={"exists": False}))
    http = SafeHttpClient(settings)
    await BeaconAdapter(http).query_variant(
        _beacon("1.0"), V1_QUERY | {"includeResultsetResponses": "ALL"}, OutboundCredential())
    await http.aclose()
    params = dict(route.calls[0].request.url.params)
    assert params["includeDatasetResponses"] == "ALL"
    assert "includeResultsetResponses" not in params


async def test_beacon_v1_missing_required_fields_is_invalid_request(settings) -> None:
    http = SafeHttpClient(settings)
    with pytest.raises(ValueError, match=r"referenceBases.*assemblyId"):
        await BeaconAdapter(http).query_variant(
            _beacon("v1.0"), {"referenceName": "1", "start": 5}, OutboundCredential())
    await http.aclose()


async def test_beacon_v1_has_no_other_entry_types(settings) -> None:
    http = SafeHttpClient(settings)
    with pytest.raises(BeaconVersionError, match="g_variants"):
        await BeaconAdapter(http).query_variant(_beacon("v1.0"), dict(V1_QUERY),
                                                OutboundCredential(), entry_type="individuals")
    await http.aclose()


@pytest.mark.parametrize("version", ["0.3.0", "v3.0", "latest"])
async def test_beacon_unsupported_declared_version_is_refused(settings, version) -> None:
    http = SafeHttpClient(settings)
    with pytest.raises(BeaconVersionError, match="Beacon"):
        await BeaconAdapter(http).query_variant(_beacon(version), dict(V1_QUERY),
                                                OutboundCredential())
    await http.aclose()


@pytest.mark.parametrize("version", [None, "v2.0.0", "2.0.0"])
@respx.mock
async def test_beacon_v2_or_undeclared_keeps_g_variants(settings, version) -> None:
    route = respx.get("https://beacon1.test/api/g_variants").mock(
        return_value=httpx.Response(200, json={"responseSummary": {"exists": True}}))
    http = SafeHttpClient(settings)
    await BeaconAdapter(http).query_variant(_beacon(version), dict(V1_QUERY),
                                            OutboundCredential())
    await http.aclose()
    assert route.called
