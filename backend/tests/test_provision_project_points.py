"""Real Flow identity and PostgreSQL authority proof for the points operator."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.adapters.auth.flow import FlowAuthVerifier
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.interfaces.auth import AuthVerificationError
from app.modules.actors.api import CompensationAdapterActorUnavailable, ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.compensation.api import (
    AdapterBindingConflict,
    AdapterBindingSuspendRequest,
    AdapterBindingUnavailable,
)
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.contributions.api import ContributionPolicyAuthorizationDenied
from app.modules.contributions.models import ProjectCompensationUnit
from app.modules.contributions.units.models import ProjectCompensationUnitCreationEvent
from project_create_fixtures import insert_historical_project
from tests.authentication.fixtures import rsa_signing_material as rsa_signing_material
from tests.authentication.support import (
    issue_asymmetric_token,
    jwks_transport,
    production_verifier_settings,
)
from tests.projects.guide_compilation.proposals.pg_support import (
    revoke_review_grant,
    seed_review_actor,
)

script = importlib.import_module("scripts.provision_project_points")
ISSUER = "https://identity.flowresearch.tech"
ROUTE = "flow_points.recording"


@pytest.fixture(name="points_database_env")
def _points_database_env(monkeypatch, clean_postgres_database: str) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    get_settings.cache_clear()
    yield clean_postgres_database
    get_settings.cache_clear()


async def _project() -> UUID:
    project = new_record_id()
    async with db_session.get_session_factory()() as session, session.begin():
        await insert_historical_project(
            session, project_id=str(project), name="Points project", slug=f"points-{project.hex}"
        )
    return project


async def _adapter() -> UUID:
    """Fixture only: the public service-actor owner is tested separately."""
    actor = new_record_id()
    async with db_session.get_session_factory()() as session, session.begin():
        session.add(
            ActorProfile(
                id=str(actor),
                actor_kind="service",
                status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=ServiceIdentity.COMPENSATION_ADAPTER.value,
                created_by="points-fixture",
            )
        )
        await session.flush()
        session.add(
            ActorIdentityLink(
                id=str(new_record_id()),
                actor_profile_id=str(actor),
                issuer=ISSUER,
                subject=f"adapter-{actor}",
                subject_kind="service",
                status="active",
                linked_by="points-fixture",
            )
        )
    return actor


def _authenticate(monkeypatch, tmp_path, signing_material, actor, **claims):
    key, jwk = signing_material
    settings = production_verifier_settings(token_issuer=ISSUER)
    verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    monkeypatch.setattr(script, "get_settings", lambda: settings)
    monkeypatch.setattr(script, "get_auth_verifier", lambda: verifier)
    token = issue_asymmetric_token(
        key, claims={"iss": ISSUER, "sub": str(actor.actor_profile_id), **claims}
    )
    path = tmp_path / f"finance-{actor.actor_profile_id}.token"
    path.write_text(token)
    path.chmod(0o600)
    return path, token


def _args(project, path, adapter, **changes):
    values = dict(
        project_id=project,
        finance_token_file=path,
        adapter_actor_id=adapter,
        unit_code="FLOW",
        route_key=ROUTE,
    )
    return argparse.Namespace(**(values | changes))


async def _state(project):
    async with db_session.get_session_factory()() as session:
        return tuple(
            [
                await session.scalar(
                    select(func.count()).select_from(model).where(model.project_id == str(project))
                )
                for model in (
                    ProjectCompensationUnit,
                    ProjectCompensationUnitCreationEvent,
                    ProjectCompensationAdapterBinding,
                )
            ]
        )


async def _prepared(
    points_database_env, monkeypatch, tmp_path, rsa_signing_material, *, role="finance_authority"
):
    project = await _project()
    actor, grant = await seed_review_actor(db_session.get_session_factory(), project, role=role)
    adapter = await _adapter()
    path, token = _authenticate(monkeypatch, tmp_path, rsa_signing_material, actor)
    return project, actor, grant, _args(project, path, adapter), token


def test_operation_ids_are_stable_request_keys():
    project = new_record_id()
    assert script.DEFAULT_UNIT_CODE == "FLOW"
    assert script.operation_id("unit", project, "FLOW") == script.operation_id(
        "unit", project, "FLOW"
    )
    assert script.operation_id("unit", project, "FLOW") != script.operation_id(
        "binding", project, "FLOW"
    )
    assert script.operation_id("unit", project, "FLOW").version == 5


@pytest.mark.parametrize(
    "unsafe", ["symlink", "hardlink", "directory", "public", "oversized", "empty", "wrong-owner"]
)
def test_token_file_custody_fails_closed(tmp_path, monkeypatch, unsafe):
    path = tmp_path / "bearer"
    path.write_text("never-log-this-bearer")
    path.chmod(0o600)
    if unsafe == "symlink":
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    elif unsafe == "hardlink":
        os.link(path, tmp_path / "link")
    elif unsafe == "directory":
        path = tmp_path
    elif unsafe == "public":
        path.chmod(0o644)
    elif unsafe == "oversized":
        path.write_text("x" * 65)
    elif unsafe == "empty":
        path.write_text("")
    else:
        uid = os.geteuid()
        monkeypatch.setattr(script.os, "geteuid", lambda: uid + 1)
    with pytest.raises(script.ProvisioningUnavailable, match="finance_token_file_unavailable"):
        script._read_token(path, 64)


@pytest.mark.parametrize("failure", ["invalid", "expired", "wrong-issuer", "service"])
async def test_bad_flow_identity_rejected_before_database(
    monkeypatch, tmp_path, rsa_signing_material, failure
):
    from types import SimpleNamespace

    actor = SimpleNamespace(actor_profile_id=new_record_id())
    claims = {}
    if failure == "expired":
        claims["exp"] = int((datetime.now(UTC) - timedelta(seconds=60)).timestamp())
    elif failure == "wrong-issuer":
        claims["iss"] = "https://foreign.example"
    path, _ = _authenticate(monkeypatch, tmp_path, rsa_signing_material, actor, **claims)
    if failure == "invalid":
        path.write_text("invalid-bearer")
    if failure == "service":
        path.write_text(
            issue_asymmetric_token(
                rsa_signing_material[0],
                subject_kind="service",
                claims={"iss": ISSUER, "sub": str(actor.actor_profile_id)},
            )
        )
    monkeypatch.setattr(script, "get_session_factory", lambda: pytest.fail("database accessed"))
    with pytest.raises((AuthVerificationError, script.ProvisioningUnavailable)):
        await script._finance_context(path)


async def test_dev_provider_is_rejected_before_file_or_database(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace(auth_provider="dev"))
    with pytest.raises(script.ProvisioningUnavailable, match="flow_authentication_required"):
        await script._finance_context(tmp_path / "missing")


async def test_create_and_exact_replay_use_live_flow_and_owner_receipts(
    points_database_env,
    monkeypatch,
    tmp_path,
    rsa_signing_material,
):
    project, _, _, args, _ = await _prepared(
        points_database_env, monkeypatch, tmp_path, rsa_signing_material
    )
    first = await script.run(args, {})
    second = await script.run(args, {})
    assert first == second and first["result_code"] == "ready"
    assert first["unit"] == first["binding"] == "ready"
    assert (
        UUID(first["unit_creation_event_id"]).version
        == UUID(first["adapter_binding_id"]).version
        == 7
    )
    assert await _state(project) == (1, 1, 1)


@pytest.mark.parametrize("existing", [False, True])
async def test_non_finance_cannot_discover_missing_or_existing_readiness(
    points_database_env,
    monkeypatch,
    tmp_path,
    rsa_signing_material,
    existing,
):
    project, _, _, args, _ = await _prepared(
        points_database_env, monkeypatch, tmp_path, rsa_signing_material
    )
    if existing:
        await script.run(args, {})
    manager, _ = await seed_review_actor(
        db_session.get_session_factory(), project, role="project_manager"
    )
    args.finance_token_file, _ = _authenticate(monkeypatch, tmp_path, rsa_signing_material, manager)
    output = {}
    with pytest.raises(ContributionPolicyAuthorizationDenied):
        await script.run(args, output)
    assert output == {} and await _state(project) == ((1, 1, 1) if existing else (0, 0, 0))


async def test_foreign_finance_scope_cannot_enable_target_project(
    points_database_env,
    monkeypatch,
    tmp_path,
    rsa_signing_material,
):
    project, _, _, args, _ = await _prepared(
        points_database_env, monkeypatch, tmp_path, rsa_signing_material
    )
    foreign = await _project()
    actor, _ = await seed_review_actor(
        db_session.get_session_factory(), foreign, role="finance_authority"
    )
    args.finance_token_file, _ = _authenticate(monkeypatch, tmp_path, rsa_signing_material, actor)
    with pytest.raises(ContributionPolicyAuthorizationDenied):
        await script.run(args, {})
    assert await _state(project) == (0, 0, 0)


async def test_token_is_reverified_between_commits_and_partial_step_is_retained(
    points_database_env,
    monkeypatch,
    tmp_path,
    rsa_signing_material,
):
    project, actor, _, args, _ = await _prepared(
        points_database_env, monkeypatch, tmp_path, rsa_signing_material
    )
    original = script._ensure_unit

    async def expire(context, values):
        result = await original(context, values)
        args.finance_token_file.write_text(
            issue_asymmetric_token(
                rsa_signing_material[0],
                claims={
                    "iss": ISSUER,
                    "sub": str(actor.actor_profile_id),
                    "exp": int((datetime.now(UTC) - timedelta(seconds=60)).timestamp()),
                },
            )
        )
        return result

    monkeypatch.setattr(script, "_ensure_unit", expire)
    output = {}
    with pytest.raises(AuthVerificationError):
        await script.run(args, output)
    assert output["unit"] == "ready" and "binding" not in output
    assert await _state(project) == (1, 1, 0)
    monkeypatch.setattr(script, "_ensure_unit", original)
    _authenticate(monkeypatch, tmp_path, rsa_signing_material, actor)
    assert (await script.run(args, {}))["result_code"] == "ready"
    assert await _state(project) == (1, 1, 1)


async def test_valid_finance_identity_change_between_commits_is_rejected(
    points_database_env,
    monkeypatch,
    tmp_path,
    rsa_signing_material,
):
    project, _, _, args, _ = await _prepared(
        points_database_env, monkeypatch, tmp_path, rsa_signing_material
    )
    other, _ = await seed_review_actor(
        db_session.get_session_factory(), project, role="finance_authority"
    )
    other_path, _ = _authenticate(monkeypatch, tmp_path, rsa_signing_material, other)
    original = script._ensure_unit

    async def switch_identity(context, values):
        result = await original(context, values)
        args.finance_token_file = other_path
        return result

    monkeypatch.setattr(script, "_ensure_unit", switch_identity)
    output = {}
    with pytest.raises(script.ProvisioningUnavailable, match="finance_identity_changed"):
        await script.run(args, output)
    assert output["unit"] == "ready" and "binding" not in output
    assert await _state(project) == (1, 1, 0)


async def test_revoked_finance_grant_blocks_binding_after_unit_commit(
    points_database_env,
    monkeypatch,
    tmp_path,
    rsa_signing_material,
):
    project, actor, grant, args, _ = await _prepared(
        points_database_env, monkeypatch, tmp_path, rsa_signing_material
    )
    original = script._ensure_unit

    async def revoke(context, values):
        result = await original(context, values)
        await revoke_review_grant(db_session.get_session_factory(), actor, grant)
        return result

    monkeypatch.setattr(script, "_ensure_unit", revoke)
    output = {}
    with pytest.raises(AdapterBindingUnavailable):
        await script.run(args, output)
    assert output["unit"] == "ready" and "binding" not in output
    assert await _state(project) == (1, 1, 0)


@pytest.mark.parametrize("inactive", ["adapter", "binding"])
async def test_binding_replay_requires_active_adapter_and_binding(
    points_database_env,
    monkeypatch,
    tmp_path,
    rsa_signing_material,
    inactive,
):
    project, _, _, args, _ = await _prepared(
        points_database_env, monkeypatch, tmp_path, rsa_signing_material
    )
    created = await script.run(args, {})
    assert created["result_code"] == "ready"
    context, _ = await script._finance_context(args.finance_token_file)
    async with db_session.get_session_factory()() as session, session.begin():
        if inactive == "adapter":
            # Fixture state: ACTORS eligibility must be rechecked even on exact replay.
            adapter = await session.get(ActorProfile, str(args.adapter_actor_id))
            adapter.status = "suspended"
            adapter.suspended_by = str(context.actor_profile_id)
            adapter.suspended_at = func.now()
            adapter.suspension_reason = "security response"
        else:
            authority = script.compensation_adapter_binding_authorization(session, context)
            await script.AdapterBindingService(
                session, read_authorization=authority, mutation_authorization=authority
            ).suspend(
                AdapterBindingSuspendRequest(
                    operation_id=new_record_id(),
                    actor_profile_id=context.actor_profile_id,
                    project_id=args.project_id,
                    adapter_binding_id=UUID(created["adapter_binding_id"]),
                    expected_lifecycle_version=1,
                )
            )
    expected = (
        CompensationAdapterActorUnavailable
        if inactive == "adapter"
        else script.ProvisioningUnavailable
    )
    output = {}
    with pytest.raises(expected):
        await script.run(args, output)
    assert output["unit"] == "ready" and "binding" not in output
    assert await _state(project) == (1, 1, 1)


async def test_changed_binding_request_conflicts_instead_of_reporting_ready(
    points_database_env,
    monkeypatch,
    tmp_path,
    rsa_signing_material,
):
    project, _, _, args, _ = await _prepared(
        points_database_env, monkeypatch, tmp_path, rsa_signing_material
    )
    await script.run(args, {})
    args.route_key = "other.points"
    with pytest.raises(AdapterBindingConflict):
        await script.run(args, {})
    assert await _state(project) == (1, 1, 1)


async def test_main_error_does_not_echo_bearer_or_verifier_details(monkeypatch, capsys, tmp_path):
    path = tmp_path / "token"
    path.write_text("private-bearer")
    path.chmod(0o600)

    async def fail(args, output):
        raise RuntimeError("private-bearer provider detail")

    monkeypatch.setattr(script, "run", fail)
    result = await asyncio.to_thread(
        script.main,
        [
            "--project-id",
            str(new_record_id()),
            "--finance-token-file",
            str(path),
            "--adapter-actor-id",
            str(new_record_id()),
            "--route-key",
            ROUTE,
        ],
    )
    output = capsys.readouterr().out
    assert result == 1 and "private-bearer" not in output and "provider detail" not in output
    assert json.loads(output)["error_type"] == "RuntimeError"


def test_help_exposes_authenticated_standard_without_local_bypass():
    result = subprocess.run(
        [sys.executable, "scripts/provision_project_points.py", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--finance-token-file" in result.stdout and "--adapter-actor-id" in result.stdout
    assert (
        "--admin-subject" not in result.stdout and "--finance-actor-profile-id" not in result.stdout
    )
