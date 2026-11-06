#!/usr/bin/env python3
"""Provision a project points unit and binding as a verified Finance Authority.

The compensation-adapter service actor must already be provisioned through the
Access Administrator's public service-actor route. One private token file is
verified with the configured Flow verifier before each separately committed
owner command. AUTH/PREP supplies current project authority, including replay;
this command neither inserts product rows directly nor invokes fulfillment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import stat
from typing import Any
from uuid import UUID, uuid5

from app.adapters.auth import (
    compensation_adapter_binding_authorization,
    contribution_policy_authorization,
)
from app.adapters.contributions import project_compensation_unit_service
from app.core.auth import get_auth_verifier
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db.session import dispose_engine, get_session_factory
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.actors.service import ActorService
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.compensation.api import AdapterBindingCreateRequest, AdapterBindingReadRequest
from app.modules.compensation.service import AdapterBindingService
from app.modules.contributions.api import ProjectCompensationUnitCreateRequest
from app.modules.contributions.models import ProjectCompensationUnit
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility

INSTRUMENT = "project_points"
DEFAULT_UNIT_CODE = "FLOW"
_OPERATION_NAMESPACE = UUID("3c4f0b9e-2a7d-4e51-8b6c-9d1e0f2a7b33")


class ProvisioningUnavailable(RuntimeError):
    """A bounded prerequisite failure without credentials or resource details."""


def operation_id(step: str, project_id: UUID, value: str) -> UUID:
    """Retain stable request keys; owner-generated record IDs remain UUIDv7."""
    return uuid5(_OPERATION_NAMESPACE, f"{step}\n{project_id}\n{value}")


def _read_token(path: Path, maximum: int) -> str:
    """Read one bounded caller-owned regular token file without following links."""
    try:
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
                or not 0 < info.st_size <= maximum
            ):
                raise ValueError
            raw = source.read(maximum + 1)
        if len(raw) > maximum:
            raise ValueError
        token = raw.decode("utf-8").strip()
        if not token or any(not 33 <= ord(character) <= 126 for character in token):
            raise ValueError
        return token
    except (OSError, ValueError, UnicodeError):
        raise ProvisioningUnavailable("finance_token_file_unavailable") from None


async def _finance_context(path: Path) -> tuple[HumanAuthorizationContext, tuple[str, ...]]:
    """Verify Flow identity and project exact ACTORS rows, never caller UUID/status claims."""
    settings = get_settings()
    if settings.auth_provider != "flow":
        raise ProvisioningUnavailable("flow_authentication_required")
    result = await get_auth_verifier().verify(_read_token(path, settings.token_max_bytes))
    if result.token.subject_kind != "human":
        raise ProvisioningUnavailable("finance_identity_unavailable")
    async with get_session_factory()() as session:
        resolved = await ActorService(session).find_actor_for_authorization(result.token)
        if resolved is None or resolved.profile.actor_kind != "human":
            raise ProvisioningUnavailable("finance_identity_unavailable")
        context = HumanAuthorizationContext(
            actor_profile_id=UUID(resolved.profile.id),
            identity_link_id=UUID(resolved.identity_link.id),
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus(resolved.profile.status),
            identity_link_status=IdentityLinkStatus(resolved.identity_link.status),
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        )
        anchor = (
            result.token.issuer,
            result.token.subject,
            str(context.actor_profile_id),
            str(context.identity_link_id),
        )
    return context, anchor


async def _ensure_unit(context: HumanAuthorizationContext, args: argparse.Namespace):
    """Always enter the canonical owner, including existing-operation replay."""
    async with get_session_factory()() as session, session.begin():
        result = await project_compensation_unit_service(
            session,
            mutation_authorization=contribution_policy_authorization(session, context),
        ).create(
            ProjectCompensationUnitCreateRequest(
                operation_id=operation_id("unit", args.project_id, args.unit_code),
                actor_profile_id=context.actor_profile_id,
                project_id=args.project_id,
                instrument_type=INSTRUMENT,
                unit_code=args.unit_code,
            )
        )
        unit = await session.get(
            ProjectCompensationUnit,
            (str(args.project_id), INSTRUMENT, args.unit_code),
            with_for_update=True,
        )
        if unit is None or unit.status != "active":
            raise ProvisioningUnavailable("points_unit_unavailable")
    return result


async def _ensure_binding(context: HumanAuthorizationContext, args: argparse.Namespace):
    """Create/replay under Finance create authority and require live readiness."""
    async with get_session_factory()() as session, session.begin():
        authorization = compensation_adapter_binding_authorization(session, context)
        projects = ProjectCompensationBindingEligibility(session)
        actors = CompensationAdapterActorEligibility(session)
        service = AdapterBindingService(
            session,
            read_authorization=authorization,
            mutation_authorization=authorization,
            projects=projects,
            actors=actors,
        )
        result = await service.create(
            AdapterBindingCreateRequest(
                operation_id=operation_id("binding", args.project_id, args.route_key),
                actor_profile_id=context.actor_profile_id,
                project_id=args.project_id,
                instrument_type=INSTRUMENT,
                adapter_actor_id=args.adapter_actor_id,
                route_key=args.route_key,
            )
        )
        await projects.lock_compensation_binding_project(args.project_id)
        await actors.lock_compensation_adapter_actor(args.adapter_actor_id)
        binding = await service.read(
            AdapterBindingReadRequest(
                actor_profile_id=context.actor_profile_id,
                project_id=args.project_id,
                adapter_binding_id=result.adapter_binding_id,
            )
        )
        if (
            binding.status != "active"
            or binding.adapter_actor_id != args.adapter_actor_id
            or binding.instrument_type != INSTRUMENT
            or binding.route_key != args.route_key
        ):
            raise ProvisioningUnavailable("points_binding_unavailable")
    return result


async def run(args: argparse.Namespace, output: dict[str, Any]) -> dict[str, Any]:
    """Reverify identity before each committed step and retain only actual results."""
    try:
        context, anchor = await _finance_context(args.finance_token_file)
        unit = await _ensure_unit(context, args)
        output.update(
            finance_actor_profile_id=str(context.actor_profile_id),
            unit="ready",
            unit_code=args.unit_code,
            unit_creation_event_id=str(unit.event_id),
            unit_operation_id=str(unit.operation_id),
            unit_request_digest=unit.request_digest,
        )
        context, current_anchor = await _finance_context(args.finance_token_file)
        if current_anchor != anchor:
            raise ProvisioningUnavailable("finance_identity_changed")
        binding = await _ensure_binding(context, args)
        output.update(
            binding="ready",
            adapter_actor_id=str(args.adapter_actor_id),
            adapter_binding_id=str(binding.adapter_binding_id),
            binding_event_id=str(binding.event_id),
            binding_operation_id=str(binding.operation_id),
            binding_request_digest=binding.request_digest,
        )
        return {"result_code": "ready", **output}
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-id", type=UUID, required=True)
    parser.add_argument("--finance-token-file", type=Path, required=True)
    parser.add_argument("--adapter-actor-id", type=UUID, required=True)
    parser.add_argument("--route-key", required=True)
    parser.add_argument("--unit-code", default=DEFAULT_UNIT_CODE)
    args = parser.parse_args(argv)
    output: dict[str, Any] = {"project_id": str(args.project_id)}
    try:
        result = asyncio.run(run(args, output))
    except ProvisioningUnavailable as error:
        print(json.dumps({"result_code": "unavailable", "detail": str(error), **output}))
        return 3
    except Exception as error:  # noqa: BLE001 - never expose bearer, verifier or database detail.
        print(json.dumps({"result_code": "failed", "error_type": type(error).__name__, **output}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
