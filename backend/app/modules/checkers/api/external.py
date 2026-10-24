"""Normalized external-checker contracts; values never grant execution authority."""

from __future__ import annotations

import json
import hashlib
import unicodedata
from collections.abc import Mapping
from decimal import Decimal
from math import isfinite
from typing import Annotated, Literal, Protocol, Self
from uuid import RFC_4122, UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Identifier = Annotated[
    StrictStr, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$")
]
SchemaVersion = Annotated[
    StrictStr, Field(min_length=1, max_length=50, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
]
ExternalCheckerPhase = Literal["pre_submit", "post_submit"]
EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS = 60_000

PRE_SUBMIT_INPUT_SCHEMA_ID = "external_checker_pre_submit_input"
POST_SUBMIT_INPUT_SCHEMA_ID = "external_checker_post_submit_input"
RESULT_SCHEMA_ID = "external_checker_result"
EXTERNAL_CHECKER_REQUEST_SCHEMA_VERSION = "external_checker_request.v1"
EXTERNAL_CHECKER_RESULT_SCHEMA_VERSION = "external_checker_result.v1"
MAX_SCHEMA_BYTES = 65_536
MAX_CONFIGURATION_BYTES = 65_536
MAX_INPUT_BYTES = 1_048_576
MAX_RESULT_BYTES = 65_536


class ExternalCheckerContractError(ValueError):
    """Reject an ambiguous, mismatched or unbounded external-checker value."""


class ExternalCheckerRegistryUnavailable(RuntimeError):
    """Conceal denied authority or unavailable durable registry state."""


class ExternalCheckerRegistryConflict(ExternalCheckerRegistryUnavailable):
    """Reject replay or immutable identity substitution without partial effects."""


class ExternalCheckerRegistryAuthorizationDenied(ExternalCheckerRegistryUnavailable):
    """Conceal a current caller that lacks exact registry authority."""


class ExternalCheckerRegistryNotFound(ExternalCheckerRegistryUnavailable):
    """Conceal an absent exact registry identity."""


class ExternalCheckerValue(BaseModel):
    """Strict immutable values shared across the registry and execution protocol."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


def _canonical_json(value: object) -> str:
    """Match PostgreSQL JSONB canonical scalars without changing shared hashes."""
    if isinstance(value, Mapping):
        if any(type(key) is not str or "\x00" in key for key in value):
            raise ExternalCheckerContractError("external checker value is not canonical JSON")
        return (
            "{"
            + ",".join(
                f"{json.dumps(key, ensure_ascii=False)}:{_canonical_json(item)}"
                for key, item in sorted(value.items())
            )
            + "}"
        )
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if type(value) is float:
        if not isfinite(value):
            raise ExternalCheckerContractError("external checker value is not canonical JSON")
        if value == 0.0:
            return "0.0"
        return format(Decimal(str(value)), "f")
    if type(value) is str:
        if "\x00" in value:
            raise ExternalCheckerContractError("external checker value is not canonical JSON")
        return json.dumps(value, ensure_ascii=False)
    raise ExternalCheckerContractError("external checker value is not canonical JSON")


def _canonical_bytes(value: object) -> bytes:
    """Encode checker-owned canonical JSON for both digests and byte ceilings."""
    return _canonical_json(value).encode("utf-8")


def external_checker_json_hash(value: object) -> str:
    """Hash the checker-only canonical representation shared with PostgreSQL."""
    return f"sha256:{hashlib.sha256(_canonical_bytes(value)).hexdigest()}"


def _reject_remote_references(value: object) -> None:
    """Keep schema evaluation offline by permitting local JSON pointers only."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef"} and (
                type(item) is not str or not item.startswith("#/")
            ):
                raise ExternalCheckerContractError(
                    "external checker schema contains a non-local reference"
                )
            _reject_remote_references(item)
    elif isinstance(value, list):
        for item in value:
            _reject_remote_references(item)


class ExternalCheckerSchema(ExternalCheckerValue):
    """One bounded self-contained JSON Schema with an exact canonical identity."""

    schema_id: Identifier
    schema_version: SchemaVersion
    document: dict[str, JsonValue]
    schema_sha256: Sha256

    @model_validator(mode="after")
    def validate_schema(self) -> Self:
        """Reject oversized, remote, invalid or digest-substituted schemas."""
        if len(_canonical_bytes(self.document)) > MAX_SCHEMA_BYTES:
            raise ExternalCheckerContractError("external checker schema is too large")
        _reject_remote_references(self.document)
        try:
            Draft202012Validator.check_schema(self.document)
        except SchemaError as exc:
            raise ExternalCheckerContractError("external checker schema is invalid") from exc
        if self.schema_sha256 != external_checker_json_hash(self.document):
            raise ExternalCheckerContractError("external checker schema digest mismatch")
        return self

    def validate_instance(self, value: object) -> None:
        """Validate one detached JSON value without resolving remote material."""
        try:
            Draft202012Validator(self.document).validate(value)
        except ValidationError as exc:
            raise ExternalCheckerContractError(
                f"external checker {self.schema_id} value is invalid"
            ) from exc


class ExternalCheckerResourceLimits(ExternalCheckerValue):
    """Registry-owned finite resource ceilings, not representative defaults."""

    cpu_millis: Annotated[StrictInt, Field(ge=100, le=64_000)]
    memory_bytes: Annotated[StrictInt, Field(ge=16 * 1024 * 1024, le=64 * 1024**3)]
    deadline_ms: Annotated[StrictInt, Field(ge=100, le=3_600_000)]
    maximum_output_bytes: Annotated[StrictInt, Field(ge=256, le=MAX_RESULT_BYTES)]


class ExternalCheckerRegistrySpec(ExternalCheckerValue):
    """Canonical immutable definition supplied for one external image version."""

    capability_id: Identifier
    capability_version: SchemaVersion
    phase: ExternalCheckerPhase
    image_digest: Sha256
    configuration_schema: ExternalCheckerSchema
    input_schema: ExternalCheckerSchema
    output_schema: ExternalCheckerSchema
    resources: ExternalCheckerResourceLimits

    @model_validator(mode="after")
    def validate_protocol_schemas(self) -> Self:
        """Bind the registered input schema to its phase and one result schema."""
        expected_input = (
            PRE_SUBMIT_INPUT_SCHEMA_ID
            if self.phase == "pre_submit"
            else POST_SUBMIT_INPUT_SCHEMA_ID
        )
        if self.input_schema.schema_id != expected_input:
            raise ExternalCheckerContractError(
                "external checker input schema does not match its phase"
            )
        if self.output_schema.schema_id != RESULT_SCHEMA_ID:
            raise ExternalCheckerContractError("external checker result schema is invalid")
        return self

    @property
    def spec_digest(self) -> str:
        """Commit to every immutable registry field without a second representation."""
        return external_checker_json_hash(self.model_dump(mode="json"))


class ExternalCheckerRegistryEntry(ExternalCheckerRegistrySpec):
    """Published registry identity; publication does not authorize execution."""

    registry_entry_id: UUID = Field(strict=True)
    entry_digest: Sha256
    registration_operation_id: UUID = Field(strict=True)
    registered_by_actor_profile_id: UUID = Field(strict=True)
    authorization_decision_event_id: UUID = Field(strict=True)
    created_at: AwareDatetime

    @field_validator("registry_entry_id")
    @classmethod
    def validate_registry_entry_id(cls, value: UUID) -> UUID:
        """Require the server-selected registry identity to be canonical UUIDv7."""
        if value.version != 7 or value.variant != RFC_4122:
            raise ExternalCheckerContractError("external checker registry entry ID must be UUIDv7")
        return value

    @model_validator(mode="after")
    def validate_entry_digest(self) -> Self:
        """Recompute the immutable specification digest carried by the row."""
        spec = ExternalCheckerRegistrySpec.model_validate(
            self.model_dump(
                mode="json",
                exclude={
                    "registry_entry_id",
                    "entry_digest",
                    "registration_operation_id",
                    "registered_by_actor_profile_id",
                    "authorization_decision_event_id",
                    "created_at",
                },
            )
        )
        if self.entry_digest != spec.spec_digest:
            raise ExternalCheckerContractError("external checker entry digest mismatch")
        return self


class ExternalCheckerRegistrationCommand(ExternalCheckerValue):
    """Idempotent human command before the server selects a durable row ID."""

    actor_profile_id: UUID = Field(strict=True)
    operation_id: UUID = Field(strict=True)
    spec: ExternalCheckerRegistrySpec


class ExternalCheckerRegistrationPreparation(ExternalCheckerValue):
    """Stable command facts prepared before CHECKERS locks or selects a row."""

    actor_profile_id: UUID = Field(strict=True)
    operation_id: UUID = Field(strict=True)
    entry_digest: Sha256


class ExternalCheckerRegistrationAuthorityFacts(ExternalCheckerValue):
    """Exact immutable registration facts evaluated by AUTH."""

    actor_profile_id: UUID = Field(strict=True)
    operation_id: UUID = Field(strict=True)
    registry_entry_id: UUID = Field(strict=True)
    request_digest: Sha256
    entry_digest: Sha256


class ExternalCheckerRegistrationAuthorityReceipt(ExternalCheckerValue):
    """Opaque successful AUTH decision retained by the registry row."""

    actor_profile_id: UUID = Field(strict=True)
    authorization_decision_event_id: UUID = Field(strict=True)


class ExternalCheckerRegistrationAuthorityPort(Protocol):
    """Prepare and finalize one exact system-scoped registry publication."""

    async def prepare_registration(
        self, facts: ExternalCheckerRegistrationPreparation
    ) -> object:
        """Lock current actor, identity-link and system Operator authority."""

    async def consume_registration(
        self, prepared: object, preparation: ExternalCheckerRegistrationPreparation,
        facts: ExternalCheckerRegistrationAuthorityFacts,
    ) -> ExternalCheckerRegistrationAuthorityReceipt:
        """Finalize exact selected row facts and return durable allow evidence."""

    def close_registration(self, prepared: object) -> None:
        """Invalidate an unconsumed or consumed transaction-local capability."""

    async def prepare_read(self, actor_profile_id: UUID) -> None:
        """Lock and revalidate the current human actor before registry access."""

    async def authorize_read(
        self, facts: ExternalCheckerRegistrationAuthorityFacts
    ) -> None:
        """Authorize disclosure of one exact immutable registry entry."""


class ExternalCheckerRegistryPort(Protocol):
    """Hidden registry operation; policy and execution owners consume later."""

    async def register(
        self, command: ExternalCheckerRegistrationCommand
    ) -> ExternalCheckerRegistryEntry:
        """Publish or exactly replay one immutable authorized entry."""

    async def read_authorized(
        self, actor_profile_id: UUID, registry_entry_id: UUID
    ) -> ExternalCheckerRegistryEntry:
        """Read one exact immutable entry under current system Operator authority."""

    async def read_exact(
        self, registry_entry_id: UUID, entry_digest: str
    ) -> ExternalCheckerRegistryEntry:
        """Read one exact immutable entry without selecting a latest version."""

    async def read_identity(
        self, *, capability_id: str, capability_version: str, phase: ExternalCheckerPhase
    ) -> ExternalCheckerRegistryEntry:
        """Resolve the one immutable registered phase identity during approval."""

    async def list_entries(self) -> tuple[ExternalCheckerRegistryEntry, ...]:
        """Return every immutable identity in canonical phase/name/version order."""


def external_checker_registration_request_digest(
    command: ExternalCheckerRegistrationCommand, registry_entry_id: UUID,
) -> str:
    """Commit one server-selected row ID to the database's canonical request."""
    command = ExternalCheckerRegistrationCommand.model_validate(command)
    if (
        type(registry_entry_id) is not UUID
        or registry_entry_id.version != 7
        or registry_entry_id.variant != RFC_4122
    ):
        raise ExternalCheckerContractError(
            "external checker registry entry ID must be UUIDv7"
        )
    return external_checker_json_hash(
        {
            "actor_profile_id": str(command.actor_profile_id),
            "operation_id": str(command.operation_id),
            "registry_entry_id": str(registry_entry_id),
            "spec": command.spec.model_dump(mode="json"),
        }
    )


class ExternalCheckerCapabilityDefinition(ExternalCheckerValue):
    """One model-facing capability backed by code or an immutable registry row."""

    capability_id: Identifier
    capability_version: SchemaVersion
    phase: ExternalCheckerPhase
    selectable: bool
    registry_entry: ExternalCheckerRegistryEntry | None = None

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        """Keep the sole code-owned default distinct from selectable project images."""
        if self.selectable != (self.registry_entry is not None):
            raise ExternalCheckerContractError("external checker capability source is invalid")
        if self.registry_entry is not None and (
            self.capability_id,
            self.capability_version,
            self.phase,
        ) != (
            self.registry_entry.capability_id,
            self.registry_entry.capability_version,
            self.registry_entry.phase,
        ):
            raise ExternalCheckerContractError("external checker capability identity is invalid")
        return self


class ExternalCheckerCapabilityProjection(ExternalCheckerValue):
    """Complete immutable compiler input with one default and registered images."""

    schema_version: Literal["external_checker_capabilities.v1"] = "external_checker_capabilities.v1"
    definitions: tuple[ExternalCheckerCapabilityDefinition, ...]
    manifest_sha256: Sha256

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        identities = [
            (item.phase, item.capability_id, item.capability_version) for item in self.definitions
        ]
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            raise ExternalCheckerContractError(
                "external checker capability projection is not canonical"
            )
        defaults = [item for item in self.definitions if not item.selectable]
        if len(defaults) != 1 or (
            defaults[0].capability_id,
            defaults[0].capability_version,
            defaults[0].phase,
        ) != ("workstream.default", "v1", "pre_submit"):
            raise ExternalCheckerContractError("external checker default capability is invalid")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if self.manifest_sha256 != external_checker_json_hash(body):
            raise ExternalCheckerContractError(
                "external checker capability projection digest mismatch"
            )
        return self


class PreSubmitExternalCheckerMaterial(ExternalCheckerValue):
    """Verified prepared bytes that exist before a Submission or ART binding."""

    phase: Literal["pre_submit"] = "pre_submit"
    role: Identifier
    prepared_generation_id: UUID = Field(strict=True)
    attempt_id: UUID = Field(strict=True)
    attempt_request_digest: Sha256
    archive_sha256: Sha256
    archive_byte_count: Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]
    semantic_manifest_sha256: Sha256
    media_type: Annotated[
        StrictStr, Field(min_length=1, max_length=255, pattern=r"^[^\s/]+/[^\s/]+$")
    ]


class PostSubmitExternalCheckerMaterial(ExternalCheckerValue):
    """Verified native Submission and ART ancestry selected for POST execution."""

    phase: Literal["post_submit"] = "post_submit"
    role: Identifier
    submission_id: UUID = Field(strict=True)
    submission_version: Annotated[StrictInt, Field(ge=1)]
    binding_id: UUID = Field(strict=True)
    content_id: UUID = Field(strict=True)
    replica_id: UUID = Field(strict=True)
    content_sha256: Sha256
    byte_count: Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]
    media_type: Annotated[
        StrictStr, Field(min_length=1, max_length=255, pattern=r"^[^\s/]+/[^\s/]+$")
    ]
    evidence_id: UUID = Field(strict=True)
    verification_receipt_id: UUID = Field(strict=True)
    verification_job_id: UUID = Field(strict=True)
    verification_generation: Annotated[StrictInt, Field(ge=1)]
    namespace_fingerprint: Sha256
    semantic_manifest_sha256: Sha256


ExternalCheckerMaterial = Annotated[
    PreSubmitExternalCheckerMaterial | PostSubmitExternalCheckerMaterial,
    Field(discriminator="phase"),
]


class PreSubmitExternalCheckerIdentity(ExternalCheckerValue):
    """Existing pre-submit preparation and attempt identity; no Submission exists."""

    phase: Literal["pre_submit"] = "pre_submit"
    project_id: UUID = Field(strict=True)
    task_id: UUID = Field(strict=True)
    assignment_id: UUID = Field(strict=True)
    prepared_generation_id: UUID = Field(strict=True)
    attempt_id: UUID = Field(strict=True)
    attempt_request_digest: Sha256
    effective_plan_sha256: Sha256


class PostSubmitExternalCheckerIdentity(ExternalCheckerValue):
    """Existing post-submit request, reservation and current lease identity."""

    phase: Literal["post_submit"] = "post_submit"
    project_id: UUID = Field(strict=True)
    task_id: UUID = Field(strict=True)
    assignment_id: UUID = Field(strict=True)
    submission_id: UUID = Field(strict=True)
    submission_version: Annotated[StrictInt, Field(ge=1)]
    evaluation_request_id: UUID = Field(strict=True)
    evaluation_request_digest: Sha256
    evaluation_generation: Annotated[StrictInt, Field(ge=1)]
    attempt_id: UUID = Field(strict=True)
    result_id: UUID = Field(strict=True)
    lease_id: UUID = Field(strict=True)
    lease_generation: Annotated[StrictInt, Field(ge=1)]
    lease_expires_at: AwareDatetime


ExternalCheckerExecutionIdentity = Annotated[
    PreSubmitExternalCheckerIdentity | PostSubmitExternalCheckerIdentity,
    Field(discriminator="phase"),
]


class ExternalCheckerExecutionRequest(ExternalCheckerValue):
    """One bounded normalized invocation selected by a later owner operation."""

    schema_version: Literal["external_checker_request.v1"] = EXTERNAL_CHECKER_REQUEST_SCHEMA_VERSION
    registry: ExternalCheckerRegistryEntry
    identity: ExternalCheckerExecutionIdentity
    configuration: dict[str, JsonValue]
    configuration_sha256: Sha256
    input: dict[str, JsonValue]
    input_sha256: Sha256
    materials: tuple[ExternalCheckerMaterial, ...] = Field(min_length=1, max_length=32)
    request_digest: Sha256

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        """Close phase, material, schema, size and digest request commitments."""
        if self.registry.phase != self.identity.phase:
            raise ExternalCheckerContractError("external checker request phase mismatch")
        if len({item.role for item in self.materials}) != len(self.materials):
            raise ExternalCheckerContractError("external checker material role is duplicated")
        if any(item.phase != self.identity.phase for item in self.materials):
            raise ExternalCheckerContractError("external checker material phase mismatch")
        if self.identity.phase == "pre_submit":
            for material in self.materials:
                if not isinstance(material, PreSubmitExternalCheckerMaterial) or (
                    material.prepared_generation_id,
                    material.attempt_id,
                    material.attempt_request_digest,
                ) != (
                    self.identity.prepared_generation_id,
                    self.identity.attempt_id,
                    self.identity.attempt_request_digest,
                ):
                    raise ExternalCheckerContractError(
                        "external checker prepared material identity mismatch"
                    )
        if self.configuration_sha256 != external_checker_json_hash(self.configuration):
            raise ExternalCheckerContractError("external checker configuration digest mismatch")
        if self.input_sha256 != external_checker_json_hash(self.input):
            raise ExternalCheckerContractError("external checker input digest mismatch")
        if len(_canonical_bytes(self.configuration)) > MAX_CONFIGURATION_BYTES:
            raise ExternalCheckerContractError("external checker configuration is too large")
        if len(_canonical_bytes(self.input)) > MAX_INPUT_BYTES:
            raise ExternalCheckerContractError("external checker input is too large")
        self.registry.configuration_schema.validate_instance(self.configuration)
        self.registry.input_schema.validate_instance(self.input)
        body = self.model_dump(mode="json", exclude={"request_digest"})
        if self.request_digest != external_checker_json_hash(body):
            raise ExternalCheckerContractError("external checker request digest mismatch")
        # The semantic projection reuses the normalized result contracts, which
        # depend on this wire module. Import after its definitions are loaded.
        from app.modules.checkers.api.evaluation_context import validate_post_evaluation_materials
        from app.modules.checkers.api.external_policy import selected_evaluation_context_roles
        if self.identity.phase == "post_submit":
            validate_post_evaluation_materials(self)
        else:
            selected_evaluation_context_roles(self.configuration, self.identity.phase)
            if "evaluation_context" in self.input:
                raise ExternalCheckerContractError("PRE cannot contain evaluation context")
        return self


ExternalCheckerFindingLevel = Literal["info", "warning", "error", "coverage_incomplete"]


class ExternalCheckerFinding(ExternalCheckerValue):
    """Sanitized work result; policy later decides whether failure blocks.

    ``coverage_incomplete`` reports work the checker could not evaluate. It never
    fails the verdict or costs a revision round; locked ReviewPolicy routing sends
    it to a reviewer or back to the contributor.
    """

    check_id: Identifier
    code: Identifier
    level: ExternalCheckerFindingLevel
    message: Annotated[StrictStr, Field(min_length=1, max_length=4096)]
    path: Annotated[StrictStr, Field(min_length=1, max_length=1000)] | None = None
    line: Annotated[StrictInt, Field(ge=1, le=10_000_000)] | None = None

    @model_validator(mode="after")
    def validate_location(self) -> Self:
        """A location names one safe relative archive path and, optionally, a line in it."""
        if self.path is not None and not safe_finding_path(self.path):
            raise ExternalCheckerContractError("external checker finding path is unsafe")
        if self.line is not None and self.path is None:
            raise ExternalCheckerContractError("external checker finding line requires a path")
        return self


def safe_finding_path(path: str) -> bool:
    """Accept only a relative archive path that intake could have admitted.

    Paths are shown to contributors and managers, so they must not carry
    control or formatting characters, traversal or absolute forms.
    """
    parts = path.split("/")
    return not (
        "\\" in path or path.startswith("/")
        or any(unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
               for character in path)
        or any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts)
        or ":" in parts[0]
    )


class ExternalCheckerExecutionResult(ExternalCheckerValue):
    """Normalized completed or infrastructure result bound to one exact request."""

    schema_version: Literal["external_checker_result.v1"] = EXTERNAL_CHECKER_RESULT_SCHEMA_VERSION
    request_digest: Sha256
    registry_entry_id: UUID = Field(strict=True)
    registry_entry_digest: Sha256
    phase: ExternalCheckerPhase
    outcome: Literal["completed", "infrastructure_failed"]
    verdict: Literal["passed", "failed"] | None
    findings: tuple[ExternalCheckerFinding, ...] = Field(max_length=256)
    infrastructure_failure_code: (
        Literal[
            "capacity_exceeded",
            "deadline_exceeded",
            "material_unavailable",
            "implementation_unavailable",
            "invalid_output",
        ]
        | None
    ) = None
    result_digest: Sha256

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        """Keep work verdicts distinct from bounded infrastructure outcomes."""
        if self.outcome == "infrastructure_failed":
            if (
                self.verdict is not None
                or self.findings
                or self.infrastructure_failure_code is None
            ):
                raise ExternalCheckerContractError(
                    "external checker infrastructure result shape is invalid"
                )
        else:
            if self.verdict is None or self.infrastructure_failure_code is not None:
                raise ExternalCheckerContractError(
                    "external checker completed result shape is invalid"
                )
            has_error = any(item.level == "error" for item in self.findings)
            if (self.verdict == "failed") != has_error:
                raise ExternalCheckerContractError("external checker verdict and findings disagree")
        body = self.model_dump(mode="json", exclude={"result_digest"})
        if len(_canonical_bytes(body)) > MAX_RESULT_BYTES:
            raise ExternalCheckerContractError("external checker result is too large")
        if self.result_digest != external_checker_json_hash(body):
            raise ExternalCheckerContractError("external checker result digest mismatch")
        return self

    def validate_request(self, request: ExternalCheckerExecutionRequest) -> None:
        """Require the complete registry and request identity without claiming custody."""
        result = ExternalCheckerExecutionResult.model_validate(self)
        request = ExternalCheckerExecutionRequest.model_validate(request)
        if (
            result.request_digest,
            result.registry_entry_id,
            result.registry_entry_digest,
            result.phase,
        ) != (
            request.request_digest,
            request.registry.registry_entry_id,
            request.registry.entry_digest,
            request.identity.phase,
        ):
            raise ExternalCheckerContractError("external checker result request mismatch")
        if result.outcome == "completed":
            request.registry.output_schema.validate_instance(
                result.model_dump(mode="json", exclude={"result_digest"})
            )
        if len(_canonical_bytes(result.model_dump(mode="json"))) > (
            request.registry.resources.maximum_output_bytes
        ):
            raise ExternalCheckerContractError("external checker result exceeds registry limit")


_REQUEST_FIELDS = {
    name: TypeAdapter(field.rebuild_annotation())
    for name, field in ExternalCheckerExecutionRequest.model_fields.items()
}
_RESULT_FIELDS = {
    name: TypeAdapter(field.rebuild_annotation())
    for name, field in ExternalCheckerExecutionResult.model_fields.items()
}


def _make_derived(model, adapters, digest_field: str, fields: dict[str, object]):
    """Validate caller fields and derive the one non-caller-selected digest."""
    if digest_field in fields:
        raise ExternalCheckerContractError(f"{digest_field} is derived, not caller selected")
    values = {
        name: adapters[name].validate_python(value) if name in adapters else value
        for name, value in fields.items()
    }
    candidate = model.model_construct(**values, **{digest_field: "sha256:" + "0" * 64})
    values[digest_field] = external_checker_json_hash(
        candidate.model_dump(mode="json", exclude={digest_field})
    )
    return model.model_validate(values)


def make_external_checker_execution_request(
    **fields: object,
) -> ExternalCheckerExecutionRequest:
    """Build one external execution request with a derived canonical digest."""
    return _make_derived(ExternalCheckerExecutionRequest, _REQUEST_FIELDS, "request_digest", fields)


def make_external_checker_execution_result(
    **fields: object,
) -> ExternalCheckerExecutionResult:
    """Build one normalized result with a derived canonical digest."""
    return _make_derived(ExternalCheckerExecutionResult, _RESULT_FIELDS, "result_digest", fields)
