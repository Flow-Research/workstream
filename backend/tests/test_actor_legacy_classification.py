"""Behavior tests for the legacy actor classification preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.actors import legacy_classification as legacy_classification_module
from app.modules.actors.legacy_classification import (
    CLASSIFICATION_FILE_ENV,
    MAX_CLASSIFICATION_FILE_BYTES,
    LegacyActorClassification,
    LegacyActorClassificationEnvelope,
    LegacyActorClassificationManifest,
    LegacyActorRow,
    LegacyActorSnapshot,
    LegacyClassificationError,
    build_envelope,
    build_report,
    canonical_envelope_bytes,
    canonical_manifest_bytes,
    database_binding_identifier,
    load_envelope,
    load_manifest,
    load_migration_envelope_from_environment,
    publish_envelope,
    source_row_set_sha256,
    validate_manifest,
    verify_envelope,
)
from app.schemas.auth import actor_id_from_external_identity
from scripts import legacy_actor_classification as classification_cli

ISSUER = "https://issuer.example.test"
SUBJECT = "Opaque-Subject-A"
ACTOR_ID = actor_id_from_external_identity(ISSUER, SUBJECT)
DATABASE_BINDING = database_binding_identifier("workstream", 16_384)
GENERATED_AT = "2026-07-13T12:30:00Z"


def classification(
    *,
    issuer: str = ISSUER,
    subject: str = SUBJECT,
    subject_kind: str = "human",
) -> LegacyActorClassification:
    """Build one valid classification."""
    return LegacyActorClassification(
        actor_id=actor_id_from_external_identity(issuer, subject),
        issuer=issuer,
        subject=subject,
        subject_kind=subject_kind,
    )


def legacy_row(*, issuer: str = ISSUER, subject: str = SUBJECT) -> LegacyActorRow:
    """Build one valid live-row projection."""
    return LegacyActorRow(
        actor_id=actor_id_from_external_identity(issuer, subject),
        issuer=issuer,
        subject=subject,
    )


def manifest(*entries: LegacyActorClassification) -> LegacyActorClassificationManifest:
    """Build a version-one manifest."""
    return LegacyActorClassificationManifest(schema_version=1, classifications=entries)


def envelope() -> LegacyActorClassificationEnvelope:
    """Build one valid deterministic envelope."""
    return build_envelope(
        manifest(classification()),
        (legacy_row(),),
        database_binding=DATABASE_BINDING,
        generated_at=GENERATED_AT,
    )


def write_json(path: Path, value: object) -> None:
    """Write test JSON without relying on production serialization."""
    path.write_text(json.dumps(value), encoding="utf-8")
    os.chmod(path, 0o600)


def test_manifest_and_row_hashes_are_order_independent() -> None:
    second = classification(subject="Opaque-Subject-B", subject_kind="service")
    second_row = legacy_row(subject="Opaque-Subject-B")
    forward = manifest(classification(), second)
    reverse = manifest(second, classification())

    assert canonical_manifest_bytes(forward) == canonical_manifest_bytes(reverse)
    assert source_row_set_sha256((legacy_row(), second_row)) == source_row_set_sha256(
        (second_row, legacy_row())
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("subject_kind", "agent"),
        ("subject_kind", "unknown"),
        ("actor_id", str(uuid4())),
        ("actor_id", ACTOR_ID.upper()),
        ("issuer", "http://issuer.example.test"),
        ("issuer", "https://user@issuer.example.test"),
        ("issuer", "https://issuer.example.test?key=value"),
        ("issuer", "https://issuer.example.test:abc"),
        ("issuer", "https://issuer example.test"),
        ("subject", ""),
        ("subject", "   "),
    ],
)
def test_classification_rejects_unsupported_or_noncanonical_values(
    field: str, value: str
) -> None:
    payload = {
        "actor_id": ACTOR_ID,
        "issuer": ISSUER,
        "subject": SUBJECT,
        "subject_kind": "human",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        LegacyActorClassification.model_validate(payload)


def test_classification_rejects_uuidv5_not_derived_from_exact_identity() -> None:
    with pytest.raises(ValidationError):
        LegacyActorClassification(
            actor_id=actor_id_from_external_identity(ISSUER, "different-subject"),
            issuer=ISSUER,
            subject=SUBJECT,
            subject_kind="human",
        )


def test_manifest_rejects_duplicate_actor_and_external_identity() -> None:
    entry = classification()

    with pytest.raises(ValidationError):
        manifest(entry, entry)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":1,"schema_version":1,"classifications":[]}',
        b'{"schema_version":NaN,"classifications":[]}',
        b'{"schema_version":Infinity,"classifications":[]}',
        b'{not-json}',
        b'{"schema_version":1e9999,"classifications":[]}',
        (b'{"schema_version":' + b"9" * 4_301 + b',"classifications":[]}'),
    ],
)
def test_manifest_loader_rejects_ambiguous_or_nonfinite_json(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(raw)
    os.chmod(path, 0o600)

    with pytest.raises(LegacyClassificationError, match="^invalid_json$"):
        load_manifest(path)


def test_manifest_loader_rejects_unknown_fields_without_echoing_identity(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_json(
        path,
        {
            "schema_version": 1,
            "classifications": [],
            "private-subject-value": SUBJECT,
        },
    )

    with pytest.raises(LegacyClassificationError) as captured:
        load_manifest(path)

    assert captured.value.code == "invalid_manifest"
    assert SUBJECT not in str(captured.value)
    assert ISSUER not in str(captured.value)


def test_manifest_loader_rejects_oversized_and_symlink_files(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (MAX_CLASSIFICATION_FILE_BYTES + 1))
    os.chmod(oversized, 0o600)
    target = tmp_path / "target.json"
    write_json(target, {"schema_version": 1, "classifications": []})
    symlink = tmp_path / "manifest-link.json"
    symlink.symlink_to(target)

    with pytest.raises(LegacyClassificationError, match="^invalid_classification_file$"):
        load_manifest(oversized)
    with pytest.raises(LegacyClassificationError, match="^classification_file_unavailable$"):
        load_manifest(symlink)


def test_manifest_loader_rejects_file_owned_by_another_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    write_json(path, {"schema_version": 1, "classifications": []})
    original_fstat = os.fstat

    def foreign_owner(descriptor: int) -> SimpleNamespace:
        metadata = original_fstat(descriptor)
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_size=metadata.st_size,
            st_uid=os.geteuid() + 1,
        )

    monkeypatch.setattr(os, "fstat", foreign_owner)
    with pytest.raises(LegacyClassificationError, match="^invalid_classification_file$"):
        load_manifest(path)


def test_empty_registry_needs_no_manifest_and_rejects_stale_entries() -> None:
    empty = validate_manifest(None, ())

    assert empty.classifications == ()
    with pytest.raises(LegacyClassificationError, match="^stale_manifest_rows$"):
        validate_manifest(manifest(classification()), ())


def test_nonempty_registry_requires_complete_exact_manifest() -> None:
    second_row = legacy_row(subject="Opaque-Subject-B")
    with pytest.raises(LegacyClassificationError, match="^manifest_required$"):
        validate_manifest(None, (legacy_row(),))
    with pytest.raises(LegacyClassificationError, match="^missing_manifest_rows$"):
        validate_manifest(manifest(classification()), (legacy_row(), second_row))
    with pytest.raises(LegacyClassificationError, match="^stale_manifest_rows$"):
        validate_manifest(
            manifest(classification(), classification(subject="Opaque-Subject-B")),
            (legacy_row(),),
        )


def test_manifest_subject_is_case_sensitive_and_never_normalized() -> None:
    changed_subject = SUBJECT.lower()
    changed = classification(subject=changed_subject)

    with pytest.raises(LegacyClassificationError):
        validate_manifest(manifest(changed), (legacy_row(),))


def test_manifest_rejects_duplicate_source_rows_and_exact_identity_mismatch() -> None:
    row = legacy_row()
    with pytest.raises(LegacyClassificationError, match="^duplicate_source_rows$"):
        validate_manifest(manifest(classification()), (row, row))

    mismatched = LegacyActorClassification.model_construct(
        actor_id=row.actor_id,
        issuer=row.issuer,
        subject="Different-Case",
        subject_kind="human",
    )
    unsafe_manifest = LegacyActorClassificationManifest.model_construct(
        schema_version=1,
        classifications=(mismatched,),
    )
    with pytest.raises(LegacyClassificationError, match="^identity_mismatch$"):
        validate_manifest(unsafe_manifest, (row,))


def test_envelope_generation_is_deterministic_and_checksum_binds_all_fields() -> None:
    first = envelope()
    second = envelope()
    payload = first.model_dump(mode="json")
    payload["generated_at"] = "2026-07-13T12:30:01Z"
    tampered = LegacyActorClassificationEnvelope.model_validate_json(json.dumps(payload))

    assert canonical_envelope_bytes(first) == canonical_envelope_bytes(second)
    assert canonical_envelope_bytes(first).endswith(b"\n")
    with pytest.raises(LegacyClassificationError, match="^envelope_checksum_mismatch$"):
        verify_envelope(tampered, (legacy_row(),), database_binding=DATABASE_BINDING)


@pytest.mark.parametrize(
    "generated_at",
    [
        "2026-07-13T12:30:00+00:00",
        "2026-07-13T12:30:00.000Z",
        "2026-07-13T12:30:00",
        "not-a-time",
    ],
)
def test_envelope_requires_one_canonical_generated_at(generated_at: str) -> None:
    with pytest.raises(LegacyClassificationError, match="^invalid_envelope_input$"):
        build_envelope(
            manifest(classification()),
            (legacy_row(),),
            database_binding=DATABASE_BINDING,
            generated_at=generated_at,
        )


def test_envelope_verification_rejects_row_set_and_database_drift() -> None:
    evidence = envelope()
    changed_row = legacy_row(subject="Opaque-Subject-B")

    with pytest.raises(LegacyClassificationError):
        verify_envelope(evidence, (changed_row,), database_binding=DATABASE_BINDING)
    with pytest.raises(LegacyClassificationError, match="^database_binding_mismatch$"):
        verify_envelope(
            evidence,
            (legacy_row(),),
            database_binding=database_binding_identifier("other", 16_385),
        )


def test_envelope_verification_recomputes_manifest_and_row_digests() -> None:
    original = envelope().model_dump(mode="json")
    original["manifest_sha256"] = "0" * 64
    unsigned = {key: value for key, value in original.items() if key != "envelope_sha256"}
    original["envelope_sha256"] = hashlib.sha256(
        json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    manifest_tampered = LegacyActorClassificationEnvelope.model_validate_json(
        json.dumps(original)
    )
    with pytest.raises(LegacyClassificationError, match="^manifest_checksum_mismatch$"):
        verify_envelope(
            manifest_tampered,
            (legacy_row(),),
            database_binding=DATABASE_BINDING,
        )

    original = envelope().model_dump(mode="json")
    original["source_row_set_sha256"] = "0" * 64
    unsigned = {key: value for key, value in original.items() if key != "envelope_sha256"}
    original["envelope_sha256"] = hashlib.sha256(
        json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    row_tampered = LegacyActorClassificationEnvelope.model_validate_json(json.dumps(original))
    with pytest.raises(LegacyClassificationError, match="^source_row_set_mismatch$"):
        verify_envelope(row_tampered, (legacy_row(),), database_binding=DATABASE_BINDING)


def test_database_binding_is_stable_and_does_not_disclose_database_name() -> None:
    first = database_binding_identifier("private-production-name", 99)

    assert first == database_binding_identifier("private-production-name", 99)
    assert "private-production-name" not in first
    assert first != database_binding_identifier("private-production-name", 100)
    with pytest.raises(LegacyClassificationError, match="^database_binding_unavailable$"):
        database_binding_identifier("", 0)


def test_publish_is_mode_0600_no_overwrite_and_byte_idempotent(tmp_path: Path) -> None:
    destination = tmp_path / "classification-envelope.json"
    repository = tmp_path / "repository"
    git_common = tmp_path / "main" / ".git"
    repository.mkdir()
    git_common.mkdir(parents=True)

    assert publish_envelope(
        destination,
        envelope(),
        repository_root=repository,
        git_common_dir=git_common,
    )
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert not publish_envelope(
        destination,
        envelope(),
        repository_root=repository,
        git_common_dir=git_common,
    )

    destination.write_bytes(b"different")
    os.chmod(destination, 0o600)
    with pytest.raises(LegacyClassificationError, match="^output_already_exists$"):
        publish_envelope(
            destination,
            envelope(),
            repository_root=repository,
            git_common_dir=git_common,
        )


def test_publish_rejects_relative_repo_git_symlink_and_permissive_existing_paths(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    git_common = tmp_path / "main" / ".git"
    outside = tmp_path / "outside"
    repository.mkdir()
    git_common.mkdir(parents=True)
    outside.mkdir()
    os.chmod(outside, 0o700)

    for destination in (
        Path("relative.json"),
        repository / "inside.json",
        git_common / "inside.json",
    ):
        with pytest.raises(LegacyClassificationError):
            publish_envelope(
                destination,
                envelope(),
                repository_root=repository,
                git_common_dir=git_common,
            )

    target = outside / "target.json"
    target.write_bytes(b"target")
    symlink = outside / "symlink.json"
    symlink.symlink_to(target)
    with pytest.raises(LegacyClassificationError, match="^invalid_existing_output$"):
        publish_envelope(
            symlink,
            envelope(),
            repository_root=repository,
            git_common_dir=git_common,
        )

    permissive = outside / "permissive.json"
    permissive.write_bytes(canonical_envelope_bytes(envelope()))
    os.chmod(permissive, 0o644)
    with pytest.raises(LegacyClassificationError, match="^invalid_existing_output$"):
        publish_envelope(
            permissive,
            envelope(),
            repository_root=repository,
            git_common_dir=git_common,
        )


def test_publish_rejects_main_and_every_registered_linked_worktree(tmp_path: Path) -> None:
    main = tmp_path / "main"
    common_git = main / ".git"
    current = tmp_path / "current"
    other = tmp_path / "other"
    common_git.mkdir(parents=True)
    current.mkdir()
    other.mkdir()
    for name, root in (("current", current), ("other", other)):
        metadata = common_git / "worktrees" / name
        metadata.mkdir(parents=True)
        (root / ".git").write_text("linked marker", encoding="utf-8")
        (metadata / "gitdir").write_text(f"{root / '.git'}\n", encoding="utf-8")

    for destination in (main / "leak.json", current / "leak.json", other / "leak.json"):
        with pytest.raises(LegacyClassificationError, match="^output_path_inside_repository$"):
            publish_envelope(
                destination,
                envelope(),
                repository_root=current,
                git_common_dir=common_git,
            )


def test_loaders_require_owner_only_input_permissions(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    envelope_path = tmp_path / "envelope.json"
    write_json(manifest_path, {"schema_version": 1, "classifications": []})
    envelope_path.write_bytes(canonical_envelope_bytes(envelope()))
    os.chmod(manifest_path, 0o644)
    os.chmod(envelope_path, 0o640)

    with pytest.raises(LegacyClassificationError, match="^invalid_classification_file$"):
        load_manifest(manifest_path)
    with pytest.raises(LegacyClassificationError, match="^invalid_classification_file$"):
        load_envelope(envelope_path)


def test_publish_requires_owner_only_output_directory(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    git_common = tmp_path / "main" / ".git"
    shared = tmp_path / "shared"
    repository.mkdir()
    git_common.mkdir(parents=True)
    shared.mkdir(mode=0o770)

    with pytest.raises(LegacyClassificationError, match="^output_parent_insecure$"):
        publish_envelope(
            shared / "envelope.json",
            envelope(),
            repository_root=repository,
            git_common_dir=git_common,
        )

def test_failed_atomic_publish_leaves_no_destination_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "classification-envelope.json"
    repository = tmp_path / "repository"
    git_common = tmp_path / "main" / ".git"
    repository.mkdir()
    git_common.mkdir(parents=True)

    def fail_link(*_args, **_kwargs) -> None:
        raise OSError("simulated publish interruption")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(LegacyClassificationError, match="^output_publish_failed$"):
        publish_envelope(
            destination,
            envelope(),
            repository_root=repository,
            git_common_dir=git_common,
        )

    assert not destination.exists()
    assert not list(tmp_path.glob(".workstream-legacy-classification-*"))


def test_post_link_fsync_failure_rolls_back_published_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "classification-envelope.json"
    repository = tmp_path / "repository"
    git_common = tmp_path / "main" / ".git"
    repository.mkdir()
    git_common.mkdir(parents=True)

    def fail_fsync(_path: Path) -> None:
        raise OSError("simulated directory fsync failure")

    monkeypatch.setattr(legacy_classification_module, "_fsync_directory", fail_fsync)
    with pytest.raises(LegacyClassificationError, match="^output_publish_failed$"):
        publish_envelope(
            destination,
            envelope(),
            repository_root=repository,
            git_common_dir=git_common,
        )

    assert not destination.exists()
    assert not list(tmp_path.glob(".workstream-legacy-classification-*"))


def test_migration_handoff_uses_only_absolute_environment_path(tmp_path: Path) -> None:
    path = tmp_path / "classification-envelope.json"
    path.write_bytes(canonical_envelope_bytes(envelope()))
    os.chmod(path, 0o600)

    loaded = load_migration_envelope_from_environment(
        (legacy_row(),),
        database_binding=DATABASE_BINDING,
        environ={CLASSIFICATION_FILE_ENV: str(path)},
    )

    assert loaded == envelope()
    with pytest.raises(LegacyClassificationError, match="^classification_file_not_configured$"):
        load_migration_envelope_from_environment(
            (legacy_row(),), database_binding=DATABASE_BINDING, environ={}
        )
    with pytest.raises(LegacyClassificationError, match="^classification_file_path_not_absolute$"):
        load_migration_envelope_from_environment(
            (legacy_row(),),
            database_binding=DATABASE_BINDING,
            environ={CLASSIFICATION_FILE_ENV: "relative.json"},
        )


def test_migration_handoff_reads_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "classification-envelope.json"
    path.write_bytes(canonical_envelope_bytes(envelope()))
    os.chmod(path, 0o600)
    monkeypatch.setenv(CLASSIFICATION_FILE_ENV, str(path))

    assert (
        load_migration_envelope_from_environment(
            (legacy_row(),), database_binding=DATABASE_BINDING
        )
        == envelope()
    )


def test_migration_verifier_import_does_not_require_live_actor_orm() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.modules['app.modules.actors.models'] = None; "
                "import app.modules.actors.legacy_classification"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_envelope_loader_rejects_unknown_or_tampered_payload_without_echo(tmp_path: Path) -> None:
    path = tmp_path / "envelope.json"
    payload = envelope().model_dump(mode="json")
    payload["unexpected"] = SUBJECT
    write_json(path, payload)

    with pytest.raises(LegacyClassificationError) as captured:
        load_envelope(path)

    assert captured.value.code == "invalid_envelope"
    assert SUBJECT not in str(captured.value)


def test_envelope_loader_rejects_duplicate_classifications(tmp_path: Path) -> None:
    path = tmp_path / "envelope.json"
    payload = envelope().model_dump(mode="json")
    payload["classifications"] *= 2
    write_json(path, payload)

    with pytest.raises(LegacyClassificationError, match="^invalid_envelope$"):
        load_envelope(path)


def test_envelope_loader_requires_exact_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "envelope.json"
    path.write_text(json.dumps(envelope().model_dump(mode="json"), indent=7), encoding="utf-8")
    os.chmod(path, 0o600)

    with pytest.raises(LegacyClassificationError, match="^invalid_envelope$"):
        load_envelope(path)


def test_report_is_privacy_bounded_and_default_mode_is_dry_run() -> None:
    snapshot = LegacyActorSnapshot(rows=(legacy_row(),), database_binding=DATABASE_BINDING)
    report = build_report(snapshot, manifest(classification()))
    serialized = report.model_dump_json()

    assert report.mode == "dry_run"
    assert not report.envelope_written
    assert SUBJECT not in serialized
    assert ISSUER not in serialized
    assert ACTOR_ID not in serialized


def test_cli_git_common_directory_supports_main_and_linked_worktrees(tmp_path: Path) -> None:
    main_repository = tmp_path / "main"
    main_repository.mkdir()
    (main_repository / ".git").mkdir()
    assert classification_cli._git_common_directory(main_repository) == main_repository / ".git"

    linked_repository = tmp_path / "linked"
    linked_repository.mkdir()
    common = tmp_path / "common" / ".git"
    worktree_git = common / "worktrees" / "linked"
    worktree_git.mkdir(parents=True)
    (linked_repository / ".git").write_text(f"gitdir: {worktree_git}\n", encoding="utf-8")
    assert classification_cli._git_common_directory(linked_repository) == common


def test_cli_git_common_directory_and_parser_fail_privately(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").write_text("invalid", encoding="utf-8")
    with pytest.raises(LegacyClassificationError, match="^git_directory_unavailable$"):
        classification_cli._git_common_directory(repository)
    with pytest.raises(LegacyClassificationError, match="^invalid_arguments$"):
        classification_cli._parser().parse_args(["--unknown-private-path", SUBJECT])


@pytest.mark.asyncio
async def test_cli_execute_defaults_to_no_write_and_exports_only_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = LegacyActorSnapshot(rows=(), database_binding=DATABASE_BINDING)

    async def fake_snapshot(_engine) -> LegacyActorSnapshot:
        return snapshot

    monkeypatch.setattr(classification_cli, "get_engine", object)
    monkeypatch.setattr(classification_cli, "snapshot_legacy_actors", fake_snapshot)
    dry_run = await classification_cli._execute(
        argparse.Namespace(manifest=None, output=None, generated_at=None)
    )
    assert dry_run["mode"] == "dry_run"
    assert not list(tmp_path.iterdir())

    output = tmp_path / "empty-envelope.json"
    monkeypatch.setattr(classification_cli, "REPOSITORY_ROOT", Path(__file__).parents[2])
    exported = await classification_cli._execute(
        argparse.Namespace(manifest=None, output=output, generated_at=GENERATED_AT)
    )
    assert exported["mode"] == "export"
    assert exported["envelope_written"]
    assert output.exists()


@pytest.mark.asyncio
async def test_cli_execute_requires_generated_at_only_for_export() -> None:
    with pytest.raises(LegacyClassificationError, match="^generated_at_requires_output$"):
        await classification_cli._execute(
            argparse.Namespace(manifest=None, output=None, generated_at=GENERATED_AT)
        )
    with pytest.raises(LegacyClassificationError, match="^generated_at_required$"):
        await classification_cli._execute(
            argparse.Namespace(manifest=None, output=Path("unused"), generated_at=None)
        )


def test_cli_main_emits_bounded_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def successful(_args) -> dict:
        return {"status": "valid"}

    async def dispose() -> None:
        return None

    monkeypatch.setattr(classification_cli, "_execute", successful)
    monkeypatch.setattr(classification_cli, "dispose_engine", dispose)
    assert classification_cli.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "valid"}

    async def bounded_failure(_args) -> dict:
        raise LegacyClassificationError("generated_at_required")

    monkeypatch.setattr(classification_cli, "_execute", bounded_failure)
    assert classification_cli.main(["--output", SUBJECT]) == 2
    captured = capsys.readouterr()
    assert SUBJECT not in captured.err
    assert json.loads(captured.err) == {"error": "generated_at_required", "status": "error"}


def test_cli_main_bounds_unexpected_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fail(_args) -> dict:
        raise RuntimeError(SUBJECT)

    async def dispose() -> None:
        return None

    monkeypatch.setattr(classification_cli, "_execute", fail)
    monkeypatch.setattr(classification_cli, "dispose_engine", dispose)

    assert classification_cli.main([]) == 2
    captured = capsys.readouterr()
    assert SUBJECT not in captured.err
    assert json.loads(captured.err) == {
        "error": "database_operation_failed",
        "status": "error",
    }


def test_cli_main_bounds_database_cleanup_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def successful(_args) -> dict:
        return {"status": "valid"}

    async def fail_cleanup() -> None:
        raise RuntimeError(SUBJECT)

    monkeypatch.setattr(classification_cli, "_execute", successful)
    monkeypatch.setattr(classification_cli, "dispose_engine", fail_cleanup)

    assert classification_cli.main([]) == 2
    captured = capsys.readouterr()
    assert SUBJECT not in captured.err
    assert json.loads(captured.err) == {
        "error": "database_cleanup_failed",
        "status": "error",
    }


@pytest.mark.parametrize(
    ("primary_failure", "expected_result", "expected_error"),
    [
        (KeyboardInterrupt(), 130, "interrupted"),
        (LegacyClassificationError("generated_at_required"), 2, "generated_at_required"),
        (RuntimeError(SUBJECT), 2, "database_operation_failed"),
    ],
)
def test_cli_cleanup_preserves_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    primary_failure: BaseException,
    expected_result: int,
    expected_error: str,
) -> None:
    async def fail(_args) -> dict:
        raise primary_failure

    async def fail_cleanup() -> None:
        raise RuntimeError(SUBJECT)

    monkeypatch.setattr(classification_cli, "_execute", fail)
    monkeypatch.setattr(classification_cli, "dispose_engine", fail_cleanup)

    assert classification_cli.main([]) == expected_result
    captured = capsys.readouterr()
    assert captured.out == ""
    assert SUBJECT not in captured.err
    assert json.loads(captured.err) == {"error": expected_error, "status": "error"}
