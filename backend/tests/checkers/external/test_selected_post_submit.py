"""Selected project POST images consume actual ART custody as evidence only."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from app.adapters.checkers import selected_submission_evaluation_content
from app.core.hashing import canonical_json_hash
from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionResponse,
    ExternalCheckerIsolationReceipt,
    ExternalCheckerMaterialGrant,
)
from app.modules.checkers.api.external import (
    POST_SUBMIT_INPUT_SCHEMA_ID,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
    ExternalCheckerSchema,
    external_checker_json_hash,
    make_external_checker_execution_result,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerBinding,
    LockedExternalPostSubmitPolicy,
)
from app.modules.checkers.api.evaluation_contract import (
    validate_execution_request,
    validate_execution_result,
    validate_stored_execution_request,
    validate_stored_execution_result,
)
from app.modules.checkers.api.execution import EvaluationReservation, ExecutionLease
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.artifacts.preparation import ArtifactScratchIntegrityError
from app.modules.checkers.selected_post_submit_execution import (
    SelectedPostSubmitProcessor,
)
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmitExecutionFacts,
    SelectedPostSubmitLockedContext,
    make_selected_post_submit_request,
    make_selected_post_submit_result,
)
from app.core.identifiers import new_record_id
from tests.checkers.external.support import (
    SHA,
    execution_identity,
    execution_material,
    post_registry_spec,
    registry_entry,
)
from tests.checkers.execution.support import live_executor, reserve
from tests.post_submit_materialization_helpers import material_fixture


def _policy() -> LockedExternalPostSubmitPolicy:
    values = registry_entry("post_submit").model_dump()
    document = {"type": "object"}
    values["input_schema"] = ExternalCheckerSchema(
        schema_id=POST_SUBMIT_INPUT_SCHEMA_ID,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    spec = {
        key: value
        for key, value in values.items()
        if key
        not in {
            "registry_entry_id",
            "entry_digest",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        }
    }
    spec["input_schema"] = values["input_schema"].model_dump(mode="json")
    values["entry_digest"] = external_checker_json_hash(spec)
    binding = LockedExternalCheckerBinding(
        requirement_id="project.post_evidence",
        stage="post_submit",
        registry=ExternalCheckerRegistryEntry.model_validate(values),
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
    )
    body = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [binding.model_dump(mode="json")],
    }
    return LockedExternalPostSubmitPolicy(
        entries=(binding,),
        policy_sha256=canonical_json_hash(body),
    )


def _post_spec() -> ExternalCheckerRegistrySpec:
    """Use the exact selected POST schema with the shared immutable registry facts."""
    return post_registry_spec()


def _request(identity, policy):
    context = SelectedPostSubmitLockedContext(
        guide_version="guide-v1",
        source_id=new_record_id(),
        source_hash=SHA,
        effective_policy_id=new_record_id(),
        effective_policy_hash=SHA,
        pre_policy_id=new_record_id(),
        pre_policy_hash=SHA,
        post_policy_id=new_record_id(),
        post_policy_version="guide-v1",
        post_policy_hash=policy.policy_sha256,
        review_policy_id=new_record_id(),
        review_generation=1,
        review_hash=SHA,
        revision_policy_id=new_record_id(),
        revision_generation=1,
        revision_hash=SHA,
    )
    return make_selected_post_submit_request(
        project_id=identity.project_id,
        expected_context=context,
        policy=policy,
        evaluation_request_id=identity.evaluation_request_id,
        evaluation_generation=identity.evaluation_generation,
        task_id=identity.task_id,
        assignment_id=identity.assignment_id,
        submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        content_id=new_record_id(),
        binding_id=new_record_id(),
        content_sha256=SHA,
        byte_count=42,
    )


class _MaterialView:
    def __init__(self, material, *, events=None, cleanup_failure=False) -> None:
        self.external_checker_material = material
        self.entries = (
            SubmissionMaterialEntry("src/main.py", "file", 4, SHA, False),
        )
        self.requests = []
        self.events = events
        self.cleanup_failure = cleanup_failure

    @contextmanager
    def external_checker_grant(self, request):
        self.requests.append(request)
        if self.events is not None:
            self.events.append("grant_entered")
        try:
            yield ExternalCheckerMaterialGrant(
                grant_id="extract_" + "a" * 32,
                binding_digest="sha256:" + "b" * 64,
            )
        finally:
            if self.events is not None:
                self.events.append("grant_closed")
            if self.cleanup_failure:
                raise ArtifactScratchIntegrityError("controlled grant cleanup failure")


class _Execution:
    def __init__(self, *, outcome="completed", verdict="passed", events=None) -> None:
        self.outcome, self.verdict = outcome, verdict
        self.requests = []
        self.events = events

    async def execute(self, request, _grant):
        assert type(_grant) is ExternalCheckerMaterialGrant
        self.requests.append(request)
        if self.events is not None:
            self.events.append("execute")
        infrastructure = self.outcome == "infrastructure_failed"
        findings = () if self.verdict == "passed" or infrastructure else ({
            "check_id": "post_evidence",
            "code": "post_evidence_failed",
            "level": "error",
            "message": "Post evidence failed.",
        },)
        result = make_external_checker_execution_result(
            request_digest=request.request_digest,
            registry_entry_id=request.registry.registry_entry_id,
            registry_entry_digest=request.registry.entry_digest,
            phase="post_submit",
            outcome=self.outcome,
            verdict=None if infrastructure else self.verdict,
            findings=findings,
            infrastructure_failure_code="deadline_exceeded" if infrastructure else None,
        )
        response = ExternalCheckerExecutionResponse(
            result=result,
            isolation=None if infrastructure else ExternalCheckerIsolationReceipt(
                repository="registry.example/workstream/checker",
                platform_manifest_digest=request.registry.image_digest,
                platform_manifest_media_type="application/vnd.oci.image.manifest.v1+json",
                platform_manifest_byte_count=1024,
                operating_system="linux",
                architecture="amd64",
                config_image_id=SHA,
                runtime="runsc",
                isolation_mode="gvisor",
                sandbox_uid=65532,
                sandbox_gid=65532,
            ),
        )
        if self.events is not None:
            self.events.append("response_received")
        return response


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["passed", "failed"])
async def test_selected_post_runs_every_locked_image_without_acceptance(verdict) -> None:
    identity = execution_identity("post_submit")
    material = execution_material(identity)
    view, execution, policy = _MaterialView(material), _Execution(verdict=verdict), _policy()
    result = await SelectedPostSubmitProcessor(
        policy=policy,
        identity=identity,
        execution=execution,
    ).evaluate(object(), view)

    assert len(result.external_members) == 1
    assert result.external_members[0].result.verdict == verdict
    assert result.result_digest == canonical_json_hash(result.canonical_body())
    assert len(view.requests) == len(execution.requests) == 1
    assert view.requests[0].identity.submission_id == identity.submission_id
    assert "routing" not in result.canonical_body()
    assert "accepted" not in result.canonical_body()


@pytest.mark.asyncio
async def test_selected_post_separates_infrastructure_from_work_findings() -> None:
    identity = execution_identity("post_submit")
    with pytest.raises(RuntimeError, match="deadline_exceeded"):
        await SelectedPostSubmitProcessor(
            policy=_policy(),
            identity=identity,
            execution=_Execution(outcome="infrastructure_failed"),
        ).evaluate(object(), _MaterialView(execution_material(identity)))


@pytest.mark.asyncio
async def test_selected_post_exposes_result_only_after_grant_cleanup() -> None:
    identity = execution_identity("post_submit")
    events = []
    result = await SelectedPostSubmitProcessor(
        policy=_policy(),
        identity=identity,
        execution=_Execution(events=events),
    ).evaluate(
        object(),
        _MaterialView(execution_material(identity), events=events),
    )

    assert result.external_members[0].result.verdict == "passed"
    assert events == ["grant_entered", "execute", "response_received", "grant_closed"]


@pytest.mark.asyncio
async def test_selected_post_discards_received_result_when_grant_cleanup_fails() -> None:
    identity = execution_identity("post_submit")
    events = []
    with pytest.raises(ArtifactScratchIntegrityError, match="controlled grant cleanup failure"):
        await SelectedPostSubmitProcessor(
            policy=_policy(),
            identity=identity,
            execution=_Execution(events=events),
        ).evaluate(
            object(),
            _MaterialView(
                execution_material(identity),
                events=events,
                cleanup_failure=True,
            ),
        )

    assert events == ["grant_entered", "execute", "response_received", "grant_closed"]


@pytest.mark.postgres_schema_contract
async def test_selected_post_materializes_actual_submission_and_replays(
    tmp_path, isolated_database_env,
) -> None:
    """Exercise selected POST through native Submission, ART, AUTH and storage."""
    async with material_fixture(tmp_path, isolated_database_env) as h:
        reservation = await reserve(h)
        executor = live_executor(h, selected_execution=_Execution())
        result = await executor.evaluate_post_submission(h.request)
        assert result.outcome == "completed"
        assert result.attempt_id == reservation.attempt_id
        assert result.execution is not None
        assert result.execution.external_members == ()
        assert await executor.evaluate_post_submission(h.request) == result
        assert len(h.store.opens) == 1


@pytest.mark.postgres_schema_contract
async def test_selected_post_persists_locked_external_member(
    tmp_path, isolated_database_env,
) -> None:
    """Compile, approve and execute one real registered POST requirement."""
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        post_submit_registry_spec=_post_spec(),
    ) as h:
        assert len(h.request.policy.entries) == 1
        execution = _Execution()
        result = await live_executor(
            h,
            selected_execution=execution,
        ).evaluate_post_submission(h.request)
        assert result.outcome == "completed"
        assert result.execution is not None
        assert len(result.execution.external_members) == 1
        member = result.execution.external_members[0]
        assert member.requirement_id == "project.post_evidence"
        assert member.registry_entry_id == h.request.policy.entries[0].registry.registry_entry_id
        assert member.result.verdict == "passed"
        assert len(execution.requests) == 1


@pytest.mark.asyncio
async def test_selected_post_request_and_result_bind_exact_locked_policy() -> None:
    identity = execution_identity("post_submit")
    policy = _policy()
    request = _request(identity, policy)
    execution = await SelectedPostSubmitProcessor(
        policy=policy,
        identity=identity,
        execution=_Execution(),
    ).evaluate(request, _MaterialView(execution_material(identity)))
    result = make_selected_post_submit_result(
        request_id=request.evaluation_request_id,
        request_digest=request.request_sha256,
        attempt_id=identity.attempt_id,
        evaluation_generation=request.evaluation_generation,
        result_id=identity.result_id,
        outcome="completed",
        execution=execution,
        infrastructure_failure_code=None,
    )

    result.validate_request(request)
    empty_policy = LockedExternalPostSubmitPolicy(
        entries=(),
        policy_sha256=canonical_json_hash(
            {
                "schema_version": "external_post_submit_policy.v1",
                "entries": [],
            }
        ),
    )
    with pytest.raises(ValueError, match="request mismatch"):
        result.validate_request(
            make_selected_post_submit_request(
                **request.model_dump(
                    exclude={"request_sha256", "policy", "expected_context"},
                ),
                policy=empty_policy,
                expected_context=request.expected_context.model_copy(
                    update={
                        "post_policy_hash": empty_policy.policy_sha256
                    }
                ),
            )
        )

    missing = SelectedPostSubmitExecutionFacts(
        policy_sha256=policy.policy_sha256,
        required_external_count=0,
        external_members=(),
    )
    with pytest.raises(ValueError, match="request mismatch"):
        make_selected_post_submit_result(
            **result.model_dump(exclude={"result_digest", "execution"}),
            execution=missing,
        ).validate_request(request)

    member = execution.external_members[0]
    extra = SelectedPostSubmitExecutionFacts(
        policy_sha256=policy.policy_sha256,
        required_external_count=2,
        external_members=(
            member,
            replace(member, order=1, requirement_id="project.unrequested"),
        ),
    )
    with pytest.raises(ValueError, match="request mismatch"):
        make_selected_post_submit_result(
            **result.model_dump(exclude={"result_digest", "execution"}),
            execution=extra,
        ).validate_request(request)

    second = policy.entries[0].model_copy(
        update={"requirement_id": "project.post_evidence.secondary"}
    )
    two_policy_body = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [item.model_dump(mode="json") for item in (*policy.entries, second)],
    }
    two_policy = LockedExternalPostSubmitPolicy(
        entries=(*policy.entries, second),
        policy_sha256=canonical_json_hash(two_policy_body),
    )
    two_request = _request(identity, two_policy)
    two_execution = await SelectedPostSubmitProcessor(
        policy=two_policy,
        identity=identity,
        execution=_Execution(),
    ).evaluate(two_request, _MaterialView(execution_material(identity)))
    reordered = SelectedPostSubmitExecutionFacts(
        policy_sha256=two_policy.policy_sha256,
        required_external_count=2,
        external_members=(
            replace(two_execution.external_members[1], order=0),
            replace(two_execution.external_members[0], order=1),
        ),
    )
    with pytest.raises(ValueError, match="request mismatch"):
        make_selected_post_submit_result(
            request_id=two_request.evaluation_request_id,
            request_digest=two_request.request_sha256,
            attempt_id=identity.attempt_id,
            evaluation_generation=two_request.evaluation_generation,
            result_id=identity.result_id,
            outcome="completed",
            execution=reordered,
            infrastructure_failure_code=None,
        ).validate_request(two_request)

    foreign_registry = two_policy.entries[0].registry.model_copy(
        update={"registry_entry_id": new_record_id()}
    )
    foreign_entry = two_policy.entries[0].model_copy(update={"registry": foreign_registry})
    foreign_policy_body = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [
            item.model_dump(mode="json") for item in (foreign_entry, two_policy.entries[1])
        ],
    }
    foreign_policy = LockedExternalPostSubmitPolicy(
        entries=(foreign_entry, two_policy.entries[1]),
        policy_sha256=canonical_json_hash(foreign_policy_body),
    )
    foreign_request = _request(identity, foreign_policy)
    wrong_registry_execution = SelectedPostSubmitExecutionFacts(
        policy_sha256=foreign_policy.policy_sha256,
        required_external_count=2,
        external_members=two_execution.external_members,
    )
    with pytest.raises(ValueError, match="request mismatch"):
        make_selected_post_submit_result(
            request_id=foreign_request.evaluation_request_id,
            request_digest=foreign_request.request_sha256,
            attempt_id=identity.attempt_id,
            evaluation_generation=foreign_request.evaluation_generation,
            result_id=identity.result_id,
            outcome="completed",
            execution=wrong_registry_execution,
            infrastructure_failure_code=None,
        ).validate_request(foreign_request)

    wrong_image_execution = SelectedPostSubmitExecutionFacts(
        policy_sha256=two_policy.policy_sha256,
        required_external_count=2,
        external_members=(
            replace(
                two_execution.external_members[0],
                isolation=replace(
                    two_execution.external_members[0].isolation,
                    platform_manifest_digest="sha256:" + "b" * 64,
                ),
            ),
            two_execution.external_members[1],
        ),
    )
    with pytest.raises(ValueError, match="request mismatch"):
        make_selected_post_submit_result(
            request_id=two_request.evaluation_request_id,
            request_digest=two_request.request_sha256,
            attempt_id=identity.attempt_id,
            evaluation_generation=two_request.evaluation_generation,
            result_id=identity.result_id,
            outcome="completed",
            execution=wrong_image_execution,
            infrastructure_failure_code=None,
        ).validate_request(two_request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,expected",
    [("completed", "completed"), ("infrastructure_failed", "infrastructure_failed")],
)
async def test_selected_scheduler_consumer_derives_exact_envelope(outcome, expected) -> None:
    from app.modules.checkers.execution import _SelectedExternalConsumer

    identity = execution_identity("post_submit")
    policy = _policy()
    request = _request(identity, policy)
    lease = ExecutionLease(
        reservation=EvaluationReservation(
            request_id=request.evaluation_request_id,
            request_digest=request.request_sha256,
            attempt_id=identity.attempt_id,
            result_id=identity.result_id,
            evaluation_generation=request.evaluation_generation,
        ),
        lease_id=identity.lease_id,
        lease_generation=identity.lease_generation,
        expires_at=identity.lease_expires_at,
    )
    result = await _SelectedExternalConsumer(
        _Execution(outcome=outcome), lease
    ).evaluate(request, _MaterialView(execution_material(identity)))

    assert result.outcome == expected
    result.validate_request(request)
    assert type(validate_execution_request(request.model_dump())) is type(request)
    assert type(validate_execution_result(result.model_dump())) is type(result)
    stored = json.loads(result.model_dump_json())
    assert type(validate_stored_execution_result(json.dumps(stored))) is type(result)


def test_execution_boundary_rejects_removed_catalogue_request_schema() -> None:
    """Retained catalogue-shaped facts cannot enter the active scheduler."""
    removed = {
        "schema_version": "post_submit_evaluation_request",
        "evaluation_request_id": str(new_record_id()),
    }
    with pytest.raises(ValueError):
        validate_execution_request(removed)
    with pytest.raises(ValueError):
        validate_stored_execution_request(json.dumps(removed))


def test_selected_post_content_uses_exact_locked_external_policy() -> None:
    policy = _policy()
    locked = SimpleNamespace(
        locked_guide_version="guide-v1",
        locked_guide_source_snapshot_id=new_record_id(),
        locked_guide_source_snapshot_hash=SHA,
        locked_effective_project_submission_artifact_policy_id=new_record_id(),
        locked_effective_project_submission_artifact_policy_hash=SHA,
        locked_pre_submit_checker_policy_id=new_record_id(),
        locked_pre_submit_checker_bundle_hash=SHA,
        locked_post_submit_checker_policy_hash=policy.policy_sha256,
        locked_post_submit_checker_policy_id=new_record_id(),
        locked_post_submit_checker_policy_version="guide-v1",
        locked_review_policy_id=new_record_id(),
        locked_review_policy_generation=1,
        locked_review_policy_hash=SHA,
        locked_revision_policy_id=new_record_id(),
        locked_revision_policy_generation=1,
        locked_revision_policy_hash=SHA,
    )
    task = SimpleNamespace(
        locked_policy=locked,
        locked_project_context=SimpleNamespace(project_id=new_record_id()),
    )

    content = selected_submission_evaluation_content(task, policy)

    assert content.expected_context.post_policy_hash == policy.policy_sha256
    assert content.expected_context.post_policy_hash == locked.locked_post_submit_checker_policy_hash
