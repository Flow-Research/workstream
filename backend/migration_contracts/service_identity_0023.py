"""Frozen confidential mapping contract for revision 0023."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum, unique
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine



@unique
class ServiceIdentity(StrEnum):
    """Revision-0023 fixed service identity values."""

    ARTIFACT_VERIFIER = "workstream.artifact.verifier"
    ARTIFACT_PUT_RESOLVER = "workstream.artifact.put_resolver"
    ARTIFACT_SCHEDULER = "workstream.artifact.scheduler"
    ARTIFACT_BINDING = "workstream.artifact.binding"
    ARTIFACT_GUIDE_READER = "workstream.artifact.guide_reader"
    ARTIFACT_MATERIALIZER = "workstream.artifact.materializer"
    ARTIFACT_CHECKER_OUTPUT = "workstream.artifact.checker_output"


SERVICE_IDENTITIES = frozenset(ServiceIdentity)
SERVICE_IDENTITY_VALUES = tuple(identity.value for identity in ServiceIdentity)

MAPPING_FILE_ENV = "WORKSTREAM_SERVICE_ACTOR_IDENTITY_MAPPING_FILE"
MAX_MAPPING_FILE_BYTES = 64 * 1024
MAX_MAPPINGS = len(SERVICE_IDENTITIES)
MAPPING_SCHEMA_VERSION = 1
_DATABASE_BINDING_PATTERN = re.compile(r"postgres-v1:[0-9a-f]{64}")
_GENERATED_AT_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class ServiceIdentityMappingError(RuntimeError):
    """Privacy-bounded mapping failure safe for migration and CLI output."""

    def __init__(self, code: str, *, count: int | None = None) -> None:
        self.code = code
        self.count = count
        super().__init__(code)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def database_binding_identifier(database_name: str, database_oid: int) -> str:
    """Build the revision-0023 same-database binding identifier."""
    if not database_name or database_oid <= 0:
        raise ServiceIdentityMappingError("database_binding_unavailable")
    digest = _sha256(
        _canonical_bytes(
            {
                "database_name": database_name,
                "database_oid": database_oid,
                "schema_version": MAPPING_SCHEMA_VERSION,
            }
        )
    )
    return f"postgres-v1:{digest}"


def _canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("invalid actor profile id") from exc
    if str(parsed) != value:
        raise ValueError("invalid actor profile id")
    return value


def _canonical_issuer(value: str) -> str:
    if not value or len(value) > 200 or value.strip() != value:
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
        or any(character.isspace() or ord(character) < 0x20 for character in value)
    ):
        raise ValueError("invalid issuer")
    return value


def _canonical_subject(value: str) -> str:
    if not value or not value.strip() or len(value) > 200:
        raise ValueError("invalid subject")
    return value


class ServiceActorIdentityMapping(BaseModel):
    """One operator-approved fixed identity for an exact existing service link."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_profile_id: str
    issuer: str
    subject: str
    service_identity: ServiceIdentity

    @field_validator("actor_profile_id")
    @classmethod
    def validate_actor_profile_id(cls, value: str) -> str:
        return _canonical_uuid(value)

    @field_validator("issuer")
    @classmethod
    def validate_issuer(cls, value: str) -> str:
        return _canonical_issuer(value)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        return _canonical_subject(value)


class ServiceActorIdentityMappingDraft(BaseModel):
    """Strict operator-authored choices before database binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    mappings: tuple[ServiceActorIdentityMapping, ...] = Field(max_length=MAX_MAPPINGS)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, value: Any) -> int:
        if type(value) is not int or value != MAPPING_SCHEMA_VERSION:
            raise ValueError("invalid schema version")
        return value

    @model_validator(mode="after")
    def validate_uniqueness(self) -> ServiceActorIdentityMappingDraft:
        actor_ids = [row.actor_profile_id for row in self.mappings]
        external_ids = [(row.issuer, row.subject) for row in self.mappings]
        identities = [row.service_identity for row in self.mappings]
        if (
            len(actor_ids) != len(set(actor_ids))
            or len(external_ids) != len(set(external_ids))
            or len(identities) != len(set(identities))
        ):
            raise ValueError("duplicate mapping")
        return self


class ExistingServiceActorRow(BaseModel):
    """Privacy-sensitive locked database projection used only during mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_profile_id: str
    issuer: str
    subject: str

    @field_validator("actor_profile_id")
    @classmethod
    def validate_actor_profile_id(cls, value: str) -> str:
        return _canonical_uuid(value)

    @field_validator("issuer")
    @classmethod
    def validate_issuer(cls, value: str) -> str:
        return _canonical_issuer(value)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        return _canonical_subject(value)


class ServiceActorIdentityMappingEnvelope(BaseModel):
    """Confidential exact mapping bound to one locked database snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    mappings: tuple[ServiceActorIdentityMapping, ...] = Field(max_length=MAX_MAPPINGS)
    source_row_set_sha256: str
    manifest_sha256: str
    generated_at: str
    database_binding: str
    envelope_sha256: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, value: Any) -> int:
        if type(value) is not int or value != MAPPING_SCHEMA_VERSION:
            raise ValueError("invalid schema version")
        return value

    @model_validator(mode="after")
    def validate_mapping_uniqueness(self) -> ServiceActorIdentityMappingEnvelope:
        ServiceActorIdentityMappingDraft(schema_version=1, mappings=self.mappings)
        for digest in (
            self.source_row_set_sha256,
            self.manifest_sha256,
            self.envelope_sha256,
        ):
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("invalid digest")
        if _DATABASE_BINDING_PATTERN.fullmatch(self.database_binding) is None:
            raise ValueError("invalid database binding")
        if _GENERATED_AT_PATTERN.fullmatch(self.generated_at) is None:
            raise ValueError("invalid generated_at")
        try:
            parsed = datetime.fromisoformat(self.generated_at.removesuffix("Z") + "+00:00")
        except ValueError as exc:
            raise ValueError("invalid generated_at") from exc
        if parsed.tzinfo != UTC or parsed.microsecond:
            raise ValueError("invalid generated_at")
        return self


class ServiceActorIdentitySnapshot(BaseModel):
    """Exact existing service rows plus a non-secret database binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: tuple[ExistingServiceActorRow, ...]
    database_binding: str


class ServiceActorIdentityMappingReport(BaseModel):
    """Bounded CLI report without actor or external identity material."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["valid"] = "valid"
    mapped_count: int
    source_row_set_sha256: str
    manifest_sha256: str
    envelope_sha256: str | None = None
    database_binding: str
    envelope_written: bool = False


def _mapping_payload(rows: Sequence[ServiceActorIdentityMapping]) -> list[dict[str, str]]:
    return [
        row.model_dump(mode="json")
        for row in sorted(rows, key=lambda item: item.actor_profile_id)
    ]


def _source_payload(rows: Sequence[ExistingServiceActorRow]) -> list[dict[str, str]]:
    return [
        row.model_dump(mode="json")
        for row in sorted(rows, key=lambda item: item.actor_profile_id)
    ]


def source_row_set_sha256(rows: Sequence[ExistingServiceActorRow]) -> str:
    """Digest the exact private source set without exposing it."""
    return _sha256(_canonical_bytes(_source_payload(rows)))


def canonical_draft_bytes(draft: ServiceActorIdentityMappingDraft) -> bytes:
    """Serialize operator choices deterministically for review and hashing."""
    return _canonical_bytes(
        {"schema_version": draft.schema_version, "mappings": _mapping_payload(draft.mappings)}
    )


def _envelope_payload(envelope: ServiceActorIdentityMappingEnvelope) -> dict[str, Any]:
    return {
        "schema_version": envelope.schema_version,
        "mappings": _mapping_payload(envelope.mappings),
        "source_row_set_sha256": envelope.source_row_set_sha256,
        "manifest_sha256": envelope.manifest_sha256,
        "generated_at": envelope.generated_at,
        "database_binding": envelope.database_binding,
    }


def canonical_envelope_bytes(envelope: ServiceActorIdentityMappingEnvelope) -> bytes:
    """Serialize a complete envelope deterministically."""
    return _canonical_bytes(envelope.model_dump(mode="json"))


def validate_draft(
    draft: ServiceActorIdentityMappingDraft,
    rows: Sequence[ExistingServiceActorRow],
) -> ServiceActorIdentityMappingDraft:
    """Require a one-to-one mapping for the exact existing service row set."""
    if len(rows) > MAX_MAPPINGS:
        raise ServiceIdentityMappingError("service_inventory_exceeds_registry", count=len(rows))
    source = {(row.actor_profile_id, row.issuer, row.subject) for row in rows}
    proposed = {
        (row.actor_profile_id, row.issuer, row.subject) for row in draft.mappings
    }
    if source != proposed:
        raise ServiceIdentityMappingError("service_mapping_source_mismatch", count=len(rows))
    return draft


def build_envelope(
    draft: ServiceActorIdentityMappingDraft,
    rows: Sequence[ExistingServiceActorRow],
    *,
    database_binding: str,
    generated_at: str,
) -> ServiceActorIdentityMappingEnvelope:
    """Bind validated operator choices to one exact database snapshot."""
    validate_draft(draft, rows)
    provisional = ServiceActorIdentityMappingEnvelope(
        schema_version=MAPPING_SCHEMA_VERSION,
        mappings=tuple(sorted(draft.mappings, key=lambda row: row.actor_profile_id)),
        source_row_set_sha256=source_row_set_sha256(rows),
        manifest_sha256=_sha256(canonical_draft_bytes(draft)),
        generated_at=generated_at,
        database_binding=database_binding,
        envelope_sha256="0" * 64,
    )
    return provisional.model_copy(
        update={"envelope_sha256": _sha256(_canonical_bytes(_envelope_payload(provisional)))}
    )


def verify_envelope(
    envelope: ServiceActorIdentityMappingEnvelope,
    rows: Sequence[ExistingServiceActorRow],
    *,
    database_binding: str,
) -> ServiceActorIdentityMappingEnvelope:
    """Verify checksums, database binding, and the complete current source set."""
    draft = ServiceActorIdentityMappingDraft(
        schema_version=MAPPING_SCHEMA_VERSION,
        mappings=envelope.mappings,
    )
    validate_draft(draft, rows)
    expected = build_envelope(
        draft,
        rows,
        database_binding=database_binding,
        generated_at=envelope.generated_at,
    )
    if expected != envelope:
        raise ServiceIdentityMappingError("service_mapping_envelope_mismatch", count=len(rows))
    return envelope


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _read_private_json_bytes(path: Path) -> bytes:
    """Read one owner-only regular file without following symlinks."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise ServiceIdentityMappingError("service_mapping_file_unavailable") from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size > MAX_MAPPING_FILE_BYTES
        ):
            raise ServiceIdentityMappingError("service_mapping_file_insecure")
        chunks: list[bytes] = []
        remaining = MAX_MAPPING_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(data) > MAX_MAPPING_FILE_BYTES:
        raise ServiceIdentityMappingError("service_mapping_file_too_large")
    return data


def _parse_private_json(data: bytes) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise ServiceIdentityMappingError("service_mapping_file_invalid") from None


def _git_common_directory(repository_root: Path) -> Path | None:
    marker = repository_root / ".git"
    if marker.is_dir():
        return marker.resolve()
    try:
        value = marker.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        raise ServiceIdentityMappingError("git_directory_unavailable") from None
    prefix = "gitdir: "
    if not value.startswith(prefix):
        raise ServiceIdentityMappingError("git_directory_unavailable")
    worktree_git = Path(value.removeprefix(prefix))
    if not worktree_git.is_absolute():
        worktree_git = marker.parent / worktree_git
    resolved = worktree_git.resolve()
    if resolved.parent.name != "worktrees":
        raise ServiceIdentityMappingError("git_directory_unavailable")
    return resolved.parent.parent


def protected_mapping_roots(repository_root: Path) -> tuple[Path, ...]:
    """Return every linked worktree root plus shared Git metadata."""
    common = _git_common_directory(repository_root)
    roots = {repository_root.resolve()}
    if common is None:
        return tuple(roots)
    roots.update({common, common.parent.resolve()})
    worktrees = common / "worktrees"
    if worktrees.exists():
        try:
            metadata_directories = tuple(worktrees.iterdir())
        except OSError:
            raise ServiceIdentityMappingError("git_directory_unavailable") from None
        for metadata in metadata_directories:
            marker = metadata / "gitdir"
            try:
                git_file = Path(marker.read_text(encoding="utf-8").strip())
            except OSError:
                raise ServiceIdentityMappingError("git_directory_unavailable") from None
            if git_file.name != ".git" or not git_file.is_absolute():
                raise ServiceIdentityMappingError("git_directory_unavailable")
            roots.add(git_file.parent.resolve())
    return tuple(sorted(roots, key=str))


def validate_mapping_path(
    path: Path,
    *,
    repository_root: Path,
    output: bool = False,
) -> Path:
    """Require an absolute path outside every repository and Git root."""
    if not path.is_absolute():
        raise ServiceIdentityMappingError("service_mapping_path_forbidden")
    try:
        resolved = path.parent.resolve(strict=True) / path.name
        if not output and not resolved.exists():
            raise OSError("missing input")
    except OSError:
        raise ServiceIdentityMappingError("service_mapping_path_unavailable") from None
    if any(
        resolved == root or resolved.is_relative_to(root)
        for root in protected_mapping_roots(repository_root)
    ):
        raise ServiceIdentityMappingError("service_mapping_path_forbidden")
    return resolved


def load_draft(path: Path) -> ServiceActorIdentityMappingDraft:
    """Load one strict confidential operator draft."""
    try:
        data = _read_private_json_bytes(path)
        draft = ServiceActorIdentityMappingDraft.model_validate(_parse_private_json(data))
        if data != canonical_draft_bytes(draft) + b"\n":
            raise ValueError("noncanonical draft")
        return draft
    except ServiceIdentityMappingError:
        raise
    except Exception:
        raise ServiceIdentityMappingError("service_mapping_draft_invalid") from None


def load_envelope(path: Path) -> ServiceActorIdentityMappingEnvelope:
    """Load one strict confidential database-bound envelope."""
    try:
        data = _read_private_json_bytes(path)
        envelope = ServiceActorIdentityMappingEnvelope.model_validate(_parse_private_json(data))
        if data != canonical_envelope_bytes(envelope) + b"\n":
            raise ValueError("noncanonical envelope")
        return envelope
    except ServiceIdentityMappingError:
        raise
    except Exception:
        raise ServiceIdentityMappingError("service_mapping_envelope_invalid") from None


def publish_envelope(path: Path, envelope: ServiceActorIdentityMappingEnvelope) -> None:
    """Create one owner-only envelope without overwriting or following links."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        raise ServiceIdentityMappingError("service_mapping_output_unavailable") from None
    try:
        remaining = memoryview(canonical_envelope_bytes(envelope) + b"\n")
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short write")
            remaining = remaining[written:]
        os.fsync(descriptor)
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
        raise ServiceIdentityMappingError("service_mapping_output_failed") from None
    finally:
        os.close(descriptor)


async def read_existing_service_rows(connection: AsyncConnection) -> ServiceActorIdentitySnapshot:
    """Read the exact existing service/link set and bind it to this database."""
    raw_rows = (
        await connection.execute(
            text(
                "select p.id, l.issuer, l.subject from actor_profiles p "
                "join actor_identity_links l on l.actor_profile_id=p.id "
                "where p.actor_kind='service' order by p.id"
            )
        )
    ).all()
    database_name, database_oid = (
        await connection.execute(
            text(
                "select current_database(), oid from pg_database "
                "where datname=current_database()"
            )
        )
    ).one()
    try:
        rows = tuple(
            ExistingServiceActorRow(
                actor_profile_id=row[0],
                issuer=row[1],
                subject=row[2],
            )
            for row in raw_rows
        )
    except Exception:
        raise ServiceIdentityMappingError("service_mapping_source_invalid") from None
    return ServiceActorIdentitySnapshot(
        rows=rows,
        database_binding=database_binding_identifier(database_name, database_oid),
    )


async def snapshot_existing_service_rows(engine: AsyncEngine) -> ServiceActorIdentitySnapshot:
    """Read one non-mutating snapshot for the operator tool."""
    async with engine.connect() as connection:
        return await read_existing_service_rows(connection)


def load_migration_mapping(
    rows: Sequence[ExistingServiceActorRow],
    *,
    database_binding: str,
    repository_root: Path,
) -> ServiceActorIdentityMappingEnvelope | None:
    """Load the required exact mapping from the migration-only environment."""
    raw_path = os.environ.get(MAPPING_FILE_ENV)
    if not rows:
        if raw_path:
            raise ServiceIdentityMappingError("service_mapping_not_required", count=0)
        return None
    if not raw_path:
        raise ServiceIdentityMappingError("service_mapping_required", count=len(rows))
    return verify_envelope(
        load_envelope(
            validate_mapping_path(Path(raw_path), repository_root=repository_root)
        ),
        rows,
        database_binding=database_binding,
    )


def build_report(
    snapshot: ServiceActorIdentitySnapshot,
    draft: ServiceActorIdentityMappingDraft,
    *,
    envelope: ServiceActorIdentityMappingEnvelope | None = None,
    envelope_written: bool = False,
) -> ServiceActorIdentityMappingReport:
    """Return only bounded counts, bindings, and non-secret digests."""
    return ServiceActorIdentityMappingReport(
        mapped_count=len(draft.mappings),
        source_row_set_sha256=source_row_set_sha256(snapshot.rows),
        manifest_sha256=_sha256(canonical_draft_bytes(draft)),
        envelope_sha256=envelope.envelope_sha256 if envelope else None,
        database_binding=snapshot.database_binding,
        envelope_written=envelope_written,
    )
