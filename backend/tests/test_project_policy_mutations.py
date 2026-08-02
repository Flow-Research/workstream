"""Focused proof for the sole review/revision policy mutation path."""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.hashing import canonical_json_hash
from app.main import create_app
from app.modules.projects import policy_mutation_router as router_module
from app.modules.projects.models import PolicyMutationIdempotencyRecord
from app.modules.projects.policy_mutation_replay_repository import (
    PolicyMutationReplayRepository,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.audit.schemas import ActorReferenceKind
from app.modules.authorization.prepared import (
    _PreparedAuthorizationBinding,
    _policy_mutation_binding_matches,
)
from app.modules.authorization.runtime import (
    MatchedAuthorityKind,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectReviewPolicyMutationResourceContext,
)
from app.modules.projects.policy_mutation_service import (
    NO_CURRENT_POLICY_ETAG,
    PolicyMutationConflict,
    ProjectPolicyMutationService,
    policy_selector_etag,
)
from app.modules.projects.policy_mutation_router import require_policy_mutation_key
from app.modules.projects.schemas import ReviewPolicyInput, RevisionPolicyInput
from app.modules.projects.service import ProjectNotFound


def _review_payload() -> ReviewPolicyInput:
    return ReviewPolicyInput(
        review_preference_window_seconds=3600,
        review_lease_duration_seconds=7200,
        allowed_decisions=["accept", "needs_revision", "reject"],
    )


def _revision_payload() -> RevisionPolicyInput:
    return RevisionPolicyInput(
        max_revision_rounds=3,
        revision_deadline_hours=48,
        allowed_resubmission_states=["needs_revision"],
    )


class _Repository:
    def __init__(self, project_id, guide_id) -> None:
        self.guide = SimpleNamespace(
            id=str(guide_id),
            project_id=str(project_id),
            version="v1",
            status="draft",
            selected_review_policy_id=None,
            selected_review_policy_generation=None,
            selected_review_policy_hash=None,
            selected_revision_policy_id=None,
            selected_revision_policy_generation=None,
            selected_revision_policy_hash=None,
        )
        self.review = None
        self.revision = None

    async def lock_project_guide(self, _guide_id):
        return self.guide

    async def get_guide(self, _guide_id):
        return self.guide

    async def lock_review_policy(self, _project_id, _guide_version):
        return self.review

    async def lock_revision_policy(self, _project_id, _guide_version):
        return self.revision

    async def add_review_policy_version(self, policy, guide):
        policy.created_at = datetime.now(UTC)
        self.review = policy
        guide.selected_review_policy_id = policy.id
        guide.selected_review_policy_generation = policy.policy_generation
        guide.selected_review_policy_hash = policy.policy_hash
        return policy

    async def add_revision_policy_version(self, policy, guide):
        policy.created_at = datetime.now(UTC)
        self.revision = policy
        guide.selected_revision_policy_id = policy.id
        guide.selected_revision_policy_generation = policy.policy_generation
        guide.selected_revision_policy_hash = policy.policy_hash
        return policy


class _Replay:
    def __init__(self) -> None:
        self.records = {}
        self.completed = 0

    async def find(self, actor_profile_id, action_id, idempotency_key):
        return self.records.get((actor_profile_id, action_id, idempotency_key))

    async def reserve(self, **facts):
        record = SimpleNamespace(**facts, status="pending", response_json=None)
        self.records[(facts["actor_profile_id"], facts["action_id"], facts["idempotency_key"])] = (
            record
        )
        return "claimed", record

    async def complete(self, record, *, response_json):
        record.status = "committed"
        record.response_json = response_json
        self.completed += 1


class _Prepared:
    def __init__(self, project_id, grant_id) -> None:
        self.project_id = project_id
        self.grant_id = grant_id
        self.prepared = []
        self.consumed = []

    async def prepare(self, action, caller, scope):
        self.prepared.append((action, caller, scope))
        return object()

    async def consume(self, handle, action, caller, resource):
        self.consumed.append((handle, action, caller, resource))
        return SimpleNamespace(
            matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
            matched_grant_id=self.grant_id,
            matched_scope_project_id=self.project_id,
            resource_context_digest=canonical_json_hash(resource.model_dump(mode="json")),
            decision_id=uuid4(),
        )


def _subject():
    project_id, guide_id, actor_id, link_id, grant_id = (uuid4() for _ in range(5))
    resolved = SimpleNamespace(
        profile=SimpleNamespace(id=str(actor_id)),
        identity_link=SimpleNamespace(id=str(link_id)),
    )
    repository = _Repository(project_id, guide_id)
    replay = _Replay()
    prepared = _Prepared(project_id, grant_id)
    service = ProjectPolicyMutationService(SimpleNamespace())
    service._projects = repository  # type: ignore[assignment]
    service._replay = replay  # type: ignore[assignment]
    return service, resolved, prepared, replay, repository, project_id, guide_id


def test_policy_mutation_routes_declare_only_their_exact_primary_actions() -> None:
    schema = create_app().openapi()
    routes = {
        "/api/v1/projects/{project_id}/guides/{guide_id}/review-policy": (
            "project.review_policy.update"
        ),
        "/api/v1/projects/{project_id}/guides/{guide_id}/revision-policy": (
            "project.revision_policy.update"
        ),
    }
    for path, action in routes.items():
        operation = schema["paths"][path]["put"]
        assert operation["x-workstream-action-id"] == action
        assert set(schema["paths"][path]) == {"put"}
    key = uuid4()
    assert require_policy_mutation_key(str(key)) == key


def test_policy_prepared_binding_rejects_every_changed_lineage_fact() -> None:
    project_id, guide_id, policy_id, operation_id, predecessor_id = (uuid4() for _ in range(5))
    request_digest = "sha256:" + "1" * 64
    policy_digest_value = "sha256:" + "2" * 64
    predecessor_digest = "sha256:" + "3" * 64
    binding = _PreparedAuthorizationBinding(
        action_id=ActionId.PROJECT_REVIEW_POLICY_UPDATE,
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=uuid4(),
        scope=PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=project_id,
        ),
        idempotency_key=uuid4(),
        request_digest="sha256:" + "4" * 64,
        policy_mutation_project_id=project_id,
        policy_mutation_guide_id=guide_id,
        policy_mutation_policy_id=policy_id,
        policy_mutation_operation_id=operation_id,
        policy_mutation_request_digest=request_digest,
        policy_mutation_policy_digest=policy_digest_value,
        policy_mutation_generation=2,
        policy_mutation_predecessor_id=predecessor_id,
        policy_mutation_predecessor_generation=1,
        policy_mutation_predecessor_digest=predecessor_digest,
        policy_mutation_guide_status="draft",
    )
    resource = ProjectReviewPolicyMutationResourceContext(
        resource_type="project_review_policy_mutation",
        resource_id=policy_id,
        operation_id=operation_id,
        request_digest=request_digest,
        scope_project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        guide_status="draft",
        review_policy_id=policy_id,
        policy_generation=2,
        policy_digest=policy_digest_value,
        predecessor_policy_id=predecessor_id,
        predecessor_policy_generation=1,
        current_policy_digest=predecessor_digest,
    )
    assert _policy_mutation_binding_matches(binding, resource)
    assert not _policy_mutation_binding_matches(
        replace(binding, policy_mutation_generation=3), resource
    )
    assert not _policy_mutation_binding_matches(
        replace(binding, policy_mutation_predecessor_id=uuid4()), resource
    )
    assert not _policy_mutation_binding_matches(
        replace(binding, policy_mutation_predecessor_digest="sha256:" + "5" * 64),
        resource,
    )
    assert not _policy_mutation_binding_matches(
        replace(binding, policy_mutation_guide_status="active"), resource
    )


@pytest.mark.asyncio
async def test_separate_policy_routes_append_in_either_order_with_exact_authority() -> None:
    service, resolved, prepared, replay, repository, project_id, guide_id = _subject()
    revision = await service.replace_revision_policy(
        resolved,
        prepared,
        uuid4(),
        NO_CURRENT_POLICY_ETAG,
        project_id,
        guide_id,
        _revision_payload(),
    )
    review = await service.replace_review_policy(
        resolved,
        prepared,
        uuid4(),
        NO_CURRENT_POLICY_ETAG,
        project_id,
        guide_id,
        _review_payload(),
    )

    assert revision.response.policy_generation == review.response.policy_generation == 1
    assert repository.guide.selected_review_policy_id == review.response.id
    assert repository.guide.selected_revision_policy_id == revision.response.id
    assert [call[0] for call in prepared.prepared] == [
        ActionId.PROJECT_REVISION_POLICY_UPDATE,
        ActionId.PROJECT_REVIEW_POLICY_UPDATE,
    ]
    assert all(call[3].guide_status == "draft" for call in prepared.consumed)
    assert replay.completed == 2


@pytest.mark.asyncio
async def test_replay_claim_precedes_prepared_authority() -> None:
    service, resolved, prepared, replay, _repository, project_id, guide_id = _subject()
    key = uuid4()
    original_prepare = prepared.prepare

    async def assert_claimed_before_prepare(*args, **kwargs):
        record = replay.records[
            (resolved.profile.id, ActionId.PROJECT_REVIEW_POLICY_UPDATE.value, key)
        ]
        assert record.status == "pending"
        return await original_prepare(*args, **kwargs)

    prepared.prepare = assert_claimed_before_prepare
    await service.replace_review_policy(
        resolved,
        prepared,
        key,
        NO_CURRENT_POLICY_ETAG,
        project_id,
        guide_id,
        _review_payload(),
    )


@pytest.mark.asyncio
async def test_policy_replacement_binds_predecessor_and_exact_etag() -> None:
    service, resolved, prepared, _replay, repository, project_id, guide_id = _subject()
    first = await service.replace_review_policy(
        resolved,
        prepared,
        uuid4(),
        NO_CURRENT_POLICY_ETAG,
        project_id,
        guide_id,
        _review_payload(),
    )
    second = await service.replace_review_policy(
        resolved,
        prepared,
        uuid4(),
        policy_selector_etag(
            first.response.id,
            first.response.policy_generation,
            first.response.policy_hash,
        ),
        project_id,
        guide_id,
        _review_payload().model_copy(update={"review_lease_duration_seconds": 9000}),
    )

    assert second.response.policy_generation == 2
    assert second.response.supersedes_policy_id == first.response.id
    resource = prepared.consumed[-1][3]
    assert str(resource.predecessor_policy_id) == first.response.id
    assert resource.current_policy_digest == first.response.policy_hash
    assert repository.review.predecessor_policy_hash == first.response.policy_hash


@pytest.mark.asyncio
async def test_stale_or_unquoted_policy_precondition_fails_without_consumption() -> None:
    service, resolved, prepared, replay, _repository, project_id, guide_id = _subject()
    with pytest.raises(PolicyMutationConflict, match="policy_precondition_invalid"):
        await service.replace_review_policy(
            resolved,
            prepared,
            uuid4(),
            "sha256:" + "0" * 64,
            project_id,
            guide_id,
            _review_payload(),
        )
    for invalid_generation in ("0", "not-an-integer"):
        with pytest.raises(PolicyMutationConflict, match="policy_precondition_invalid"):
            await service.replace_review_policy(
                resolved,
                prepared,
                uuid4(),
                f'"{uuid4()}.{invalid_generation}.{"0" * 64}"',
                project_id,
                guide_id,
                _review_payload(),
            )
    assert not prepared.prepared
    assert replay.completed == 0

    with pytest.raises(PolicyMutationConflict, match="policy_precondition_failed"):
        await service.replace_review_policy(
            resolved,
            prepared,
            uuid4(),
            policy_selector_etag(str(uuid4()), 1, "sha256:" + "0" * 64),
            project_id,
            guide_id,
            _review_payload(),
        )
    assert not prepared.prepared
    assert not prepared.consumed
    assert replay.completed == 0


@pytest.mark.asyncio
async def test_exact_committed_replay_returns_without_new_prep_or_write() -> None:
    service, resolved, prepared, replay, repository, project_id, guide_id = _subject()
    key = uuid4()
    first = await service.replace_revision_policy(
        resolved,
        prepared,
        key,
        NO_CURRENT_POLICY_ETAG,
        project_id,
        guide_id,
        _revision_payload(),
    )
    prepared.prepared.clear()
    prepared.consumed.clear()
    resolved.identity_link.id = str(uuid4())
    second = await service.replace_revision_policy(
        resolved,
        prepared,
        key,
        NO_CURRENT_POLICY_ETAG,
        project_id,
        guide_id,
        _revision_payload(),
    )

    assert second.replayed is True
    assert second.response == first.response
    assert not prepared.prepared and not prepared.consumed
    assert repository.revision.id == first.response.id
    assert replay.completed == 1


@pytest.mark.asyncio
async def test_replay_repository_owns_claim_classification_and_completion() -> None:
    actor_id, link_id, project_id, guide_id = (str(uuid4()) for _ in range(4))
    key, operation_id, record_id = uuid4(), uuid4(), uuid4()
    digest = "sha256:" + "1" * 64
    resource_digest = "sha256:" + "2" * 64

    class Session:
        scalar_values = []
        record = None

        async def scalar(self, _statement):
            return self.scalar_values.pop(0)

        async def get(self, model, selected_id):
            assert model is PolicyMutationIdempotencyRecord
            assert selected_id == record_id
            return self.record

    session = Session()
    repository = PolicyMutationReplayRepository(session)  # type: ignore[arg-type]
    found = SimpleNamespace(id=record_id)
    session.scalar_values = [found]
    assert (
        await repository.find(actor_id, ActionId.PROJECT_REVIEW_POLICY_UPDATE.value, key) is found
    )

    record = SimpleNamespace(
        id=record_id,
        identity_link_id=link_id,
        project_id=project_id,
        guide_id=guide_id,
        request_digest=digest,
        policy_hash="sha256:" + "3" * 64,
        status="pending",
    )
    session.record = record
    session.scalar_values = [record_id]
    disposition, selected = await repository.reserve(
        actor_profile_id=actor_id,
        identity_link_id=link_id,
        action_id=ActionId.PROJECT_REVIEW_POLICY_UPDATE.value,
        idempotency_key=key,
        request_digest=digest,
        policy_hash="sha256:" + "3" * 64,
        resource_context_digest=resource_digest,
        operation_id=operation_id,
        project_id=project_id,
        guide_id=guide_id,
        policy_id=str(uuid4()),
        policy_generation=1,
    )
    assert disposition == "pending" and selected is record

    record.status = "committed"
    session.scalar_values = [record_id]
    disposition, _ = await repository.reserve(
        actor_profile_id=actor_id,
        identity_link_id=link_id,
        action_id=ActionId.PROJECT_REVIEW_POLICY_UPDATE.value,
        idempotency_key=key,
        request_digest=digest,
        policy_hash="sha256:" + "3" * 64,
        resource_context_digest=resource_digest,
        operation_id=operation_id,
        project_id=project_id,
        guide_id=guide_id,
        policy_id=str(uuid4()),
        policy_generation=1,
    )
    assert disposition == "replayed"

    session.scalar_values = [record_id]
    await repository.complete(record, response_json={"id": "response"})


@pytest.mark.asyncio
async def test_policy_router_dependencies_errors_and_transaction_outcomes(monkeypatch) -> None:
    key = uuid4()
    with pytest.raises(HTTPException):
        require_policy_mutation_key("not-a-uuid")

    resolved = object()

    async def resolve(*_args):
        return resolved

    monkeypatch.setattr(router_module, "resolve_authorization_actor", resolve)
    assert (
        await router_module.policy_authorization_actor(key, object(), object(), object(), object())
        is resolved
    )

    prepared = object()

    class PreparedContext:
        async def __aenter__(self):
            return prepared

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(
        router_module,
        "prepared_authorization_service",
        lambda *_args: PreparedContext(),
    )
    dependency = router_module.get_policy_prepared_authorization_service(
        object(), resolved, object()
    )
    assert await anext(dependency) is prepared
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)
    assert await router_module.policy_authorization(key, resolved, prepared) == (
        key,
        resolved,
        prepared,
    )

    pending = router_module._error(PolicyMutationConflict("idempotency_pending"))
    assert pending.status_code == 409 and pending.retryable is True
    missing = router_module._error(ProjectNotFound("project not found"))
    assert missing.status_code == 404

    class Session:
        committed = rolled_back = 0

        async def commit(self):
            self.committed += 1

        async def rollback(self):
            self.rolled_back += 1

    session = Session()
    response = object()
    assert (
        await router_module._finish(session, SimpleNamespace(response=response, replayed=False))
        is response
    )
    assert (
        await router_module._finish(session, SimpleNamespace(response=response, replayed=True))
        is response
    )
    assert (session.committed, session.rolled_back) == (1, 1)

    review_response = object()
    revision_response = object()

    class Service:
        def __init__(self, selected_session):
            assert selected_session is session

        async def replace_review_policy(self, *_args):
            return SimpleNamespace(response=review_response, replayed=False)

        async def replace_revision_policy(self, *_args):
            return SimpleNamespace(response=revision_response, replayed=False)

    monkeypatch.setattr(router_module, "ProjectPolicyMutationService", Service)
    authorization = (key, resolved, prepared)
    assert (
        await router_module.replace_review_policy(
            uuid4(),
            uuid4(),
            _review_payload(),
            NO_CURRENT_POLICY_ETAG,
            authorization,
            session,
        )
        is review_response
    )
    assert (
        await router_module.replace_revision_policy(
            uuid4(),
            uuid4(),
            _revision_payload(),
            NO_CURRENT_POLICY_ETAG,
            authorization,
            session,
        )
        is revision_response
    )

    class ErrorService(Service):
        async def replace_review_policy(self, *_args):
            raise PolicyMutationConflict("policy_precondition_failed")

        async def replace_revision_policy(self, *_args):
            raise PolicyMutationConflict("policy_precondition_failed")

    monkeypatch.setattr(router_module, "ProjectPolicyMutationService", ErrorService)
    with pytest.raises(HTTPException):
        await router_module.replace_review_policy(
            uuid4(),
            uuid4(),
            _review_payload(),
            NO_CURRENT_POLICY_ETAG,
            authorization,
            session,
        )
    with pytest.raises(HTTPException):
        await router_module.replace_revision_policy(
            uuid4(),
            uuid4(),
            _revision_payload(),
            NO_CURRENT_POLICY_ETAG,
            authorization,
            session,
        )


@pytest.mark.asyncio
async def test_policy_service_denies_stale_guide_and_replay_mismatch() -> None:
    service, resolved, prepared, replay, repository, project_id, guide_id = _subject()
    repository.guide.status = "active"
    with pytest.raises(Exception, match="only draft guides"):
        await service.replace_revision_policy(
            resolved,
            prepared,
            uuid4(),
            NO_CURRENT_POLICY_ETAG,
            project_id,
            guide_id,
            _revision_payload(),
        )
    assert not prepared.consumed

    key = uuid4()
    replay.records[(resolved.profile.id, ActionId.PROJECT_REVISION_POLICY_UPDATE.value, key)] = (
        SimpleNamespace(
            identity_link_id=str(uuid4()),
            project_id=str(project_id),
            guide_id=str(guide_id),
            request_digest="sha256:" + "0" * 64,
            status="committed",
            response_json={},
        )
    )
    with pytest.raises(PolicyMutationConflict, match="idempotency_mismatch"):
        await service.replace_revision_policy(
            resolved,
            prepared,
            key,
            NO_CURRENT_POLICY_ETAG,
            project_id,
            guide_id,
            _revision_payload(),
        )
