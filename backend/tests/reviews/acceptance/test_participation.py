"""Real human-source shared-acceptance lifecycle and economic proof."""

from uuid import UUID

import pytest

from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.reviews.api.acceptance import FinalAcceptanceConflict
from tests.contributions.records.support import contribution_source

from .participation_support import (
    participant,
    prepare_review_pending,
    request_for,
    stored_effects,
)

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


@pytest.mark.parametrize(
    "instruments",
    [(), ("money",), ("money", "project_points")],
    ids=("unpaid", "one-award", "two-awards"),
)
async def test_human_acceptance_creates_and_exactly_replays_complete_effects(
    tmp_path, isolated_database_env, instruments
):
    async with contribution_source(
        tmp_path,
        isolated_database_env,
        contribution_awards=instruments,
        persist_acceptance=False,
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())

        async with h.factory() as session, session.begin():
            created = await participant(session).participate(request)
        async with h.factory() as session, session.begin():
            replayed = await participant(session).participate(request)

        assert replayed == created
        assert created.acceptance.id == request.acceptance.id
        assert created.acceptance.accepted_at == replayed.acceptance.accepted_at
        assert created.task_effects.request == request.task_effects
        assert created.task_effects.task_status == "accepted"
        assert created.task_effects.assignment_status == "completed"
        assert created.participation.contribution.source_final_acceptance_id == created.acceptance.id
        assert created.participation.contribution.source_task_assignment_id == (
            request.task_effects.assignment_id
        )
        assert {award.instrument_type.value for award in created.participation.awards} == set(
            instruments
        )

        async with h.factory() as session:
            acceptance = (
                await session.execute(
                    text("SELECT * FROM public.final_acceptances WHERE id=:id"),
                    {"id": created.acceptance.id},
                )
            ).mappings().one()
            for field in (
                "id",
                "source_review_id",
                "source_routing_manifest_id",
                "policy_context_ref",
            ):
                assert acceptance[field] == getattr(created.acceptance, field)
            for field in (
                "project_id",
                "task_id",
                "submission_id",
                "accepted_submitter_id",
                "recorded_by",
            ):
                assert UUID(str(acceptance[field])) == getattr(created.acceptance, field)
            assert acceptance["acceptance_source"] == created.acceptance.acceptance_source
            assert acceptance["accepted_at"] == created.acceptance.accepted_at

            contribution = (
                await session.execute(
                    text(
                        "SELECT id,created_at FROM public.contribution_records "
                        "WHERE source_final_acceptance_id=:id"
                    ),
                    {"id": created.acceptance.id},
                )
            ).one()
            assert contribution == (
                created.participation.contribution.id,
                created.participation.contribution.created_at,
            )
            awards = (
                await session.execute(
                    text(
                        "SELECT id,created_at FROM public.compensation_awards "
                        "WHERE contribution_record_id=:id ORDER BY instrument_type"
                    ),
                    {"id": created.participation.contribution.id},
                )
            ).all()
            assert awards == [
                (award.id, award.created_at) for award in created.participation.awards
            ]
            assert await stored_effects(session, request.task_effects.task_id) == {
                "task_status": "accepted",
                "assignment_status": "completed",
                "acceptances": 1,
                "contributions": 1,
                "reviewer_contributions": 0,
                "awards": len(instruments),
            }
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 1


async def test_human_source_rejects_foreign_review_identity_and_invalid_artifact_hash(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path / "local", isolated_database_env, persist_acceptance=False
    ) as h:
        async with contribution_source(
            tmp_path / "foreign",
            isolated_database_env,
            persist_acceptance=False,
            provision_services=False,
            storage_settings=h.settings,
        ) as foreign:
            await prepare_review_pending(h)
            request = await request_for(h, correlation_id=new_record_id())

            foreign_sources = (
                request.acceptance.model_copy(
                    update={"source_review_id": foreign.acceptance.source_review_id}
                ),
                request.acceptance.model_copy(
                    update={"recorded_by": foreign.acceptance.recorded_by}
                ),
            )
            for acceptance in foreign_sources:
                async with h.factory() as session, session.begin():
                    with pytest.raises(FinalAcceptanceConflict):
                        await participant(session).participate(
                            request.model_copy(update={"acceptance": acceptance})
                        )

            changed_hash = "sha256:" + (
                "0" * 64
                if request.task_effects.content_sha256 != "sha256:" + "0" * 64
                else "1" * 64
            )
            changed_task = request.task_effects.model_copy(
                update={"content_sha256": changed_hash}
            )
            async with h.factory() as session, session.begin():
                with pytest.raises(FinalAcceptanceConflict):
                    await participant(session).participate(
                        request.model_copy(update={"task_effects": changed_task})
                    )

            async with h.factory() as session:
                assert await stored_effects(session, request.task_effects.task_id) == {
                    "task_status": "review_pending",
                    "assignment_status": "active",
                    "acceptances": 0,
                    "contributions": 0,
                    "reviewer_contributions": 0,
                    "awards": 0,
                }
                assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 2
