"""PostgreSQL protects one current unified approval independently of repository reads."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval, GuideProposalCorrection, GuideProposalError,
)
from app.modules.projects.guide_compilation.proposal_repository import GuideProposalRepository
from .pg_support import finalize_corrected_attempt, proposal_case, read_package
from .test_postgresql import approve, correct


@pytest.mark.parametrize("omitted_guard", ["lookup", "supersession"])
async def test_database_rejects_duplicate_approved_tip_and_allows_linked_successor(
    clean_postgres_database, monkeypatch, omitted_guard,
):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        first = await approve(factory, command, actor, grant, GuideProposalApproval(
            target=package.target, idempotency_key=uuid4()))
        correction = await correct(factory, command, actor, grant, GuideProposalCorrection(
            target=package.target, idempotency_key=uuid4(), reason="Reconsider the required inputs."))
        successor = await finalize_corrected_attempt(factory, values, actor, correction)
        next_package = await read_package(factory, successor, actor, grant)
        assert next_package.current_approval_operation_id == first.operation_id
        async with factory() as session:
            audit_count = await session.scalar(text("SELECT count(*) FROM audit_events"))

        async def omit_current_approval(self, guide_id):
            return None

        original_flush = AsyncSession.flush
        prior_states = {str(first.artifact_policy_id): "approved",
                        str(first.effective_policy_id): "approved",
                        str(first.pre_submit_policy_id): "compiled"}

        async def omit_prior_supersession(self, objects=None):
            for row in tuple(self.dirty):
                if str(getattr(row, "id", "")) in prior_states:
                    row.lifecycle_status = prior_states[str(row.id)]
                    row.superseded_at = None
            return await original_flush(self, objects)

        # Omit only one application behavior. Actual authority, reservation,
        # compiler outputs and all database guards remain active.
        with monkeypatch.context() as patch:
            if omitted_guard == "lookup":
                patch.setattr(GuideProposalRepository, "current_approval", omit_current_approval)
            else:
                patch.setattr(AsyncSession, "flush", omit_prior_supersession)
            prior = {} if omitted_guard == "lookup" else dict(
                expected_previous_approval_operation_id=first.operation_id,
                expected_previous_approval_output_digest=next_package.current_approval_output_digest)
            expected_error = GuideProposalError if omitted_guard == "lookup" else DBAPIError
            with pytest.raises(expected_error) as error:
                await approve(factory, successor, actor, grant, GuideProposalApproval(
                    target=next_package.target, idempotency_key=uuid4(), **prior))
            if omitted_guard == "lookup":
                assert error.value.code == "storage_unavailable"
                assert isinstance(error.value.__cause__, IntegrityError)
                assert "uq_proposal_approval_root_guide" in str(error.value.__cause__)
            else:
                assert "proposal prior approval is not superseded" in str(error.value)
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM audit_events")) == audit_count
            for table in ("project_guide_proposal_approvals", "effective_project_submission_artifact_policies",
                          "pre_submit_checker_policies", "submission_policy_mutation_idempotency_records"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 1
            assert await session.scalar(text("SELECT lifecycle_status FROM submission_artifact_policies WHERE id=:id"),
                                        {"id": str(next_package.target.artifact_policy_id)}) == "draft"

        second = await approve(factory, successor, actor, grant, GuideProposalApproval(
            target=next_package.target, idempotency_key=uuid4(),
            expected_previous_approval_operation_id=first.operation_id,
            expected_previous_approval_output_digest=next_package.current_approval_output_digest))
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM submission_artifact_policies "
                                             "WHERE guide_id=:guide AND lifecycle_status='approved'"),
                                        {"guide": str(command.guide_id)}) == 1
            assert await session.scalar(text("SELECT lifecycle_status FROM submission_artifact_policies WHERE id=:id"),
                                        {"id": str(first.artifact_policy_id)}) == "superseded"
            assert await session.scalar(text("SELECT prior_approval_operation_id FROM project_guide_proposal_approvals "
                                             "WHERE operation_id=:id"), {"id": second.operation_id}) == first.operation_id
        await assert_predecessor_cannot_be_reactivated(factory, first)


async def assert_predecessor_cannot_be_reactivated(factory, predecessor):
    """Retained valid custody cannot authorize a second current tip via direct SQL."""
    rows = (
        ("submission_artifact_policies", predecessor.artifact_policy_id, "approved"),
        ("effective_project_submission_artifact_policies", predecessor.effective_policy_id, "approved"),
        ("pre_submit_checker_policies", predecessor.pre_submit_policy_id, "compiled"),
    )
    async with factory() as session:
        before = {}
        for table, identity, _ in rows:
            before[table] = (await session.execute(text(
                f"SELECT lifecycle_status,superseded_at FROM {table} WHERE id=:id"),
                {"id": str(identity)})).one()
        timestamps = {row.superseded_at for row in before.values()}
        assert len(timestamps) == 1 and None not in timestamps
    with pytest.raises(DBAPIError, match="proposal approval lifecycle mismatch"):
        async with factory() as session, session.begin():
            for table, identity, status in rows:
                await session.execute(text(f"UPDATE {table} SET lifecycle_status=:status, superseded_at=NULL WHERE id=:id"),
                                      {"id": str(identity), "status": status})
            await session.execute(text("SET CONSTRAINTS guide_proposal_approval_custody IMMEDIATE"))
    async with factory() as session:
        for table, identity, _ in rows:
            assert (await session.execute(text(
                f"SELECT lifecycle_status,superseded_at FROM {table} WHERE id=:id"),
                {"id": str(identity)})).one() == before[table]
        assert await session.scalar(text(
            "SELECT count(*) FROM project_guide_proposal_approvals a "
            "JOIN submission_artifact_policies p ON p.id=a.artifact_policy_id "
            "WHERE a.prior_approval_operation_id=:id AND p.lifecycle_status='approved'"),
            {"id": predecessor.operation_id}) == 1
