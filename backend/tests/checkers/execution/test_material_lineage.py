"""Canonical ART membership is enforced at commit, including retained failed runs."""

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError

from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.checkers.post_submit_contracts import make_post_submit_result
from app.modules.outbox.models import OutboxEvent
from tests.post_submit_materialization_helpers import material_fixture
from .support import live_executor, reserve
from .test_concurrency import final_facts
from .material_storage_helpers import write_terminal


async def terminal_facts(h, lease, outcome):
    facts = await final_facts(h, lease)
    if outcome == "infrastructure_failed":
        body = facts.result.model_dump(exclude={"result_digest"})
        body.update(outcome=outcome, member_results=(), infrastructure_failure_code="implementation_unavailable")
        facts = facts.model_copy(update={"result": make_post_submit_result(**body)})
    return facts


@pytest.mark.parametrize("outcome", ["completed", "infrastructure_failed"])
async def test_foreign_canonical_material_is_rejected_at_commit(
    tmp_path, isolated_database_env, outcome
):
    async with material_fixture(tmp_path / "own", isolated_database_env) as h:
        async with material_fixture(
            tmp_path / "foreign",
            isolated_database_env,
            storage_settings=h.settings,
            provision_services=False,
        ) as foreign:
            await reserve(h)
            lease, _ = await live_executor(h)._claim(h.request)
            facts = await terminal_facts(h, lease, outcome)
            canonical = facts.material.model_dump(mode="json")
            substitutions = {
                "admission_id": str(foreign.created.admission_id),
                "replica_id": str(foreign.replica_id),
                "semantic_manifest_sha256": foreign.manifest.sha256,
                "submission_version": str(canonical["submission_version"]),
                "byte_count": str(canonical["byte_count"]),
                "unexpected": "untrusted extra material",

            }
            async with h.factory() as session:
                before_events = await session.scalar(select(func.count()).select_from(OutboxEvent))
                before = (await session.get(CheckerRun, str(facts.result.attempt_id))).finalize_evidence_id
            for field, value in substitutions.items():
                assert canonical.get(field) != value
                async with h.factory() as session:
                    await write_terminal(session, facts, canonical | {field: value},
                                         authorized_facts=facts if field in {"submission_version", "byte_count", "unexpected"} else None)
                    # Force this deferred guard before receipt validation so its
                    # rejection cannot be substituted by a different constraint.
                    with pytest.raises(IntegrityError, match="checker material canonical ART lineage mismatch"):
                        await session.execute(text("SET CONSTRAINTS public.checker_material_lineage IMMEDIATE"))
                    await session.rollback()
                async with h.factory() as session:
                    run = await session.get(CheckerRun, str(facts.result.attempt_id))
                    assert run.status == "running" and run.result_json is None and run.material_custody is None
                    assert run.finalize_evidence_id == before and run.completion_event_id is None
                    assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
                    assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == before_events
            async with h.factory() as session, session.begin():
                await write_terminal(session, facts, canonical)
            async with h.factory() as session:
                stored = await session.get(CheckerRun, str(facts.result.attempt_id))
                assert stored.status == outcome and stored.material_custody == canonical


@pytest.mark.parametrize("outcome", ["completed", "infrastructure_failed"])
@pytest.mark.parametrize("shadow", ["checker_runs", "art_lineage"])
async def test_temporary_tables_cannot_replace_canonical_material(
    tmp_path,
    isolated_database_env,
    outcome,
    shadow,
):
    from sqlalchemy import text

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        lease, _ = await live_executor(h)._claim(h.request)
        facts = await terminal_facts(h, lease, outcome)
        canonical = facts.material.model_dump(mode="json")
        digest = canonical["semantic_manifest_sha256"]
        forged_digest = digest[:-1] + ("0" if digest[-1] != "0" else "1")
        forged = canonical | {"semantic_manifest_sha256": forged_digest}

        async def stage(session, material):
            await write_terminal(session, facts, material)
            # Validate the other deferred constraints against the real rows first.
            # No guard is disabled: only 0009 remains deferred when the hostile
            # session changes its name-resolution environment before COMMIT.
            await session.execute(text(
                "SET CONSTRAINTS public.checker_terminal_custody, "
                "public.checker_member_terminal_custody IMMEDIATE"
            ))
            if shadow == "checker_runs":
                await session.execute(text(
                    "CREATE TEMP TABLE checker_runs ON COMMIT DROP AS "
                    "SELECT * FROM public.checker_runs WITH NO DATA"
                ))
            else:
                for table in (
                    "submissions", "workstream_tasks", "submission_bundle_admissions",
                    "artifact_bindings", "artifact_contents",
                ):
                    await session.execute(text(
                        f"CREATE TEMP TABLE {table} ON COMMIT DROP AS SELECT * FROM public.{table}"
                    ))
                await session.execute(text(
                    "UPDATE pg_temp.submission_bundle_admissions "
                    "SET semantic_manifest_sha256=:digest WHERE id=:id"
                ), {"digest": forged_digest, "id": facts.material.admission_id})
            await session.execute(text("SET LOCAL search_path = pg_temp, public, pg_catalog"))

        async with h.factory() as session:
            before_events = await session.scalar(select(func.count()).select_from(OutboxEvent))
        async with h.factory() as session:
            await stage(session, forged)
            with pytest.raises(IntegrityError, match="checker material canonical ART lineage mismatch"):
                await session.commit()
            await session.rollback()
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(facts.result.attempt_id))
            assert run.status == "running" and run.material_custody is None
            assert run.result_json is None and run.finalize_evidence_id is None
            assert run.completion_event_id is None
            assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == before_events
        # The same hostile environment must not prevent valid canonical custody.
        async with h.factory() as session:
            await stage(session, canonical)
            await session.commit()
        async with h.factory() as session:
            row = (await session.execute(text(
                "SELECT status, material_custody FROM public.checker_runs WHERE id=:id"
            ), {"id": facts.result.attempt_id})).one()
            assert row.status == outcome and row.material_custody == canonical


async def test_canonical_validator_binds_numeric_version_argument(tmp_path, isolated_database_env):
    from sqlalchemy import text

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        lease, _ = await live_executor(h)._claim(h.request)
        facts = await final_facts(h, lease)
        parameters = {
            "project": h.request.project_id,
            "task": h.request.task_id,
            "submission": h.request.submission_id,
            "version": facts.material.submission_version,
            "material": facts.material.model_dump_json(),
        }
        query = text(
            "SELECT public.art_submission_material_matches("
            ":project, :task, :submission, :version, CAST(:material AS jsonb))"
        )
        async with h.factory() as session:
            assert await session.scalar(query, parameters) is True
            # Preserve every canonical material fact; only the scalar input differs.
            wrong_version = parameters["version"] + 1
            assert await session.scalar(query, parameters | {"version": wrong_version}) is False
            # The JSON version is independently bound to the same canonical row.
            wrong_material = facts.material.model_copy(update={"submission_version": wrong_version})
            assert await session.scalar(query, parameters | {
                "material": wrong_material.model_dump_json(),
            }) is False
