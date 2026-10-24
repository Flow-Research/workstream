"""Exact prepared resources for private generated model-output custody."""

from __future__ import annotations

import json
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.checkers.api.output_custody import (
    GENERATED_OUTPUT_RESERVATION,
    GENERATED_OUTPUT_SELECTOR,
    GeneratedOutputSubject,
    GeneratedOutputReservation,
    GeneratedOutputSelector,
    CheckerOutputUnavailable,
    generated_output_subject,
)
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceSelector,
    TrialEvidenceUnavailable,
)
from app.modules.model_usage.api import ModelCallUnavailable, SetupModelOutputSelector


WRITE = ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE
BIND = ActionId.ARTIFACT_CHECKER_OUTPUT_BINDING_CREATE
CHECKER_OUTPUT_ACTIONS = frozenset({WRITE, BIND})

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class CheckerOutputCommitmentFacts(BaseModel):
    """Server-computed content commitment without source bytes or scratch identity."""

    model_config = _STRICT_FROZEN
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(strict=True, ge=0, le=1_048_576)
    media_type: Literal["application/json"]


class CheckerOutputStoredAuthorityFacts(BaseModel):
    """Verified ART ancestry selected under the exact model-call reservation."""

    model_config = _STRICT_FROZEN
    put_attempt_id: UUID
    checker_request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(strict=True, ge=0, le=1_048_576)
    media_type: Literal["application/json"]
    status: Literal[
        "prepared",
        "put_in_flight",
        "acknowledgement_unknown",
        "object_confirmed",
        "absent_replay_required",
        "integrity_mismatch",
        "provider_unavailable",
        "conflict",
        "verified",
    ]
    content_id: UUID | None
    replica_id: UUID | None
    verification_receipt_id: UUID | None

    @model_validator(mode="after")
    def exact_verification(self) -> Self:
        present = (
            self.content_id is not None,
            self.replica_id is not None,
            self.verification_receipt_id is not None,
        )
        if self.status == "verified" and not all(present):
            raise ValueError("verified checker output ancestry is incomplete")
        if self.status != "verified" and any(present):
            raise ValueError("unverified checker output has verified ancestry")
        return self


class CheckerOutputResourceContext(BaseModel):
    """One exact selector prepared before owner locks and closed by stored facts."""

    model_config = _STRICT_FROZEN
    resource_type: Literal[
        "checker_model_output", "setup_model_call", "checker_trial_evidence"
    ]
    resource_id: UUID
    scope_project_id: UUID
    action_id: ActionId
    selector: GeneratedOutputSelector
    selector_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reservation: GeneratedOutputReservation | None = None
    commitment: CheckerOutputCommitmentFacts | None = None
    stored: CheckerOutputStoredAuthorityFacts | None = None

    @model_validator(mode="after")
    def exact_selector(self) -> Self:
        selector = GENERATED_OUTPUT_SELECTOR.validate_python(self.selector)
        if self.action_id not in CHECKER_OUTPUT_ACTIONS:
            raise ValueError("invalid checker output action")
        resource_type, resource_id, project_id = _selector_resource(selector)
        if (self.resource_type, self.resource_id, self.scope_project_id) != (
            resource_type,
            resource_id,
            project_id,
        ) or self.selector_digest != checker_output_selector_digest(selector):
            raise ValueError("invalid checker output selector resource")
        if self.reservation is not None:
            reservation = GENERATED_OUTPUT_RESERVATION.validate_python(self.reservation)
            try:
                slot = reservation.select(selector)
            except (
                CheckerOutputUnavailable,
                ModelCallUnavailable,
                TrialEvidenceUnavailable,
                ValidationError,
            ) as error:
                raise ValueError("model output reservation differs from selector") from error
            subject = generated_output_subject(reservation)
            if (
                _subject_resource_id(subject) != self.resource_id
                or subject.project_id != self.scope_project_id
                or _subject_resource_type(subject.resource_type) != self.resource_type
            ):
                raise ValueError("model output reservation resource differs")
            if self.commitment is not None and (
                self.commitment.byte_count > slot.maximum_bytes
                or self.commitment.media_type != slot.media_type
            ):
                raise ValueError("checker output commitment exceeds its reservation")
            if self.stored is not None and (
                self.stored.byte_count > slot.maximum_bytes
                or self.stored.media_type != slot.media_type
                or self.stored.checker_request_digest
                != canonical_json_hash(subject.request_digest_facts)
            ):
                raise ValueError("stored checker output differs from its reservation")
        if self.commitment is not None and self.action_id is not WRITE:
            raise ValueError("checker output commitment requires write authority")
        if self.stored is not None and self.stored.sha256 != self.selector.content_sha256:
            raise ValueError("stored checker output differs from selector")
        if (
            self.reservation is not None
            and self.action_id is BIND
            and (self.stored is None or self.stored.status != "verified")
        ):
            raise ValueError("checker output binding requires verified ancestry")
        if self.commitment is not None and self.commitment.sha256 != self.selector.content_sha256:
            raise ValueError("checker output commitment differs from selector")
        if self.commitment is not None and self.stored is not None:
            raise ValueError("checker output authority facts are ambiguous")
        return self


def checker_output_selector_digest(selector: GeneratedOutputSelector) -> str:
    """Hash the entire typed selector prepared before protected owner access."""
    checked = GENERATED_OUTPUT_SELECTOR.validate_python(selector)
    return canonical_json_hash(checked.model_dump(mode="json"))


def checker_output_prepare_resource(
    action: ActionId, selector: GeneratedOutputSelector
) -> CheckerOutputResourceContext:
    """Build the preliminary resource bound only to the caller's exact selector."""
    checked = GENERATED_OUTPUT_SELECTOR.validate_python(selector)
    resource_type, resource_id, project_id = _selector_resource(checked)
    return CheckerOutputResourceContext(
        resource_type=resource_type,
        resource_id=resource_id,
        scope_project_id=project_id,
        action_id=action,
        selector=checked,
        selector_digest=checker_output_selector_digest(checked),
    )


def checker_output_admission_resource(
    selector: GeneratedOutputSelector,
    facts: object,
) -> CheckerOutputResourceContext:
    """Bind prepared write authority to server-computed content facts."""
    prepared = checker_output_prepare_resource(WRITE, selector)
    return CheckerOutputResourceContext(
        resource_type=prepared.resource_type,
        resource_id=prepared.resource_id,
        scope_project_id=prepared.scope_project_id,
        action_id=prepared.action_id,
        selector=prepared.selector,
        selector_digest=prepared.selector_digest,
        reservation=facts.reservation,
        commitment=CheckerOutputCommitmentFacts(
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            media_type=facts.media_type,
        ),
    )


def checker_output_stored_resource(
    action: ActionId,
    selector: GeneratedOutputSelector,
    reservation: GeneratedOutputReservation,
    facts: object,
) -> CheckerOutputResourceContext:
    """Bind prepared authority to storage facts selected by ART itself."""
    prepared = checker_output_prepare_resource(action, selector)
    return CheckerOutputResourceContext(
        resource_type=prepared.resource_type,
        resource_id=prepared.resource_id,
        scope_project_id=prepared.scope_project_id,
        action_id=prepared.action_id,
        selector=prepared.selector,
        selector_digest=prepared.selector_digest,
        reservation=reservation,
        stored=CheckerOutputStoredAuthorityFacts(
            put_attempt_id=facts.put_attempt_id,
            checker_request_digest=facts.checker_request_digest,
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            media_type=facts.media_type,
            status=facts.status,
            content_id=facts.content_id,
            replica_id=facts.replica_id,
            verification_receipt_id=facts.verification_receipt_id,
        ),
    )


def _selector_resource(
    selector: GeneratedOutputSelector,
) -> tuple[
    Literal["checker_model_output", "setup_model_call", "checker_trial_evidence"],
    UUID,
    UUID,
]:
    """Project one closed selector union onto its AUTH resource identity."""
    if isinstance(selector, TrialEvidenceSelector):
        return "checker_trial_evidence", selector.trial_evidence_id, selector.project_id
    if isinstance(selector, SetupModelOutputSelector):
        return "setup_model_call", selector.model_call_attempt_id, selector.slot_key.project_id
    return (
        "checker_model_output",
        selector.model_call_attempt_id,
        selector.paid_slot.project_id,
    )


def _subject_resource_type(
    value: Literal["checker_model_call", "setup_model_call", "checker_trial_evidence"],
) -> Literal["checker_model_output", "setup_model_call", "checker_trial_evidence"]:
    return "checker_model_output" if value == "checker_model_call" else value


def _subject_resource_id(subject: GeneratedOutputSubject) -> UUID:
    """Project the exact non-null owner ID from the closed shared subject."""
    if subject.resource_type == "checker_trial_evidence":
        if subject.checker_trial_evidence_id is None:
            raise ValueError("trial evidence subject owner is missing")
        return subject.checker_trial_evidence_id
    if subject.model_call_attempt_id is None:
        raise ValueError("model output subject owner is missing")
    return subject.model_call_attempt_id


def parse_checker_output_prepare(
    action: ActionId, value: object, invalid_error: type[Exception]
) -> CheckerOutputResourceContext | None:
    """Parse only preliminary selector resources at PREP issuance."""
    if action not in CHECKER_OUTPUT_ACTIONS:
        return None
    try:
        resource = CheckerOutputResourceContext.model_validate_json(json.dumps(value))
        if (
            resource.action_id is not action
            or resource.reservation is not None
            or resource.commitment is not None
            or resource.stored is not None
        ):
            raise ValueError("checker output prepare resource is not preliminary")
        return resource
    except (TypeError, ValueError) as error:
        raise invalid_error("invalid prepared checker output authority") from error


def checker_output_prepare_matches(
    prepared: CheckerOutputResourceContext | None,
    resource: object,
) -> bool:
    """Require final facts to retain the exact selector committed at preparation."""
    return (
        prepared is not None
        and type(resource) is CheckerOutputResourceContext
        and resource.resource_type == prepared.resource_type
        and resource.action_id is prepared.action_id
        and resource.resource_id == prepared.resource_id
        and resource.scope_project_id == prepared.scope_project_id
        and resource.selector == prepared.selector
        and resource.selector_digest == prepared.selector_digest
        and resource.reservation is not None
        and ((resource.commitment is not None) ^ (resource.stored is not None))
    )


__all__ = (
    "BIND",
    "CHECKER_OUTPUT_ACTIONS",
    "CheckerOutputResourceContext",
    "WRITE",
    "checker_output_admission_resource",
    "checker_output_prepare_matches",
    "checker_output_prepare_resource",
    "checker_output_selector_digest",
    "checker_output_stored_resource",
    "parse_checker_output_prepare",
)
