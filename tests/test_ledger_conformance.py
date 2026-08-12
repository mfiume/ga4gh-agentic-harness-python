from __future__ import annotations

from pathlib import Path

from ga4gh_agentic_harness.conformance import ConformanceAssessor
from ga4gh_agentic_harness.ledger import WorkflowRunLedger
from ga4gh_agentic_harness.models import CheckStatus, ProbeResult, ProbeStatus


async def test_ledger_is_idempotent_and_persistent(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    ledger = WorkflowRunLedger(path)
    first, created = await ledger.create_submission(
        service_id="wes-1",
        authority_key="tenant|user|agent",
        request_id="request-1",
        idempotency_key="key-1",
    )
    replay, replay_created = await ledger.create_submission(
        service_id="wes-1",
        authority_key="tenant|user|agent",
        request_id="request-2",
        idempotency_key="key-1",
    )
    assert created is True
    assert replay_created is False
    assert replay.local_run_id == first.local_run_id
    await ledger.update(first.local_run_id, state="submitted", remote_run_id="remote-1")
    reopened = WorkflowRunLedger(path)
    restored = await reopened.get(first.local_run_id)
    assert restored.remote_run_id == "remote-1" and restored.state == "submitted"


def test_conformance_passes_valid_service_info(drs_service) -> None:
    probe = ProbeResult(
        service=drs_service,
        status=ProbeStatus.LIVE,
        probed_url=str(drs_service.service_info_url),
        http_status=200,
        service_info={
            "id": "drs-1",
            "name": "DRS",
            "type": {"group": "org.ga4gh", "artifact": "drs", "version": "1.4.0"},
            "organization": {"name": "Example"},
            "version": "1.0.0",
        },
    )
    report = ConformanceAssessor().assess(drs_service, probe)
    assert report.certification is False
    assert all(check.status == CheckStatus.PASS for check in report.checks)


def test_conformance_reports_missing_fields(drs_service) -> None:
    probe = ProbeResult(
        service=drs_service,
        status=ProbeStatus.LIVE,
        probed_url=str(drs_service.service_info_url),
        service_info={"id": "drs-1", "type": {"artifact": "wes"}},
    )
    report = ConformanceAssessor().assess(drs_service, probe)
    failed = {check.id for check in report.checks if check.status == CheckStatus.FAIL}
    assert "service-info.required-fields" in failed
    assert "registry.product-consistency" in failed
