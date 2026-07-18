#!/usr/bin/env python3
"""Validate and bind confidential existing-service identity mappings."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from app.db.session import dispose_engine, get_engine
from app.modules.actors.service_identity_migration import (
    ServiceActorIdentityMappingDraft,
    ServiceIdentityMappingError,
    build_envelope,
    build_report,
    load_draft,
    load_envelope,
    publish_envelope,
    snapshot_existing_service_rows,
    validate_draft,
    validate_mapping_path,
    verify_envelope,
)


class DatabaseCleanupError(RuntimeError):
    """The CLI workflow succeeded but its async engine cleanup failed."""


class PrivacyBoundedParser(argparse.ArgumentParser):
    """Argument parser that never reflects confidential paths or values."""

    def error(self, _message: str) -> None:
        raise ServiceIdentityMappingError("invalid_arguments")


def _parser() -> PrivacyBoundedParser:
    parser = PrivacyBoundedParser(
        description="Validate fixed service identities without changing database state."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--draft", type=Path, required=True)
    bind = commands.add_parser("bind")
    bind.add_argument("--draft", type=Path, required=True)
    bind.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--envelope", type=Path, required=True)
    return parser


async def _execute(args: argparse.Namespace) -> dict:
    snapshot = await snapshot_existing_service_rows(get_engine())
    if args.command == "verify":
        envelope = load_envelope(validate_mapping_path(args.envelope))
        verify_envelope(
            envelope,
            snapshot.rows,
            database_binding=snapshot.database_binding,
        )
        draft = ServiceActorIdentityMappingDraft(
            schema_version=1,
            mappings=envelope.mappings,
        )
        return build_report(snapshot, draft, envelope=envelope).model_dump(mode="json")

    draft = load_draft(validate_mapping_path(args.draft))
    validate_draft(draft, snapshot.rows)
    if args.command == "validate":
        return build_report(snapshot, draft).model_dump(mode="json")

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    envelope = build_envelope(
        draft,
        snapshot.rows,
        database_binding=snapshot.database_binding,
        generated_at=generated_at,
    )
    publish_envelope(validate_mapping_path(args.output, output=True), envelope)
    return build_report(
        snapshot,
        draft,
        envelope=envelope,
        envelope_written=True,
    ).model_dump(mode="json")


async def _execute_and_dispose(args: argparse.Namespace) -> dict:
    """Execute and dispose the pooled engine on the same event loop."""
    try:
        report = await _execute(args)
    except BaseException:
        try:
            await dispose_engine()
        except BaseException:
            pass
        raise
    try:
        await dispose_engine()
    except BaseException:
        raise DatabaseCleanupError from None
    return report


def main(argv: list[str] | None = None) -> int:
    """Run the validate, bind, or verify workflow with bounded output."""
    result = 0
    stdout_message: str | None = None
    stderr_message: str | None = None
    try:
        args = _parser().parse_args(argv)
        report = asyncio.run(_execute_and_dispose(args))
        stdout_message = json.dumps(
            report,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except ServiceIdentityMappingError as exc:
        error = {"error": exc.code, "status": "error"}
        if exc.count is not None:
            error["count"] = exc.count
        stderr_message = json.dumps(error, separators=(",", ":"), sort_keys=True)
        result = 2
    except KeyboardInterrupt:
        stderr_message = '{"error":"interrupted","status":"error"}'
        result = 130
    except DatabaseCleanupError:
        stderr_message = '{"error":"database_cleanup_failed","status":"error"}'
        result = 2
    except Exception:
        stderr_message = '{"error":"database_operation_failed","status":"error"}'
        result = 2
    if stdout_message is not None:
        print(stdout_message)
    if stderr_message is not None:
        print(stderr_message, file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
