"""Immutable authority for bounded external-checker trial execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from types import MappingProxyType
from typing import Literal, Mapping
from uuid import UUID

from app.modules.checkers.api.external import external_checker_json_hash


Sha256 = str
Identifier = str
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,99}")
_RETAINABLE_OUTCOMES = frozenset({"succeeded", "exit_nonzero", "signalled"})
_MANIFEST_PROTOCOL = "workstream.trial_authority_manifest.v1"
_MAXIMUM_MANIFEST_BYTES = 4 * 1024 * 1024


class TrialProfileError(ValueError):
    """A selector, trusted profile, or project projection is malformed."""


@dataclass(frozen=True, slots=True)
class TrialProfileSelector:
    """Exact immutable trial-profile version selected by locked policy."""

    profile_id: UUID
    profile_version: int
    profile_digest: Sha256

    def __post_init__(self) -> None:
        """Reject non-native UUIDs, non-positive versions and malformed content digests."""
        if (
            type(self.profile_id) is not UUID
            or type(self.profile_version) is not int
            or self.profile_version < 1
            or type(self.profile_digest) is not str
            or _DIGEST.fullmatch(self.profile_digest) is None
        ):
            raise TrialProfileError("trial profile selector is invalid")


@dataclass(frozen=True, slots=True)
class TrialProjectionSelector:
    """Exact immutable project projection selected by locked policy."""

    projection_id: UUID
    projection_version: int
    projection_digest: Sha256

    def __post_init__(self) -> None:
        """Require an exact typed projection version and SHA-256 identity."""
        if (
            type(self.projection_id) is not UUID
            or type(self.projection_version) is not int
            or self.projection_version < 1
            or type(self.projection_digest) is not str
            or _DIGEST.fullmatch(self.projection_digest) is None
        ):
            raise TrialProfileError("trial projection selector is invalid")


@dataclass(frozen=True, slots=True)
class TrialResourceCeilings:
    """Whole-invocation and per-operation limits owned by trusted config."""

    maximum_total_timeout_ms: int
    maximum_build_timeout_ms: int
    maximum_step_timeout_ms: int
    maximum_steps: int
    maximum_cpu_quota_millis: int
    maximum_cpu_time_ms: int
    maximum_wall_time_overrun_ms: int
    maximum_cpu_time_overrun_ms: int
    maximum_memory_bytes: int
    maximum_swap_bytes: int
    maximum_memory_overrun_bytes: int
    maximum_pids: int
    maximum_pids_overrun: int
    maximum_disk_bytes: int
    maximum_disk_overrun_bytes: int
    maximum_entries: int
    maximum_entries_overrun: int
    maximum_step_output_bytes: int
    maximum_observation_bytes: int
    maximum_receipt_bytes: int
    maximum_frame_bytes: int
    maximum_response_bytes: int

    def __post_init__(self) -> None:
        """Enforce positive finite ceilings, disabled swap and bounded protocol payloads."""
        values = asdict(self)
        if any(type(value) is not int or value < 1 for value in values.values()):
            raise TrialProfileError("trial resource ceiling is invalid")
        if self.maximum_build_timeout_ms > self.maximum_total_timeout_ms or (
            self.maximum_step_timeout_ms > self.maximum_total_timeout_ms
        ):
            raise TrialProfileError("trial timeout ceiling is invalid")
        if self.maximum_memory_bytes != self.maximum_swap_bytes:
            raise TrialProfileError("trial swap must be disabled")
        if self.maximum_pids < 2:
            raise TrialProfileError("trial PID ceiling cannot host the trusted launcher and child")
        if (
            any(
                value > 4 * 1024 * 1024
                for value in (
                    self.maximum_step_output_bytes,
                    self.maximum_observation_bytes,
                    self.maximum_frame_bytes,
                    self.maximum_response_bytes,
                )
            )
            or self.maximum_receipt_bytes > 1024 * 1024
        ):
            raise TrialProfileError("trial byte ceiling is invalid")


@dataclass(frozen=True, slots=True)
class TrialExecutionProfile:
    """One trusted node-provisioned generic builder/runner profile."""

    schema_version: Literal["workstream.trial_execution_profile.v1"]
    selector: TrialProfileSelector
    runtime: Literal["runsc"]
    isolation_mode: Literal["gvisor"]
    outer_host_uds: Literal["open"]
    child_host_uds: Literal["none"]
    outer_runtime_config_digest: Sha256
    child_runtime_config_digest: Sha256
    engine_identity_digest: Sha256
    platform: str
    platform_identity_digest: Sha256
    builder_image_digest: Sha256
    trusted_launcher_digest: Sha256
    offline_cache_digest: Sha256
    approved_base_digests: tuple[Sha256, ...]
    permitted_source_roles: tuple[Identifier, ...]
    permitted_material_roles: tuple[Identifier, ...]
    permitted_operations: tuple[Literal["run"], ...]
    permitted_state_retention_outcomes: tuple[
        Literal["succeeded", "exit_nonzero", "signalled"], ...
    ]
    trusted_launcher_capabilities: tuple[
        Literal[
            "CHOWN",
            "DAC_OVERRIDE",
            "FOWNER",
            "KILL",
            "SETGID",
            "SETPCAP",
            "SETUID",
            "SYS_ADMIN",
            "SYS_CHROOT",
        ],
        ...,
    ]
    builder_capabilities: tuple[Literal["CHOWN", "DAC_OVERRIDE", "FOWNER"], ...]
    child_capabilities: tuple[()]
    child_network: Literal["none"]
    child_runs_as_non_root: Literal[True]
    limits: TrialResourceCeilings

    def __post_init__(self) -> None:
        """Validate isolated runtime controls and recompute the immutable profile digest."""
        if (
            self.schema_version != "workstream.trial_execution_profile.v1"
            or self.runtime != "runsc"
            or self.isolation_mode != "gvisor"
            or self.outer_host_uds != "open"
            or self.child_host_uds != "none"
            or self.child_network != "none"
            or self.child_runs_as_non_root is not True
            or self.child_capabilities != ()
            or self.trusted_launcher_capabilities
            != (
                "CHOWN",
                "DAC_OVERRIDE",
                "FOWNER",
                "KILL",
                "SETGID",
                "SETPCAP",
                "SETUID",
                "SYS_ADMIN",
                "SYS_CHROOT",
            )
            or self.builder_capabilities != ("CHOWN", "DAC_OVERRIDE", "FOWNER")
            or self.permitted_operations != ("run",)
            or not self.permitted_state_retention_outcomes
            or len(set(self.permitted_state_retention_outcomes))
            != len(self.permitted_state_retention_outcomes)
            or not set(self.permitted_state_retention_outcomes) <= _RETAINABLE_OUTCOMES
            or type(self.platform) is not str
            or not re.fullmatch(r"linux/[a-z0-9_.-]{1,32}", self.platform)
        ):
            raise TrialProfileError("trial execution profile is invalid")
        digests = (
            self.outer_runtime_config_digest,
            self.child_runtime_config_digest,
            self.engine_identity_digest,
            self.platform_identity_digest,
            self.builder_image_digest,
            self.trusted_launcher_digest,
            self.offline_cache_digest,
            *self.approved_base_digests,
        )
        if (
            not self.approved_base_digests
            or len(set(self.approved_base_digests)) != len(self.approved_base_digests)
            or any(type(value) is not str or _DIGEST.fullmatch(value) is None for value in digests)
            or not self.permitted_material_roles
            or not self.permitted_source_roles
            or len(set(self.permitted_source_roles)) != len(self.permitted_source_roles)
            or len(set(self.permitted_material_roles)) != len(self.permitted_material_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in (*self.permitted_source_roles, *self.permitted_material_roles)
            )
            or profile_digest(self) != self.selector.profile_digest
        ):
            raise TrialProfileError("trial execution profile digest differs")


@dataclass(frozen=True, slots=True)
class TrialSlotProjection:
    """One ordered project-selected operation with an exact material view."""

    slot_kind: Identifier
    minimum_occurrences: int
    maximum_occurrences: int
    seed_roles: tuple[Identifier, ...]
    visible_roles: tuple[Identifier, ...]
    fresh_workspace: bool
    retain_state_after: tuple[Literal["succeeded", "exit_nonzero", "signalled"], ...]

    def __post_init__(self) -> None:
        """Bound ordered occurrences and reject ambiguous role or state-retention grants."""
        if (
            type(self.slot_kind) is not str
            or _IDENTIFIER.fullmatch(self.slot_kind) is None
            or type(self.minimum_occurrences) is not int
            or type(self.maximum_occurrences) is not int
            or self.minimum_occurrences < 0
            or self.maximum_occurrences < max(1, self.minimum_occurrences)
            or len(set(self.seed_roles)) != len(self.seed_roles)
            or len(set(self.visible_roles)) != len(self.visible_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in (*self.seed_roles, *self.visible_roles)
            )
            or type(self.fresh_workspace) is not bool
            or not self.retain_state_after
            or len(set(self.retain_state_after)) != len(self.retain_state_after)
            or not set(self.retain_state_after) <= _RETAINABLE_OUTCOMES
        ):
            raise TrialProfileError("trial slot projection is invalid")


@dataclass(frozen=True, slots=True)
class TrialMaterialProjection:
    """One private engine projection from an authorized source-material role."""

    role: Identifier
    source_role: Identifier
    projection_kind: Literal["build_context", "state_seed", "state_overlay"]
    source_relative: str
    destination_relative: str
    exclusions: tuple[str, ...]

    def __post_init__(self) -> None:
        """Constrain material copies to canonical relative paths and disjoint exclusions."""
        if (
            type(self.role) is not str
            or _IDENTIFIER.fullmatch(self.role) is None
            or type(self.source_role) is not str
            or _IDENTIFIER.fullmatch(self.source_role) is None
            or self.projection_kind not in {"build_context", "state_seed", "state_overlay"}
            or not _safe_relative(self.source_relative, allow_dot=True)
            or not _safe_relative(self.destination_relative, allow_dot=True)
            or self.projection_kind == "state_overlay"
            and (self.destination_relative == "." or "/" in self.destination_relative)
            or tuple(sorted(set(self.exclusions))) != self.exclusions
            or any(not _safe_relative(value, allow_dot=False) for value in self.exclusions)
            or _paths_overlap(self.exclusions)
        ):
            raise TrialProfileError("trial material projection is invalid")


@dataclass(frozen=True, slots=True)
class TrialExecutionProjection:
    """Exact project-owned subset resolved from trusted immutable config."""

    selector: TrialProjectionSelector
    trial_kind: Identifier
    material_projections: tuple[TrialMaterialProjection, ...]
    allowed_material_roles: tuple[Identifier, ...]
    build_context_roles: tuple[Identifier, ...]
    slot_templates: tuple[TrialSlotProjection, ...]

    def __post_init__(self) -> None:
        """Validate material and slot relationships before accepting the projection digest."""
        allowed = set(self.allowed_material_roles)
        projected = {item.role for item in self.material_projections}
        if (
            type(self.trial_kind) is not str
            or _IDENTIFIER.fullmatch(self.trial_kind) is None
            or not allowed
            or not self.material_projections
            or len(projected) != len(self.material_projections)
            or projected != allowed
            or len(allowed) != len(self.allowed_material_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in (*self.allowed_material_roles, *self.build_context_roles)
            )
            or not set(self.build_context_roles) <= allowed
            or not self.build_context_roles
            or not self.slot_templates
            or len({slot.slot_kind for slot in self.slot_templates}) != len(self.slot_templates)
            or any(not set(slot.visible_roles) <= allowed for slot in self.slot_templates)
            or any(not set(slot.seed_roles) <= allowed for slot in self.slot_templates)
            or any(
                _paths_overlap(
                    tuple(
                        item.destination_relative
                        for item in self.material_projections
                        if item.projection_kind == kind
                    )
                )
                for kind in ("build_context", "state_seed", "state_overlay")
            )
            or any(
                next(
                    item for item in self.material_projections if item.role == role
                ).projection_kind
                != "build_context"
                for role in self.build_context_roles
            )
            or any(
                next(
                    item for item in self.material_projections if item.role == role
                ).projection_kind
                != "state_seed"
                for slot in self.slot_templates
                for role in slot.seed_roles
            )
            or any(
                next(
                    item for item in self.material_projections if item.role == role
                ).projection_kind
                != "state_overlay"
                for slot in self.slot_templates
                for role in slot.visible_roles
            )
            or any(
                _paths_overlap(
                    tuple(
                        next(
                            item for item in self.material_projections if item.role == role
                        ).destination_relative
                        for role in (*slot.seed_roles, *slot.visible_roles)
                    )
                )
                for slot in self.slot_templates
            )
            or projection_digest(self) != self.selector.projection_digest
        ):
            raise TrialProfileError("trial execution projection is invalid")

    def validate_profile(self, profile: TrialExecutionProfile) -> None:
        """Require the project projection to be a subset of trusted authority."""
        if (
            not set(self.allowed_material_roles) <= set(profile.permitted_material_roles)
            or not {item.source_role for item in self.material_projections}
            <= set(profile.permitted_source_roles)
            or sum(slot.maximum_occurrences for slot in self.slot_templates)
            > profile.limits.maximum_steps
            or any(
                not set(slot.retain_state_after) <= set(profile.permitted_state_retention_outcomes)
                for slot in self.slot_templates
            )
        ):
            raise TrialProfileError("trial execution projection exceeds profile")


def _selector_value(selector: TrialProfileSelector, *, include_digest: bool) -> dict[str, object]:
    """Serialize native profile identity and optionally include its stored digest."""
    value = {
        "profile_id": str(selector.profile_id),
        "profile_version": selector.profile_version,
    }
    if include_digest:
        value["profile_digest"] = selector.profile_digest
    return value


def profile_digest(profile: TrialExecutionProfile) -> Sha256:
    """Hash the canonical immutable payload without its self-referential digest."""
    value = asdict(profile)
    value["selector"] = _selector_value(profile.selector, include_digest=False)
    return external_checker_json_hash(value)


def make_trial_execution_profile(**fields: object) -> TrialExecutionProfile:
    """Derive, then validate, the profile digest; callers cannot choose it."""
    selector = fields.get("selector")
    if not isinstance(selector, TrialProfileSelector):
        raise TrialProfileError("trial profile selector is invalid")
    placeholder = TrialProfileSelector(
        profile_id=selector.profile_id,
        profile_version=selector.profile_version,
        profile_digest="sha256:" + "0" * 64,
    )
    candidate = object.__new__(TrialExecutionProfile)
    for name in TrialExecutionProfile.__dataclass_fields__:
        object.__setattr__(candidate, name, placeholder if name == "selector" else fields[name])
    derived = profile_digest(candidate)
    exact = dict(fields)
    exact["selector"] = TrialProfileSelector(
        profile_id=selector.profile_id,
        profile_version=selector.profile_version,
        profile_digest=derived,
    )
    return TrialExecutionProfile(**exact)


def projection_digest(projection: TrialExecutionProjection) -> Sha256:
    """Hash the canonical immutable projection without its self digest."""
    value = asdict(projection)
    value["selector"] = {
        "projection_id": str(projection.selector.projection_id),
        "projection_version": projection.selector.projection_version,
    }
    return external_checker_json_hash(value)


def make_trial_execution_projection(**fields: object) -> TrialExecutionProjection:
    """Derive, then validate, a project projection digest."""
    selector = fields.get("selector")
    if not isinstance(selector, TrialProjectionSelector):
        raise TrialProfileError("trial projection selector is invalid")
    placeholder = TrialProjectionSelector(
        projection_id=selector.projection_id,
        projection_version=selector.projection_version,
        projection_digest="sha256:" + "0" * 64,
    )
    candidate = object.__new__(TrialExecutionProjection)
    for name in TrialExecutionProjection.__dataclass_fields__:
        object.__setattr__(candidate, name, placeholder if name == "selector" else fields[name])
    exact = dict(fields)
    exact["selector"] = TrialProjectionSelector(
        projection_id=selector.projection_id,
        projection_version=selector.projection_version,
        projection_digest=projection_digest(candidate),
    )
    return TrialExecutionProjection(**exact)


@dataclass(frozen=True, slots=True)
class TrialExecutionSelector:
    """Flat policy selection of one compatible profile/projection pair."""

    profile: TrialProfileSelector
    projection: TrialProjectionSelector


@dataclass(frozen=True, slots=True)
class TrialAuthorityContext:
    """Exact locked checker binding that may select one trial bundle."""

    registry_entry_id: UUID
    registry_entry_digest: Sha256
    checker_image_digest: Sha256
    configuration_sha256: Sha256

    def __post_init__(self) -> None:
        """Reject incomplete or malformed request-binding identities."""
        if type(self.registry_entry_id) is not UUID or any(
            type(value) is not str or _DIGEST.fullmatch(value) is None
            for value in (
                self.registry_entry_digest,
                self.checker_image_digest,
                self.configuration_sha256,
            )
        ):
            raise TrialProfileError("trial authority context is invalid")


@dataclass(frozen=True, slots=True)
class TrialAuthorityBinding:
    """One operator-provisioned binding of runtime authority to locked policy."""

    registry_entry_id: UUID
    registry_entry_digest: Sha256
    checker_image_digest: Sha256
    configuration_sha256: Sha256
    profile: TrialExecutionProfile
    projection: TrialExecutionProjection

    def __post_init__(self) -> None:
        """Bind exact registry, image and configuration identities to a permitted projection."""
        if type(self.registry_entry_id) is not UUID or any(
            type(value) is not str or _DIGEST.fullmatch(value) is None
            for value in (
                self.registry_entry_digest,
                self.checker_image_digest,
                self.configuration_sha256,
            )
        ):
            raise TrialProfileError("trial authority binding is invalid")
        self.projection.validate_profile(self.profile)

    @property
    def context(self) -> TrialAuthorityContext:
        """Return the exact request binding independently from reused selectors."""
        return TrialAuthorityContext(
            registry_entry_id=self.registry_entry_id,
            registry_entry_digest=self.registry_entry_digest,
            checker_image_digest=self.checker_image_digest,
            configuration_sha256=self.configuration_sha256,
        )


def trial_selector_from_configuration(
    configuration: Mapping[str, object],
) -> TrialExecutionSelector | None:
    """Parse only flat immutable selectors from locked checker configuration."""
    selector_keys = {
        "trial_profile_id",
        "trial_profile_version",
        "trial_profile_digest",
        "trial_projection_id",
        "trial_projection_version",
        "trial_projection_digest",
    }
    present = selector_keys & configuration.keys()
    reserved = {key for key in configuration if type(key) is str and key.startswith("trial_")}
    if reserved - selector_keys:
        raise TrialProfileError("trial execution selector is invalid")
    if not present:
        return None
    if present != selector_keys or "trial_execution" in configuration:
        raise TrialProfileError("trial execution selector is incomplete")
    try:
        for name in ("trial_profile_id", "trial_projection_id"):
            value = configuration[name]
            if type(value) is not str or str(UUID(value)) != value:
                raise TrialProfileError("trial execution selector is not canonical")
        return TrialExecutionSelector(
            profile=TrialProfileSelector(
                profile_id=UUID(configuration["trial_profile_id"]),
                profile_version=configuration["trial_profile_version"],
                profile_digest=configuration["trial_profile_digest"],
            ),
            projection=TrialProjectionSelector(
                projection_id=UUID(configuration["trial_projection_id"]),
                projection_version=configuration["trial_projection_version"],
                projection_digest=configuration["trial_projection_digest"],
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TrialProfileError):
            raise
        raise TrialProfileError("trial execution projection is invalid") from exc


def _string_tuple(value: object) -> tuple[str, ...]:
    """Accept a JSON string array without coercing other scalar types."""
    if type(value) is not list or any(type(item) is not str for item in value):
        raise TrialProfileError("trial execution projection is invalid")
    return tuple(value)


def _safe_relative(value: object, *, allow_dot: bool) -> bool:
    """Check a canonical POSIX relative path without traversal or alternate separators."""
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        return False
    if value == ".":
        return allow_dot
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and str(path) == value and tuple(raw_parts) == path.parts


def _paths_overlap(values: tuple[str, ...]) -> bool:
    """Detect duplicate paths and ancestor/descendant pairs in exclusion lists."""
    normalized = [() if value == "." else PurePosixPath(value).parts for value in values]
    for index, left in enumerate(normalized):
        for right in normalized[index + 1 :]:
            if left == right or left == right[: len(left)] or right == left[: len(right)]:
                return True
    return False


class PinnedTrialProfileCatalog:
    """Read-only exact-match catalog populated only from trusted service config."""

    def __init__(self, profiles: tuple[TrialExecutionProfile, ...]) -> None:
        """Freeze trusted profiles while rejecting duplicate identities or version aliases."""
        values: dict[tuple[UUID, int, str], TrialExecutionProfile] = {}
        versions: set[tuple[UUID, int]] = set()
        for profile in profiles:
            key = (
                profile.selector.profile_id,
                profile.selector.profile_version,
                profile.selector.profile_digest,
            )
            version = key[:2]
            if key in values or version in versions:
                raise TrialProfileError("trial profile version is duplicated")
            values[key] = profile
            versions.add(version)
        self._profiles = MappingProxyType(values)

    def read(self, selector: TrialProfileSelector) -> TrialExecutionProfile | None:
        """Return only one exact id/version/digest match."""
        return self._profiles.get(
            (selector.profile_id, selector.profile_version, selector.profile_digest)
        )


class PinnedTrialExecutionCatalog:
    """Exact profile/projection bundles provisioned by trusted service config."""

    def __init__(
        self,
        entries: tuple[TrialAuthorityBinding, ...],
    ) -> None:
        """Freeze exact request-bound bundles while permitting selector reuse."""
        values: dict[
            TrialAuthorityContext,
            TrialAuthorityBinding,
        ] = {}
        for binding in entries:
            if not isinstance(binding, TrialAuthorityBinding):
                raise TrialProfileError("trial authority binding is invalid")
            key = binding.context
            if key in values:
                raise TrialProfileError("trial authority binding is duplicated")
            values[key] = binding
        self._entries = MappingProxyType(values)

    def read(
        self,
        context: TrialAuthorityContext,
        selector: TrialExecutionSelector,
    ) -> tuple[TrialExecutionProfile, TrialExecutionProjection] | None:
        """Resolve selectors only inside their exact locked checker binding."""
        binding = self._entries.get(context)
        if binding is None or (
            binding.profile.selector != selector.profile
            or binding.projection.selector != selector.projection
        ):
            return None
        return binding.profile, binding.projection


def load_trial_authority_manifest(path: Path, expected_digest: str) -> PinnedTrialExecutionCatalog:
    """Read one bounded immutable operator manifest with no fallback."""
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or type(expected_digest) is not str
        or _DIGEST.fullmatch(expected_digest) is None
    ):
        raise TrialProfileError("trial authority manifest configuration is invalid")
    raw = _read_bounded_manifest(path)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_manifest_object,
            parse_constant=_invalid_manifest_constant,
        )
    except (UnicodeError, json.JSONDecodeError, TrialProfileError) as exc:
        raise TrialProfileError("trial authority manifest is invalid") from exc
    if (
        type(value) is not dict
        or set(value) != {"protocol_version", "entries"}
        or value["protocol_version"] != _MANIFEST_PROTOCOL
        or type(value["entries"]) is not list
        or not value["entries"]
        or external_checker_json_hash(value) != expected_digest
    ):
        raise TrialProfileError("trial authority manifest is invalid")
    bindings = tuple(_parse_authority_binding(item) for item in value["entries"])
    return PinnedTrialExecutionCatalog(bindings)


def _read_bounded_manifest(path: Path) -> bytes:
    """Read one bounded regular file and reject link or inode replacement races."""
    try:
        if path.resolve(strict=True) != path:
            raise TrialProfileError("trial authority manifest is invalid")
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
    except OSError as exc:
        raise TrialProfileError("trial authority manifest is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not (0 < before.st_size <= _MAXIMUM_MANIFEST_BYTES)
        ):
            raise TrialProfileError("trial authority manifest is invalid")
        chunks: list[bytes] = []
        remaining = _MAXIMUM_MANIFEST_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if (
            len(raw) != before.st_size
            or len(raw) > _MAXIMUM_MANIFEST_BYTES
            or (after.st_dev, after.st_ino, after.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
            or (current.st_dev, current.st_ino, current.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
        ):
            raise TrialProfileError("trial authority manifest changed")
        return raw
    except OSError as exc:
        raise TrialProfileError("trial authority manifest is unavailable") from exc
    finally:
        os.close(descriptor)


def _closed_manifest_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys rather than silently replacing trusted authority."""
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise TrialProfileError("trial authority manifest is invalid")
        value[key] = item
    return value


def _invalid_manifest_constant(_value: str) -> object:
    """Reject non-finite JSON numeric constants in the trusted manifest."""
    raise TrialProfileError("trial authority manifest is invalid")


def _parse_authority_binding(value: object) -> TrialAuthorityBinding:
    """Parse the closed image/policy authority envelope and its immutable selectors."""
    if type(value) is not dict or set(value) != {
        "registry_entry_id",
        "registry_entry_digest",
        "checker_image_digest",
        "configuration_sha256",
        "profile",
        "projection",
    }:
        raise TrialProfileError("trial authority binding is invalid")
    try:
        return TrialAuthorityBinding(
            registry_entry_id=UUID(value["registry_entry_id"]),
            registry_entry_digest=value["registry_entry_digest"],
            checker_image_digest=value["checker_image_digest"],
            configuration_sha256=value["configuration_sha256"],
            profile=_parse_profile(value["profile"]),
            projection=_parse_projection(value["projection"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TrialProfileError):
            raise
        raise TrialProfileError("trial authority binding is invalid") from exc


def _parse_profile(value: object) -> TrialExecutionProfile:
    """Reconstruct a complete profile with typed selectors, ceilings and JSON arrays."""
    if type(value) is not dict or set(value) != set(TrialExecutionProfile.__dataclass_fields__):
        raise TrialProfileError("trial execution profile is invalid")
    selector = value["selector"]
    limits = value["limits"]
    if (
        type(selector) is not dict
        or set(selector)
        != {
            "profile_id",
            "profile_version",
            "profile_digest",
        }
        or type(limits) is not dict
        or set(limits) != set(TrialResourceCeilings.__dataclass_fields__)
    ):
        raise TrialProfileError("trial execution profile is invalid")
    fields = dict(value)
    fields["selector"] = TrialProfileSelector(
        UUID(selector["profile_id"]), selector["profile_version"], selector["profile_digest"]
    )
    fields["limits"] = TrialResourceCeilings(**limits)
    for name in (
        "approved_base_digests",
        "permitted_source_roles",
        "permitted_material_roles",
        "permitted_operations",
        "permitted_state_retention_outcomes",
        "trusted_launcher_capabilities",
        "builder_capabilities",
        "child_capabilities",
    ):
        fields[name] = _manifest_tuple(fields[name])
    return TrialExecutionProfile(**fields)


def _parse_projection(value: object) -> TrialExecutionProjection:
    """Reconstruct exact material and slot projections without dropping unknown fields."""
    if type(value) is not dict or set(value) != set(TrialExecutionProjection.__dataclass_fields__):
        raise TrialProfileError("trial execution projection is invalid")
    selector = value["selector"]
    materials = value["material_projections"]
    slots = value["slot_templates"]
    if (
        type(selector) is not dict
        or set(selector)
        != {
            "projection_id",
            "projection_version",
            "projection_digest",
        }
        or type(materials) is not list
        or type(slots) is not list
    ):
        raise TrialProfileError("trial execution projection is invalid")
    fields = dict(value)
    fields["selector"] = TrialProjectionSelector(
        UUID(selector["projection_id"]),
        selector["projection_version"],
        selector["projection_digest"],
    )
    fields["material_projections"] = tuple(
        TrialMaterialProjection(
            role=item["role"],
            source_role=item["source_role"],
            projection_kind=item["projection_kind"],
            source_relative=item["source_relative"],
            destination_relative=item["destination_relative"],
            exclusions=_manifest_tuple(item["exclusions"]),
        )
        for item in materials
        if _exact_manifest_item(item, TrialMaterialProjection)
    )
    if len(fields["material_projections"]) != len(materials):
        raise TrialProfileError("trial material projection is invalid")
    fields["slot_templates"] = tuple(
        TrialSlotProjection(
            slot_kind=item["slot_kind"],
            minimum_occurrences=item["minimum_occurrences"],
            maximum_occurrences=item["maximum_occurrences"],
            seed_roles=_manifest_tuple(item["seed_roles"]),
            visible_roles=_manifest_tuple(item["visible_roles"]),
            fresh_workspace=item["fresh_workspace"],
            retain_state_after=_manifest_tuple(item["retain_state_after"]),
        )
        for item in slots
        if _exact_manifest_item(item, TrialSlotProjection)
    )
    if len(fields["slot_templates"]) != len(slots):
        raise TrialProfileError("trial slot projection is invalid")
    fields["allowed_material_roles"] = _manifest_tuple(fields["allowed_material_roles"])
    fields["build_context_roles"] = _manifest_tuple(fields["build_context_roles"])
    return TrialExecutionProjection(**fields)


def _exact_manifest_item(value: object, cls: type[object]) -> bool:
    """Require a manifest object to contain exactly the declared dataclass fields."""
    return type(value) is dict and set(value) == set(cls.__dataclass_fields__)


def _manifest_tuple(value: object) -> tuple:
    """Convert only a JSON array to the immutable manifest representation."""
    if type(value) is not list:
        raise TrialProfileError("trial authority manifest is invalid")
    return tuple(value)


__all__ = (
    "PinnedTrialProfileCatalog",
    "PinnedTrialExecutionCatalog",
    "TrialExecutionProfile",
    "TrialExecutionProjection",
    "TrialExecutionSelector",
    "TrialAuthorityContext",
    "TrialAuthorityBinding",
    "TrialMaterialProjection",
    "TrialProfileError",
    "TrialProfileSelector",
    "TrialProjectionSelector",
    "TrialResourceCeilings",
    "TrialSlotProjection",
    "make_trial_execution_profile",
    "make_trial_execution_projection",
    "load_trial_authority_manifest",
    "profile_digest",
    "projection_digest",
    "trial_selector_from_configuration",
)
