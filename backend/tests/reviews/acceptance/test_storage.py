"""Stored acceptance custody through the actual authorized outcome operation."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.reviews.acceptance.models import FinalAcceptance
from app.modules.reviews.acceptance.repository import FinalAcceptanceRepository
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome,
    authorized_routing_source,
    outcome_snapshot,
)

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


async def reject_candidate(h, monkeypatch, changes, message):
    """Substitute the actual candidate, preserving all other source and AUTH facts."""
    original = FinalAcceptanceRepository.persist

    async def substituted(repository, source, *, disposition):
        return await original(
            repository, source.model_copy(update=changes), disposition=disposition
        )

    async with h.factory() as session:
        before = await outcome_snapshot(session)
    with monkeypatch.context() as patch:
        patch.setattr(FinalAcceptanceRepository, "persist", substituted)
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match=message):
                async with session.begin():
                    await apply_outcome(session, h, 2)
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    async with h.factory() as session:
        assert await outcome_snapshot(session) == before


async def test_acceptance_owner_substitution(tmp_path, isolated_database_env, monkeypatch):
    async with authorized_routing_source(tmp_path / "one", isolated_database_env) as h:
        async with authorized_routing_source(
            tmp_path / "two",
            isolated_database_env,
            storage_settings=h.settings,
            provision_services=False,
        ) as foreign:
            # Both complete sources exist. Neither outcome has been applied.
            async with h.factory() as session:
                foreign_policy = await session.scalar(
                    text("SELECT locked_review_policy_id FROM public.submissions WHERE id=:id"),
                    {"id": foreign.request.submission_id},
                )
            replacements = {
                "project_id": foreign.request.project_id,
                "task_id": foreign.request.task_id,
                "submission_id": foreign.request.submission_id,
                "accepted_submitter_id": foreign.source["contributor_id"],
                "policy_context_ref": foreign_policy,
            }
            for field, value in replacements.items():
                await reject_candidate(
                    h, monkeypatch, {field: value}, "final acceptance canonical lineage mismatch"
                )
            await reject_candidate(
                h,
                monkeypatch,
                {"source_routing_manifest_id": new_record_id()},
                "final acceptance routing source mismatch",
            )
            await reject_candidate(
                h,
                monkeypatch,
                {"recorded_by": h.source["contributor_id"]},
                "final acceptance routing source mismatch",
            )
            # A real AUTH event for the same work is still the wrong phase receipt.
            await reject_candidate(
                h,
                monkeypatch,
                {"source_authorization_decision_id": h.source["execute_evidence_id"]},
                "routing authority requires its complete governed outcome",
            )
            async with h.factory() as session, session.begin():
                assert (await apply_outcome(session, h, 2))["final_acceptance_id"]


async def test_exclusive_source_shape(tmp_path, isolated_database_env, monkeypatch):
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        for changes in (
            {"source_routing_manifest_id": None},
            {"source_review_id": new_record_id()},
            {"acceptance_source": "human_review"},
            {"acceptance_source": "automatic"},
        ):
            await reject_candidate(h, monkeypatch, changes, "ck_final_acceptances_source_shape")
        async with h.factory() as session, session.begin():
            assert (await apply_outcome(session, h, 2))["final_acceptance_id"]


async def test_acceptance_clock_and_immutability(tmp_path, isolated_database_env, monkeypatch):
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        original = FinalAcceptanceRepository.persist

        async def supplied_clock(repository, source, *, disposition):
            assert disposition == "new"
            values = source.model_dump()
            for field in (
                "project_id",
                "task_id",
                "submission_id",
                "accepted_submitter_id",
                "recorded_by",
                "policy_context_ref",
            ):
                values[field] = str(values[field])
            await repository._session.execute(
                insert(FinalAcceptance).values(
                    **values, accepted_at=datetime(2000, 1, 1, tzinfo=UTC)
                )
            )
            return await original(repository, source, disposition="replay")

        with monkeypatch.context() as patch:
            patch.setattr(FinalAcceptanceRepository, "persist", supplied_clock)
            async with h.factory() as session, session.begin():
                before = await session.scalar(text("SELECT clock_timestamp()"))
                result = await apply_outcome(session, h, 2)
                stored = await session.scalar(
                    text("SELECT accepted_at FROM public.final_acceptances")
                )
                after = await session.scalar(text("SELECT clock_timestamp()"))
                assert before <= stored <= after
        async with h.factory() as session:
            retained = await outcome_snapshot(session)
        for command in (
            "UPDATE public.final_acceptances SET accepted_at=clock_timestamp()",
            "UPDATE public.final_acceptances SET recorded_by=accepted_submitter_id",
            "DELETE FROM public.final_acceptances",
            "TRUNCATE public.final_acceptances CASCADE",
        ):
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match="immutable"):
                    async with session.begin():
                        await session.execute(text(command))
        async with h.factory() as session:
            assert await outcome_snapshot(session) == retained
        async with h.factory() as session, session.begin():
            assert await apply_outcome(session, h, 2) == result | {"replayed": True}


async def test_uncommitted_routing_parent_cannot_authorize_acceptance(
    tmp_path, isolated_database_env
):
    """Independent visibility rejects a parent that subsequently rolls back."""
    from uuid import UUID

    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as parent:
            await parent.begin()
            pending = await apply_outcome(parent, h, 2)
            values = await parent.scalar(
                text("SELECT to_jsonb(f) FROM public.final_acceptances f WHERE id=:id"),
                {"id": pending["final_acceptance_id"]},
            )
            values.pop("accepted_at")
            values["id"] = new_record_id()
            for field in ("source_authorization_decision_id", "source_routing_manifest_id"):
                values[field] = UUID(values[field])
            async with h.factory() as child:
                with pytest.raises(DBAPIError, match="final acceptance routing source mismatch"):
                    async with child.begin():
                        await child.execute(text("SET LOCAL statement_timeout='2s'"))
                        await child.execute(insert(FinalAcceptance).values(**values))
            await parent.rollback()
        async with h.factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 0
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM public.task_post_submit_routing_manifests")
                )
                == 0
            )
        async with h.factory() as session, session.begin():
            assert (await apply_outcome(session, h, 2))["final_acceptance_id"]
