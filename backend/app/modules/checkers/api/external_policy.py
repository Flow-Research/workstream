"""Locked external-checker policies compiled from approved guide bindings."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Literal, Self, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WORKSTREAM_DEFAULT_CHECKER_ID,
    WORKSTREAM_DEFAULT_CHECKER_VERSION,
)
from app.modules.checkers.api.external import (
    MAX_CONFIGURATION_BYTES,
    EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS,
    ExternalCheckerPhase,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistryPort,
    external_checker_json_hash,
)
from app.interfaces.forge_facts import (
    FORGE_FACTS_MAXIMUM_READ_MS,
    SUPPORTED_FORGES,
    is_forge_origin,
    is_repository_path,
)
from app.modules.model_usage.api import ModelProfileReaderPort
from app.modules.checkers.api.model_profiles import (
    ModelProfileConfigurationError,
    configured_model_profile_selector,
    require_model_profile_configuration,
)
from app.modules.checkers.api.trial_profiles import (
    TrialProfileError,
    trial_selector_from_configuration,
)


WORKSTREAM_DEFAULT_EXECUTION_BUDGET_MS = 60_000
MAXIMUM_SELECTED_PRE_EXECUTION_BUDGET_MS = 7_200_000
SELECTED_POST_MATERIALIZATION_BUDGET_MS = 60_000
# The outbox claim is natively bounded to one hour. Keep explicit time for the
# request reader/authority prelude, execution finalization and delivery commit.
MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS = 3_400_000
SELECTED_POST_HANDLER_PRELUDE_MARGIN_MS = 60_000
SELECTED_POST_FINALIZATION_MARGIN_MS = 60_000
SELECTED_POST_HANDLER_TIMEOUT_SECONDS = (
    MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS
    + SELECTED_POST_HANDLER_PRELUDE_MARGIN_MS
    + SELECTED_POST_FINALIZATION_MARGIN_MS
) // 1000
SELECTED_POST_DELIVERY_LEASE_SECONDS = 3_600

EVALUATION_CONTEXT_VERSION_KEY = "workstream_evaluation_context_version"
EVALUATION_CONTEXT_ROLES_KEY = "workstream_evaluation_context_roles"
EvaluationContextRole = Literal["predecessor_findings", "predecessor_submission_archive"]
EVALUATION_CONTEXT_ROLES = get_args(EvaluationContextRole)
FORGE_FACTS_VERSION_KEY = "workstream_forge_facts_version"
FORGE_FACTS_FORGE_KEY = "forge"
FORGE_FACTS_ORIGIN_KEY = "forge_origin"
FORGE_FACTS_REPOSITORY_KEY = "repository"
FORGE_FACTS_BASE_BRANCH_KEY = "base_branch"
# Provider settings cap one forge facts read; reserve that maximum per selection.
SELECTED_POST_FORGE_FACTS_BUDGET_MS = FORGE_FACTS_MAXIMUM_READ_MS


class ExternalCheckerPolicyError(ValueError):
    """Reject incomplete, stale or phase-substituted locked checker policy."""


def selected_evaluation_context_roles(
    configuration: dict[str, JsonValue],
    phase: ExternalCheckerPhase,
) -> tuple[str, ...] | None:
    """Select approved historical material only through an exact POST capability."""
    keys = {key for key in configuration if key.startswith("workstream_evaluation_context_")}
    if not keys:
        return None
    if keys != {EVALUATION_CONTEXT_VERSION_KEY, EVALUATION_CONTEXT_ROLES_KEY}:
        raise ExternalCheckerPolicyError("evaluation context selection is incomplete or unknown")
    roles = configuration[EVALUATION_CONTEXT_ROLES_KEY]
    if (
        phase != "post_submit"
        or configuration[EVALUATION_CONTEXT_VERSION_KEY] != "v1"
        or type(roles) is not list
        or any(type(role) is not str or role not in EVALUATION_CONTEXT_ROLES for role in roles)
        or roles != sorted(set(roles))
    ):
        raise ExternalCheckerPolicyError("evaluation context selection is invalid")
    return tuple(roles)


def validated_evaluation_context_roles(
    configuration: dict[str, JsonValue],
    registry: ExternalCheckerRegistryEntry,
) -> tuple[str, ...] | None:
    """Require the immutable checker schema to declare any selected context capability."""
    selected = selected_evaluation_context_roles(configuration, registry.phase)
    if selected is not None:
        properties = registry.configuration_schema.document.get("properties")
        if not isinstance(properties, dict) or not {
            EVALUATION_CONTEXT_VERSION_KEY,
            EVALUATION_CONTEXT_ROLES_KEY,
        }.issubset(properties):
            raise ExternalCheckerPolicyError("checker schema does not declare evaluation context")
    return selected


def require_evaluation_context_agreement(
    declared_roles: tuple[EvaluationContextRole, ...] | None,
    configuration: dict[str, JsonValue],
    registry: ExternalCheckerRegistryEntry,
) -> None:
    """Match descriptive setup inputs to the exact supported registry selection."""
    selected = validated_evaluation_context_roles(configuration, registry)
    if declared_roles != selected:
        raise ExternalCheckerPolicyError("evaluation context declaration and selection disagree")


@dataclass(frozen=True, slots=True)
class ForgeFactsSelection:
    """The forge instance, repository and base branch a POST binding asks WorkStream to read."""

    forge: str
    forge_origin: str
    repository: str
    base_branch: str


def selected_forge_facts(
    configuration: dict[str, JsonValue],
    phase: ExternalCheckerPhase,
) -> ForgeFactsSelection | None:
    """Select forge change facts only through an exact POST capability."""
    if FORGE_FACTS_VERSION_KEY not in configuration:
        return None
    forge = configuration.get(FORGE_FACTS_FORGE_KEY)
    forge_origin = configuration.get(FORGE_FACTS_ORIGIN_KEY)
    repository = configuration.get(FORGE_FACTS_REPOSITORY_KEY)
    base_branch = configuration.get(FORGE_FACTS_BASE_BRANCH_KEY)
    if (
        phase != "post_submit"
        or configuration[FORGE_FACTS_VERSION_KEY] != "v1"
        or forge not in SUPPORTED_FORGES
        or not is_forge_origin(forge_origin)
        or not is_repository_path(repository)
        or type(base_branch) is not str
        or not 1 <= len(base_branch) <= 255
    ):
        raise ExternalCheckerPolicyError("forge facts selection is invalid")
    return ForgeFactsSelection(
        forge=forge, forge_origin=forge_origin, repository=repository, base_branch=base_branch
    )


def validated_forge_facts(
    configuration: dict[str, JsonValue],
    registry: ExternalCheckerRegistryEntry,
) -> ForgeFactsSelection | None:
    """Require the immutable checker schema to declare any selected facts capability."""
    selected = selected_forge_facts(configuration, registry.phase)
    if selected is not None:
        properties = registry.configuration_schema.document.get("properties")
        if not isinstance(properties, dict) or FORGE_FACTS_VERSION_KEY not in properties:
            raise ExternalCheckerPolicyError("checker schema does not declare forge facts")
    return selected


def validated_trial_configuration(configuration, registry):
    """Select only an explicitly declared POST trial capability, never a partial pin."""
    try:
        selector = trial_selector_from_configuration(configuration)
    except TrialProfileError as exc:
        raise ExternalCheckerPolicyError(str(exc)) from exc
    if selector is None:
        return None
    if registry.phase != "post_submit":
        raise ExternalCheckerPolicyError("trial execution requires post-submit work")
    properties = registry.configuration_schema.document.get("properties")
    selected_keys = {key for key in configuration if key.startswith("trial_")}
    if not isinstance(properties, dict) or not selected_keys.issubset(properties):
        raise ExternalCheckerPolicyError("checker schema does not declare trial execution")
    return selector


class _PolicyValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class ExternalCheckerImageAttachment(_PolicyValue):
    """One human-selected execution member of a project's PRE or POST phase."""

    requirement_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$", strict=True)
    registry_entry_id: UUID
    registry_entry_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$", strict=True)
    configuration: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_attachment(self) -> Self:
        if self.requirement_id.startswith("workstream."):
            raise ExternalCheckerPolicyError("platform checker key cannot be selected")
        if self.registry_entry_id.version != 7:
            raise ExternalCheckerPolicyError("selected registry entry ID must be UUIDv7")
        if len(json.dumps(self.configuration, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_CONFIGURATION_BYTES:
            raise ExternalCheckerPolicyError("selected checker configuration exceeds byte limit")
        return self


class ExternalCheckerPolicyCompileRequest(_PolicyValue):
    """Phase-separated project images, independent of setup suggestions."""

    pre_submit_attachments: tuple[ExternalCheckerImageAttachment, ...] = Field(max_length=200)
    post_submit_attachments: tuple[ExternalCheckerImageAttachment, ...] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        for attachments in (self.pre_submit_attachments, self.post_submit_attachments):
            keys = [item.requirement_id for item in attachments]
            if keys != sorted(set(keys)):
                raise ExternalCheckerPolicyError("image attachments must have unique canonical order")
        return self


class LockedExternalCheckerBinding(_PolicyValue):
    """One requirement bound to an exact immutable registry publication."""

    requirement_id: str = Field(min_length=1, max_length=100)
    stage: ExternalCheckerPhase
    registry: ExternalCheckerRegistryEntry
    configuration: dict[str, JsonValue]
    configuration_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if self.registry.phase != self.stage:
            raise ExternalCheckerPolicyError("checker binding phase mismatch")
        self.registry.configuration_schema.validate_instance(self.configuration)
        validated_evaluation_context_roles(self.configuration, self.registry)
        validated_forge_facts(self.configuration, self.registry)
        validated_trial_configuration(self.configuration, self.registry)
        try:
            configured_model_profile_selector(self.configuration, stage=self.stage)
        except ModelProfileConfigurationError as exc:
            raise ExternalCheckerPolicyError(str(exc)) from exc
        if self.configuration_sha256 != external_checker_json_hash(self.configuration):
            raise ExternalCheckerPolicyError("checker binding configuration mismatch")
        return self


class LockedWorkstreamDefault(_PolicyValue):
    """Code-owned default identity included in every approved pre policy."""

    checker_id: Literal[WORKSTREAM_DEFAULT_CHECKER_ID] = WORKSTREAM_DEFAULT_CHECKER_ID
    checker_version: Literal[WORKSTREAM_DEFAULT_CHECKER_VERSION] = (
        WORKSTREAM_DEFAULT_CHECKER_VERSION
    )
    behavior_sha256: str = Field(
        default=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_behavior(self) -> Self:
        """Bind the locked identity to the executable code-owned manifest."""
        if self.behavior_sha256 != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256:
            raise ExternalCheckerPolicyError("default checker behavior mismatch")
        return self


class LockedExternalPreSubmitPolicy(_PolicyValue):
    """One default followed by every required project pre-submit image."""

    schema_version: Literal["external_pre_submit_policy.v1"] = "external_pre_submit_policy.v1"
    workstream_default: LockedWorkstreamDefault = Field(default_factory=LockedWorkstreamDefault)
    entries: tuple[LockedExternalCheckerBinding, ...]
    policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        _validate_entries(self.entries, "pre_submit")
        if self.policy_sha256 != canonical_json_hash(
            self.model_dump(mode="json", exclude={"policy_sha256"})
        ):
            raise ExternalCheckerPolicyError("pre-submit policy digest mismatch")
        selected_pre_submit_execution_budget_ms(
            self, artifact_deadline_ms=MAXIMUM_SELECTED_PRE_EXECUTION_BUDGET_MS
        )
        return self


class LockedExternalPostSubmitPolicy(_PolicyValue):
    """Every required post-submit image; checkers retain no acceptance authority."""

    schema_version: Literal["external_post_submit_policy.v1"] = "external_post_submit_policy.v1"
    entries: tuple[LockedExternalCheckerBinding, ...]
    policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        _validate_entries(self.entries, "post_submit")
        if self.policy_sha256 != canonical_json_hash(
            self.model_dump(mode="json", exclude={"policy_sha256"})
        ):
            raise ExternalCheckerPolicyError("post-submit policy digest mismatch")
        # Approval, admission and dispatch share this closed runnable policy.
        selected_post_submit_execution_budget_ms(self)
        return self


class LockedExternalCheckerPolicies(_PolicyValue):
    """Complete approval-time pre/post policy custody for one guide generation."""

    schema_version: Literal["external_checker_policies.v1"] = "external_checker_policies.v1"
    pre_submit: LockedExternalPreSubmitPolicy
    post_submit: LockedExternalPostSubmitPolicy
    policies_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_policies(self) -> Self:
        if self.policies_sha256 != canonical_json_hash(
            self.model_dump(mode="json", exclude={"policies_sha256"})
        ):
            raise ExternalCheckerPolicyError("checker policies digest mismatch")
        return self


def validate_stored_external_checker_policies(
    value: object,
) -> LockedExternalCheckerPolicies:
    """Decode retained JSON through strict UUID and timestamp model boundaries."""
    return LockedExternalCheckerPolicies.model_validate_json(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    )


def validate_stored_external_pre_policy(value: object) -> LockedExternalPreSubmitPolicy:
    """Decode one retained selected PRE policy without Python-string coercion."""
    return LockedExternalPreSubmitPolicy.model_validate_json(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    )


def validate_stored_external_post_policy(value: object) -> LockedExternalPostSubmitPolicy:
    """Decode one retained selected POST policy without Python-string coercion."""
    return LockedExternalPostSubmitPolicy.model_validate_json(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    )


def _validate_entries(
    entries: tuple[LockedExternalCheckerBinding, ...], phase: ExternalCheckerPhase
) -> None:
    identities = [
        (
            item.requirement_id,
            item.registry.capability_id,
            item.registry.capability_version,
        )
        for item in entries
    ]
    if any(item.stage != phase for item in entries) or identities != sorted(identities):
        raise ExternalCheckerPolicyError("checker policy order is not canonical")
    if len(identities) != len(set(identities)):
        raise ExternalCheckerPolicyError("checker policy binding is duplicated")
    if len({item.requirement_id for item in entries}) != len(entries):
        raise ExternalCheckerPolicyError("checker execution member key is duplicated")


async def compile_external_checker_policies(
    request: ExternalCheckerPolicyCompileRequest,
    registry: ExternalCheckerRegistryPort,
    *,
    project_id: UUID | None = None,
    profiles: ModelProfileReaderPort | None = None,
) -> tuple[LockedExternalPreSubmitPolicy, LockedExternalPostSubmitPolicy]:
    """Resolve exact human image attachments, independent of setup suggestions."""
    request = ExternalCheckerPolicyCompileRequest.model_validate(request)
    pre = await _resolve_attachments(
        request.pre_submit_attachments, registry, "pre_submit",
        project_id=project_id, profiles=profiles,
    )
    post = await _resolve_attachments(
        request.post_submit_attachments, registry, "post_submit",
        project_id=project_id, profiles=profiles,
    )
    return _make_policy(LockedExternalPreSubmitPolicy, pre), _make_policy(
        LockedExternalPostSubmitPolicy, post
    )


async def compile_external_checker_policy_bundle(
    request: ExternalCheckerPolicyCompileRequest,
    registry: ExternalCheckerRegistryPort,
    *,
    project_id: UUID | None = None,
    profiles: ModelProfileReaderPort | None = None,
) -> LockedExternalCheckerPolicies:
    """Lock both execution phases into one immutable approval-time value."""
    pre, post = await compile_external_checker_policies(
        request, registry, project_id=project_id, profiles=profiles,
    )
    body = {
        "schema_version": "external_checker_policies.v1",
        "pre_submit": pre.model_dump(mode="json"),
        "post_submit": post.model_dump(mode="json"),
    }
    return LockedExternalCheckerPolicies(
        pre_submit=pre,
        post_submit=post,
        policies_sha256=canonical_json_hash(body),
    )


async def _resolve_attachments(
    attachments: tuple[ExternalCheckerImageAttachment, ...],
    registry: ExternalCheckerRegistryPort,
    phase: ExternalCheckerPhase,
    *,
    project_id: UUID | None,
    profiles: ModelProfileReaderPort | None,
) -> tuple[LockedExternalCheckerBinding, ...]:
    from app.modules.checkers.api.external import ExternalCheckerRegistryUnavailable

    resolved = []
    for attachment in attachments:
        try:
            entry = await registry.read_exact(
                attachment.registry_entry_id, attachment.registry_entry_digest,
            )
        except ExternalCheckerRegistryUnavailable as exc:
            raise ExternalCheckerPolicyError("selected checker registry entry is unavailable") from exc
        if (
            entry.registry_entry_id != attachment.registry_entry_id
            or entry.entry_digest != attachment.registry_entry_digest
            or entry.phase != phase
        ):
            raise ExternalCheckerPolicyError("selected checker registry identity or phase mismatch")
        configuration = attachment.configuration
        entry.configuration_schema.validate_instance(configuration)
        validated_evaluation_context_roles(configuration, entry)
        if validated_forge_facts(configuration, entry) is not None:
            # New bindings must support location; retained policy facts keep their locked shape.
            inputs = entry.input_schema.document.get("properties", {})
            if (
                not isinstance(inputs, dict)
                or not isinstance(inputs.get("workstream_forge_facts_stage"), dict)
                or inputs["workstream_forge_facts_stage"].get("const") != "locate"
            ):
                raise ExternalCheckerPolicyError("checker input schema does not declare forge locator")
        validated_trial_configuration(configuration, entry)
        try:
            selector = configured_model_profile_selector(configuration, stage=phase)
            if selector is not None:
                if project_id is None:
                    raise ModelProfileConfigurationError("model profile project is unavailable")
                await require_model_profile_configuration(
                    configuration, stage=phase, project_id=project_id,
                    registry=entry, profiles=profiles,
                )
        except ModelProfileConfigurationError as exc:
            raise ExternalCheckerPolicyError(str(exc)) from exc
        resolved.append(
            LockedExternalCheckerBinding(
                requirement_id=attachment.requirement_id,
                stage=phase,
                registry=entry,
                configuration=configuration,
                configuration_sha256=external_checker_json_hash(configuration),
            )
        )
    return tuple(resolved)


async def require_locked_model_profiles(
    policies: LockedExternalCheckerPolicies,
    *,
    project_id: UUID,
    profiles: ModelProfileReaderPort | None,
) -> None:
    """Revalidate every exact selected profile before readiness or activation."""
    policies = LockedExternalCheckerPolicies.model_validate(policies)
    for binding in (*policies.pre_submit.entries, *policies.post_submit.entries):
        try:
            await require_model_profile_configuration(
                binding.configuration,
                stage=binding.stage,
                project_id=project_id,
                registry=binding.registry,
                profiles=profiles,
            )
        except ModelProfileConfigurationError as exc:
            raise ExternalCheckerPolicyError(str(exc)) from exc


def _make_policy(model, entries):
    hash_body = {
        "schema_version": model.model_fields["schema_version"].default,
        "entries": [item.model_dump(mode="json") for item in entries],
    }
    if model is LockedExternalPreSubmitPolicy:
        default = LockedWorkstreamDefault()
        hash_body["workstream_default"] = default.model_dump(mode="json")
        return model(
            workstream_default=default,
            entries=entries,
            policy_sha256=canonical_json_hash(hash_body),
        )
    return model(entries=entries, policy_sha256=canonical_json_hash(hash_body))


def selected_pre_submit_execution_budget_ms(
    policy: LockedExternalPreSubmitPolicy,
    *,
    artifact_deadline_ms: int,
) -> int:
    """Return the exact ordered work budget only when ART can keep custody alive."""
    if (
        type(policy) is not LockedExternalPreSubmitPolicy
        or type(artifact_deadline_ms) is not int
        or artifact_deadline_ms <= 0
        or artifact_deadline_ms > MAXIMUM_SELECTED_PRE_EXECUTION_BUDGET_MS
    ):
        raise ExternalCheckerPolicyError("selected PRE execution budget is invalid")
    required = WORKSTREAM_DEFAULT_EXECUTION_BUDGET_MS + sum(
        binding.registry.resources.deadline_ms + EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
        for binding in policy.entries
    )
    if required > artifact_deadline_ms:
        raise ExternalCheckerPolicyError("selected PRE execution exceeds ART custody deadline")
    return required


def selected_post_submit_execution_budget_ms(
    policy: LockedExternalPostSubmitPolicy,
    *,
    artifact_deadline_ms: int | None = None,
) -> int:
    """Bound ART materialization and every ordered POST image under one lease."""
    if (
        type(policy) is not LockedExternalPostSubmitPolicy
        or artifact_deadline_ms is not None
        and (type(artifact_deadline_ms) is not int or artifact_deadline_ms <= 0)
    ):
        raise ExternalCheckerPolicyError("selected POST execution budget is invalid")
    required = SELECTED_POST_MATERIALIZATION_BUDGET_MS + sum(
        binding.registry.resources.deadline_ms
        + EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
        + (
            SELECTED_POST_FORGE_FACTS_BUDGET_MS
            + binding.registry.resources.deadline_ms
            + EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
            if selected_forge_facts(binding.configuration, binding.stage) is not None
            else 0
        )
        for binding in policy.entries
    )
    if required > MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS:
        raise ExternalCheckerPolicyError("selected POST execution exceeds durable worker deadline")
    if artifact_deadline_ms is not None and required > artifact_deadline_ms:
        raise ExternalCheckerPolicyError("selected POST execution exceeds ART custody deadline")
    return required
