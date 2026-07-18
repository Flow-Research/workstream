"""Fail-closed legacy actor classification evidence helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

MANIFEST_SCHEMA_VERSION = 1
CLASSIFICATION_FILE_ENV = "WORKSTREAM_LEGACY_ACTOR_CLASSIFICATION_FILE"
MAX_CLASSIFICATIONS = 100_000
MAX_CLASSIFICATION_FILE_BYTES = 16 * 1024 * 1024
MAX_ISSUER_CHARACTERS = 200
MAX_SUBJECT_CHARACTERS = 200
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_DATABASE_BINDING_PATTERN = re.compile(r"postgres-v1:[0-9a-f]{64}")
_GENERATED_AT_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class LegacyClassificationError(RuntimeError):
    """Stable, privacy-bounded classification failure."""

    def __init__(self, code: str) -> None:
        """Create an error whose message contains only a stable code."""
        self.code = code
        super().__init__(code)


def _canonical_json_bytes(value: Any) -> bytes:
    """Serialize one value with the checksum canonicalization rules."""
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()


def _validate_sha256(value: str) -> str:
    """Validate canonical SHA-256 text."""
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid digest")
    return value


def _validate_issuer(value: str) -> str:
    """Validate issuer shape without changing its identity bytes."""
    if (
        len(value) > MAX_ISSUER_CHARACTERS
        or value.strip() != value
        or any(character.isspace() or ord(character) < 0x20 for character in value)
    ):
        raise ValueError("invalid issuer")
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError:
        raise ValueError("invalid issuer") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid issuer")
    return value


def _validate_actor_id(value: str) -> str:
    """Validate a canonical UUIDv5 string."""
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("invalid actor id") from exc
    if parsed.version != 5 or str(parsed) != value:
        raise ValueError("invalid actor id")
    return value


def _expected_actor_id(issuer: str, subject: str) -> str:
    """Derive the repository's historical actor identifier."""
    return str(uuid5(NAMESPACE_URL, f"{issuer}:{subject}"))


class LegacyActorClassification(BaseModel):
    """One explicit classification for an exact legacy external identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    actor_id: str
    issuer: str
    subject: str = Field(min_length=1, max_length=MAX_SUBJECT_CHARACTERS)
    subject_kind: Literal["human", "service"]

    @field_validator("actor_id")
    @classmethod
    def validate_actor_id(cls, value: str) -> str:
        """Require the canonical UUIDv5 representation used by the registry."""
        return _validate_actor_id(value)

    @field_validator("issuer")
    @classmethod
    def validate_issuer(cls, value: str) -> str:
        """Require the verified-token boundary's exact HTTPS issuer shape."""
        return _validate_issuer(value)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        """Require a bounded, nonblank subject without changing its bytes."""
        if not value.strip():
            raise ValueError("invalid subject")
        return value

    @model_validator(mode="after")
    def validate_actor_derivation(self) -> LegacyActorClassification:
        """Bind the actor ID to the exact issuer and opaque subject."""
        if self.actor_id != _expected_actor_id(self.issuer, self.subject):
            raise ValueError("actor id does not match identity")
        return self


class LegacyActorClassificationManifest(BaseModel):
    """Versioned operator classification input."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    classifications: tuple[LegacyActorClassification, ...] = Field(
        max_length=MAX_CLASSIFICATIONS
    )

    @model_validator(mode="after")
    def validate_uniqueness(self) -> LegacyActorClassificationManifest:
        """Reject duplicate actor and external-identity declarations."""
        actor_ids = [entry.actor_id for entry in self.classifications]
        identities = [(entry.issuer, entry.subject) for entry in self.classifications]
        if len(actor_ids) != len(set(actor_ids)) or len(identities) != len(set(identities)):
            raise ValueError("duplicate classification")
        return self


class LegacyActorRow(BaseModel):
    """Complete legacy identity projection required by the later migration."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    actor_id: str
    issuer: str
    subject: str

    @field_validator("actor_id")
    @classmethod
    def validate_actor_id(cls, value: str) -> str:
        """Require one canonical historical UUIDv5."""
        return _validate_actor_id(value)

    @field_validator("issuer")
    @classmethod
    def validate_issuer(cls, value: str) -> str:
        """Require exact canonical issuer input."""
        return _validate_issuer(value)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        """Require the bounded, opaque subject used by the registry."""
        if not value or not value.strip() or len(value) > MAX_SUBJECT_CHARACTERS:
            raise ValueError("invalid subject")
        return value

    @model_validator(mode="after")
    def validate_actor_derivation(self) -> LegacyActorRow:
        """Reject source rows whose historical identity derivation drifted."""
        if self.actor_id != _expected_actor_id(self.issuer, self.subject):
            raise ValueError("actor id does not match identity")
        return self


class LegacyActorClassificationEnvelope(BaseModel):
    """Canonical confidential evidence consumed by the future migration."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    classifications: tuple[LegacyActorClassification, ...] = Field(
        max_length=MAX_CLASSIFICATIONS
    )
    source_row_set_sha256: str
    manifest_sha256: str
    generated_at: str
    database_binding: str
    envelope_sha256: str

    @field_validator("source_row_set_sha256", "manifest_sha256", "envelope_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        """Require canonical lowercase SHA-256 text."""
        return _validate_sha256(value)

    @field_validator("database_binding")
    @classmethod
    def validate_database_binding(cls, value: str) -> str:
        """Require the versioned non-secret Postgres binding form."""
        if _DATABASE_BINDING_PATTERN.fullmatch(value) is None:
            raise ValueError("invalid database binding")
        return value

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: str) -> str:
        """Require one deterministic UTC RFC3339 representation."""
        if _GENERATED_AT_PATTERN.fullmatch(value) is None:
            raise ValueError("invalid generated_at")
        try:
            parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
        except ValueError as exc:
            raise ValueError("invalid generated_at") from exc
        if parsed.tzinfo != UTC:
            raise ValueError("invalid generated_at")
        return value

    @model_validator(mode="after")
    def validate_unique_classifications(self) -> LegacyActorClassificationEnvelope:
        """Reject duplicate actors or external identities in staged evidence."""
        actor_ids = [entry.actor_id for entry in self.classifications]
        identities = [(entry.issuer, entry.subject) for entry in self.classifications]
        if len(actor_ids) != len(set(actor_ids)) or len(identities) != len(set(identities)):
            raise ValueError("duplicate classification")
        return self


class LegacyActorSnapshot(BaseModel):
    """One read-only repeatable-read view of the legacy registry."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    rows: tuple[LegacyActorRow, ...]
    database_binding: str


class LegacyActorClassificationReport(BaseModel):
    """Privacy-bounded operator result suitable for stdout evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    status: Literal["valid"] = "valid"
    mode: Literal["dry_run", "export"]
    row_count: int = Field(ge=0)
    empty_registry: bool
    source_row_set_sha256: str
    manifest_sha256: str
    database_binding: str
    envelope_sha256: str | None = None
    envelope_written: bool = False


def _model_payload(model: BaseModel, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """Convert a validated model to a JSON-compatible payload."""
    return model.model_dump(mode="json", exclude=exclude or set())


def _sorted_classifications(
    classifications: Sequence[LegacyActorClassification],
) -> tuple[LegacyActorClassification, ...]:
    """Sort classifications by canonical actor ID."""
    return tuple(sorted(classifications, key=lambda entry: entry.actor_id))


def _sorted_rows(rows: Sequence[LegacyActorRow]) -> tuple[LegacyActorRow, ...]:
    """Sort source rows by canonical actor ID."""
    return tuple(sorted(rows, key=lambda row: row.actor_id))


def canonical_manifest_bytes(manifest: LegacyActorClassificationManifest) -> bytes:
    """Return the canonical, order-independent manifest representation."""
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "classifications": [
            _model_payload(entry) for entry in _sorted_classifications(manifest.classifications)
        ],
    }
    return _canonical_json_bytes(payload)


def source_row_set_sha256(rows: Sequence[LegacyActorRow]) -> str:
    """Hash the complete sorted legacy identity projection."""
    payload = [_model_payload(row) for row in _sorted_rows(rows)]
    return _sha256(_canonical_json_bytes(payload))


def database_binding_identifier(database_name: str, database_oid: int) -> str:
    """Build a non-secret same-cluster database binding identifier."""
    if not database_name or database_oid <= 0:
        raise LegacyClassificationError("database_binding_unavailable")
    digest = _sha256(
        _canonical_json_bytes(
            {
                "database_name": database_name,
                "database_oid": database_oid,
                "schema_version": MANIFEST_SCHEMA_VERSION,
            }
        )
    )
    return f"postgres-v1:{digest}"


def _duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build an object while rejecting duplicate JSON keys."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LegacyClassificationError("invalid_json")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    """Reject JSON constants outside the standard number grammar."""
    raise LegacyClassificationError("invalid_json")


def _finite_json_float(value: str) -> float:
    """Parse a JSON float only when the runtime result remains finite."""
    parsed = float(value)
    if not math.isfinite(parsed):
        raise LegacyClassificationError("invalid_json")
    return parsed


def _strict_json(data: bytes) -> Any:
    """Parse bounded JSON without duplicate keys or non-finite values."""
    try:
        return json.loads(
            data,
            object_pairs_hook=_duplicate_object_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_finite_json_float,
        )
    except LegacyClassificationError:
        raise
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, RecursionError):
        raise LegacyClassificationError("invalid_json") from None


def _read_bounded_regular_file(path: Path) -> bytes:
    """Read one no-follow regular file within the evidence size bound."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise LegacyClassificationError("classification_file_unavailable") from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077
            or metadata.st_size > MAX_CLASSIFICATION_FILE_BYTES
        ):
            raise LegacyClassificationError("invalid_classification_file")
        chunks: list[bytes] = []
        remaining = MAX_CLASSIFICATION_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_CLASSIFICATION_FILE_BYTES:
            raise LegacyClassificationError("invalid_classification_file")
        return data
    finally:
        os.close(descriptor)


def load_manifest(path: Path) -> LegacyActorClassificationManifest:
    """Load one strict, bounded classification manifest."""
    try:
        parsed = _strict_json(_read_bounded_regular_file(path))
        manifest = LegacyActorClassificationManifest.model_validate_json(
            _canonical_json_bytes(parsed), strict=True
        )
        if len(canonical_manifest_bytes(manifest)) > MAX_CLASSIFICATION_FILE_BYTES:
            raise LegacyClassificationError("invalid_manifest")
        return manifest
    except LegacyClassificationError:
        raise
    except ValidationError:
        raise LegacyClassificationError("invalid_manifest") from None


def load_envelope(path: Path) -> LegacyActorClassificationEnvelope:
    """Load one strict, bounded confidential classification envelope."""
    try:
        raw = _read_bounded_regular_file(path)
        parsed = _strict_json(raw)
        envelope = LegacyActorClassificationEnvelope.model_validate_json(
            _canonical_json_bytes(parsed), strict=True
        )
        canonical = canonical_envelope_bytes(envelope)
        if len(canonical) > MAX_CLASSIFICATION_FILE_BYTES or raw != canonical:
            raise LegacyClassificationError("invalid_envelope")
        return envelope
    except LegacyClassificationError:
        raise
    except ValidationError:
        raise LegacyClassificationError("invalid_envelope") from None


def validate_manifest(
    manifest: LegacyActorClassificationManifest | None,
    rows: Sequence[LegacyActorRow],
) -> LegacyActorClassificationManifest:
    """Validate an explicit manifest against every live legacy identity row."""
    sorted_rows = _sorted_rows(rows)
    if not sorted_rows:
        if manifest is None:
            return LegacyActorClassificationManifest(schema_version=1, classifications=())
        if manifest.classifications:
            raise LegacyClassificationError("stale_manifest_rows")
        return manifest
    if manifest is None:
        raise LegacyClassificationError("manifest_required")

    row_by_actor = {row.actor_id: row for row in sorted_rows}
    if len(row_by_actor) != len(sorted_rows):
        raise LegacyClassificationError("duplicate_source_rows")
    manifest_by_actor = {entry.actor_id: entry for entry in manifest.classifications}
    missing = row_by_actor.keys() - manifest_by_actor.keys()
    stale = manifest_by_actor.keys() - row_by_actor.keys()
    if missing:
        raise LegacyClassificationError("missing_manifest_rows")
    if stale:
        raise LegacyClassificationError("stale_manifest_rows")
    for actor_id, row in row_by_actor.items():
        entry = manifest_by_actor[actor_id]
        if entry.issuer != row.issuer or entry.subject != row.subject:
            raise LegacyClassificationError("identity_mismatch")
    return LegacyActorClassificationManifest(
        schema_version=1,
        classifications=_sorted_classifications(manifest.classifications),
    )


def build_envelope(
    manifest: LegacyActorClassificationManifest,
    rows: Sequence[LegacyActorRow],
    *,
    database_binding: str,
    generated_at: str,
) -> LegacyActorClassificationEnvelope:
    """Build a checksum-bound canonical envelope from validated inputs."""
    validated = validate_manifest(manifest, rows)
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "classifications": [
            _model_payload(entry) for entry in _sorted_classifications(validated.classifications)
        ],
        "source_row_set_sha256": source_row_set_sha256(rows),
        "manifest_sha256": _sha256(canonical_manifest_bytes(validated)),
        "generated_at": generated_at,
        "database_binding": database_binding,
    }
    try:
        envelope = LegacyActorClassificationEnvelope.model_validate_json(
            _canonical_json_bytes(
                {
                    **payload,
                    "envelope_sha256": _sha256(_canonical_json_bytes(payload)),
                }
            ),
            strict=True,
        )
        if len(canonical_envelope_bytes(envelope)) > MAX_CLASSIFICATION_FILE_BYTES:
            raise LegacyClassificationError("envelope_too_large")
        return envelope
    except ValidationError:
        raise LegacyClassificationError("invalid_envelope_input") from None


def canonical_envelope_bytes(envelope: LegacyActorClassificationEnvelope) -> bytes:
    """Return canonical envelope bytes terminated by one newline."""
    return _canonical_json_bytes(_model_payload(envelope)) + b"\n"


def verify_envelope(
    envelope: LegacyActorClassificationEnvelope,
    rows: Sequence[LegacyActorRow],
    *,
    database_binding: str,
) -> LegacyActorClassificationEnvelope:
    """Recompute all bindings against the migration transaction's live rows."""
    payload = _model_payload(envelope, exclude={"envelope_sha256"})
    if _sha256(_canonical_json_bytes(payload)) != envelope.envelope_sha256:
        raise LegacyClassificationError("envelope_checksum_mismatch")
    manifest = LegacyActorClassificationManifest(
        schema_version=1,
        classifications=envelope.classifications,
    )
    if _sha256(canonical_manifest_bytes(manifest)) != envelope.manifest_sha256:
        raise LegacyClassificationError("manifest_checksum_mismatch")
    validated = validate_manifest(manifest, rows)
    if source_row_set_sha256(rows) != envelope.source_row_set_sha256:
        raise LegacyClassificationError("source_row_set_mismatch")
    if database_binding != envelope.database_binding:
        raise LegacyClassificationError("database_binding_mismatch")
    if validated.classifications != envelope.classifications:
        raise LegacyClassificationError("noncanonical_envelope")
    return envelope


def load_migration_envelope_from_environment(
    rows: Sequence[LegacyActorRow],
    *,
    database_binding: str,
    environ: Mapping[str, str] | None = None,
) -> LegacyActorClassificationEnvelope:
    """Load later migration evidence only from the approved environment variable."""
    source = os.environ if environ is None else environ
    raw_path = source.get(CLASSIFICATION_FILE_ENV)
    if not raw_path:
        raise LegacyClassificationError("classification_file_not_configured")
    path = Path(raw_path)
    if not path.is_absolute():
        raise LegacyClassificationError("classification_file_path_not_absolute")
    return verify_envelope(load_envelope(path), rows, database_binding=database_binding)


async def read_legacy_actor_snapshot(connection: AsyncConnection) -> LegacyActorSnapshot:
    """Read binding and identity rows from the caller's read-only transaction."""
    await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    binding_row = (
        await connection.execute(
            text(
                "SELECT current_database() AS database_name, oid AS database_oid "
                "FROM pg_database WHERE datname = current_database()"
            )
        )
    ).one()
    result = await connection.execute(
        text(
            "SELECT actor_id, external_issuer, external_subject "
            "FROM actor_identities ORDER BY actor_id ASC"
        )
    )
    try:
        rows = tuple(
            LegacyActorRow(actor_id=row[0], issuer=row[1], subject=row[2])
            for row in result.all()
        )
    except ValidationError:
        raise LegacyClassificationError("invalid_source_rows") from None
    return LegacyActorSnapshot(
        rows=rows,
        database_binding=database_binding_identifier(binding_row[0], binding_row[1]),
    )


async def snapshot_legacy_actors(engine: AsyncEngine) -> LegacyActorSnapshot:
    """Create one read-only repeatable-read legacy registry snapshot."""
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="REPEATABLE READ")
        async with connection.begin():
            return await read_legacy_actor_snapshot(connection)


def _path_within(path: Path, parent: Path) -> bool:
    """Return whether a resolved path is inside a resolved parent."""
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _protected_repository_roots(repository_root: Path, git_common_dir: Path) -> tuple[Path, ...]:
    """Discover the main and every registered linked worktree root."""
    try:
        roots = {repository_root.resolve(strict=True), git_common_dir.resolve(strict=True)}
        if git_common_dir.name != ".git":
            raise LegacyClassificationError("git_directory_unavailable")
        roots.add(git_common_dir.parent.resolve(strict=True))
        worktree_metadata = git_common_dir / "worktrees"
        if worktree_metadata.exists():
            for entry in worktree_metadata.iterdir():
                gitdir_marker = entry / "gitdir"
                raw_gitdir = gitdir_marker.read_text(encoding="utf-8").strip()
                worktree_gitdir = Path(raw_gitdir)
                if not worktree_gitdir.is_absolute():
                    worktree_gitdir = gitdir_marker.parent / worktree_gitdir
                resolved_gitdir = worktree_gitdir.resolve(strict=True)
                if resolved_gitdir.name != ".git":
                    raise LegacyClassificationError("git_directory_unavailable")
                roots.add(resolved_gitdir.parent)
    except LegacyClassificationError:
        raise
    except OSError:
        raise LegacyClassificationError("git_directory_unavailable") from None
    return tuple(sorted(roots))


def _validate_output_path(path: Path, *, repository_root: Path, git_common_dir: Path) -> Path:
    """Validate a secure envelope destination outside repository state."""
    if not path.is_absolute():
        raise LegacyClassificationError("output_path_not_absolute")
    try:
        parent = path.parent.resolve(strict=True)
        protected_roots = _protected_repository_roots(repository_root, git_common_dir)
    except OSError:
        raise LegacyClassificationError("output_parent_unavailable") from None
    destination = parent / path.name
    if any(_path_within(destination, protected) for protected in protected_roots):
        raise LegacyClassificationError("output_path_inside_repository")
    try:
        parent_metadata = os.stat(parent, follow_symlinks=False)
    except OSError:
        raise LegacyClassificationError("output_parent_unavailable") from None
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or parent_metadata.st_mode & 0o077
    ):
        raise LegacyClassificationError("output_parent_insecure")
    try:
        metadata = os.lstat(destination)
    except FileNotFoundError:
        return destination
    except OSError:
        raise LegacyClassificationError("output_path_unavailable") from None
    if not stat.S_ISREG(metadata.st_mode):
        raise LegacyClassificationError("invalid_existing_output")
    return destination


def _existing_output_matches(path: Path, expected: bytes) -> bool:
    """Compare private regular-file evidence without following symlinks."""
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
        raise LegacyClassificationError("invalid_existing_output")
    return _read_bounded_regular_file(path) == expected


def _fsync_directory(path: Path) -> None:
    """Persist a directory-entry update."""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_envelope(
    path: Path,
    envelope: LegacyActorClassificationEnvelope,
    *,
    repository_root: Path,
    git_common_dir: Path,
) -> bool:
    """Crash-safely publish one immutable envelope without overwriting evidence."""
    destination = _validate_output_path(
        path,
        repository_root=repository_root,
        git_common_dir=git_common_dir,
    )
    content = canonical_envelope_bytes(envelope)
    if destination.exists():
        if _existing_output_matches(destination, content):
            return False
        raise LegacyClassificationError("output_already_exists")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=".workstream-legacy-classification-",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            if _existing_output_matches(destination, content):
                return False
            raise LegacyClassificationError("output_already_exists") from None
        try:
            _fsync_directory(destination.parent)
        except OSError:
            try:
                destination.unlink()
                _fsync_directory(destination.parent)
            except OSError:
                pass
            raise LegacyClassificationError("output_publish_failed") from None
        return True
    except OSError:
        raise LegacyClassificationError("output_publish_failed") from None
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def build_report(
    snapshot: LegacyActorSnapshot,
    manifest: LegacyActorClassificationManifest,
    *,
    envelope: LegacyActorClassificationEnvelope | None = None,
    envelope_written: bool = False,
) -> LegacyActorClassificationReport:
    """Build a report that contains no issuer, subject, actor ID, or path."""
    return LegacyActorClassificationReport(
        mode="export" if envelope is not None else "dry_run",
        row_count=len(snapshot.rows),
        empty_registry=not snapshot.rows,
        source_row_set_sha256=source_row_set_sha256(snapshot.rows),
        manifest_sha256=_sha256(canonical_manifest_bytes(manifest)),
        database_binding=snapshot.database_binding,
        envelope_sha256=envelope.envelope_sha256 if envelope is not None else None,
        envelope_written=envelope_written,
    )
