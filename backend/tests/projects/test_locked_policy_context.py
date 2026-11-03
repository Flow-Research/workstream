"""Fail closed at exact complete-context boundaries using real activated sources."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.projects.api import CanonicalJsonObject, ProjectLockedPolicyContextUnavailable
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideMutationIdempotencyRecord,
    GuideSourceSnapshot,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ReviewPolicy,
    RevisionPolicy,
)
from app.modules.projects.guide_compilation.models import (
    ProjectGuideCompilationAttempt,
    ProjectGuideProposalApproval,
    ProjectGuideSetupFinalization,
)
from app.modules.projects.post_policy.models import PostPolicyOperation
from tests.projects.locked_policy_fixtures import activated_context, frozen_request


async def test_false_locked_context_rechecks_approved_checker_plan(
    clean_postgres_database, monkeypatch,
):
    """Execution refuses a changed plan even when the review policy allows automatic acceptance."""
    from app.modules.projects.post_policy.repository import PostPolicyRepository
    from tests.authorization.guide_activation.pg_support import activate
    from tests.projects.guide_activation.pg_support import activation_case

    async with activation_case(
        clean_postgres_database, human_review_required=False,
    ) as (factory, command, actor, _, _, _):
        receipt = await activate(factory, actor, command)
        request = frozen_request(receipt)
        async with factory() as session, session.begin():
            assert (await ProjectLockedPolicyRepository(
                session
            ).lock_locked_policy_context(request)).activation_receipt == receipt

        original = PostPolicyRepository.lock_policy

        async def locked_with_changed_plan(self, *args, **kwargs):
            locked, policy, custody = await original(self, *args, **kwargs)
            operation = locked.view.approval_custody.operation
            plan = json.loads(json.dumps(operation.effective_pre_submit_plan))
            assert plan["pre_submit"]["policy_sha256"].startswith("sha256:")
            plan["pre_submit"]["policy_sha256"] = "sha256:" + "f" * 64
            set_committed_value(operation, "effective_pre_submit_plan", plan)
            return locked, policy, custody

        monkeypatch.setattr(PostPolicyRepository, "lock_policy", locked_with_changed_plan)
        async with factory() as session, session.begin():
            with pytest.raises(ProjectLockedPolicyContextUnavailable):
                await ProjectLockedPolicyRepository(session).lock_locked_policy_context(request)


@pytest.mark.parametrize(
    "failure",
    [
        "activation",
        "activation_digest",
        "pre_approval",
        "post_approval",
        "finalization",
        "attempt_input_hash",
        "foreign_selector",
        "foreign_project",
        "snapshot_hash",
        "effective_hash",
        "pre_hash",
        "post_hash",
        "review_hash",
        "revision_hash",
        "review_incomplete",
        "revision_incomplete",
        "project_archived",
        "pre_pending",
        "snapshot_array",
        "effective_array",
        "pre_array",
        "nonfinite_body",
    ],
)
async def test_context_rejects_missing_or_substituted_custody(
    clean_postgres_database, monkeypatch, failure
):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        request = frozen_request(receipt)
        async with factory() as session, session.begin():
            owner = ProjectLockedPolicyRepository(session)
            assert (await owner.lock_locked_policy_context(request)).activation_receipt == receipt
            missing = {
                "activation": GuideMutationIdempotencyRecord,
                "pre_approval": ProjectGuideProposalApproval,
                "finalization": ProjectGuideSetupFinalization,
            }.get(failure)
            altered = {
                "activation_digest": (
                    GuideMutationIdempotencyRecord,
                    "request_digest",
                    "sha256:" + "a" * 64,
                ),
                "attempt_input_hash": (
                    ProjectGuideCompilationAttempt,
                    "canonical_input_hash",
                    "sha256:" + "a" * 64,
                ),
                "snapshot_hash": (GuideSourceSnapshot, "manifest_json", {"wrong": True}),
                "effective_hash": (
                    EffectiveProjectSubmissionArtifactPolicy,
                    "effective_policy",
                    {"wrong": True},
                ),
                "pre_hash": (PreSubmitCheckerPolicy, "compiled_bundle", {"wrong": True}),
                "post_hash": (PostSubmitCheckerPolicy, "policy_body", {"wrong": True}),
                "review_hash": (ReviewPolicy, "human_review_required", False),
                "revision_hash": (RevisionPolicy, "max_revision_rounds", 999),
                "review_incomplete": (ReviewPolicy, "semantics_status", "legacy_incomplete"),
                "revision_incomplete": (RevisionPolicy, "semantics_status", "legacy_incomplete"),
                "project_archived": (Project, "status", "archived"),
                "pre_pending": (PreSubmitCheckerPolicy, "lifecycle_status", "pending_compilation"),
                "snapshot_array": (GuideSourceSnapshot, "manifest_json", []),
                "effective_array": (
                    EffectiveProjectSubmissionArtifactPolicy,
                    "effective_policy",
                    [],
                ),
                "pre_array": (PreSubmitCheckerPolicy, "compiled_bundle", []),
                "nonfinite_body": (
                    EffectiveProjectSubmissionArtifactPolicy,
                    "effective_policy",
                    {"invalid": float("nan")},
                ),
            }.get(failure)
            seen = []

            def corrupt(row):
                if missing is not None and isinstance(row, missing):
                    seen.append(failure)
                    return None
                if altered is not None and isinstance(row, altered[0]):
                    seen.append(failure)
                    set_committed_value(row, altered[1], altered[2])
                return row

            original_scalar, original_get, original_scalars = (
                session.scalar,
                session.get,
                session.scalars,
            )
            original_refresh = session.refresh

            async def scalar(*args, **kwargs):
                return corrupt(await original_scalar(*args, **kwargs))

            async def get(*args, **kwargs):
                return corrupt(await original_get(*args, **kwargs))

            async def scalars(statement, *args, **kwargs):
                if (
                    failure == "post_approval"
                    and statement.column_descriptions[0]["entity"] is PostPolicyOperation
                ):
                    seen.append(failure)
                    statement = statement.where(PostPolicyOperation.kind != "approve")
                return await original_scalars(statement, *args, **kwargs)

            async def refresh(row, *args, **kwargs):
                await original_refresh(row, *args, **kwargs)
                corrupt(row)

            monkeypatch.setattr(session, "refresh", refresh)
            monkeypatch.setattr(session, "scalar", scalar)
            monkeypatch.setattr(session, "get", get)
            monkeypatch.setattr(session, "scalars", scalars)
            if failure == "foreign_selector":
                request = replace(request, effective_policy_id=uuid4())
            elif failure == "foreign_project":
                request = replace(request, project_id=uuid4())
            with pytest.raises(ProjectLockedPolicyContextUnavailable) as denied:
                await owner.lock_locked_policy_context(request)
            assert denied.value.code == "project_locked_policy_context_changed"
            if not failure.startswith("foreign_"):
                assert seen, "the intended corrupt read was not reached"
            assert not session.new and not session.dirty and not session.deleted


async def test_context_requires_caller_root_transaction(clean_postgres_database):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session:
            owner = ProjectLockedPolicyRepository(session)
            with pytest.raises(ProjectLockedPolicyContextUnavailable):
                await owner.lock_active_policy_context(receipt.contribution.project_id)
            assert not session.in_transaction()
            async with session.begin(), session.begin_nested():
                with pytest.raises(ProjectLockedPolicyContextUnavailable):
                    await owner.lock_locked_policy_context(frozen_request(receipt))


@pytest.mark.parametrize(
    "field,value",
    [
        ("guide_status", "draft"),
        ("effective_policy_status", "draft"),
        ("pre_submit_policy_status", "pending_compilation"),
        ("pre_submit_compiler_version", ""),
        ("guide_version", ""),
        ("effective_policy_id", None),
    ],
)
async def test_context_rejects_invalid_public_facts(clean_postgres_database, field, value):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            facts = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(receipt)
            )
        with pytest.raises(ValueError):
            replace(facts, **{field: value})


async def test_context_refreshes_preloaded_custody(clean_postgres_database):
    from sqlalchemy import select
    from app.modules.projects.models import ProjectGuide, SubmissionPolicyMutationIdempotencyRecord
    from app.modules.projects.guide_compilation.models import (
        ProjectGuideCompilationRequestOperation,
    )

    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            owner = ProjectLockedPolicyRepository(session)
            expected = await owner.lock_locked_policy_context(frozen_request(receipt))
            held = []
            for model, field, bad in (
                (Project, "status", "archived"),
                (ProjectGuide, "status", "draft"),
                (GuideMutationIdempotencyRecord, "request_digest", "sha256:" + "f" * 64),
                (
                    ProjectGuideCompilationAttempt,
                    "canonical_input_hash",
                    "sha256:" + "f" * 64,
                ),
                (ProjectGuideCompilationRequestOperation, "source_snapshot_id", str(uuid4())),
                (ProjectGuideSetupFinalization, "facts_digest", "sha256:" + "f" * 64),
                (ProjectGuideProposalApproval, "output_digest", "sha256:" + "f" * 64),
                (SubmissionPolicyMutationIdempotencyRecord, "status", "reserved"),
                (EffectiveProjectSubmissionArtifactPolicy, "effective_policy", {}),
                (PreSubmitCheckerPolicy, "compiled_bundle", {}),
                (PostSubmitCheckerPolicy, "policy_body", {}),
                (PostPolicyOperation, "output_digest", "sha256:" + "f" * 64),
                (ReviewPolicy, "human_review_required", False),
                (RevisionPolicy, "max_revision_rounds", 999),
            ):
                statement = select(model)
                if model is GuideMutationIdempotencyRecord:
                    statement = statement.where(model.operation_id == receipt.operation_id)
                elif model is SubmissionPolicyMutationIdempotencyRecord:
                    statement = statement.where(
                        model.operation_id
                        == receipt.command.target.upstream.operation_id
                    )
                rows = list(await session.scalars(statement))
                assert rows
                for row in rows:
                    original = getattr(row, field)
                    held.append((row, field, original))
                    set_committed_value(row, field, bad)
            assert await owner.lock_locked_policy_context(frozen_request(receipt)) == expected
            for row, field, original in held:
                assert getattr(row, field) == original, (type(row).__name__, field)
            assert not session.dirty


async def test_context_rejects_substituted_post_policy_body(clean_postgres_database):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            facts = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(receipt)
            )
        assert replace(facts) == facts
        body = json.loads(facts.compiled_post_submit_policy.value)
        body["guide_version"] = "different-guide"
        with pytest.raises(ValueError, match="project locked policy facts differ from activation"):
            replace(facts, compiled_post_submit_policy=CanonicalJsonObject.from_mapping(body))


async def test_context_rejects_substituted_review_body(clean_postgres_database):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            facts = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(receipt)
            )
        assert replace(facts) == facts
        body = json.loads(facts.review_policy.value)
        assert body["human_review_required"] is True
        body["human_review_required"] = False
        with pytest.raises(ValueError, match="policy semantics digest mismatch"):
            replace(facts, review_policy=CanonicalJsonObject.from_mapping(body))


async def test_context_rejects_substituted_revision_body(clean_postgres_database):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            facts = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(receipt)
            )
        assert replace(facts) == facts
        body = json.loads(facts.revision_policy.value)
        assert body["max_revision_rounds"] != 999
        body["max_revision_rounds"] = 999
        with pytest.raises(ValueError, match="policy semantics digest mismatch"):
            replace(facts, revision_policy=CanonicalJsonObject.from_mapping(body))


@pytest.mark.parametrize("semantics_format,human_review_required", [("v1", True), ("v2", True), ("v2", False)])
async def test_context_binds_explicit_review_format(
    clean_postgres_database, semantics_format, human_review_required,
):
    """Public value reconstruction is not authorization to activate changed policies."""
    from app.modules.projects.api.guide_activation import GuideActivationReceipt
    from app.modules.projects.api.policy_lineage import ReviewPolicySemantics, policy_digest

    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            facts = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(receipt)
            )
        assert facts.review_semantics_format == "v2"
        body = json.loads(facts.review_policy.value)
        body["human_review_required"] = human_review_required
        values = receipt.model_dump(mode="json")
        values["command"]["review"]["policy_hash"] = policy_digest(
            "review", ReviewPolicySemantics.model_validate(body),
            review_semantics_format=semantics_format,
        )
        consistent = replace(
            facts, activation_receipt=GuideActivationReceipt.model_validate(values),
            review_policy=CanonicalJsonObject.from_mapping(body),
            review_semantics_format=semantics_format,
        )
        assert replace(consistent) == consistent
        if human_review_required:
            wrong_format = "v2" if semantics_format == "v1" else "v1"
            with pytest.raises(ValueError, match="policy semantics digest mismatch"):
                replace(consistent, review_semantics_format=wrong_format)
