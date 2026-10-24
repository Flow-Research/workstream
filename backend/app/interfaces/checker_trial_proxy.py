"""Closed trusted-host trial callbacks; never an image-facing authority grant."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr, TypeAdapter

from app.modules.checkers.api.canonical_values import CheckerValue, ResourceId, Sha256
from app.modules.checkers.api.external import ExternalCheckerExecutionRequest
from app.modules.checkers.api.trial_evidence import TrialEvidenceStableSubject

TRIAL_PROXY_PROTOCOL = "workstream.trial_evidence_proxy.v1"
TRIAL_PROXY_MAXIMUM_FRAME_BYTES = 4 * 1024 * 1024


class TrialReserveRequest(CheckerValue):
    """Select an immutable slot before starting a bounded sandbox plan."""

    protocol_version: Literal["workstream.trial_evidence_proxy.v1"]
    operation: Literal["reserve"]
    external_request: ExternalCheckerExecutionRequest
    subject: TrialEvidenceStableSubject


class TrialPublishRequest(CheckerValue):
    """Commit exact canonical trial bytes to existing ART verification custody."""

    protocol_version: Literal["workstream.trial_evidence_proxy.v1"]
    operation: Literal["publish"]
    external_request: ExternalCheckerExecutionRequest
    trial_evidence_id: ResourceId
    project_id: ResourceId
    content_sha256: Sha256
    byte_count: Annotated[StrictInt, Field(ge=1, le=1_048_576)]
    canonical_receipt_utf8: Annotated[StrictStr, Field(min_length=1, max_length=1_048_576)]


TrialProxyRequest = Annotated[
    TrialReserveRequest | TrialPublishRequest, Field(discriminator="operation"),
]
TRIAL_PROXY_REQUEST = TypeAdapter(TrialProxyRequest)
