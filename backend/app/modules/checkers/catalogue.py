"""Single immutable catalogue for pre-submission checker planning."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import (
    PreSubmissionCapabilityDefinition,
    PreSubmissionCapabilityProjection,
)
from app.modules.checkers.api import (
    EffectivePreSubmissionExecutionPlan,
    EffectivePreSubmissionPlanLineage,
)


PRE_SUBMISSION_CATALOGUE_ID = "workstream.pre_submission_checkers"
PRE_SUBMISSION_CATALOGUE_VERSION = "v0.1"
PRE_SUBMISSION_CATALOGUE_SCHEMA_VERSION = "pre_submission_checker_catalogue.v1"
PRE_SUBMISSION_RESULT_SCHEMA_VERSION = "pre_submission_checker_result.v1"


class PreSubmissionCatalogueError(ValueError):
    """Reject an invalid or ambiguous catalogue configuration."""


class PreSubmissionCheckerClassification(StrEnum):
    """Closed operational classification for one catalogue definition."""

    MANDATORY_SECURITY = "mandatory_security"
    MANDATORY_INTEGRITY = "mandatory_integrity"
    MANDATORY_ACCOUNTABILITY = "mandatory_accountability"
    ADVISORY = "advisory"

    @property
    def mandatory(self) -> bool:
        """Return whether disabling this definition makes intake unavailable."""
        return self is not PreSubmissionCheckerClassification.ADVISORY


class PreSubmissionCheckerPhase(StrEnum):
    """Canonical execution-plan phases."""

    CUSTODY = "custody"
    IDENTITY = "identity"
    MATERIALIZATION = "materialization"
    DEFAULT_POLICY = "default_policy"
    PROJECT_POLICY = "project_policy"


_PHASE_ORDER = {phase: index for index, phase in enumerate(PreSubmissionCheckerPhase)}


def pre_submission_phase_order(phase: PreSubmissionCheckerPhase) -> int:
    """Return the canonical ordinal for one pre-submission phase."""
    return _PHASE_ORDER[phase]


class PreSubmissionCheckerState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class PreSubmissionDisabledBehavior(StrEnum):
    INFRASTRUCTURE_UNAVAILABLE = "infrastructure_unavailable"
    RECORD_DISABLED_AND_CONTINUE = "record_disabled_and_continue"


class PreSubmissionDispatchKind(StrEnum):
    PLATFORM_CAPABILITY = "platform_capability"
    POLICY_PRIMITIVE = "policy_primitive"


class PreSubmissionPlatformCapability(StrEnum):
    OUTER_ZIP_VALID = "submission_archive.outer_zip_valid"
    PATHS_SAFE = "submission_archive.paths_safe"
    ENTRIES_SAFE = "submission_archive.entries_safe"
    RESOURCES_BOUNDED = "submission_archive.resources_bounded"
    INTEGRITY_VERIFIED = "submission_archive.integrity_verified"
    ARCHIVE_IDENTITY = "artifact_commitment.identity"
    MANIFEST_IDENTITY = "submission_manifest.semantic_identity"
    EXECUTABLE_NORMALIZED = "submission_manifest.executable_normalized"
    CONTENT_CHANGED = "submission_change.changed"
    SEALED_TREE_VERIFIED = "submission_materialization.sealed_tree_verified"
    SUBMISSION_PACKET = "validate_submission_packet"
    ATTESTATION = "require_attestation"
    SENSITIVE_PATH = "forbid_high_confidence_sensitive_path"
    QUALITY_WARNING = "warn_low_quality_generated_artifact"


class PreSubmissionPolicyPrimitive(StrEnum):
    FORBID_ARTIFACT = "forbid_artifact"
    LIMIT_FILE_SIZE = "limit_file_size"
    LIMIT_PACKAGE_SIZE = "limit_package_size"
    ENFORCE_STORAGE_SCHEME = "enforce_storage_scheme"
    VERIFY_HASH = "verify_hash"
    REQUIRE_ATTESTATION = "require_attestation"
    REQUIRE_PACKAGING = "require_packaging"
    REQUIRE_FILE = "require_file"
    REQUIRE_MINIMUM_EVIDENCE = "require_minimum_evidence"
    REQUIRE_MANIFEST_FIELD = "require_manifest_field"
    VALIDATE_SUBMISSION_PACKET = "validate_submission_packet"
    WARN_LOW_QUALITY_GENERATED_ARTIFACT = "warn_low_quality_generated_artifact"


@dataclass(frozen=True, slots=True)
class PreSubmissionCheckerDefinition:
    """One closed typed definition in the process-wide catalogue."""

    stable_id: str
    version: str
    public_name: str
    owner: str
    phase: PreSubmissionCheckerPhase
    order: int
    dependencies: tuple[str, ...]
    classification: PreSubmissionCheckerClassification
    typed_inputs: tuple[str, ...]
    result_schema: str
    failure_code: str
    resource_budget: tuple[tuple[str, int], ...]
    state: PreSubmissionCheckerState
    disabled_behavior: PreSubmissionDisabledBehavior
    policy_trace_source: str
    dispatch_kind: PreSubmissionDispatchKind
    dispatch_capability: str
    primitive: str | None = None
    policy_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (
            self.stable_id,
            self.version,
            self.public_name,
            self.owner,
            self.result_schema,
            self.failure_code,
            self.policy_trace_source,
            self.dispatch_capability,
        )
        if any(type(value) is not str or not value for value in values):
            raise PreSubmissionCatalogueError("catalogue definition identity is invalid")
        if type(self.order) is not int or self.order < 0:
            raise PreSubmissionCatalogueError("catalogue definition order is invalid")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise PreSubmissionCatalogueError("catalogue definition has duplicate dependencies")
        if len(self.typed_inputs) != len(set(self.typed_inputs)) or not self.typed_inputs:
            raise PreSubmissionCatalogueError("catalogue definition typed inputs are invalid")
        if tuple(sorted(self.resource_budget)) != self.resource_budget or any(
            type(key) is not str or not key or type(value) is not int or value < 0
            for key, value in self.resource_budget
        ):
            raise PreSubmissionCatalogueError("catalogue definition resource budget is invalid")
        if self.classification.mandatory:
            if (
                self.disabled_behavior
                is not PreSubmissionDisabledBehavior.INFRASTRUCTURE_UNAVAILABLE
            ):
                raise PreSubmissionCatalogueError("mandatory catalogue definition may not skip")
        elif (
            self.disabled_behavior is not PreSubmissionDisabledBehavior.RECORD_DISABLED_AND_CONTINUE
        ):
            raise PreSubmissionCatalogueError("advisory catalogue definition may not block startup")
        if self.dispatch_kind is PreSubmissionDispatchKind.POLICY_PRIMITIVE:
            if not self.primitive or not self.policy_fields:
                raise PreSubmissionCatalogueError("policy catalogue definition is incomplete")
            if (
                self.primitive not in set(PreSubmissionPolicyPrimitive)
                or self.dispatch_capability != self.primitive
            ):
                raise PreSubmissionCatalogueError("policy catalogue primitive is unknown")
        elif self.primitive is not None or self.policy_fields:
            raise PreSubmissionCatalogueError(
                "platform capability may not masquerade as a primitive"
            )
        elif self.dispatch_capability not in set(PreSubmissionPlatformCapability):
            raise PreSubmissionCatalogueError("platform catalogue capability is unknown")

    def manifest_entry(self) -> dict[str, Any]:
        """Return the canonical immutable catalogue projection."""
        return {
            "stable_id": self.stable_id,
            "version": self.version,
            "public_name": self.public_name,
            "owner": self.owner,
            "phase": self.phase.value,
            "order": self.order,
            "dependencies": list(self.dependencies),
            "classification": self.classification.value,
            "typed_inputs": list(self.typed_inputs),
            "result_schema": self.result_schema,
            "failure_code": self.failure_code,
            "resource_budget": dict(self.resource_budget),
            "state": self.state.value,
            "disabled_behavior": self.disabled_behavior.value,
            "policy_trace_source": self.policy_trace_source,
            "dispatch_kind": self.dispatch_kind.value,
            "dispatch_capability": self.dispatch_capability,
            "primitive": self.primitive,
            "policy_fields": list(self.policy_fields),
        }


@dataclass(frozen=True, slots=True)
class PreSubmissionCheckerCatalogue:
    """Validated process-wide catalogue and its canonical identity."""

    catalogue_id: str
    version: str
    schema_version: str
    entries: tuple[PreSubmissionCheckerDefinition, ...]

    def __post_init__(self) -> None:
        if (
            self.catalogue_id != PRE_SUBMISSION_CATALOGUE_ID
            or self.version != PRE_SUBMISSION_CATALOGUE_VERSION
            or self.schema_version != PRE_SUBMISSION_CATALOGUE_SCHEMA_VERSION
        ):
            raise PreSubmissionCatalogueError("catalogue envelope is invalid")
        if not self.entries:
            raise PreSubmissionCatalogueError("catalogue requires definitions")
        stable_ids = [entry.stable_id for entry in self.entries]
        if len(stable_ids) != len(set(stable_ids)):
            raise PreSubmissionCatalogueError("catalogue contains duplicate stable IDs")
        primitives = [entry.primitive for entry in self.entries if entry.primitive is not None]
        if len(primitives) != len(set(primitives)):
            raise PreSubmissionCatalogueError("catalogue contains duplicate primitives")
        expected_order = tuple(sorted(self.entries, key=_definition_sort_key))
        if self.entries != expected_order:
            raise PreSubmissionCatalogueError("catalogue definitions are not canonical")
        self._validate_dependencies()

    def _validate_dependencies(self) -> None:
        by_id = {entry.stable_id: entry for entry in self.entries}
        for entry in self.entries:
            for dependency_id in entry.dependencies:
                dependency = by_id.get(dependency_id)
                if dependency is None:
                    raise PreSubmissionCatalogueError("catalogue dependency is missing")
                if _PHASE_ORDER[dependency.phase] > _PHASE_ORDER[entry.phase]:
                    raise PreSubmissionCatalogueError("catalogue dependency phase is invalid")
                if dependency.phase is entry.phase and dependency.order >= entry.order:
                    raise PreSubmissionCatalogueError("catalogue dependency order is invalid")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(stable_id: str) -> None:
            if stable_id in visiting:
                raise PreSubmissionCatalogueError("catalogue dependency cycle detected")
            if stable_id in visited:
                return
            visiting.add(stable_id)
            for dependency_id in by_id[stable_id].dependencies:
                visit(dependency_id)
            visiting.remove(stable_id)
            visited.add(stable_id)

        for entry in self.entries:
            visit(entry.stable_id)

    @property
    def manifest(self) -> Mapping[str, Any]:
        """Return an immutable top-level manifest projection."""
        return MappingProxyType(
            {
                "catalogue_id": self.catalogue_id,
                "version": self.version,
                "schema_version": self.schema_version,
                "entries": [entry.manifest_entry() for entry in self.entries],
            }
        )

    @property
    def manifest_sha256(self) -> str:
        return canonical_json_hash(dict(self.manifest))

    @property
    def available(self) -> bool:
        return not any(
            entry.classification.mandatory and entry.state is PreSubmissionCheckerState.DISABLED
            for entry in self.entries
        )

    def definition(self, stable_id: str) -> PreSubmissionCheckerDefinition:
        for entry in self.entries:
            if entry.stable_id == stable_id:
                return entry
        raise PreSubmissionCatalogueError("catalogue definition is unknown")

    def primitive_definition(self, primitive: str) -> PreSubmissionCheckerDefinition:
        for entry in self.entries:
            if entry.primitive == primitive:
                return entry
        raise PreSubmissionCatalogueError("catalogue primitive is unknown")

    def compile_effective_plan(
        self,
        *,
        lineage: EffectivePreSubmissionPlanLineage,
        effective_policy: Mapping[str, object],
        compiled_bundle: Mapping[str, object],
    ) -> EffectivePreSubmissionExecutionPlan:
        """Implement the public deterministic CHECKER planning capability."""
        from app.modules.checkers.effective_plan import (
            compile_effective_pre_submission_execution_plan,
        )

        return compile_effective_pre_submission_execution_plan(
            lineage=lineage,
            effective_policy=dict(effective_policy),
            compiled_bundle=dict(compiled_bundle),
            catalogue=self,
        )


def build_pre_submission_checker_catalogue(
    *, disabled_entry_ids: frozenset[str] = frozenset()
) -> PreSubmissionCheckerCatalogue:
    """Build the sole catalogue with startup-fixed availability state."""
    definitions = _default_definitions()
    known = {definition.stable_id for definition in definitions}
    if not disabled_entry_ids.issubset(known):
        raise PreSubmissionCatalogueError("disabled catalogue definition is unknown")
    entries = tuple(
        replace(definition, state=PreSubmissionCheckerState.DISABLED)
        if definition.stable_id in disabled_entry_ids
        else definition
        for definition in definitions
    )
    return PreSubmissionCheckerCatalogue(
        PRE_SUBMISSION_CATALOGUE_ID,
        PRE_SUBMISSION_CATALOGUE_VERSION,
        PRE_SUBMISSION_CATALOGUE_SCHEMA_VERSION,
        tuple(sorted(entries, key=_definition_sort_key)),
    )


def parse_disabled_pre_submission_checker_ids(raw: str) -> frozenset[str]:
    """Parse one startup-owned comma-separated disabled-definition set."""
    if type(raw) is not str:
        raise PreSubmissionCatalogueError("disabled catalogue configuration is invalid")
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != len(set(parts)):
        raise PreSubmissionCatalogueError("disabled catalogue configuration has duplicates")
    return frozenset(parts)


def project_guide_pre_submission_capabilities(
    catalogue: PreSubmissionCheckerCatalogue,
) -> PreSubmissionCapabilityProjection:
    """Project the exact deployment catalogue without creating policy authority."""
    definitions = tuple(
        PreSubmissionCapabilityDefinition(
            **entry.manifest_entry(),
            selectable=(
                entry.state is PreSubmissionCheckerState.ENABLED
                and entry.dispatch_kind is PreSubmissionDispatchKind.POLICY_PRIMITIVE
                and entry.phase is PreSubmissionCheckerPhase.PROJECT_POLICY
            ),
        )
        for entry in catalogue.entries
    )
    return PreSubmissionCapabilityProjection(
        catalogue_id=catalogue.catalogue_id,
        version=catalogue.version,
        schema_version=catalogue.schema_version,
        manifest_sha256=catalogue.manifest_sha256,
        available=catalogue.available,
        definitions=definitions,
    )


def _definition_sort_key(entry: PreSubmissionCheckerDefinition) -> tuple[int, int, str]:
    return (_PHASE_ORDER[entry.phase], entry.order, entry.stable_id)


def _platform(
    stable_id: str,
    *,
    phase: PreSubmissionCheckerPhase,
    order: int,
    classification: PreSubmissionCheckerClassification,
    input_name: str,
    capability: str,
    failure_code: str,
    dependencies: tuple[str, ...] = (),
    public_name: str | None = None,
) -> PreSubmissionCheckerDefinition:
    return PreSubmissionCheckerDefinition(
        stable_id=stable_id,
        version="v1",
        public_name=public_name or stable_id,
        owner="workstream.artifact",
        phase=phase,
        order=order,
        dependencies=dependencies,
        classification=classification,
        typed_inputs=(input_name,),
        result_schema=PRE_SUBMISSION_RESULT_SCHEMA_VERSION,
        failure_code=failure_code,
        resource_budget=(("maximum_results", 1),),
        state=PreSubmissionCheckerState.ENABLED,
        disabled_behavior=(
            PreSubmissionDisabledBehavior.RECORD_DISABLED_AND_CONTINUE
            if classification is PreSubmissionCheckerClassification.ADVISORY
            else PreSubmissionDisabledBehavior.INFRASTRUCTURE_UNAVAILABLE
        ),
        policy_trace_source="workstream_default_policy",
        dispatch_kind=PreSubmissionDispatchKind.PLATFORM_CAPABILITY,
        dispatch_capability=capability,
    )


def _policy(
    stable_id: str,
    primitive: str,
    public_name: str,
    policy_fields: tuple[str, ...],
    *,
    order: int,
    classification: PreSubmissionCheckerClassification = PreSubmissionCheckerClassification.MANDATORY_ACCOUNTABILITY,
) -> PreSubmissionCheckerDefinition:
    return PreSubmissionCheckerDefinition(
        stable_id=stable_id,
        version="v1",
        public_name=public_name,
        owner="workstream.checker_policy",
        phase=PreSubmissionCheckerPhase.PROJECT_POLICY,
        order=order,
        dependencies=("artifact.scratch.sealed_tree_verified",),
        classification=classification,
        typed_inputs=("LockedProjectCheckerRule", "SubmissionManifestView"),
        result_schema=PRE_SUBMISSION_RESULT_SCHEMA_VERSION,
        failure_code="pre_submission_checker_failed",
        resource_budget=(("maximum_results", 1),),
        state=PreSubmissionCheckerState.ENABLED,
        disabled_behavior=(
            PreSubmissionDisabledBehavior.RECORD_DISABLED_AND_CONTINUE
            if classification is PreSubmissionCheckerClassification.ADVISORY
            else PreSubmissionDisabledBehavior.INFRASTRUCTURE_UNAVAILABLE
        ),
        policy_trace_source="locked_effective_project_submission_artifact_policy",
        dispatch_kind=PreSubmissionDispatchKind.POLICY_PRIMITIVE,
        dispatch_capability=primitive,
        primitive=primitive,
        policy_fields=tuple(sorted(policy_fields)),
    )


def _default_definitions() -> tuple[PreSubmissionCheckerDefinition, ...]:
    security = PreSubmissionCheckerClassification.MANDATORY_SECURITY
    integrity = PreSubmissionCheckerClassification.MANDATORY_INTEGRITY
    accountability = PreSubmissionCheckerClassification.MANDATORY_ACCOUNTABILITY
    advisory = PreSubmissionCheckerClassification.ADVISORY
    custody = PreSubmissionCheckerPhase.CUSTODY
    identity = PreSubmissionCheckerPhase.IDENTITY
    materialization = PreSubmissionCheckerPhase.MATERIALIZATION
    defaults = PreSubmissionCheckerPhase.DEFAULT_POLICY
    definitions = (
        _platform(
            "artifact.outer_zip.valid",
            phase=custody,
            order=10,
            classification=security,
            input_name="SubmissionArchiveInspectionResult",
            capability="submission_archive.outer_zip_valid",
            failure_code="submission_archive_malformed",
        ),
        _platform(
            "artifact.archive.paths_safe",
            phase=custody,
            order=20,
            classification=security,
            input_name="SubmissionArchiveInspectionResult",
            capability="submission_archive.paths_safe",
            failure_code="submission_archive_unsafe_entry",
            dependencies=("artifact.outer_zip.valid",),
        ),
        _platform(
            "artifact.archive.entries_safe",
            phase=custody,
            order=30,
            classification=security,
            input_name="SubmissionArchiveInspectionResult",
            capability="submission_archive.entries_safe",
            failure_code="submission_archive_unsafe_entry",
            dependencies=("artifact.archive.paths_safe",),
        ),
        _platform(
            "artifact.archive.resources_bounded",
            phase=custody,
            order=40,
            classification=security,
            input_name="SubmissionArchiveInspectionResult",
            capability="submission_archive.resources_bounded",
            failure_code="submission_archive_limit_exceeded",
            dependencies=("artifact.archive.entries_safe",),
        ),
        _platform(
            "artifact.archive.integrity_verified",
            phase=custody,
            order=50,
            classification=integrity,
            input_name="SubmissionArchiveInspectionResult",
            capability="submission_archive.integrity_verified",
            failure_code="submission_archive_integrity_failure",
            dependencies=("artifact.archive.resources_bounded",),
        ),
        _platform(
            "artifact.archive.identity_computed",
            phase=identity,
            order=10,
            classification=integrity,
            input_name="ArtifactCommitment",
            capability="artifact_commitment.identity",
            failure_code="submission_archive_identity_unavailable",
            dependencies=("artifact.archive.integrity_verified",),
        ),
        _platform(
            "artifact.manifest.semantic_identity_computed",
            phase=identity,
            order=20,
            classification=integrity,
            input_name="SubmissionManifest",
            capability="submission_manifest.semantic_identity",
            failure_code="submission_manifest_identity_unavailable",
            dependencies=("artifact.archive.identity_computed",),
        ),
        _platform(
            "artifact.manifest.executable_normalized",
            phase=identity,
            order=30,
            classification=integrity,
            input_name="SubmissionManifest",
            capability="submission_manifest.executable_normalized",
            failure_code="submission_manifest_executable_invalid",
            dependencies=("artifact.manifest.semantic_identity_computed",),
        ),
        _platform(
            "artifact.revision.content_changed",
            phase=identity,
            order=40,
            classification=integrity,
            input_name="SubmissionChangeGateResult",
            capability="submission_change.changed",
            failure_code="submission_manifest_unchanged",
            dependencies=("artifact.manifest.executable_normalized",),
        ),
        _platform(
            "artifact.scratch.sealed_tree_verified",
            phase=materialization,
            order=10,
            classification=integrity,
            input_name="SealedSubmissionTree",
            capability="submission_materialization.sealed_tree_verified",
            failure_code="pre_submission_materialization_unavailable",
            dependencies=("artifact.revision.content_changed",),
        ),
        _platform(
            "submission.packet.required_fields",
            phase=defaults,
            order=10,
            classification=accountability,
            input_name="SubmissionPacket",
            capability="validate_submission_packet",
            failure_code="pre_submission_packet_invalid",
            dependencies=("artifact.scratch.sealed_tree_verified",),
            public_name="check_submission_packet",
        ),
        _platform(
            "submission.attestation.required_topics",
            phase=defaults,
            order=20,
            classification=accountability,
            input_name="SubmissionPacket",
            capability="require_attestation",
            failure_code="pre_submission_attestation_missing",
            dependencies=("submission.packet.required_fields",),
            public_name="check_confidentiality_attestation",
        ),
        _platform(
            "artifact.sensitive_paths.high_confidence",
            phase=defaults,
            order=30,
            classification=security,
            input_name="SubmissionManifest",
            capability="forbid_high_confidence_sensitive_path",
            failure_code="pre_submission_sensitive_path_forbidden",
            dependencies=("submission.attestation.required_topics",),
            public_name="check_forbidden_files",
        ),
        _platform(
            "artifact.quality.placeholder_signal",
            phase=defaults,
            order=40,
            classification=advisory,
            input_name="SubmissionPacket",
            capability="warn_low_quality_generated_artifact",
            failure_code="pre_submission_quality_warning",
            dependencies=("artifact.sensitive_paths.high_confidence",),
            public_name="check_low_quality_generated_artifacts",
        ),
        _policy(
            "policy.submission_packet.validate",
            "validate_submission_packet",
            "check_submission_packet",
            ("required_packet_fields",),
            order=10,
        ),
        _policy(
            "policy.storage_scheme.enforce",
            "enforce_storage_scheme",
            "check_evidence_integrity",
            ("allowed_storage_schemes",),
            order=20,
            classification=integrity,
        ),
        _policy(
            "policy.manifest_field.require",
            "require_manifest_field",
            "check_evidence_integrity",
            ("manifest_required",),
            order=30,
            classification=integrity,
        ),
        _policy(
            "policy.hash.verify",
            "verify_hash",
            "check_evidence_integrity",
            ("artifact_hash_algorithm", "artifact_hash_required"),
            order=40,
            classification=integrity,
        ),
        _policy(
            "policy.file.require",
            "require_file",
            "check_required_files",
            ("required_artifacts",),
            order=50,
        ),
        _policy(
            "policy.evidence.minimum",
            "require_minimum_evidence",
            "check_evidence_present",
            ("required_evidence",),
            order=60,
        ),
        _policy(
            "policy.artifact.forbid",
            "forbid_artifact",
            "check_forbidden_files",
            ("forbidden_artifacts",),
            order=70,
            classification=security,
        ),
        _policy(
            "policy.attestation.require",
            "require_attestation",
            "check_confidentiality_attestation",
            ("attestation_terms",),
            order=80,
        ),
        _policy(
            "policy.file_size.limit",
            "limit_file_size",
            "check_evidence_integrity",
            ("maximum_file_size_bytes",),
            order=90,
            classification=integrity,
        ),
        _policy(
            "policy.package_size.limit",
            "limit_package_size",
            "check_evidence_integrity",
            ("maximum_package_size_bytes",),
            order=100,
            classification=integrity,
        ),
        _policy(
            "policy.packaging.require",
            "require_packaging",
            "check_submission_packet",
            ("packaging",),
            order=110,
        ),
        _policy(
            "policy.generated_quality.warn",
            "warn_low_quality_generated_artifact",
            "check_low_quality_generated_artifacts",
            ("workstream_default_policy",),
            order=120,
            classification=advisory,
        ),
    )
    return tuple(sorted(definitions, key=_definition_sort_key))
