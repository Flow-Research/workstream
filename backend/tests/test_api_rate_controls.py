from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps.api_controls import (
    enforce_admin_mutation_rate_limit,
    enforce_first_access_rate_limit,
    get_rate_control_service,
)
from app.api.deps.auth import get_auth_verification_result
from app.core.config import Settings, get_settings
from app.main import create_app
from app.modules.api_controls import service as rate_service_module
from app.modules.api_controls.models import ApiRateControlCounter
from app.modules.api_controls.repository import ApiRateControlRepository, ConsumedCounter
from app.modules.api_controls.service import (
    ADMIN_MUTATION_SCOPE,
    FIRST_ACCESS_SCOPE,
    RateControlDecision,
    RateControlService,
    RateControlUnavailableError,
    rate_key_digest,
)
from app.schemas.auth import AuthVerificationResult, VerifiedIssuerToken

RATE_SECRET_TEXT = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
RATE_SECRET = SecretStr(RATE_SECRET_TEXT)
RATE_ISSUER = "https://issuer.example.test"
RATE_SUBJECT = "opaque-subject"


def test_rate_control_orm_model_matches_the_migration_contract() -> None:
    table = ApiRateControlCounter.__table__

    assert list(table.columns) == [
        table.c.control_scope,
        table.c.key_digest,
        table.c.window_started_at,
        table.c.window_expires_at,
        table.c.request_count,
        table.c.updated_at,
    ]
    assert {column.name for column in table.primary_key.columns} == {
        "control_scope",
        "key_digest",
    }
    assert {constraint.name for constraint in table.constraints} == {
        "pk_api_rate_control_counters",
        "ck_api_rate_control_counters_scope_token",
        "ck_api_rate_control_counters_digest_length",
        "ck_api_rate_control_counters_request_count",
        "ck_api_rate_control_counters_window_order",
    }
    assert {index.name for index in table.indexes} == {
        "ix_api_rate_control_counters_window_expires_at"
    }


@pytest.fixture
def rate_control_database_env(
    postgres_database_url: str,
    migration_lock,
    monkeypatch: pytest.MonkeyPatch,
):
    """Bind settings and migrate the exact isolated database used by this suite."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    get_settings.cache_clear()
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    with migration_lock():
        command.upgrade(config, "head")
    yield postgres_database_url
    get_settings.cache_clear()


@pytest.fixture
async def rate_control_factory(rate_control_database_env: str):
    """Provide independent sessions over a clean, migrated rate-control table."""
    engine = create_async_engine(rate_control_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("delete from api_rate_control_counters"))
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("delete from api_rate_control_counters"))
        await engine.dispose()


def test_rate_key_digest_matches_literal_vector_and_separates_boundaries() -> None:
    expected = bytes.fromhex(
        "35b4fb3e6a647a52596a5240b0b3ad5c2976d91771f95e2497be247081e53b31"
    )

    assert rate_key_digest(
        RATE_SECRET, FIRST_ACCESS_SCOPE, RATE_ISSUER, RATE_SUBJECT
    ) == expected
    assert rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, "ab", "c") != (
        rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, "a", "bc")
    )
    assert rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, "Issuer", "subject") != (
        rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, "issuer", "subject")
    )
    assert rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, "issuer", "e\u0301") != (
        rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, "issuer", "\u00e9")
    )
    assert rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, "issuer", "subject") != (
        rate_key_digest(RATE_SECRET, ADMIN_MUTATION_SCOPE, "issuer", "subject")
    )


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        ("", "subject"),
        ("x" * 4_097, "subject"),
        ("\u00e9" * 2_049, "subject"),
        ("\ud800", "subject"),
        ("issuer", "\ud800"),
    ],
)
def test_rate_key_digest_rejects_unbounded_identity_without_echo(
    issuer: str, subject: str
) -> None:
    with pytest.raises(RateControlUnavailableError) as caught:
        rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, issuer, subject)
    assert str(caught.value) == "rate control unavailable"


async def _stored_rate_row(factory, scope: str, digest: bytes):
    async with factory() as session:
        return (
            await session.execute(
                text(
                    "select window_started_at, window_expires_at, request_count "
                    "from api_rate_control_counters "
                    "where control_scope = :scope and key_digest = :digest"
                ),
                {"scope": scope, "digest": digest},
            )
        ).one()


async def _insert_counter_row(
    session,
    scope: str,
    digest: bytes,
    *,
    started_offset: int,
    expires_offset: int,
    request_count: int,
    updated_offset: int = 0,
) -> None:
    await session.execute(
        text(
            "insert into api_rate_control_counters "
            "(control_scope, key_digest, window_started_at, window_expires_at, "
            "request_count, updated_at) values "
            "(:scope, :digest, "
            "statement_timestamp() + make_interval(secs => :started_offset), "
            "statement_timestamp() + make_interval(secs => :expires_offset), "
            ":request_count, "
            "statement_timestamp() + make_interval(secs => :updated_offset))"
        ),
        {
            "scope": scope,
            "digest": digest,
            "started_offset": started_offset,
            "expires_offset": expires_offset,
            "request_count": request_count,
            "updated_offset": updated_offset,
        },
    )


async def test_rate_control_commits_fixed_window_denials_and_resets_expiry(
    rate_control_factory,
) -> None:
    service = RateControlService(rate_control_factory)
    decisions = [
        await service.consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=RATE_SUBJECT,
            limit=2,
            window_seconds=60,
            secret=RATE_SECRET,
        )
        for _ in range(4)
    ]
    digest = rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, RATE_ISSUER, RATE_SUBJECT)
    original = await _stored_rate_row(rate_control_factory, FIRST_ACCESS_SCOPE, digest)

    assert [decision.allowed for decision in decisions] == [True, True, False, False]
    assert [decision.request_count for decision in decisions] == [1, 2, 3, 4]
    assert all(1 <= decision.retry_after <= 60 for decision in decisions)
    assert original.request_count == 4

    async with rate_control_factory() as session:
        await session.execute(
            text(
                "update api_rate_control_counters set "
                "window_started_at = statement_timestamp() - interval '2 seconds', "
                "window_expires_at = statement_timestamp() - interval '1 second' "
                "where control_scope = :scope and key_digest = :digest"
            ),
            {"scope": FIRST_ACCESS_SCOPE, "digest": digest},
        )
        await session.commit()

    reset = await service.consume(
        control_scope=FIRST_ACCESS_SCOPE,
        issuer=RATE_ISSUER,
        subject=RATE_SUBJECT,
        limit=2,
        window_seconds=60,
        secret=RATE_SECRET,
    )
    persisted = await _stored_rate_row(rate_control_factory, FIRST_ACCESS_SCOPE, digest)
    assert reset == RateControlDecision(allowed=True, request_count=1, retry_after=60)
    assert persisted.request_count == 1
    assert persisted.window_started_at > original.window_started_at

    other_scope = await service.consume(
        control_scope=ADMIN_MUTATION_SCOPE,
        issuer=RATE_ISSUER,
        subject=RATE_SUBJECT,
        limit=2,
        window_seconds=60,
        secret=RATE_SECRET,
    )
    other_subject = await service.consume(
        control_scope=FIRST_ACCESS_SCOPE,
        issuer=RATE_ISSUER,
        subject="distinct-subject",
        limit=2,
        window_seconds=60,
        secret=RATE_SECRET,
    )
    assert other_scope.request_count == other_subject.request_count == 1
    assert (
        await _stored_rate_row(rate_control_factory, FIRST_ACCESS_SCOPE, digest)
    ).request_count == 1


async def test_repository_persists_the_returned_database_timestamp(
    rate_control_factory,
) -> None:
    digest = bytes([17]) * 32
    async with rate_control_factory() as session:
        consumed = await ApiRateControlRepository(session).consume(
            FIRST_ACCESS_SCOPE, digest, 60
        )
        updated_at = await session.scalar(
            text(
                "select updated_at from api_rate_control_counters "
                "where control_scope = :scope and key_digest = :digest"
            ),
            {"scope": FIRST_ACCESS_SCOPE, "digest": digest},
        )
        await session.rollback()
    assert updated_at == consumed.db_now


async def test_rate_control_concurrency_has_no_lost_or_rolled_back_consumption(
    rate_control_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_consume = ApiRateControlRepository.consume
    all_started = asyncio.Event()
    started = 0

    async def synchronized_consume(repository, *args, **kwargs):
        nonlocal started
        started += 1
        if started == 20:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=5)
        return await original_consume(repository, *args, **kwargs)

    monkeypatch.setattr(ApiRateControlRepository, "consume", synchronized_consume)
    service = RateControlService(rate_control_factory)

    async def consume_once():
        return await service.consume(
            control_scope=ADMIN_MUTATION_SCOPE,
            issuer=RATE_ISSUER,
            subject="concurrent-subject",
            limit=7,
            window_seconds=30,
            secret=RATE_SECRET,
        )

    decisions = await asyncio.gather(*(consume_once() for _ in range(20)))
    digest = rate_key_digest(
        RATE_SECRET, ADMIN_MUTATION_SCOPE, RATE_ISSUER, "concurrent-subject"
    )
    persisted = await _stored_rate_row(rate_control_factory, ADMIN_MUTATION_SCOPE, digest)

    assert sum(decision.allowed for decision in decisions) == 7
    assert sorted(decision.request_count for decision in decisions) == list(range(1, 21))
    assert persisted.request_count == 20

    probe_digest = bytes([255]) * 32
    independent_subject = "rollback-independent"
    independent_digest = rate_key_digest(
        RATE_SECRET, FIRST_ACCESS_SCOPE, RATE_ISSUER, independent_subject
    )
    async with rate_control_factory() as outer:
        await _insert_counter_row(
            outer,
            FIRST_ACCESS_SCOPE,
            probe_digest,
            started_offset=0,
            expires_offset=60,
            request_count=1,
        )
        independent = await service.consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=independent_subject,
            limit=1,
            window_seconds=60,
            secret=RATE_SECRET,
        )
        await outer.rollback()
    async with rate_control_factory() as session:
        probe_count = await session.scalar(
            text(
                "select count(*) from api_rate_control_counters "
                "where control_scope = :scope and key_digest = :digest"
            ),
            {"scope": FIRST_ACCESS_SCOPE, "digest": probe_digest},
        )
    assert independent.allowed is True
    assert probe_count == 0
    assert (
        await _stored_rate_row(rate_control_factory, FIRST_ACCESS_SCOPE, independent_digest)
    ).request_count == 1


async def test_rate_control_saturates_bigint_and_prunes_only_bounded_other_rows(
    rate_control_factory,
) -> None:
    service = RateControlService(rate_control_factory)
    digest = rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, RATE_ISSUER, "saturated")
    async with rate_control_factory() as session:
        await _insert_counter_row(
            session,
            FIRST_ACCESS_SCOPE,
            digest,
            started_offset=0,
            expires_offset=60,
            request_count=9_223_372_036_854_775_807,
        )
        for value in range(125):
            await _insert_counter_row(
                session,
                ADMIN_MUTATION_SCOPE,
                value.to_bytes(32, "big"),
                started_offset=-120,
                expires_offset=-60,
                request_count=1,
                updated_offset=-60,
            )
        await session.commit()

    decision = await service.consume(
        control_scope=FIRST_ACCESS_SCOPE,
        issuer=RATE_ISSUER,
        subject="saturated",
        limit=10_000,
        window_seconds=60,
        secret=RATE_SECRET,
    )
    async with rate_control_factory() as session:
        expired = await session.scalar(
            text(
                "select count(*) from api_rate_control_counters "
                "where window_expires_at <= statement_timestamp()"
            )
        )
    assert decision.request_count == 9_223_372_036_854_775_807
    assert decision.allowed is False
    assert expired == 25


async def test_concurrent_expired_keys_do_not_deadlock_during_pruning(
    rate_control_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subjects = ("expired-a", "expired-b")
    async with rate_control_factory() as session:
        for subject in subjects:
            await _insert_counter_row(
                session,
                FIRST_ACCESS_SCOPE,
                rate_key_digest(RATE_SECRET, FIRST_ACCESS_SCOPE, RATE_ISSUER, subject),
                started_offset=-2,
                expires_offset=-1,
                request_count=5,
                updated_offset=-1,
            )
        await session.commit()

    original_prune = ApiRateControlRepository.prune_expired
    both_upserted = asyncio.Event()
    upserted = 0

    async def synchronized_prune(repository, *args, **kwargs):
        nonlocal upserted
        upserted += 1
        if upserted == 2:
            both_upserted.set()
        await asyncio.wait_for(both_upserted.wait(), timeout=5)
        return await original_prune(repository, *args, **kwargs)

    monkeypatch.setattr(ApiRateControlRepository, "prune_expired", synchronized_prune)
    service = RateControlService(rate_control_factory)
    decisions = await asyncio.wait_for(
        asyncio.gather(
            *(
                service.consume(
                    control_scope=FIRST_ACCESS_SCOPE,
                    issuer=RATE_ISSUER,
                    subject=subject,
                    limit=1,
                    window_seconds=60,
                    secret=RATE_SECRET,
                )
                for subject in subjects
            )
        ),
        timeout=5,
    )
    assert decisions == [
        RateControlDecision(allowed=True, request_count=1, retry_after=60),
        RateControlDecision(allowed=True, request_count=1, retry_after=60),
    ]


class _FakeSession:
    """Minimal async-session context for deterministic failure tests."""

    def __init__(
        self, *, commit_error: bool = False, enter_error: bool = False
    ) -> None:
        self.commit_error = commit_error
        self.enter_error = enter_error
        self.rolled_back = False

    async def __aenter__(self):
        if self.enter_error:
            raise SQLAlchemyError("private session-open detail")
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def commit(self) -> None:
        if self.commit_error:
            raise SQLAlchemyError("private commit detail")

    async def rollback(self) -> None:
        self.rolled_back = True


async def test_rate_control_maps_only_database_failures_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    with pytest.raises(RateControlUnavailableError, match="^rate control unavailable$"):
        await RateControlService(lambda: _FakeSession(enter_error=True)).consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=RATE_SUBJECT,
            limit=1,
            window_seconds=60,
            secret=RATE_SECRET,
        )

    session = _FakeSession()

    async def fail_execute(*_args, **_kwargs):
        raise SQLAlchemyError("private execute detail")

    monkeypatch.setattr(ApiRateControlRepository, "consume", fail_execute)
    with pytest.raises(RateControlUnavailableError, match="^rate control unavailable$"):
        await RateControlService(lambda: session).consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=RATE_SUBJECT,
            limit=1,
            window_seconds=60,
            secret=RATE_SECRET,
        )
    assert session.rolled_back is True

    async def successful_consume(*_args, **_kwargs):
        return ConsumedCounter(now, now, now + timedelta(seconds=60), 1)

    async def successful_prune(*_args, **_kwargs):
        return None

    async def fail_prune(*_args, **_kwargs):
        raise SQLAlchemyError("private prune detail")

    prune_session = _FakeSession()
    monkeypatch.setattr(ApiRateControlRepository, "consume", successful_consume)
    monkeypatch.setattr(ApiRateControlRepository, "prune_expired", fail_prune)
    with pytest.raises(RateControlUnavailableError, match="^rate control unavailable$"):
        await RateControlService(lambda: prune_session).consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=RATE_SUBJECT,
            limit=1,
            window_seconds=60,
            secret=RATE_SECRET,
        )
    assert prune_session.rolled_back is True

    commit_session = _FakeSession(commit_error=True)
    monkeypatch.setattr(ApiRateControlRepository, "consume", successful_consume)
    monkeypatch.setattr(ApiRateControlRepository, "prune_expired", successful_prune)
    with pytest.raises(RateControlUnavailableError, match="^rate control unavailable$"):
        await RateControlService(lambda: commit_session).consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=RATE_SUBJECT,
            limit=1,
            window_seconds=60,
            secret=RATE_SECRET,
        )
    assert commit_session.rolled_back is True


async def test_retry_after_uses_only_returned_database_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_now = datetime(2000, 1, 1, tzinfo=UTC)

    async def subsecond(*_args, **_kwargs):
        return ConsumedCounter(
            database_now,
            database_now,
            database_now + timedelta(milliseconds=200),
            2,
        )

    async def no_prune(*_args, **_kwargs):
        return None

    monkeypatch.setattr(ApiRateControlRepository, "consume", subsecond)
    monkeypatch.setattr(ApiRateControlRepository, "prune_expired", no_prune)
    decision = await RateControlService(lambda: _FakeSession()).consume(
        control_scope=FIRST_ACCESS_SCOPE,
        issuer=RATE_ISSUER,
        subject=RATE_SUBJECT,
        limit=1,
        window_seconds=60,
        secret=RATE_SECRET,
    )
    assert decision.retry_after == 1

    async def beyond_window(*_args, **_kwargs):
        return ConsumedCounter(
            database_now,
            database_now,
            database_now + timedelta(seconds=120),
            2,
        )

    monkeypatch.setattr(ApiRateControlRepository, "consume", beyond_window)
    decision = await RateControlService(lambda: _FakeSession()).consume(
        control_scope=FIRST_ACCESS_SCOPE,
        issuer=RATE_ISSUER,
        subject=RATE_SUBJECT,
        limit=1,
        window_seconds=60,
        secret=RATE_SECRET,
    )
    assert decision.retry_after == 60


async def test_rate_control_narrowly_maps_missing_database_and_propagates_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_database():
        raise RuntimeError("WORKSTREAM_DATABASE_URL must be set before database access")

    monkeypatch.setattr(rate_service_module, "get_session_factory", missing_database)
    with pytest.raises(RateControlUnavailableError, match="^rate control unavailable$"):
        await RateControlService().consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=RATE_SUBJECT,
            limit=1,
            window_seconds=60,
            secret=RATE_SECRET,
        )

    def unrelated_failure():
        raise RuntimeError("unrelated runtime failure")

    monkeypatch.setattr(rate_service_module, "get_session_factory", unrelated_failure)
    with pytest.raises(RuntimeError, match="unrelated runtime failure"):
        await RateControlService().consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=RATE_SUBJECT,
            limit=1,
            window_seconds=60,
            secret=RATE_SECRET,
        )

    async def cancel(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(ApiRateControlRepository, "consume", cancel)
    with pytest.raises(asyncio.CancelledError):
        await RateControlService(lambda: _FakeSession()).consume(
            control_scope=FIRST_ACCESS_SCOPE,
            issuer=RATE_ISSUER,
            subject=RATE_SUBJECT,
            limit=1,
            window_seconds=60,
            secret=RATE_SECRET,
        )


def _verified_rate_identity(subject: str = RATE_SUBJECT) -> AuthVerificationResult:
    return AuthVerificationResult(
        token=VerifiedIssuerToken(
            issuer=RATE_ISSUER,
            subject=subject,
            audience=("workstream",),
            expires_at=2_000_000_000,
            issued_at=1_999_999_000,
            token_id="rate-token",
            subject_kind="human",
            scopes=frozenset({"workstream:access"}),
        )
    )


class _DecisionService:
    def __init__(self, decisions: list[RateControlDecision] | None = None) -> None:
        self.decisions = decisions or []
        self.calls: list[dict] = []

    async def consume(self, **kwargs) -> RateControlDecision:
        self.calls.append(kwargs)
        if not self.decisions:
            raise RateControlUnavailableError("private database detail")
        return self.decisions.pop(0)


async def test_unattached_dependencies_emit_canonical_429_and_use_token_identity() -> None:
    service = _DecisionService(
        [
            RateControlDecision(True, 1, 60),
            RateControlDecision(False, 31, 17),
        ]
    )
    app = create_app(
        Settings(environment="test", api_rate_limit_key_secret=RATE_SECRET_TEXT)
    )
    app.dependency_overrides[get_auth_verification_result] = _verified_rate_identity
    app.dependency_overrides[get_rate_control_service] = lambda: service

    @app.post(
        "/_test/first-access-rate",
        dependencies=[Depends(enforce_first_access_rate_limit)],
    )
    async def first_access() -> dict[str, bool]:
        return {"allowed": True}

    @app.post(
        "/_test/admin-mutation-rate",
        dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    )
    async def admin_mutation() -> dict[str, bool]:
        return {"allowed": True}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        allowed = await client.post("/_test/first-access-rate")
        denied = await client.post("/_test/admin-mutation-rate")

    assert allowed.status_code == 200
    assert denied.status_code == 429
    assert denied.headers["retry-after"] == "17"
    assert denied.json() == {
        "detail": "Rate limit exceeded",
        "error": {
            "code": "rate_limit_exceeded",
            "message": "Rate limit exceeded",
            "details": {},
            "correlation_id": denied.headers["x-correlation-id"],
            "retryable": True,
        },
    }
    assert [call["control_scope"] for call in service.calls] == [
        FIRST_ACCESS_SCOPE,
        ADMIN_MUTATION_SCOPE,
    ]
    assert all(call["issuer"] == RATE_ISSUER for call in service.calls)
    assert all(call["subject"] == RATE_SUBJECT for call in service.calls)


@pytest.mark.parametrize(
    ("settings", "subject", "service"),
    [
        (Settings(environment="test"), RATE_SUBJECT, RateControlService()),
        (
            Settings(environment="test", api_rate_limit_key_secret=RATE_SECRET_TEXT),
            RATE_SUBJECT,
            _DecisionService(),
        ),
    ],
)
async def test_rate_dependency_unavailability_is_private_503(
    settings: Settings,
    subject: str,
    service,
) -> None:
    app = create_app(settings)
    app.dependency_overrides[get_auth_verification_result] = lambda: _verified_rate_identity(
        subject
    )
    app.dependency_overrides[get_rate_control_service] = lambda: service

    @app.post(
        "/_test/rate-unavailable",
        dependencies=[Depends(enforce_first_access_rate_limit)],
    )
    async def unavailable() -> None:
        return None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/_test/rate-unavailable")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Service unavailable",
        "error": {
            "code": "service_unavailable",
            "message": "Service unavailable",
            "details": {},
            "correlation_id": response.headers["x-correlation-id"],
            "retryable": True,
        },
    }
    assert subject not in response.text


def test_rate_dependencies_are_not_attached_to_production_routes() -> None:
    forbidden = {
        enforce_first_access_rate_limit,
        enforce_admin_mutation_rate_limit,
    }

    def dependency_calls(dependant) -> set:
        calls = {dependant.call}
        for dependency in dependant.dependencies:
            calls.update(dependency_calls(dependency))
        return calls

    app = create_app()
    assert all(
        forbidden.isdisjoint(dependency_calls(route.dependant))
        for route in app.routes
        if hasattr(route, "dependant")
    )
