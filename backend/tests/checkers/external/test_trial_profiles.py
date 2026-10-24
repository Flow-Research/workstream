from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest

import app.modules.checkers.api.trial_profiles as trial_profiles

from app.modules.checkers.api.external import external_checker_json_hash
from app.modules.checkers.api.trial_profiles import (
    PinnedTrialExecutionCatalog,
    PinnedTrialProfileCatalog,
    TrialAuthorityBinding,
    TrialAuthorityContext,
    TrialExecutionProjection,
    TrialMaterialProjection,
    TrialProfileError,
    TrialProfileSelector,
    TrialProjectionSelector,
    TrialResourceCeilings,
    TrialSlotProjection,
    make_trial_execution_profile,
    make_trial_execution_projection,
    load_trial_authority_manifest,
    trial_selector_from_configuration,
)


PROFILE_ID = UUID("018f6f49-66b8-7d2a-bf4d-0e2eeaa00001")
PROJECTION_ID = UUID("018f6f49-66b8-7d2a-bf4d-0e2eeaa00002")


def digest(character: str) -> str:
    return "sha256:" + character * 64


def profile():
    return make_trial_execution_profile(
        schema_version="workstream.trial_execution_profile.v1",
        selector=TrialProfileSelector(PROFILE_ID, 1, digest("0")),
        runtime="runsc",
        isolation_mode="gvisor",
        outer_host_uds="open",
        child_host_uds="none",
        outer_runtime_config_digest=digest("1"),
        child_runtime_config_digest=digest("2"),
        engine_identity_digest=digest("3"),
        platform="linux/amd64",
        platform_identity_digest=digest("4"),
        builder_image_digest=digest("5"),
        trusted_launcher_digest=digest("6"),
        offline_cache_digest=digest("6"),
        approved_base_digests=(digest("7"),),
        permitted_source_roles=("submission_archive",),
        permitted_material_roles=("candidate_source", "verification"),
        permitted_operations=("run",),
        permitted_state_retention_outcomes=(
            "succeeded",
            "exit_nonzero",
            "signalled",
        ),
        trusted_launcher_capabilities=(
            "CHOWN",
            "DAC_OVERRIDE",
            "FOWNER",
            "KILL",
            "SETGID",
            "SETPCAP",
            "SETUID",
            "SYS_ADMIN",
            "SYS_CHROOT",
        ),
        builder_capabilities=("CHOWN", "DAC_OVERRIDE", "FOWNER"),
        child_capabilities=(),
        child_network="none",
        child_runs_as_non_root=True,
        limits=TrialResourceCeilings(
            maximum_total_timeout_ms=30_000,
            maximum_build_timeout_ms=10_000,
            maximum_step_timeout_ms=5_000,
            maximum_steps=3,
            maximum_cpu_quota_millis=1_000,
            maximum_cpu_time_ms=20_000,
            maximum_wall_time_overrun_ms=100,
            maximum_cpu_time_overrun_ms=250,
            maximum_memory_bytes=128 * 1024 * 1024,
            maximum_swap_bytes=128 * 1024 * 1024,
            maximum_memory_overrun_bytes=1024 * 1024,
            maximum_pids=32,
            maximum_pids_overrun=2,
            maximum_disk_bytes=128 * 1024 * 1024,
            maximum_disk_overrun_bytes=1024 * 1024,
            maximum_entries=10_000,
            maximum_entries_overrun=16,
            maximum_step_output_bytes=64 * 1024,
            maximum_observation_bytes=256 * 1024,
            maximum_receipt_bytes=512 * 1024,
            maximum_frame_bytes=256 * 1024,
            maximum_response_bytes=16 * 1024,
        ),
    )


def projection(selected=None) -> TrialExecutionProjection:
    selected = selected or profile()
    return make_trial_execution_projection(
        selector=TrialProjectionSelector(PROJECTION_ID, 1, digest("0")),
        trial_kind="generic_build_run",
        allowed_material_roles=("candidate_source", "verification"),
        build_context_roles=("candidate_source",),
        material_projections=(
            TrialMaterialProjection(
                "candidate_source",
                "submission_archive",
                "build_context",
                ".",
                ".",
                ("solution", "tests"),
            ),
            TrialMaterialProjection(
                "verification", "submission_archive", "state_overlay", "tests", "tests", ()
            ),
        ),
        slot_templates=(
            TrialSlotProjection("generic_run", 1, 2, (), ("verification",), True, ("succeeded",)),
        ),
    )


def configuration(selected=None, projected=None) -> dict[str, object]:
    selected = selected or profile()
    projected = projected or projection(selected)
    return {
        "check": "check_a",
        "model_profile_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00002",
        "model_profile_version": 1,
        "model_profile_digest": digest("8"),
        "trial_profile_id": str(selected.selector.profile_id),
        "trial_profile_version": selected.selector.profile_version,
        "trial_profile_digest": selected.selector.profile_digest,
        "trial_projection_id": str(projected.selector.projection_id),
        "trial_projection_version": projected.selector.projection_version,
        "trial_projection_digest": projected.selector.projection_digest,
    }


def authority_binding(selected=None, projected=None, *, configuration_sha256=None):
    selected = selected or profile()
    projected = projected or projection(selected)
    return TrialAuthorityBinding(
        registry_entry_id=UUID("018f6f49-66b8-7d2a-bf4d-0e2eeaa00003"),
        registry_entry_digest=digest("a"),
        checker_image_digest=digest("b"),
        configuration_sha256=configuration_sha256 or digest("c"),
        profile=selected,
        projection=projected,
    )


def test_profile_digest_is_derived_and_catalog_requires_exact_selector():
    selected = profile()
    assert selected.selector.profile_digest != digest("0")
    assert profile() == selected
    catalog = PinnedTrialProfileCatalog((selected,))
    assert catalog.read(selected.selector) == selected
    substituted = replace(selected.selector, profile_digest=digest("f"))
    assert catalog.read(substituted) is None
    with pytest.raises(TrialProfileError, match="duplicated"):
        PinnedTrialProfileCatalog((selected, selected))


def test_runtime_split_and_no_swap_are_closed_trusted_profile_rules():
    selected = profile()
    with pytest.raises(TrialProfileError, match="invalid"):
        replace(selected, child_host_uds="open")
    with pytest.raises(TrialProfileError, match="swap"):
        replace(
            selected.limits,
            maximum_swap_bytes=selected.limits.maximum_memory_bytes * 2,
        )
    with pytest.raises(TrialProfileError, match="invalid"):
        replace(selected, child_capabilities=("SYS_ADMIN",))
    with pytest.raises(TrialProfileError, match="invalid"):
        replace(selected, builder_capabilities=selected.trusted_launcher_capabilities)
    with pytest.raises(TrialProfileError, match="invalid"):
        replace(selected, trusted_launcher_capabilities=selected.builder_capabilities)
    with pytest.raises(TrialProfileError, match="byte ceiling"):
        replace(selected.limits, maximum_receipt_bytes=1024 * 1024 + 1)
    with pytest.raises(TrialProfileError, match="PID ceiling"):
        replace(selected.limits, maximum_pids=1)


def test_state_overlay_destination_is_exactly_one_workspace_component():
    with pytest.raises(TrialProfileError, match="material projection"):
        TrialMaterialProjection(
            "verification",
            "submission_archive",
            "state_overlay",
            "tests",
            "nested/tests",
            (),
        )


def test_locked_configuration_parses_trial_and_model_selectors_independently():
    selected = profile()
    projected = projection(selected)
    selector = trial_selector_from_configuration(configuration(selected, projected))
    assert selector is not None
    assert selector.profile == selected.selector
    assert selector.projection == projected.selector
    binding = authority_binding(selected, projected)
    catalog = PinnedTrialExecutionCatalog((binding,))
    assert catalog.read(binding.context, selector) == (selected, projected)

    without_trial = {
        key: value for key, value in configuration(selected).items() if not key.startswith("trial_")
    }
    assert trial_selector_from_configuration(without_trial) is None


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.pop("trial_profile_digest"),
        lambda value: value.update(trial_execution={"network_mode": "host"}),
        lambda value: value.update(trial_future_authority="forbidden"),
        lambda value: value.update(trial_projection_digest=["bad"]),
        lambda value: value.update(trial_profile_version=True),
    ),
)
def test_partial_unknown_foreign_or_wrong_typed_projection_is_rejected(mutation):
    value = configuration()
    mutation(value)
    with pytest.raises(TrialProfileError):
        trial_selector_from_configuration(value)


def test_projection_cannot_exceed_trusted_roles_or_step_count():
    selected = profile()
    foreign_role = make_trial_execution_projection(
        selector=TrialProjectionSelector(PROJECTION_ID, 1, digest("f")),
        trial_kind="generic_build_run",
        material_projections=(
            TrialMaterialProjection(
                "protected_role",
                "protected_source",
                "build_context",
                ".",
                ".",
                (),
            ),
        ),
        allowed_material_roles=("protected_role",),
        build_context_roles=("protected_role",),
        slot_templates=(TrialSlotProjection("generic_run", 1, 1, (), (), True, ("succeeded",)),),
    )
    with pytest.raises(TrialProfileError, match="exceeds"):
        foreign_role.validate_profile(selected)

    too_many = make_trial_execution_projection(
        selector=foreign_role.selector,
        trial_kind=foreign_role.trial_kind,
        material_projections=(
            TrialMaterialProjection(
                "candidate_source",
                "submission_archive",
                "build_context",
                ".",
                ".",
                (),
            ),
        ),
        allowed_material_roles=("candidate_source",),
        build_context_roles=("candidate_source",),
        slot_templates=tuple(
            TrialSlotProjection(f"slot_{index}", 1, 1, (), (), True, ("succeeded",))
            for index in range(selected.limits.maximum_steps + 1)
        ),
    )
    with pytest.raises(TrialProfileError, match="exceeds"):
        too_many.validate_profile(selected)


def test_projection_rejects_escape_overlap_shadow_and_unsafe_state_retention():
    with pytest.raises(TrialProfileError, match="material projection"):
        TrialMaterialProjection("bad", "submission_archive", "build_context", "../host", ".", ())

    with pytest.raises(TrialProfileError, match="material projection"):
        TrialMaterialProjection(
            "bad", "submission_archive", "build_context", ".", ".", ("tests", "tests/fixtures")
        )

    for alias in ("a//b", "a/./b", "./a"):
        with pytest.raises(TrialProfileError, match="material projection"):
            TrialMaterialProjection("bad", "submission_archive", "build_context", alias, ".", ())

    with pytest.raises(TrialProfileError, match="slot projection"):
        TrialSlotProjection("bad", 1, 1, (), (), True, ("deadline_exceeded",))


def test_operator_manifest_loader_is_digest_bound_strict_and_shared(tmp_path):
    selected = profile()
    projected = projection(selected)
    entry = {
        "registry_entry_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00003",
        "registry_entry_digest": digest("a"),
        "checker_image_digest": digest("b"),
        "configuration_sha256": digest("c"),
        "profile": asdict(selected),
        "projection": asdict(projected),
    }
    other = {**entry, "configuration_sha256": digest("d")}
    value = {"protocol_version": "workstream.trial_authority_manifest.v1", "entries": [entry, other]}
    value = json.loads(json.dumps(value, default=str))
    path = tmp_path / "trial-authority.json"
    path.write_text(json.dumps(value, default=str), encoding="utf-8")
    catalog = load_trial_authority_manifest(path, external_checker_json_hash(value))
    selector = trial_selector_from_configuration(configuration(selected, projected))
    assert selector is not None
    first_context = authority_binding(selected, projected).context
    second_context = TrialAuthorityContext(
        registry_entry_id=first_context.registry_entry_id,
        registry_entry_digest=first_context.registry_entry_digest,
        checker_image_digest=first_context.checker_image_digest,
        configuration_sha256=digest("d"),
    )
    assert catalog.read(first_context, selector) == (selected, projected)
    assert catalog.read(second_context, selector) == (selected, projected)
    substituted_selector = replace(
        selector,
        projection=replace(selector.projection, projection_digest=digest("e")),
    )
    assert catalog.read(first_context, substituted_selector) is None
    for field, replacement in (
        ("registry_entry_id", UUID("018f6f49-66b8-7d2a-bf4d-0e2eeaa00004")),
        ("registry_entry_digest", digest("e")),
        ("checker_image_digest", digest("e")),
        ("configuration_sha256", digest("e")),
    ):
        assert catalog.read(replace(first_context, **{field: replacement}), selector) is None

    canonical_entry = value["entries"][0]
    duplicate = {
        "protocol_version": value["protocol_version"],
        "entries": [canonical_entry, canonical_entry],
    }
    path.write_text(json.dumps(duplicate, default=str), encoding="utf-8")
    with pytest.raises(TrialProfileError, match="binding is duplicated"):
        load_trial_authority_manifest(path, external_checker_json_hash(duplicate))

    conflicting = {
        **entry,
        "projection": asdict(
            make_trial_execution_projection(
                selector=TrialProjectionSelector(
                    UUID("018f6f49-66b8-7d2a-bf4d-0e2eeaa00005"), 1, digest("0")
                ),
                trial_kind=projected.trial_kind,
                material_projections=projected.material_projections,
                allowed_material_roles=projected.allowed_material_roles,
                build_context_roles=projected.build_context_roles,
                slot_templates=projected.slot_templates,
            )
        ),
    }
    conflict_value = {
        "protocol_version": value["protocol_version"],
        "entries": [entry, conflicting],
    }
    conflict_value = json.loads(json.dumps(conflict_value, default=str))
    path.write_text(json.dumps(conflict_value), encoding="utf-8")
    with pytest.raises(TrialProfileError, match="binding is duplicated"):
        load_trial_authority_manifest(path, external_checker_json_hash(conflict_value))

    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(TrialProfileError, match="invalid"):
        load_trial_authority_manifest(path, digest("f"))

    path.write_text(
        '{"protocol_version":"workstream.trial_authority_manifest.v1","entries":[],"entries":[]}',
        encoding="utf-8",
    )
    with pytest.raises(TrialProfileError, match="invalid"):
        load_trial_authority_manifest(path, digest("f"))


def test_operator_manifest_loader_rejects_growth_during_bounded_read(tmp_path, monkeypatch):
    path = tmp_path / "trial-authority.json"
    path.write_bytes(b"{}")
    original_read = os.read
    grew = False

    def grow_then_read(descriptor, count):
        nonlocal grew
        if not grew:
            with path.open("ab") as stream:
                stream.write(b"x")
            grew = True
        return original_read(descriptor, count)

    monkeypatch.setattr(trial_profiles.os, "read", grow_then_read)
    with pytest.raises(TrialProfileError, match="changed"):
        load_trial_authority_manifest(path, digest("f"))


def test_operator_manifest_loader_rejects_path_replacement_during_read(tmp_path, monkeypatch):
    path = tmp_path / "trial-authority.json"
    replacement = tmp_path / "replacement.json"
    path.write_bytes(b"{}")
    replacement.write_bytes(b"{}")
    original_read = os.read
    replaced = False

    def replace_then_read(descriptor, count):
        nonlocal replaced
        if not replaced:
            os.replace(replacement, path)
            replaced = True
        return original_read(descriptor, count)

    monkeypatch.setattr(trial_profiles.os, "read", replace_then_read)
    with pytest.raises(TrialProfileError, match="changed"):
        load_trial_authority_manifest(path, digest("f"))


def test_operator_manifest_loader_rejects_fifo_without_blocking(tmp_path):
    path = tmp_path / "trial-authority.fifo"
    os.mkfifo(path, 0o600)
    backend_root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import signal; "
                "from app.modules.checkers.api.trial_profiles import "
                "load_trial_authority_manifest, TrialProfileError; "
                "signal.signal(signal.SIGALRM, lambda *_: "
                "(_ for _ in ()).throw(TimeoutError('fifo open blocked'))); "
                "signal.setitimer(signal.ITIMER_REAL, 2.0); "
                "\ntry: load_trial_authority_manifest(Path(__import__('sys').argv[1]), "
                "'sha256:' + 'f' * 64)"
                "\nexcept TrialProfileError: raise SystemExit(0)"
                "\nexcept TimeoutError: raise SystemExit(2)"
                "\nraise SystemExit(1)"
            ),
            str(path),
        ],
        cwd=backend_root,
        capture_output=True,
        check=False,
        # Interpreter/Pydantic startup is intentionally outside the two-second
        # action timer armed immediately before the loader call above.
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
