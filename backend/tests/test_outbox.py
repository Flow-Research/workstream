from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
from pathlib import Path
import traceback
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.outbox.schemas import (
    OutboxAppendDisposition,
    OutboxAppendInput,
    OutboxIdempotencyConflict,
    OutboxInputError,
    OutboxPersistenceError,
)
from app.modules.outbox.repository import OutboxRepository
from app.modules.outbox.service import OutboxService
from tests.assertion_helpers import assert_secret_not_retained


def _alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return config


@pytest.fixture
def outbox_database_env(
    isolated_database_env: str,
    migration_lock,
) -> str:
    """Upgrade the isolated database to the exact shared-outbox head."""
    with migration_lock():
        command.upgrade(_alembic_config(), "head")
    return isolated_database_env


@pytest.fixture
async def outbox_factory(
    outbox_database_env: str,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], UUID]]:
    """Provide one project-scoped session factory and privileged local cleanup."""
    engine = create_async_engine(outbox_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    project_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into projects(id, name, slug, status) "
                "values (:id, 'Outbox test', :slug, 'active')"
            ),
            {"id": str(project_id), "slug": f"outbox-{project_id}"},
        )
    try:
        yield factory, project_id
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("alter table outbox_events disable trigger user"))
            await connection.execute(
                text("delete from outbox_events where project_id=:project_id"),
                {"project_id": str(project_id)},
            )
            await connection.execute(text("alter table outbox_events enable trigger user"))
            await connection.execute(
                text("delete from projects where id=:project_id"),
                {"project_id": str(project_id)},
            )
        await engine.dispose()


def _event(project_id: UUID, **changes: Any) -> OutboxAppendInput:
    values: dict[str, Any] = {
        "event_id": uuid4(),
        "event_type": "ContributionRecorded",
        "event_version": 1,
        "aggregate_type": "contribution_record",
        "aggregate_id": uuid4(),
        "project_id": project_id,
        "correlation_id": f"request:{uuid4()}",
        "causation_event_id": uuid4(),
        "idempotency_key": f"contribution:{uuid4()}:recorded:v1",
        "payload": {"contribution_record_id": str(uuid4()), "award_ids": []},
    }
    values.update(changes)
    return OutboxAppendInput(**values)


def _unsafe_event(project_id: UUID, payload: object) -> OutboxAppendInput:
    valid = _event(project_id)
    values = valid.model_dump()
    values["payload"] = payload
    return OutboxAppendInput.model_construct(**values)


def test_outbox_input_requires_closed_tokens_and_object_payload() -> None:
    project_id = uuid4()
    with pytest.raises(OutboxInputError, match="^outbox_invalid_input$"):
        _event(project_id, event_type="bad event")
    with pytest.raises(OutboxInputError, match="^outbox_invalid_input$"):
        _event(project_id, aggregate_type="BadAggregate")
    with pytest.raises(OutboxInputError, match="^outbox_invalid_input$"):
        _event(project_id, payload=[])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"Authorization": "Bearer secret"},
        {"access-token": "secret"},
        {"nested": {"refresh_token": "secret"}},
        {"api_key": "secret"},
        {"private_key": "secret"},
        {"client_secret": "secret"},
        {"provider_token": "secret"},
        {"session_token": "secret"},
        {"provider_credentials": "secret"},
        {"apikey": "secret"},
        {"privatekey": "secret"},
        {"clientsecret": "secret"},
        {"providertoken": "secret"},
        {"sessiontoken": "secret"},
        {"providercredential": "secret"},
        {"jwt": "secret"},
        {"passphrase": "secret"},
        {"providertokenvalue": "secret"},
        {"sessiontokendata": "secret"},
        {"clientsecretvalue": "secret"},
        {"providercredentialvalue": "secret"},
        {"passwordvalue": "secret"},
        {"jwtvalue": "secret"},
        {"keymaterial": "secret"},
        {"api_key_material": "secret"},
        {"private_key_material": "secret"},
        {"provider_key_value": "secret"},
        {"access_key_data": "secret"},
        {"encryption_key_payload": "secret"},
        {"signing_key_material": "secret"},
        {"ratio": 1.5},
        {"blob": b"secret"},
        {"huge_integer": 10**38},
        {"oversized": "x" * 16_385},
        {"BadKey": "value"},
    ],
)
async def test_outbox_invalid_payload_errors_never_echo_values(
    payload: object,
) -> None:
    service = OutboxService(cast(AsyncSession, None))
    with pytest.raises(OutboxInputError) as raised:
        await service.append(_unsafe_event(uuid4(), payload))
    assert str(raised.value) == "outbox_invalid_input"
    assert "secret" not in str(raised.value)


@pytest.mark.parametrize("key", ["hockey", "monkey", "turnkey"])
def test_outbox_allows_benign_words_ending_in_key_letters(key: str) -> None:
    """Keep ordinary generic payload names outside the credential-key policy."""
    value = _event(uuid4(), payload={key: "safe"})
    assert value.payload == {key: "safe"}


def test_outbox_normal_validation_detaches_rejected_secret_input() -> None:
    values = _event(uuid4()).model_dump()
    marker = f"private-marker-{uuid4()}"
    values["payload"] = {"authorization": marker}
    with pytest.raises(OutboxInputError, match="^outbox_invalid_input$") as raised:
        OutboxAppendInput(**values)
    rendered = "".join(traceback.format_exception(raised.value))
    assert marker not in rendered
    assert_secret_not_retained(
        raised.value,
        marker,
        traceback_module_prefixes=("app.modules.outbox",),
    )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


def test_outbox_all_validation_entry_points_detach_rejected_input() -> None:
    marker = f"private-marker-{uuid4()}"

    class ExplodingDict(dict[str, object]):
        def items(self):
            raise RuntimeError(marker)

    class ExplodingList(list[object]):
        def __iter__(self):
            raise RuntimeError(marker)

    class ExplodingString(str):
        def encode(self, *args: object, **kwargs: object):
            raise RuntimeError(marker)

    adapter = TypeAdapter(OutboxAppendInput)
    hostile_payloads = (
        {"nested": ExplodingDict({"value": "safe"})},
        {"nested": ExplodingList(["safe"])},
        {"nested": ExplodingString("safe")},
    )
    for payload in hostile_payloads:
        values = _event(uuid4()).model_dump()
        values["payload"] = payload
        calls = (
            lambda: OutboxAppendInput(**values),
            lambda: OutboxAppendInput.model_validate(values),
            lambda: OutboxAppendInput.model_validate_strings(values),
            lambda: adapter.validate_python(values),
        )
        for call in calls:
            with pytest.raises(
                OutboxInputError,
                match="^outbox_invalid_input$",
            ) as raised:
                call()
            assert_secret_not_retained(
                raised.value,
                marker,
                traceback_module_prefixes=("app.modules.outbox",),
            )
            assert raised.value.__context__ is None
            assert raised.value.__cause__ is None

    json_values = _event(uuid4()).model_dump(mode="json")
    json_values["payload"] = {"authorization": marker}
    document = json.dumps(json_values)
    for call in (
        lambda: OutboxAppendInput.model_validate_json(document),
        lambda: adapter.validate_json(document),
    ):
        with pytest.raises(OutboxInputError, match="^outbox_invalid_input$") as raised:
            call()
        assert_secret_not_retained(
            raised.value,
            marker,
            traceback_module_prefixes=("app.modules.outbox",),
        )


def test_outbox_rejects_hostile_top_level_payload_before_traversal() -> None:
    marker = "top-level-payload-override-must-not-run"
    calls: list[str] = []

    class ExplodingDict(dict[str, object]):
        def items(self):
            calls.append(marker)
            raise RuntimeError(marker)

    adapter = TypeAdapter(OutboxAppendInput)
    values = _event(uuid4()).model_dump()
    values["payload"] = ExplodingDict(value="safe")
    string_values = _event(uuid4()).model_dump(mode="json")
    string_values["event_version"] = str(string_values["event_version"])
    string_values["payload"] = ExplodingDict(value="safe")
    for call in (
        lambda: OutboxAppendInput(**values),
        lambda: OutboxAppendInput.model_validate(values),
        lambda: OutboxAppendInput.model_validate_strings(string_values),
        lambda: adapter.validate_python(values),
        lambda: adapter.validate_strings(string_values),
    ):
        with pytest.raises(OutboxInputError, match="^outbox_invalid_input$"):
            call()
    assert calls == []


@pytest.mark.asyncio
async def test_outbox_service_detaches_hostile_nested_container_failure() -> None:
    marker = f"private-marker-{uuid4()}"

    class ExplodingDict(dict[str, object]):
        def items(self):
            raise RuntimeError(marker)

    class ExplodingList(list[object]):
        def __iter__(self):
            raise RuntimeError(marker)

    class ExplodingString(str):
        def encode(self, *args: object, **kwargs: object):
            raise RuntimeError(marker)

    for payload in (
        {"nested": ExplodingDict({"value": "safe"})},
        {"nested": ExplodingList(["safe"])},
        {"nested": ExplodingString("safe")},
    ):
        value = _unsafe_event(uuid4(), payload)
        with pytest.raises(OutboxInputError, match="^outbox_invalid_input$") as raised:
            await OutboxService(cast(AsyncSession, None)).append(value)
        assert_secret_not_retained(
            raised.value,
            marker,
            traceback_module_prefixes=("app.modules.outbox",),
        )
        assert raised.value.__context__ is None
        assert raised.value.__cause__ is None


def test_outbox_validation_entry_points_preserve_valid_modes() -> None:
    expected = _event(uuid4(), payload={"marker": "safe"})
    adapter = TypeAdapter(OutboxAppendInput)
    python_value = OutboxAppendInput.model_validate(expected.model_dump())
    json_value = OutboxAppendInput.model_validate_json(
        json.dumps(expected.model_dump(mode="json"))
    )
    strings = expected.model_dump(mode="json")
    strings["event_version"] = str(strings["event_version"])
    string_value = OutboxAppendInput.model_validate_strings(strings)
    adapter_python = adapter.validate_python(expected.model_dump())
    adapter_json = adapter.validate_json(json.dumps(expected.model_dump(mode="json")))
    adapter_strings = adapter.validate_strings(strings)
    assert all(
        value == expected
        for value in (
            python_value,
            json_value,
            string_value,
            adapter_python,
            adapter_json,
            adapter_strings,
        )
    )


@pytest.mark.asyncio
async def test_outbox_payload_depth_nodes_members_and_budget_are_bounded() -> None:
    project_id = uuid4()
    nested: dict[str, Any] = {}
    cursor = nested
    for _ in range(17):
        cursor["nested"] = {}
        cursor = cursor["nested"]
    cases = (
        nested,
        {"items": list(range(1025))},
        {f"key_{index}": index for index in range(1025)},
        {"items": [[index] for index in range(4096)]},
        {"one": "x" * 16_000, "two": "y" * 16_000, "three": "z" * 16_000},
    )
    for payload in cases:
        with pytest.raises(OutboxInputError, match="^outbox_invalid_input$"):
            await OutboxService(cast(AsyncSession, None)).append(
                _unsafe_event(project_id, payload)
            )


@pytest.mark.asyncio
async def test_outbox_append_flushes_pending_event_without_committing(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as session:
        async with session.begin():
            result = await OutboxService(session).append(value)
            row = (
                await session.execute(
                    text(
                        "select producer, aggregate_type, aggregate_id, payload, "
                        "payload_digest, delivery_state, attempt_count, claim_generation, "
                        "occurred_at, next_attempt_at from outbox_events where event_id=:id"
                    ),
                    {"id": value.event_id},
                )
            ).one()
            assert result.disposition is OutboxAppendDisposition.CREATED
            assert row.producer == "workstream"
            assert row.aggregate_type == value.aggregate_type
            assert row.aggregate_id == value.aggregate_id
            assert row.payload == value.payload
            assert row.payload_digest == result.payload_digest
            assert row.delivery_state == "pending"
            assert row.attempt_count == row.claim_generation == 0
            assert row.occurred_at == row.next_attempt_at == result.occurred_at


@pytest.mark.asyncio
async def test_outbox_insert_trigger_rejects_preforged_operational_state(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    event_id = uuid4()
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    "insert into outbox_events "
                    "(event_id,event_type,event_version,producer,aggregate_type,aggregate_id,"
                    "project_id,correlation_id,idempotency_key,payload,payload_digest,occurred_at,"
                    "delivery_state,attempt_count,next_attempt_at,claim_owner,claim_generation,"
                    "claimed_at,claim_expires_at,last_attempt_at,last_error_code,finalized_at,"
                    "archived_at) values "
                    "(:event_id,'ForgedProbe',1,'forged','forged_probe',:aggregate_id,:project_id,"
                    ":correlation_id,:idempotency_key,'{}'::jsonb,:digest,'2000-01-01Z',"
                    "'acknowledged',99,null,'forged:worker',99,'2000-01-01Z','2099-01-01Z',"
                    "'2000-01-01Z','FORGED','2000-01-01Z','2000-01-01Z')"
                ),
                {
                    "event_id": event_id,
                    "aggregate_id": uuid4(),
                    "project_id": str(project_id),
                    "correlation_id": f"forged:{event_id}",
                    "idempotency_key": f"forged:{event_id}:v1",
                    "digest": "sha256:" + ("0" * 64),
                },
            )
            row = (
                await session.execute(
                    text(
                        "select producer,occurred_at,delivery_state,attempt_count,"
                        "next_attempt_at,claim_owner,claim_generation,claimed_at,"
                        "claim_expires_at,last_attempt_at,last_error_code,finalized_at,archived_at "
                        "from outbox_events where event_id=:event_id"
                    ),
                    {"event_id": event_id},
                )
            ).one()
            assert row.producer == "workstream"
            assert row.occurred_at == row.next_attempt_at
            assert row.occurred_at.year >= 2026
            assert row.delivery_state == "pending"
            assert row.attempt_count == row.claim_generation == 0
            assert all(
                value is None
                for value in (
                    row.claim_owner,
                    row.claimed_at,
                    row.claim_expires_at,
                    row.last_attempt_at,
                    row.last_error_code,
                    row.finalized_at,
                    row.archived_at,
                )
            )


@pytest.mark.asyncio
async def test_outbox_caller_rollback_removes_flushed_event(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as session:
        transaction = await session.begin()
        await OutboxService(session).append(value)
        assert await session.scalar(
            text("select count(*) from outbox_events where event_id=:id"),
            {"id": value.event_id},
        ) == 1
        await transaction.rollback()
    async with factory() as observer:
        assert await observer.scalar(
            text("select count(*) from outbox_events where event_id=:id"),
            {"id": value.event_id},
        ) == 0


@pytest.mark.asyncio
async def test_outbox_post_reservation_failure_rolls_back_caller_transaction(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    original_reserve = OutboxRepository.reserve

    async def fail_after_reservation(
        repository: OutboxRepository,
        event: OutboxAppendInput,
        *,
        payload_digest: str,
    ) -> None:
        await original_reserve(repository, event, payload_digest=payload_digest)
        raise RuntimeError("injected_outbox_failure")

    monkeypatch.setattr(OutboxRepository, "reserve", fail_after_reservation)
    async with factory() as session:
        transaction = await session.begin()
        with pytest.raises(RuntimeError, match="^injected_outbox_failure$"):
            await OutboxService(session).append(value)
        await transaction.rollback()
    async with factory() as observer:
        assert await observer.scalar(
            text("select count(*) from outbox_events where event_id=:id"),
            {"id": value.event_id},
        ) == 0


@pytest.mark.asyncio
async def test_outbox_database_error_never_reflects_payload(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, _ = outbox_factory
    marker = f"private-marker-{uuid4()}"
    value = _event(uuid4(), payload={"private_marker": marker})
    async with factory() as session:
        transaction = await session.begin()
        with pytest.raises(
            OutboxPersistenceError,
            match="^outbox_persistence_failed$",
        ) as raised:
            await OutboxService(session).append(value)
        rendered = "".join(traceback.format_exception(raised.value))
        assert marker not in rendered
        assert_secret_not_retained(
            raised.value,
            marker,
            traceback_module_prefixes=("app.modules.outbox",),
        )
        assert raised.value.__context__ is None
        assert raised.value.__cause__ is None
        await transaction.rollback()


@pytest.mark.asyncio
async def test_outbox_snapshots_nested_payload_before_first_await(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id, payload={"nested": {"state": "before"}})
    reserve_started = asyncio.Event()
    release_reserve = asyncio.Event()
    original_reserve = OutboxRepository.reserve

    async def blocked_reserve(
        repository: OutboxRepository,
        event: OutboxAppendInput,
        *,
        payload_digest: str,
    ):
        reserve_started.set()
        await release_reserve.wait()
        return await original_reserve(repository, event, payload_digest=payload_digest)

    monkeypatch.setattr(OutboxRepository, "reserve", blocked_reserve)
    async with factory() as session:
        async with session.begin():
            append_task = asyncio.create_task(OutboxService(session).append(value))
            await reserve_started.wait()
            value.payload["nested"]["state"] = "after"
            release_reserve.set()
            result = await append_task
            row = (
                await session.execute(
                    text(
                        "select payload, payload_digest from outbox_events "
                        "where event_id=:event_id"
                    ),
                    {"event_id": value.event_id},
                )
            ).one()
    assert result.disposition is OutboxAppendDisposition.CREATED
    assert row.payload == {"nested": {"state": "before"}}
    assert row.payload_digest == result.payload_digest


@pytest.mark.asyncio
async def test_outbox_exact_replay_uses_canonical_payload_and_original_time(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(
        project_id,
        payload={"nested": {"second": 2, "first": 1}, "items": ["a", "b"]},
    )
    async with factory() as session:
        async with session.begin():
            created = await OutboxService(session).append(value)
    replay_payload = {"items": ["a", "b"], "nested": {"first": 1, "second": 2}}
    replay = OutboxAppendInput(**{**value.model_dump(), "payload": replay_payload})
    async with factory() as session:
        async with session.begin():
            result = await OutboxService(session).append(replay)
    assert result.disposition is OutboxAppendDisposition.REPLAYED
    assert result.event_id == created.event_id
    assert result.payload_digest == created.payload_digest
    assert result.occurred_at == created.occurred_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "event_id",
        "event_type",
        "event_version",
        "aggregate_type",
        "aggregate_id",
        "project_id",
        "correlation_id",
        "causation_event_id",
        "idempotency_key",
        "payload",
    ],
)
async def test_outbox_reused_identity_with_immutable_drift_conflicts(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
    field: str,
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as session:
        async with session.begin():
            await OutboxService(session).append(value)
    changes: dict[str, Any] = {
        "event_id": uuid4(),
        "event_type": "CompensationAwardCreated",
        "event_version": 2,
        "aggregate_type": "compensation_award",
        "aggregate_id": uuid4(),
        "project_id": uuid4(),
        "correlation_id": f"request:{uuid4()}",
        "causation_event_id": uuid4(),
        "idempotency_key": f"changed:{uuid4()}",
        "payload": {"contribution_record_id": str(uuid4()), "award_ids": []},
    }
    drift = OutboxAppendInput(**{**value.model_dump(), field: changes[field]})
    async with factory() as session:
        async with session.begin():
            with pytest.raises(
                OutboxIdempotencyConflict,
                match="^outbox_idempotency_conflict$",
            ):
                await OutboxService(session).append(drift)


@pytest.mark.asyncio
async def test_outbox_conflict_does_not_retain_stored_payload(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    marker = f"stored-conflict-{uuid4()}"
    value = _event(project_id, payload={"detail": marker})
    async with factory() as session:
        async with session.begin():
            await OutboxService(session).append(value)
    drift = OutboxAppendInput(
        **{**value.model_dump(), "payload": {"detail": "changed"}}
    )
    async with factory() as session:
        async with session.begin():
            with pytest.raises(
                OutboxIdempotencyConflict,
                match="^outbox_idempotency_conflict$",
            ) as raised:
                await OutboxService(session).append(drift)
            assert_secret_not_retained(
                raised.value,
                marker,
                traceback_module_prefixes=("app.modules.outbox",),
            )
            assert raised.value.__context__ is None
            assert raised.value.__cause__ is None


@pytest.mark.asyncio
async def test_outbox_split_event_and_idempotency_identities_conflict(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    first = _event(project_id)
    second = _event(project_id)
    async with factory() as session:
        async with session.begin():
            await OutboxService(session).append(first)
            await OutboxService(session).append(second)
    crossed = OutboxAppendInput(
        **{
            **first.model_dump(),
            "idempotency_key": second.idempotency_key,
        }
    )
    async with factory() as session:
        async with session.begin():
            with pytest.raises(OutboxIdempotencyConflict):
                await OutboxService(session).append(crossed)


async def _blocked_append(
    session: AsyncSession,
    value: OutboxAppendInput,
) -> tuple[OutboxAppendDisposition | None, Exception | None]:
    try:
        result = await OutboxService(session).append(value)
        return result.disposition, None
    except Exception as error:  # noqa: BLE001 - test returns exact typed race outcome
        return None, error


@pytest.mark.asyncio
async def test_outbox_duplicate_race_replays_after_first_reserver_commits(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as winner, factory() as contender:
        await winner.begin()
        await contender.begin()
        first = await OutboxService(winner).append(value)
        blocked = asyncio.create_task(_blocked_append(contender, value))
        await asyncio.sleep(0.05)
        assert not blocked.done()
        await winner.commit()
        disposition, error = await asyncio.wait_for(blocked, timeout=3)
        await contender.commit()
    assert first.disposition is OutboxAppendDisposition.CREATED
    assert disposition is OutboxAppendDisposition.REPLAYED
    assert error is None


@pytest.mark.asyncio
async def test_outbox_duplicate_race_creates_after_first_reserver_rolls_back(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as reserver, factory() as contender:
        await reserver.begin()
        await contender.begin()
        await OutboxService(reserver).append(value)
        blocked = asyncio.create_task(_blocked_append(contender, value))
        await asyncio.sleep(0.05)
        assert not blocked.done()
        await reserver.rollback()
        disposition, error = await asyncio.wait_for(blocked, timeout=3)
        await contender.commit()
    assert disposition is OutboxAppendDisposition.CREATED
    assert error is None


@pytest.mark.asyncio
async def test_outbox_changed_payload_race_conflicts_after_first_reserver_commits(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    changed = OutboxAppendInput(
        **{**value.model_dump(), "payload": {"contribution_record_id": str(uuid4())}}
    )
    async with factory() as winner, factory() as contender:
        await winner.begin()
        await contender.begin()
        await OutboxService(winner).append(value)
        blocked = asyncio.create_task(_blocked_append(contender, changed))
        await asyncio.sleep(0.05)
        assert not blocked.done()
        await winner.commit()
        disposition, error = await asyncio.wait_for(blocked, timeout=3)
        await contender.rollback()
    assert disposition is None
    assert isinstance(error, OutboxIdempotencyConflict)


@pytest.mark.asyncio
async def test_outbox_custody_allows_closed_sequence_and_denies_terminal_reopen(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as session:
        async with session.begin():
            await OutboxService(session).append(value)
            await session.execute(
                text(
                    "update outbox_events set delivery_state='claimed', attempt_count=1, "
                    "claim_generation=1, next_attempt_at=null, claim_owner='worker:1', "
                    "claimed_at=statement_timestamp(), last_attempt_at=statement_timestamp(), "
                    "claim_expires_at=statement_timestamp()+interval '30 seconds' "
                    "where event_id=:id"
                ),
                {"id": value.event_id},
            )
            await session.execute(
                text(
                    "update outbox_events set delivery_state='retryable', "
                    "next_attempt_at=clock_timestamp()+interval '1 second', "
                    "claim_owner=null, claimed_at=null, claim_expires_at=null, "
                    "last_error_code='PROVIDER_UNAVAILABLE' where event_id=:id"
                ),
                {"id": value.event_id},
            )
            await session.execute(
                text(
                    "update outbox_events set delivery_state='claimed', attempt_count=2, "
                    "claim_generation=2, next_attempt_at=null, claim_owner='worker:2', "
                    "claimed_at=statement_timestamp(), last_attempt_at=statement_timestamp(), "
                    "claim_expires_at=statement_timestamp()+interval '30 seconds' "
                    "where event_id=:id"
                ),
                {"id": value.event_id},
            )
            await session.execute(
                text(
                    "update outbox_events set delivery_state='acknowledged', "
                    "claim_owner=null, claimed_at=null, claim_expires_at=null, "
                    "finalized_at=clock_timestamp() where event_id=:id"
                ),
                {"id": value.event_id},
            )
        with pytest.raises(DBAPIError, match="illegal outbox delivery transition"):
            async with session.begin():
                await session.execute(
                    text(
                        "update outbox_events set delivery_state='retryable', "
                        "next_attempt_at=clock_timestamp(), finalized_at=null, "
                        "last_error_code='RETRY_REQUESTED' where event_id=:id"
                    ),
                    {"id": value.event_id},
                )
        async with session.begin():
            await session.execute(
                text("update outbox_events set archived_at=clock_timestamp() where event_id=:id"),
                {"id": value.event_id},
            )
        with pytest.raises(DBAPIError, match="archived outbox event is closed"):
            async with session.begin():
                await session.execute(
                    text("update outbox_events set archived_at=null where event_id=:id"),
                    {"id": value.event_id},
                )


@pytest.mark.asyncio
async def test_outbox_immutable_columns_delete_and_truncate_are_guarded(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as session:
        async with session.begin():
            await OutboxService(session).append(value)
        immutable_updates = (
            f"event_id='{uuid4()}'",
            "event_type='ChangedEvent'",
            "event_version=2",
            "producer='other'",
            "aggregate_type='other'",
            f"aggregate_id='{uuid4()}'",
            f"project_id='{uuid4()}'",
            "correlation_id='changed'",
            f"causation_event_id='{uuid4()}'",
            "idempotency_key='changed:key'",
            "payload='{}'::jsonb",
            "payload_digest='sha256:" + ("0" * 64) + "'",
            "occurred_at=clock_timestamp()",
        )
        for assignment in immutable_updates:
            with pytest.raises(DBAPIError, match="outbox event envelope is immutable"):
                async with session.begin():
                    await session.execute(
                        text(f"update outbox_events set {assignment} where event_id=:id"),
                        {"id": value.event_id},
                    )
        with pytest.raises(DBAPIError, match="outbox events cannot be deleted"):
            async with session.begin():
                await session.execute(
                    text("delete from outbox_events where event_id=:id"),
                    {"id": value.event_id},
                )
        with pytest.raises(DBAPIError, match="outbox events cannot be truncated"):
            async with session.begin():
                await session.execute(text("truncate table outbox_events"))


@pytest.mark.asyncio
async def test_outbox_pending_cancellation_is_terminal_and_archivable(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as session:
        async with session.begin():
            await OutboxService(session).append(value)
            await session.execute(
                text(
                    "update outbox_events set delivery_state='cancelled', "
                    "next_attempt_at=null, finalized_at=clock_timestamp() where event_id=:id"
                ),
                {"id": value.event_id},
            )
        with pytest.raises(DBAPIError, match="illegal outbox delivery transition"):
            async with session.begin():
                await session.execute(
                    text(
                        "update outbox_events set delivery_state='claimed', attempt_count=1, "
                        "claim_generation=1, claim_owner='worker:1', "
                        "claimed_at=statement_timestamp(), last_attempt_at=statement_timestamp(), "
                        "claim_expires_at=statement_timestamp()+interval '30 seconds', "
                        "finalized_at=null where event_id=:id"
                    ),
                    {"id": value.event_id},
                )
        async with session.begin():
            await session.execute(
                text("update outbox_events set archived_at=clock_timestamp() where event_id=:id"),
                {"id": value.event_id},
            )


@pytest.mark.asyncio
async def test_outbox_unarchived_dead_letter_can_requeue_with_identity_preserved(
    outbox_factory: tuple[async_sessionmaker[AsyncSession], UUID],
) -> None:
    factory, project_id = outbox_factory
    value = _event(project_id)
    async with factory() as session:
        async with session.begin():
            await OutboxService(session).append(value)
            await session.execute(
                text(
                    "update outbox_events set delivery_state='claimed', attempt_count=1, "
                    "claim_generation=1, next_attempt_at=null, claim_owner='worker:1', "
                    "claimed_at=statement_timestamp(), last_attempt_at=statement_timestamp(), "
                    "claim_expires_at=statement_timestamp()+interval '30 seconds' "
                    "where event_id=:id"
                ),
                {"id": value.event_id},
            )
            await session.execute(
                text(
                    "update outbox_events set delivery_state='dead_letter', claim_owner=null, "
                    "claimed_at=null, claim_expires_at=null, last_error_code='ATTEMPTS_EXHAUSTED', "
                    "finalized_at=clock_timestamp() where event_id=:id"
                ),
                {"id": value.event_id},
            )
            await session.execute(
                text(
                    "update outbox_events set delivery_state='retryable', "
                    "next_attempt_at=clock_timestamp(), finalized_at=null where event_id=:id"
                ),
                {"id": value.event_id},
            )
            row = (
                await session.execute(
                    text(
                        "select event_id,idempotency_key,attempt_count,claim_generation,"
                        "delivery_state,last_error_code from outbox_events where event_id=:id"
                    ),
                    {"id": value.event_id},
                )
            ).one()
            assert row.event_id == value.event_id
            assert row.idempotency_key == value.idempotency_key
            assert row.attempt_count == row.claim_generation == 1
            assert row.delivery_state == "retryable"
            assert row.last_error_code == "ATTEMPTS_EXHAUSTED"
        with pytest.raises(DBAPIError, match="outbox claim generation must increment once"):
            async with session.begin():
                await session.execute(
                    text(
                        "update outbox_events set delivery_state='claimed', attempt_count=2, "
                        "claim_generation=2, next_attempt_at=null, claim_owner='worker:2', "
                        "claimed_at=statement_timestamp(), last_attempt_at=statement_timestamp(), "
                        "claim_expires_at=statement_timestamp()+interval '30 seconds', "
                        "last_error_code='CHANGED_DURING_CLAIM' where event_id=:id"
                    ),
                    {"id": value.event_id},
                )


def test_outbox_module_contains_no_dispatch_publish_or_commit_surface() -> None:
    root = Path(__file__).resolve().parents[1] / "app/modules/outbox"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "celery" not in source.lower()
    assert "broker" not in source.lower()
    assert ".commit(" not in source
    assert "def publish" not in source
