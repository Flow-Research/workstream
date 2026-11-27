"""Closed public and owner values for uncertain post-submit delivery recovery."""

from __future__ import annotations

import json
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.evaluation_contract import PostSubmissionExecutionRequest


_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    strict=True,
    hide_input_in_errors=True,
    revalidate_instances="always",
)

POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT = (
    "PostSubmissionDeliveryReconciliationRequested"
)
POST_SUBMIT_DELIVERY_SUPPORTED_EVENTS = (
    ("PostSubmissionEvaluationRequested", 1),
    ("PostSubmissionEvaluationCompleted", 1),
)


def _without_none(value):
    """Mirror Pydantic's recursive exclude-none digest input."""
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_without_none(item) for item in value]
    return value


class PostSubmitDeliveryUnavailable(RuntimeError):
    """The selected delivery is absent, stale, denied, corrupt, or held."""


class PostSubmitDeliveryConflict(RuntimeError):
    """The request key or immutable reconciliation facts conflict."""


class PostSubmitDeliveryOperationUnavailable(RuntimeError):
    """Internal reconciliation evidence or persistence is unavailable."""


class PostSubmitDeliveryAuthorityDenied(RuntimeError):
    """Fresh system Operator authority denied the reconciliation command."""


class PostSubmitDeliveryCursorInvalid(ValueError):
    """The signed project/query cursor is invalid."""


class PostSubmitDeliverySourceUnavailable(RuntimeError):
    """An exact TASK-owned source is absent, stale, or internally inconsistent."""


class PostSubmitDeliveryRetryable(RuntimeError):
    """The existing TASK owner refused before effects and may be retried safely."""


def _reason(value: str) -> str:
    if value != value.strip() or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise ValueError("post-submit delivery reason is invalid")
    return value


PostSubmitDeliveryReason = Annotated[
    str,
    Field(min_length=1, max_length=500),
    AfterValidator(_reason),
]


class PostSubmitDeliveryRequest(BaseModel):
    """Public reason for one exact uncertain-delivery reconciliation."""

    model_config = _STRICT
    reason: PostSubmitDeliveryReason
    action: Literal["abandon_unknown"] | None = None


class PostSubmitDeliveryQuery(BaseModel):
    """One project-bound page of exact finalized UNKNOWN attempts."""

    model_config = _STRICT
    project_id: UUID
    limit: int = Field(ge=1, le=100, strict=True)
    cursor: str | None = Field(default=None, max_length=512)


class PostSubmitDeliveryPosition(BaseModel):
    """Stable keyset boundary carried only by the signed cursor."""

    model_config = _STRICT
    finalized_at: AwareDatetime
    event_id: UUID


class PostSubmitRequestDeliveryFacts(BaseModel):
    """CHECKERS-owned classification for one exact original request delivery."""

    model_config = _STRICT
    request: PostSubmissionExecutionRequest
    checker_run_id: UUID
    classification: Literal["committed", "retry_safe", "unresolved"]
    terminal_outcome: Literal["completed", "infrastructure_failed"] | None = None
    completion_event_id: UUID | None = None

    @model_validator(mode="after")
    def exact_terminal_shape(self):
        terminal = self.classification == "committed"
        if terminal != (self.terminal_outcome is not None):
            raise ValueError("request delivery classification differs")
        completed = self.terminal_outcome == "completed"
        if completed != (self.completion_event_id is not None):
            raise ValueError("request delivery completion identity differs")
        return self


class PostSubmitDeliverySource(BaseModel):
    """Privacy-bounded finalized delivery identity and source classification."""

    model_config = _STRICT

    project_id: UUID
    event_id: UUID
    event_type: Literal[
        "PostSubmissionEvaluationRequested",
        "PostSubmissionEvaluationCompleted",
    ]
    event_version: Literal[1]
    aggregate_id: UUID
    evaluation_request_id: UUID
    checker_run_id: UUID
    evaluation_generation: int = Field(ge=1)
    claim_generation: int = Field(ge=1)
    payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    finalized_at: AwareDatetime
    delivery_state: Literal["dead_letter"] = "dead_letter"
    error_code: Literal["INVOKE_OUTCOME_UNKNOWN"] = "INVOKE_OUTCOME_UNKNOWN"
    classification: Literal["committed", "retry_safe", "unresolved"]
    reconciliation_event_id: UUID | None = None
    reconciliation_state: Literal[
        "pending", "active", "acknowledged", "held"
    ] | None = None

    @model_validator(mode="after")
    def exact_reconciliation(self):
        if (self.reconciliation_event_id is None) != (
            self.reconciliation_state is None
        ):
            raise ValueError("delivery reconciliation identity is incomplete")
        if (
            self.reconciliation_state == "held"
            and self.classification != "unresolved"
        ):
            raise ValueError("uncertain reconciliation child must be held")
        return self


class PostSubmitDeliveryPage(BaseModel):
    """Bounded project page of uncertain post-submit deliveries."""

    model_config = _STRICT
    project_id: UUID
    items: tuple[PostSubmitDeliverySource, ...]
    next_cursor: str | None

    @model_validator(mode="after")
    def exact_project(self):
        if len(self.items) > 100 or any(
            item.project_id != self.project_id for item in self.items
        ):
            raise ValueError("post-submit delivery page differs")
        return self


class PostSubmitDeliveryCommand(BaseModel):
    """Operator's exact source, reason and replay key."""

    model_config = _STRICT
    actor_profile_id: UUID
    project_id: UUID
    event_id: UUID
    request_key: UUID
    reason: PostSubmitDeliveryReason
    action: Literal["abandon_unknown"] | None = Field(default=None, exclude_if=lambda value: value is None)


class PostSubmitExpiredLease(BaseModel):
    """Exact worker custody displaced by an explicit Operator decision."""

    model_config = _STRICT
    lease_id: UUID
    lease_generation: int = Field(ge=1)
    expires_at: AwareDatetime


class PostSubmitDeliveryPreparation(BaseModel):
    """Stable command and locked source facts prepared before child append."""

    model_config = _STRICT
    command: PostSubmitDeliveryCommand
    source: PostSubmitDeliverySource
    abandonment: PostSubmitExpiredLease | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def exact_source(self):
        if (
            self.command.project_id != self.source.project_id
            or self.command.event_id != self.source.event_id
            or (self.source.classification == "unresolved") != (self.abandonment is not None)
            or (self.command.action == "abandon_unknown") != (self.abandonment is not None)
            or (self.abandonment is not None and self.source.event_type != "PostSubmissionEvaluationRequested")
            or self.source.reconciliation_event_id is not None
        ):
            raise ValueError("post-submit delivery preparation differs")
        return self


def post_submit_delivery_request_digest(
    facts: PostSubmitDeliveryPreparation,
) -> str:
    """Commit the exact Operator command and locked source classification."""
    checked = PostSubmitDeliveryPreparation.model_validate(facts)
    return canonical_json_hash(
        {
            "domain": "workstream.post_submit_delivery_reconciliation.v0.1",
            "preparation": checked.model_dump(mode="json"),
        }
    )


class PostSubmitDeliveryChildPayload(BaseModel):
    """Privacy-bounded child facts; the original payload is never copied."""

    model_config = _STRICT
    schema_version: Literal["post_submit_delivery_reconciliation.v1"] = (
        "post_submit_delivery_reconciliation.v1"
    )
    original_event_id: UUID
    original_claim_generation: int = Field(ge=1)
    original_payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    original_event_type: Literal[
        "PostSubmissionEvaluationRequested",
        "PostSubmissionEvaluationCompleted",
    ]
    original_event_version: Literal[1]
    evaluation_request_id: UUID
    checker_run_id: UUID
    evaluation_generation: int = Field(ge=1)
    classification: Literal["committed", "retry_safe", "unresolved"]
    abandonment: PostSubmitExpiredLease | None = Field(default=None, exclude_if=lambda value: value is None)
    reconciliation_request_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    authorization_decision_id: UUID
    authorization_resource_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    authorization_resource_json: str = Field(min_length=2, max_length=8192)
    operator_actor_profile_id: UUID
    operator_identity_link_id: UUID

    @model_validator(mode="after")
    def exact_authorization_resource(self):
        """Retain one canonical bounded Operator resource receipt."""
        if (self.classification == "unresolved") != (self.abandonment is not None) or (
            self.abandonment is not None and self.original_event_type != "PostSubmissionEvaluationRequested"
        ):
            raise ValueError("delivery abandonment facts differ")
        try:
            resource = json.loads(self.authorization_resource_json)
        except (TypeError, ValueError) as exc:
            raise ValueError("delivery authorization resource is invalid") from exc
        if (
            not isinstance(resource, dict)
            or set(resource) != {"resource_context"}
            or json.dumps(
                resource,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            != self.authorization_resource_json
            or canonical_json_hash(_without_none(resource))
            != self.authorization_resource_digest
        ):
            raise ValueError("delivery authorization resource differs")
        if self.abandonment is not None:
            try:
                preparation = PostSubmitDeliveryPreparation.model_validate_json(
                    json.dumps(resource["resource_context"]["preparation"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("delivery abandonment authority is invalid") from exc
            source, command = preparation.source, preparation.command
            if (preparation.abandonment != self.abandonment or command.action != "abandon_unknown"
                    or command.request_key != self.reconciliation_request_id
                    or command.actor_profile_id != self.operator_actor_profile_id
                    or source.event_id != self.original_event_id
                    or source.claim_generation != self.original_claim_generation
                    or source.payload_digest != self.original_payload_digest
                    or source.checker_run_id != self.checker_run_id
                    or source.evaluation_request_id != self.evaluation_request_id
                    or source.evaluation_generation != self.evaluation_generation):
                raise ValueError("delivery abandonment authority differs")
        return self


class PostSubmitDeliverySuccessor(BaseModel):
    """The sole immutable child event appended for an original UNKNOWN attempt."""

    model_config = _STRICT
    event_id: UUID
    payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    occurred_at: AwareDatetime
    classification: Literal["committed", "retry_safe", "unresolved"]


class PostSubmitDeliveryAuthorityReceipt(BaseModel):
    """AUTH's consumed exact resource retained by the child payload."""

    model_config = _STRICT
    actor_profile_id: UUID
    identity_link_id: UUID
    decision_id: UUID
    resource_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    resource_json: str


class PostSubmitDeliveryResult(BaseModel):
    """Public immutable reconciliation receipt."""

    model_config = _STRICT
    source: PostSubmitDeliverySource
    successor: PostSubmitDeliverySuccessor
    authorization_decision_id: UUID

    @model_validator(mode="after")
    def exact_child(self):
        if (
            self.source.reconciliation_event_id != self.successor.event_id
            or self.source.reconciliation_state is None
            or (
                self.source.reconciliation_state == "pending"
                and self.source.classification != self.successor.classification
            )
        ):
            raise ValueError("post-submit delivery result differs")
        return self


class PostSubmitDeliveryReadAuthority(Protocol):
    """Fresh system-Operator discovery authority and signed cursor custody."""

    async def authorize_and_decode(
        self, query: PostSubmitDeliveryQuery,
    ) -> PostSubmitDeliveryPosition | None: ...

    def encode(
        self, query: PostSubmitDeliveryQuery, position: PostSubmitDeliveryPosition,
    ) -> str: ...

    async def restage_denial(self, error: Exception) -> bool: ...


class PostSubmitDeliveryAuthorizationPort(Protocol):
    """Prepared Operator reconciliation authority with exact replay validation."""

    async def prepare(self, facts: PostSubmitDeliveryPreparation) -> object: ...

    async def consume(
        self,
        handle: object,
        facts: PostSubmitDeliveryPreparation,
    ) -> PostSubmitDeliveryAuthorityReceipt: ...

    async def authorize_replay(
        self,
        handle: object,
        facts: PostSubmitDeliveryPreparation,
    ) -> None: ...

    async def validate_replay(
        self,
        handle: object,
        facts: PostSubmitDeliveryPreparation,
        original_link_id: UUID,
        decision_id: UUID,
    ) -> None: ...

    def close(self, handle: object) -> None: ...

    async def restage_denial(self, error: PostSubmitDeliveryAuthorityDenied) -> bool: ...


def post_submit_reconciliation_event_json(
    project_id: UUID, payload: PostSubmitDeliveryChildPayload,
) -> str:
    """Immutable child envelope shared by publication and read-only observation."""
    return json.dumps({
        "event_type": POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT, "event_version": 1,
        "aggregate_type": "outbox_delivery", "aggregate_id": str(payload.original_event_id),
        "project_id": str(project_id), "correlation_id": str(payload.reconciliation_request_id),
        "causation_event_id": str(payload.original_event_id),
        "idempotency_key": "post-submit-reconcile:" + str(payload.original_event_id),
        "payload": payload.model_dump(mode="json"),
    }, sort_keys=True, separators=(",", ":"))
