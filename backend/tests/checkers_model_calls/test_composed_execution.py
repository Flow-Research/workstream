"""Real approval, AUTH, PostgreSQL and ART with an offline provider and image boundary."""

from app.adapters.checkers import checker_output_reservations

from contextlib import asynccontextmanager
import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func

from app.adapters.artifacts import checker_output_binding, checker_output_storage
from app.adapters.auth import checker_model_service_authorization
from app.adapters.checkers import (
    evaluation_coordinator,
    model_call_service,
    model_invocation_grants,
    model_profile_reader,
)
from app.adapters.checkers.model_execution import ModelAwareExternalExecution
from app.interfaces.checker_model_provider import (
    CheckerModelCreateFailure,
    CheckerModelCreateOutcome,
    CheckerModelCreateResult,
    CheckerModelObservation,
    CheckerModelProviderStatus,
    CheckerModelRecoveryOutcome,
    CheckerModelRecoveryResult,
    CheckerModelResponseReference,
    CheckerModelUsage,
)
from app.interfaces.checker_model_proxy import ModelProxyRequest
from app.interfaces.external_services import (
    ExternalServiceAdapterIdentity,
    ExternalServiceUnavailableError,
)
from app.interfaces.project_agents import CapabilityParameter, CheckSpecification
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.preparation import HARD_MAXIMUM_ARTIFACT_BYTES
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.model_usage.models import (
    ModelUsageEffect,
    ModelUsageBudgetAccount,
)
from app.adapters.checkers.model_proxy import CheckerModelProxy
from tests.checkers.external.support import post_registry_spec
from tests.checkers.execution.support import (
    ControlledSelectedExecution,
    live_executor,
    reserve,
    provision_post_submit_service,
)
from tests.checkers_model_calls.test_public_api import profile_spec
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_checker_materialization import _limits
from tests.projects.guide_compilation.helpers import valid_specification


def model_review_specification():
    """Declare model review explicitly before the real policy compiler binds it."""
    specification = valid_specification().model_dump(mode="json")
    specification.update(
        evaluation_method="model_evaluation",
        execution_mode="background",
        maximum_duration_seconds=120,
        stage_rationale="Content review runs after immutable submission creation.",
        runtime_dependencies=[
            {
                "dependency_id": "model_runtime",
                "kind": "model_service",
                "provisioning": "model_proxy",
                "purpose": "Evaluate submitted evidence through the budgeted model service.",
                "unavailable_code": "implementation_unavailable",
            }
        ],
        infrastructure_failures=[
            *specification["infrastructure_failures"],
            {
                "code": "implementation_unavailable",
                "condition": "The budgeted model service is unavailable.",
            },
        ],
    )
    return CheckSpecification.model_validate(specification)


def model_registry_spec():
    spec = post_registry_spec()
    document = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "model_profile_id": {"type": "string"},
            "model_profile_version": {"type": "integer"},
            "model_profile_digest": {"type": "string"},
        },
        "required": ["model_profile_id", "model_profile_version", "model_profile_digest"],
    }
    return spec.model_copy(
        update={
            "resources": spec.resources.model_copy(update={"deadline_ms": 120_000}),
            "configuration_schema": ExternalCheckerSchema(
                schema_id="acme.model_review.configuration",
                schema_version="v1",
                document=document,
                schema_sha256=external_checker_json_hash(document),
            ),
        }
    )


@pytest.mark.parametrize(
    ("storage_provider", "lose_first_image_reply", "concurrent_callback", "terminal_mode"),
    [
        pytest.param("local", False, False, None, id="completed"),
        pytest.param("local", True, False, None, id="retry-retains-paid-effect"),
        pytest.param("minio", True, False, None, id="minio-retry-retains-paid-effect"),
        pytest.param("local", False, True, None, id="concurrent-callback-single-charge"),
        pytest.param("local", False, False, "no_effect", id="operator-recovers-no-effect"),
        pytest.param("minio", False, False, "failed", id="operator-recovers-settled-failure"),
    ],
)
async def test_public_profile_to_private_model_call_and_completed_checker(
    tmp_path,
    isolated_database_env,
    admin_access,
    monkeypatch,
    storage_provider,
    lose_first_image_reply,
    concurrent_callback,
    terminal_mode,
):
    if storage_provider == "minio":
        from tests import test_s3_artifact_store

        monkeypatch.setattr(
            test_s3_artifact_store, "MINIO_BUCKET", os.environ["WORKSTREAM_TEST_MINIO_BUCKET"]
        )
    await admin_access.signed.grant(admin_access.admin, admin_access.target, role="operator")
    profiles = []

    async def publish(_factory, project_id, registry):
        spec = profile_spec(project_id).model_copy(
            update={
                "registry_entry_id": registry.registry_entry_id,
                "registry_entry_digest": registry.entry_digest,
            }
        )
        if terminal_mode is not None:
            # An authorized child is a second provider dispatch in the same
            # immutable envelope, even though it reuses logical call slot zero.
            spec = spec.model_copy(
                update={
                    "maximum_calls": 2,
                    "maximum_total_request_bytes": 20_000,
                    "maximum_total_response_bytes": 60_000,
                    "maximum_total_input_tokens": 200,
                    "maximum_total_output_tokens": 100,
                }
            )
        response = await admin_access.signed.client.post(
            f"/api/v1/operations/projects/{project_id}/model-profiles",
            headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
            json=spec.model_dump(mode="json"),
        )
        assert response.status_code == 201, response.text
        profile = response.json()
        profiles.append(profile)
        budget = await admin_access.signed.client.post(
            f"/api/v1/operations/projects/{project_id}/model-budget-configurations",
            headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
            json={
                "project_id": str(project_id),
                "configuration_version": 1,
                "authorized_total_nanodollars": 10_000_000_000,
                "externally_reconciled_prior_spend_nanodollars": 0,
                "lifetime_limit_nanodollars": 10_000_000_000,
            },
        )
        assert budget.status_code == 201, budget.text
        return tuple(
            CapabilityParameter(name=key, value=value)
            for key, value in {
                "model_profile_id": profile["profile_id"],
                "model_profile_version": profile["spec"]["profile_version"],
                "model_profile_digest": profile["profile_digest"],
            }.items()
        )

    async with material_fixture(
        tmp_path,
        isolated_database_env,
        provider=storage_provider,
        post_submit_registry_spec=model_registry_spec(),
        post_submit_binding_setup=publish,
        post_submit_specification=model_review_specification(),
        # This composed process holds ZIP material while also retaining model
        # evidence; the ordinary two-slot material-only fixture is insufficient.
        scratch_limits=_limits(
            aggregate_reserved_bytes=4 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=4,
            maximum_concurrency=4,
            total_deadline_seconds=120.0,
            reservation_ttl_seconds=150.0,
        ),
    ) as h:
        await provision_post_submit_service(h.factory, ServiceIdentity.ARTIFACT_CHECKER_OUTPUT)
        creates = []
        lost_replies = []
        recovered_references = []
        first_response_waiting = asyncio.Event()
        release_first_response = asyncio.Event()

        class Provider:
            async def create(self, request):
                creates.append(request.prompt)
                if terminal_mode == "no_effect" and len(creates) == 1:
                    return CheckerModelCreateResult(
                        CheckerModelCreateOutcome.NO_EFFECT,
                        failure=CheckerModelCreateFailure.INPUT_COUNT_UNAVAILABLE,
                    )
                failed = terminal_mode == "failed" and len(creates) == 1
                reference = CheckerModelResponseReference(f"resp_composed_{len(creates)}")
                return CheckerModelCreateResult(
                    CheckerModelCreateOutcome.ACCEPTED,
                    known_response=reference,
                    observation=CheckerModelObservation(
                        reference,
                        profiles[0]["spec"]["model_snapshot"],
                        CheckerModelProviderStatus.FAILED
                        if failed
                        else CheckerModelProviderStatus.COMPLETED,
                        None if failed else '{"verdict":"passed"}',
                        CheckerModelUsage(20, 5, 10, 2, 30),
                    ),
                )

            async def recover(self, reference):
                # A concurrent callback can attach after the first dispatch has
                # persisted its provider identity but before response ART is
                # terminal. It may retrieve that exact effect, never create it
                # again; completed replays still read retained ART directly.
                recovered_references.append(reference.provider_response_id)
                if concurrent_callback:
                    assert first_response_waiting.is_set()
                    assert not release_first_response.is_set()
                return CheckerModelRecoveryResult(
                    CheckerModelRecoveryOutcome.OBSERVED,
                    reference,
                    CheckerModelObservation(
                        reference,
                        profiles[0]["spec"]["model_snapshot"],
                        CheckerModelProviderStatus.COMPLETED,
                        '{"verdict":"passed"}',
                        CheckerModelUsage(20, 5, 10, 2, 30),
                    ),
                )

        @asynccontextmanager
        async def provider(_):
            yield Provider()

        outputs = checker_output_storage(
            reservations=checker_output_reservations,
            sessions=h.factory,
            store=h.store.wrapped,
            namespace=h.namespace,
            preparation=h.preparation,
            settings=h.settings,
        )
        original_store = outputs.store

        async def hold_first_response(request):
            if (
                concurrent_callback
                and request.selector.slot_key == "model_response"
                and not first_response_waiting.is_set()
            ):
                first_response_waiting.set()
                await asyncio.wait_for(release_first_response.wait(), timeout=30)
            return await original_store(request)

        monkeypatch.setattr(outputs, "store", hold_first_response)
        proxy = CheckerModelProxy(
            sessions=h.factory,
            authorization=checker_model_service_authorization,
            grants=model_invocation_grants,
            calls=model_call_service,
            profiles=model_profile_reader,
            outputs=outputs,
            bindings=lambda session: checker_output_binding(session, namespace=h.namespace, reservations=checker_output_reservations(session)),
            provider=provider,
        )

        class Image(ControlledSelectedExecution):
            identity = ExternalServiceAdapterIdentity("external_checker_execution", "unix_socket")

            def __init__(self):
                super().__init__()
                self.invocations = 0

            async def execute(self, request, grant, *, model_grant=None):
                self.invocations += 1
                assert model_grant is not None
                callback = ModelProxyRequest(
                    grant_id=model_grant.grant_id,
                    request_digest=request.request_digest,
                    call_index=0,
                    prompt="Evaluate the verified work",
                )
                if concurrent_callback:
                    first = asyncio.create_task(proxy.handle(callback))
                    try:
                        await asyncio.wait_for(first_response_waiting.wait(), timeout=30)
                        async with h.factory() as session:
                            pending = await session.scalar(select(ModelUsageEffect))
                            assert pending.provider_response_id == "resp_composed_1"
                            assert pending.state == "uncertain"
                            assert pending.response_binding_id is None
                        # The first callback cannot settle while the second retrieves
                        # the known response. A cached terminal replay cannot pass.
                        second_reply = await proxy.handle(callback)
                        assert recovered_references == ["resp_composed_1"]
                    finally:
                        release_first_response.set()
                        first_reply = await first
                    replies = [first_reply, second_reply]
                    assert [reply.outcome for reply in replies] == ["completed", "completed"]
                    assert replies[0].receipt_digest == replies[1].receipt_digest
                    reply = replies[0]
                else:
                    reply = await proxy.handle(callback)
                if terminal_mode is not None and self.invocations == 1:
                    assert reply.outcome == "unavailable", reply.outcome
                    assert reply.failure_code == (
                        "model_provider_no_effect"
                        if terminal_mode == "no_effect"
                        else "model_provider_failed"
                    )
                    raise ExternalServiceUnavailableError(self.identity)
                assert reply.outcome == "completed", reply.failure_code
                assert reply.output == '{"verdict":"passed"}'
                if lose_first_image_reply and self.invocations == 1:
                    lost_replies.append(reply.receipt_digest)
                    raise ExternalServiceUnavailableError(self.identity)
                return await super().execute(request, grant)

        await reserve(h)
        executor = live_executor(
            h,
            selected_execution=ModelAwareExternalExecution(
                execution=Image(),
                sessions=h.factory,
            ),
        )
        current_request = h.request
        result = await executor.evaluate_post_submission(current_request)
        if lose_first_image_reply or terminal_mode is not None:
            assert result.outcome == "infrastructure_failed"
            if lose_first_image_reply:
                assert len(lost_replies) == 1, result.infrastructure_failure_code
            if terminal_mode is not None:
                sources = await admin_access.signed.client.get(
                    f"/api/v1/operations/projects/{h.request.project_id}/checker-retry-sources",
                    headers=admin_access.target.headers,
                )
                assert sources.status_code == 200, sources.text
                candidates = sources.json()["items"][0]["model_recovery_candidates"]
                assert len(candidates) == 1
                candidate = candidates[0]
                parent = candidate.pop("parent_attempt_id")
                recovery_path = (
                    f"/api/v1/operations/projects/{h.request.project_id}/model-call-attempts/"
                    f"{parent}/recovery-children"
                )
                recovery_headers = admin_access.target.headers
                child = await admin_access.signed.client.post(
                    recovery_path,
                    headers=recovery_headers,
                    json=candidate,
                )
                assert child.status_code == 201, child.text
                replay = await admin_access.signed.client.post(
                    recovery_path,
                    headers=recovery_headers,
                    json=candidate,
                )
                assert replay.status_code == 201, replay.text
                assert replay.json()["attempt_id"] == child.json()["attempt_id"]
                assert len(creates) == 1  # Recovery authorization itself cannot dispatch.
            retry = await admin_access.signed.client.post(
                f"/api/v1/operations/projects/{h.request.project_id}/checker-runs/"
                f"{h.created.evaluation_attempt_id}/retry",
                headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
                json={
                    "reason": "Recover lost image response without repeating the paid model call"
                },
            )
            assert retry.status_code == 201, retry.text
            async with h.factory() as session, session.begin():
                reserved = await evaluation_coordinator(session).read_reserved_evaluation(
                    project_id=h.request.project_id,
                    task_id=h.request.task_id,
                    submission_id=h.request.submission_id,
                    request_id=UUID(retry.json()["successor"]["request_id"]),
                )
            current_request = reserved.request
            assert current_request.evaluation_generation == 2
            result = await executor.evaluate_post_submission(current_request)
        assert result.outcome == "completed"
        assert len(result.execution.external_members) == 1
        assert await executor.evaluate_post_submission(current_request) == result
        assert len(creates) == (2 if terminal_mode else 1)
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(ModelUsageEffect)) == (
                2 if terminal_mode else 1
            )
            attempt = await session.scalar(
                select(ModelUsageEffect).where(ModelUsageEffect.state == "completed")
            )
            account = await session.get(ModelUsageBudgetAccount, str(h.request.project_id))
            assert attempt.state == "completed"
            assert account.lifetime_reserved_nanodollars == 0
            assert account.lifetime_settled_nanodollars == (
                (15 * 11 + 5 * 2 + 10 * 29) * (2 if terminal_mode == "failed" else 1)
            )
            assert UUID(attempt.response_binding_id).version == 7
            assert UUID(attempt.request_binding_id).version == 7
