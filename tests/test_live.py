from __future__ import annotations

import pytest

from ga4gh_agentic_harness.harness import Harness
from ga4gh_agentic_harness.http import SafeHttpClient
from ga4gh_agentic_harness.models import ServiceDescriptor
from ga4gh_agentic_harness.registry import ServiceRegistry
from ga4gh_agentic_harness.settings import Settings

pytestmark = pytest.mark.live


async def test_public_registry_search() -> None:
    async with Harness() as harness:
        result = await harness.service_search(limit=1)
    assert result.status == "success"
    assert result.data


async def test_public_afrigen_beacon_variant_query() -> None:
    async with Harness() as harness:
        found = await harness.service_search(product="Beacon", limit=20)
        service = next(
            (
                item
                for item in (found.data or [])
                if "beacon.afrigen-d.org" in str(item.url)
            ),
            None,
        )
        if service is None:
            pytest.skip("AfriGen-D Beacon is not currently declared in the registry")
        result = await harness.beacon_variant_query(
            service.id,
            {
                "assemblyId": "GRCh38",
                "referenceName": "1",
                "start": 100000,
                "referenceBases": "A",
                "alternateBases": "T",
            },
        )
    assert result.status == "success"
    assert isinstance(result.data, dict)


async def test_public_usegalaxy_wes_service_info() -> None:
    service = ServiceDescriptor(
        id="org.usegalaxy.wes",
        name="UseGalaxy.org WES",
        product="WES",
        standard_version="1.0.0",
        url="https://usegalaxy.org/ga4gh/wes/v1",
        service_info_url="https://usegalaxy.org/ga4gh/wes/v1/service-info",
        source="explicit-live-test",
    )
    settings = Settings()
    http = SafeHttpClient(settings)
    async with Harness(
        settings=settings,
        http=http,
        registry=ServiceRegistry(http, settings, static_services=[service]),
    ) as harness:
        result = await harness.wes_service_describe(service.id)
    assert result.status == "success"
    assert isinstance(result.data, dict)
