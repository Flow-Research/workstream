"""Focused prepared-capability proofs for contributor bundle preparation."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationService,
)
from app.modules.authorization.runtime import (
    MatchedAuthorityKind,
    PreparedAuthorizationInput,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)
from app.modules.authorization.submission_preparation import (
    SubmissionBundlePreparationPreflightResourceContext,
    SubmissionBundlePreparationResourceContext,
)
from tests.test_authorization import _PreparedTestSession, _runtime_context, _runtime_service


def _request_values(context, project_id, task_id, assignment_id):
    return {
        "scope_project_id": str(project_id),
        "actor_profile_id": str(context.actor_profile_id),
        "identity_link_id": str(context.identity_link_id),
        "task_id": str(task_id),
        "assignment_id": str(assignment_id),
        "predecessor_submission_id": None,
    }


def _final_values(request_values):
    values = {
        "predecessor_submission_version": None,
        "guide_version": "v1",
        "source_snapshot_sha256": "sha256:" + "1" * 64,
        "effective_policy_sha256": "sha256:" + "2" * 64,
        "pre_submit_policy_sha256": "sha256:" + "3" * 64,
        "effective_plan_sha256": "sha256:" + "4" * 64,
        "semantic_manifest_sha256": "sha256:" + "5" * 64,
        "archive_sha256": "sha256:" + "6" * 64,
        "archive_byte_count": 42,
        "media_type": "application/zip",
        "storage_scheme": "s3",
        "operation_identity": "sha256:" + "7" * 64,
        "replay_durable_intent_id": None,
    }
    for field in (
        "pre_submit_evidence_set_id",
        "prepared_generation_id",
        "guide_id",
        "source_snapshot_id",
        "effective_policy_id",
        "pre_submit_policy_id",
        "semantic_manifest_id",
    ):
        values[field] = str(uuid4())
    return {**request_values, **values}


def _resource(values):
    typed = dict(values)
    for field in (
        "scope_project_id",
        "actor_profile_id",
        "identity_link_id",
        "task_id",
        "assignment_id",
        "pre_submit_evidence_set_id",
        "prepared_generation_id",
        "guide_id",
        "source_snapshot_id",
        "effective_policy_id",
        "pre_submit_policy_id",
        "semantic_manifest_id",
    ):
        typed[field] = UUID(typed[field])
    return SubmissionBundlePreparationResourceContext(
        resource_type="submission_bundle_preparation",
        resource_id=typed["prepared_generation_id"],
        **typed,
    )


@pytest.mark.asyncio
async def test_submission_preparation_binds_exact_facts_and_rejects_replay() -> None:
    context, session = _runtime_context(), _PreparedTestSession()
    project_id, task_id, assignment_id = uuid4(), uuid4(), uuid4()

    class Facts:
        async def lock_request_actor(self, identity_link_id, actor_profile_id):
            return (
                SimpleNamespace(
                    id=str(identity_link_id),
                    actor_profile_id=str(actor_profile_id),
                    status="active",
                ),
                SimpleNamespace(id=str(actor_profile_id), actor_kind="human", status="active"),
            )

        async def find_active_project_role(self, **values):
            return SimpleNamespace(id=uuid4(), status="active")

    facts = Facts()
    authorization, evidence = _runtime_service(context, session=session, admin_repository=facts)
    prepared = PreparedAuthorizationService(session, context, authorization, facts)
    values = _request_values(context, project_id, task_id, assignment_id)
    caller = PreparedAuthorizationInput(idempotency_key=uuid4(), request_value=values)
    scope = PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=project_id)
    await prepared.preflight(
        ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE,
        caller,
        scope,
        SubmissionBundlePreparationPreflightResourceContext(
            resource_type="submission_bundle_preparation_preflight",
            resource_id=assignment_id,
            **{key: UUID(value) if value is not None else None for key, value in values.items()},
        ),
    )
    final = _final_values(values)
    final_caller = PreparedAuthorizationInput(
        idempotency_key=caller.idempotency_key, request_value=final
    )
    resource = _resource(final)
    handle = await prepared.prepare(
        ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE, final_caller, scope
    )
    decision = await prepared.consume(
        handle, ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE, final_caller, resource
    )
    assert decision.allowed is True
    assert decision.matched_authority_kind is MatchedAuthorityKind.PROJECT_ROLE_GRANT
    assert len(evidence.events) == 1
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(
            handle, ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE, final_caller, resource
        )
