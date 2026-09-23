"""Normative SDK data contracts and canonical operation identifiers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Operation(str, Enum):
    HARNESS_DESCRIBE = "ga4gh.harness.describe"
    SERVICE_SEARCH = "ga4gh.service.search"
    SERVICE_DESCRIBE = "ga4gh.service.describe"
    SERVICE_PROBE = "ga4gh.service.probe"
    TRS_WORKFLOW_RESOLVE = "ga4gh.trs.workflow.resolve"
    DRS_OBJECT_RESOLVE = "ga4gh.drs.object.resolve"
    DRS_ACCESS_RESOLVE = "ga4gh.drs.access.resolve"
    BEACON_VARIANT_QUERY = "ga4gh.beacon.variant.query"
    WES_SERVICE_DESCRIBE = "ga4gh.wes.service.describe"
    WES_RUN_SUBMIT = "ga4gh.wes.run.submit"
    WES_RUN_GET = "ga4gh.wes.run.get"
    WES_RUN_CANCEL = "ga4gh.wes.run.cancel"
    CONFORMANCE_ASSESS = "ga4gh.conformance.assess"


class ResultStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class ErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "SERVICE_NOT_FOUND"
    NOT_AUTHORIZED = "AUTHORIZATION_DENIED"
    POLICY_DENIED = "POLICY_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    UNSUPPORTED = "NOT_SUPPORTED"
    UPSTREAM = "UPSTREAM_FAILURE"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "UPSTREAM_INVALID_RESPONSE"
    SECURITY = "POLICY_DENIED"
    INTERNAL = "INTERNAL_ERROR"


class HarnessError(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool = False
    native_status: int | str | None = None
    details: dict[str, Any] | None = None


class Warning(BaseModel):
    code: str
    message: str


class EvidenceReference(BaseModel):
    type: Literal["native-response", "trace", "test-report", "object", "provenance"]
    uri: str
    media_type: str | None = None
    digest: dict[str, str] | None = None
    sensitive: bool = False


class Page(BaseModel):
    returned: int
    next_page_token: str | None = None
    total: int | None = None


T = TypeVar("T")


class ResultEnvelope(BaseModel, Generic[T]):
    model_config = ConfigDict(use_enum_values=True)

    profile_version: str
    operation: Operation
    request_id: str
    status: ResultStatus
    data: T | None = None
    errors: list[HarnessError] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)
    trace_id: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    page: Page | None = None


class ServiceDescriptor(BaseModel):
    id: str
    implementation_id: str | None = None
    name: str | None = None
    product: str | None = None
    standard_version: str | None = None
    url: HttpUrl
    service_info_url: HttpUrl | None = None
    organization: str | None = None
    environment: str | None = None
    source: str = "ga4gh-implementation-registry"
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


class AuthRequirement(BaseModel):
    required: bool = False
    schemes: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    resource: str | None = None
    authorization_servers: list[str] = Field(default_factory=list)


class Capability(BaseModel):
    operation: Operation
    purpose: str
    side_effects: bool = False
    underlying_standard: str
    standard_version: str | None = None
    auth: AuthRequirement = Field(default_factory=AuthRequirement)


class CapabilityDescriptor(BaseModel):
    profile_version: str
    service: ServiceDescriptor | None = None
    capabilities: list[Capability]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProbeStatus(str, Enum):
    LIVE = "live"
    AUTH_REQUIRED = "auth_required"
    HTTP_ERROR = "http_error"
    INVALID_RESPONSE = "invalid_response"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"


class ProbeResult(BaseModel):
    service: ServiceDescriptor
    status: ProbeStatus
    probed_url: str
    http_status: int | None = None
    latency_ms: int | None = None
    service_info: dict[str, Any] | None = None
    auth: AuthRequirement = Field(default_factory=AuthRequirement)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    ERROR = "error"
    INCONCLUSIVE = "inconclusive"


class ConformanceCheck(BaseModel):
    id: str
    title: str
    status: CheckStatus
    message: str
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ConformanceReport(BaseModel):
    service: ServiceDescriptor
    test_pack: str
    test_pack_version: str
    checks: list[ConformanceCheck]
    summary: dict[str, int]
    certification: bool = False
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
