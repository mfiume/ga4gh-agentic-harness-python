"""Deterministic service conformance checks with reproducible result semantics."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import (
    CheckStatus,
    ConformanceCheck,
    ConformanceReport,
    ProbeResult,
    ProbeStatus,
    ServiceDescriptor,
)

TEST_PACK = "ga4gh.service-info.core"
TEST_PACK_VERSION = "0.1.0"


def _check(
    check_id: str, title: str, passed: bool | None, success: str, failure: str
) -> ConformanceCheck:
    if passed is None:
        status, message = CheckStatus.INCONCLUSIVE, failure
    else:
        status, message = (CheckStatus.PASS, success) if passed else (CheckStatus.FAIL, failure)
    return ConformanceCheck(id=check_id, title=title, status=status, message=message)


class ConformanceAssessor:
    def assess(
        self,
        service: ServiceDescriptor,
        probe: ProbeResult,
        *,
        test_pack: str = TEST_PACK,
    ) -> ConformanceReport:
        if test_pack != TEST_PACK:
            raise ValueError(f"unsupported test pack {test_pack!r}")
        info = probe.service_info
        checks = [
            _check(
                "transport.reachable",
                "Service is reachable",
                probe.status in {ProbeStatus.LIVE, ProbeStatus.AUTH_REQUIRED},
                "The service produced a meaningful HTTP response.",
                f"Observed probe status: {probe.status.value}.",
            ),
            _check(
                "service-info.json-object",
                "Service Info is a JSON object",
                isinstance(info, dict) if probe.status == ProbeStatus.LIVE else None,
                "The response is a JSON object.",
                "A Service Info JSON object was not available.",
            ),
        ]
        if isinstance(info, dict):
            required = ["id", "name", "type", "organization", "version"]
            missing = [
                field for field in required if info.get(field) is None or info.get(field) == ""
            ]
            checks.append(
                _check(
                    "service-info.required-fields",
                    "Required Service Info fields are present",
                    not missing,
                    "All core required fields are present.",
                    "Missing fields: " + ", ".join(missing),
                )
            )
            observed = (info.get("type") or {}).get("artifact")
            declared = service.product
            checks.append(
                _check(
                    "registry.product-consistency",
                    "Registry product agrees with Service Info",
                    _product_matches(declared, observed),
                    "Declared and observed products agree.",
                    f"Registry declares {declared!r}; Service Info reports {observed!r}.",
                )
            )
        else:
            checks.extend(
                [
                    ConformanceCheck(
                        id="service-info.required-fields",
                        title="Required Service Info fields are present",
                        status=CheckStatus.INCONCLUSIVE,
                        message="Service Info was unavailable.",
                    ),
                    ConformanceCheck(
                        id="registry.product-consistency",
                        title="Registry product agrees with Service Info",
                        status=CheckStatus.INCONCLUSIVE,
                        message="Service Info was unavailable.",
                    ),
                ]
            )
        counts = Counter(check.status.value for check in checks)
        return ConformanceReport(
            service=service,
            test_pack=test_pack,
            test_pack_version=TEST_PACK_VERSION,
            checks=checks,
            summary={status.value: counts.get(status.value, 0) for status in CheckStatus},
        )


def _product_matches(declared: str | None, observed: Any) -> bool | None:
    if not declared or not observed:
        return None
    aliases = {
        "beacon": "beacon",
        "data repository service": "drs",
        "drs": "drs",
        "tool registry service": "trs",
        "trs": "trs",
        "workflow execution service": "wes",
        "wes": "wes",
    }
    return aliases.get(declared.lower(), declared.lower()) == str(observed).lower()
