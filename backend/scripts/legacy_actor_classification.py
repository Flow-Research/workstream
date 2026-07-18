#!/usr/bin/env python3
"""Validate and export confidential legacy actor classification evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from app.db.session import dispose_engine, get_engine
from app.modules.actors.legacy_classification import (
    LegacyClassificationError,
    build_envelope,
    build_report,
    load_manifest,
    publish_envelope,
    snapshot_legacy_actors,
    validate_manifest,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class PrivacyBoundedParser(argparse.ArgumentParser):
    """Argument parser that never reflects confidential path values."""

    def error(self, _message: str) -> None:
        """Raise one stable error instead of rendering argument contents."""
        raise LegacyClassificationError("invalid_arguments")


def _git_common_directory(repository_root: Path) -> Path:
    marker = repository_root / ".git"
    if marker.is_dir():
        return marker
    try:
        value = marker.read_text(encoding="utf-8").strip()
    except OSError:
        raise LegacyClassificationError("git_directory_unavailable") from None
    prefix = "gitdir: "
    if not value.startswith(prefix):
        raise LegacyClassificationError("git_directory_unavailable")
    worktree_git = Path(value.removeprefix(prefix))
    if not worktree_git.is_absolute():
        worktree_git = marker.parent / worktree_git
    resolved = worktree_git.resolve()
    if resolved.parent.name != "worktrees":
        raise LegacyClassificationError("git_directory_unavailable")
    return resolved.parent.parent


def _parser() -> PrivacyBoundedParser:
    parser = PrivacyBoundedParser(
        description="Validate legacy actor classifications without changing database state."
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generated-at")
    return parser


async def _execute(args: argparse.Namespace) -> dict:
    if args.output is None and args.generated_at is not None:
        raise LegacyClassificationError("generated_at_requires_output")
    if args.output is not None and args.generated_at is None:
        raise LegacyClassificationError("generated_at_required")

    manifest = load_manifest(args.manifest) if args.manifest is not None else None
    snapshot = await snapshot_legacy_actors(get_engine())
    validated_manifest = validate_manifest(manifest, snapshot.rows)
    if args.output is None:
        return build_report(snapshot, validated_manifest).model_dump(mode="json")

    envelope = build_envelope(
        validated_manifest,
        snapshot.rows,
        database_binding=snapshot.database_binding,
        generated_at=args.generated_at,
    )
    written = publish_envelope(
        args.output,
        envelope,
        repository_root=REPOSITORY_ROOT,
        git_common_dir=_git_common_directory(REPOSITORY_ROOT),
    )
    return build_report(
        snapshot,
        validated_manifest,
        envelope=envelope,
        envelope_written=written,
    ).model_dump(mode="json")


def main(argv: list[str] | None = None) -> int:
    """Run the dry-run-first classification workflow."""
    result = 0
    stdout_message: str | None = None
    stderr_message: str | None = None
    try:
        args = _parser().parse_args(argv)
        report = asyncio.run(_execute(args))
        stdout_message = json.dumps(
            report,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except LegacyClassificationError as exc:
        stderr_message = json.dumps(
            {"error": exc.code, "status": "error"},
            separators=(",", ":"),
        )
        result = 2
    except KeyboardInterrupt:
        stderr_message = '{"error":"interrupted","status":"error"}'
        result = 130
    except Exception:
        stderr_message = '{"error":"database_operation_failed","status":"error"}'
        result = 2
    try:
        asyncio.run(dispose_engine())
    except Exception:
        if result == 0:
            stdout_message = None
            stderr_message = '{"error":"database_cleanup_failed","status":"error"}'
            result = 2
    if stdout_message is not None:
        print(stdout_message)
    if stderr_message is not None:
        print(stderr_message, file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
