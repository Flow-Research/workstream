"""Explicit production Rust/Smol/trial/ART composition qualification.

This test is invoked only by the native Smol qualification wrapper. It uses the
small qualification-only package, not a real Terminal Systems contribution or
the setup/activation journey owned by issue 555.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time
from uuid import UUID, uuid4
import zipfile

from sqlalchemy import select

from app.adapters.artifacts import checker_output_binding, checker_output_storage
from app.adapters.artifacts import post_submission_materialization
from app.adapters.artifacts.trusted_intake import UnixSocketTrustedIntakeAdapter
from app.adapters.auth import checker_model_service_authorization
from app.adapters.checkers import (
    checker_output_reservations,
    model_call_service,
    model_invocation_grants,
    model_profile_reader,
)
from app.adapters.checkers.external_service import UnixSocketExternalCheckerAdapter
from app.adapters.checkers.model_execution import ModelAwareExternalExecution
from app.adapters.checkers.model_proxy import CheckerModelProxy
from app.adapters.checkers.model_proxy_transport import ModelProxyTransport
from app.adapters.checkers.trial_proxy import CheckerTrialProxy
from app.interfaces.checker_model_provider import (
    CheckerModelCreateOutcome,
    CheckerModelCreateResult,
    CheckerModelObservation,
    CheckerModelProviderStatus,
    CheckerModelResponseReference,
    CheckerModelUsage,
)
from app.interfaces.project_agents import CapabilityParameter, CheckSpecification
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.preparation import HARD_MAXIMUM_ARTIFACT_BYTES
from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactContent,
    ArtifactPutAttempt,
    ArtifactVerificationReceipt,
)
from app.modules.checkers.api.external import (
    ExternalCheckerSchema,
    external_checker_json_hash,
)
from app.modules.checkers.api.trial_profiles import (
    TrialMaterialProjection,
    TrialProfileSelector,
    TrialProjectionSelector,
    TrialResourceCeilings,
    TrialSlotProjection,
    load_trial_authority_manifest,
    make_trial_execution_profile,
    make_trial_execution_projection,
)
from app.modules.model_usage.api import (
    ProjectModelBudgetConfigurationSpec,
    ProjectModelProfileSpec,
)
from app.modules.model_usage.models import ModelUsageEffect
from app.modules.checkers.models import CheckerTrialEvidence
from tests.checkers.execution.support import (
    live_executor,
    provision_post_submit_service,
    reserve,
)
from tests.checkers.external.support import post_registry_spec
from tests.checkers.external.test_trial_evidence import _owner
from tests.checkers.external.test_revision_materialization import (
    DiagnosticMaterialization,
)
from tests.checkers.external.test_trial_policy import trial_specification
from tests.checkers_model_calls.test_composed_execution import (
    model_review_specification,
)
from tests.checkers_model_calls.test_public_api import profile_spec
import tests.post_submit_materialization_helpers as material_helpers
from tests.post_submit_materialization_helpers import material_fixture
from tests.artifact_store_helpers import artifact_admission_limit_settings
from tests.test_s3_artifact_store import minio_settings
from tests.projects.guide_activation.source_fixtures import PostSubmitBindingCase
from tests.test_checker_materialization import _limits


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROJECT_MODEL = REPOSITORY_ROOT / "pilots/terminal_systems/checkers/post/model"
PACKAGE_ROOT = (
    REPOSITORY_ROOT
    / "pilots/terminal_systems/checkers/post/qualification/runtime_package"
)
sys.path.insert(0, str(PROJECT_MODEL))
from trial_plan import (  # noqa: E402
    REVISION_PROJECTION_ID,
    RUNTIME_PROJECTION_ID,
    project_revision_trial_execution_projection,
    project_trial_execution_projection,
    project_trial_projection_selector,
)
from author_checker import AUTHOR_REQUIREMENT  # noqa: E402


class DiagnosticModelProxy(CheckerModelProxy):
    """Keep controlled-provider failure causes in the qualification log."""

    async def _handle(self, request):
        try:
            reply = await super()._handle(request)
        except Exception as error:
            print("model callback error:", type(error).__name__, str(error)[:1_000])
            raise
        print("model callback outcome:", reply.outcome, reply.failure_code)
        return reply


class DiagnosticTrialProxy(CheckerTrialProxy):
    """Retain bounded callback stages without logging material or receipt bodies."""

    async def handle(self, payload):
        operation = payload.get("operation")
        print("trial callback entered:", operation)
        try:
            reply = await super().handle(payload)
        except Exception as error:
            print("trial callback error:", type(error).__name__, str(error)[:1_000])
            raise
        print(
            "trial callback outcome:",
            operation,
            reply.get("outcome"),
            reply.get("failure_code"),
        )
        return reply


REQUIREMENT = "runtime_environment_and_verification_trials"
PROFILE_ID = UUID("018f6f49-66b8-7d2a-bf4d-0e2eeaa00493")
ALPINE_DIGEST = (
    "sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e"
)
TRIAL_DISK_CEILING_BYTES = 2 * 1024 * 1024 * 1024


def _required_environment() -> dict[str, str]:
    names = (
        "WORKSTREAM_TS_SMOL_NODE_CONFIG",
        "WORKSTREAM_TS_SMOL_SERVICE",
        "WORKSTREAM_TS_SMOL_ROOT",
        "WORKSTREAM_TS_SMOL_SUMMARY_PATH",
        "WORKSTREAM_TS_SMOL_PLATFORM_IDENTITY",
        "WORKSTREAM_TS_SMOL_CACHE_DIGEST",
        "WORKSTREAM_TS_SMOL_CHECKER_DIGEST",
    )
    values = {name: os.environ.get(name, "") for name in names}
    assert all(values.values()), f"qualification environment incomplete: {values}"
    return values


def _node_configuration(env: dict[str, str]) -> tuple[dict, dict, dict, dict]:
    """Load one wrapper-provisioned native node and resolve its pinned images."""
    path = Path(env["WORKSTREAM_TS_SMOL_NODE_CONFIG"])
    assert path.is_absolute() and path.is_file() and not path.is_symlink()
    node = json.loads(path.read_text(encoding="utf-8"))
    assert type(node) is dict
    assert node["runtime"] == "smolvm"
    assert node["isolation_mode"] == "smol-microvm"
    assert node.get("docker_binary", "") == ""
    assert node["operating_system"] == "linux" and node["architecture"] == "amd64"
    assert node["sandbox_uid"] == os.geteuid() and node["sandbox_gid"] == os.getegid()
    cache = node["cache"]
    assert type(cache) is list and cache

    def exact(field: str, value: str) -> dict:
        selected = [entry for entry in cache if entry[field] == value]
        assert len(selected) == 1, (field, value, len(selected))
        return selected[0]

    checker = exact(
        "platform_manifest_digest", env["WORKSTREAM_TS_SMOL_CHECKER_DIGEST"]
    )
    builder = exact("config_image_id", node["trial_runtime"]["builder_image_id"])
    intake = exact(
        "platform_manifest_digest", node["trusted_intake"]["platform_manifest_digest"]
    )
    for entry in (checker, builder, intake):
        assert entry["operating_system"] == "linux"
        assert entry["architecture"] == "amd64"
        assert type(entry.get("smol")) is dict
    assert node["trial_runtime"]["outer_runtime_config_digest"] == (
        _runtime_configuration_digest(node)
    )
    return node, checker, builder, intake


def _runtime_configuration_digest(node: dict) -> str:
    """Mirror the closed Rust identity hash without including mutable paths."""
    return external_checker_json_hash(
        {
            "schema_version": "workstream.smol_runtime_configuration.v1",
            "runtime": node["runtime"],
            "isolation_mode": node["isolation_mode"],
            "engine_identity_digest": node["smol"]["binary_sha256"],
            "guest_binary_digest": node["smol"]["guest_sha256"],
            "outer_transport": "workstream.smol_guest_io.v1",
            "child_transport": "workstream.smol_guest_io.v1",
            "network": "none",
            "swap": "none",
            "sandbox_uid": node["sandbox_uid"],
            "sandbox_gid": node["sandbox_gid"],
            "trusted_launcher_digest": node["trial_runtime"][
                "trusted_launcher_digest"
            ],
            "filesystem_tool_digest": node["trial_runtime"][
                "filesystem_tool_digest"
            ],
            "maximum_candidate_archive_bytes": node["trial_runtime"][
                "maximum_candidate_archive_bytes"
            ],
        }
    )


def _direct_baseline_bytes(node: dict, builder: dict) -> int:
    """Measure the directly stored inputs; Rust also charges expanded image facts."""
    paths = (
        node["trial_runtime"]["offline_cache_root"],
        node["trial_runtime"]["trusted_launcher_path"],
        node["trial_runtime"]["filesystem_tool_path"],
        node["smol"]["guest_binary"],
        builder["smol"]["archive"],
        builder["smol"]["image_config"],
    )
    total = 0
    for raw in paths:
        path = Path(raw)
        assert path.is_absolute() and path.exists() and not path.is_symlink()
        if path.is_file():
            total += path.stat().st_size
        else:
            for item in path.rglob("*"):
                assert not item.is_symlink()
                if item.is_file():
                    total += item.stat().st_size
    return total


def _directory_children(path: Path) -> set[str]:
    """Snapshot owned runtime child names without interpreting runtime internals."""
    if not path.exists():
        return set()
    return {item.name for item in path.iterdir()}


def _assert_idle_trial_roots(root: Path, service_root: Path, child_home_root: Path) -> None:
    owner = (service_root / ".workstream-checker-owner").read_text()
    assert len(owner) == 64 and all(
        character in "0123456789abcdef" for character in owner
    )
    for path, role in (
        (root / "trial-relay", "relay"),
        (root / "trial-scratch", "scratch"),
        (child_home_root, "child_home"),
    ):
        identity = path.lstat()
        assert path.resolve() == path and stat.S_ISDIR(identity.st_mode)
        assert (identity.st_uid, identity.st_gid) == (os.geteuid(), os.getegid())
        assert stat.S_IMODE(identity.st_mode) == 0o700
        assert _directory_children(path) == {".workstream-trial-root.json"}
        descriptor = os.open(
            path / ".workstream-trial-root.json",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        )
        with os.fdopen(descriptor, "rb") as marker:
            metadata = os.fstat(marker.fileno())
            assert stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
            assert (metadata.st_uid, metadata.st_gid) == (os.geteuid(), os.getegid())
            assert stat.S_IMODE(metadata.st_mode) == 0o600 and metadata.st_size <= 4096
            assert json.loads(marker.read(4097)) == {
                "schema": "workstream.trial_root.v1",
                "owner": owner,
                "deployment_owner": "terminal-systems-smol-qualification",
                "role": role,
                "path": str(path),
                "device": identity.st_dev,
                "inode": identity.st_ino,
            }


async def _retained_trial_summary(session, retained, receipts):
    """Retain exact verified content/binding identities without provider coordinates."""
    rows = tuple(
        await session.execute(
            select(
                ArtifactBinding,
                ArtifactContent,
                ArtifactPutAttempt,
                ArtifactVerificationReceipt,
            )
            .join(ArtifactContent, ArtifactContent.id == ArtifactBinding.content_id)
            .join(
                ArtifactPutAttempt,
                ArtifactPutAttempt.id == ArtifactBinding.put_attempt_id,
            )
            .join(
                ArtifactVerificationReceipt,
                ArtifactVerificationReceipt.id
                == ArtifactBinding.verification_receipt_id,
            )
            .where(
                ArtifactBinding.resource_type == "checker_trial_evidence",
                ArtifactBinding.resource_id.in_([item.id for item in retained]),
                ArtifactBinding.logical_role == "trial_receipt",
            )
        )
    )
    assert len(rows) == len(retained) == len(receipts) == 2
    bindings = {
        binding.resource_id: (binding, content, attempt, verification)
        for binding, content, attempt, verification in rows
    }
    assert len(bindings) == 2
    by_digest = {external_checker_json_hash(receipt): receipt for receipt in receipts}
    result = []
    for item in sorted(retained, key=lambda item: item.id):
        binding, content, attempt, verification = bindings[item.id]
        assert binding.project_id == item.project_id
        assert binding.scope_version == 1 and binding.supersedes_binding_id is None
        assert binding.put_attempt_id and binding.verification_receipt_id
        assert attempt.checker_trial_evidence_id == item.id
        assert (
            attempt.status == "object_confirmed"
            and attempt.checker_output_custody_sealed
        )
        assert verification.outcome == "verified"
        assert (
            content.sha256
            == item.content_sha256
            == attempt.sha256
            == verification.observed_sha256
        )
        assert (
            content.byte_count == attempt.byte_count == verification.observed_byte_count
        )
        assert content.media_type == attempt.media_type == "application/json"
        receipt = by_digest[item.content_sha256]
        result.append(
            {
                "trial_evidence_id": str(item.id),
                "address_digest": item.address_digest,
                "requirement_id": receipt["originating_identity"]["requirement_id"],
                "receipt_digest": item.content_sha256,
                "artifact_binding_id": str(binding.id),
                "artifact_content_id": str(content.id),
                "artifact_byte_count": content.byte_count,
                "put_attempt_id": str(binding.put_attempt_id),
                "verification_receipt_id": str(binding.verification_receipt_id),
                "candidate_image_digest": receipt["execution"]["build"][
                    "candidate_image_digest"
                ],
                "candidate_archive_digest": receipt["execution"]["build"][
                    "candidate_archive_digest"
                ],
                "step_outcomes": {
                    step["slot_id"]: step["outcome"]
                    for step in receipt["execution"]["steps"]
                },
            }
        )
    return result


def _qualification_archive(evidence_path: str, _project_id) -> bytes:
    """Create one valid submission archive from the explicit package."""
    stream = io.BytesIO()
    names = set()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE_ROOT.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(PACKAGE_ROOT).as_posix()
            names.add(relative)
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = 0o100755 if os.access(path, os.X_OK) else 0o100644
            info.external_attr = mode << 16
            archive.writestr(info, path.read_bytes())
        if evidence_path not in names:
            info = zipfile.ZipInfo(evidence_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, b"qualification-only submission evidence\n")
    return stream.getvalue()


def _trial_authority(
    env: dict[str, str], node: dict, builder: dict, *, revision: bool = False
):
    projected = (
        project_revision_trial_execution_projection()
        if revision
        else project_trial_execution_projection()
    )
    limits = TrialResourceCeilings(
        maximum_total_timeout_ms=360_000,
        maximum_build_timeout_ms=30_000,
        maximum_step_timeout_ms=20_000,
        maximum_steps=35,
        maximum_cpu_quota_millis=1_000,
        maximum_cpu_time_ms=330_000,
        maximum_wall_time_overrun_ms=1_000,
        maximum_cpu_time_overrun_ms=1_000,
        maximum_memory_bytes=1024 * 1024 * 1024,
        maximum_memory_overrun_bytes=4 * 1024 * 1024,
        maximum_pids=128,
        maximum_pids_overrun=4,
        # This whole-invocation ceiling includes the offline cache, expanded
        # pinned builder, three trusted tools, retained candidate and mutable
        # trial state. The old 128 MiB Docker-only fixture did not include that
        # immutable baseline. Two GiB is finite and is checked against the
        # provisioned inputs below; Rust independently charges expanded facts.
        maximum_disk_bytes=TRIAL_DISK_CEILING_BYTES,
        maximum_disk_overrun_bytes=4 * 1024 * 1024,
        maximum_entries=20_000,
        maximum_entries_overrun=32,
        maximum_step_output_bytes=64 * 1024,
        maximum_observation_bytes=512 * 1024,
        maximum_receipt_bytes=1024 * 1024,
        maximum_frame_bytes=1024 * 1024,
        maximum_response_bytes=1024 * 1024,
    )
    profile = make_trial_execution_profile(
        schema_version="workstream.trial_execution_profile.v1",
        selector=TrialProfileSelector(PROFILE_ID, 1, "sha256:" + "0" * 64),
        runtime="smolvm",
        isolation_mode="smol-microvm",
        outer_transport="workstream.smol_guest_io.v1",
        child_transport="workstream.smol_guest_io.v1",
        outer_runtime_config_digest=node["trial_runtime"][
            "outer_runtime_config_digest"
        ],
        child_runtime_config_digest=node["trial_runtime"][
            "outer_runtime_config_digest"
        ],
        engine_identity_digest=node["smol"]["binary_sha256"],
        guest_binary_digest=node["smol"]["guest_sha256"],
        filesystem_tool_digest=node["trial_runtime"]["filesystem_tool_digest"],
        platform="linux/amd64",
        platform_identity_digest=env["WORKSTREAM_TS_SMOL_PLATFORM_IDENTITY"],
        builder_image_digest=builder["platform_manifest_digest"],
        trusted_launcher_digest=node["trial_runtime"]["trusted_launcher_digest"],
        offline_cache_digest=env["WORKSTREAM_TS_SMOL_CACHE_DIGEST"],
        approved_base_digests=(ALPINE_DIGEST,),
        permitted_source_roles=("submission_archive",),
        permitted_material_roles=(
            "build_context",
            "workspace_seed",
            "reference",
            "verification",
        ),
        permitted_operations=("run",),
        permitted_state_retention_outcomes=("succeeded", "exit_nonzero", "signalled"),
        trusted_launcher_capabilities=(
            "CHOWN",
            "DAC_OVERRIDE",
            "FOWNER",
            "KILL",
            "SETGID",
            "SETPCAP",
            "SETUID",
            "SYS_ADMIN",
            "SYS_CHROOT",
        ),
        builder_capabilities=("CHOWN", "DAC_OVERRIDE", "FOWNER"),
        child_capabilities=(),
        child_network="none",
        child_runs_as_non_root=True,
        limits=limits,
    )
    selector = project_trial_projection_selector(revision=revision)
    projection = make_trial_execution_projection(
        selector=TrialProjectionSelector(
            UUID(REVISION_PROJECTION_ID if revision else RUNTIME_PROJECTION_ID),
            selector["trial_projection_version"],
            "sha256:" + "0" * 64,
        ),
        trial_kind=projected["trial_kind"],
        material_projections=tuple(
            TrialMaterialProjection(
                item["role"],
                item["source_role"],
                item["projection_kind"],
                item["source_relative"],
                item["destination_relative"],
                tuple(item["exclusions"]),
            )
            for item in projected["material_projections"]
        ),
        allowed_material_roles=tuple(projected["allowed_material_roles"]),
        build_context_roles=tuple(projected["build_context_roles"]),
        slot_templates=tuple(
            TrialSlotProjection(
                item["slot_kind"],
                item["minimum_occurrences"],
                item["maximum_occurrences"],
                tuple(item["seed_roles"]),
                tuple(item["visible_roles"]),
                item["fresh_workspace"],
                tuple(item["retain_state_after"]),
            )
            for item in projected["slot_templates"]
        ),
    )
    assert project_trial_projection_selector(revision=revision) == {
        "trial_projection_id": str(projection.selector.projection_id),
        "trial_projection_version": projection.selector.projection_version,
        "trial_projection_digest": projection.selector.projection_digest,
    }
    return profile, projection


def _registry_spec(image_digest: str, profile, projection):
    values = {
        "trial_profile_id": str(profile.selector.profile_id),
        "trial_profile_version": profile.selector.profile_version,
        "trial_profile_digest": profile.selector.profile_digest,
        "trial_projection_id": str(projection.selector.projection_id),
        "trial_projection_version": projection.selector.projection_version,
        "trial_projection_digest": projection.selector.projection_digest,
    }
    properties = {key: {"const": value} for key, value in values.items()}
    properties["check"] = {"enum": [AUTHOR_REQUIREMENT, REQUIREMENT]}
    properties.update(
        model_profile_id={"type": "string"},
        model_profile_version={"type": "integer"},
        model_profile_digest={"type": "string"},
    )
    document = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(properties),
    }
    base = post_registry_spec()
    updated = base.model_copy(
        update={
            "capability_id": "terminal_systems.post.model",
            "capability_version": "v1",
            "image_digest": image_digest,
            "resources": base.resources.model_copy(
                update={
                    "cpu_millis": 1_000,
                    "memory_bytes": 512 * 1024 * 1024,
                    "deadline_ms": 600_000,
                    "maximum_output_bytes": 64 * 1024,
                }
            ),
            "configuration_schema": ExternalCheckerSchema(
                schema_id="terminal_systems.post.runtime_qualification.configuration",
                schema_version="v1",
                document=document,
                schema_sha256=external_checker_json_hash(document),
            ),
        }
    )
    return type(base).model_validate(updated.model_dump(mode="json")), values


def _trial_model_specification() -> CheckSpecification:
    """Declare both the nested sandbox and the bounded semantic assessment."""
    trial = trial_specification()
    model = model_review_specification()
    model_dependency = next(
        item for item in model.runtime_dependencies if item.kind == "model_service"
    )
    return CheckSpecification.model_validate(
        trial.model_dump(mode="json")
        | {
            "runtime_dependencies": [
                *trial.model_dump(mode="json")["runtime_dependencies"],
                model_dependency.model_dump(mode="json"),
            ]
        }
    )


def _manifest(bindings, profile, projection) -> dict[str, object]:
    value = {
        "protocol_version": "workstream.trial_authority_manifest.v1",
        "entries": [
            {
                "registry_entry_id": str(binding.registry.registry_entry_id),
                "registry_entry_digest": binding.registry.entry_digest,
                "checker_image_digest": binding.registry.image_digest,
                "configuration_sha256": binding.configuration_sha256,
                "profile": asdict(profile),
                "projection": asdict(projection),
            }
            for binding in bindings
        ],
    }
    return json.loads(json.dumps(value, default=str))


def _procedure(identifier, purpose, command, state_source, evidence_id, line):
    return {
        "procedure_id": identifier,
        "purpose": purpose,
        "command_text": " ".join(command),
        "command": command,
        "working_directory": ".",
        "state_source": state_source,
        "evidence_id": evidence_id,
        "start_line": line,
        "end_line": line,
    }


def _provider_output(prompt: str, index: int, observations: list[dict]) -> str:
    value = json.loads(prompt)
    if value.get("schema_version") == "terminal_systems.trial_plan_proposal.v2":
        observations.append({"planner_prompt": value})
        procedures = [
            _procedure(
                "qualification_status",
                "documented_command",
                ["qualification-status"],
                "fresh",
                "source_1",
                5,
            ),
            _procedure(
                "apply_incomplete",
                "incomplete_repair",
                ["sh", "solution/incomplete.sh"],
                "fresh",
                "source_2",
                3,
            ),
            _procedure(
                "remove_output",
                "missing_output_mutation",
                ["sh", "tests/remove-output.sh"],
                "reference_baseline",
                "source_2",
                4,
            ),
            _procedure(
                "fabricate_output",
                "fabricated_output_mutation",
                ["sh", "tests/fabricate-output.sh"],
                "reference_baseline",
                "source_2",
                5,
            ),
            _procedure(
                "interrupt_work",
                "controlled_interruption",
                ["sh", "tests/interrupt.sh"],
                "reference_baseline",
                "source_2",
                6,
            ),
            _procedure(
                "restart_work",
                "restart",
                ["sh", "tests/restart.sh"],
                "interrupt_work",
                "source_2",
                7,
            ),
        ]
        return json.dumps(
            {
                "schema_version": "terminal_systems.trial_plan_proposal.v2",
                "material_digest": value["material_digest"],
                "recovery_applicability": {
                    "required": True,
                    "evidence_id": "source_1",
                    "start_line": 1,
                    "end_line": next(
                        item["line_count"]
                        for item in value["untrusted_source_evidence"]
                        if item["path"] == "instruction.md"
                    ),
                },
                "coverage_complete": True,
                "procedures": procedures,
                "coverage_gaps": [],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    assert value["schema_version"] == "workstream.model_prompt_with_receipts.v1"
    assert len(value["trusted_receipts"]) == 1
    receipt = value["trusted_receipts"][0]["receipt"]
    observations.append({"receipt": receipt})
    assessment = json.loads(value["prompt"])
    result = {
        "schema_version": "terminal_systems.model_assessment.v1",
        "requirement_id": assessment["rubric"]["requirement_id"],
        "material_digest": assessment["untrusted_evidence_data"]["material_digest"],
        "conditions": [
            {
                "condition_number": item["condition_number"],
                "status": "satisfied",
                "evidence_ids": ["trial_receipt"],
                "finding_numbers": [],
            }
            for item in assessment["rubric"]["pass_conditions"]
        ],
        "findings": [],
    }
    instruction = next(
        item
        for item in assessment["untrusted_evidence_data"]["evidence"]
        if item["path"] == "instruction.md"
    )
    return json.dumps(
        {
            "recovery_applicability": {
                "required": True,
                "evidence_id": instruction["evidence_id"],
                "start_line": 1,
                "end_line": instruction["line_count"],
            },
            "assessment": result,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _wait_for_socket(
    path: Path, process: subprocess.Popen, timeout: float = 30.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"Rust service exited early with {process.returncode}")
        if path.is_socket():
            with socket.socket(socket.AF_UNIX) as stream:
                try:
                    stream.connect(str(path))
                except OSError:
                    pass
                else:
                    return
        time.sleep(0.05)
    raise AssertionError("Rust service socket did not become ready")


async def test_production_service_executes_project_trial_under_smol_with_real_custody(
    tmp_path, isolated_database_env, admin_access, monkeypatch, *, recovery=None
):
    """Prove the exact qualification boundary; no live model provider is used."""
    env = _required_environment()
    configured_root = Path(env["WORKSTREAM_TS_SMOL_ROOT"])
    assert configured_root.is_absolute() and not configured_root.is_symlink()
    root = configured_root.resolve(strict=True)
    assert root == configured_root and root.stat().st_mode & 0o077 == 0
    node, checker_image, builder_image, intake_image = _node_configuration(env)
    child_home_root = Path(node["trial_runtime"]["child_home_root"])
    assert child_home_root.is_absolute() and child_home_root.resolve(strict=True) == child_home_root
    assert len(os.fsencode(child_home_root)) <= 18
    child_root_stat = child_home_root.lstat()
    assert stat.S_ISDIR(child_root_stat.st_mode)
    assert stat.S_IMODE(child_root_stat.st_mode) == 0o700
    assert (child_root_stat.st_uid, child_root_stat.st_gid) == (os.geteuid(), os.getegid())
    assert not _directory_children(child_home_root), "qualification requires a fresh owned child HOME root"
    service_binary = Path(env["WORKSTREAM_TS_SMOL_SERVICE"])
    assert service_binary.is_absolute() and service_binary.is_file()
    assert not service_binary.is_symlink() and os.access(service_binary, os.X_OK)
    # The Rust runtime additionally scans expanded builder contents and rejects
    # the invocation before its first model call if the complete baseline does
    # not fit. This direct measurement prevents an unexplained fixture increase.
    assert _direct_baseline_bytes(node, builder_image) < TRIAL_DISK_CEILING_BYTES
    archive_factory = _qualification_archive
    if recovery is not None:
        archive_factory = recovery.archive_factory(_qualification_archive)
    monkeypatch.setattr(material_helpers, "archive_with_modes", archive_factory)
    await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    profile, projection = _trial_authority(env, node, builder_image)
    _trial_authority(env, node, builder_image, revision=True)
    registry_spec, trial_values = _registry_spec(
        env["WORKSTREAM_TS_SMOL_CHECKER_DIGEST"], profile, projection
    )
    model_profiles = []

    async def binding_cases(_factory, project_id, registry):
        selected = ProjectModelProfileSpec.model_validate(
            profile_spec(project_id)
            .model_copy(
                update={
                    "registry_entry_id": registry.registry_entry_id,
                    "registry_entry_digest": registry.entry_digest,
                    "maximum_request_bytes": 512 * 1024,
                    "maximum_output_bytes": 64 * 1024,
                    "maximum_response_bytes": 1024 * 1024,
                    "maximum_input_tokens": 100_000,
                    "maximum_output_tokens": 20_000,
                    "maximum_calls": 2,
                    "maximum_total_request_bytes": 1024 * 1024,
                    "maximum_total_response_bytes": 2 * 1024 * 1024,
                    "maximum_total_input_tokens": 200_000,
                    "maximum_total_output_tokens": 40_000,
                    "allowed_tools": ("trial_receipt",),
                    "maximum_tool_calls": 1,
                    "maximum_tool_output_bytes": 1024 * 1024,
                    "deadline_ms": 600_000,
                }
            )
            .model_dump(mode="json")
        )
        response = await admin_access.signed.client.post(
            f"/api/v1/operations/projects/{project_id}/model-profiles",
            headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
            json=selected.model_dump(mode="json"),
        )
        assert response.status_code == 201, response.text
        model_profiles.append(response.json())
        budget_spec = ProjectModelBudgetConfigurationSpec(
            project_id=project_id,
            configuration_version=1,
            authorized_total_nanodollars=10_000_000_000,
            externally_reconciled_prior_spend_nanodollars=0,
            lifetime_limit_nanodollars=10_000_000_000,
        )
        budget = await admin_access.signed.client.post(
            f"/api/v1/operations/projects/{project_id}/model-budget-configurations",
            headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
            json=budget_spec.model_dump(mode="json"),
        )
        assert budget.status_code == 201, budget.text
        shared = trial_values | {
            "model_profile_id": response.json()["profile_id"],
            "model_profile_version": response.json()["spec"]["profile_version"],
            "model_profile_digest": response.json()["profile_digest"],
        }
        specification = _trial_model_specification()
        return tuple(
            PostSubmitBindingCase(
                requirement_id=requirement_id,
                statement=statement,
                classification_rationale=(
                    "A project image evaluates immutable material through bounded model and "
                    "isolated trial dependencies."
                ),
                specification=specification,
                parameters=tuple(
                    CapabilityParameter(name=key, value=value)
                    for key, value in (shared | {"check": requirement_id}).items()
                ),
            )
            for requirement_id, statement in (
                (
                    AUTHOR_REQUIREMENT,
                    "Compare author claims with authenticated trial evidence.",
                ),
                (
                    REQUIREMENT,
                    "Evaluate runtime and verification behavior in isolated trials.",
                ),
            )
            if recovery is None or requirement_id == REQUIREMENT
        )

    post_scratch = root / "post-scratch"
    post_scratch.mkdir(mode=0o700)
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        provider="minio",
        storage_settings=minio_settings(
            private_prefix=f"{os.environ['WORKSTREAM_TEST_MINIO_PREFIX']}/smol/{uuid4()}"
        ).model_copy(
            update={
                **artifact_admission_limit_settings(1024 * 1024),
                "artifact_s3_bucket": os.environ["WORKSTREAM_TEST_MINIO_BUCKET"],
                "artifact_scratch_root": tmp_path / "intake-scratch",
                "artifact_scratch_minimum_free_bytes": 0,
                # Exercise the deployed buffer, not the two-byte boundary-test fixture.
                "artifact_stream_buffer_bytes": 1024 * 1024,
            }
        ),
        post_submit_registry_spec=registry_spec,
        post_submit_bindings_setup=binding_cases,
        post_scratch_root=post_scratch,
        scratch_limits=_limits(
            aggregate_reserved_bytes=5 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=5,
            maximum_concurrency=5,
            total_deadline_seconds=720.0,
            reservation_ttl_seconds=750.0,
        ),
    ) as h:
        # Fixture creation deliberately uses its in-process intake to seed the
        # already-verified submission admission. The public post-submit journey
        # below is recomposed with the native trusted-intake socket only after
        # the authority manifest and Rust service exist.
        await provision_post_submit_service(
            h.factory, ServiceIdentity.ARTIFACT_CHECKER_OUTPUT
        )
        expected_requirements = (
            {AUTHOR_REQUIREMENT, REQUIREMENT} if recovery is None else {REQUIREMENT}
        )
        assert len(h.request.policy.entries) == len(expected_requirements)
        assert {
            entry.requirement_id: entry.configuration["check"]
            for entry in h.request.policy.entries
        } == {requirement: requirement for requirement in expected_requirements}
        assert (
            len(
                {
                    (
                        entry.configuration["trial_profile_digest"],
                        entry.configuration["trial_projection_digest"],
                    )
                    for entry in h.request.policy.entries
                }
            )
            == 1
        )
        assert (
            len({entry.configuration_sha256 for entry in h.request.policy.entries})
            == len(expected_requirements)
        )
        manifest = _manifest(h.request.policy.entries, profile, projection)
        manifest_bytes = json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        manifest_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = root / "trial-authority.json"
        manifest_path.write_bytes(manifest_bytes)
        manifest_path.chmod(0o400)
        catalog = load_trial_authority_manifest(manifest_path, manifest_digest)

        observations: list[dict] = []
        creates = []

        class Provider:
            async def create(self, model_request):
                index = len(creates)
                creates.append(model_request)
                output = _provider_output(model_request.prompt, index, observations)
                reference = CheckerModelResponseReference(f"resp_ts_smol_{index}")
                return CheckerModelCreateResult(
                    CheckerModelCreateOutcome.ACCEPTED,
                    known_response=reference,
                    observation=CheckerModelObservation(
                        reference,
                        model_profiles[0]["spec"]["model_snapshot"],
                        CheckerModelProviderStatus.COMPLETED,
                        output,
                        CheckerModelUsage(200, 0, 100, 20, 300),
                    ),
                )

            async def recover(self, _reference):
                raise AssertionError(
                    "completed controlled calls must use retained responses"
                )

        @asynccontextmanager
        async def provider(_profile):
            yield Provider()

        outputs = checker_output_storage(
            reservations=checker_output_reservations,
            sessions=h.factory,
            store=h.store.wrapped,
            namespace=h.namespace,
            preparation=h.preparation,
            settings=h.settings,
        )
        model_proxy = DiagnosticModelProxy(
            sessions=h.factory,
            authorization=checker_model_service_authorization,
            grants=model_invocation_grants,
            calls=model_call_service,
            profiles=model_profile_reader,
            outputs=outputs,
            bindings=lambda session: checker_output_binding(
                session,
                namespace=h.namespace,
                reservations=checker_output_reservations(session),
            ),
            provider=provider,
        )

        def trial_reservations(session, external):
            return _owner(session, external, catalog)

        trial_proxy = DiagnosticTrialProxy(
            sessions=h.factory,
            reservations=trial_reservations,
            profiles=catalog,
            outputs=lambda external: checker_output_storage(
                sessions=h.factory,
                store=h.store.wrapped,
                namespace=h.namespace,
                preparation=h.preparation,
                settings=h.settings,
                reservations=lambda session: trial_reservations(session, external),
            ),
            bindings=lambda session, external: checker_output_binding(
                session,
                namespace=h.namespace,
                reservations=trial_reservations(session, external),
            ),
        )

        proxy_root = root / "private-proxy"
        service_root = root / "service"
        for directory in (
            proxy_root,
            service_root,
            root / "model-relay",
            root / "trial-relay",
            root / "trial-scratch",
        ):
            directory.mkdir(mode=0o700, exist_ok=True)
        proxy_path = proxy_root / "proxy.sock"
        service_socket = service_root / "checker.sock"
        service_config = json.loads(json.dumps(node))
        service_config.update(
            socket_path=str(service_socket),
            model_proxy_socket=str(proxy_path),
            model_relay_root=str(root / "model-relay"),
            trial_authority_manifest_path=str(manifest_path),
            trial_authority_manifest_digest=manifest_digest,
            material_root=str(post_scratch),
            docker_binary="",
            sandbox_uid=os.geteuid(),
            sandbox_gid=os.getegid(),
        )
        service_config["trial_runtime"].update(
            relay_root=str(root / "trial-relay"),
            scratch_root=str(root / "trial-scratch"),
            deployment_owner="terminal-systems-smol-qualification",
        )
        runtime_configuration_digest = _runtime_configuration_digest(service_config)
        service_config["trial_runtime"][
            "outer_runtime_config_digest"
        ] = runtime_configuration_digest
        assert profile.outer_runtime_config_digest == runtime_configuration_digest
        assert profile.child_runtime_config_digest == runtime_configuration_digest
        assert service_config["trial_runtime"]["builder_image_id"] == builder_image[
            "config_image_id"
        ]
        assert service_config["smol"]["binary_sha256"] == profile.engine_identity_digest
        assert service_config["smol"]["guest_sha256"] == profile.guest_binary_digest
        assert service_config["trial_runtime"]["filesystem_tool_digest"] == (
            profile.filesystem_tool_digest
        )
        config_path = root / "service.json"
        config_path.write_text(
            json.dumps(service_config, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        config_path.chmod(0o400)
        service_log = (root / "service.stderr").open("w", encoding="utf-8")
        vms_root = Path(node["smol"]["home"]) / ".cache/smolvm/vms"
        cgroup_root = Path(node["smol"]["cgroup_root"])
        before_vms = _directory_children(vms_root)
        before_cgroups = _directory_children(cgroup_root)
        service = None
        try:
            async with ModelProxyTransport(
                socket_path=proxy_path,
                handler=model_proxy.handle,
                trial_handler=trial_proxy.handle,
                read_timeout_seconds=60.0,
                write_timeout_seconds=60.0,
                shutdown_timeout_seconds=30.0,
            ):
                service = subprocess.Popen(
                    [str(service_binary), str(config_path)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=service_log,
                    text=True,
                )
                _wait_for_socket(service_socket, service)
                intake = UnixSocketTrustedIntakeAdapter(
                    socket_path=service_socket,
                    image_digest=intake_image["platform_manifest_digest"],
                    config_digest=intake_image["config_image_id"],
                )
                intake_health = await intake.health()
                assert (
                    intake_health.image_digest,
                    intake_health.config_digest,
                    intake_health.runtime,
                    intake_health.isolation_mode,
                ) == (
                    intake_image["platform_manifest_digest"],
                    intake_image["config_image_id"],
                    "smolvm",
                    "smol-microvm",
                )
                monkeypatch.setattr(
                    material_helpers,
                    "LocalIntakeAdapter",
                    lambda _inspector=None: intake,
                )
                h.service = DiagnosticMaterialization(
                    post_submission_materialization(
                        sessions=h.factory,
                        store=h.store,
                        namespace=h.namespace,
                        preparation=h.preparation,
                        intake=material_helpers.LocalIntakeAdapter(h.inspector),
                        archive_limits=SubmissionArchiveLimits(),
                        artifact_deadline_ms=120_000,
                    )
                )
                adapter = UnixSocketExternalCheckerAdapter(
                    socket_path=service_socket, timeout_seconds=660.0
                )
                health = await adapter.health()
                assert (health.runtime, health.isolation_mode) == (
                    "smolvm",
                    "smol-microvm",
                )
                await reserve(h)
                executor = live_executor(
                    h,
                    selected_execution=ModelAwareExternalExecution(
                        execution=adapter, sessions=h.factory
                    ),
                )
                if recovery is not None:
                    await recovery.exercise(
                        executor=executor,
                        harness=h,
                        controller=service,
                        service_binary=service_binary,
                        config_path=config_path,
                        config=service_config,
                        service_log=service_log,
                        intake=intake,
                        observations=observations,
                        creates=creates,
                    )
                    _assert_idle_trial_roots(root, service_root, child_home_root)
                    assert _directory_children(service_root / "smol-leases") == set()
                    assert _directory_children(vms_root) == before_vms
                    assert _directory_children(cgroup_root) == before_cgroups
                    return
                result = await executor.evaluate_post_submission(h.request)
            assert result.outcome == "completed", (
                result,
                len(creates),
                len(observations),
            )
            assert len(result.execution.external_members) == 2
            # This qualification is an initial submission: it proves the
            # current-only least-material path and explicitly does not claim a
            # predecessor/archive revision journey.
            assert all(
                member.input_receipt is None
                for member in result.execution.external_members
            )
            assert {
                member.requirement_id: (member.result.outcome, member.result.verdict)
                for member in result.execution.external_members
            } == {
                AUTHOR_REQUIREMENT: ("completed", "passed"),
                REQUIREMENT: ("completed", "passed"),
            }
            assert len(creates) == 4
            receipts = [item["receipt"] for item in observations if "receipt" in item]
            assert len(receipts) == 2
            assert {
                receipt["originating_identity"]["requirement_id"]
                for receipt in receipts
            } == {AUTHOR_REQUIREMENT, REQUIREMENT}
            for receipt in receipts:
                assert receipt["plan_completed"] is True
                assert receipt["cleanup_confirmed"] is True
                assert (
                    receipt["engine_identity_digest"]
                    == node["smol"]["binary_sha256"]
                )
                execution = receipt["execution"]
                assert (
                    execution["platform_identity_digest"]
                    == env["WORKSTREAM_TS_SMOL_PLATFORM_IDENTITY"]
                )
                assert (
                    execution["builder_image_digest"]
                    == builder_image["platform_manifest_digest"]
                )
                assert (
                    execution["trusted_launcher_digest"]
                    == node["trial_runtime"]["trusted_launcher_digest"]
                )
                assert (
                    execution["offline_cache_digest"]
                    == env["WORKSTREAM_TS_SMOL_CACHE_DIGEST"]
                )
                assert execution["approved_base_digests"] == [ALPINE_DIGEST]
                assert execution["build"]["outcome"] == "succeeded"
                assert execution["build"]["candidate_image_digest"].startswith(
                    "sha256:"
                )
                outcomes = {
                    item["slot_id"]: item["outcome"] for item in execution["steps"]
                }
                assert len(outcomes) == 17
                assert outcomes["qualification_status"] == "succeeded"
                assert outcomes["starter_verification"] == "exit_nonzero"
                assert outcomes["reference_verify_1"] == "succeeded"
                assert outcomes["reference_verify_2"] == "succeeded"
                assert outcomes["reference_verify_3"] == "succeeded"
                assert outcomes["apply_incomplete_verification"] == "exit_nonzero"
                assert outcomes["remove_output_verification"] == "exit_nonzero"
                assert outcomes["fabricate_output_verification"] == "exit_nonzero"
                assert outcomes["interrupt_work"] == "signalled"
                assert outcomes["restart_work_verification"] == "succeeded"
            assert await executor.evaluate_post_submission(h.request) == result
            assert len(creates) == 4
            async with h.factory() as session:
                effects = tuple(await session.scalars(select(ModelUsageEffect)))
                assert len(effects) == 4
                assert all(item.state == "completed" for item in effects)
                assert all(
                    UUID(item.request_binding_id).version == 7 for item in effects
                )
                assert all(
                    UUID(item.response_binding_id).version == 7 for item in effects
                )
                retained = tuple(await session.scalars(select(CheckerTrialEvidence)))
                assert len(retained) == 2
                assert {item.content_sha256 for item in retained} == {
                    external_checker_json_hash(receipt) for receipt in receipts
                }
                trial_summary = await _retained_trial_summary(
                    session, retained, receipts
                )
                model_summary = [
                    {
                        "effect_id": str(item.id),
                        "request_binding_id": str(item.request_binding_id),
                        "response_binding_id": str(item.response_binding_id),
                        "settled_nanodollars": item.settled_nanodollars,
                    }
                    for item in sorted(effects, key=lambda item: item.id)
                ]
            _assert_idle_trial_roots(root, service_root, child_home_root)
            assert _directory_children(service_root / "smol-leases") == set()
            assert _directory_children(vms_root) == before_vms
            assert _directory_children(cgroup_root) == before_cgroups
        finally:
            if recovery is not None:
                recovery.close()
            if service is not None and service.poll() is None:
                service.terminate()
                try:
                    service.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    service.kill()
                    service.wait(timeout=15)
            service_log.close()
            diagnostic = (root / "service.stderr").read_text(encoding="utf-8")
            if diagnostic:
                print("Rust service diagnostic:", diagnostic[-16_384:])
            if (
                service is not None
                and service.returncode not in {0, -15, 143}
                and not (recovery is not None and recovery.expected_controller_exit(service))
            ):
                raise AssertionError(
                    (root / "service.stderr").read_text(encoding="utf-8")
                )
    summary = {
        "schema_version": "workstream.terminal_systems_composition_evidence.v1",
        "provider_mode": "controlled",
        "guide_to_contribution_proven": False,
        "image": {
            "digest": env["WORKSTREAM_TS_SMOL_CHECKER_DIGEST"],
            "id": checker_image["config_image_id"],
        },
        "profile": {
            "id": str(profile.selector.profile_id),
            "version": profile.selector.profile_version,
            "digest": profile.selector.profile_digest,
        },
        "projection": {
            "id": str(projection.selector.projection_id),
            "version": projection.selector.projection_version,
            "digest": projection.selector.projection_digest,
        },
        "authority_manifest_digest": manifest_digest,
        "runtime": {
            "runtime": "smolvm",
            "isolation_mode": "smol-microvm",
            "platform": profile.platform,
            "platform_identity_digest": env[
                "WORKSTREAM_TS_SMOL_PLATFORM_IDENTITY"
            ],
            "outer_configuration_digest": profile.outer_runtime_config_digest,
            "child_configuration_digest": profile.child_runtime_config_digest,
            "engine_digest": profile.engine_identity_digest,
            "guest_digest": profile.guest_binary_digest,
            "filesystem_tool_digest": profile.filesystem_tool_digest,
            "launcher_digest": profile.trusted_launcher_digest,
            "builder_image_id": builder_image["config_image_id"],
            "builder_manifest": builder_image["platform_manifest_digest"],
            "offline_cache_digest": env["WORKSTREAM_TS_SMOL_CACHE_DIGEST"],
            "approved_base_digests": list(profile.approved_base_digests),
            "maximum_disk_bytes": profile.limits.maximum_disk_bytes,
        },
        "model_effects": model_summary,
        "trials": trial_summary,
        "replay_additional_provider_calls": len(creates) - 4,
        "predecessor_material_exercised": False,
        "owned_runtime_resources_removed": True,
    }
    encoded = json.dumps(
        summary, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    assert len(encoded) <= 64 * 1024
    summary_path = Path(env["WORKSTREAM_TS_SMOL_SUMMARY_PATH"])
    assert summary_path.is_absolute() and root not in summary_path.parents
    descriptor = os.open(summary_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
