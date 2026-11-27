"""Direct-SQL custody and a faulty classifier cannot bypass the database owner."""

from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.checkers.execution_repository import request_text
from tests.checkers.post_submit.support import change_request
from tests.post_submit_materialization_helpers import material_fixture
from .support import reserve, live_executor
from .test_concurrency import final_facts
from tests.checkers.external.support import post_registry_spec


async def test_failed_external_image_history_uses_normalized_result_status(
    tmp_path, isolated_database_env,
):
    from app.modules.checkers.history import CheckerHistoryRepository

    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec()
    ) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = await final_facts(h, lease, verdict="failed")
        await executor.finalize(facts)
        async with h.factory() as session:
            for manager in (False, True):
                rows, more = await CheckerHistoryRepository(session).read(
                    submission_id=h.request.submission_id,
                    task_id=h.request.task_id,
                    manager=manager,
                )
                assert not more and len(rows) == 1
                member, = rows[0].results
                assert member.checker_name == h.request.policy.entries[0].requirement_id
                assert member.status == "failed" and member.severity == "error"
                assert member.worker_message == "Post evidence failed."
                assert member.worker_suggested_fix is None
                if manager:
                    assert member.blocks_review is True
                    assert member.message == member.worker_message


@pytest.mark.parametrize("duplicate", ["request", "generation"])
async def test_duplicate_request_and_generation_rejected(
    tmp_path, isolated_database_env, duplicate
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        reservation = await reserve(h)
        async with h.factory() as session:
            original = await session.get(CheckerRun, str(reservation.attempt_id))
            values = {
                column.name: getattr(original, column.name)
                for column in CheckerRun.__table__.columns
            }
            changed = change_request(
                h.request,
                **(
                    {"evaluation_generation": 2}
                    if duplicate == "request"
                    else {"evaluation_request_id": new_record_id()}
                ),
            )
            values.update(
                id=str(new_record_id()),
                result_id=str(new_record_id()),
                evaluation_request_id=str(changed.evaluation_request_id),
                evaluation_generation=changed.evaluation_generation,
                request_json=request_text(changed),
                request_digest=changed.request_sha256,
            )
            session.add(CheckerRun(**values))
            constraint = (
                "uq_checker_runs_request_phase"
                if duplicate == "request"
                else "uq_checker_runs_generation"
            )
            with pytest.raises(IntegrityError, match=constraint):
                await session.flush()
            await session.rollback()


async def test_terminal_member_and_routing_custody(tmp_path, isolated_database_env, monkeypatch):
    import app.modules.checkers.execution as execution

    async with material_fixture(tmp_path, isolated_database_env,
                                post_submit_registry_spec=post_registry_spec()) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = await final_facts(h, lease, verdict="failed")
        blocked = facts.result
        canonical = execution.classify_result
        assert canonical(h.request, blocked, human_review_required=True).routing == "needs_revision"
        monkeypatch.setattr(
            execution,
            "classify_result",
            lambda request, result, **policy: replace(
                canonical(request, result, **policy), routing="allow_review",
            ),
        )
        with pytest.raises(IntegrityError, match="completed custody or routing invalid"):
            await executor.finalize(facts)
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            assert run.status == "running" and run.result_json is None
            assert list(await session.scalars(select(CheckerResult.id))) == []
        monkeypatch.setattr(execution, "classify_result", canonical)
        assert await executor.finalize(facts) == blocked


@pytest.mark.parametrize(
    "field",
    ["request_json", "evaluation_request_id", "evaluation_generation", "result_id", "project_id"],
)
async def test_execution_custody_rejects_mutation(tmp_path, isolated_database_env, field):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        receipt = await reserve(h)
        async with h.factory() as session:
            original = await session.get(CheckerRun, str(receipt.attempt_id))
            before = getattr(original, field)
            replacement = (
                request_text(change_request(h.request, evaluation_request_id=new_record_id()))
                if field == "request_json"
                else 2
                if field == "evaluation_generation"
                else str(new_record_id())
            )
            setattr(original, field, replacement)
            with pytest.raises(IntegrityError, match="checker run custody is immutable") as refused:
                await session.flush()
            assert refused.value.orig.sqlstate == "23514"
            await session.rollback()
            assert getattr(await session.get(CheckerRun, str(receipt.attempt_id)), field) == before


async def test_unfinished_members_cannot_commit(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env,
                                post_submit_registry_spec=post_registry_spec()) as h:
        await reserve(h)
        lease, _ = await live_executor(h)._claim(h.request)
        async with h.factory() as session:
            from app.modules.checkers.execution_repository import ExecutionRepository

            repo = ExecutionRepository(session)
            run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            await repo.write_members(run, (await final_facts(h, lease)).result)
            # An insert must itself schedule the parent terminal constraint; this
            # cannot depend on the caller remembering to update the parent.
            with pytest.raises(IntegrityError, match="partial checker members"):
                await session.commit()


async def test_member_shape_and_complete_set_enforced_in_database(
    tmp_path, isolated_database_env, monkeypatch
):
    from sqlalchemy import insert
    from app.modules.checkers.execution_repository import ExecutionRepository

    async with material_fixture(tmp_path, isolated_database_env,
                                post_submit_registry_spec=post_registry_spec()) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = await final_facts(h, lease)
        first = facts.result.execution.external_members[0]
        values = dict(
            id=str(new_record_id()),
            checker_run_id=str(lease.reservation.attempt_id),
            task_id=str(h.request.task_id),
            submission_id=str(h.request.submission_id),
            member_order=0,
            checker_name=first.requirement_id,
            definition_version=first.result.schema_version,
            implementation_version=first.registry_entry_digest,
            status=first.result.verdict,
            code="passed",
            failure_category="none",
            severity="info",
            counters=[],
        )
        invalid = [
            ({"checker_name": "unselected_checker"}, "differs from selected definition"),
            (
                {"member_order": len(facts.result.execution.external_members)},
                "differs from selected definition",
            ),
            ({"status": "passed", "code": "unexpected_pass_code"}, "differs from selected definition"),
            ({"counters": [{"metric": 1}]}, "differs from selected definition"),
            ({"counters": {"metric": 1}}, "differs from selected definition"),
            ({"task_id": str(new_record_id())}, "fk_checker_results_run_ownership"),
        ]
        async with h.factory() as session:
            for changes, message in invalid:
                # Core INSERT bypasses service validation; each tuple changes one
                # otherwise valid selected member and reaches its specific guard.
                with pytest.raises(IntegrityError, match=message):
                    await session.execute(insert(CheckerResult).values(**(values | changes)))
                await session.rollback()
            await session.execute(insert(CheckerResult).values(**values))
            await session.rollback()
        original = ExecutionRepository.write_members

        async def omit_last(repo, run, result):
            await original(
                repo, run, result.model_copy(update={"execution": replace(result.execution, required_external_count=0, external_members=())})
            )

        monkeypatch.setattr(ExecutionRepository, "write_members", omit_last)
        with pytest.raises(IntegrityError, match="terminal members differ"):
            await executor.finalize(facts)
        async with h.factory() as session:
            assert list(await session.scalars(select(CheckerResult.id))) == []
            assert (
                await session.get(CheckerRun, str(lease.reservation.attempt_id))
            ).status == "running"
        monkeypatch.setattr(ExecutionRepository, "write_members", original)
        assert await executor.finalize(facts) == facts.result


async def test_consistently_short_result_cannot_omit_selected_policy_member(
    tmp_path, isolated_database_env, monkeypatch
):
    from app.modules.checkers.execution_results import ResultClassification
    from app.modules.checkers.api.selected_post_submit import make_selected_post_submit_result
    from app.modules.outbox.models import OutboxEvent
    from app.modules.checkers.api.execution import COMPLETION_EVENT
    from sqlalchemy import func
    from sqlalchemy import text
    from . import material_storage_helpers

    async with material_fixture(tmp_path, isolated_database_env,
                                post_submit_registry_spec=post_registry_spec()) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        valid = await final_facts(h, lease)
        assert len(valid.result.execution.external_members) == 1
        assert all(member.result.verdict == "passed" for member in valid.result.execution.external_members)
        body = valid.result.model_dump(exclude={"result_digest"})
        body["execution"] = replace(valid.result.execution, required_external_count=0, external_members=())
        short = make_selected_post_submit_result(**body)
        facts = valid.model_copy(update={"result": short})
        # Simulate a faulty validator/compiler accepting a self-consistent short
        # result. Persisted members, counts, result digest and event all agree;
        # only comparison with the locked policy's selected set can reject it.
        canonical = material_storage_helpers.classify_result

        def faulty_classifier(request, result, **policy):
            assert request == h.request and result == short
            return ResultClassification("allow_review", len(short.execution.external_members), 0, 0, 0)

        monkeypatch.setattr(material_storage_helpers, "classify_result", faulty_classifier)
        # This SQL-owner control deliberately simulates an application accepting
        # only this counterfeit, while its AUTH digest binds the same counterfeit
        # facts. A mismatched valid AUTH receipt must not mask policy-set custody.
        from app.modules.checkers.api.selected_post_submit import SelectedPostSubmissionEvaluationResult
        validate_request = SelectedPostSubmissionEvaluationResult.validate_request

        def faulty_request_validator(result, request):
            if result == short and request == h.request:
                return None
            return validate_request(result, request)

        monkeypatch.setattr(SelectedPostSubmissionEvaluationResult, "validate_request", faulty_request_validator)
        async with h.factory() as session:
            await material_storage_helpers.write_terminal(
                session, facts, facts.material.model_dump(mode="json"),
            )
            with pytest.raises(IntegrityError, match="checker terminal selected policy differs") as refused:
                await session.execute(text("SET CONSTRAINTS public.checker_terminal_custody IMMEDIATE"))
            assert refused.value.orig.sqlstate == "23514"
            await session.rollback()
        async with h.factory() as session:
            assert (
                await session.get(CheckerRun, str(lease.reservation.attempt_id))
            ).status == "running"
            assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.event_type == COMPLETION_EVENT)
                )
                == 0
            )
        monkeypatch.setattr(material_storage_helpers, "classify_result", canonical)
        assert await executor.finalize(valid) == valid.result


@pytest.mark.parametrize("substitution", ["registry_entry_id", "image_digest"])
async def test_same_count_result_cannot_substitute_locked_image_identity(
    tmp_path, isolated_database_env, monkeypatch, substitution
):
    from app.modules.checkers.api.external import make_external_checker_execution_result
    from app.modules.checkers.api.selected_post_submit import (
        SelectedPostSubmissionEvaluationResult,
        make_selected_post_submit_result,
    )
    from sqlalchemy import func, text
    from . import material_storage_helpers

    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec()
    ) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        valid = await final_facts(h, lease)
        member, = valid.result.execution.external_members
        if substitution == "registry_entry_id":
            foreign_id = new_record_id()
            normalized_body = member.result.model_dump(exclude={"result_digest"})
            normalized_body["registry_entry_id"] = foreign_id
            changed = replace(
                member, registry_entry_id=foreign_id,
                result=make_external_checker_execution_result(**normalized_body),
            )
        else:
            foreign_image = "sha256:" + (
                "c" if member.isolation.platform_manifest_digest != "sha256:" + "c" * 64 else "d"
            ) * 64
            changed = replace(member, isolation=replace(
                member.isolation, platform_manifest_digest=foreign_image,
            ))
        body = valid.result.model_dump(exclude={"result_digest"})
        body["execution"] = replace(valid.result.execution, external_members=(changed,))
        counterfeit = make_selected_post_submit_result(**body)
        assert counterfeit.execution.required_external_count == 1
        assert counterfeit.execution.policy_sha256 == h.request.policy.policy_sha256
        with pytest.raises(ValueError, match="selected POST result request mismatch"):
            counterfeit.validate_request(h.request)
        facts = valid.model_copy(update={"result": counterfeit})
        canonical = SelectedPostSubmissionEvaluationResult.validate_request

        def faulty_validator(result, request):
            if result == counterfeit and request == h.request:
                return None
            return canonical(result, request)

        monkeypatch.setattr(SelectedPostSubmissionEvaluationResult, "validate_request", faulty_validator)
        async with h.factory() as session:
            before_audits = await session.scalar(text("SELECT count(*) FROM public.audit_events"))
            await material_storage_helpers.write_terminal(
                session, facts, facts.material.model_dump(mode="json"),
            )
            with pytest.raises(IntegrityError, match="checker terminal selected policy differs") as denied:
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            assert denied.value.orig.sqlstate == "23514"
            await session.rollback()
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            assert run.status == "running" and run.result_json is None
            assert run.finalize_evidence_id is None and run.completion_event_id is None
            assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
            assert await session.scalar(text("SELECT count(*) FROM public.audit_events")) == before_audits
            assert await session.scalar(text(
                "SELECT count(*) FROM public.outbox_events "
                "WHERE event_type='PostSubmissionEvaluationCompleted'"
            )) == 0
        monkeypatch.setattr(SelectedPostSubmissionEvaluationResult, "validate_request", canonical)
        assert await executor.finalize(valid) == valid.result


async def test_infrastructure_failure_code_is_closed_in_database(tmp_path, isolated_database_env):
    import json
    from sqlalchemy import update, func, text
    from app.core.hashing import canonical_json_hash
    from app.modules.checkers.api.selected_post_submit import make_selected_post_submit_result

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        lease, _ = await live_executor(h)._claim(h.request)
        result = make_selected_post_submit_result(
            request_id=h.request.evaluation_request_id, request_digest=h.request.request_sha256,
            attempt_id=lease.reservation.attempt_id, result_id=lease.reservation.result_id,
            evaluation_generation=h.request.evaluation_generation, outcome="infrastructure_failed",
            execution=None, infrastructure_failure_code="material_unavailable",
        )
        body = result.model_dump(mode="json", exclude={"result_digest"})
        async with h.factory() as session:
            for code, custody in (
                ("invented_failure", None),
                # Valid ART lineage isolates the terminal-shape guard: material
                # must be absent when the declared failure is material_unavailable.
                (
                    "material_unavailable",
                    (await final_facts(h, lease)).material.model_dump(mode="json"),
                ),
            ):
                candidate = body | {"infrastructure_failure_code": code}
                statement = update(CheckerRun).where(CheckerRun.id == str(result.attempt_id)).values(
                    status="infrastructure_failed", failure_code=code, material_custody=custody,
                    result_json=json.dumps(candidate, sort_keys=True, separators=(",", ":")),
                    result_digest=canonical_json_hash(candidate),
                    finalize_evidence_id=str(new_record_id()), completed_at=func.clock_timestamp(),
                    outcome_source="auto_checker", routing_recommendation="not_evaluated",
                )
                with pytest.raises(IntegrityError, match="infrastructure terminal shape invalid"):
                    await session.execute(statement)
                    await session.execute(text("SET CONSTRAINTS public.checker_terminal_custody IMMEDIATE"))
                await session.rollback()
                run = await session.get(CheckerRun, str(result.attempt_id))
                assert run.status == "running" and run.result_json is None
        valid = (await final_facts(h, lease)).model_copy(
            update={"result": result, "material": None, "input_materialization_evidence_id": None}
        )
        assert await live_executor(h).finalize(valid) == result
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(result.attempt_id))
            assert run.failure_code == "material_unavailable" and run.status == "infrastructure_failed"
            assert run.material_custody is None


async def test_unfenced_successor_cannot_poison_next_generation(tmp_path, isolated_database_env):
    from sqlalchemy import insert
    from app.modules.checkers.models import CheckerSubmissionFence

    async with material_fixture(tmp_path, isolated_database_env) as h:
        first = await reserve(h)
        successor = change_request(
            h.request, evaluation_request_id=new_record_id(), evaluation_generation=2,
        )
        orphan_id = str(new_record_id())
        async with h.factory() as session:
            original = await session.get(CheckerRun, str(first.attempt_id))
            values = {column.name: getattr(original, column.name) for column in CheckerRun.__table__.columns}
            values.update(
                id=orphan_id, result_id=str(new_record_id()),
                evaluation_request_id=str(successor.evaluation_request_id),
                evaluation_generation=2, request_json=request_text(successor),
                request_digest=successor.request_sha256,
                supersedes_checker_run_id=str(first.attempt_id),
            )
            # Every immediate ownership/shape/uniqueness guard accepts this row.
            # Only the deferred exact fence check must reject its commit.
            await session.execute(insert(CheckerRun).values(**values))
            with pytest.raises(IntegrityError, match="checker run requires currentness custody"):
                await session.commit()
            await session.rollback()
        async with h.factory() as session:
            assert await session.get(CheckerRun, orphan_id) is None
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(first.attempt_id)
            assert list(await session.scalars(select(CheckerRun.id))) == [str(first.attempt_id)]
        second = await reserve(h, successor)
        assert second.evaluation_generation == 2
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(second.attempt_id)
            run = await session.get(CheckerRun, str(second.attempt_id))
            assert run.supersedes_checker_run_id == str(first.attempt_id)
        assert await reserve(h, successor) == second
        assert await reserve(h) == first
