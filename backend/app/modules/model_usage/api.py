"""Typed contracts for project-image model calls and lifetime project spend."""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol, Self
from uuid import RFC_4122, UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.core.hashing import canonical_json_hash

Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Identifier = Annotated[
    StrictStr, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$")
]
ProviderIdentifier = Annotated[
    StrictStr,
    Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"),
]
ProviderResponseIdentifier = Annotated[
    StrictStr,
    Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Nanodollars = Annotated[StrictInt, Field(ge=0, le=9_000_000_000_000_000_000)]


class ModelCallUnavailable(RuntimeError):
    """Conceal unavailable, foreign, stale or unauthorized model-call state."""


class ModelCallConflict(ModelCallUnavailable):
    """Reject immutable identity or replay substitution."""


class ModelCallBudgetUnavailable(ModelCallUnavailable):
    """Report a finite project budget that cannot cover the next dispatch."""


class ModelCallValue(BaseModel):
    """Strict immutable values shared across model-call owner boundaries."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )


def _require_uuid7(value: UUID, name: str) -> UUID:
    if value.version != 7 or value.variant != RFC_4122:
        raise ValueError(f"{name} must be UUIDv7")
    return value


def _public_uuid(value: object) -> object:
    """Decode only the canonical UUID spelling that a JSON request can carry."""
    if isinstance(value, UUID) or type(value) is not str:
        return value
    try:
        parsed = UUID(value)
    except ValueError:
        return value
    if str(parsed) != value:
        raise ValueError("UUID must use its canonical lowercase spelling")
    return parsed


def _public_datetime(value: object) -> object:
    """Decode an RFC 3339-compatible timestamp before strict aware validation."""
    if isinstance(value, datetime) or type(value) is not str:
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return value


class ModelProfileSelector(ModelCallValue):
    """Exact immutable profile identity retained in approved checker configuration."""

    profile_id: UUID
    profile_version: StrictInt = Field(ge=1)
    profile_digest: Sha256

    @model_validator(mode="after")
    def canonical_id(self) -> Self:
        _require_uuid7(self.profile_id, "model profile ID")
        return self


class ModelGenerationSettings(ModelCallValue):
    """Closed provider-neutral settings; prompts never belong to a profile."""

    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
    text_verbosity: Literal["low", "medium", "high"]


class ModelPricing(ModelCallValue):
    """Exact integer nano-USD rates with no floating-point rounding."""

    pricing_policy_id: UUID
    pricing_policy_version: StrictInt = Field(ge=1)
    pricing_policy_digest: Sha256
    uncached_input_nanodollars_per_token: Nanodollars
    cached_input_nanodollars_per_token: Nanodollars
    output_nanodollars_per_token: Nanodollars

    _decode_public_uuid = field_validator("pricing_policy_id", mode="before")(_public_uuid)

    @model_validator(mode="after")
    def nonzero_and_canonical(self) -> Self:
        _require_uuid7(self.pricing_policy_id, "model pricing policy ID")
        rates = (
            self.uncached_input_nanodollars_per_token,
            self.cached_input_nanodollars_per_token,
            self.output_nanodollars_per_token,
        )
        if max(rates) <= 0:
            raise ValueError("model pricing rates cannot all be zero")
        return self


class ProjectModelProfileSpec(ModelCallValue):
    """Operator-owned provider and pricing profile shared by model-use owners."""

    project_id: UUID
    profile_version: StrictInt = Field(ge=1)
    provider: ProviderIdentifier
    api: ProviderIdentifier
    model_snapshot: ProviderIdentifier
    settings: ModelGenerationSettings
    maximum_request_bytes: StrictInt = Field(ge=1, le=1_048_576)
    maximum_output_bytes: StrictInt = Field(ge=1, le=1_048_576)
    maximum_response_bytes: StrictInt = Field(ge=1, le=1_048_576)
    maximum_input_tokens: StrictInt = Field(ge=1, le=10_000_000)
    maximum_output_tokens: StrictInt = Field(ge=1, le=10_000_000)
    maximum_calls: StrictInt = Field(ge=1, le=100)
    maximum_total_request_bytes: StrictInt = Field(ge=1, le=104_857_600)
    maximum_total_response_bytes: StrictInt = Field(ge=1, le=104_857_600)
    maximum_total_input_tokens: StrictInt = Field(ge=1, le=100_000_000)
    maximum_total_output_tokens: StrictInt = Field(ge=1, le=100_000_000)
    allowed_tools: tuple[Identifier, ...] = ()
    maximum_tool_calls: StrictInt = Field(ge=0, le=1_000)
    maximum_tool_output_bytes: StrictInt = Field(ge=0, le=104_857_600)
    deadline_ms: StrictInt = Field(ge=100, le=3_600_000)
    pricing: ModelPricing

    _decode_public_uuid = field_validator("project_id", mode="before")(_public_uuid)

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def decode_public_tools(cls, value):
        """Decode the JSON array representation into the frozen canonical tuple."""
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def coherent_bounds(self) -> Self:
        if self.maximum_response_bytes < 6 * self.maximum_output_bytes + 4096:
            raise ValueError("model response evidence cannot preserve the maximum output")
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("model profile tools must be unique")
        if tuple(sorted(self.allowed_tools)) != self.allowed_tools:
            raise ValueError("model profile tools must be canonical")
        if not self.allowed_tools and (
            self.maximum_tool_calls != 0 or self.maximum_tool_output_bytes != 0
        ):
            raise ValueError("tool-free model profiles cannot reserve tool capacity")
        if self.allowed_tools and (
            self.maximum_tool_calls == 0 or self.maximum_tool_output_bytes == 0
        ):
            raise ValueError("tool-enabled model profiles require finite tool bounds")
        bounded_totals = (
            (self.maximum_request_bytes, self.maximum_total_request_bytes),
            (self.maximum_response_bytes, self.maximum_total_response_bytes),
            (self.maximum_input_tokens, self.maximum_total_input_tokens),
            (self.maximum_output_tokens, self.maximum_total_output_tokens),
        )
        if any(per_call > total for per_call, total in bounded_totals):
            raise ValueError("model run totals cannot be smaller than one call")
        if any(total > per_call * self.maximum_calls for per_call, total in bounded_totals):
            raise ValueError("model run totals exceed the finite call envelope")
        return self

    @property
    def maximum_reservation_nanodollars(self) -> int:
        """Return the maximum settled plus outstanding amount for one whole run."""
        input_rate = max(
            self.pricing.uncached_input_nanodollars_per_token,
            self.pricing.cached_input_nanodollars_per_token,
        )
        value = (
            self.maximum_total_input_tokens * input_rate
            + self.maximum_total_output_tokens * self.pricing.output_nanodollars_per_token
        )
        if value <= 0 or value > 9_000_000_000_000_000_000:
            raise ValueError("model profile reservation is outside the supported range")
        return value

    @property
    def maximum_dispatch_reservation_nanodollars(self) -> int:
        """Return the conservative reservation for one actual provider dispatch."""
        input_rate = max(
            self.pricing.uncached_input_nanodollars_per_token,
            self.pricing.cached_input_nanodollars_per_token,
        )
        value = (
            self.maximum_input_tokens * input_rate
            + self.maximum_output_tokens * self.pricing.output_nanodollars_per_token
        )
        if value <= 0 or value > self.maximum_reservation_nanodollars:
            raise ValueError("model dispatch reservation is outside the run envelope")
        return value


class ModelProfileProvisioningFacts(ModelCallValue):
    """Complete immutable profile publication facts consumed by Operator authority."""

    operation_id: UUID
    actor_profile_id: UUID
    spec: ProjectModelProfileSpec
    profile_digest: Sha256

    @model_validator(mode="after")
    def exact_digest(self) -> Self:
        if self.profile_digest != canonical_json_hash(self.spec.model_dump(mode="json")):
            raise ValueError("model profile digest mismatch")
        return self


class ProjectModelProfile(ModelProfileProvisioningFacts):
    """Published exact profile with its immutable authorization receipt."""

    profile_id: UUID
    authorization_evidence_id: UUID
    created_at: AwareDatetime

    @model_validator(mode="after")
    def canonical_record_id(self) -> Self:
        _require_uuid7(self.profile_id, "model profile ID")
        return self

    @property
    def selector(self) -> ModelProfileSelector:
        return ModelProfileSelector(
            profile_id=self.profile_id,
            profile_version=self.spec.profile_version,
            profile_digest=self.profile_digest,
        )


class ProjectModelBudgetConfigurationSpec(ModelCallValue):
    """One explicit authorization/reconciliation and metered-ceiling adjustment.

    Externally reconciled prior spend excludes usage retained by this ledger. Later
    immutable versions may only increase that external fact; account counters remain
    lifetime values and are never folded into or reset by this field.
    """

    project_id: UUID
    configuration_version: StrictInt = Field(ge=1)
    authorized_total_nanodollars: Nanodollars
    externally_reconciled_prior_spend_nanodollars: Nanodollars
    lifetime_limit_nanodollars: Nanodollars

    _decode_public_uuid = field_validator("project_id", mode="before")(_public_uuid)

    @model_validator(mode="after")
    def positive_limit(self) -> Self:
        if self.lifetime_limit_nanodollars <= 0:
            raise ValueError("model budget limit must be positive")
        if self.authorized_total_nanodollars <= 0:
            raise ValueError("model authorization ceiling must be positive")
        if (
            self.externally_reconciled_prior_spend_nanodollars + self.lifetime_limit_nanodollars
            > self.authorized_total_nanodollars
        ):
            raise ValueError("model metered allowance exceeds the reconciled authorization")
        return self


class ModelBudgetProvisioningFacts(ModelCallValue):
    """Operator mutation facts for one immutable budget configuration version."""

    operation_id: UUID
    actor_profile_id: UUID
    spec: ProjectModelBudgetConfigurationSpec
    configuration_digest: Sha256

    @model_validator(mode="after")
    def exact_digest(self) -> Self:
        if self.configuration_digest != canonical_json_hash(self.spec.model_dump(mode="json")):
            raise ValueError("model budget configuration digest mismatch")
        return self


class ProjectModelBudgetConfiguration(ModelBudgetProvisioningFacts):
    """Published budget version plus lifetime counters retained on its project account."""

    configuration_id: UUID
    authorization_evidence_id: UUID
    created_at: AwareDatetime
    lifetime_reserved_nanodollars: Nanodollars
    lifetime_settled_nanodollars: Nanodollars

    @model_validator(mode="after")
    def canonical_record_id(self) -> Self:
        _require_uuid7(self.configuration_id, "model budget configuration ID")
        return self


class ModelUsageInspectionFacts(ModelCallValue):
    """Exact Operator read target committed before model-ledger inspection."""

    project_id: UUID
    effect_id: UUID
    actor_profile_id: UUID
    request_id: UUID

    _decode_public_uuids = field_validator(
        "project_id", "effect_id", "actor_profile_id", "request_id", mode="before"
    )(_public_uuid)


class ModelPaidSlotKey(ModelCallValue):
    """Paid-effect identity stable across checker leases and retry generations."""

    project_id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version: StrictInt = Field(ge=1)
    requirement_id: Identifier
    registry_entry_digest: Sha256
    configuration_sha256: Sha256
    profile_id: UUID
    profile_version: StrictInt = Field(ge=1)
    profile_digest: Sha256
    slot_index: StrictInt = Field(default=0, ge=0, le=99)

    _decode_public_uuids = field_validator(
        "project_id", "assignment_id", "submission_id", "profile_id", mode="before"
    )(_public_uuid)

    @model_validator(mode="after")
    def canonical_profile(self) -> Self:
        _require_uuid7(self.profile_id, "model profile ID")
        return self

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))

    @property
    def envelope_digest(self) -> str:
        """Commit the stable whole-run subject independently of a call index."""
        return canonical_json_hash(self.model_dump(mode="json", exclude={"slot_index"}))


class SetupModelUsageSlotKey(ModelCallValue):
    """Exact setup-owned provider dispatch identity allocated before I/O."""

    compilation_attempt_id: UUID
    project_id: UUID
    guide_id: UUID
    source_snapshot_id: UUID
    setup_run_id: UUID
    setup_generation: StrictInt = Field(ge=1)
    runtime_configuration_hash: Sha256
    profile_id: UUID
    profile_version: StrictInt = Field(ge=1)
    profile_digest: Sha256
    phase: Literal["draft", "review", "correction"]
    call_index: StrictInt = Field(ge=0, le=99)

    _decode_public_uuids = field_validator(
        "compilation_attempt_id",
        "project_id",
        "guide_id",
        "source_snapshot_id",
        "setup_run_id",
        "profile_id",
        mode="before",
    )(_public_uuid)

    @model_validator(mode="after")
    def canonical_records(self) -> Self:
        _require_uuid7(self.compilation_attempt_id, "guide compilation attempt ID")
        _require_uuid7(self.setup_run_id, "project setup run ID")
        _require_uuid7(self.profile_id, "model profile ID")
        return self

    @property
    def digest(self) -> str:
        """Commit the complete setup subject without provider request bytes."""
        return canonical_json_hash(self.model_dump(mode="json"))

    @property
    def envelope_digest(self) -> str:
        """Commit the setup attempt run independently of phase and call index."""
        return canonical_json_hash(self.model_dump(mode="json", exclude={"phase", "call_index"}))


class PreparedSetupModelUsageEffect(ModelCallValue):
    """Prepared setup effect allocated under exact attempt custody before I/O."""

    envelope_id: UUID
    slot_id: UUID
    slot_key: SetupModelUsageSlotKey
    effect_id: UUID
    attempt_number: StrictInt = Field(ge=1)
    internal_call_request_id: UUID
    request_sha256: Sha256
    state: Literal["prepared"] = "prepared"
    replayed: bool


class SetupModelEffectAuthorityFacts(ModelCallValue):
    """Exact setup-owned provider effect used by narrow observation authority."""

    project_id: UUID
    slot_id: UUID
    slot_key: SetupModelUsageSlotKey
    effect_id: UUID
    internal_call_request_id: UUID


class SetupModelDispatchReservation(ModelCallValue):
    """One setup provider dispatch reserved against shared project and run ceilings."""

    envelope_id: UUID
    slot_id: UUID
    slot_key: SetupModelUsageSlotKey
    effect_id: UUID
    attempt_number: StrictInt = Field(ge=1)
    internal_call_request_id: UUID
    effect: SetupModelEffectAuthorityFacts
    request_sha256: Sha256
    request_evidence: ModelCallEvidence
    budget_configuration_id: UUID
    budget_configuration_version: StrictInt = Field(ge=1)
    budget_configuration_digest: Sha256
    reserved_nanodollars: Nanodollars
    state: Literal["dispatching"] = "dispatching"
    replayed: bool

    @model_validator(mode="after")
    def exact_effect(self) -> Self:
        if (
            self.effect.project_id != self.slot_key.project_id
            or self.effect.slot_id != self.slot_id
            or self.effect.slot_key != self.slot_key
            or self.effect.effect_id != self.effect_id
            or self.effect.internal_call_request_id != self.internal_call_request_id
        ):
            raise ValueError("setup dispatch effect identity mismatch")
        return self


class ObservedSetupModelUsageEffect(ModelCallValue):
    """Durable ambiguous provider effect that keeps its full reservation."""

    effect: SetupModelEffectAuthorityFacts
    uncertainty_digest: Sha256
    provider_response_id: ProviderResponseIdentifier | None = None
    state: Literal["uncertain"] = "uncertain"
    replayed: bool


class SetupModelUsageAuthorityPort(Protocol):
    """PROJECTS-owned authorization for exact setup model-use mutations."""

    async def authorize_setup_prepare(
        self, slot: SetupModelUsageSlotKey, request_sha256: str
    ) -> ModelActionEvidence:
        """Authorize one preallocated setup call slot before owner locks."""
        ...

    async def authorize_setup_dispatch(
        self,
        prepared: PreparedSetupModelUsageEffect,
        request_evidence: ModelCallEvidence,
    ) -> ModelActionEvidence:
        """Authorize one verified setup provider dispatch before owner locks."""
        ...

    async def authorize_setup_observe(
        self,
        effect: SetupModelEffectAuthorityFacts,
        provider_response_id: str | None,
        observation_digest: str,
    ) -> ModelActionEvidence:
        """Authorize retention of one ambiguous provider observation."""
        ...

    async def authorize_setup_complete(
        self,
        effect: SetupModelEffectAuthorityFacts,
        response_evidence: ModelCallEvidence | None,
        terminal_digest: str,
    ) -> ModelActionEvidence:
        """Authorize exact terminal accounting or authenticated no-effect release."""
        ...


class SetupModelUsageEvidencePort(Protocol):
    """Verify private ART request evidence for an exact setup effect."""

    async def require_setup_request(
        self,
        prepared: PreparedSetupModelUsageEffect,
        evidence: ModelCallEvidence,
    ) -> None:
        """Require sealed bytes owned by the exact setup effect and request hash."""
        ...

    async def require_setup_response(self, effect_id: UUID, evidence: ModelCallEvidence) -> None:
        """Require sealed response bytes owned by the exact setup effect."""
        ...


class SetupModelOwnerProfile(ModelCallValue):
    """Exact profile and provider identity frozen by the PROJECTS attempt owner."""

    selector: ModelProfileSelector
    provider: ProviderIdentifier
    api: ProviderIdentifier
    model_snapshot: ProviderIdentifier


class SetupModelUsageOwnerPort(Protocol):
    """Require the exact current PROJECTS compilation attempt before MODEL locks."""

    async def require_setup_current(self, slot: SetupModelUsageSlotKey) -> SetupModelOwnerProfile:
        """Lock and validate the complete setup attempt ancestry."""
        ...


class ModelEvidenceSelector(ModelCallValue):
    """Owner-neutral selector for one checker request or response evidence slot."""

    paid_slot: ModelPaidSlotKey
    task_id: UUID
    model_call_slot_id: UUID
    model_call_attempt_id: UUID
    role: Literal["model_request", "model_response"]
    content_sha256: Sha256


class ModelEvidenceReservation(ModelCallValue):
    """Bound returned by the shared ledger after exact effect validation."""

    maximum_bytes: StrictInt = Field(ge=1, le=1_048_576)


class ModelEvidenceCustodyPort(Protocol):
    """Resolve shared ledger custody after the owner has taken its own locks."""

    async def resolve_evidence(self, selector: ModelEvidenceSelector) -> ModelEvidenceReservation:
        """Lock envelope, slot and effect and return the exact role bound."""
        ...


class SetupModelOutputSelector(ModelCallValue):
    """Select one private setup request or response by its exact paid effect."""

    slot_key: SetupModelUsageSlotKey
    model_call_slot_id: UUID
    model_call_attempt_id: UUID
    role: Literal["model_request", "model_response"]
    content_sha256: Sha256

    _decode_public_uuids = field_validator(
        "model_call_slot_id", "model_call_attempt_id", mode="before"
    )(_public_uuid)


class SetupModelOutputSlot(ModelCallValue):
    """One bounded canonical JSON role issued by the setup effect owner."""

    key: Literal["model_request", "model_response"]
    media_type: Literal["application/json"] = "application/json"
    maximum_bytes: StrictInt = Field(ge=1, le=1_048_576)


class SetupModelOutputReservation(ModelCallValue):
    """Detached setup owner facts, never fresh dispatch authority."""

    selector: SetupModelOutputSelector
    slot: SetupModelOutputSlot

    @model_validator(mode="after")
    def exact_role(self) -> Self:
        if self.slot.key != self.selector.role:
            raise ValueError("setup model output role differs from reservation")
        return self

    def select(self, selector: SetupModelOutputSelector) -> SetupModelOutputSlot:
        current = SetupModelOutputReservation.model_validate(self)
        if current.selector != SetupModelOutputSelector.model_validate(selector):
            raise ModelCallUnavailable("setup_model_output_reservation_unavailable")
        return current.slot


class SetupModelOutputReservationPort(Protocol):
    """Resolve current request or retained paid-effect response ART custody."""

    async def resolve(self, selector: SetupModelOutputSelector) -> SetupModelOutputReservation:
        """Return exact bounds after the role-specific owner checks."""
        ...


@dataclass(frozen=True, slots=True)
class SetupModelOutputArtifactRequest:
    """Bounded setup bytes admitted through the shared generated-output path."""

    selector: SetupModelOutputSelector
    byte_source: AsyncIterable[bytes]


@dataclass(frozen=True, slots=True)
class SetupModelOutputBindingRequest:
    """Bind one independently verified setup output to its paid effect."""

    selector: SetupModelOutputSelector
    put_attempt_id: UUID
    verification_receipt_id: UUID


@dataclass(frozen=True, slots=True)
class SetupModelOutputArtifactResult:
    put_attempt_id: UUID
    status: str
    content_id: UUID | None
    verification_receipt_id: UUID | None
    content_sha256: Sha256
    byte_count: int
    replayed: bool

    def __post_init__(self) -> None:
        if type(self.byte_count) is not int or not 0 <= self.byte_count <= 1_048_576:
            raise ValueError("setup model output byte count is invalid")


@dataclass(frozen=True, slots=True)
class SetupModelOutputBindingResult:
    binding_id: UUID
    content_id: UUID
    put_attempt_id: UUID
    verification_receipt_id: UUID
    replayed: bool


class SetupModelOutputBindingPort(Protocol):
    """Publish exact verified setup bytes under the paid effect owner."""

    async def bind_setup_output(
        self, request: SetupModelOutputBindingRequest
    ) -> SetupModelOutputBindingResult:
        """Bind one setup request or response in the caller transaction."""
        ...


class SetupModelArtifactOutputPort(Protocol):
    """Store and recover bounded setup output through shared ART custody."""

    async def store_setup_output(
        self, request: SetupModelOutputArtifactRequest
    ) -> SetupModelOutputArtifactResult:
        """Store one setup request or response."""
        ...

    async def recover_setup_output(
        self, selector: SetupModelOutputSelector
    ) -> SetupModelOutputArtifactResult | None:
        """Recover a committed setup output without regenerating bytes."""
        ...

    async def read_setup_response(
        self, selector: SetupModelOutputSelector, evidence: ModelCallEvidence
    ) -> bytes:
        """Read exact independently verified response bytes."""
        ...


class ModelRecoverySourcePort(Protocol):
    """Read retained recovery lineage without granting fresh owner authority."""

    async def recovery_owner(
        self, slot: ModelPaidSlotKey, parent_attempt_id: UUID
    ) -> ModelRecoveryOwnerFacts:
        """Resolve an exact terminal effect to its originating checker run."""
        ...

    async def recovery_candidates(
        self, source_run_ids: tuple[UUID, ...]
    ) -> dict[UUID, tuple[ModelRecoveryCandidate, ...]]:
        """Project retryable terminal effects for the requested retained runs."""
        ...


class ModelInvocationGrantAuthorityPort(Protocol):
    """Issue one bounded callback capability without authorizing provider spend."""

    async def authorize_grant(
        self,
        execution: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
        external_request_digest: str,
        token_hash: str,
    ) -> ModelActionEvidence:
        """Authorize the exact invocation, request binding and opaque token hash."""
        ...


class ModelCallExecutionFacts(ModelCallValue):
    """Current run/lease facts used only for authority and currentness checks."""

    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version: StrictInt = Field(ge=1)
    evaluation_request_id: UUID
    evaluation_generation: StrictInt = Field(ge=1)
    checker_run_id: UUID
    worker_lease_id: UUID
    worker_lease_generation: StrictInt = Field(ge=1)
    worker_lease_expires_at: AwareDatetime

    _decode_public_uuids = field_validator(
        "project_id",
        "task_id",
        "assignment_id",
        "submission_id",
        "evaluation_request_id",
        "checker_run_id",
        "worker_lease_id",
        mode="before",
    )(_public_uuid)
    _decode_public_expiry = field_validator("worker_lease_expires_at", mode="before")(
        _public_datetime
    )


class ModelRecoveryChildRequest(ModelCallValue):
    """Public Operator request for one exact known-terminal paid-call child."""

    slot: ModelPaidSlotKey
    registry_entry_id: UUID
    terminal_digest: Sha256
    request_sha256: Sha256

    _decode_public_uuid = field_validator("registry_entry_id", mode="before")(_public_uuid)

    @model_validator(mode="after")
    def canonical_registry(self) -> Self:
        _require_uuid7(self.registry_entry_id, "external checker registry entry ID")
        return self


class ModelRecoveryCandidate(ModelRecoveryChildRequest):
    """Exact terminal paid effect disclosed under existing Operator retry reads."""

    parent_attempt_id: UUID

    _decode_public_parent = field_validator("parent_attempt_id", mode="before")(_public_uuid)


class ModelCallEvidence(ModelCallValue):
    """Verified private ART identity; transcript bytes never cross this contract."""

    binding_id: UUID
    content_id: UUID
    put_attempt_id: UUID
    verification_receipt_id: UUID
    content_sha256: Sha256
    byte_count: StrictInt = Field(ge=1, le=1_048_576)
    media_type: Literal["application/json"] = "application/json"


class ModelCallEffectAuthorityFacts(ModelCallValue):
    """Exact paid effect identity supplied to AUTH for lease-independent observations."""

    project_id: UUID
    task_id: UUID
    slot_id: UUID
    slot_key: ModelPaidSlotKey
    attempt_id: UUID
    internal_call_request_id: UUID


class AttachedModelCallAttempt(ModelCallValue):
    """Existing stable effect attached to a fresh checker invocation."""

    slot_id: UUID
    slot_key: ModelPaidSlotKey
    attempt_id: UUID
    attempt_number: StrictInt = Field(ge=1)
    internal_call_request_id: UUID
    request_sha256: Sha256
    state: Literal[
        "prepared", "dispatching", "uncertain", "completed", "known_failed", "known_no_effect"
    ]
    replayed: bool


class PreparedModelCallAttempt(AttachedModelCallAttempt):
    """Server-owned attempt identity created before ART request evidence exists."""

    state: Literal["prepared"] = "prepared"


class ModelCallUsage(ModelCallValue):
    """Provider-observed token classes used for exact integer settlement."""

    input_tokens: StrictInt = Field(ge=0)
    cached_input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)
    reasoning_tokens: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def nested_classes(self) -> Self:
        if (
            self.cached_input_tokens > self.input_tokens
            or self.reasoning_tokens > self.output_tokens
        ):
            raise ValueError("model usage token classes are inconsistent")
        return self


class ModelDispatchReservation(ModelCallValue):
    """Committed dispatch intent and lifetime project-budget reservation."""

    slot_id: UUID
    attempt_id: UUID
    attempt_number: StrictInt = Field(ge=1)
    internal_call_request_id: UUID
    effect: ModelCallEffectAuthorityFacts
    request_sha256: Sha256
    request_evidence: ModelCallEvidence
    budget_configuration_id: UUID
    budget_configuration_version: StrictInt = Field(ge=1)
    budget_configuration_digest: Sha256
    reserved_nanodollars: Nanodollars
    state: Literal["dispatching", "uncertain", "completed"]
    provider_response_id: ProviderResponseIdentifier | None = None
    response_evidence: ModelCallEvidence | None = None
    replayed: bool


class ModelCallRecoveryAttachment(ModelCallValue):
    """Fresh authorized recovery access to one known provider effect."""

    slot_id: UUID
    attempt_id: UUID
    attempt_number: StrictInt = Field(ge=1)
    internal_call_request_id: UUID
    provider_response_id: ProviderResponseIdentifier
    state: Literal["dispatching", "uncertain"]
    replayed: bool


class CompletedModelCall(ModelCallValue):
    """Exact immutable response evidence and once-settled project cost."""

    slot_id: UUID
    attempt_id: UUID
    attempt_number: StrictInt = Field(ge=1)
    internal_call_request_id: UUID
    provider_response_id: ProviderResponseIdentifier
    request_evidence: ModelCallEvidence
    response_evidence: ModelCallEvidence
    usage: ModelCallUsage
    settled_nanodollars: Nanodollars
    completed_at: AwareDatetime
    replayed: bool


class KnownFailedModelCall(ModelCallValue):
    """Authenticated terminal provider effect without a usable model response."""

    slot_id: UUID
    attempt_id: UUID
    attempt_number: StrictInt = Field(ge=1)
    internal_call_request_id: UUID
    provider_response_id: ProviderResponseIdentifier
    request_evidence: ModelCallEvidence
    response_evidence: ModelCallEvidence
    usage: ModelCallUsage
    settled_nanodollars: Nanodollars
    completed_at: AwareDatetime
    replayed: bool


class KnownNoEffectProof(ModelCallValue):
    """Exact provider proof that an attempted create caused no billable effect."""

    proof_id: UUID
    proof_digest: Sha256
    observed_at: AwareDatetime


class CompletedSetupModelUsageEffect(ModelCallValue):
    """Exact retained setup response and once-settled project cost or unusable result."""

    effect: SetupModelEffectAuthorityFacts
    provider_response_id: ProviderResponseIdentifier
    request_evidence: ModelCallEvidence
    response_evidence: ModelCallEvidence
    usage: ModelCallUsage
    settled_nanodollars: Nanodollars
    completed_at: AwareDatetime
    state: Literal["completed", "known_failed"] = "completed"
    replayed: bool


class KnownNoEffectSetupModelUsageEffect(ModelCallValue):
    """Authenticated zero-effect terminal setup call with released reservation."""

    effect: SetupModelEffectAuthorityFacts
    proof: KnownNoEffectProof
    state: Literal["known_no_effect"] = "known_no_effect"
    replayed: bool


class ModelUsageEffectInspection(ModelCallValue):
    """Redacted exact-effect accounting and evidence identities for an Operator."""

    project_id: UUID
    effect_id: UUID
    owner_kind: Literal["checker", "setup"]
    owner: ModelPaidSlotKey | SetupModelUsageSlotKey
    attempt_number: StrictInt = Field(ge=1)
    state: Literal[
        "prepared", "dispatching", "uncertain", "completed", "known_failed", "known_no_effect"
    ]
    provider_response_known: bool
    request_evidence: ModelCallEvidence | None
    response_evidence: ModelCallEvidence | None
    usage: ModelCallUsage | None
    budget_configuration_id: UUID | None
    budget_configuration_version: StrictInt | None = Field(default=None, ge=1)
    budget_configuration_digest: Sha256 | None
    reserved_nanodollars: Nanodollars | None
    settled_nanodollars: Nanodollars | None
    uncertainty_digest: Sha256 | None
    prepared_at: AwareDatetime
    dispatched_at: AwareDatetime | None
    terminal_at: AwareDatetime | None

    @model_validator(mode="after")
    def exact_owner(self) -> Self:
        expected = "checker" if isinstance(self.owner, ModelPaidSlotKey) else "setup"
        if self.owner_kind != expected or self.owner.project_id != self.project_id:
            raise ValueError("model usage inspection owner mismatch")
        budget = (
            self.budget_configuration_id,
            self.budget_configuration_version,
            self.budget_configuration_digest,
            self.reserved_nanodollars,
        )
        if any(value is not None for value in budget) and not all(
            value is not None for value in budget
        ):
            raise ValueError("model usage inspection budget identity is incomplete")
        return self


def model_usage_instant(value: datetime) -> str:
    """Match PostgreSQL's canonical UTC timestamptz JSON spelling exactly."""
    utc = value.astimezone(UTC)
    rendered = utc.strftime("%Y-%m-%dT%H:%M:%S")
    if utc.microsecond:
        rendered += "." + f"{utc.microsecond:06d}".rstrip("0")
    return rendered + "+00:00"


def model_retry_terminal_digest(
    terminal: KnownFailedModelCall | KnownNoEffectProof,
) -> str:
    """Commit the exact terminal facts that may authorize a paid child attempt."""
    if isinstance(terminal, KnownNoEffectProof):
        facts = {
            "state": "known_no_effect",
            "proof_id": str(terminal.proof_id),
            "proof_digest": terminal.proof_digest,
            "observed_at": model_usage_instant(terminal.observed_at),
        }
    else:
        facts = {
            "state": "known_failed",
            "provider_response_id": terminal.provider_response_id,
            "response_content_sha256": terminal.response_evidence.content_sha256,
            "usage": terminal.usage.model_dump(mode="json"),
            "settled_nanodollars": terminal.settled_nanodollars,
        }
    return canonical_json_hash(facts)


class ModelActionEvidence(ModelCallValue):
    """Opaque exact AUTH decision returned to the model-call owner."""

    evidence_id: UUID
    facts_digest: Sha256


class ModelRecoveryOwnerFacts(ModelCallValue):
    """Retained checker lineage selected from an exact paid effect and grant."""

    checker_run_id: UUID
    task_id: UUID
    execution: ModelCallExecutionFacts
    request_sha256: Sha256


class ModelInvocationGrantFacts(ModelCallValue):
    """Immutable owner facts selected privately by the proxy, never image input."""

    token_hash: str = Field(repr=False)
    external_request_digest: Sha256
    execution: ModelCallExecutionFacts
    slot: ModelPaidSlotKey
    registry_entry_id: UUID


class ModelProfileReaderPort(Protocol):
    """Read immutable project profiles without mutation authority."""

    async def read_exact(
        self,
        selector: ModelProfileSelector,
        *,
        project_id: UUID,
    ) -> ProjectModelProfile:
        """Resolve the complete selector only for its exact project."""
        ...

    async def read_latest_matching(
        self,
        *,
        project_id: UUID,
        provider: str,
        api: str,
        model_snapshot: str,
    ) -> ProjectModelProfile:
        """Select the highest published version matching one configured identity."""
        ...


class ModelCallAdministrationPort(Protocol):
    """Own exact public profile, budget and recovery-child mutations."""

    async def provision_profile(self, facts: ModelProfileProvisioningFacts) -> ProjectModelProfile:
        """Authorize and retain immutable profile facts with exact operation replay."""
        ...

    async def provision_budget(
        self, facts: ModelBudgetProvisioningFacts
    ) -> ProjectModelBudgetConfiguration:
        """Publish a finite lifetime limit without resetting reserved or settled spend."""
        ...

    async def prepare_recovery_child(
        self,
        slot: ModelPaidSlotKey,
        *,
        registry_entry_id: UUID,
        parent_attempt_id: UUID,
        terminal_digest: str,
        request_sha256: str,
    ) -> PreparedModelCallAttempt:
        """Authorize a child of proven terminal failure without dispatching a provider call."""
        ...


class ModelUsageInspectionPort(Protocol):
    """Read one exact redacted paid effect without mutation authority."""

    async def inspect_effect(self, facts: ModelUsageInspectionFacts) -> ModelUsageEffectInspection:
        """Return the authorized effect only when it belongs to the exact project."""
        ...


class ModelCallCurrentExecutionPort(Protocol):
    """Require one current authorized checker execution without granting model effects."""

    async def require_current(self, facts: ModelCallExecutionFacts, slot: ModelPaidSlotKey) -> datetime:
        """Require current custody and return its database-timed live grant limit."""
        ...

    async def require_recovery_current(
        self, slot: ModelPaidSlotKey, parent_attempt_id: UUID
    ) -> None:
        """Lock current TASK/Submission custody without requiring a live worker lease."""
        ...


class ModelCallEvidencePort(Protocol):
    """Verify ART evidence belongs to the exact call attempt and role."""

    async def require_request(
        self, attempt: PreparedModelCallAttempt, evidence: ModelCallEvidence
    ) -> None:
        """Verify the exact attempt owns the sealed request bytes before dispatch."""
        ...

    async def require_response(self, attempt_id: UUID, evidence: ModelCallEvidence) -> None:
        """Verify sealed response evidence belongs to this attempt before settlement."""
        ...


class ModelCallAuthorityPort(Protocol):
    """Action-specific authority; implementations must reject phase substitution."""

    async def authorize_profile(self, facts: ModelProfileProvisioningFacts) -> ModelActionEvidence:
        """Bind profile publication authority to the project and complete immutable facts."""
        ...

    async def authorize_budget(self, facts: ModelBudgetProvisioningFacts) -> ModelActionEvidence:
        """Bind budget publication authority to the exact project and configuration."""
        ...

    async def authorize_usage_read(self, facts: ModelUsageInspectionFacts) -> ModelActionEvidence:
        """Bind an Operator read to one exact project and paid effect."""
        ...

    async def authorize_prepare(
        self,
        execution: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
        request_sha256: str,
    ) -> ModelActionEvidence:
        """Authorize request preparation for the current execution and stable paid slot."""
        ...

    async def authorize_dispatch(
        self,
        execution: ModelCallExecutionFacts,
        attempt: PreparedModelCallAttempt,
        request_evidence: ModelCallEvidence,
    ) -> ModelActionEvidence:
        """Authorize one provider effect using current execution and verified request evidence."""
        ...

    async def authorize_recover(
        self,
        execution: ModelCallExecutionFacts,
        effect: ModelCallEffectAuthorityFacts,
    ) -> ModelActionEvidence:
        """Authorize inspection of an existing effect without permitting another create."""
        ...

    async def authorize_observe(
        self,
        effect: ModelCallEffectAuthorityFacts,
        provider_response_id: str | None,
        observation_digest: str,
    ) -> ModelActionEvidence:
        """Authorize retention of exact provider observations independently of lease expiry."""
        ...

    async def authorize_child(
        self,
        project_id: UUID,
        parent_attempt_id: UUID,
        terminal_digest: str,
    ) -> ModelActionEvidence:
        """Authorize a recovery child only against the exact retained terminal digest."""
        ...

    async def authorize_complete(
        self,
        effect: ModelCallEffectAuthorityFacts,
        response_evidence: ModelCallEvidence | None,
        terminal_digest: str,
    ) -> ModelActionEvidence:
        """Authorize terminal accounting against the effect and its response evidence."""
        ...


def model_usage_cost(profile: ProjectModelProfileSpec, usage: ModelCallUsage) -> int:
    """Price disjoint token classes using exact integer nano-USD arithmetic."""
    usage = ModelCallUsage.model_validate(usage)
    if (
        usage.input_tokens > profile.maximum_input_tokens
        or usage.output_tokens > profile.maximum_output_tokens
    ):
        raise ModelCallConflict("model usage exceeds the approved profile")
    uncached = usage.input_tokens - usage.cached_input_tokens
    pricing = profile.pricing
    value = (
        uncached * pricing.uncached_input_nanodollars_per_token
        + usage.cached_input_tokens * pricing.cached_input_nanodollars_per_token
        + usage.output_tokens * pricing.output_nanodollars_per_token
    )
    if value < 0 or value > profile.maximum_reservation_nanodollars:
        raise ModelCallConflict("model usage cost exceeds the approved reservation")
    return value


def model_action_digest(action: str, facts: object) -> str:
    """Commit one action name and its complete typed facts for AUTH evidence."""
    if isinstance(facts, BaseModel):
        value = facts.model_dump(mode="json")
    else:
        value = facts
    return canonical_json_hash({"action": action, "facts": value})


__all__ = (
    "AttachedModelCallAttempt",
    "CompletedModelCall",
    "CompletedSetupModelUsageEffect",
    "KnownFailedModelCall",
    "KnownNoEffectProof",
    "KnownNoEffectSetupModelUsageEffect",
    "ModelActionEvidence",
    "ModelBudgetProvisioningFacts",
    "ModelCallAdministrationPort",
    "ModelCallAuthorityPort",
    "ModelCallBudgetUnavailable",
    "ModelCallConflict",
    "ModelCallCurrentExecutionPort",
    "ModelCallEffectAuthorityFacts",
    "ModelCallEvidence",
    "ModelCallEvidencePort",
    "ModelCallExecutionFacts",
    "ModelCallRecoveryAttachment",
    "ModelCallUnavailable",
    "ModelCallUsage",
    "ModelUsageEffectInspection",
    "ModelUsageInspectionFacts",
    "ModelUsageInspectionPort",
    "ModelDispatchReservation",
    "ModelEvidenceCustodyPort",
    "ModelEvidenceReservation",
    "ModelEvidenceSelector",
    "ModelGenerationSettings",
    "ModelInvocationGrantAuthorityPort",
    "ModelInvocationGrantFacts",
    "ModelPaidSlotKey",
    "ModelPricing",
    "ModelProfileProvisioningFacts",
    "ModelProfileReaderPort",
    "ModelProfileSelector",
    "ModelRecoveryCandidate",
    "ModelRecoveryChildRequest",
    "ModelRecoveryOwnerFacts",
    "ModelRecoverySourcePort",
    "ObservedSetupModelUsageEffect",
    "PreparedModelCallAttempt",
    "PreparedSetupModelUsageEffect",
    "ProjectModelBudgetConfiguration",
    "ProjectModelBudgetConfigurationSpec",
    "ProjectModelProfile",
    "ProjectModelProfileSpec",
    "SetupModelArtifactOutputPort",
    "SetupModelDispatchReservation",
    "SetupModelEffectAuthorityFacts",
    "SetupModelOutputArtifactRequest",
    "SetupModelOutputArtifactResult",
    "SetupModelOutputBindingPort",
    "SetupModelOutputBindingRequest",
    "SetupModelOutputBindingResult",
    "SetupModelOutputReservation",
    "SetupModelOutputReservationPort",
    "SetupModelOutputSelector",
    "SetupModelOutputSlot",
    "SetupModelOwnerProfile",
    "SetupModelUsageAuthorityPort",
    "SetupModelUsageEvidencePort",
    "SetupModelUsageOwnerPort",
    "SetupModelUsageSlotKey",
    "model_action_digest",
    "model_retry_terminal_digest",
    "model_usage_instant",
    "model_usage_cost",
)
