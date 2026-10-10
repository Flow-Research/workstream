"""Database source custody through the real authorized outcome transaction."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.tasks.models import Submission, WorkstreamTask
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from tests.tasks.post_submit_routing.outcome_support import (
    authorized_routing_source,
    apply_outcome,
    outcome_snapshot,
)
from .support import (
    SOURCE_COLUMNS,
    activate_successor_guide,
    as_uuid,
    joined_source_facts,
    other_hash,
    source_rows,
)

pytestmark = pytest.mark.postgres_schema_contract


async def test_source_matches_real_completed_run(tmp_path, isolated_database_env):
    async with authorized_routing_source(
        tmp_path, isolated_database_env, human_review_required=True
    ) as h:
        async with h.factory() as session, session.begin():
            before = await session.scalar(text("SELECT clock_timestamp()"))
            result = await apply_outcome(session, h, None)
            after = await session.scalar(text("SELECT clock_timestamp()"))
        async with h.factory() as session:
            stored = await session.get(TaskPostSubmitRoutingManifest, result.routing_manifest_id)
            values = {column: getattr(stored, column) for column in SOURCE_COLUMNS}
            submission = await session.get(Submission, str(h.request.submission_id))
            task = await session.get(WorkstreamTask, str(h.request.task_id))
        facts = await joined_source_facts(h, values)
        assert before <= stored.created_at <= after
        for column, value in h.source.items():
            if column != "id":
                expected = as_uuid(value) if column.endswith("_id") else value
                assert getattr(facts, column) == expected, column
        assert facts.predecessor_submission_id is facts.predecessor_submission_version is None
        assert facts.admission_id == h.created.admission_id
        assert facts.binding_id == h.created.artifact_binding_id
        assert facts.content_id == h.created.artifact_content_id
        for field in type(facts.locked_policy).model_fields:
            expected = getattr(
                task if field == "locked_contribution_policy_version_id" else submission, field
            )
            if field.endswith("_id"):
                expected = as_uuid(expected)
            assert getattr(facts.locked_policy, field) == expected, field
        assert facts.routing_recommendation == "allow_review"
        assert facts.input_materialization_evidence_id != facts.execute_evidence_id
        assert facts.execute_evidence_id != facts.finalize_evidence_id


async def _reject_changed_manifest(h, monkeypatch, changes, message):
    """Change only persisted candidate fields; keep actual source AUTH otherwise valid."""
    import app.modules.tasks.post_submit_routing.outcome as outcome

    original = outcome._manifest

    def changed(*args):
        row = original(*args)
        for name, value in changes.items():
            setattr(row, name, value)
        return row

    async with h.factory() as session:
        before = await outcome_snapshot(session)
    with monkeypatch.context() as patch:
        patch.setattr(outcome, "_manifest", changed)
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match=message):
                async with session.begin():
                    await apply_outcome(session, h, None)
    async with h.factory() as session:
        assert await outcome_snapshot(session) == before


async def test_source_rejects_scalar_and_phase_substitutions(
    tmp_path, isolated_database_env, monkeypatch
):
    async with authorized_routing_source(
        tmp_path, isolated_database_env, human_review_required=True
    ) as h:
        s = h.source
        cases = {
            "request_digest": other_hash(s["request_digest"]),
            "result_digest": other_hash(s["result_digest"]),
            "evaluation_generation": s["evaluation_generation"] + 1,
            "content_sha256": other_hash(s["content_sha256"]),
            "byte_count": s["byte_count"] + 1,
            "semantic_manifest_sha256": other_hash(s["semantic_manifest_sha256"]),
            "execute_evidence_id": str(s["finalize_evidence_id"]),
            "finalize_evidence_id": str(s["execute_evidence_id"]),
            "human_review_required": False,
        }
        for field, value in cases.items():
            await _reject_changed_manifest(
                h,
                monkeypatch,
                {field: value},
                "routing (source authority context|checker source|material|review policy) mismatch",
            )
        async with h.factory() as session, session.begin():
            await apply_outcome(session, h, None)


async def test_source_rejects_foreign_stored_lineage(tmp_path, isolated_database_env, monkeypatch):
    async with authorized_routing_source(
        tmp_path / "one", isolated_database_env, human_review_required=True
    ) as h:
        async with authorized_routing_source(
            tmp_path / "two",
            isolated_database_env,
            human_review_required=True,
            storage_settings=h.settings,
            provision_services=False,
        ) as foreign:
            for field in (
                "project_id",
                "task_id",
                "submission_id",
                "assignment_id",
                "contributor_id",
                "contribution_policy_version_id",
                "checker_run_id",
                "evaluation_request_id",
                "result_id",
                "completion_event_id",
                "replica_id",
            ):
                value = foreign.source[field]
                assert value != h.source[field]
                column = TaskPostSubmitRoutingManifest.__table__.columns[field]
                if getattr(column.type, "as_uuid", True) is False:
                    value = str(value)
                await _reject_changed_manifest(
                    h,
                    monkeypatch,
                    {field: value},
                    "routing (task is not current|assignment is not current|submission is not current|evaluation is not current|source .*mismatch)",
                )
            async with h.factory() as session, session.begin():
                await apply_outcome(session, h, None)


async def test_source_creation_time_is_database_owned(tmp_path, isolated_database_env, monkeypatch):
    import app.modules.tasks.post_submit_routing.outcome as outcome

    async with authorized_routing_source(
        tmp_path, isolated_database_env, human_review_required=True
    ) as h:
        original = outcome._manifest
        for supplied in (datetime(2000, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC), None):

            def changed(*args):
                row = original(*args)
                row.created_at = supplied
                return row

            with monkeypatch.context() as patch:
                patch.setattr(outcome, "_manifest", changed)
                async with h.factory() as session:
                    await session.begin()
                    before = await session.scalar(text("SELECT clock_timestamp()"))
                    result = await apply_outcome(session, h, None)
                    stored = await session.scalar(
                        select(TaskPostSubmitRoutingManifest.created_at).where(
                            TaskPostSubmitRoutingManifest.id == result.routing_manifest_id
                        )
                    )
                    after = await session.scalar(text("SELECT clock_timestamp()"))
                    assert before <= stored <= after and stored != supplied
                    await session.rollback()


async def test_source_is_immutable_and_preserves_locked_guide(tmp_path, isolated_database_env):
    async with authorized_routing_source(
        tmp_path, isolated_database_env, human_review_required=True
    ) as h:
        async with h.factory() as session, session.begin():
            result = await apply_outcome(session, h, None)
        async with h.factory() as session:
            before = await source_rows(session)
        successor = await activate_successor_guide(h)
        assert successor.command.target.proposal.guide_version == "v2"
        async with h.factory() as session:
            assert await source_rows(session) == before
        for sql in (
            "UPDATE public.task_post_submit_routing_manifests SET human_review_required=false",
            "DELETE FROM public.task_post_submit_routing_manifests",
            "TRUNCATE public.task_post_submit_routing_manifests CASCADE",
        ):
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match="source is immutable"):
                    async with session.begin():
                        await session.execute(text(sql))
        async with h.factory() as session:
            assert await source_rows(session) == before
        async with h.factory() as session, session.begin():
            assert await apply_outcome(session, h, None) == result.model_copy(update={"replayed": True})
