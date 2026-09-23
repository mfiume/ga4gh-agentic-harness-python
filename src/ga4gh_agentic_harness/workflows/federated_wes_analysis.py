"""Federated WES analysis workflow realization."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Set
from typing import Any
from urllib.parse import unquote, urlsplit

from ..auth import AuthorityContext
from ..harness import Harness
from ._common import data_as_dict, evidence_ids, first_error_code, succeeded

_SUCCESS_STATES = {"COMPLETE"}
_FAILED_STATES = {"EXECUTOR_ERROR", "SYSTEM_ERROR"}
_CANCELLED_STATES = {"CANCELED", "CANCELLED"}


def _parse_trs_uri(uri: str) -> tuple[str, str, str]:
    parsed = urlsplit(uri)
    if parsed.scheme != "trs" or not parsed.hostname:
        raise ValueError("workflow.trs_uri must use trs://host/tool-id/version")
    parts = [unquote(item) for item in parsed.path.split("/") if item]
    if len(parts) < 2:
        raise ValueError("TRS URI must contain a tool id and version")
    return parsed.hostname, "/".join(parts[:-1]), parts[-1]


def _workflow_digest(resolved: dict[str, Any]) -> str:
    encoded = json.dumps(resolved, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _wes_type_version(service_info: dict[str, Any], workflow_type: str) -> str:
    versions = service_info.get("workflow_type_versions") or {}
    candidates = versions.get(workflow_type) or versions.get(workflow_type.upper()) or []
    if isinstance(candidates, dict):
        candidates = candidates.get("workflow_type_version") or []
    if not candidates:
        raise ValueError(f"WES does not advertise {workflow_type} support")
    return str(candidates[0])


async def run(
    harness: Harness,
    inputs: dict[str, Any],
    *,
    authority: AuthorityContext,
    approved_targets: Set[str],
    poll_interval_seconds: float = 1.0,
    poll_timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Resolve one TRS workflow and execute it at approved WES targets.

    Approval is execution context rather than workflow input so persisted workflow inputs
    cannot silently authorize a future side effect.
    """
    workflow = inputs.get("workflow") or {}
    trs_uri = str(workflow.get("trs_uri") or "")
    descriptor_type = str(workflow.get("descriptor_type") or "")
    targets = [str(item) for item in inputs.get("targets") or []]
    if not targets:
        raise ValueError("at least one WES target is required")
    host, tool_id, version = _parse_trs_uri(trs_uri)
    search = await harness.service_search(
        query=host, product="TRS", limit=200, authority=authority
    )
    # The search matches text anywhere in a declaration, including names. Only a service
    # whose URL host is the TRS URI's host may resolve the workflow.
    candidates = [
        service
        for service in (search.data or [])
        if urlsplit(str(service.url)).hostname == host.lower()
    ]
    if not succeeded(search) or not candidates:
        raise ValueError(f"no TRS service found for {host}")
    trs_service_id = candidates[0].id
    resolved_result = await harness.trs_workflow_resolve(
        trs_service_id,
        tool_id,
        version=version,
        descriptor_type=descriptor_type,
        authority=authority,
    )
    if not succeeded(resolved_result):
        raise RuntimeError(f"TRS resolution failed: {first_error_code(resolved_result)}")
    resolved = data_as_dict(resolved_result)
    workflow_summary = {
        "trs_uri": trs_uri,
        "version": str(resolved.get("resolved_version") or version),
        "digest": _workflow_digest(resolved),
    }

    outcomes: list[dict[str, Any]] = []
    for service_id in targets:
        if service_id not in approved_targets:
            outcomes.append(
                {
                    "service_id": service_id,
                    "status": "skipped",
                    "run_id": None,
                    "outputs": None,
                    "error_code": "approval_required",
                    "evidence": [],
                }
            )
            continue
        probe = await harness.service_probe(service_id, authority=authority)
        if not succeeded(probe):
            outcomes.append(
                {
                    "service_id": service_id,
                    "status": "skipped",
                    "run_id": None,
                    "outputs": None,
                    "error_code": first_error_code(probe),
                    "evidence": evidence_ids(probe),
                }
            )
            continue
        described = await harness.wes_service_describe(service_id, authority=authority)
        if not succeeded(described):
            outcomes.append(
                {
                    "service_id": service_id,
                    "status": "skipped",
                    "run_id": None,
                    "outputs": None,
                    "error_code": first_error_code(described),
                    "evidence": evidence_ids(described),
                }
            )
            continue
        try:
            type_version = _wes_type_version(data_as_dict(described), descriptor_type)
        except ValueError:
            outcomes.append(
                {
                    "service_id": service_id,
                    "status": "skipped",
                    "run_id": None,
                    "outputs": None,
                    "error_code": "unsupported_workflow_type",
                    "evidence": evidence_ids(described),
                }
            )
            continue
        key_material = f"{workflow_summary['digest']}|{service_id}|{authority.software_actor}"
        idempotency_key = hashlib.sha256(key_material.encode()).hexdigest()
        submitted = await harness.wes_run_submit(
            service_id,
            workflow_url=trs_uri,
            workflow_type=descriptor_type,
            workflow_type_version=type_version,
            workflow_params=inputs.get("workflow_inputs") or {},
            tags=inputs.get("tags") or {},
            idempotency_key=idempotency_key,
            authority=authority,
        )
        if not succeeded(submitted):
            code = first_error_code(submitted)
            status = "unknown" if "reconcil" in submitted.errors[0].message.lower() else "failed"
            outcomes.append(
                {
                    "service_id": service_id,
                    "status": status,
                    "run_id": None,
                    "outputs": None,
                    "error_code": code,
                    "evidence": evidence_ids(submitted),
                }
            )
            continue
        submission_data = data_as_dict(submitted)
        run = submission_data.get("run") or submission_data
        run_id = str(run["run_id"])
        ledger = submission_data.get("ledger") or {}
        local_run_id = ledger.get("local_run_id")
        deadline = asyncio.get_running_loop().time() + poll_timeout_seconds
        while True:
            observed = await harness.wes_run_get(
                service_id,
                run_id,
                local_run_id=local_run_id,
                authority=authority,
            )
            if not succeeded(observed):
                outcomes.append(
                    {
                        "service_id": service_id,
                        "status": "unknown",
                        "run_id": run_id,
                        "outputs": None,
                        "error_code": first_error_code(observed),
                        "evidence": evidence_ids(observed),
                    }
                )
                break
            observed_data = data_as_dict(observed)
            state = str(observed_data.get("state") or "UNKNOWN").upper()
            if state in _SUCCESS_STATES | _FAILED_STATES | _CANCELLED_STATES:
                status = (
                    "succeeded"
                    if state in _SUCCESS_STATES
                    else "cancelled"
                    if state in _CANCELLED_STATES
                    else "failed"
                )
                outcome = {
                    "service_id": service_id,
                    "status": status,
                    "run_id": run_id,
                    "outputs": observed_data.get("outputs"),
                    "evidence": evidence_ids(observed),
                }
                if status == "failed":
                    outcome["error_code"] = state.lower()
                outcomes.append(outcome)
                break
            if asyncio.get_running_loop().time() >= deadline:
                outcomes.append(
                    {
                        "service_id": service_id,
                        "status": "unknown",
                        "run_id": run_id,
                        "outputs": None,
                        "error_code": "poll_timeout",
                        "evidence": evidence_ids(observed),
                    }
                )
                break
            await asyncio.sleep(max(0, poll_interval_seconds))

    return {
        "workflow": workflow_summary,
        "summary": {
            "selected": len(outcomes),
            "submitted": sum(item["run_id"] is not None for item in outcomes),
            "succeeded": sum(item["status"] == "succeeded" for item in outcomes),
            "failed": sum(item["status"] == "failed" for item in outcomes),
            "skipped": sum(item["status"] == "skipped" for item in outcomes),
            "unknown": sum(item["status"] == "unknown" for item in outcomes),
        },
        "targets": outcomes,
    }
