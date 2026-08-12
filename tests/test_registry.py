from __future__ import annotations

import httpx
import respx

from ga4gh_agentic_harness.http import SafeHttpClient
from ga4gh_agentic_harness.models import ServiceDescriptor
from ga4gh_agentic_harness.registry import ServiceRegistry, normalize_service


def test_normalize_service(registry_items) -> None:
    service = normalize_service(registry_items[0])
    assert service.id == "drs-1"
    assert service.product == "DRS"
    assert service.organization == "Example Org"


def test_normalize_standard_service_registry_record() -> None:
    service = normalize_service(
        {
            "id": "local.drs",
            "name": "Local DRS",
            "type": {"group": "org.ga4gh", "artifact": "drs", "version": "1.4.0"},
            "organization": {"name": "Local"},
            "version": "0.1.0",
            "url": "http://127.0.0.1:8080/ga4gh/drs/v1",
        }
    )
    assert service.product == "drs"
    assert service.standard_version == "1.4.0"
    assert service.implementation_id == "local.drs"


@respx.mock
async def test_search_filter_pagination_and_cache(settings, registry_items) -> None:
    route = respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=registry_items)
    )
    http = SafeHttpClient(settings)
    registry = ServiceRegistry(http, settings)
    services, next_cursor, total = await registry.search(product="DRS", limit=1)
    assert [service.id for service in services] == ["drs-1"]
    assert next_cursor is None and total == 1
    assert (await registry.get("example.drs")).id == "drs-1"
    assert route.call_count == 1
    await http.aclose()


@respx.mock
async def test_search_free_text(settings, registry_items) -> None:
    respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=registry_items)
    )
    http = SafeHttpClient(settings)
    registry = ServiceRegistry(http, settings)
    services, _, total = await registry.search(query="workflow")
    assert total == 1 and services[0].id == "wes-1"
    await http.aclose()


async def test_static_service_resolves_without_remote_registry(settings) -> None:
    service = ServiceDescriptor(
        id="private-wes",
        product="WES",
        url="https://private.test/ga4gh/wes/v1",
    )
    http = SafeHttpClient(settings)
    registry = ServiceRegistry(http, settings, static_services=[service])
    try:
        resolved = await registry.get(service.id)
    finally:
        await http.aclose()
    assert resolved == service
