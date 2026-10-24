"""Explicit production Rust/runsc/trial/ART composition qualification.

This test is invoked only by ``qualify_terminal_systems_runsc.sh``. It uses the
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
import subprocess
import sys
import time
from uuid import UUID, uuid4
import zipfile

from sqlalchemy import select

from app.adapters.artifacts import checker_output_binding, checker_output_storage
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
from app.modules.artifacts.preparation import HARD_MAXIMUM_ARTIFACT_BYTES
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
from tests.checkers.external.test_revision_materialization import DiagnosticMaterialization
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
    REPOSITORY_ROOT / "pilots/terminal_systems/checkers/post/qualification/runtime_package"
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
        print("trial callback outcome:", operation, reply.get("outcome"), reply.get("failure_code"))
        return reply


REQUIREMENT = "runtime_environment_and_verification_trials"
PROFILE_ID = UUID("018f6f49-66b8-7d2a-bf4d-0e2eeaa00493")
ALPINE_DIGEST = "sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e"


def _required_environment() -> dict[str, str]:
    names = (
        "WORKSTREAM_TS_RUNSC_COMPOSITION_ROOT",
        "WORKSTREAM_TS_RUNSC_INNER_COMPOSITION_ROOT",
        "WORKSTREAM_TS_RUNSC_SOCKET_ROOT",
        "WORKSTREAM_TS_RUNSC_INNER_SOCKET_ROOT",
        "WORKSTREAM_TS_RUNSC_CONTAINER",
        "WORKSTREAM_TS_RUNSC_DAEMON_DIGEST",
        "WORKSTREAM_TS_RUNSC_PLATFORM_IDENTITY",
        "WORKSTREAM_TS_RUNSC_CHECKER_REPOSITORY",
        "WORKSTREAM_TS_RUNSC_CHECKER_DIGEST",
        "WORKSTREAM_TS_RUNSC_CHECKER_ID",
        "WORKSTREAM_TS_RUNSC_BUILDER_ID",
        "WORKSTREAM_TS_RUNSC_BUILDER_MANIFEST",
        "WORKSTREAM_TS_RUNSC_CACHE_DIGEST",
        "WORKSTREAM_TS_RUNSC_ENGINE_DIGEST",
    )
    values = {name: os.environ.get(name, "") for name in names}
    assert all(values.values()), f"qualification environment incomplete: {values}"
    return values


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


def _trial_authority(env: dict[str, str], *, revision: bool = False):
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
        maximum_swap_bytes=1024 * 1024 * 1024,
        maximum_memory_overrun_bytes=4 * 1024 * 1024,
        maximum_pids=128,
        maximum_pids_overrun=4,
        maximum_disk_bytes=128 * 1024 * 1024,
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
        runtime="runsc",
        isolation_mode="gvisor",
        outer_host_uds="open",
        child_host_uds="none",
        outer_runtime_config_digest=env["WORKSTREAM_TS_RUNSC_DAEMON_DIGEST"],
        child_runtime_config_digest=env["WORKSTREAM_TS_RUNSC_DAEMON_DIGEST"],
        engine_identity_digest=env["WORKSTREAM_TS_RUNSC_ENGINE_DIGEST"],
        platform="linux/amd64",
        platform_identity_digest=env["WORKSTREAM_TS_RUNSC_PLATFORM_IDENTITY"],
        builder_image_digest=env["WORKSTREAM_TS_RUNSC_BUILDER_ID"],
        trusted_launcher_digest=env["WORKSTREAM_TS_RUNSC_LAUNCHER_DIGEST"],
        offline_cache_digest=env["WORKSTREAM_TS_RUNSC_CACHE_DIGEST"],
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
    projection = make_trial_execution_projection(
        selector=TrialProjectionSelector(
            UUID(REVISION_PROJECTION_ID if revision else RUNTIME_PROJECTION_ID),
            1,
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
    if value.get("schema_version") == "terminal_systems.trial_plan_proposal.v1":
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
                "fresh",
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
                "schema_version": "terminal_systems.trial_plan_proposal.v1",
                "material_digest": value["material_digest"],
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
    return json.dumps(
        {
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
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _wait_for_socket(path: Path, process: subprocess.Popen, timeout: float = 30.0) -> None:
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


async def test_production_service_executes_project_trial_under_runsc_with_real_custody(
    tmp_path, isolated_database_env, admin_access, monkeypatch
):
    """Prove the exact qualification boundary; no live model provider is used."""
    env = _required_environment()
    root = Path(env["WORKSTREAM_TS_RUNSC_COMPOSITION_ROOT"]).resolve(strict=True)
    inner = env["WORKSTREAM_TS_RUNSC_INNER_COMPOSITION_ROOT"]
    assert root.name == "terminal-systems-runsc-composition"
    builder_image_id = subprocess.check_output(
        [
            "docker",
            "exec",
            env["WORKSTREAM_TS_RUNSC_CONTAINER"],
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            env["WORKSTREAM_TS_RUNSC_BUILDER_ID"],
        ],
        text=True,
        timeout=15,
    ).strip()
    assert builder_image_id == env["WORKSTREAM_TS_RUNSC_BUILDER_ID"]
    monkeypatch.setattr(material_helpers, "archive_with_modes", _qualification_archive)
    await admin_access.signed.grant(admin_access.admin, admin_access.target, role="operator")
    profile, projection = _trial_authority(env)
    _trial_authority(env, revision=True)
    registry_spec, trial_values = _registry_spec(
        env["WORKSTREAM_TS_RUNSC_CHECKER_DIGEST"], profile, projection
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
                (AUTHOR_REQUIREMENT, "Compare author claims with authenticated trial evidence."),
                (REQUIREMENT, "Evaluate runtime and verification behavior in isolated trials."),
            )
        )

    post_scratch = root / "post-scratch"
    post_scratch.mkdir(mode=0o700)
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        provider="minio",
        storage_settings=minio_settings(private_prefix=f"runsc/{uuid4()}").model_copy(
            update={
                **artifact_admission_limit_settings(1024 * 1024),
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
        h.service = DiagnosticMaterialization(h.service)
        await provision_post_submit_service(h.factory, ServiceIdentity.ARTIFACT_CHECKER_OUTPUT)
        assert len(h.request.policy.entries) == 2
        assert {
            entry.requirement_id: entry.configuration["check"]
            for entry in h.request.policy.entries
        } == {AUTHOR_REQUIREMENT: AUTHOR_REQUIREMENT, REQUIREMENT: REQUIREMENT}
        assert len(
            {
                (
                    entry.configuration["trial_profile_digest"],
                    entry.configuration["trial_projection_digest"],
                )
                for entry in h.request.policy.entries
            }
        ) == 1
        assert len({entry.configuration_sha256 for entry in h.request.policy.entries}) == 2
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
                reference = CheckerModelResponseReference(f"resp_ts_runsc_{index}")
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
                raise AssertionError("completed controlled calls must use retained responses")

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

        socket_root = Path(env["WORKSTREAM_TS_RUNSC_SOCKET_ROOT"]).resolve(strict=True)
        inner_socket_root = env["WORKSTREAM_TS_RUNSC_INNER_SOCKET_ROOT"]
        proxy_root = socket_root / "private-proxy"
        service_root = socket_root / "service"
        for directory in (
            proxy_root,
            service_root,
            root / "model-relay",
            root / "trial-relay",
            root / "trial-scratch",
            root / "trial-runtime",
        ):
            directory.mkdir(mode=0o700, exist_ok=True)
        proxy_path = proxy_root / "proxy.sock"
        service_socket = service_root / "checker.sock"
        service_config = {
            "socket_path": f"{inner_socket_root}/service/checker.sock",
            "model_proxy_socket": f"{inner_socket_root}/private-proxy/proxy.sock",
            "model_relay_root": f"{inner}/model-relay",
            "trial_authority_manifest_path": f"{inner}/trial-authority.json",
            "trial_authority_manifest_digest": manifest_digest,
            "trial_runtime": {
                "relay_root": f"{inner}/trial-relay",
                "scratch_root": f"{inner}/trial-scratch",
                "runtime_root": f"{inner}/trial-runtime",
                "runtime_configuration": "/etc/docker/pilot-daemon.json",
                "outer_runtime_config_digest": env["WORKSTREAM_TS_RUNSC_DAEMON_DIGEST"],
                "offline_cache_root": "/workstream-state/cache/content",
                "deployment_owner": "terminal-systems-runsc-qualification",
                "runtime_key": "runsc-trial",
                "builder_image_id": env["WORKSTREAM_TS_RUNSC_BUILDER_ID"],
                "trusted_launcher_path": env["WORKSTREAM_TS_RUNSC_LAUNCHER_PATH"],
                "trusted_launcher_digest": env["WORKSTREAM_TS_RUNSC_LAUNCHER_DIGEST"],
                "maximum_candidate_archive_bytes": 64 * 1024 * 1024,
            },
            "material_root": f"{inner}/post-scratch",
            "docker_binary": "/usr/local/bin/docker",
            "runtime": "runsc",
            "isolation_mode": "gvisor",
            "operating_system": "linux",
            "architecture": "amd64",
            "sandbox_uid": os.geteuid(),
            "sandbox_gid": os.getegid(),
            "cache": [
                {
                    "repository": env["WORKSTREAM_TS_RUNSC_CHECKER_REPOSITORY"],
                    "platform_manifest_digest": env["WORKSTREAM_TS_RUNSC_CHECKER_DIGEST"],
                    "platform_manifest_media_type": "application/vnd.docker.distribution.manifest.v2+json",
                    "platform_manifest_byte_count": 1,
                    "operating_system": "linux",
                    "architecture": "amd64",
                    "config_image_id": env["WORKSTREAM_TS_RUNSC_CHECKER_ID"],
                }
            ],
        }
        config_path = root / "service.json"
        config_path.write_text(
            json.dumps(service_config, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        config_path.chmod(0o400)
        service_log = (root / "service.stderr").open("w", encoding="utf-8")
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
                command = [
                    "docker",
                    "exec",
                    "--user",
                    f"{os.geteuid()}:{os.getegid()}",
                    env["WORKSTREAM_TS_RUNSC_CONTAINER"],
                    f"{inner}/bin/ld-linux-x86-64.so.2",
                    "--library-path",
                    f"{inner}/bin",
                    f"{inner}/bin/workstream-checker-service",
                    f"{inner}/service.json",
                ]
                service = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=service_log,
                    text=True,
                )
                _wait_for_socket(service_socket, service)
                adapter = UnixSocketExternalCheckerAdapter(
                    socket_path=service_socket, timeout_seconds=660.0
                )
                health = await adapter.health()
                assert (health.runtime, health.isolation_mode) == ("runsc", "gvisor")
                await reserve(h)
                executor = live_executor(
                    h,
                    selected_execution=ModelAwareExternalExecution(
                        execution=adapter, sessions=h.factory
                    ),
                )
                result = await executor.evaluate_post_submission(h.request)
            assert result.outcome == "completed", (result, len(creates), len(observations))
            assert len(result.execution.external_members) == 2
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
                receipt["originating_identity"]["requirement_id"] for receipt in receipts
            } == {AUTHOR_REQUIREMENT, REQUIREMENT}
            for receipt in receipts:
                assert receipt["plan_completed"] is True
                assert receipt["cleanup_confirmed"] is True
                assert (
                    receipt["engine_identity_digest"]
                    == env["WORKSTREAM_TS_RUNSC_ENGINE_DIGEST"]
                )
                execution = receipt["execution"]
                assert (
                    execution["platform_identity_digest"]
                    == env["WORKSTREAM_TS_RUNSC_PLATFORM_IDENTITY"]
                )
                assert (
                    execution["builder_image_digest"]
                    == env["WORKSTREAM_TS_RUNSC_BUILDER_ID"]
                )
                assert (
                    execution["trusted_launcher_digest"]
                    == env["WORKSTREAM_TS_RUNSC_LAUNCHER_DIGEST"]
                )
                assert execution["offline_cache_digest"] == env["WORKSTREAM_TS_RUNSC_CACHE_DIGEST"]
                assert execution["base_image_digests"] == [ALPINE_DIGEST]
                assert execution["build"]["outcome"] == "succeeded"
                assert execution["build"]["candidate_image_digest"].startswith("sha256:")
                outcomes = {item["slot_id"]: item["outcome"] for item in execution["steps"]}
                assert len(outcomes) == 17
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
                assert all(UUID(item.request_binding_id).version == 7 for item in effects)
                assert all(UUID(item.response_binding_id).version == 7 for item in effects)
                retained = tuple(await session.scalars(select(CheckerTrialEvidence)))
                assert len(retained) == 2
                assert {item.content_sha256 for item in retained} == {
                    external_checker_json_hash(receipt) for receipt in receipts
                }
            for directory in ("trial-relay", "trial-scratch", "trial-runtime"):
                assert list((root / directory).iterdir()) == []
            checkers = subprocess.check_output(
                [
                    "docker",
                    "exec",
                    env["WORKSTREAM_TS_RUNSC_CONTAINER"],
                    "docker",
                    "container",
                    "ls",
                    "-aq",
                    "--filter",
                    "label=workstream.external-checker=true",
                ],
                text=True,
            )
            assert checkers.strip() == ""
            inventory = subprocess.check_output(
                [
                    "docker",
                    "exec",
                    env["WORKSTREAM_TS_RUNSC_CONTAINER"],
                    "docker",
                    "container",
                    "ls",
                    "-aq",
                    "--filter",
                    "label=workstream.trial.deployment-owner=terminal-systems-runsc-qualification",
                ],
                text=True,
            )
            assert inventory.strip() == ""
            candidates = subprocess.check_output(
                [
                    "docker",
                    "exec",
                    env["WORKSTREAM_TS_RUNSC_CONTAINER"],
                    "docker",
                    "images",
                    "-q",
                    "--filter",
                    "reference=workstream-trial:*",
                ],
                text=True,
            )
            assert candidates.strip() == ""
        finally:
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
            if service is not None and service.returncode not in {0, -15, 143}:
                raise AssertionError((root / "service.stderr").read_text(encoding="utf-8"))
