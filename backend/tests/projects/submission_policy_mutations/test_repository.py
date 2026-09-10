"""SQL-port query and classification proof; real contention remains in PostgreSQL."""

from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.projects import submission_policy_mutation_service as module
from app.modules.projects.submission_policy_mutation_repository import (
    SubmissionPolicyMutationReplayRepository,
)
from projects.submission_policy_mutations import rows


@pytest.fixture
def repo_case():
    facts = rows.replay_facts()
    values = asdict(facts)
    del values["resource_context"]
    values["resource_context_json"] = facts.resource_context.model_dump(mode="json")
    values["resource_context_digest"] = module.authorization_resource_digest(facts.resource_context)
    record = SimpleNamespace(
        id=rows.OPERATION,
        status="pending",
        **values,
        service_identity=None,
        setup_run_id=None,
        setup_task_id=None,
        correlation_id=None,
        response_json=None,
        committed_policy_id=None,
        committed_at=None,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None), get=AsyncMock(return_value=record)
    )
    repository = SubmissionPolicyMutationReplayRepository(session)

    async def find_operation(operation_id):
        return record if operation_id == record.operation_id else None

    repository.find_by_operation = AsyncMock(side_effect=find_operation)
    repository._find_namespace = AsyncMock(
        side_effect=AssertionError("exact operation must not use namespace fallback")
    )
    return SimpleNamespace(session=session, repository=repository, record=record, values=values)


@pytest.mark.parametrize("status,expected", [("pending", "pending"), ("committed", "replayed")])
async def test_reservation_classifies_existing_exact_row(repo_case, status, expected):
    case = repo_case
    case.record.status = status
    if status == "committed":
        case.record.response_json = {"id": str(rows.POLICY)}
        case.record.committed_policy_id = str(rows.POLICY)
        case.record.committed_at = rows.NOW
    assert await case.repository.reserve(**case.values) == (expected, case.record)
    case.repository.find_by_operation.assert_awaited_once_with(case.record.operation_id)
    case.repository._find_namespace.assert_not_awaited()
    case.session.get.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_digest", "sha256:" + "c" * 64),
        ("idempotency_key", rows.OPERATION),
        ("action_id", "project.submission_artifact_policy.update"),
    ],
)
async def test_reservation_rejects_changed_operation_facts(repo_case, field, value):
    values = {**repo_case.values, field: value}
    assert await repo_case.repository.reserve(**values) == ("mismatch", repo_case.record)
    repo_case.repository.find_by_operation.assert_awaited_once_with(values["operation_id"])
    repo_case.repository._find_namespace.assert_not_awaited()
    repo_case.session.get.assert_not_awaited()


async def test_reservation_rejects_different_operation_in_human_namespace(repo_case):
    case = repo_case
    original = rows.replay_facts()
    operation, link = UUID(int=99), UUID(int=100)
    digest = "sha256:" + "e" * 64
    # A new identity link changes operation custody, not the actor/key namespace.
    facts = replace(
        original,
        operation_id=operation,
        identity_link_id=str(link),
        request_digest=digest,
        resource_context=original.resource_context.model_copy(
            update={"operation_id": operation, "request_digest": digest}
        ),
    )
    # Use the unchanged validator to establish admissible input, not an expected
    # SQL/result oracle. Lookup selectors and mismatch below remain independent.
    values = module.SubmissionPolicyMutationService._replay_values(facts)
    selectors = {
        name: values[name]
        for name in (
            "actor_profile_id",
            "idempotency_key",
        )
    }

    async def find_namespace(**actual):
        assert actual == selectors
        return case.record

    case.repository._find_namespace.side_effect = find_namespace
    lookups = MagicMock()
    lookups.attach_mock(case.repository.find_by_operation, "operation")
    lookups.attach_mock(case.repository._find_namespace, "namespace")
    assert await case.repository.reserve(**values) == ("mismatch", case.record)
    assert lookups.mock_calls == [
        call.operation(values["operation_id"]),
        call.namespace(**selectors),
    ]
    case.session.get.assert_not_awaited()


async def test_reservation_insert_binds_exact_values(repo_case):
    case = repo_case
    case.session.scalar.return_value = rows.OPERATION
    assert await case.repository.reserve(**case.values) == ("claimed", case.record)
    case.repository.find_by_operation.assert_not_awaited()
    case.repository._find_namespace.assert_not_awaited()
    case.session.get.assert_awaited_once_with(
        module.SubmissionPolicyMutationIdempotencyRecord, rows.OPERATION
    )
    compiled = case.session.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
    assert {key: value for key, value in compiled.params.items() if key != "id"} == {
        **case.values,
        "status": "pending",
        "service_identity": None,
        "setup_run_id": None,
        "setup_task_id": None,
        "correlation_id": None,
    }
    assert str(compiled).endswith(
        "ON CONFLICT DO NOTHING RETURNING submission_policy_mutation_idempotency_records.id"
    )


def predicates(statement):
    compiled = statement.whereclause.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def expected_predicate(field, value):
    column = f"submission_policy_mutation_idempotency_records.{field}"
    if value is None:
        return f"{column} IS NULL"
    return f"{column} = %({field}_1)s" + ("::UUID" if isinstance(value, UUID) else "")


async def test_namespace_query_binds_exact_human_selectors(repo_case):
    case = repo_case
    await SubmissionPolicyMutationReplayRepository._find_namespace(
        case.repository,
        actor_profile_id=str(rows.ACTOR),
        idempotency_key=rows.KEY,
    )
    sql, params = predicates(case.session.scalar.await_args.args[0])
    assert sql == " AND ".join(
        [
            expected_predicate("actor_profile_id", str(rows.ACTOR)),
            expected_predicate("service_identity", None),
            expected_predicate("idempotency_key", rows.KEY),
        ]
    )
    assert params == {"actor_profile_id_1": str(rows.ACTOR), "idempotency_key_1": rows.KEY}


@pytest.mark.parametrize(
    "field", ["service_identity", "setup_run_id", "setup_task_id", "correlation_id"]
)
async def test_human_reservation_cannot_adopt_retained_service_custody(repo_case, field):
    setattr(repo_case.record, field, "retained-service-custody")
    assert await repo_case.repository.reserve(**repo_case.values) == ("mismatch", repo_case.record)


async def test_operation_lookup_uses_exact_operation_predicate(repo_case):
    repo_case.session.scalar.return_value = repo_case.record
    result = await SubmissionPolicyMutationReplayRepository.find_by_operation(
        repo_case.repository, rows.OPERATION
    )
    assert result is repo_case.record
    sql, params = predicates(repo_case.session.scalar.await_args.args[0])
    assert (
        sql
        == "submission_policy_mutation_idempotency_records.operation_id = %(operation_id_1)s::UUID"
    )
    assert params == {"operation_id_1": rows.OPERATION}


@pytest.mark.parametrize("matched", [False, True])
async def test_completion_requires_exact_pending_row(repo_case, matched):
    case = repo_case
    values = {
        key: value
        for key, value in case.values.items()
        if key
        not in {
            "project_id",
            "guide_id",
            "source_snapshot_id",
            "policy_id",
            "resource_context_json",
        }
    }
    case.session.scalar.return_value = rows.OPERATION if matched else None
    call = case.repository.complete(
        **values, response_json={"id": str(rows.POLICY)}, committed_policy_id=str(rows.POLICY)
    )
    if matched:
        assert await call is None
    else:
        with pytest.raises(module.ProjectRepositoryIntegrityError, match="invalid.*completion"):
            await call
    sql, params = predicates(case.session.scalar.await_args.args[0])
    fields = {
        "operation_id": values["operation_id"],
        **values,
        "status": "pending",
        "service_identity": None,
        "setup_run_id": None,
        "setup_task_id": None,
        "correlation_id": None,
    }
    assert sorted(sql.split(" AND ")) == sorted(
        expected_predicate(field, value) for field, value in fields.items()
    )
    assert params == {f"{field}_1": value for field, value in fields.items() if value is not None}
