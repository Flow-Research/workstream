#!/usr/bin/env python3
"""Run the one-time local Access Administrator bootstrap operation."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
from typing import Literal
from uuid import UUID

from app.db.session import dispose_engine, get_session_factory
from app.modules.authorization.admin_service import (
    AdminRoleGrantService,
    BootstrapAlreadyCompleted,
    BootstrapTargetIneligible,
)
from app.modules.authorization.catalogue import ActionId, PermissionId


@dataclass(frozen=True)
class BootstrapCommandManifest:
    """Static catalogue declaration for the local trust-root operation."""

    action_id: ActionId
    permission_id: PermissionId
    principal: Literal["workstream:system:bootstrap"]


BOOTSTRAP_COMMAND_MANIFEST = BootstrapCommandManifest(
    action_id=ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP,
    permission_id=PermissionId.ADMIN_ROLE_GRANT,
    principal="workstream:system:bootstrap",
)


class InvalidBootstrapArguments(ValueError):
    """The command arguments are invalid without retaining raw input."""


class PrivacyBoundedParser(argparse.ArgumentParser):
    """Reject invalid arguments without echoing raw values."""

    def error(self, _message: str) -> None:
        raise InvalidBootstrapArguments("invalid_arguments")


def _parser() -> PrivacyBoundedParser:
    parser = PrivacyBoundedParser(description="Bootstrap the first Access Administrator.")
    parser.add_argument("--actor-profile-id", type=UUID, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return parser


async def _run(actor_profile_id: UUID, *, execute: bool) -> tuple[int, dict[str, object]]:
    async with get_session_factory()() as session:
        service = AdminRoleGrantService(session)
        if not execute:
            try:
                eligible = await service.bootstrap_eligible(actor_profile_id)
            except BootstrapAlreadyCompleted:
                await session.rollback()
                return 3, {
                    "result_code": "admin_role_grant_exists",
                    "actor_profile_id": str(actor_profile_id),
                    "would_change": False,
                }
            await session.rollback()
            if not eligible:
                return 2, {
                    "result_code": "target_ineligible",
                    "actor_profile_id": str(actor_profile_id),
                    "would_change": False,
                }
            return 0, {
                "result_code": "eligible",
                "actor_profile_id": str(actor_profile_id),
                "would_change": True,
            }
        try:
            grant_id = await service.bootstrap(actor_profile_id)
            await session.commit()
        except BootstrapAlreadyCompleted as exc:
            await session.rollback()
            await service.record_bootstrap_conflict(
                actor_profile_id=actor_profile_id,
                grant_id=exc.grant_id,
            )
            await session.commit()
            return 3, {
                "result_code": "admin_role_grant_exists",
                "actor_profile_id": str(actor_profile_id),
                "grant_id": str(exc.grant_id),
                "changed": False,
            }
        except BootstrapTargetIneligible:
            await session.rollback()
            return 2, {
                "result_code": "target_ineligible",
                "actor_profile_id": str(actor_profile_id),
                "grant_id": None,
                "changed": False,
            }
        return 0, {
            "result_code": "bootstrapped",
            "actor_profile_id": str(actor_profile_id),
            "grant_id": str(grant_id),
            "changed": True,
        }


def main(argv: list[str] | None = None) -> int:
    """Parse, execute, and emit one bounded JSON result."""
    exit_code = 1
    output: dict[str, object] = {"result_code": "infrastructure_failure"}
    domain_outcome_returned = False
    try:
        args = _parser().parse_args(argv)
        exit_code, output = asyncio.run(_run(args.actor_profile_id, execute=bool(args.execute)))
        domain_outcome_returned = True
    except InvalidBootstrapArguments:
        exit_code = 2
        output = {"result_code": "invalid_request"}
    except KeyboardInterrupt:
        exit_code = 1
        output = {"result_code": "interrupted"}
    except Exception:
        exit_code = 1
        output = {"result_code": "infrastructure_failure"}
    finally:
        try:
            asyncio.run(dispose_engine())
        except Exception:
            if not domain_outcome_returned:
                exit_code = 1
                output = {"result_code": "infrastructure_failure"}
    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
