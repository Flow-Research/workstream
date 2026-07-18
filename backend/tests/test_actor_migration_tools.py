"""Behavior tests for fixed service-identity migration evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.actors import service_identity_migration as identity_migration
from app.modules.actors.legacy_classification import database_binding_identifier
from app.modules.actors.service_identities import SERVICE_IDENTITY_VALUES, ServiceIdentity
from app.modules.actors.service_identity_migration import (
    MAPPING_FILE_ENV,
    MAX_MAPPINGS,
    ExistingServiceActorRow,
    ServiceActorIdentityMapping,
    ServiceActorIdentityMappingDraft,
    ServiceActorIdentityMappingEnvelope,
    ServiceIdentityMappingError,
    build_envelope,
    build_report,
    canonical_draft_bytes,
    load_draft,
    load_envelope,
    load_migration_mapping,
    publish_envelope,
    protected_mapping_roots,
    source_row_set_sha256,
    validate_draft,
    validate_mapping_path,
    verify_envelope,
)
from scripts import service_actor_identity_mapping as mapping_cli

ISSUER = "https://identity.example.test"
SUBJECT = "Opaque-Service-Subject"
ACTOR_ID = "11111111-1111-4111-8111-111111111111"
DATABASE_BINDING = database_binding_identifier("workstream", 16_384)
GENERATED_AT = "2026-07-16T12:00:00Z"


def source_row(
    *,
    actor_profile_id: str = ACTOR_ID,
    subject: str = SUBJECT,
) -> ExistingServiceActorRow:
    return ExistingServiceActorRow(
        actor_profile_id=actor_profile_id,
        issuer=ISSUER,
        subject=subject,
    )


def mapping(
    *,
    actor_profile_id: str = ACTOR_ID,
    subject: str = SUBJECT,
    service_identity: ServiceIdentity = ServiceIdentity.ARTIFACT_VERIFIER,
) -> ServiceActorIdentityMapping:
    return ServiceActorIdentityMapping(
        actor_profile_id=actor_profile_id,
        issuer=ISSUER,
        subject=subject,
        service_identity=service_identity,
    )


def draft(*rows: ServiceActorIdentityMapping) -> ServiceActorIdentityMappingDraft:
    return ServiceActorIdentityMappingDraft(schema_version=1, mappings=rows)


def envelope():
    return build_envelope(
        draft(mapping()),
        (source_row(),),
        database_binding=DATABASE_BINDING,
        generated_at=GENERATED_AT,
    )


def write_private_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def test_fixed_service_identity_registry_is_exact() -> None:
    assert SERVICE_IDENTITY_VALUES == (
        "workstream.artifact.verifier",
        "workstream.artifact.put_resolver",
        "workstream.artifact.scheduler",
        "workstream.artifact.binding",
        "workstream.artifact.guide_reader",
        "workstream.artifact.materializer",
        "workstream.artifact.checker_output",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_profile_id", str(uuid4()).upper()),
        ("actor_profile_id", "not-a-uuid"),
        ("issuer", "http://identity.example.test"),
        ("issuer", "https://user@identity.example.test"),
        ("issuer", "https://identity.example.test?private=true"),
        ("subject", ""),
        ("subject", "   "),
        ("service_identity", "workstream.artifact.unknown"),
    ],
)
def test_mapping_rejects_noncanonical_or_unknown_values(field: str, value: str) -> None:
    payload = mapping().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        ServiceActorIdentityMapping.model_validate(payload)


@pytest.mark.parametrize(
    "issuer",
    [
        "",
        " https://identity.example.test",
        "https://identity.example.test:invalid",
        "https://identity.example.test/path\nsegment",
    ],
)
def test_mapping_rejects_ambiguous_issuer_bytes(issuer: str) -> None:
    payload = mapping().model_dump(mode="json")
    payload["issuer"] = issuer
    with pytest.raises(ValidationError):
        ServiceActorIdentityMapping.model_validate(payload)


def test_draft_rejects_duplicate_profile_external_identity_and_fixed_identity() -> None:
    duplicate = mapping()
    with pytest.raises(ValidationError):
        draft(duplicate, duplicate)
    with pytest.raises(ValidationError):
        draft(
            duplicate,
            mapping(
                actor_profile_id="22222222-2222-4222-8222-222222222222",
                subject="Other-Subject",
            ),
        )


def test_exact_mapping_accepts_zero_subset_and_all_seven_rows() -> None:
    assert validate_draft(draft(), ()) == draft()
    assert validate_draft(draft(mapping()), (source_row(),)) == draft(mapping())
    source_rows = tuple(
        source_row(
            actor_profile_id=f"00000000-0000-4000-8000-{index:012d}",
            subject=f"subject-{index}",
        )
        for index in range(1, 8)
    )
    mapped_rows = tuple(
        mapping(
            actor_profile_id=row.actor_profile_id,
            subject=row.subject,
            service_identity=identity,
        )
        for row, identity in zip(source_rows, ServiceIdentity, strict=True)
    )
    assert validate_draft(draft(*mapped_rows), source_rows).mappings == mapped_rows


def test_exact_mapping_rejects_missing_extra_or_changed_private_source() -> None:
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_source_mismatch"):
        validate_draft(draft(), (source_row(),))
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_source_mismatch"):
        validate_draft(draft(mapping()), ())
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_source_mismatch"):
        validate_draft(draft(mapping(subject=SUBJECT.lower())), (source_row(),))


def test_exact_mapping_rejects_inventory_larger_than_closed_registry() -> None:
    rows = tuple(
        source_row(
            actor_profile_id=f"00000000-0000-4000-8000-{index:012d}",
            subject=f"subject-{index}",
        )
        for index in range(1, MAX_MAPPINGS + 2)
    )
    with pytest.raises(
        ServiceIdentityMappingError,
        match="service_inventory_exceeds_registry",
    ) as captured:
        validate_draft(draft(), rows)
    assert captured.value.count == MAX_MAPPINGS + 1


def test_envelope_has_stable_known_answer_and_detects_any_binding_drift() -> None:
    built = envelope()
    assert built.envelope_sha256 == "1ca678ece8ec42fbd119209b963e3d25b36fc9c60dc00e9788328d4ed517a2d8"
    assert verify_envelope(
        built,
        (source_row(),),
        database_binding=DATABASE_BINDING,
    ) == built
    with pytest.raises(ServiceIdentityMappingError, match="envelope_mismatch"):
        verify_envelope(
            built,
            (source_row(),),
            database_binding=database_binding_identifier("other", 16_384),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 1.0),
        ("source_row_set_sha256", "g" * 64),
        ("manifest_sha256", "0" * 63),
        ("database_binding", "postgres-v1:not-a-digest"),
        ("generated_at", "2026-02-31T12:00:00Z"),
        ("generated_at", "2026-07-16 12:00:00Z"),
    ],
)
def test_envelope_rejects_noncanonical_or_impossible_metadata(
    field: str,
    value: object,
) -> None:
    payload = envelope().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        ServiceActorIdentityMappingEnvelope.model_validate(payload)


def test_canonical_hashes_ignore_input_order() -> None:
    first = source_row()
    second = source_row(
        actor_profile_id="22222222-2222-4222-8222-222222222222",
        subject="Second",
    )
    first_mapping = mapping()
    second_mapping = mapping(
        actor_profile_id=second.actor_profile_id,
        subject=second.subject,
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
    )
    assert source_row_set_sha256((first, second)) == source_row_set_sha256((second, first))
    assert canonical_draft_bytes(draft(first_mapping, second_mapping)) == canonical_draft_bytes(
        draft(second_mapping, first_mapping)
    )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version":1,"schema_version":1,"mappings":[]}',
        b'{"schema_version":NaN,"mappings":[]}',
        b"{not-json}",
    ],
)
def test_private_loader_rejects_ambiguous_json_without_echo(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "draft.json"
    path.write_bytes(payload)
    os.chmod(path, 0o600)
    with pytest.raises(ServiceIdentityMappingError) as captured:
        load_draft(path)
    assert SUBJECT not in str(captured.value)
    assert ISSUER not in str(captured.value)


def test_private_loader_redacts_strict_schema_failures(tmp_path: Path) -> None:
    draft_path = tmp_path / "invalid-draft.json"
    write_private_json(
        draft_path,
        {
            "schema_version": 1,
            "mappings": [{"actor_profile_id": ACTOR_ID, "subject": SUBJECT}],
        },
    )
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_draft_invalid"):
        load_draft(draft_path)

    envelope_path = tmp_path / "invalid-envelope.json"
    payload = envelope().model_dump(mode="json")
    payload["unexpected_private_field"] = SUBJECT
    write_private_json(envelope_path, payload)
    with pytest.raises(
        ServiceIdentityMappingError,
        match="service_mapping_envelope_invalid",
    ) as captured:
        load_envelope(envelope_path)
    assert SUBJECT not in str(captured.value)


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_private_loader_rejects_coerced_schema_versions(
    tmp_path: Path,
    schema_version: object,
) -> None:
    path = tmp_path / "coerced-version.json"
    payload = draft().model_dump(mode="json")
    payload["schema_version"] = schema_version
    write_private_json(path, payload)
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_draft_invalid"):
        load_draft(path)


def test_private_loader_accepts_only_exact_canonical_draft(tmp_path: Path) -> None:
    path = tmp_path / "canonical-draft.json"
    write_private_json(path, draft(mapping()).model_dump(mode="json"))
    assert load_draft(path) == draft(mapping())


def test_private_loader_requires_exact_canonical_bytes(tmp_path: Path) -> None:
    draft_path = tmp_path / "pretty-draft.json"
    draft_path.write_text(
        json.dumps(draft().model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(draft_path, 0o600)
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_draft_invalid"):
        load_draft(draft_path)

    envelope_path = tmp_path / "whitespace-envelope.json"
    envelope_path.write_bytes(
        json.dumps(envelope().model_dump(mode="json"), sort_keys=True).encode() + b"\n"
    )
    os.chmod(envelope_path, 0o600)
    with pytest.raises(
        ServiceIdentityMappingError,
        match="service_mapping_envelope_invalid",
    ):
        load_envelope(envelope_path)


def test_private_loader_rejects_open_permissions_and_symlink(tmp_path: Path) -> None:
    path = tmp_path / "draft.json"
    write_private_json(path, draft().model_dump(mode="json"))
    os.chmod(path, 0o644)
    with pytest.raises(ServiceIdentityMappingError, match="file_insecure"):
        load_draft(path)
    os.chmod(path, 0o600)
    link = tmp_path / "draft-link.json"
    link.symlink_to(path)
    with pytest.raises(ServiceIdentityMappingError, match="file_unavailable"):
        load_draft(link)


def test_publish_envelope_is_owner_only_reloadable_and_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "envelope.json"
    publish_envelope(path, envelope())
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert load_envelope(path) == envelope()
    with pytest.raises(ServiceIdentityMappingError, match="output_unavailable"):
        publish_envelope(path, envelope())


def test_publish_envelope_removes_partial_output_after_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "partial-envelope.json"

    def fail_write(_descriptor: int, _data: object) -> int:
        raise OSError("simulated private-output failure")

    monkeypatch.setattr(os, "write", fail_write)
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_output_failed"):
        publish_envelope(path, envelope())
    assert not path.exists()


def test_migration_environment_is_required_only_for_existing_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(MAPPING_FILE_ENV, raising=False)
    assert load_migration_mapping((), database_binding=DATABASE_BINDING) is None
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_required"):
        load_migration_mapping((source_row(),), database_binding=DATABASE_BINDING)
    path = tmp_path / "envelope.json"
    publish_envelope(path, envelope())
    monkeypatch.setenv(MAPPING_FILE_ENV, str(path))
    assert load_migration_mapping(
        (source_row(),), database_binding=DATABASE_BINDING
    ) == envelope()
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_not_required"):
        load_migration_mapping((), database_binding=DATABASE_BINDING)


def test_mapping_paths_reject_relative_and_every_linked_repository_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_path_forbidden"):
        validate_mapping_path(Path("relative-private-mapping.json"), output=True)
    roots = protected_mapping_roots()
    assert Path(__file__).resolve().parents[2] in roots
    for root in roots:
        with pytest.raises(
            ServiceIdentityMappingError,
            match="service_mapping_path_forbidden",
        ):
            validate_mapping_path(root / "private-mapping.json", output=True)

    monkeypatch.setenv(MAPPING_FILE_ENV, str(Path(__file__).resolve()))
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_path_forbidden"):
        load_migration_mapping((source_row(),), database_binding=DATABASE_BINDING)


def test_mapping_path_guard_supports_deployments_without_git_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployed_root = tmp_path / "deployed-workstream"
    deployed_root.mkdir()
    private_root = tmp_path / "private"
    private_root.mkdir()
    monkeypatch.setattr(identity_migration, "REPOSITORY_ROOT", deployed_root)
    assert protected_mapping_roots() == (deployed_root,)
    assert validate_mapping_path(
        private_root / "mapping.json",
        output=True,
    ) == private_root / "mapping.json"


def test_mapping_path_guard_handles_main_and_linked_git_layouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_root = tmp_path / "main"
    (main_root / ".git").mkdir(parents=True)
    monkeypatch.setattr(identity_migration, "REPOSITORY_ROOT", main_root)
    assert set(protected_mapping_roots()) == {main_root, main_root / ".git"}

    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    common = tmp_path / "common" / ".git"
    metadata = common / "worktrees" / "linked"
    metadata.mkdir(parents=True)
    (linked_root / ".git").write_text(
        "gitdir: ../common/.git/worktrees/linked\n",
        encoding="utf-8",
    )
    (metadata / "gitdir").write_text(
        str(linked_root / ".git") + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(identity_migration, "REPOSITORY_ROOT", linked_root)
    assert {linked_root, common, common.parent}.issubset(protected_mapping_roots())


@pytest.mark.parametrize(
    "git_marker",
    [
        "invalid-marker",
        "gitdir: /tmp/not-a-worktrees-entry",
    ],
)
def test_mapping_path_guard_rejects_invalid_git_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    git_marker: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").write_text(git_marker + "\n", encoding="utf-8")
    monkeypatch.setattr(identity_migration, "REPOSITORY_ROOT", repository)
    with pytest.raises(ServiceIdentityMappingError, match="git_directory_unavailable"):
        protected_mapping_roots()


def test_mapping_path_guard_rejects_missing_linked_worktree_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    common = tmp_path / "common" / ".git"
    (common / "worktrees" / "linked").mkdir(parents=True)
    (linked_root / ".git").write_text(
        f"gitdir: {common / 'worktrees' / 'linked'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(identity_migration, "REPOSITORY_ROOT", linked_root)
    with pytest.raises(ServiceIdentityMappingError, match="git_directory_unavailable"):
        protected_mapping_roots()


def test_mapping_path_guard_rejects_missing_input(
    tmp_path: Path,
) -> None:
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_path_unavailable"):
        validate_mapping_path(tmp_path / "missing-envelope.json")


def test_envelope_loader_preserves_bounded_file_errors(tmp_path: Path) -> None:
    with pytest.raises(ServiceIdentityMappingError, match="service_mapping_file_unavailable"):
        load_envelope(tmp_path / "missing-envelope.json")


def test_report_contains_only_counts_and_non_secret_digests() -> None:
    snapshot = type("Snapshot", (), {"rows": (source_row(),), "database_binding": DATABASE_BINDING})
    report = build_report(snapshot, draft(mapping()), envelope=envelope())
    serialized = report.model_dump_json()
    assert report.mapped_count == 1
    assert ACTOR_ID not in serialized
    assert SUBJECT not in serialized
    assert ISSUER not in serialized


def test_cli_executes_and_disposes_engine_on_one_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop_ids: list[int] = []

    async def execute(_args: argparse.Namespace) -> dict[str, str]:
        loop_ids.append(id(asyncio.get_running_loop()))
        return {"status": "valid"}

    async def dispose() -> None:
        loop_ids.append(id(asyncio.get_running_loop()))

    monkeypatch.setattr(mapping_cli, "_execute", execute)
    monkeypatch.setattr(mapping_cli, "dispose_engine", dispose)
    assert asyncio.run(mapping_cli._execute_and_dispose(argparse.Namespace())) == {
        "status": "valid"
    }
    assert len(set(loop_ids)) == 1


def test_cli_preserves_workflow_error_when_cleanup_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def execute(_args: argparse.Namespace) -> dict:
        raise ServiceIdentityMappingError("expected_mapping_failure")

    async def dispose() -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(mapping_cli, "_execute", execute)
    monkeypatch.setattr(mapping_cli, "dispose_engine", dispose)
    with pytest.raises(ServiceIdentityMappingError, match="expected_mapping_failure"):
        asyncio.run(mapping_cli._execute_and_dispose(argparse.Namespace()))


def test_cli_reports_cleanup_failure_only_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def execute(_args: argparse.Namespace) -> dict[str, str]:
        return {"status": "valid"}

    async def dispose() -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(mapping_cli, "_execute", execute)
    monkeypatch.setattr(mapping_cli, "dispose_engine", dispose)
    with pytest.raises(mapping_cli.DatabaseCleanupError):
        asyncio.run(mapping_cli._execute_and_dispose(argparse.Namespace()))
