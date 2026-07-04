from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

LEGACY_EVALUATION_STATUS = "auto_checking"
EVALUATION_PENDING_STATUS = "evaluation_pending"


def test_alembic_upgrade_and_downgrade(isolated_database_env: str, migration_lock) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    with migration_lock():
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        command.downgrade(config, "base")


def test_post_submit_policy_upgrade_leaves_legacy_rows_fail_closed(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0008 does not create fake post-submit policy authority for legacy rows."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    legacy_project_id = str(uuid4())
    legacy_guide_id = str(uuid4())
    legacy_policy_id = str(uuid4())
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0007_task_locked_context")
            asyncio.run(
                _seed_legacy_post_submit_policy(
                    isolated_database_env,
                    legacy_project_id,
                    legacy_guide_id,
                    legacy_policy_id,
                )
            )
            command.upgrade(config, "0008_post_submit_checker_policy")
            policy_hash = asyncio.run(
                _fetch_legacy_post_submit_policy_hash(isolated_database_env, legacy_policy_id)
            )
        finally:
            command.downgrade(config, "base")

    assert policy_hash is None


def test_post_submit_policy_upgrade_blocks_legacy_runtime_rows(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0008 fails clearly when runtime rows cannot gain trusted provenance."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    ids = {name: str(uuid4()) for name in ("project", "guide", "policy", "task", "submission", "run")}
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0007_task_locked_context")
            asyncio.run(_seed_legacy_runtime_rows(isolated_database_env, ids))

            with pytest.raises(RuntimeError, match="cannot infer locked post-submit"):
                command.upgrade(config, "0008_post_submit_checker_policy")

            columns_exist = asyncio.run(
                _post_submit_lock_columns_exist(isolated_database_env, "submissions")
            )
        finally:
            command.downgrade(config, "base")

    assert columns_exist is False


def test_evaluation_pending_status_migration_rewrites_task_and_audit_rows(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0009 backfills persisted post-submission evaluation statuses."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    ids = {name: str(uuid4()) for name in ("project", "policy", "task", "audit_start", "audit_done")}
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0008_post_submit_checker_policy")
            asyncio.run(_seed_legacy_evaluation_status_rows(isolated_database_env, ids))

            command.upgrade(config, "0009_evaluation_pending_status")
            upgraded = asyncio.run(_fetch_status_migration_rows(isolated_database_env, ids))
            command.downgrade(config, "0008_post_submit_checker_policy")
            downgraded = asyncio.run(_fetch_status_migration_rows(isolated_database_env, ids))
        finally:
            command.downgrade(config, "base")

    assert upgraded == {
        "task_status": EVALUATION_PENDING_STATUS,
        "audit_start_to_status": EVALUATION_PENDING_STATUS,
        "audit_done_from_status": EVALUATION_PENDING_STATUS,
    }
    assert downgraded == {
        "task_status": LEGACY_EVALUATION_STATUS,
        "audit_start_to_status": LEGACY_EVALUATION_STATUS,
        "audit_done_from_status": LEGACY_EVALUATION_STATUS,
    }


async def _seed_legacy_post_submit_policy(
    database_url: str,
    project_id: str,
    guide_id: str,
    policy_id: str,
) -> None:
    """Seed a valid 0007 checker policy row before post-submit hashes exist."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into projects (
                        id,
                        name,
                        slug,
                        status,
                        base_amount,
                        currency
                    )
                    values (
                        :project_id,
                        'Legacy policy project',
                        'legacy-policy-project',
                        'draft',
                        25.00,
                        'USD'
                    )
                    """
                ),
                {"project_id": project_id},
            )
            await connection.execute(
                text(
                    """
                    insert into project_guides (
                        id,
                        project_id,
                        version,
                        status,
                        content_markdown,
                        required_task_fields,
                        required_submission_fields,
                        required_skills,
                        difficulty_scale,
                        estimated_time_policy,
                        common_rejection_reasons,
                        created_by
                    )
                    values (
                        :guide_id,
                        :project_id,
                        'v1',
                        'draft',
                        '# Legacy guide',
                        '[]'::json,
                        '[]'::json,
                        '[]'::json,
                        '{}'::json,
                        '{}'::json,
                        '[]'::json,
                        'legacy-test'
                    )
                    """
                ),
                {"guide_id": guide_id, "project_id": project_id},
            )
            await connection.execute(
                text(
                    """
                    insert into checker_policies (
                        id,
                        project_id,
                        guide_version,
                        required_checkers,
                        warning_checkers,
                        blocking_severities
                    )
                    values (
                        :policy_id,
                        :project_id,
                        'v1',
                        '["check_policy_context_present"]'::json,
                        '[]'::json,
                        '["high"]'::json
                    )
                    """
                ),
                {"policy_id": policy_id, "project_id": project_id},
            )
    finally:
        await engine.dispose()


async def _seed_legacy_evaluation_status_rows(database_url: str, ids: dict[str, str]) -> None:
    """Seed post-0008 rows carrying the old persisted evaluation status."""
    engine = create_async_engine(database_url)
    params = {
        **ids,
        "project_id": ids["project"],
        "policy_id": ids["policy"],
        "task_id": ids["task"],
        "guide_id": str(uuid4()),
        "legacy_status": LEGACY_EVALUATION_STATUS,
    }
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into projects (
                        id,
                        name,
                        slug,
                        status,
                        base_amount,
                        currency
                    )
                    values (
                        :project_id,
                        'Evaluation pending migration project',
                        'evaluation-pending-migration-project',
                        'draft',
                        25.00,
                        'USD'
                    )
                    """
                ),
                params,
            )
            await connection.execute(
                text(
                    """
                    insert into project_guides (
                        id,
                        project_id,
                        version,
                        status,
                        content_markdown,
                        required_task_fields,
                        required_submission_fields,
                        required_skills,
                        difficulty_scale,
                        estimated_time_policy,
                        common_rejection_reasons,
                        created_by
                    )
                    values (
                        :guide_id,
                        :project_id,
                        'v1',
                        'active',
                        '# Evaluation pending migration guide',
                        '[]'::json,
                        '[]'::json,
                        '[]'::json,
                        '{}'::json,
                        '{}'::json,
                        '[]'::json,
                        'migration-test'
                    )
                    """
                ),
                params,
            )
            await connection.execute(
                text(
                    """
                    insert into checker_policies (
                        id,
                        project_id,
                        guide_version,
                        required_checkers,
                        warning_checkers,
                        blocking_severities,
                        policy_hash,
                        policy_body
                    )
                    values (
                        :policy_id,
                        :project_id,
                        'v1',
                        '["check_policy_context_present"]'::json,
                        '[]'::json,
                        '["high"]'::json,
                        'sha256:0000000000000000000000000000000000000000000000000000000000000000',
                        '{}'::json
                    )
                    """
                ),
                params,
            )
            await connection.execute(
                text(
                    """
                    insert into workstream_tasks (
                        id,
                        project_id,
                        locked_post_submit_checker_policy_id,
                        locked_post_submit_checker_policy_version,
                        locked_post_submit_checker_policy_hash,
                        locked_post_submit_checker_policy_body,
                        source_type,
                        title,
                        description,
                        skill_tags,
                        status,
                        required_files,
                        required_evidence,
                        created_by
                    )
                    values (
                        :task_id,
                        :project_id,
                        :policy_id,
                        'v1',
                        'sha256:0000000000000000000000000000000000000000000000000000000000000000',
                        '{}'::json,
                        'manual',
                        'Evaluation pending migration task',
                        'Task waiting in the old persisted evaluation status.',
                        '[]'::json,
                        :legacy_status,
                        '[]'::json,
                        '[]'::json,
                        'migration-test'
                    )
                    """
                ),
                params,
            )
            await connection.execute(
                text(
                    """
                    insert into audit_events (
                        id,
                        entity_type,
                        entity_id,
                        event_type,
                        from_status,
                        to_status,
                        actor_id,
                        external_subject,
                        external_issuer,
                        actor_roles,
                        claim_snapshot,
                        auth_source,
                        is_dev_auth,
                        event_payload
                    )
                    values
                    (
                        :audit_start,
                        'task',
                        :task_id,
                        'pre_review_gate_started',
                        'submitted',
                        :legacy_status,
                        'migration-test',
                        'migration-test',
                        'flow-test',
                        '["project_manager"]'::json,
                        '{}'::json,
                        'dev_mock',
                        true,
                        '{}'::json
                    ),
                    (
                        :audit_done,
                        'task',
                        :task_id,
                        'pre_review_gate_passed',
                        :legacy_status,
                        'review_pending',
                        'migration-test',
                        'migration-test',
                        'flow-test',
                        '["project_manager"]'::json,
                        '{}'::json,
                        'dev_mock',
                        true,
                        '{}'::json
                    )
                    """
                ),
                params,
            )
    finally:
        await engine.dispose()


async def _fetch_status_migration_rows(
    database_url: str,
    ids: dict[str, str],
) -> dict[str, str | None]:
    """Return status values touched by the 0009 status migration."""
    engine = create_async_engine(database_url)
    params = {
        **ids,
        "task_id": ids["task"],
    }
    try:
        async with engine.begin() as connection:
            task_status = await connection.scalar(
                text("select status from workstream_tasks where id = :task_id"),
                params,
            )
            audit_start_to_status = await connection.scalar(
                text("select to_status from audit_events where id = :audit_start"),
                ids,
            )
            audit_done_from_status = await connection.scalar(
                text("select from_status from audit_events where id = :audit_done"),
                ids,
            )
            return {
                "task_status": task_status,
                "audit_start_to_status": audit_start_to_status,
                "audit_done_from_status": audit_done_from_status,
            }
    finally:
        await engine.dispose()


async def _seed_legacy_runtime_rows(database_url: str, ids: dict[str, str]) -> None:
    """Seed 0007 runtime rows that cannot be trusted under 0008 provenance."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into projects (
                        id,
                        name,
                        slug,
                        status,
                        base_amount,
                        currency
                    )
                    values (
                        :project_id,
                        'Legacy runtime project',
                        'legacy-runtime-project',
                        'draft',
                        25.00,
                        'USD'
                    )
                    """
                ),
                {"project_id": ids["project"]},
            )
            await connection.execute(
                text(
                    """
                    insert into project_guides (
                        id,
                        project_id,
                        version,
                        status,
                        content_markdown,
                        required_task_fields,
                        required_submission_fields,
                        required_skills,
                        difficulty_scale,
                        estimated_time_policy,
                        common_rejection_reasons,
                        created_by
                    )
                    values (
                        :guide_id,
                        :project_id,
                        'v1',
                        'active',
                        '# Legacy runtime guide',
                        '[]'::json,
                        '[]'::json,
                        '[]'::json,
                        '{}'::json,
                        '{}'::json,
                        '[]'::json,
                        'legacy-test'
                    )
                    """
                ),
                {"guide_id": ids["guide"], "project_id": ids["project"]},
            )
            await _seed_legacy_policies(connection, ids["project"], ids["policy"])
            await connection.execute(
                text(
                    """
                    insert into workstream_tasks (
                        id,
                        project_id,
                        locked_guide_version,
                        locked_checker_policy_version,
                        locked_review_policy_version,
                        locked_revision_policy_version,
                        locked_payment_policy_version,
                        source_type,
                        title,
                        description,
                        skill_tags,
                        status,
                        required_files,
                        required_evidence,
                        created_by
                    )
                    values (
                        :task_id,
                        :project_id,
                        'v1',
                        'v1',
                        'v1',
                        'v1',
                        'v1',
                        'manual',
                        'Legacy runtime task',
                        'Already in progress before 0008.',
                        '[]'::json,
                        'in_progress',
                        '[]'::json,
                        '[]'::json,
                        'legacy-test'
                    )
                    """
                ),
                {"task_id": ids["task"], "project_id": ids["project"]},
            )
            await connection.execute(
                text(
                    """
                    insert into submissions (
                        id,
                        task_id,
                        worker_id,
                        version,
                        status,
                        summary,
                        package_hash,
                        artifact_hash_manifest,
                        worker_attestation,
                        locked_guide_version,
                        locked_checker_policy_version,
                        locked_review_policy_version,
                        locked_revision_policy_version,
                        locked_payment_policy_version
                    )
                    values (
                        :submission_id,
                        :task_id,
                        'legacy-worker',
                        1,
                        'submitted',
                        'Legacy submitted packet',
                        'sha256:legacy-package',
                        '[]'::json,
                        'legacy attestation',
                        'v1',
                        'v1',
                        'v1',
                        'v1',
                        'v1'
                    )
                    """
                ),
                {"submission_id": ids["submission"], "task_id": ids["task"]},
            )
            await connection.execute(
                text(
                    """
                    insert into checker_runs (
                        id,
                        task_id,
                        submission_id,
                        submission_version,
                        trigger_source,
                        status,
                        routing_recommendation,
                        outcome_source,
                        triggered_by,
                        triggered_by_subject,
                        triggered_by_issuer,
                        trigger_auth_source,
                        attempt_number,
                        is_current_for_submission,
                        locked_guide_version,
                        locked_checker_policy_version,
                        locked_review_policy_version,
                        locked_revision_policy_version,
                        locked_payment_policy_version,
                        package_hash,
                        artifact_hash_manifest,
                        artifact_manifest_hash,
                        passed_count,
                        warning_count,
                        failed_count,
                        blocking_count
                    )
                    values (
                        :run_id,
                        :task_id,
                        :submission_id,
                        1,
                        'submission_lock',
                        'completed',
                        'allow_review',
                        'auto_checker',
                        'legacy-test',
                        'legacy-test',
                        'flow-legacy',
                        'flow',
                        1,
                        true,
                        'v1',
                        'v1',
                        'v1',
                        'v1',
                        'v1',
                        'sha256:legacy-package',
                        '[]'::json,
                        'sha256:legacy-manifest',
                        1,
                        0,
                        0,
                        0
                    )
                    """
                ),
                {
                    "run_id": ids["run"],
                    "task_id": ids["task"],
                    "submission_id": ids["submission"],
                },
            )
    finally:
        await engine.dispose()


async def _seed_legacy_policies(connection, project_id: str, checker_policy_id: str) -> None:
    """Seed v0.1 guide policies required by locked task foreign keys."""
    await connection.execute(
        text(
            """
            insert into checker_policies (
                id,
                project_id,
                guide_version,
                required_checkers,
                warning_checkers,
                blocking_severities
            )
            values (
                :checker_policy_id,
                :project_id,
                'v1',
                '["check_policy_context_present"]'::json,
                '[]'::json,
                '["high"]'::json
            )
            """
        ),
        {"checker_policy_id": checker_policy_id, "project_id": project_id},
    )
    await connection.execute(
        text(
            """
            insert into review_policies (
                id,
                project_id,
                guide_version,
                requires_second_review,
                allowed_decisions,
                minimum_finding_fields
            )
            values (
                :review_policy_id,
                :project_id,
                'v1',
                false,
                '["accept", "needs_revision", "reject"]'::json,
                '[]'::json
            )
            """
        ),
        {"review_policy_id": str(uuid4()), "project_id": project_id},
    )
    await connection.execute(
        text(
            """
            insert into revision_policies (
                id,
                project_id,
                guide_version,
                max_revision_rounds,
                revision_deadline_hours,
                auto_reject_after_limit,
                allowed_resubmission_states
            )
            values (
                :revision_policy_id,
                :project_id,
                'v1',
                7,
                48,
                true,
                '["needs_revision"]'::json
            )
            """
        ),
        {"revision_policy_id": str(uuid4()), "project_id": project_id},
    )
    await connection.execute(
        text(
            """
            insert into payment_policies (
                id,
                project_id,
                guide_version,
                base_amount,
                currency,
                payout_type
            )
            values (
                :payment_policy_id,
                :project_id,
                'v1',
                25.00,
                'USD',
                'fixed'
            )
            """
        ),
        {"payment_policy_id": str(uuid4()), "project_id": project_id},
    )


async def _post_submit_lock_columns_exist(database_url: str, table_name: str) -> bool:
    """Return whether a post-submit lock column was added to a table."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            count = await connection.scalar(
                text(
                    """
                    select count(*)
                    from information_schema.columns
                    where table_name = :table_name
                      and column_name = 'locked_post_submit_checker_policy_id'
                    """
                ),
                {"table_name": table_name},
            )
            return bool(count)
    finally:
        await engine.dispose()


async def _fetch_legacy_post_submit_policy_hash(database_url: str, policy_id: str) -> str | None:
    """Return the post-submit policy hash created by the 0008 migration, if any."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            return await connection.scalar(
                text("select policy_hash from checker_policies where id = :policy_id"),
                {"policy_id": policy_id},
            )
    finally:
        await engine.dispose()
