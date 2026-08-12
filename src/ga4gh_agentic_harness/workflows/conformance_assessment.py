"""Read-only conformance assessment workflow realization."""

from __future__ import annotations

from typing import Any

from ..auth import AuthorityContext
from ..harness import Harness
from ._common import data_as_dict, evidence_ids, first_error_code, succeeded, value


async def run(
    harness: Harness,
    inputs: dict[str, Any],
    *,
    authority: AuthorityContext | None = None,
) -> dict[str, Any]:
    """Assess every target with deterministic read-only test packs.

    The returned object conforms to the pilot workflow output schema. It is observed
    evidence, never a GA4GH certification decision.
    """
    if inputs.get("allow_mutating_tests"):
        raise PermissionError("MUTATING_TESTS_PROHIBITED")
    targets = inputs.get("targets") or []
    test_packs = inputs.get("test_packs") or []
    if not targets or not test_packs:
        raise ValueError("targets and test_packs must be non-empty")

    outcomes: list[dict[str, Any]] = []
    for target in targets:
        service_id = str(target["service_id"])
        probe = await harness.service_probe(service_id, authority=authority)
        if not succeeded(probe):
            code = first_error_code(probe)
            reachability = "auth-blocked" if code in {
                "not_authorized",
                "policy_denied",
                "audience_mismatch",
                "insufficient_scope",
            } else "unreachable"
            outcomes.append(
                {
                    "service_id": service_id,
                    "reachability": reachability,
                    "assessment": "not-assessed",
                    "findings": [],
                    "evidence": evidence_ids(probe),
                }
            )
            continue

        findings: list[dict[str, str]] = []
        traces: list[str] = []
        assessment = "conformant"
        for pack in test_packs:
            result = await harness.conformance_assess(
                service_id, test_pack=str(pack["id"]), authority=authority
            )
            traces.extend(evidence_ids(result))
            if not succeeded(result):
                findings.append(
                    {
                        "test_id": str(pack["id"]),
                        "status": "error",
                        "code": first_error_code(result),
                    }
                )
                assessment = "inconclusive"
                continue
            checks = data_as_dict(result).get("checks", [])
            for check in checks:
                finding = {
                    "test_id": str(check.get("id", "unknown")),
                    "status": str(value(check.get("status", "inconclusive"))),
                }
                findings.append(finding)
            statuses = {finding["status"] for finding in findings}
            if "fail" in statuses:
                assessment = "non-conformant"
            elif statuses & {"error", "inconclusive"}:
                assessment = "inconclusive"
        outcomes.append(
            {
                "service_id": service_id,
                "reachability": "reachable",
                "assessment": assessment,
                "findings": findings,
                "evidence": traces,
            }
        )

    return {
        "summary": {
            "assessed": len(outcomes),
            "reachable": sum(item["reachability"] == "reachable" for item in outcomes),
            "conformant": sum(item["assessment"] == "conformant" for item in outcomes),
            "non_conformant": sum(
                item["assessment"] == "non-conformant" for item in outcomes
            ),
            "inconclusive": sum(
                item["assessment"] in {"inconclusive", "not-assessed"} for item in outcomes
            ),
        },
        "targets": outcomes,
        "test_packs": test_packs,
        "disclaimer": "Observed test evidence; not GA4GH certification.",
    }
