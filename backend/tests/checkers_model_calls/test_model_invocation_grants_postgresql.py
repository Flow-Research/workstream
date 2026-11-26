"""Real PostgreSQL proof for bounded multi-call checker model invocation grants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import runpy
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.authorization.domain.model_usage import (
    GRANT,
    ModelCallGrantAuthorityFacts,
    checker_model_call_resource,
)
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.model_usage.api import (
    ModelActionEvidence,
    ModelCallExecutionFacts,
    ModelCallUsage,
    ModelCallUnavailable,
    ModelPaidSlotKey,
    PreparedModelCallAttempt,
    model_action_digest,
)
from app.modules.model_usage.grants import ModelInvocationGrants
from app.modules.model_usage.models import ModelUsageBudgetAccount, ModelUsageEffect
from tests.checkers_model_calls.model_usage_pg_support import (
    DatabaseFacts,
    model_database as _ledger_database,
)
from tests.checkers_model_calls.model_usage_boundary_support import BoundaryPorts
from tests.checkers_model_calls.test_model_call_transactions_postgresql import (
    evidence,
    execution,
    provision,
    service,
    sha,
    slot,
)


ledger_database_fixture = _ledger_database


class _CaptureOperations:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


@dataclass(frozen=True)
class GrantDatabase:
    facts: DatabaseFacts
    execution: ModelCallExecutionFacts
    slot: ModelPaidSlotKey
    prepared: PreparedModelCallAttempt
    prepared_attempt_id: UUID
    prepared_request_sha256: str


class GrantBoundaries:
    """Persist exact fake AUTH receipts while PostgreSQL owns all ancestry checks."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        evidence_id: UUID | None = None,
        action: str = "checker.model_call.grant",
        corrupt_digest: bool = False,
    ) -> None:
        self._session = session
        self._evidence_id = evidence_id
        self._action = action
        self._corrupt_digest = corrupt_digest

    async def authorize_grant(
        self,
        execution_facts: ModelCallExecutionFacts,
        paid_slot: ModelPaidSlotKey,
        external_request_digest: str,
        token_hash: str,
    ) -> ModelActionEvidence:
        facts = {
            "execution": execution_facts.model_dump(mode="json"),
            "slot": paid_slot.model_dump(mode="json"),
            "external_request_digest": external_request_digest,
            "token_hash": token_hash,
        }
        evidence = ModelActionEvidence(
            evidence_id=self._evidence_id or new_record_id(),
            facts_digest=model_action_digest("grant", facts),
        )
        actor_id = new_record_id()
        resource = checker_model_call_resource(
            GRANT,
            ModelCallGrantAuthorityFacts(
                execution=execution_facts,
                slot=paid_slot,
                external_request_digest=external_request_digest,
                token_hash=token_hash,
            ),
        )
        await self._session.execute(
            text(
                "insert into actor_profiles(id,actor_kind,status,service_identity) "
                "values (:id,'service','active','workstream.checker.post_submit')"
            ),
            {"id": actor_id},
        )
        await self._session.execute(
            text(
                "insert into audit_events(id,event_domain,event_type,actor_ref_kind,actor_id,"
                "action_id,permission_id,project_id,resource_type,resource_id,"
                "denial_code,after_facts) values "
                "(:id,'authority','SensitiveAuthorizationAllowed','actor_profile',:actor,"
                ":action,'checker.model_call.grant',null,null,null,"
                "null,cast(:after as jsonb)) "
                "on conflict(id) do nothing"
            ),
            {
                "id": evidence.evidence_id,
                "actor": str(actor_id),
                "action": self._action,
                "after": json.dumps(
                    {
                        "allowed": True,
                        "resource_context_digest": (
                            sha("foreign grant authority")
                            if self._corrupt_digest
                            else authorization_resource_digest(resource)
                        ),
                    }
                ),
            },
        )
        return evidence

    async def require_current(
        self,
        facts: ModelCallExecutionFacts,
        __: ModelPaidSlotKey,
    ):
        return facts.worker_lease_expires_at


def _isolated(statement: str, schema: str) -> str:
    return statement.replace("public.", f'"{schema}".').replace(
        "pg_catalog,public,pg_temp", f'pg_catalog,"{schema}",pg_temp'
    )


@pytest.fixture
async def grant_database(ledger_database_fixture: DatabaseFacts) -> GrantDatabase:
    ledger_database = ledger_database_fixture
    async with ledger_database.engine.connect() as connection:
        schema = str(await connection.scalar(text("select current_schema()")))
    migration = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "alembic/versions/0062_model_usage.py")
    )
    capture = _CaptureOperations()
    migration["_upgrade_invocation_grants"].__globals__["op"] = capture
    migration["_upgrade_invocation_grants"]()
    async with ledger_database.engine.begin() as connection:
        for statement in capture.statements:
            await connection.execute(text(_isolated(statement, schema)))

    profile = await provision(
        ledger_database,
        BoundaryPorts(),
        limit=100_000,
        profile_changes={
            "maximum_calls": 3,
            "maximum_total_request_bytes": 30_000,
            "maximum_total_response_bytes": 90_000,
            "maximum_total_input_tokens": 300,
            "maximum_total_output_tokens": 150,
        },
    )
    current = execution(ledger_database)
    paid_slot = slot(ledger_database, profile, "model_judge")
    request_sha256 = sha("prepared request")
    async with AsyncSession(ledger_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            prepared = await service(session, BoundaryPorts()).prepare_attempt(
                current,
                paid_slot,
                registry_entry_id=ledger_database.registry_entry_id,
                request_sha256=request_sha256,
            )

    policy_sha256 = sha("locked post policy")
    policy = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [
            {
                "requirement_id": paid_slot.requirement_id,
                "stage": "post_submit",
                "registry": {
                    "registry_entry_id": str(ledger_database.registry_entry_id),
                    "entry_digest": paid_slot.registry_entry_digest,
                },
                "configuration": {
                    "model_profile_id": str(paid_slot.profile_id),
                    "model_profile_version": paid_slot.profile_version,
                    "model_profile_digest": paid_slot.profile_digest,
                },
                "configuration_sha256": paid_slot.configuration_sha256,
            }
        ],
        "policy_sha256": policy_sha256,
    }
    async with ledger_database.engine.begin() as connection:
        await connection.execute(
            text(
                "insert into checker_runs(id,project_id,task_id,submission_id,submission_version,"
                "evaluation_request_id,evaluation_generation,request_json,worker_lease_id,"
                "worker_lease_generation,worker_lease_expires_at,status,phase,"
                "selected_post_submit_policy_sha256,selected_post_submit_policy_body,"
                "locked_post_submit_checker_policy_hash) values "
                "(:id,:project,:task,:submission,:version,:request,:generation,:request_json,"
                ":lease,:lease_generation,:expires,'running','post_submission',:policy_sha,"
                "cast(:policy as jsonb),:policy_sha)"
            ),
            {
                "id": current.checker_run_id,
                "project": current.project_id,
                "task": current.task_id,
                "submission": current.submission_id,
                "version": current.submission_version,
                "request": current.evaluation_request_id,
                "generation": current.evaluation_generation,
                "request_json": json.dumps({"assignment_id": str(current.assignment_id)}),
                "lease": current.worker_lease_id,
                "lease_generation": current.worker_lease_generation,
                "expires": current.worker_lease_expires_at,
                "policy_sha": policy_sha256,
                "policy": json.dumps(policy),
            },
        )
    return GrantDatabase(
        ledger_database,
        current,
        paid_slot,
        prepared,
        prepared.attempt_id,
        request_sha256,
    )


async def _issue(
    database: GrantDatabase,
    *,
    boundaries: GrantBoundaries,
    session: AsyncSession,
):
    return await ModelInvocationGrants(
        session,
        authority=boundaries,
        current=boundaries,
    ).issue(
        database.execution,
        database.slot,
        sha("external checker request"),
        registry_entry_id=database.facts.registry_entry_id,
    )


async def test_grant_round_trip_binds_exact_calls_and_becomes_immutable(
    grant_database: GrantDatabase,
) -> None:
    async with AsyncSession(grant_database.facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            boundaries = GrantBoundaries(session)
            grant = await _issue(
                grant_database,
                boundaries=boundaries,
                session=session,
            )
            owner = ModelInvocationGrants(
                session,
                authority=boundaries,
                current=boundaries,
            )
            facts = await owner.resolve(grant.grant_id, grant.binding_digest)
            await owner.consume_prepared(
                facts,
                call_index=0,
                request_sha256=grant_database.prepared_request_sha256,
                prepared_attempt_id=grant_database.prepared_attempt_id,
            )
            # An exact transport replay is idempotent and does not mint another binding.
            await owner.consume_prepared(
                facts,
                call_index=0,
                request_sha256=grant_database.prepared_request_sha256,
                prepared_attempt_id=grant_database.prepared_attempt_id,
            )
            row = (
                (
                    await session.execute(
                        text(
                            "select c.request_sha256,c.attempt_id,c.bound_at,"
                            "g.issued_at,g.expires_at,g.token_hash,g.id as grant_id from "
                            "checker_model_invocation_grant_calls c join "
                            "checker_model_invocation_grants g on g.id=c.grant_id"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert row.request_sha256 == grant_database.prepared_request_sha256
            assert row.attempt_id == grant_database.prepared_attempt_id
            assert row.issued_at < row.bound_at < row.expires_at
            assert row.token_hash != grant.grant_id

            second_request = sha("second prepared request")
            second_slot = grant_database.slot.model_copy(update={"slot_index": 1})
            second_attempt = await service(session, BoundaryPorts()).prepare_attempt(
                grant_database.execution,
                second_slot,
                registry_entry_id=grant_database.facts.registry_entry_id,
                request_sha256=second_request,
            )
            await owner.consume_prepared(
                facts,
                call_index=1,
                request_sha256=second_request,
                prepared_attempt_id=second_attempt.attempt_id,
            )
            assert (
                await session.scalar(
                    text(
                        "select count(*) from checker_model_invocation_grant_calls "
                        "where grant_id=:grant"
                    ),
                    {"grant": row.grant_id},
                )
                == 2
            )

    for mutation in (
        "update checker_model_invocation_grants set external_request_digest="
        "'sha256:" + "d" * 64 + "'",
        "delete from checker_model_invocation_grants",
        "truncate checker_model_invocation_grants",
        "update checker_model_invocation_grant_calls set request_sha256='sha256:" + "e" * 64 + "'",
        "delete from checker_model_invocation_grant_calls",
        "truncate checker_model_invocation_grant_calls",
    ):
        async with AsyncSession(grant_database.facts.engine) as session:
            with pytest.raises(DBAPIError):
                async with session.begin():
                    await session.execute(text(mutation))


async def _consume_grant(owner, grant, database: GrantDatabase) -> None:
    facts = await owner.resolve(grant.grant_id, grant.binding_digest)
    await owner.consume_prepared(
        facts,
        call_index=0,
        request_sha256=database.prepared_request_sha256,
        prepared_attempt_id=database.prepared_attempt_id,
    )


async def _attached_grants(session: AsyncSession, database: GrantDatabase) -> int:
    count = await session.scalar(
        text(
            "select count(*) from checker_model_invocation_grant_calls "
            "where attempt_id=:attempt"
        ),
        {"attempt": database.prepared_attempt_id},
    )
    assert count is not None
    return count


async def _renew_and_consume(session, owner, boundaries, database: GrantDatabase):
    renewed = database.execution.model_copy(
        update={
            "worker_lease_id": new_record_id(),
            "worker_lease_generation": database.execution.worker_lease_generation + 1,
            "worker_lease_expires_at": datetime.now(UTC) + timedelta(minutes=10),
        }
    )
    await session.execute(
        text(
            "update checker_runs set worker_lease_id=:lease,"
            "worker_lease_generation=:generation,worker_lease_expires_at=:expires "
            "where id=:run"
        ),
        {
            "lease": renewed.worker_lease_id,
            "generation": renewed.worker_lease_generation,
            "expires": renewed.worker_lease_expires_at,
            "run": renewed.checker_run_id,
        },
    )
    renewed_database = GrantDatabase(
        database.facts,
        renewed,
        database.slot,
        database.prepared,
        database.prepared_attempt_id,
        database.prepared_request_sha256,
    )
    grant = await _issue(renewed_database, boundaries=boundaries, session=session)
    await _consume_grant(owner, grant, database)
    return renewed


async def _settle_renewed_effect(session, database: GrantDatabase, renewed) -> None:
    dispatched = await service(session, BoundaryPorts()).reserve_dispatch(
        renewed,
        database.prepared,
        evidence("renewed-dispatch-request", database.prepared_request_sha256),
    )
    completed = await service(session, BoundaryPorts()).complete_known_failure(
        dispatched.effect,
        provider_response_id="resp_renewed_dispatch",
        provider_model_snapshot="gpt-example-2026-10-01",
        response_evidence=evidence(
            "renewed-dispatch-response", sha("renewed-dispatch-response")
        ),
        usage=ModelCallUsage(
            input_tokens=22,
            cached_input_tokens=2,
            output_tokens=3,
            reasoning_tokens=1,
        ),
    )
    effect = await session.get(ModelUsageEffect, str(completed.attempt_id))
    account = await session.get(ModelUsageBudgetAccount, str(database.facts.project_id))
    assert effect.prepared_execution_facts == database.execution.model_dump(mode="json")
    assert effect.dispatch_execution_facts == renewed.model_dump(mode="json")
    assert account.lifetime_reserved_nanodollars == 0
    assert account.lifetime_settled_nanodollars == completed.settled_nanodollars


async def _attach_successor(session, owner, boundaries, database, renewed) -> None:
    successor = renewed.model_copy(
        update={
            "checker_run_id": new_record_id(),
            "evaluation_request_id": new_record_id(),
            "evaluation_generation": renewed.evaluation_generation + 1,
            "worker_lease_id": new_record_id(),
        }
    )
    await session.execute(
        text(
            "insert into checker_runs select :run,task_id,submission_id,submission_version,"
            "project_id,:request,phase,:generation,request_json,:lease,"
            "worker_lease_generation,worker_lease_expires_at,status,"
            "selected_post_submit_policy_sha256,selected_post_submit_policy_body,"
            "locked_post_submit_checker_policy_hash from checker_runs where id=:source"
        ),
        {
            "run": successor.checker_run_id,
            "request": successor.evaluation_request_id,
            "generation": successor.evaluation_generation,
            "lease": successor.worker_lease_id,
            "source": database.execution.checker_run_id,
        },
    )
    successor_database = GrantDatabase(
        database.facts,
        successor,
        database.slot,
        database.prepared,
        database.prepared_attempt_id,
        database.prepared_request_sha256,
    )
    grant = await _issue(successor_database, boundaries=boundaries, session=session)
    await _consume_grant(owner, grant, database)


async def test_renewed_and_successor_grants_reattach_the_same_paid_effect(
    grant_database: GrantDatabase,
) -> None:
    """Lease renewal and an authorized retry run reuse one stable paid effect."""
    async with AsyncSession(grant_database.facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            boundaries = GrantBoundaries(session)
            owner = ModelInvocationGrants(session, authority=boundaries, current=boundaries)
            first = await _issue(grant_database, boundaries=boundaries, session=session)
            await _consume_grant(owner, first, grant_database)
            renewed = await _renew_and_consume(session, owner, boundaries, grant_database)
            assert await _attached_grants(session, grant_database) == 2
            await _settle_renewed_effect(session, grant_database, renewed)
            await _attach_successor(session, owner, boundaries, grant_database, renewed)
            assert await _attached_grants(session, grant_database) == 3


async def test_grant_rejects_reused_or_wrong_authority_and_stale_db_clock(
    grant_database: GrantDatabase,
) -> None:
    evidence_id = new_record_id()
    async with AsyncSession(grant_database.facts.engine) as session:
        async with session.begin():
            boundaries = GrantBoundaries(session, evidence_id=evidence_id)
            await _issue(grant_database, boundaries=boundaries, session=session)

    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session, evidence_id=evidence_id)
                await _issue(grant_database, boundaries=boundaries, session=session)

    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session, action="checker.model_call.dispatch")
                await _issue(grant_database, boundaries=boundaries, session=session)

    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session, corrupt_digest=True)
                await _issue(grant_database, boundaries=boundaries, session=session)

    expired = grant_database.execution.model_copy(
        update={"worker_lease_expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    async with grant_database.facts.engine.begin() as connection:
        await connection.execute(
            text("update checker_runs set worker_lease_expires_at=:expires where id=:id"),
            {"expires": expired.worker_lease_expires_at, "id": expired.checker_run_id},
        )
    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session)
                await ModelInvocationGrants(
                    session,
                    authority=boundaries,
                    current=boundaries,
                ).issue(
                    expired,
                    grant_database.slot,
                    sha("expired request"),
                    registry_entry_id=grant_database.facts.registry_entry_id,
                )


async def _reject_grant_scope_substitutions(database: GrantDatabase) -> None:
    foreign_registry = new_record_id()
    async with database.facts.engine.begin() as connection:
        await connection.execute(
            text(
                "insert into external_checker_registry_entries(id,entry_digest,phase) "
                "values (:id,:digest,'post_submit')"
            ),
            {"id": foreign_registry, "digest": database.slot.registry_entry_digest},
        )
    async with AsyncSession(database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session)
                await ModelInvocationGrants(
                    session, authority=boundaries, current=boundaries
                ).issue(
                    database.execution,
                    database.slot,
                    sha("foreign registry request"),
                    registry_entry_id=foreign_registry,
                )

    foreign_project = new_record_id()
    async with database.facts.engine.begin() as connection:
        await connection.execute(
            text("insert into projects(id) values (:id)"), {"id": foreign_project}
        )
    async with AsyncSession(database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session)
                await ModelInvocationGrants(
                    session, authority=boundaries, current=boundaries
                ).issue(
                    database.execution.model_copy(update={"project_id": foreign_project}),
                    database.slot.model_copy(update={"project_id": foreign_project}),
                    sha("foreign project request"),
                    registry_entry_id=database.facts.registry_entry_id,
                )

    async with database.facts.engine.begin() as connection:
        await connection.execute(
            text(
                "update checker_runs set selected_post_submit_policy_body="
                "jsonb_set(selected_post_submit_policy_body,"
                "'{entries,0,configuration_sha256}',to_jsonb(cast(:digest as text)))"
            ),
            {"digest": sha("substituted configuration")},
        )
    async with AsyncSession(database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session)
                await _issue(database, boundaries=boundaries, session=session)


async def test_grant_rejects_locked_binding_and_call_substitution_or_gaps(
    grant_database: GrantDatabase,
) -> None:
    async with AsyncSession(grant_database.facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            boundaries = GrantBoundaries(session)
            grant = await _issue(grant_database, boundaries=boundaries, session=session)
            facts = await ModelInvocationGrants(
                session,
                authority=boundaries,
                current=boundaries,
            ).resolve(grant.grant_id, grant.binding_digest)

    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "update checker_model_invocation_grants "
                        "set external_request_digest=:request"
                    ),
                    {"request": sha("immutable grant facts")},
                )

    async with AsyncSession(grant_database.facts.engine) as session:
        async with session.begin():
            owner = ModelInvocationGrants(
                session,
                authority=GrantBoundaries(session),
                current=GrantBoundaries(session),
            )
            await owner.consume_prepared(
                facts,
                call_index=0,
                request_sha256=grant_database.prepared_request_sha256,
                prepared_attempt_id=grant_database.prepared_attempt_id,
            )

    # A call index is an immutable replay key, not permission to replace its request.
    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(ModelCallUnavailable):
            async with session.begin():
                await ModelInvocationGrants(
                    session,
                    authority=GrantBoundaries(session),
                    current=GrantBoundaries(session),
                ).consume_prepared(
                    facts,
                    call_index=0,
                    request_sha256=sha("substituted request"),
                    prepared_attempt_id=grant_database.prepared_attempt_id,
                )

    other_slot = grant_database.slot.model_copy(update={"slot_index": 1})
    other_request = sha("other prepared request")
    async with AsyncSession(grant_database.facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            other_attempt = await service(session, BoundaryPorts()).prepare_attempt(
                grant_database.execution,
                other_slot,
                registry_entry_id=grant_database.facts.registry_entry_id,
                request_sha256=other_request,
            )
    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                grant_id = await session.scalar(
                    text(
                        "select id from checker_model_invocation_grants "
                        "where token_hash=:token_hash"
                    ),
                    {"token_hash": facts.token_hash},
                )
                await session.execute(
                    text(
                        "insert into checker_model_invocation_grant_calls"
                        "(grant_id,call_index,attempt_id,request_sha256) "
                        "values (:grant,2,:attempt,:request)"
                    ),
                    {
                        "grant": grant_id,
                        "request": other_request,
                        "attempt": other_attempt.attempt_id,
                    },
                )

    await _reject_grant_scope_substitutions(grant_database)
    assert facts.slot == grant_database.slot


async def test_grant_trigger_locks_authority_then_task_then_checker_ancestry(
    grant_database: GrantDatabase,
) -> None:
    async with grant_database.facts.engine.connect() as connection:
        definition = await connection.scalar(
            text(
                "select pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n "
                "on n.oid=p.pronamespace where p.proname="
                "'guard_checker_model_invocation_grant' and n.nspname=current_schema()"
            )
        )
    insert_branch = definition.split("IF jsonb_typeof", maxsplit=1)[1]
    assert insert_branch.index("audit_events") < insert_branch.index("workstream_tasks")
    assert insert_branch.index("workstream_tasks") < insert_branch.index("checker_runs")
    assert insert_branch.index("checker_runs") < insert_branch.index("model_usage_profiles")
