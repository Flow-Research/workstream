"""Fail closed at exact complete-context boundaries using real activated sources."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.projects.api import ProjectLockedPolicyContextUnavailable
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


@pytest.mark.parametrize(
    "failure",
    [
        "activation",
        "activation_digest",
        "pre_approval",
        "post_approval",
        "finalization",
        "catalogue",
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
                "catalogue": (
                    ProjectGuideCompilationAttempt,
                    "pre_catalogue_manifest_hash",
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
                    "pre_catalogue_manifest_hash",
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
