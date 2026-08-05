"""Proof for plan-bound hidden Workstream-default pre-submit execution."""

from __future__ import annotations

import asyncio
from io import BytesIO
from dataclasses import replace
from pathlib import Path
import threading
import zipfile
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.interfaces.artifact_operations import PreparedBundleMaterializationRequest
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactPreparationDeadlineError,
    ArtifactScratchManager,
)
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_manifest import (
    build_submission_manifest,
    evaluate_submission_change,
)
from app.modules.artifacts.submission_materialization import (
    DenyPreSubmitMaterializationAuthorization,
    PreparedBundleMaterializationService,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.checkers.catalogue import (
    PreSubmissionCheckerPhase,
    build_pre_submission_checker_catalogue,
)
from app.modules.checkers.compiler import compile_effective_project_submission_artifact_policy
from app.modules.checkers.effective_plan import (
    EffectivePreSubmissionPlanLineage,
    compile_effective_pre_submission_execution_plan,
)
from app.modules.checkers.pre_submit_execution import (
    DefaultPreSubmissionResultStatus,
    PreSubmissionInfrastructureUnavailable,
    SubmissionPacketView,
)


async def _bytes(value: bytes):
    yield value


def _archive(path: str = "task.toml") -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(path, b"[task]\nname='proof'\n")
    return output.getvalue()


def _effective_policy() -> dict[str, object]:
    defaults = {
        "required_packet_fields": ["summary", "worker_attestation"],
        "forbidden_artifacts": [{"pattern": ".env"}, {"pattern": ".git/**"}],
        "attestation_terms": ["rights_confirmed"],
    }
    return {
        "workstream_default_policy": defaults,
        "project_policy": {},
        "required_packet_fields": defaults["required_packet_fields"],
        "required_artifacts": [{"key": "task.toml", "required": True}],
        "required_evidence": [{"key": "results", "required": True}],
        "forbidden_artifacts": defaults["forbidden_artifacts"],
        "attestation_terms": defaults["attestation_terms"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["s3"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": {"package_required": True, "allowed_package_formats": ["zip"]},
    }


def _plan(catalogue):
    policy = _effective_policy()
    policy_hash = canonical_json_hash(policy)
    compiled = compile_effective_project_submission_artifact_policy(policy, policy_hash)
    lineage = EffectivePreSubmissionPlanLineage(
        project_id=uuid4(),
        guide_id=uuid4(),
        guide_version=1,
        source_snapshot_id=uuid4(),
        source_snapshot_hash="sha256:" + "1" * 64,
        effective_policy_id=uuid4(),
        effective_policy_hash=policy_hash,
        pre_submit_policy_id=uuid4(),
        pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
    )
    return compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=policy,
        compiled_bundle=compiled.compiled_bundle,
        catalogue=catalogue,
    )


def _rehash_plan(plan, *, entries=None, catalogue_manifest_sha256=None):
    changed = replace(
        plan,
        entries=plan.entries if entries is None else tuple(entries),
        catalogue_manifest_sha256=(
            plan.catalogue_manifest_sha256
            if catalogue_manifest_sha256 is None
            else catalogue_manifest_sha256
        ),
    )
    return replace(changed, plan_sha256=canonical_json_hash(changed.as_dict()))


def _limits() -> ArtifactPreparationLimits:
    return ArtifactPreparationLimits(
        aggregate_reserved_bytes=2 * HARD_MAXIMUM_ARTIFACT_BYTES,
        maximum_files=2,
        maximum_concurrency=2,
        minimum_free_bytes=0,
        reservation_ttl_seconds=30,
        total_deadline_seconds=10,
        cleanup_margin_seconds=5,
        stream_buffer_bytes=1024,
        maximum_source_bytes=1024 * 1024,
        maximum_workspace_entries=2_000,
    )


class _AllowAuthority:
    def __init__(self) -> None:
        self.facts = None

    async def consume(self, **values):
        self.facts = values["facts"]


def _handle() -> PreparedAuthorizationHandle:
    return object.__new__(PreparedAuthorizationHandle)


async def _request(tmp_path: Path, *, path: str = "task.toml", catalogue=None):
    selected_catalogue = catalogue or build_pre_submission_checker_catalogue()
    plan = _plan(selected_catalogue)
    data = _archive(path)
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=_limits())
    preparation = ArtifactPreparationService(manager)
    prepared = await preparation.prepare(_bytes(data), media_type="application/zip")
    inspection = await prepared.inspect(inspector)
    manifest = build_submission_manifest(inspection)
    change = evaluate_submission_change(
        commitment=prepared.commitment,
        manifest=manifest,
        predecessor=None,
        predecessor_exists=False,
    )
    request = PreparedBundleMaterializationRequest(
        prepared_authorization=_handle(),
        task_id=uuid4(),
        assignment_id=uuid4(),
        submission_artifact_policy_id=plan.lineage.effective_policy_id,
        checker_policy_id=plan.lineage.pre_submit_policy_id,
        prepared_artifact=prepared,
        effective_plan=plan,
        inspection=inspection,
        manifest=manifest,
        change_gate=change,
        packet=SubmissionPacketView(
            summary="Completed exact project work.",
            contributor_attestation=(
                "I confirm no confidential client data, credentials, or copied source "
                "material is included in this submission."
            ),
        ),
    )
    return request, inspector, manager, preparation, selected_catalogue


@pytest.mark.asyncio
async def test_authority_denial_precedes_workspace_and_checker_access(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    service = PreparedBundleMaterializationService(
        authorization=DenyPreSubmitMaterializationAuthorization(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    with pytest.raises(ArtifactAuthorityDeniedError):
        await service.materialize_prepared_bundle(request)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_default_executor_uses_plan_order_and_never_dispatches_project_rules(
    tmp_path: Path,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    authority = _AllowAuthority()
    service = PreparedBundleMaterializationService(
        authorization=authority,
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    result = await service.materialize_prepared_bundle(request)

    expected = [
        entry.definition_id
        for entry in request.effective_plan.entries
        if entry.phase
        in {
            PreSubmissionCheckerPhase.CUSTODY.value,
            PreSubmissionCheckerPhase.IDENTITY.value,
            PreSubmissionCheckerPhase.MATERIALIZATION.value,
            PreSubmissionCheckerPhase.DEFAULT_POLICY.value,
        }
    ]
    assert [entry.entry_id for entry in result.entries] == expected
    assert all(not entry.entry_id.startswith("policy.") for entry in result.entries)
    assert all(entry.status is DefaultPreSubmissionResultStatus.PASSED for entry in result.entries)
    assert result.eligible is True
    assert authority.facts is not None
    assert authority.facts.prepared_generation_id == request.prepared_artifact.generation_id
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_blocking_default_stops_later_dependency_without_review_decision(
    tmp_path: Path,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(
        tmp_path, path=".env"
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    result = await service.materialize_prepared_bundle(request)
    by_id = {entry.entry_id: entry for entry in result.entries}

    assert by_id["artifact.sensitive_paths.high_confidence"].status is (
        DefaultPreSubmissionResultStatus.FAILED
    )
    assert by_id["artifact.quality.placeholder_signal"].status is (
        DefaultPreSubmissionResultStatus.DEPENDENCY_NOT_RUN
    )
    assert result.eligible is False
    assert all(
        value not in {"accept", "needs_revision", "reject"}
        for entry in result.entries
        for value in (entry.status.value, entry.message_code, entry.failure_code)
        if value is not None
    )
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_disabled_advisory_is_explicit_and_not_skipped_success(tmp_path: Path) -> None:
    catalogue = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.quality.placeholder_signal"})
    )
    request, inspector, manager, preparation, _ = await _request(
        tmp_path, catalogue=catalogue
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    result = await service.materialize_prepared_bundle(request)
    advisory = next(
        entry
        for entry in result.entries
        if entry.entry_id == "artifact.quality.placeholder_signal"
    )

    assert advisory.status is DefaultPreSubmissionResultStatus.ADVISORY_DISABLED
    assert result.eligible is True
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_quality_warning_emits_only_a_bounded_category_count(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    request = replace(
        request,
        packet=replace(request.packet, summary="Completed work; TODO placeholder removed."),
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    result = await service.materialize_prepared_bundle(request)
    warning = next(
        entry
        for entry in result.entries
        if entry.entry_id == "artifact.quality.placeholder_signal"
    )

    assert warning.status is DefaultPreSubmissionResultStatus.WARNING
    assert warning.metadata == (("matched_category_count", 2),)
    assert result.eligible is True
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_forged_plan_identity_fails_closed_and_cleans_workspace(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    forged = replace(request.effective_plan, plan_sha256="sha256:" + "0" * 64)
    request = replace(request, effective_plan=forged)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    with pytest.raises(PreSubmissionInfrastructureUnavailable, match="plan_identity"):
        await service.materialize_prepared_bundle(request)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_state", ("stale_entry", "duplicate", "unknown"))
async def test_invalid_executor_state_fails_closed_and_cleans_workspace(
    tmp_path: Path,
    invalid_state: str,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    entries = list(request.effective_plan.entries)
    target_index = next(
        index
        for index, entry in enumerate(entries)
        if entry.definition_id == "submission.packet.required_fields"
    )
    selected_catalogue = catalogue
    if invalid_state == "stale_entry":
        entries[target_index] = replace(entries[target_index], definition_version="stale")
    elif invalid_state == "duplicate":
        entries.insert(target_index + 1, entries[target_index])
    else:
        unknown = replace(entries[target_index], dispatch_capability="unknown.capability")
        entries[target_index] = unknown
        original = catalogue.definition(unknown.definition_id)

        class _UnknownCatalogue:
            manifest_sha256 = catalogue.manifest_sha256

            def definition(self, definition_id):
                definition = catalogue.definition(definition_id)
                if definition_id != original.stable_id:
                    return definition

                class _UnknownDefinition:
                    dispatch_capability = "unknown.capability"

                    def __getattr__(self, name):
                        return getattr(definition, name)

                return _UnknownDefinition()

        selected_catalogue = _UnknownCatalogue()
    request = replace(
        request,
        effective_plan=_rehash_plan(request.effective_plan, entries=entries),
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=selected_catalogue,
    )

    with pytest.raises(PreSubmissionInfrastructureUnavailable):
        await service.materialize_prepared_bundle(request)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_disabled_mandatory_executor_state_fails_closed(tmp_path: Path) -> None:
    request, inspector, manager, preparation, _ = await _request(tmp_path)
    catalogue = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.outer_zip.valid"})
    )
    entries = [
        replace(entry, state="disabled")
        if entry.definition_id == "artifact.outer_zip.valid"
        else entry
        for entry in request.effective_plan.entries
    ]
    request = replace(
        request,
        effective_plan=_rehash_plan(
            request.effective_plan,
            entries=entries,
            catalogue_manifest_sha256=catalogue.manifest_sha256,
        ),
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    with pytest.raises(PreSubmissionInfrastructureUnavailable):
        await service.materialize_prepared_bundle(request)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_default_execution_ignores_project_only_forbidden_rule(tmp_path: Path) -> None:
    catalogue = build_pre_submission_checker_catalogue()
    policy = _effective_policy()
    project_rule = {"pattern": "project-only.blocked"}
    policy["project_policy"] = {"forbidden_artifacts": [project_rule]}
    policy["forbidden_artifacts"] = [*policy["forbidden_artifacts"], project_rule]
    policy_hash = canonical_json_hash(policy)
    compiled = compile_effective_project_submission_artifact_policy(policy, policy_hash)
    lineage = replace(
        _plan(catalogue).lineage,
        effective_policy_hash=policy_hash,
        pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
    )
    plan = compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=policy,
        compiled_bundle=compiled.compiled_bundle,
        catalogue=catalogue,
    )
    request, inspector, manager, preparation, _ = await _request(
        tmp_path,
        path="project-only.blocked",
        catalogue=catalogue,
    )
    request = replace(
        request,
        submission_artifact_policy_id=plan.lineage.effective_policy_id,
        checker_policy_id=plan.lineage.pre_submit_policy_id,
        effective_plan=plan,
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    result = await service.materialize_prepared_bundle(request)

    assert result.eligible is True
    assert all(not entry.entry_id.startswith("policy.") for entry in result.entries)
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_legacy_precheck_runner_is_not_an_execution_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    import app.modules.checkers.runner as legacy_runner

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy precheck path was called")

    monkeypatch.setattr(legacy_runner, "pre_submit_static_feedback", forbidden)
    monkeypatch.setattr(legacy_runner, "default_checker_registry", forbidden)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )

    result = await service.materialize_prepared_bundle(request)

    assert result.eligible is True
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_authorized_cancellation_cleans_before_propagating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    from app.modules.checkers.pre_submit_execution import DefaultPreSubmissionProcessor

    original = DefaultPreSubmissionProcessor.process

    def blocking_process(self, reader, workspace):
        entered.set()
        assert release.wait(timeout=5)
        return original(self, reader, workspace)

    monkeypatch.setattr(DefaultPreSubmissionProcessor, "process", blocking_process)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )
    task = asyncio.create_task(service.materialize_prepared_bundle(request))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_cancellation_during_member_projection_cleans_workspace(
    tmp_path: Path,
) -> None:
    request, _inspector, manager, preparation, catalogue = await _request(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class _BlockingProjectionInspector(SubmissionArchiveInspector):
        def _project_file(self, *args, **kwargs):
            entered.set()
            assert release.wait(timeout=5)
            return super()._project_file(*args, **kwargs)

    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=_BlockingProjectionInspector(SubmissionArchiveLimits()),
        catalogue=catalogue,
    )
    task = asyncio.create_task(service.materialize_prepared_bundle(request))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_timeout_during_checker_access_cleans_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    from app.modules.checkers.pre_submit_execution import DefaultPreSubmissionProcessor

    original = DefaultPreSubmissionProcessor.process

    def blocking_process(self, reader, workspace):
        entered.set()
        assert release.wait(timeout=5)
        return original(self, reader, workspace)

    monkeypatch.setattr(DefaultPreSubmissionProcessor, "process", blocking_process)
    preparation._active[request.prepared_artifact._binding].deadline = (
        asyncio.get_running_loop().time() + 0.01
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=inspector,
        catalogue=catalogue,
    )
    task = asyncio.create_task(service.materialize_prepared_bundle(request))
    assert await asyncio.to_thread(entered.wait, 5)
    await asyncio.sleep(0.02)
    release.set()

    with pytest.raises(ArtifactPreparationDeadlineError):
        await task

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ("cancel", "timeout"))
async def test_terminal_event_during_sealing_precedes_checker_access_and_cleans(
    tmp_path: Path,
    terminal: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _inspector, manager, preparation, catalogue = await _request(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class _BlockingSealInspector(SubmissionArchiveInspector):
        def _seal_projected_content(self, root_fd, entries):
            entered.set()
            assert release.wait(timeout=5)
            return super()._seal_projected_content(root_fd, entries)

    from app.modules.checkers.pre_submit_execution import DefaultPreSubmissionProcessor

    checker_called = threading.Event()
    original_execute = DefaultPreSubmissionProcessor._execute

    def observed_execute(self, tree):
        checker_called.set()
        return original_execute(self, tree)

    monkeypatch.setattr(DefaultPreSubmissionProcessor, "_execute", observed_execute)

    if terminal == "timeout":
        preparation._active[request.prepared_artifact._binding].deadline = (
            asyncio.get_running_loop().time() + 0.01
        )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        archive_inspector=_BlockingSealInspector(SubmissionArchiveLimits()),
        catalogue=catalogue,
    )
    task = asyncio.create_task(service.materialize_prepared_bundle(request))
    assert await asyncio.to_thread(entered.wait, 5)
    if terminal == "cancel":
        task.cancel()
    else:
        await asyncio.sleep(0.02)
    release.set()

    expected = asyncio.CancelledError if terminal == "cancel" else ArtifactPreparationDeadlineError
    with pytest.raises(expected):
        await task

    assert checker_called.is_set() is False
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()
