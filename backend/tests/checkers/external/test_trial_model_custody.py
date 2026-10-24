"""Real owner/ART/model custody driven through the production private transport.

The normalized receipt is synthesized at this Python driver boundary. Rust
relay/engine and project-image execution are qualified separately.
"""

from contextlib import asynccontextmanager
import asyncio
import hashlib
import json
from pathlib import Path
import struct
import time
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.adapters.artifacts import checker_output_binding, checker_output_storage
from app.adapters.auth import checker_model_service_authorization
from app.adapters.checkers import (
    checker_output_reservations,
    model_call_service,
    model_invocation_grants,
    model_profile_reader,
)
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
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.models import CheckerTrialEvidence
from app.modules.model_usage.api import (
    ProjectModelBudgetConfigurationSpec,
    ProjectModelProfileSpec,
)
from app.modules.model_usage.models import ModelUsageEffect
from tests.checkers.execution.support import (
    ControlledSelectedExecution,
    live_executor,
    provision_post_submit_service,
    reserve,
)
from tests.checkers.external.test_trial_evidence import _owner, _subject, _trial_fixture
from tests.checkers.external.test_trial_profiles import configuration, profile as trial_profile
from tests.checkers.external.test_trial_policy import trial_specification
from tests.checkers.external.test_revision_materialization import DiagnosticMaterialization
from tests.checkers_model_calls.test_composed_execution import model_review_specification
from tests.checkers_model_calls.test_public_api import profile_spec
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_checker_materialization import _limits


async def _exchange(path: Path, payload: dict) -> dict:
    async with asyncio.timeout(15):
        reader, writer = await asyncio.open_unix_connection(path)
        try:
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            writer.write(struct.pack(">I", len(body)) + body)
            await writer.drain()
            size = struct.unpack(">I", await reader.readexactly(4))[0]
            return json.loads(await reader.readexactly(size))
        finally:
            writer.close()
            await writer.wait_closed()


def _combined_fixture():
    trial_spec, _, projected, catalog_for = _trial_fixture()
    selected_profile = trial_profile()
    trial_values = {
        key: value
        for key, value in configuration(selected_profile, projected).items()
        if key.startswith("trial_")
    }
    properties = {key: {"const": value} for key, value in trial_values.items()}
    properties.update(
        {
            "model_profile_id": {"type": "string"},
            "model_profile_version": {"type": "integer"},
            "model_profile_digest": {"type": "string"},
        }
    )
    document = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(properties),
    }
    spec = trial_spec.model_copy(
        update={
            "resources": trial_spec.resources.model_copy(update={"deadline_ms": 120_000}),
            "configuration_schema": ExternalCheckerSchema(
                schema_id="trial_model_composition.configuration",
                schema_version="v1",
                document=document,
                schema_sha256=external_checker_json_hash(document),
            ),
        }
    )
    return spec, trial_values, selected_profile, projected, catalog_for


def _trial_model_specification() -> CheckSpecification:
    """Declare both nested execution and its bounded model assessment."""
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


def _receipt(request, grant, ticket, profile, plan):
    identity = request.identity.model_dump(mode="json")
    materials_digest = external_checker_json_hash(
        [item.model_dump(mode="json") for item in request.materials]
    )
    originating = {
        "request_digest": request.request_digest,
        "material_binding_digest": grant.binding_digest,
        "input_digest": request.input_sha256,
        "materials_digest": materials_digest,
        "project_id": str(identity["project_id"]),
        "task_id": str(identity["task_id"]),
        "assignment_id": str(identity["assignment_id"]),
        "submission_id": str(identity["submission_id"]),
        "submission_version": identity["submission_version"],
        "requirement_id": request.input["requirement_id"],
        "registry_entry_id": str(request.registry.registry_entry_id),
        "registry_entry_digest": request.registry.entry_digest,
        "checker_image_digest": request.registry.image_digest,
        "configuration_sha256": request.configuration_sha256,
        "evaluation_request_id": str(identity["evaluation_request_id"]),
        "evaluation_generation": identity["evaluation_generation"],
        "checker_run_id": str(identity["attempt_id"]),
        "attempt_id": str(identity["attempt_id"]),
        "result_id": str(identity["result_id"]),
        "worker_lease_id": str(identity["lease_id"]),
        "worker_lease_generation": identity["lease_generation"],
        "worker_lease_expires_at": identity["lease_expires_at"],
    }
    execution = {"observations": [{"slot_id": "generic_run:0", "outcome": "succeeded"}]}
    encoded_execution = json.dumps(
        execution, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return {
        "schema_version": "workstream.checker_trial_receipt.v1",
        "request_identity_digest": request.request_digest,
        "originating_identity": originating,
        "material_binding_digest": grant.binding_digest,
        "profile_id": request.configuration["trial_profile_id"],
        "profile_version": request.configuration["trial_profile_version"],
        "profile_digest": request.configuration["trial_profile_digest"],
        "trial_kind": ticket.subject.trial_kind,
        "engine_identity_digest": profile.engine_identity_digest,
        "plan_digest": external_checker_json_hash(plan),
        "observation_digest": external_checker_json_hash(execution),
        "observation_byte_count": len(encoded_execution),
        "slot_ids": ["generic_run:0"],
        "plan_started": True,
        "plan_completed": True,
        "cleanup_confirmed": True,
        "plan": plan,
        "execution": execution,
    }


async def test_trial_receipt_is_art_retained_before_controlled_model_spend(
    tmp_path,
    isolated_database_env,
    admin_access,
):
    """Driver boundary: production transport/owners, no fake custody ack or provider call."""
    await admin_access.signed.grant(admin_access.admin, admin_access.target, role="operator")
    spec, trial_values, selected_trial_profile, projected, catalog_for = _combined_fixture()
    profiles = []

    async def parameters(_factory, project_id, registry):
        selected = ProjectModelProfileSpec.model_validate(
            profile_spec(project_id)
            .model_copy(
                update={
                    "registry_entry_id": registry.registry_entry_id,
                    "registry_entry_digest": registry.entry_digest,
                    "allowed_tools": ("trial_receipt",),
                    "maximum_tool_calls": 1,
                    "maximum_tool_output_bytes": 1_048_576,
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
        profile = response.json()
        profiles.append(profile)
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
        values = trial_values | {
            "model_profile_id": profile["profile_id"],
            "model_profile_version": profile["spec"]["profile_version"],
            "model_profile_digest": profile["profile_digest"],
        }
        return tuple(CapabilityParameter(name=key, value=value) for key, value in values.items())

    async with material_fixture(
        tmp_path,
        isolated_database_env,
        provider="minio",
        post_submit_registry_spec=spec,
        post_submit_binding_setup=parameters,
        post_submit_specification=_trial_model_specification(),
        scratch_limits=_limits(
            aggregate_reserved_bytes=4 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=4,
            maximum_concurrency=4,
            total_deadline_seconds=120.0,
            reservation_ttl_seconds=150.0,
        ),
    ) as h:
        catalog = catalog_for(h.request)
        await provision_post_submit_service(h.factory, ServiceIdentity.ARTIFACT_CHECKER_OUTPUT)
        h.service = DiagnosticMaterialization(h.service)
        creates = []
        stages: list[tuple[str, float]] = []
        started = time.monotonic()

        def stage(name: str) -> None:
            stages.append((name, round(time.monotonic() - started, 3)))

        class Provider:
            async def create(self, model_request):
                creates.append(model_request)
                reference = CheckerModelResponseReference("resp_trial_model_composed")
                return CheckerModelCreateResult(
                    CheckerModelCreateOutcome.ACCEPTED,
                    known_response=reference,
                    observation=CheckerModelObservation(
                        reference,
                        profiles[0]["spec"]["model_snapshot"],
                        CheckerModelProviderStatus.COMPLETED,
                        '{"verdict":"passed"}',
                        CheckerModelUsage(20, 5, 10, 2, 30),
                    ),
                )

            async def recover(self, _reference):
                raise AssertionError("completed call must use retained response")

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
        model_proxy = CheckerModelProxy(
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

        trial_proxy = CheckerTrialProxy(
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
        socket_root = tmp_path / "private-proxy"
        socket_root.mkdir(mode=0o700)
        socket_path = socket_root / "proxy.sock"

        class Driver(ControlledSelectedExecution):
            async def execute(self, request, grant, *, model_grant=None):
                stage("driver_entered")
                assert model_grant is not None
                plan = {"steps": [{"slot_id": "generic_run:0"}]}
                subject = _subject(request, projected).model_copy(
                    update={"plan_sha256": external_checker_json_hash(plan)}
                )
                reserved = await _exchange(
                    socket_path,
                    {
                        "protocol_version": "workstream.trial_evidence_proxy.v1",
                        "operation": "reserve",
                        "external_request": request.model_dump(mode="json"),
                        "subject": subject.model_dump(mode="json"),
                    },
                )
                assert reserved["outcome"] == "completed", reserved
                stage("trial_reserved")
                ticket = reserved["ticket"]
                from app.modules.checkers.api.trial_evidence import TrialEvidenceTicket

                typed_ticket = TrialEvidenceTicket.model_validate_json(json.dumps(ticket))
                receipt = _receipt(request, grant, typed_ticket, selected_trial_profile, plan)
                canonical_receipt = json.dumps(
                    receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
                receipt_digest = "sha256:" + hashlib.sha256(canonical_receipt.encode()).hexdigest()
                published = await _exchange(
                    socket_path,
                    {
                        "protocol_version": "workstream.trial_evidence_proxy.v1",
                        "operation": "publish",
                        "external_request": request.model_dump(mode="json"),
                        "trial_evidence_id": ticket["trial_evidence_id"],
                        "project_id": str(request.identity.project_id),
                        "content_sha256": receipt_digest,
                        "byte_count": len(canonical_receipt.encode()),
                        "canonical_receipt_utf8": canonical_receipt,
                    },
                )
                assert published["outcome"] == "completed", published
                stage("trial_published")
                model = await _exchange(
                    socket_path,
                    {
                        "protocol_version": "workstream.model_session.v2",
                        "grant_id": model_grant.grant_id,
                        "request_digest": request.request_digest,
                        "call_index": 0,
                        "prompt": "Assess only the retained trial receipt",
                        "resolved_receipts": [
                            {
                                "receipt_sha256": receipt_digest,
                                "canonical_receipt_utf8": canonical_receipt,
                            }
                        ],
                    },
                )
                assert model["outcome"] == "completed", model
                assert model["output"] == '{"verdict":"passed"}'
                stage("model_completed")
                replay = await _exchange(
                    socket_path,
                    {
                        "protocol_version": "workstream.trial_evidence_proxy.v1",
                        "operation": "reserve",
                        "external_request": request.model_dump(mode="json"),
                        "subject": subject.model_dump(mode="json"),
                    },
                )
                assert replay["retained_receipt"]["canonical_receipt_utf8"] == canonical_receipt
                stage("trial_recovered")
                return await super().execute(request, grant)

        await reserve(h)
        async with ModelProxyTransport(
            socket_path=socket_path,
            handler=model_proxy.handle,
            trial_handler=trial_proxy.handle,
            read_timeout_seconds=30.0,
            write_timeout_seconds=30.0,
        ):
            executor = live_executor(
                h,
                selected_execution=ModelAwareExternalExecution(
                    execution=Driver(), sessions=h.factory
                ),
            )
            result = await executor.evaluate_post_submission(h.request)
            stage("first_evaluation_returned")
            replayed_result = (
                await executor.evaluate_post_submission(h.request)
                if result.outcome == "completed"
                else None
            )
            stage("replay_evaluation_returned")
        assert result.outcome == "completed", json.dumps(
            {"result": result.model_dump(mode="json"), "stages": stages},
            sort_keys=True,
        )
        assert replayed_result == result
        assert len(creates) == 1
        provider_prompt = json.loads(creates[0].prompt)
        assert provider_prompt["schema_version"] == "workstream.model_prompt_with_receipts.v1"
        assert provider_prompt["prompt"] == "Assess only the retained trial receipt"
        assert len(provider_prompt["trusted_receipts"]) == 1
        retained = provider_prompt["trusted_receipts"][0]
        retained_bytes = json.dumps(
            retained["receipt"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        assert retained["receipt_sha256"] == (
            "sha256:" + hashlib.sha256(retained_bytes).hexdigest()
        )
        assert retained["receipt"]["cleanup_confirmed"] is True
        expected_request_sha256 = external_checker_json_hash(
            {
                "schema_version": "workstream.model_session_call.v2",
                "call_index": 0,
                "prompt": "Assess only the retained trial receipt",
                "resolved_receipts": [retained],
            }
        )
        async with h.factory() as session:
            effect = await session.scalar(select(ModelUsageEffect))
            assert effect is not None
            assert effect.request_sha256 == expected_request_sha256
            assert UUID(effect.request_binding_id).version == 7
            assert UUID(effect.response_binding_id).version == 7
            assert await session.scalar(select(func.count()).select_from(ModelUsageEffect)) == 1
            evidence = await session.scalar(select(CheckerTrialEvidence))
            assert evidence is not None
            assert evidence.content_sha256 == retained["receipt_sha256"]
