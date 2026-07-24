"""Regression tests for Workstream agent gate helpers.

Run with plain Python after installing the hash-pinned agent-gate dependencies;
the gate remains independent of the backend test environment.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from types import SimpleNamespace

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_COVERAGE_ORDER = (
    "foundation",
    "02A1",
    "02A2",
    "02A3",
    "02B1",
    "02C1",
    "02C2",
    "02C3",
    "02D",
    "03A",
    "03B",
    "03C",
    "04A",
    "04B",
    "04C",
    "05",
    "06A",
    "06B",
    "07",
)
FOUNDATION_ARTIFACT_COVERAGE_COMMAND = (
    "coverage report "
    "--include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,"
    "app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,"
    "app/modules/artifacts/*' --precision=2 --fail-under=90"
)
ARTIFACT_COVERAGE_COMMAND_OWNERS = {
    "foundation": (FOUNDATION_ARTIFACT_COVERAGE_COMMAND,),
    "02A1": (
        "coverage report --include='app/interfaces/external_services.py' "
        "--precision=2 --fail-under=90",
    ),
    "02A2": (
        "coverage report --include='app/core/config.py' --precision=2 --fail-under=90",
    ),
    "02A3": (
        "coverage report --include='app/workers/*' --precision=2 --fail-under=90",
        "coverage report --include='app/main.py' --precision=2 --fail-under=90",
    ),
    "02B1": (
        "coverage report --include='app/adapters/artifacts/s3_compatible.py' "
        "--precision=2 --fail-under=90",
        "coverage report --include='app/core/s3_validation.py' "
        "--precision=2 --fail-under=90",
    ),
    "02C1": (
        "coverage report --include='app/modules/audit/*' --precision=2 --fail-under=90",
    ),
    "02C2": (),
    "02C3": (),
    "02D": (
        "coverage report --include='app/api/router.py' --precision=2 --fail-under=90",
    ),
    "03A": (
        "coverage report --include='app/modules/projects/*' "
        "--precision=2 --fail-under=90",
    ),
    "03B": (
        "coverage report "
        "--include='app/adapters/project_agents/*,app/interfaces/project_agents.py' "
        "--precision=2 --fail-under=90",
    ),
    "03C": (),
    "04A": (),
    "04B": (
        "coverage report --include='app/modules/tasks/*' --precision=2 --fail-under=90",
        "coverage report --include='app/modules/checkers/*' "
        "--precision=2 --fail-under=90",
    ),
    "04C": (),
    "05": (),
    "06A": (),
    "06B": (),
    "07": (
        "python -m pytest ../examples/artifact_lifecycle/tests -q "
        "--cov=../examples/artifact_lifecycle/proof_tools "
        "--cov-report=term-missing --cov-fail-under=90",
    ),
}
BACKEND_FULL_SUITE_COVERAGE_COMMAND = "\n".join(
    (
        'metadata_dir="$(mktemp -d)"',
        "trap 'rm -rf \"$metadata_dir\"' EXIT",
        "python scripts/run_isolated_tests.py "
        '--metadata-json "$metadata_dir/result.json" --timeout-seconds 4800 -- '
        "python -m pytest -q --ignore=tests/test_isolated_database_runner.py "
        "--cov=app --cov-report=term-missing --cov-fail-under=78",
    )
)
BACKEND_API_CONTRACT_E2E_COMMAND = "\n".join(
    (
        'metadata_dir="$(mktemp -d)"',
        "trap 'rm -rf \"$metadata_dir\"' EXIT",
        "python scripts/run_isolated_tests.py "
        '--metadata-json "$metadata_dir/result.json" --timeout-seconds 1500 -- '
        "python scripts/api_contract_e2e.py",
    )
)
MINIO_IMAGE = (
    "quay.io/minio/minio:latest@"
    "sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
)
BACKEND_MINIO_START_COMMAND = "\n".join(
    (
        f"image='{MINIO_IMAGE}'",
        "docker run --detach --rm --name workstream-minio \\",
        "  --publish 127.0.0.1:9000:9000 \\",
        "  --env MINIO_ROOT_USER=workstream-minio \\",
        "  --env MINIO_ROOT_PASSWORD=workstream-minio-secret-key \\",
        '  "$image" server /data --address :9000',
        "for attempt in $(seq 1 60); do",
        "  if curl --fail --silent "
        "http://127.0.0.1:9000/minio/health/live >/dev/null; then",
        "    exit 0",
        "  fi",
        "  sleep 1",
        "done",
        "docker logs workstream-minio",
        "exit 1",
    )
)
AUTH_09B_COVERAGE_COMMANDS = (
    "coverage report --include='app/modules/actors/*' --precision=2 --fail-under=90",
    "coverage report --include='app/modules/authorization/*' "
    "--precision=2 --fail-under=90",
    "coverage report --include='app/modules/tasks/*' --precision=2 --fail-under=90",
    "coverage report "
    "--include='app/interfaces/auth.py,app/core/auth.py,app/adapters/auth/dev.py,"
    "app/adapters/auth/flow.py' --precision=2 --fail-under=90",
)
AUTHORIZATION_READ_COVERAGE_COMMANDS = (
    "coverage report "
    "--include='app/modules/api_controls/*,app/api/deps/api_controls.py' "
    "--precision=2 --fail-under=90",
)


def artifact_contract_phase_for(coverage_phase: str) -> str:
    """Map an implementation chunk to the stale-contract phase it owns."""
    active_index = ARTIFACT_COVERAGE_ORDER.index(coverage_phase)
    phase = "foundation"
    if active_index >= ARTIFACT_COVERAGE_ORDER.index("02A3"):
        phase = "artifact_store_cutover"
    if active_index >= ARTIFACT_COVERAGE_ORDER.index("03A"):
        phase = "guide_source_cutover"
    if active_index >= ARTIFACT_COVERAGE_ORDER.index("04A"):
        phase = "upload_admission"
    if active_index >= ARTIFACT_COVERAGE_ORDER.index("05"):
        phase = "submission_cutover"
    if active_index >= ARTIFACT_COVERAGE_ORDER.index("06B"):
        phase = "checker_cutover"
    return phase


def artifact_chunk_contract(coverage_phase: str) -> Path:
    """Return the one contract that owns an implementation coverage phase."""
    assert coverage_phase != "foundation"
    chunk_root = (
        ROOT / ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks"
    )
    matches = sorted(chunk_root.glob(f"WS-ART-001-{coverage_phase}-*.md"))
    assert len(matches) == 1, (coverage_phase, matches)
    return matches[0]


def artifact_contract_coverage_commands_for(coverage_phase: str) -> tuple[str, ...]:
    """Parse the cumulative coverage commands declared by one chunk contract."""
    if coverage_phase == "foundation":
        return (FOUNDATION_ARTIFACT_COVERAGE_COMMAND,)
    contract_path = artifact_chunk_contract(coverage_phase)
    contract = contract_path.read_text(encoding="utf-8")
    section = re.search(
        r"## Exact CI Coverage Gates?\n\n```bash\n(.*?)\n```",
        contract,
        re.DOTALL,
    )
    assert section is not None, contract_path
    return tuple(line for line in section.group(1).splitlines() if line)


def artifact_expected_coverage_commands_for(coverage_phase: str) -> tuple[str, ...]:
    """Build the independently owned cumulative 90 percent coverage contract."""
    active_index = ARTIFACT_COVERAGE_ORDER.index(coverage_phase)
    commands: list[str] = []
    for phase in ARTIFACT_COVERAGE_ORDER[: active_index + 1]:
        commands.extend(ARTIFACT_COVERAGE_COMMAND_OWNERS[phase])
    assert len(commands) == len(set(commands)), commands
    return tuple(commands)


def artifact_declared_contract_phase_for(coverage_phase: str) -> str:
    """Read the machine-readable stale-contract phase from a chunk contract."""
    contract = artifact_chunk_contract(coverage_phase).read_text(encoding="utf-8")
    matches = re.findall(
        r"^Artifact contract phase: `([^`]+)`$", contract, re.MULTILINE
    )
    assert len(matches) == 1, (coverage_phase, matches)
    return matches[0]


def active_artifact_coverage_phase() -> str:
    """Derive the active or most recently completed artifact phase from the queue."""
    queue = (ROOT / ".agent-loop/WORK_QUEUE.md").read_text(encoding="utf-8")
    in_progress = queue.split("## In Progress", maxsplit=1)[1].split(
        "## Planned Next",
        maxsplit=1,
    )[0]
    active_chunks = [
        chunk
        for chunk in re.findall(r"\| `([^`]+)` \|", in_progress)
        if chunk.startswith("WS-ART-001-")
    ]
    assert len(active_chunks) <= 1, active_chunks
    if active_chunks:
        active = active_chunks[0]
        if active == "WS-ART-001-OBJECT-STORAGE-AMENDMENT":
            phase = "foundation"
        else:
            phase = active.removeprefix("WS-ART-001-")
            assert phase in ARTIFACT_COVERAGE_ORDER, phase
        reviewed_intent_phases = {
            path.stem.removeprefix("WS-ART-001-")
            for path in (ROOT / ".agent-loop/merge-intents").glob("WS-ART-001-*.json")
            if path.stem.removeprefix("WS-ART-001-") in ARTIFACT_COVERAGE_ORDER
        }
        return max({phase, *reviewed_intent_phases}, key=ARTIFACT_COVERAGE_ORDER.index)

    completed = queue.split("## Completed", maxsplit=1)[1].split(
        "## Proposed Next",
        maxsplit=1,
    )[0]
    completed_phases = {
        chunk.removeprefix("WS-ART-001-")
        for chunk in re.findall(r"\| `([^`]+)` \|", completed)
        if chunk.startswith("WS-ART-001-")
        and chunk.removeprefix("WS-ART-001-") in ARTIFACT_COVERAGE_ORDER
    }
    if not completed_phases:
        return "foundation"
    return max(completed_phases, key=ARTIFACT_COVERAGE_ORDER.index)


def load_module(name: str, path: str):
    """Load a script module by path."""
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_required_tracks_expand_for_loop_and_ci_paths() -> None:
    """Loop, Codex, script, and workflow paths require focused reviewers."""
    gate = load_module("review_gate", "scripts/check_internal_review_evidence.py")
    tracks = gate.required_tracks_for(
        [
            ".agent-loop/policies/engineering-review-policy.md",
            ".agents/skills/qa-review/SKILL.md",
            ".codex/agents/qa-reviewer.toml",
            ".github/workflows/agent-gates.yml",
            "scripts/workstream_agent_gate.py",
        ]
    )
    assert tracks == (
        "senior engineering",
        "qa/test",
        "security/auth",
        "product/ops",
        "architecture",
        "docs",
        "reuse/dedup",
        "ci integrity",
    )


def test_backend_config_paths_require_review_evidence() -> None:
    """Migration and backend tooling paths cannot bypass review evidence."""
    gate = load_module(
        "review_gate_backend_paths", "scripts/check_internal_review_evidence.py"
    )
    assert gate.is_relevant("backend/alembic/versions/0001_init.py")
    assert gate.is_relevant("backend/alembic.ini")
    assert gate.is_relevant("backend/pyproject.toml")

    backend_tracks = gate.required_tracks_for(["backend/alembic/versions/0001_init.py"])
    assert "architecture" in backend_tracks
    assert "ci integrity" not in backend_tracks

    backend_config_tracks = gate.required_tracks_for(["backend/pyproject.toml"])
    assert "ci integrity" in backend_config_tracks


def test_review_evidence_files_are_not_relevant_changes() -> None:
    """Review evidence files satisfy the gate without requiring more evidence."""
    gate = load_module(
        "review_gate_relevance", "scripts/check_internal_review_evidence.py"
    )
    assert not gate.is_relevant(".agent-loop/initiatives/example/reviews/review.md")
    assert not gate.is_relevant("docs/internal_reviews/example.md")
    assert not gate.is_internal_review_evidence_path("docs/internal_reviews/example.md")
    assert gate.is_internal_review_evidence_path(
        ".agent-loop/initiatives/example/reviews/example-internal-review-evidence.md"
    )
    assert not gate.is_internal_review_evidence_path(
        ".agent-loop/initiatives/example/reviews/example-external-review-response.md"
    )


def test_evidence_requires_completed_yes_statements() -> None:
    """Evidence must contain affirmative completion statements."""
    gate = load_module(
        "review_gate_statements", "scripts/check_internal_review_evidence.py"
    )
    original_changed_files = gate.changed_files
    gate.changed_files = lambda: []
    required = ("senior engineering", "qa/test")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            weak = Path(tmpdir) / "weak.md"
            weak.write_text(
                "| Reviewer | Result | Blocking findings |\n"
                "|---|---:|---|\n"
                "| senior engineering | PASS | None |\n"
                "| qa/test | PASS | None |\n"
                "open sub-agent sessions: none\nvalid findings addressed: no\n",
                encoding="utf-8",
            )
            assert "valid findings addressed: yes" in gate.validate_evidence(
                weak,
                required,
                enforce_reviewed_revision=False,
            )

            strong = Path(tmpdir) / "strong.md"
            strong.write_text(
                "| Reviewer | Result | Blocking findings |\n"
                "|---|---:|---|\n"
                "| senior engineering | PASS | None |\n"
                "| qa/test | PASS | None |\n"
                "open sub-agent sessions: none\nvalid findings addressed: yes\n",
                encoding="utf-8",
            )
            assert (
                gate.validate_evidence(
                    strong, required, enforce_reviewed_revision=False
                )
                == []
            )
    finally:
        gate.changed_files = original_changed_files


def test_evidence_must_reference_changed_chunk() -> None:
    """Evidence must mention the changed chunk contract when one exists."""
    gate = load_module("review_gate_chunk", "scripts/check_internal_review_evidence.py")
    headings = {
        "# Chunk Contract: WS-XINT-001-PLAN Boundary Reconciliation": (
            "ws-xint-001-plan"
        ),
        "# Chunk Contract: WS-ART-001-02A3 - ArtifactStore v2 Local Clean Cut": (
            "ws-art-001-02a3"
        ),
        "# Chunk Contract: WS-QUAL-001-01B1A-R1 Normalization Closure": (
            "ws-qual-001-01b1a-r1"
        ),
        "# Chunk Contract: WS-QUAL-001-01B1A-R2 Canonical Coverage Grammar": (
            "ws-qual-001-01b1a-r2"
        ),
        "# Chunk Contract: WS-AUTH-001-CAT - Action Catalogue": "ws-auth-001-cat",
        "# Chunk Contract: WS-ART-001-OBJECT-STORAGE-AMENDMENT": (
            "ws-art-001-object-storage-amendment"
        ),
        "# Parent Chunk: WS-AUTH-001-07 - Authorization Kernel": "ws-auth-001-07",
        "# WS-ART-001-01: Artifact Domain And Local Adapter": "ws-art-001-01",
        "# Chunk Contract: WS-XINT-001-PLAN2 Distinct Chunk": "ws-xint-001-plan2",
        "# Chunk Contract: WS-XINT-001-PLANNER Distinct Chunk": ("ws-xint-001-planner"),
    }
    assert {
        heading: gate.chunk_id_from_heading(heading) for heading in headings
    } == headings
    assert gate.chunk_id_from_heading("# WS-XINT-001-PLAN without colon") is None
    assert gate.required_chunk_ids(
        [
            ".agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/"
            "chunks/WS-XINT-001-PLAN-boundary-reconciliation.md",
            ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/"
            "chunks/WS-ART-001-02A3-artifact-store-v2-local-clean-cut.md",
            ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/"
            "chunks/WS-QUAL-001-01B1A-R1-normalization-closure.md",
            ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/"
            "chunks/WS-AUTH-001-CAT-action-resource-catalogue-reconciliation.md",
            ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/"
            "chunks/WS-ART-001-OBJECT-STORAGE-AMENDMENT.md",
        ]
    ) == [
        "ws-xint-001-plan",
        "ws-art-001-02a3",
        "ws-qual-001-01b1a-r1",
        "ws-auth-001-cat",
        "ws-art-001-object-storage-amendment",
    ]
    original_root = gate.ROOT
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate.ROOT = Path(tmpdir)
            chunks = gate.ROOT / ".agent-loop/initiatives/example/chunks"
            chunks.mkdir(parents=True)
            invalid_contracts = {
                "empty.md": b"",
                "malformed.md": b"# Contract without a lifecycle id\n",
                "invalid-utf8.md": b"\xff",
            }
            for filename, content in invalid_contracts.items():
                relative_path = ".agent-loop/initiatives/example/chunks/" + filename
                (chunks / filename).write_bytes(content)
                try:
                    gate.required_chunk_ids([relative_path])
                except RuntimeError:
                    pass
                else:
                    raise AssertionError(
                        f"invalid changed contract did not fail closed: {filename}"
                    )

            unreadable_path = chunks / "unreadable.md"
            unreadable_path.mkdir()
            try:
                gate.required_chunk_ids(
                    [".agent-loop/initiatives/example/chunks/unreadable.md"]
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("unreadable changed contract did not fail closed")

            missing_relative = ".agent-loop/initiatives/example/chunks/missing.md"
            try:
                gate.required_chunk_ids([missing_relative])
            except RuntimeError:
                pass
            else:
                raise AssertionError("missing changed contract did not fail closed")

            dangling_path = chunks / "dangling.md"
            dangling_path.symlink_to(chunks / "absent-target.md")
            try:
                gate.required_chunk_ids(
                    [".agent-loop/initiatives/example/chunks/dangling.md"]
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("dangling changed contract did not fail closed")

            linked_target = chunks / "linked-target.md"
            linked_target.write_text(
                "# Chunk Contract: WS-EXAMPLE-001-LINKED - External\n",
                encoding="utf-8",
            )
            linked_path = chunks / "linked.md"
            linked_path.symlink_to(linked_target)
            try:
                gate.required_chunk_ids(
                    [".agent-loop/initiatives/example/chunks/linked.md"]
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("resolvable symlink contract did not fail closed")

            replacement = chunks / "WS-EXAMPLE-001-NEW-replacement.md"
            replacement.write_text(
                "# Chunk Contract: WS-EXAMPLE-001-NEW - Replacement\n",
                encoding="utf-8",
            )
            original_historical_contract_text = gate.historical_contract_text
            gate.historical_contract_text = lambda _path: (
                "# Chunk Contract: WS-EXAMPLE-001-OLD - Deleted\n"
            )
            try:
                assert gate.required_chunk_ids(
                    [
                        ".agent-loop/initiatives/example/chunks/"
                        "WS-EXAMPLE-001-OLD-deleted.md"
                    ]
                ) == ["ws-example-001-old"]
                assert gate.required_chunk_ids(
                    [
                        ".agent-loop/initiatives/example/chunks/"
                        "WS-EXAMPLE-001-OLD-deleted.md",
                        ".agent-loop/initiatives/example/chunks/"
                        "WS-EXAMPLE-001-NEW-replacement.md",
                    ]
                ) == ["ws-example-001-old", "ws-example-001-new"]
            finally:
                gate.historical_contract_text = original_historical_contract_text
    finally:
        gate.ROOT = original_root
    original_changed_files = gate.changed_files
    gate.changed_files = lambda: [
        ".agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/"
        "chunks/WS-ENG-001-01-codex-loop-bootstrap.md"
    ]
    required = ("senior engineering",)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = Path(tmpdir) / "review.md"
            evidence.write_text(
                "| Reviewer | Result | Blocking findings |\n"
                "|---|---:|---|\n"
                "| senior engineering | PASS | None |\n"
                "open sub-agent sessions: none\nvalid findings addressed: yes\n",
                encoding="utf-8",
            )
            assert "chunk id: one of ws-eng-001-01" in gate.validate_evidence(
                evidence,
                required,
                enforce_reviewed_revision=False,
            )

            evidence.write_text(
                "WS-ENG-001-01\n"
                "| Reviewer | Result | Blocking findings |\n"
                "|---|---:|---|\n"
                "| senior engineering | PASS | None |\n"
                "open sub-agent sessions: none\nvalid findings addressed: yes\n",
                encoding="utf-8",
            )
            assert (
                gate.validate_evidence(
                    evidence, required, enforce_reviewed_revision=False
                )
                == []
            )

            collision_template = (
                "{chunk_id}\n"
                "| Reviewer | Result | Blocking findings |\n"
                "|---|---:|---|\n"
                "| senior engineering | PASS | None |\n"
                "open sub-agent sessions: none\nvalid findings addressed: yes\n"
            )
            for collision in (
                "WS-XINT-001-PLAN2",
                "WS-XINT-001-PLANNER",
            ):
                evidence.write_text(
                    collision_template.format(chunk_id=collision),
                    encoding="utf-8",
                )
                assert "chunk id: one of ws-xint-001-plan" in gate.validate_evidence(
                    evidence,
                    required,
                    chunk_ids=["ws-xint-001-plan"],
                    enforce_reviewed_revision=False,
                )

            evidence.write_text(
                collision_template.format(chunk_id="WS-QUAL-001-01B1A-R10"),
                encoding="utf-8",
            )
            assert "chunk id: one of ws-qual-001-01b1a-r1" in gate.validate_evidence(
                evidence,
                required,
                chunk_ids=["ws-qual-001-01b1a-r1"],
                enforce_reviewed_revision=False,
            )
            assert gate.evidence_chunk_ids(
                "WS-XINT-001-PLAN WS-XINT-001-PLAN2 WS-QUAL-001-01B1A-R1"
            ) == {
                "ws-xint-001-plan",
                "ws-xint-001-plan2",
                "ws-qual-001-01b1a-r1",
            }
    finally:
        gate.changed_files = original_changed_files


def test_evidence_rejects_pending_or_blocking_reviewer_rows() -> None:
    """Evidence table rows must show passing reviewers and no blocking findings."""
    gate = load_module("review_gate_rows", "scripts/check_internal_review_evidence.py")
    original_changed_files = gate.changed_files
    gate.changed_files = lambda: []
    required = ("senior engineering", "qa/test")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = Path(tmpdir) / "review.md"
            evidence.write_text(
                "| Reviewer | Result | Blocking findings |\n"
                "|---|---:|---|\n"
                "| senior engineering | PASS | None |\n"
                "| qa/test | Pending | High finding |\n"
                "open sub-agent sessions: none\nvalid findings addressed: yes\n",
                encoding="utf-8",
            )
            missing = gate.validate_evidence(
                evidence, required, enforce_reviewed_revision=False
            )
            assert any(
                "qa/test reviewer result must be one of" in item for item in missing
            )
            assert "qa/test blocking findings must be none" in missing
    finally:
        gate.changed_files = original_changed_files


def test_evidence_accepts_exact_pass_and_approved_na_results() -> None:
    """Reviewer result values are exact, with explicit N/A reason support."""
    gate = load_module(
        "review_gate_exact_results", "scripts/check_internal_review_evidence.py"
    )
    required = ("senior engineering",)
    text = (
        "| Reviewer | Result | Blocking findings | Notes |\n"
        "|---|---:|---|---|\n"
        "| senior engineering | PASS WITH LOW RISKS | None | checked |\n"
        "| qa/test | N/A - with approved reason | None | explicitly unrelated because docs only |\n"
    )
    assert gate.validate_reviewer_rows(text.lower(), required) == []

    newest_first_text = (
        "| Reviewer | Result | Blocking findings | Notes |\n"
        "|---|---:|---|---|\n"
        "| senior engineering | PASS AFTER FIXES | None | current addendum |\n"
        "\nHistorical addendum\n\n"
        "| Reviewer | Result | Blocking findings | Notes |\n"
        "|---|---:|---|---|\n"
        "| senior engineering | Pending | Old finding | superseded |\n"
    )
    assert gate.validate_reviewer_rows(newest_first_text.lower(), required) == []

    bad_text = (
        "| Reviewer | Result | Blocking findings | Notes |\n"
        "|---|---:|---|---|\n"
        "| senior engineering | bypass | None | malformed |\n"
    )
    missing = gate.validate_reviewer_rows(bad_text.lower(), required)
    assert any(
        "senior engineering reviewer result must be one of" in item for item in missing
    )

    optional_bad_text = (
        "| Reviewer | Result | Blocking findings | Notes |\n"
        "|---|---:|---|---|\n"
        "| senior engineering | PASS | None | checked |\n"
        "| docs | Pending / N/A - with approved reason | None | |\n"
        "| ci integrity | N/A | None | |\n"
    )
    missing = gate.validate_reviewer_rows(optional_bad_text.lower(), required)
    assert any("docs reviewer result must be one of" in item for item in missing)
    assert any(
        "ci integrity reviewer result must be one of" in item for item in missing
    )

    unrelated_table_text = (
        "| Reviewer | Result | Blocking findings | Notes |\n"
        "|---|---:|---|---|\n"
        "| senior engineering | PASS | None | checked |\n"
        "| Finding | Severity | Status |\n"
        "|---|---:|---|\n"
        "| F-001 | high | closed |\n"
    )
    assert gate.validate_reviewer_rows(unrelated_table_text.lower(), required) == []

    missing_note_text = (
        "| Reviewer | Result | Blocking findings | Notes |\n"
        "|---|---:|---|---|\n"
        "| senior engineering | PASS | None | checked |\n"
        "| docs | N/A - with approved reason | None | pending |\n"
    )
    missing = gate.validate_reviewer_rows(missing_note_text.lower(), required)
    assert "docs n/a result requires notes" in missing


def test_evidence_rejects_na_for_required_tracks() -> None:
    """Required reviewer tracks must pass and cannot be bypassed with N/A."""
    gate = load_module(
        "review_gate_required_na", "scripts/check_internal_review_evidence.py"
    )
    required = ("security/auth", "architecture")
    text = (
        "| Reviewer | Result | Blocking findings | Notes |\n"
        "|---|---:|---|---|\n"
        "| security/auth | N/A - with approved reason | None | claimed unrelated |\n"
        "| architecture | N/A - with approved reason | None | claimed unrelated |\n"
    )
    missing = gate.validate_reviewer_rows(text.lower(), required)
    assert "security/auth reviewer result cannot be n/a when required" in missing
    assert "architecture reviewer result cannot be n/a when required" in missing


def test_evidence_reviewed_revision_allows_only_evidence_status_changes() -> None:
    """Evidence must be bound to a reviewed SHA and only status files may follow."""
    gate = load_module(
        "review_gate_revision_binding", "scripts/check_internal_review_evidence.py"
    )
    original_git = gate.git
    original_git_ok = gate.git_ok
    reviewed = "a" * 40

    def fake_git(*args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "b" * 40
        if args == ("diff", "--name-only", f"{reviewed}..{'b' * 40}"):
            return (
                ".agent-loop/LOOP_STATE.md\n"
                ".agent-loop/initiatives/example/reviews/review.md\n"
                "docs/internal_reviews/review.md"
            )
        if args in {
            ("diff", "--name-only", "--cached"),
            ("diff", "--name-only"),
            ("ls-files", "--others", "--exclude-standard"),
        }:
            return ""
        return ""

    gate.git = fake_git
    gate.git_ok = lambda *args: True
    try:
        text = (
            f"Reviewed code SHA: {reviewed}\n"
            "Reviewed at: 2026-06-18T00:00:00Z\n"
            "Reviewer run IDs: local\n"
        ).lower()
        assert gate.validate_reviewed_revision(text) == []
    finally:
        gate.git = original_git
        gate.git_ok = original_git_ok


def test_evidence_reviewed_revision_rejects_late_implementation_changes() -> None:
    """Implementation changes after the reviewed SHA invalidate evidence."""
    gate = load_module(
        "review_gate_revision_rejects_late_changes",
        "scripts/check_internal_review_evidence.py",
    )
    original_git = gate.git
    original_git_ok = gate.git_ok
    reviewed = "a" * 40

    def fake_git(*args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "b" * 40
        if args == ("diff", "--name-only", f"{reviewed}..{'b' * 40}"):
            return "scripts/check_internal_review_evidence.py"
        if args in {
            ("diff", "--name-only", "--cached"),
            ("diff", "--name-only"),
            ("ls-files", "--others", "--exclude-standard"),
        }:
            return ""
        return ""

    gate.git = fake_git
    gate.git_ok = lambda *args: True
    try:
        text = (
            f"Reviewed code SHA: {reviewed}\n"
            "Reviewed at: 2026-06-18T00:00:00Z\n"
            "Reviewer run IDs: local\n"
        ).lower()
        missing = gate.validate_reviewed_revision(text)
        assert any("reviewed code sha is stale" in item for item in missing)
    finally:
        gate.git = original_git
        gate.git_ok = original_git_ok


def test_evidence_reviewed_revision_rejects_dirty_tree_changes() -> None:
    """Staged, unstaged, and untracked implementation changes invalidate evidence."""
    gate = load_module(
        "review_gate_revision_rejects_dirty",
        "scripts/check_internal_review_evidence.py",
    )
    original_git = gate.git
    original_git_ok = gate.git_ok
    reviewed = "a" * 40

    def fake_git(*args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return reviewed
        if args == ("diff", "--name-only", f"{reviewed}..{reviewed}"):
            return ""
        if args == ("diff", "--name-only", "--cached"):
            return "scripts/staged_change.py"
        if args == ("diff", "--name-only"):
            return "scripts/check_internal_review_evidence.py"
        if args == ("ls-files", "--others", "--exclude-standard"):
            return "scripts/untracked_change.py"
        return ""

    gate.git = fake_git
    gate.git_ok = lambda *args: True
    try:
        text = (
            f"Reviewed code SHA: {reviewed}\n"
            "Reviewed at: 2026-06-18T00:00:00Z\n"
            "Reviewer run IDs: local\n"
        ).lower()
        missing = gate.validate_reviewed_revision(text)
        assert any("reviewed code sha is stale" in item for item in missing)
        stale = next(item for item in missing if "reviewed code sha is stale" in item)
        assert "scripts/staged_change.py" in stale
        assert "scripts/check_internal_review_evidence.py" in stale
        assert "scripts/untracked_change.py" in stale
    finally:
        gate.git = original_git
        gate.git_ok = original_git_ok


def test_evidence_reviewed_revision_rejects_invalid_provenance() -> None:
    """Reviewed at and reviewer run IDs must contain concrete values."""
    gate = load_module(
        "review_gate_revision_blank_provenance",
        "scripts/check_internal_review_evidence.py",
    )
    original_git = gate.git
    original_git_ok = gate.git_ok
    reviewed = "a" * 40

    def fake_git(*args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return reviewed
        if args == ("diff", "--name-only", f"{reviewed}..{reviewed}"):
            return ""
        if args in {
            ("diff", "--name-only", "--cached"),
            ("diff", "--name-only"),
            ("ls-files", "--others", "--exclude-standard"),
        }:
            return ""
        return ""

    gate.git = fake_git
    gate.git_ok = lambda *args: True
    try:
        text = (
            f"Reviewed code SHA: {reviewed}\nReviewed at:\nReviewer run IDs:\n".lower()
        )
        missing = gate.validate_reviewed_revision(text)
        assert "reviewed at" in missing
        assert "reviewer run ids" in missing

        placeholder_text = (
            f"Reviewed code SHA: `{reviewed}`\n"
            "Reviewed at: `<UTC timestamp>`\n"
            "Reviewer run IDs: `<agent ids, CI run IDs, or local reviewer run references>`\n"
        ).lower()
        missing = gate.validate_reviewed_revision(placeholder_text)
        assert "reviewed at" in missing
        assert "reviewer run ids" in missing

        bad_timestamp_text = (
            f"Reviewed code SHA: {reviewed}\n"
            "Reviewed at: 2026-06-18 00:00:00\n"
            "Reviewer run IDs: 019eda06-0848-7131-8895-48f8ea720fb9\n"
        ).lower()
        assert "reviewed at" in gate.validate_reviewed_revision(bad_timestamp_text)
    finally:
        gate.git = original_git
        gate.git_ok = original_git_ok


def test_evidence_main_fails_closed_on_unresolved_base_ref() -> None:
    """Configured base refs must resolve before the evidence gate can pass."""
    gate = load_module(
        "review_gate_base_ref", "scripts/check_internal_review_evidence.py"
    )
    original_env = os.environ.get("INTERNAL_REVIEW_BASE_REF")
    original_git_ok = gate.git_ok
    os.environ["INTERNAL_REVIEW_BASE_REF"] = "missing-base"
    gate.git_ok = lambda *args: False
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            assert gate.main() == 1
    finally:
        gate.git_ok = original_git_ok
        if original_env is None:
            os.environ.pop("INTERNAL_REVIEW_BASE_REF", None)
        else:
            os.environ["INTERNAL_REVIEW_BASE_REF"] = original_env


def test_evidence_main_passes_with_complete_evidence_and_pr_head() -> None:
    """The full evidence gate passes when evidence is complete and bound to PR_HEAD_SHA."""
    gate = load_module(
        "review_gate_main_complete", "scripts/check_internal_review_evidence.py"
    )
    original_env = {
        "INTERNAL_REVIEW_BASE_REF": os.environ.get("INTERNAL_REVIEW_BASE_REF"),
        "INTERNAL_REVIEW_CHUNK_ID": os.environ.get("INTERNAL_REVIEW_CHUNK_ID"),
        "PR_HEAD_SHA": os.environ.get("PR_HEAD_SHA"),
    }
    original_git = gate.git
    original_git_ok = gate.git_ok
    original_changed_files = gate.changed_files
    reviewed = "a" * 40
    local_head = "b" * 40
    evidence = (
        ROOT / ".agent-loop/initiatives/test-agent-gate/"
        "reviews/test-agent-gate-internal-review-evidence.md"
    )

    def fake_git(*args: str) -> str:
        if args == ("merge-base", "--is-ancestor", "origin/main", "HEAD"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return local_head
        if args == ("diff", "--name-only", f"{reviewed}..{reviewed}"):
            return ""
        if args in {
            ("diff", "--name-only", "--cached"),
            ("diff", "--name-only"),
            ("ls-files", "--others", "--exclude-standard"),
        }:
            return ""
        return ""

    gate.git = fake_git
    gate.git_ok = lambda *args: True
    gate.changed_files = lambda: [
        "scripts/check_internal_review_evidence.py",
        ".agent-loop/initiatives/test-agent-gate/"
        "reviews/test-agent-gate-internal-review-evidence.md",
        "docs/internal_reviews/historical-note.md",
        ".agent-loop/initiatives/example/reviews/example-external-review-response.md",
    ]
    try:
        os.environ.pop("INTERNAL_REVIEW_BASE_REF", None)
        os.environ["INTERNAL_REVIEW_CHUNK_ID"] = "WS-ENG-001-01"
        os.environ["PR_HEAD_SHA"] = reviewed
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(
            "WS-ENG-001-01\n"
            "open sub-agent sessions: none\n"
            "valid findings addressed: yes\n"
            f"Reviewed code SHA: {reviewed}\n"
            "Reviewed at: 2026-06-18T00:00:00Z\n"
            "Reviewer run IDs: 019eda83-6476-7230-895b-1877790c407b\n"
            "| Reviewer | Result | Blocking findings | Notes |\n"
            "|---|---:|---|---|\n"
            "| senior engineering | PASS | None | checked |\n"
            "| qa/test | PASS WITH LOW RISKS | None | checked |\n"
            "| security/auth | PASS | None | checked |\n"
            "| product/ops | PASS | None | checked |\n"
            "| ci integrity | PASS | None | checked |\n"
            "| reuse/dedup | PASS | None | checked |\n",
            encoding="utf-8",
        )
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            assert gate.main() == 0
    finally:
        gate.git = original_git
        gate.git_ok = original_git_ok
        gate.changed_files = original_changed_files
        evidence.unlink(missing_ok=True)
        evidence.parent.rmdir()
        evidence.parent.parent.rmdir()
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_evidence_main_rejects_external_response_without_internal_evidence() -> None:
    """External review responses do not satisfy required internal evidence."""
    gate = load_module(
        "review_gate_external_response_only",
        "scripts/check_internal_review_evidence.py",
    )
    original_env = os.environ.get("INTERNAL_REVIEW_BASE_REF")
    original_git = gate.git
    original_git_ok = gate.git_ok
    original_changed_files = gate.changed_files
    external_response = (
        ROOT / ".agent-loop/initiatives/test-agent-gate/"
        "reviews/test-agent-gate-external-review-response.md"
    )

    def fake_git(*args: str) -> str:
        if args == ("merge-base", "--is-ancestor", "origin/main", "HEAD"):
            return ""
        return ""

    gate.git = fake_git
    gate.git_ok = lambda *args: True
    gate.changed_files = lambda: [
        "scripts/check_internal_review_evidence.py",
        ".agent-loop/initiatives/test-agent-gate/"
        "reviews/test-agent-gate-external-review-response.md",
    ]
    try:
        os.environ.pop("INTERNAL_REVIEW_BASE_REF", None)
        external_response.parent.mkdir(parents=True, exist_ok=True)
        external_response.write_text(
            "# External Review Response\n\n## Source\n\nCodeRabbit\n",
            encoding="utf-8",
        )
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            assert gate.main() == 1
    finally:
        gate.git = original_git
        gate.git_ok = original_git_ok
        gate.changed_files = original_changed_files
        external_response.unlink(missing_ok=True)
        external_response.parent.rmdir()
        external_response.parent.parent.rmdir()
        if original_env is None:
            os.environ.pop("INTERNAL_REVIEW_BASE_REF", None)
        else:
            os.environ["INTERNAL_REVIEW_BASE_REF"] = original_env


def test_evidence_main_reports_missing_evidence_file() -> None:
    """Changed evidence paths that no longer exist produce structured failure."""
    gate = load_module(
        "review_gate_missing_evidence_file", "scripts/check_internal_review_evidence.py"
    )
    original_changed_files = gate.changed_files
    gate.changed_files = lambda: [
        "scripts/workstream_agent_gate.py",
        ".agent-loop/initiatives/example/reviews/deleted-internal-review-evidence.md",
    ]
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            assert gate.main() == 1
    finally:
        gate.changed_files = original_changed_files


def test_static_sensor_counts_untracked_text_lines() -> None:
    """The static sensor includes untracked text files in line totals."""
    sensor = load_module("agent_sensor", "scripts/workstream_agent_gate.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "new.md"
        sample.write_text("one\ntwo\n", encoding="utf-8")
        assert sensor.count_text_lines(str(sample)) == 2


def test_static_sensor_requires_resolved_base_ref() -> None:
    """The static sensor must not silently pass when no base ref resolves."""
    sensor = load_module("agent_sensor_base_ref", "scripts/workstream_agent_gate.py")
    original_ref_exists = sensor.ref_exists
    original_first_existing_ref = sensor.first_existing_ref
    sensor.ref_exists = lambda ref: False
    sensor.first_existing_ref = lambda *refs: None

    try:
        report = sensor.analyze("missing-base", "HEAD")
        assert report["result"] == "REVIEW_REQUIRED"
        assert report["findings"][0]["code"] == "BASE_REF_UNRESOLVED"
    finally:
        sensor.ref_exists = original_ref_exists
        sensor.first_existing_ref = original_first_existing_ref


def test_static_sensor_accumulates_numstat_for_duplicate_paths() -> None:
    """Line totals include committed, staged, and dirty changes to one file."""
    sensor = load_module("agent_sensor_numstat", "scripts/workstream_agent_gate.py")
    original_maybe_run = sensor.maybe_run

    def fake_maybe_run(cmd: list[str]) -> str:
        joined = " ".join(cmd)
        if "diff --numstat origin/main...HEAD" in joined:
            return "3\t1\tscripts/workstream_agent_gate.py"
        if cmd == ["git", "diff", "--numstat", "--cached"]:
            return "2\t0\tscripts/workstream_agent_gate.py"
        if cmd == ["git", "diff", "--numstat"]:
            return "1\t4\tscripts/workstream_agent_gate.py"
        if "ls-files --others --exclude-standard" in joined:
            return ""
        return ""

    sensor.maybe_run = fake_maybe_run
    try:
        added, deleted, rows = sensor.numstat("origin/main", "HEAD")
        assert added == 6
        assert deleted == 5
        assert rows == [("scripts/workstream_agent_gate.py", 6, 5)]
    finally:
        sensor.maybe_run = original_maybe_run


def test_static_sensor_flags_backend_config_as_ci_surface() -> None:
    """Backend config and migration-control paths are CI/build sensitive."""
    sensor = load_module("agent_sensor_ci_paths", "scripts/workstream_agent_gate.py")
    assert sensor.CI_PATTERNS.search("backend/pyproject.toml")
    assert sensor.CI_PATTERNS.search("backend/alembic.ini")
    assert sensor.CI_PATTERNS.search("backend/alembic/versions/0001_init.py")


def test_markdown_link_checker_collects_base_cached_dirty_and_untracked() -> None:
    """Markdown link collection uses PR refs plus local dirty-tree paths."""
    checker = load_module("markdown_link_checker", "scripts/check_markdown_links.py")
    original_check_output = checker.subprocess.check_output
    original_run = checker.subprocess.run

    def fake_check_output(cmd: list[str], text: bool) -> str:
        joined = " ".join(cmd)
        if "diff --name-only origin/main...HEAD" in joined:
            return "README.md\nbackend/app/main.py\n"
        if "diff --name-only --cached" in joined:
            return ".agent-loop/README.md\n"
        if cmd == ["git", "diff", "--name-only"]:
            return "docs/glossary.md\n"
        if "ls-files --others --exclude-standard" in joined:
            return "new.md\n"
        return ""

    checker.subprocess.check_output = fake_check_output
    checker.subprocess.run = lambda *args, **kwargs: SimpleNamespace(returncode=0)
    try:
        assert [str(path) for path in checker.changed_markdown_files()] == [
            "README.md",
            ".agent-loop/README.md",
            "docs/glossary.md",
            "new.md",
        ]
    finally:
        checker.subprocess.check_output = original_check_output
        checker.subprocess.run = original_run


def test_stale_wording_patterns_catch_variants() -> None:
    """Stale wording patterns catch case and separator variants."""
    stale = load_module("stale_wording", "scripts/check_stale_workstream_wording.py")
    sample = "\n".join(
        [
            "Garden " + "Roadmap",
            "task-" + "production control plane",
            "This repository does not use auto-" + "merge.",
            "Claude " + "Code support is not configured here.",
            "Approved" + "TaskArtifactBinding",
            "Effective" + "TaskSubmissionArtifactPolicy",
            "Effective" + "SubmissionArtifactPolicy",
            "Project" + "PreSubmitCheckerSpec",
            "locked_" + "task_" + "artifact_binding_id",
            "locked_" + "effective_" + "task_submission_artifact_policy_hash",
            "task artifact " + "binding",
            "effective task submission artifact " + "policy",
            "effective task " + "policy",
            "effective_" + "project_policy_hash",
            "effective project policy " + "hash",
            "effective policy " + "hashes",
            "generated task " + "pre-submit checker",
            "task-level " + "PreSubmitCheckerPolicy",
            "task-level " + "pre-submit",
            "project/task " + "policy",
            "profile-" + "scoped",
            "project/" + "profile",
            "pre-submit checker policy " + "hash",
            "pre_submit_checker_" + "policy_hash",
            "project pre-submit checker policy " + "hashes",
            "project checker " + "hash",
            "PreSubmitCheckerPolicy " + "hash",
            "PreSubmitCheckerPolicy snapshot/" + "hash",
            "NEEDS_REVISION: no payment owed " + "yet",
            "no accepted task without payment " + "record",
            "accepted work creates a pending payment " + "record",
            "contribution record is created when work is " + "accepted",
            "the evidence-backed record that accepted " + "work was completed",
            "accepted task must create a payment " + "record",
            "payment record attached to accepted " + "tasks",
            "acceptance creates a pending payment " + "record",
            "accepted transition creates payment " + "record",
            "payment record moves to " + "pending",
            "payment NONE -> PAID without accepted " + "task",
            "every accepted task updates " + "payment",
        ]
    )
    matches = [
        pattern.pattern
        for pattern in stale.FORBIDDEN_PATTERNS
        if pattern.search(sample)
    ]
    assert set(matches) == {
        "task-" + "production control plane",
        "garden " + "roadmap",
        "Approved" + "TaskArtifactBinding",
        "Effective" + "TaskSubmissionArtifactPolicy",
        "Effective" + "SubmissionArtifactPolicy",
        "Project" + "PreSubmitCheckerSpec",
        "task_" + "artifact_binding",
        "effective_" + "task_submission",
        "task artifact " + "binding",
        "effective task submission artifact " + "policy",
        "effective task " + "policy",
        "effective_" + "project_policy_hash",
        "effective project policy " + "hash(?:es)?",
        "effective policy " + "hash(?:es)?",
        "locked_" + "task_" + "artifact_binding_id",
        "locked_" + "effective_" + "task_submission_artifact_policy_hash",
        "generated task " + "pre-submit",
        "task-level " + "PreSubmitCheckerPolicy",
        "task-level " + "pre-submit",
        "project/task " + "policy",
        "profile-" + "scoped",
        "project/" + "profile",
        "pre-submit checker policy " + "hash(?:es)?",
        "pre_submit_checker_" + "policy_hash",
        "project pre-submit checker policy " + "hash(?:es)?",
        "project checker " + "hash(?:es)?",
        "PreSubmitCheckerPolicy " + "hash(?:es)?",
        "PreSubmitCheckerPolicy snapshot/" + "hash(?:es)?",
        "needs_revision:\\s+no payment owed yet",
        "no accepted task without payment " + "record",
        "accepted work creates (?:a )?pending payment " + "record",
        "contribution record is created when work is " + "accepted",
        "the evidence-backed record that accepted " + "work",
        "accepted tasks?.{0,80}payment " + "records?",
        "payment records?.{0,80}accepted " + "tasks?",
        "acceptance.{0,80}payment " + "records?",
        "accepted transition.{0,80}payment " + "records?",
        "payment record (?:moves to pending|can be generated)",
        "payment\\s+NONE\\s*->\\s*PAID.{0,80}accepted task",
        "every accepted task updates " + "payment",
    }
    case_variant_sample = "\n".join(
        [
            "approved" + "taskartifactbinding",
            "effective" + "TaskSubmissionArtifactPolicy",
            "PROJECT" + "PRESUBMITCHECKERSPEC",
        ]
    )
    case_variant_matches = [
        pattern.pattern
        for pattern in stale.FORBIDDEN_PATTERNS
        if pattern.search(case_variant_sample)
    ]
    assert {
        "Approved" + "TaskArtifactBinding",
        "Effective" + "TaskSubmissionArtifactPolicy",
        "Project" + "PreSubmitCheckerSpec",
    }.issubset(set(case_variant_matches))
    failures = stale.forbidden_path_failures(
        [Path(".claude/settings.json"), Path("CLAUDE.md")]
    )
    assert len(failures) == 2


def test_active_shared_contract_rejects_retired_contracts() -> None:
    """Live shared docs cannot revive retired roles or compensation models."""
    stale = load_module(
        "stale_wording_active_compensation",
        "scripts/check_stale_workstream_wording.py",
    )
    pattern_samples = (
        "Operator / Access Administrator",
        "contribution/payment/reputation records",
        "Project Manager manages guides and policies",
        "PM -> UI: publish contribution policy",
        "submitter/both",
        "reviewer/both",
        "Submitter or Both grant",
        "Reviewer or Both grant",
        "ProjectRoleGrant(submitter|reviewer|both)",
        "`submitter`, `reviewer`, or `both`",
        "| Both | exact project",
        "Active submitter, reviewer, and both grants",
        "ProjectRoleGrant values are exactly `submitter` and `reviewer`.",
        "Project issue roles are exactly `submitter` or `reviewer`.",
        "independent `submitter` and `reviewer` ProjectRoleGrants",
        "Adjudicator actions remain unavailable until their lifecycle is activated",
        "adjudication actions unavailable until separately activated",
        "locks actor/link/grant/assignment rows",
        "service-assignment authority",
        "service-actor assignment",
        "fixed service principals/assignments",
        "service assignments",
        "service principals and exact planned assignments",
        "identity/action assignment source",
        "service-action assignments",
        "service identities and exact assignments",
        "service identities, exact assignments",
        "AUTH-09 assigns",
        "planned assignment remains inert",
        "PermissionId mapping, or exact assignment",
        "AUTH-09 persists these exact service actors and assignments",
        "do not become normal ActorProfiles",
        "Proposed after 02C3, AUTH-09, and AUTH custody registration",
        "worker, reviewer, or project manager",
        "operators, workers, reviewers",
        "reviews, and payments",
        "owning compensation authority",
        "Finance reconciles",
        "compensation publication",
        "published compensation definition",
        "CompensationPolicyVersion",
        "CompensationPolicy",
        "CompensationRule",
        "CompensationAwardDefinition",
        "Compensation\n  PolicyVersion",
        "Compensation\n  Policy",
        "Compensation\n  Rule",
        "Compensation\n  AwardDefinition",
        "compensation_policy",
        "compensation_rule_id",
        "compensation\n  policy",
        "compensation\n  version",
        "compensation\n  rule",
        "PaymentPolicy",
        "PaymentRecord",
        "PaymentAdjustment",
        "Payment\n  Policy",
        "Payment\n  Record",
        "Payment\n  Adjustment",
        "payment-policy",
        "payment-record",
        "payment_ledger",
        "payment_adjustment",
        "locked_payment_policy_version",
        "payment_reconciliation",
        "payment truth",
        "Payment And Reputation",
        "compensation fulfillment/payment status",
        "payment status",
        "payment\n  policy",
        "payment\n  records",
        "payment\n  ledger",
        "payment exposure",
        "payment follow-up",
        "payment adjustment record",
        "accepted-unpaid",
        "accepted but unpaid",
        "contribution record generated on acceptance",
        "contribution record creation after acceptance",
        "accepted paid output",
        "award/payment record",
        "PAYOUT_SUBMITTED",
        "PAID",
        "DISPUTED",
    )
    sample = " ".join(pattern_samples)
    active_patterns = stale.ACTIVE_SHARED_CONTRACT_PATTERNS

    assert len(pattern_samples) == len(active_patterns)
    for pattern, pattern_sample in zip(active_patterns, pattern_samples, strict=True):
        assert pattern.search(pattern_sample), pattern.pattern

    additional_pattern_samples = {
        r"\badjudicat(?:ion|or) actions\s+(?:remain\s+)?unavailable\s+until\s+separately\s+activated": (
            "Adjudicator actions remain unavailable until separately activated",
        ),
        r"\bFinance\s+(?:reconciles|follows)\b": ("Finance follows",),
        r"\bCompensation\s+Policy\s*Version\b": ("Compensation\n  Policy\n  Version",),
        r"\bCompensation\s+Award\s*Definition\b": (
            "Compensation\n  Award\n  Definition",
        ),
    }
    active_pattern_by_source = {pattern.pattern: pattern for pattern in active_patterns}
    assert additional_pattern_samples.keys() <= active_pattern_by_source.keys()
    for pattern_source, extra_samples in additional_pattern_samples.items():
        assert all(
            active_pattern_by_source[pattern_source].search(extra_sample)
            for extra_sample in extra_samples
        )

    required_patterns = {
        r"\bcompensation\s+publication\b",
        r"\bpublished\s+compensation\s+definition\b",
    }
    assert required_patterns <= {pattern.pattern for pattern in active_patterns}
    assert all(pattern.search(sample) for pattern in active_patterns)
    assert all(
        pattern.search("compensation\n  publication")
        for pattern in active_patterns
        if pattern.pattern == r"\bcompensation\s+publication\b"
    )
    assert all(
        pattern.search("published\n  compensation\n  definition")
        for pattern in active_patterns
        if pattern.pattern == r"\bpublished\s+compensation\s+definition\b"
    )
    assert stale.is_active_shared_contract_path(Path("README.md"))
    assert stale.is_active_shared_contract_path(Path("AGENTS.md"))
    assert stale.is_active_shared_contract_path(Path(".agent-loop/LOOP_STATE.md"))
    assert stale.is_active_shared_contract_path(Path(".agent-loop/WORK_QUEUE.md"))
    assert stale.is_active_shared_contract_path(
        Path(".agent-loop/policies/security-boundaries.md")
    )
    assert stale.is_active_shared_contract_path(
        Path(".agent-loop/initiatives/example/PLAN.md")
    )
    assert not stale.is_active_shared_contract_path(
        Path(".agent-loop/initiatives/example/reviews/evidence.md")
    )
    assert stale.is_active_shared_contract_path(Path("docs/architecture_data_model.md"))
    assert stale.is_active_shared_contract_path(
        Path("docs/current_system_data_flow.html")
    )
    assert stale.is_active_shared_contract_path(
        Path("docs/architecture_brief/workstream_architecture_brief.md")
    )


def test_historical_docs_do_not_define_live_compensation_contract() -> None:
    """Historical/reference files may state explicitly what the clean cut removed."""
    stale = load_module(
        "stale_wording_historical_compensation",
        "scripts/check_stale_workstream_wording.py",
    )

    assert not stale.is_active_shared_contract_path(
        Path("docs/reference_specs/example.md")
    )
    assert not stale.is_active_shared_contract_path(
        Path("docs/internal_reviews/example.md")
    )
    assert not stale.is_active_shared_contract_path(
        Path("docs/spec_chunk_3_project_guide_foundation.md")
    )
    assert stale.is_active_shared_contract_path(Path("docs/spec_chunk_5_example.md"))
    assert stale.is_active_shared_contract_path(Path("docs/review_architecture.md"))

    auth_gate = load_module(
        "stale_authorization_docs_historical_compensation",
        "scripts/check_stale_authorization_docs.py",
    )
    artifact_gate = load_module(
        "stale_artifact_contracts_historical_compensation",
        "scripts/check_stale_artifact_contracts.py",
    )
    assert stale.HISTORICAL_PATHS == set(auth_gate.HISTORICAL_PATHS)
    assert stale.HISTORICAL_PATHS == artifact_gate.HISTORICAL_PATHS


def test_current_runtime_walkthrough_rejects_unimplemented_compensation_records() -> (
    None
):
    """The current-backend walkthrough cannot claim target compensation runtime."""
    stale = load_module(
        "stale_wording_current_runtime_compensation",
        "scripts/check_stale_workstream_wording.py",
    )
    sample = " ".join(
        (
            "ContributionPolicy",
            "ContributionPolicyVersion",
            "ContributionRule",
            "ContributionAwardDefinition",
            "ProjectCompensationAdapterBinding",
            "ReviewLease",
            "ContributionRecord",
            "CompensationAward",
            "CompensationFulfillmentReceipt",
            "CompensationStatusProjection",
        )
    )

    assert {
        pattern.pattern
        for pattern in stale.UNIMPLEMENTED_CURRENT_RUNTIME_COMPENSATION_PATTERNS
    } == {
        r"\bContributionPolicy\b",
        r"\bContributionPolicyVersion\b",
        r"\bContributionRule\b",
        r"\bContributionAwardDefinition\b",
        r"\bProjectCompensationAdapterBinding\b",
        r"\bReviewLease\b",
        r"\bContributionRecord\b",
        r"\bCompensationAward\b",
        r"\bCompensationFulfillmentReceipt\b",
        r"\bCompensationStatusProjection\b",
    }
    assert all(
        pattern.search(sample)
        for pattern in stale.UNIMPLEMENTED_CURRENT_RUNTIME_COMPENSATION_PATTERNS
    )
    current_walkthrough = Path("docs/current_system_data_flow.html").read_text(
        encoding="utf-8"
    )
    assert not any(
        pattern.search(current_walkthrough)
        for pattern in stale.UNIMPLEMENTED_CURRENT_RUNTIME_COMPENSATION_PATTERNS
    )


def test_stale_wording_skips_only_docs_internal_reviews_prefix() -> None:
    """Historical review archives are skipped without hiding other folders."""
    stale = load_module(
        "stale_wording_skip_prefix",
        "scripts/check_stale_workstream_wording.py",
    )
    original_check_output = stale.subprocess.check_output
    original_cwd = Path.cwd()

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "docs/internal_reviews").mkdir(parents=True)
        (root / "other/internal_reviews").mkdir(parents=True)
        (root / "active").mkdir()
        (root / "docs/internal_reviews/archive.md").write_text(
            "old review\n", encoding="utf-8"
        )
        (root / "other/internal_reviews/file.md").write_text(
            "active review\n", encoding="utf-8"
        )
        (root / "active/file.md").write_text("active doc\n", encoding="utf-8")

        def fake_check_output(cmd: list[str], text: bool) -> str:
            if cmd == ["git", "ls-files"]:
                return "\n".join(
                    [
                        "docs/internal_reviews/archive.md",
                        "other/internal_reviews/file.md",
                        "active/file.md",
                    ]
                )
            if cmd == ["git", "ls-files", "--others", "--exclude-standard"]:
                return ""
            return ""

        stale.subprocess.check_output = fake_check_output
        os.chdir(root)
        try:
            scanned = {path.as_posix() for path in stale.tracked_and_new_files()}
        finally:
            os.chdir(original_cwd)
            stale.subprocess.check_output = original_check_output

    assert "docs/internal_reviews/archive.md" not in scanned
    assert "other/internal_reviews/file.md" in scanned
    assert "active/file.md" in scanned


def test_stale_wording_catches_multiline_legacy_status_reconstruction() -> None:
    """The stale wording gate catches split legacy status construction."""
    stale = load_module(
        "stale_wording_multiline_legacy_status",
        "scripts/check_stale_workstream_wording.py",
    )
    sample = 'LEGACY = "auto" \\\n    + "_checking"\n'
    pattern = next(
        pattern
        for pattern in stale.FORBIDDEN_PATTERNS
        if pattern.pattern == r"auto\s*[\"']?\s*\\?\s*\+\s*[\"']?_checking"
    )

    match = pattern.search(sample)

    assert match is not None
    assert stale.line_number_for_offset(sample, match.start()) == 1


def test_loop_memory_state_rejects_pre_merge_status() -> None:
    """Main loop memory must not keep pre-merge checkpoint language."""
    checker = load_module(
        "loop_memory_state_rejects", "scripts/check_loop_memory_state.py"
    )
    original_root = checker.ROOT
    original_status_files = checker.INITIATIVE_STATUS_FILES
    original_contract_files = checker.STATUS_BEARING_CONTRACT_FILES
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".agent-loop/initiatives/example").mkdir(parents=True)
        (root / ".agent-loop/LOOP_STATE.md").write_text(
            "Status: PR #23 open; awaiting human merge decision\n",
            encoding="utf-8",
        )
        (root / ".agent-loop/WORK_QUEUE.md").write_text(
            "| `WS-ENG-001-01` | Bootstrap | L1 | In progress |\n",
            encoding="utf-8",
        )
        (root / ".agent-loop/REVIEW_LOG.md").write_text(
            "Status: internal reviewer fanout complete.\n",
            encoding="utf-8",
        )
        (root / ".agent-loop/initiatives/example/STATUS.md").write_text(
            "Current gate: human merge checkpoint\n",
            encoding="utf-8",
        )
        checker.ROOT = root
        checker.INITIATIVE_STATUS_FILES = (".agent-loop/initiatives/example/STATUS.md",)
        checker.STATUS_BEARING_CONTRACT_FILES = ()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                assert checker.main() == 1
        finally:
            checker.ROOT = original_root
            checker.INITIATIVE_STATUS_FILES = original_status_files
            checker.STATUS_BEARING_CONTRACT_FILES = original_contract_files


def test_loop_memory_state_accepts_merged_fixture() -> None:
    """Merged loop memory fixtures should pass the main-only guard."""
    checker = load_module(
        "loop_memory_state_accepts", "scripts/check_loop_memory_state.py"
    )
    original_root = checker.ROOT
    original_status_files = checker.INITIATIVE_STATUS_FILES
    original_contract_files = checker.STATUS_BEARING_CONTRACT_FILES
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".agent-loop/initiatives/example").mkdir(parents=True)
        (root / ".agent-loop/LOOP_STATE.md").write_text(
            "Status: `WS-ENG-001-01` merged through PR #23; no active chunk\n",
            encoding="utf-8",
        )
        (root / ".agent-loop/WORK_QUEUE.md").write_text(
            "| None | No active chunk | - | Inactive |\n",
            encoding="utf-8",
        )
        (root / ".agent-loop/REVIEW_LOG.md").write_text(
            "Status: merged through PR #23.\n",
            encoding="utf-8",
        )
        (root / ".agent-loop/initiatives/example/STATUS.md").write_text(
            "Current gate: stopped after merge memory update\n",
            encoding="utf-8",
        )
        checker.ROOT = root
        checker.INITIATIVE_STATUS_FILES = (".agent-loop/initiatives/example/STATUS.md",)
        checker.STATUS_BEARING_CONTRACT_FILES = ()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                assert checker.main() == 0
        finally:
            checker.ROOT = original_root
            checker.INITIATIVE_STATUS_FILES = original_status_files
            checker.STATUS_BEARING_CONTRACT_FILES = original_contract_files


def test_loop_memory_state_rejects_known_merged_pr_staleness() -> None:
    """Known PR #119/#120/#122 facts cannot regress to pending or active."""
    checker = load_module(
        "loop_memory_known_merge_staleness", "scripts/check_loop_memory_state.py"
    )
    stale_samples = (
        "AUTH-05B runtime is reviewed; publication is pending.",
        (
            "AUTH-05B runtime SHA is internally reviewed. Its current gate is "
            "PR publication and external checks."
        ),
        "| `WS-AUTH-001-05B` | In review | branch | - | pending |",
        "PR #120's branch is ready for review.",
        (
            "# Chunk Contract: WS-ART-001-OBJECT-STORAGE-AMENDMENT\n"
            "Status: Active planning only"
        ),
        "PR #122 remains active.",
        "PR publication and external review remain pending.",
        "PR publication and external checks remain pending.",
    )
    for sample in stale_samples:
        assert any(
            pattern.search(sample) for pattern, _message in checker.FORBIDDEN_PATTERNS
        ), sample
    valid_candidates = (
        "`WS-AUTH-001-06` remains inactive until explicit user start.",
        "`WS-ART-001-02A1` remains inactive until explicit user start.",
    )
    for sample in valid_candidates:
        assert not any(
            pattern.search(sample) for pattern, _message in checker.FORBIDDEN_PATTERNS
        ), sample


def valid_loop_intent() -> str:
    """Return one valid committed merge-intent JSON fixture."""
    return (
        '{"schema_version":2,"initiative_id":"WS-AUTH-001",'
        '"chunk_id":"WS-AUTH-001-06","chunk_title":"Canonical Actor Profile",'
        '"next_chunk_id":"WS-AUTH-001-07","next_chunk_title":"Authorization Kernel",'
        '"next_requires_explicit_start":true}\n'
    )


def test_pr_templates_share_merge_intent_contract() -> None:
    """Both human templates must state the same schema-v2 merge-intent contract."""

    def merge_intent_contract(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        start = text.index("Add exactly one new schema-v2 merge-intent file")
        end = text.index("\n## Goal", start)
        return " ".join(text[start:end].split())

    assert merge_intent_contract(
        ROOT / ".agent-loop/templates/PR_TRUST_BUNDLE.md"
    ) == merge_intent_contract(ROOT / ".github/pull_request_template.md")


def _assert_contributor_entry_contract(documents: dict[str, str]) -> None:
    """Assert stable contributor-entry policy across the canonical surfaces."""
    contribution = documents["CONTRIBUTING.md"]
    required_contribution_semantics = (
        "repository contributor",
        "Workstream product **Contributor**",
        "Existing commit or patch is preservation and discovery input only".lower(),
        "never retroactive authorization",
        "GitHub issue",
        "No agent or automation may infer merge approval".lower(),
        "Automated Merge Memory never starts it automatically",
        "Only independently verified signed automation state is canonical authority".lower(),
    )
    lowered = contribution.lower()
    for phrase in required_contribution_semantics:
        assert phrase.lower() in lowered, phrase
    normalized_contribution = " ".join(contribution.split())
    required_procedures = (
        "## Before Work",
        "dispatch `Loop Memory Explicit Event` on exact current `main`",
        "Confirm the target initiative is active for the exact chunk and phase",
        "## Contributors Without Write Permission",
        "preserving the proposal as discovery input",
        "placing the required intent, discovery, plan, chunk map, and exact chunk contract on trusted `main`",
        "dispatching the signed start for that exact contract and current-main SHA",
        "applying or recreating only the in-contract parts of the preserved patch",
        "crediting the original contributor in the resulting PR where applicable",
        "## Implementation",
        "Reconcile with current `main` before publication",
        "## Before Opening A Pull Request",
        "Complete every required internal reviewer track",
        "Ensure the reviewed implementation SHA and signed-start provenance are recorded",
        "Add exactly one schema-v2 merge intent",
        "Run the chunk's complete verification commands against the current base",
        "no reviewer agent remains active",
        "## Review, Merge, And Stop",
        "reviews the final exact PR head",
        "Verify its manifest, signature, ledger, loop view, queue, and initiative projections together",
        "Work stops",
    )
    for marker in required_procedures:
        assert marker in normalized_contribution, marker

    canonical_loop = (
        "Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> "
        "Implementation -> Evidence -> Internal Review -> PR -> Human "
        "Checkpoint -> Automated Merge Memory -> Stop"
    )
    assert canonical_loop in " ".join(contribution.split())
    for path in ("README.md", "AGENTS.md", ".agent-loop/README.md"):
        normalized = " ".join(documents[path].replace("`", "").split())
        assert canonical_loop in normalized, path
        assert "at most one active planning or implementation chunk" in normalized, path
        assert "distinct initiatives may" in normalized and "concurrently" in normalized, path


def test_contributor_entry_semantics_are_positive_and_fail_closed() -> None:
    """Canonical onboarding semantics survive positive fixtures and reject drift."""
    paths = (
        "CONTRIBUTING.md",
        "README.md",
        "AGENTS.md",
        ".agent-loop/README.md",
    )
    documents = {
        path: (ROOT / path).read_text(encoding="utf-8") for path in paths
    }
    _assert_contributor_entry_contract(documents)
    mutations = (
        ("CONTRIBUTING.md", "repository contributor"),
        ("README.md", "Automated Merge Memory"),
        ("AGENTS.md", "at most one active planning or implementation chunk"),
        ("CONTRIBUTING.md", "never retroactive authorization"),
        (
            "CONTRIBUTING.md",
            "Only independently verified signed automation state is canonical authority",
        ),
        ("CONTRIBUTING.md", "No agent or automation may infer merge approval"),
        (
            "CONTRIBUTING.md",
            "Automated Merge Memory never starts it automatically",
        ),
        ("CONTRIBUTING.md", "## Before Work"),
        (
            "CONTRIBUTING.md",
            "dispatch `Loop Memory Explicit",
        ),
        ("CONTRIBUTING.md", "preserving the proposal as discovery input"),
        (
            "CONTRIBUTING.md",
            "dispatching the signed start for that exact contract and current-main SHA",
        ),
        (
            "CONTRIBUTING.md",
            "applying or recreating only the in-contract parts",
        ),
        ("CONTRIBUTING.md", "## Before Opening A Pull Request"),
        ("CONTRIBUTING.md", "Complete every required internal reviewer track"),
        ("CONTRIBUTING.md", "reviews the final exact PR head"),
        ("CONTRIBUTING.md", "Work stops"),
    )
    for path, phrase in mutations:
        mutated = dict(documents)
        assert phrase.lower() in mutated[path].lower()
        start = mutated[path].lower().index(phrase.lower())
        mutated[path] = mutated[path][:start] + mutated[path][start + len(phrase) :]
        try:
            _assert_contributor_entry_contract(mutated)
        except AssertionError:
            continue
        raise AssertionError(f"contributor-entry drift was accepted: {path}: {phrase}")


def _signed_start_fields(text: str) -> tuple[str, ...]:
    """Return the stable signed-start provenance labels from a trust template."""
    labels = (
        "Signed start run",
        "Authorized main SHA",
        "Phase",
        "Contract path",
        "Signed contract blob SHA",
        "Reviewed implementation SHA",
    )
    return tuple(label for label in labels if f"- {label}:" in text)


def test_pr_templates_share_signed_start_provenance_fields() -> None:
    """Both trust templates expose the same complete provenance navigation set."""
    paths = (
        ROOT / ".github/pull_request_template.md",
        ROOT / ".agent-loop/templates/PR_TRUST_BUNDLE.md",
    )
    texts = [path.read_text(encoding="utf-8") for path in paths]
    expected = (
        "Signed start run",
        "Authorized main SHA",
        "Phase",
        "Contract path",
        "Signed contract blob SHA",
        "Reviewed implementation SHA",
    )
    assert all(_signed_start_fields(text) == expected for text in texts)
    warning = "Only independently verified signed automation state is canonical authority."
    assert all(warning in text for text in texts)
    for index, label in enumerate(expected):
        mutated = list(texts)
        mutated[index % 2] = mutated[index % 2].replace(f"- {label}:", "", 1)
        assert _signed_start_fields(mutated[0]) != _signed_start_fields(mutated[1])


def updater_base64(value: str) -> str:
    """Return GitHub-contents-style base64 text."""
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def sign_loop_state_with_domain(
    updater, root: Path, private_key: Path, domain: bytes
) -> None:
    """Sign canonical generated state with one explicit test signature domain."""
    payload = bytearray(domain)
    for relative_path in (
        updater.STATE_PATH,
        updater.RENDERED_PATH,
        updater.LEDGER_PATH,
    ):
        path_bytes = relative_path.as_posix().encode("ascii")
        content = (root / relative_path).read_bytes()
        payload.extend(len(path_bytes).to_bytes(4, "big"))
        payload.extend(path_bytes)
        payload.extend(len(content).to_bytes(8, "big"))
        payload.extend(content)
    with tempfile.NamedTemporaryFile() as payload_file:
        payload_file.write(payload)
        payload_file.flush()
        signed = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(private_key),
                "-in",
                payload_file.name,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    (root / updater.SIGNATURE_PATH).write_text(
        base64.b64encode(signed).decode("ascii") + "\n", encoding="ascii"
    )


def loop_record(
    module,
    *,
    sha: str = "a" * 40,
    first_parent_sha: str = "0" * 40,
    merged_at: str = "2026-07-14T20:00:00Z",
    pr_number: int = 120,
) -> dict:
    """Return one complete generated-state fixture."""
    metadata = module.parse_loop_metadata(valid_loop_intent())
    return {
        "schema_version": module.SCHEMA_VERSION,
        "repository": "Flow-Research/workstream",
        "state_branch": "automation/loop-memory",
        "updated_at": merged_at,
        "source": {
            "main_sha": sha,
            "first_parent_sha": first_parent_sha,
            "pr_number": pr_number,
            "pr_url": f"https://github.com/Flow-Research/workstream/pull/{pr_number}",
            "pr_title": "Canonical actor profile",
            "head_sha": "b" * 40,
            "head_ref": "codex/ws-auth-001-06",
            "merged_at": merged_at,
            "merged_by": "manager",
            "intent_path": ".agent-loop/merge-intents/WS-AUTH-001-06.json",
            "intent_blob_sha": "d" * 40,
        },
        "completed_chunk": module.asdict(metadata),
        "active": {"planning_chunk": None, "implementation_chunk": None},
        "gate": {
            "status": "stopped_after_merge",
            "next_chunk_id": metadata.next_chunk_id,
            "next_chunk_title": metadata.next_chunk_title,
            "next_requires_explicit_start": True,
        },
        "checks": {
            "required": {
                name: {"kind": "check_run", "conclusion": "success", "url": None}
                for name in module.REQUIRED_CHECKS
            },
            "all_required_passed": True,
        },
    }


def planning_intake_record(module, *, first_parent_sha: str = "a" * 40) -> dict:
    """Return one signed planning-intake merge fixture."""
    metadata = module.parse_loop_metadata(
        '{"schema_version":2,"initiative_id":"WS-NEW-001",'
        '"chunk_id":"WS-NEW-001-PLAN","chunk_title":"New Initiative Plan",'
        '"next_chunk_id":"WS-NEW-001-01","next_chunk_title":"First Implementation",'
        '"next_requires_explicit_start":true}'
    )
    record = loop_record(
        module,
        sha="c" * 40,
        first_parent_sha=first_parent_sha,
        pr_number=201,
        merged_at="2026-07-22T08:00:00Z",
    )
    record["source"].update(
        head_sha="e" * 40,
        head_ref="codex/ws-new-001-plan",
        intent_path=".agent-loop/merge-intents/WS-NEW-001-PLAN.json",
    )
    record["completed_chunk"] = module.asdict(metadata)
    record["gate"].update(
        next_chunk_id=metadata.next_chunk_id,
        next_chunk_title=metadata.next_chunk_title,
    )
    root = ".agent-loop/initiatives/WS-NEW-001-example"
    paths = [
        ".agent-loop/merge-intents/WS-NEW-001-PLAN.json",
        *(f"{root}/{name}" for name in sorted(module.PLANNING_ROOT_FILES)),
        f"{root}/chunks/WS-NEW-001-01-first.md",
        f"{root}/reviews/WS-NEW-001-PLAN-internal-review-evidence.md",
        f"{root}/reviews/WS-NEW-001-PLAN-pr-trust-bundle.md",
    ]
    record["planning_intake"] = {
        "schema_version": module.PLANNING_INTAKE_VERSION,
        "initiative_directory": "WS-NEW-001-example",
        "base_tree_sha": "2" * 40,
        "head_tree_sha": "f" * 40,
        "first_parent_tree_sha": "3" * 40,
        "merge_tree_sha": "4" * 40,
        "delta_sha256": "5" * 64,
        "changed_paths": sorted(paths),
    }
    return record


def test_planning_intake_is_stopped_idempotent_and_new_initiative_only() -> None:
    """Planning intake creates stopped state and never reopens an initiative."""
    updater = load_module("planning_intake_state", "scripts/update_post_merge_memory.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        base = loop_record(updater)
        base["legacy_exemptions"] = []
        updater.apply_merge_record(root, base)
        intake = planning_intake_record(updater)
        assert updater.apply_merge_record(root, intake) is True
        assert updater.apply_merge_record(root, intake) is False
        state = json.loads((root / updater.STATE_PATH).read_text(encoding="utf-8"))
        assert state["active"] == {
            "planning_chunk": None,
            "implementation_chunk": None,
        }
        assert state["gate"] == {
            "status": "stopped_after_merge",
            "next_chunk_id": "WS-NEW-001-01",
            "next_chunk_title": "First Implementation",
            "next_requires_explicit_start": True,
        }
        second = planning_intake_record(updater, first_parent_sha="c" * 40)
        second["source"].update(
            main_sha="1" * 40,
            pr_number=202,
            pr_url="https://github.com/Flow-Research/workstream/pull/202",
            merged_at="2026-07-22T09:00:00Z",
        )
        second["updated_at"] = second["source"]["merged_at"]
        assert_loop_error(
            updater,
            lambda: updater.apply_merge_record(root, second),
            "initiative already exists",
        )


def test_planning_intake_record_schema_fails_closed() -> None:
    """Planning intake identity, tree, checks, and successor remain exact."""
    updater = load_module("planning_intake_schema", "scripts/update_post_merge_memory.py")
    mutations = (
        ("planning intake", lambda item: item["planning_intake"].update(delta_sha256="bad")),
        ("intent path", lambda item: item["completed_chunk"].update(chunk_id="WS-NEW-001-01")),
        ("planning intake", lambda item: item["completed_chunk"].update(next_requires_explicit_start=False)),
        ("aggregate check evidence", lambda item: item["checks"].update(all_required_passed=False)),
    )
    for expected, mutate in mutations:
        record = planning_intake_record(updater)
        mutate(record)
        assert_loop_error(
            updater,
            lambda record=record: updater._validate_record(record),
            expected,
        )


def test_independent_checker_accepts_and_mutates_planning_intake_state() -> None:
    """Independent validation recomputes planning paths, trees, and digest."""
    updater = load_module("planning_checker_updater", "scripts/update_post_merge_memory.py")
    checker = load_module("planning_checker", "scripts/check_loop_memory_state.py")
    assert checker._planning_path_failures({}, {}, "record")
    malformed_intake = {
        "initiative_directory": "WS-NEW-001-.hidden",
        "changed_paths": [],
    }
    assert checker._planning_path_failures(
        malformed_intake,
        {"initiative_id": "WS-NEW-001", "next_chunk_id": "WS-NEW-001-01"},
        "record",
    )
    nested_intake = {
        "initiative_directory": "WS-NEW-001-example",
        "changed_paths": [
            ".agent-loop/merge-intents/WS-NEW-001-PLAN.json",
            ".agent-loop/initiatives/WS-NEW-001-example/chunks/nested/unsafe.md",
        ],
    }
    assert checker._planning_path_failures(
        nested_intake,
        {"initiative_id": "WS-NEW-001", "next_chunk_id": "WS-NEW-001-01"},
        "record",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        repository = Path(tmpdir) / "repository"
        subprocess.run(["git", "init", "--initial-branch", "base", str(repository)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
        (repository / "base.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-m", "base"], check=True, stdout=subprocess.PIPE)
        base_sha = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        record = planning_intake_record(updater)
        for path in record["planning_intake"]["changed_paths"]:
            target = repository / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{path}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-m", "plan"], check=True, stdout=subprocess.PIPE)
        head_sha = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        subprocess.run(["git", "-C", str(repository), "checkout", "-b", "main", base_sha], check=True, stdout=subprocess.PIPE)
        (repository / "main.txt").write_text("advanced\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-m", "advance"], check=True, stdout=subprocess.PIPE)
        first_parent = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        subprocess.run(["git", "-C", str(repository), "merge", "--squash", head_sha], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(repository), "commit", "-m", "squash plan"], check=True, stdout=subprocess.PIPE)
        merge_sha = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        base_tree, base_entries = checker._git_tree(repository, base_sha)
        head_tree, head_entries = checker._git_tree(repository, head_sha)
        first_parent_tree, first_parent_entries = checker._git_tree(repository, first_parent)
        merge_tree, merge_entries = checker._git_tree(repository, merge_sha)
        delta = {path: head_entries.get(path) for path in sorted(set(base_entries) | set(head_entries)) if base_entries.get(path) != head_entries.get(path)}
        assert delta == {path: merge_entries.get(path) for path in sorted(set(first_parent_entries) | set(merge_entries)) if first_parent_entries.get(path) != merge_entries.get(path)}
        record["source"].update(main_sha=merge_sha, first_parent_sha=first_parent, head_sha=head_sha)
        record["planning_intake"].update(
            base_tree_sha=base_tree,
            head_tree_sha=head_tree,
            first_parent_tree_sha=first_parent_tree,
            merge_tree_sha=merge_tree,
            delta_sha256=hashlib.sha256(json.dumps(delta, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest(),
        )
        subprocess.run(["git", "-C", str(repository), "branch", "-D", "base"], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(repository), "reflog", "expire", "--expire=now", "--all"], check=True)
        subprocess.run(["git", "-C", str(repository), "gc", "--prune=now"], check=True, stdout=subprocess.PIPE)
        assert subprocess.run(["git", "-C", str(repository), "cat-file", "-e", head_sha], check=False).returncode != 0
        assert checker._record_failures(record, "record", repository) == []
        mutations = (
            lambda item: item["planning_intake"].update(delta_sha256="0" * 64),
            lambda item: item["planning_intake"].update(changed_paths=[]),
            lambda item: item["planning_intake"]["changed_paths"].append("backend/app/unsafe.py"),
            lambda item: item["planning_intake"]["changed_paths"].append(".agent-loop/initiatives/WS-NEW-001-example/chunks/.hidden.md"),
            lambda item: item["planning_intake"]["changed_paths"].append(".agent-loop/initiatives/WS-NEW-001-example/chunks/AGENTS.md"),
            lambda item: item["planning_intake"]["changed_paths"].remove(".agent-loop/initiatives/WS-NEW-001-example/PLAN.md"),
            lambda item: item["planning_intake"].update(merge_tree_sha="0" * 40),
            lambda item: item["completed_chunk"].update(chunk_id="WS-NEW-001-01"),
            lambda item: item["completed_chunk"].update(next_requires_explicit_start=False),
            lambda item: item.update(active={"planning_chunk": "WS-NEW-001-PLAN", "implementation_chunk": None}),
            lambda item: item["checks"].update(all_required_passed=False),
        )
        for mutate in mutations:
            changed = json.loads(json.dumps(record))
            mutate(changed)
            assert checker._record_failures(changed, "record", repository)
        root = Path(tmpdir) / "state"
        updater.apply_merge_record(root, record)
        assert checker.generated_state_failures(root, repository) == []

        rebase_repository = Path(tmpdir) / "rebase-repository"
        subprocess.run(["git", "init", "--initial-branch", "topic", str(rebase_repository)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(rebase_repository), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(rebase_repository), "config", "user.name", "Test"], check=True)
        (rebase_repository / "base.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(rebase_repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(rebase_repository), "commit", "-m", "base"], check=True, stdout=subprocess.PIPE)
        rebase_base = subprocess.run(["git", "-C", str(rebase_repository), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        for path in record["planning_intake"]["changed_paths"]:
            target = rebase_repository / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{path}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(rebase_repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(rebase_repository), "commit", "-m", "original plan"], check=True, stdout=subprocess.PIPE)
        original_head = subprocess.run(["git", "-C", str(rebase_repository), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        subprocess.run(["git", "-C", str(rebase_repository), "checkout", "-b", "main", rebase_base], check=True, stdout=subprocess.PIPE)
        (rebase_repository / "main.txt").write_text("advanced\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(rebase_repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(rebase_repository), "commit", "-m", "advance"], check=True, stdout=subprocess.PIPE)
        rebase_first_parent = subprocess.run(["git", "-C", str(rebase_repository), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        subprocess.run(["git", "-C", str(rebase_repository), "cherry-pick", original_head], check=True, stdout=subprocess.PIPE)
        rebase_merge = subprocess.run(["git", "-C", str(rebase_repository), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        before_tree, before_entries = checker._git_tree(rebase_repository, rebase_first_parent)
        after_tree, after_entries = checker._git_tree(rebase_repository, rebase_merge)
        rebase_delta = {path: after_entries.get(path) for path in sorted(set(before_entries) | set(after_entries)) if before_entries.get(path) != after_entries.get(path)}
        rebased_record = json.loads(json.dumps(record))
        rebased_record["source"].update(main_sha=rebase_merge, first_parent_sha=rebase_first_parent, head_sha=original_head)
        rebased_record["planning_intake"].update(
            first_parent_tree_sha=before_tree,
            merge_tree_sha=after_tree,
            delta_sha256=hashlib.sha256(json.dumps(rebase_delta, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest(),
        )
        subprocess.run(["git", "-C", str(rebase_repository), "branch", "-D", "topic"], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(rebase_repository), "reflog", "expire", "--expire=now", "--all"], check=True)
        subprocess.run(["git", "-C", str(rebase_repository), "gc", "--prune=now"], check=True, stdout=subprocess.PIPE)
        assert subprocess.run(["git", "-C", str(rebase_repository), "cat-file", "-e", original_head], check=False).returncode != 0
        assert checker._record_failures(rebased_record, "rebase record", rebase_repository) == []


def test_planning_tree_entries_canonicalize_recursive_directory_objects() -> None:
    """Recursive API directory objects never enter the canonical leaf map."""
    updater = load_module("planning_tree_entries", "scripts/update_post_merge_memory.py")
    leaves = [f"root/dir/file-{index}.md" for index in range(13)]
    directories = ["root", "root/dir", "root/other", "alpha", "beta", "gamma"]

    class TreeClient:
        def __init__(self, entries: list[dict]) -> None:
            self.entries = entries

        def get_json(self, _path: str):
            return {"truncated": False, "tree": self.entries}

    entries = [
        *(
            {"path": path, "type": "tree", "mode": "040000", "sha": hashlib.sha1(path.encode()).hexdigest()}
            for path in directories
        ),
        *(
            {"path": path, "type": "blob", "mode": "100644", "sha": hashlib.sha1(path.encode()).hexdigest()}
            for path in leaves
        ),
    ]
    canonical = updater._tree_entries(
        TreeClient(entries), "Flow-Research/workstream", "a" * 40, "head"
    )
    assert len(entries) == 19
    assert sorted(canonical) == sorted(leaves)

    supported = [
        {"path": "regular", "type": "blob", "mode": "100644", "sha": "1" * 40},
        {"path": "executable", "type": "blob", "mode": "100755", "sha": "2" * 40},
        {"path": "symlink", "type": "blob", "mode": "120000", "sha": "3" * 40},
        {"path": "gitlink", "type": "commit", "mode": "160000", "sha": "4" * 40},
    ]
    assert set(updater._tree_entries(
        TreeClient(supported), "Flow-Research/workstream", "a" * 40, "supported"
    )) == {"regular", "executable", "symlink", "gitlink"}

    hostile = (
        ({"path": "bad", "type": "tree", "mode": "100644", "sha": "5" * 40}, "unsupported entry mode"),
        ({"path": "bad", "type": "blob", "mode": "040000", "sha": "5" * 40}, "unsupported entry mode"),
        ({"path": "bad", "type": "commit", "mode": "100644", "sha": "5" * 40}, "unsupported entry mode"),
        ({"path": "../bad", "type": "blob", "mode": "100644", "sha": "5" * 40}, "malformed"),
    )
    for entry, message in hostile:
        assert_loop_error(
            updater,
            lambda entry=entry: updater._tree_entries(
                TreeClient([entry]), "Flow-Research/workstream", "a" * 40, "hostile"
            ),
            message,
        )
    separating_sibling = [
        {"path": "a", "type": "blob", "mode": "100644", "sha": "1" * 40},
        {"path": "a-b", "type": "blob", "mode": "100644", "sha": "2" * 40},
        {"path": "a/b", "type": "blob", "mode": "100644", "sha": "3" * 40},
    ]
    assert_loop_error(
        updater,
        lambda: updater._tree_entries(
            TreeClient(separating_sibling), "Flow-Research/workstream", "a" * 40, "hostile"
        ),
        "conflicting leaf paths",
    )
    duplicate = [supported[0], dict(supported[0])]
    assert_loop_error(
        updater,
        lambda: updater._tree_entries(
            TreeClient(duplicate), "Flow-Research/workstream", "a" * 40, "hostile"
        ),
        "malformed",
    )
    malformed_sha = [{**supported[0], "sha": "not-a-sha"}]
    assert_loop_error(
        updater,
        lambda: updater._tree_entries(
            TreeClient(malformed_sha), "Flow-Research/workstream", "a" * 40, "hostile"
        ),
        "malformed",
    )
    before_file = {"node": ("100644", "blob", "1" * 40)}
    after_directory = {
        "node/one": ("100644", "blob", "2" * 40),
        "node/two": ("100644", "blob", "3" * 40),
    }
    assert updater._tree_delta(before_file, after_directory) == {
        "node": None,
        **after_directory,
    }
    assert updater._tree_delta(after_directory, before_file) == {
        "node": before_file["node"],
        "node/one": None,
        "node/two": None,
    }
    leaf_then_tree = [
        {"path": "leaf", "type": "blob", "mode": "100644", "sha": "1" * 40},
        {"path": "leaf/child", "type": "tree", "mode": "040000", "sha": "2" * 40},
    ]
    assert_loop_error(
        updater,
        lambda: updater._tree_entries(
            TreeClient(leaf_then_tree), "Flow-Research/workstream", "a" * 40, "hostile"
        ),
        "conflicting leaf paths",
    )


def test_ws_eng_007_recovery_policy_is_exactly_pinned() -> None:
    """The temporary production recovery authority is identity-exact."""
    policy = json.loads(Path(".agent-loop/policies/loop-memory-recovery.json").read_text())
    assert policy == {
        "activation": {
            "chunk_id": "WS-ENG-007-00R5",
            "initiative_id": "WS-ENG-007",
        },
        "signed_basis": "a3eecadcf847ac70fc28c58dad642f2d761015e0",
        "recovered_merges": [
            {
                "chunk_id": "WS-ENG-007-00R4",
                "initiative_id": "WS-ENG-007",
                "merge_sha": "9bf16d478f669d48172810c83cdf6a7d2b8992ed",
                "pr_number": 191,
            },
        ],
        "schema_version": 5,
    }


def test_planning_checks_canonicalize_trusted_reruns_and_fail_closed() -> None:
    """Protected checks select the latest invocation after validating all runs."""
    updater = load_module("planning_check_reruns", "scripts/update_post_merge_memory.py")
    head_sha = "a" * 40

    def run(
        check_id: int,
        name: str,
        started: str,
        completed: str,
        conclusion: str = "success",
    ) -> dict:
        return {
            "id": check_id,
            "name": name,
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": conclusion,
            "started_at": started,
            "completed_at": completed,
            "app": {"id": updater.GITHUB_ACTIONS_APP_ID, "slug": updater.GITHUB_ACTIONS_APP_SLUG},
        }

    class CheckClient:
        def __init__(self, runs: list[dict]) -> None:
            self.runs = runs

        def get_json(self, _path: str):
            return {"total_count": len(self.runs), "check_runs": self.runs}

    test_run = run(20, "test", "2026-07-23T05:00:00Z", "2026-07-23T05:01:00Z")
    older = run(10, "agent-gates", "2026-07-23T05:00:00Z", "2026-07-23T05:10:00Z")
    newer = run(11, "agent-gates", "2026-07-23T05:02:00Z", "2026-07-23T05:03:00Z")
    for ordered in ([older, newer, test_run], [test_run, newer, older]):
        updater._validate_protected_actions_checks(
            CheckClient(ordered), "Flow-Research/workstream", head_sha
        )

    old_failure = {**older, "conclusion": "failure"}
    updater._validate_protected_actions_checks(
        CheckClient([newer, old_failure, test_run]), "Flow-Research/workstream", head_sha
    )
    new_failure = {**newer, "conclusion": "failure"}
    assert_loop_error(
        updater,
        lambda: updater._validate_protected_actions_checks(
            CheckClient([older, new_failure, test_run]), "Flow-Research/workstream", head_sha
        ),
        "invalid provenance",
    )
    test_failure = {**test_run, "conclusion": "timed_out"}
    assert_loop_error(
        updater,
        lambda: updater._validate_protected_actions_checks(
            CheckClient([older, newer, test_failure]), "Flow-Research/workstream", head_sha
        ),
        "invalid provenance",
    )
    poisoned = (
        {**older, "app": {"id": 1, "slug": "foreign"}},
        {**older, "head_sha": "b" * 40},
        {**older, "status": "queued", "completed_at": None},
        {**older, "id": True},
        {**older, "started_at": "2026-07-23 05:00:00"},
        {**older, "conclusion": "forged"},
    )
    for bad in poisoned:
        for ordered in ([bad, newer, test_run], [test_run, newer, bad]):
            assert_loop_error(
                updater,
                lambda ordered=ordered: updater._validate_protected_actions_checks(
                    CheckClient(list(ordered)), "Flow-Research/workstream", head_sha
                ),
                "invalid",
            )
    assert_loop_error(
        updater,
        lambda: updater._validate_protected_actions_checks(
            CheckClient([older, dict(older), newer, test_run]),
            "Flow-Research/workstream", head_sha,
        ),
        "invalid provenance",
    )
    assert_loop_error(
        updater,
        lambda: updater._validate_protected_actions_checks(
            CheckClient([older, newer, {**test_run, "id": newer["id"]}]),
            "Flow-Research/workstream", head_sha,
        ),
        "invalid provenance",
    )


def test_planning_intake_collection_binds_paths_trees_and_check_sources() -> None:
    """Planning intake collection binds the reviewed tree and trusted checks."""
    updater = load_module("planning_intake_collection", "scripts/update_post_merge_memory.py")
    class MalformedTreeClient:
        def get_json(self, _path: str):
            return []

    assert_loop_error(
        updater,
        lambda: updater._tree_entries(
            MalformedTreeClient(), "Flow-Research/workstream", "a" * 40, "bad"
        ),
        "tree is incomplete",
    )
    metadata = updater.parse_loop_metadata(
        '{"schema_version":2,"initiative_id":"WS-NEW-001",'
        '"chunk_id":"WS-NEW-001-PLAN","chunk_title":"New Initiative Plan",'
        '"next_chunk_id":"WS-NEW-001-01","next_chunk_title":"First Implementation",'
        '"next_requires_explicit_start":true}'
    )
    root = ".agent-loop/initiatives/WS-NEW-001-example"
    paths = [
        ".agent-loop/merge-intents/WS-NEW-001-PLAN.json",
        *(f"{root}/{name}" for name in sorted(updater.PLANNING_ROOT_FILES)),
        f"{root}/chunks/WS-NEW-001-01-first.md",
        f"{root}/reviews/WS-NEW-001-PLAN-internal-review-evidence.md",
        f"{root}/reviews/WS-NEW-001-PLAN-pr-trust-bundle.md",
    ]
    head_sha = "e" * 40
    base_sha = "6" * 40
    first_parent_sha = "7" * 40
    base_tree = "8" * 40
    head_tree = "f" * 40
    first_parent_tree = "3" * 40
    merge_tree = "4" * 40

    class IntakeClient:
        def __init__(self) -> None:
            self.app_id = updater.GITHUB_ACTIONS_APP_ID
            self.app_slug = updater.GITHUB_ACTIONS_APP_SLUG
            self.mode = "100644"
            self.kind = "blob"
            self.file_status = "added"
            self.extra_path: str | None = None
            self.omit_pr_path = False
            self.duplicate_pr_path = False
            self.merge_only_path: str | None = None
            self.duplicate_run = False
            self.check_status = "completed"
            self.check_conclusion = "success"
            self.truncated_tree: str | None = None
            self.hostile_entry: dict | None = None

        def get_paginated(self, path: str) -> list[dict]:
            if "/pulls/201/files" in path:
                items = [*paths, *([self.extra_path] if self.extra_path else [])]
                if self.omit_pr_path:
                    items.pop()
                if self.duplicate_pr_path:
                    items.append(items[0])
                return [{"filename": item, "status": self.file_status} for item in items]
            if path.endswith("/statuses"):
                return [{
                    "context": "CodeRabbit",
                    "sha": head_sha,
                    "state": "success",
                    "creator": None,
                }]
            raise AssertionError(path)

        def get_json(self, path: str):
            commit_trees = {
                head_sha: head_tree,
                base_sha: base_tree,
                first_parent_sha: first_parent_tree,
            }
            for commit_sha, tree_sha in commit_trees.items():
                if path.endswith(f"/commits/{commit_sha}"):
                    return {"commit": {"tree": {"sha": tree_sha}}}
            tree_entries = {
                base_tree: [{"path": "base.txt", "type": "blob", "mode": "100644", "sha": "a" * 40}],
                head_tree: [
                    {"path": ".agent-loop", "type": "tree", "mode": "040000", "sha": "1" * 40},
                    {"path": ".agent-loop/initiatives", "type": "tree", "mode": "040000", "sha": "2" * 40},
                    {"path": "base.txt", "type": "blob", "mode": "100644", "sha": "a" * 40},
                    *({"path": item, "type": self.kind, "mode": self.mode, "sha": hashlib.sha1(item.encode()).hexdigest()} for item in paths),
                    *([self.hostile_entry] if self.hostile_entry else []),
                ],
                first_parent_tree: [
                    {"path": "base.txt", "type": "blob", "mode": "100644", "sha": "a" * 40},
                    {"path": "main.txt", "type": "blob", "mode": "100644", "sha": "b" * 40},
                ],
                merge_tree: [
                    {"path": ".agent-loop", "type": "tree", "mode": "040000", "sha": "1" * 40},
                    {"path": ".agent-loop/initiatives", "type": "tree", "mode": "040000", "sha": "2" * 40},
                    {"path": "base.txt", "type": "blob", "mode": "100644", "sha": "a" * 40},
                    {"path": "main.txt", "type": "blob", "mode": "100644", "sha": "b" * 40},
                    *({"path": item, "type": self.kind, "mode": self.mode, "sha": hashlib.sha1(item.encode()).hexdigest()} for item in paths),
                    *([{"path": self.merge_only_path, "type": "blob", "mode": "100644", "sha": "6" * 40}] if self.merge_only_path else []),
                    *([self.hostile_entry] if self.hostile_entry else []),
                ],
            }
            for tree_sha, entries in tree_entries.items():
                if path.endswith(f"/git/trees/{tree_sha}?recursive=1"):
                    return {"truncated": tree_sha == self.truncated_tree, "tree": entries}
            if path.endswith("/unused"):
                return {
                    "truncated": False,
                    "tree": [],
                }
            if "/check-runs?per_page=100" in path:
                runs = [
                    {
                        "id": index,
                        "name": name,
                        "head_sha": head_sha,
                        "status": self.check_status,
                        "conclusion": self.check_conclusion,
                        "started_at": "2026-07-22T07:59:00Z",
                        "completed_at": "2026-07-22T08:00:00Z",
                        "app": {"id": self.app_id, "slug": self.app_slug},
                    }
                    for index, name in enumerate(("agent-gates", "test"), start=1)
                ]
                if self.duplicate_run:
                    runs.append({
                        **runs[0], "id": 3,
                        "started_at": "2026-07-22T08:01:00Z",
                        "completed_at": "2026-07-22T08:02:00Z",
                    })
                return {"total_count": len(runs), "check_runs": runs}
            if "STATUS.md?ref=" in path:
                value = "- Active planning chunk: none\n- Active implementation chunk: none\n"
            elif "/chunks/WS-NEW-001-01-first.md?ref=" in path:
                value = (
                    "# Chunk Contract: WS-NEW-001-01 — First Implementation\n\n"
                    "## Start phase\n\n`implementation`\n"
                )
            else:
                raise AssertionError(path)
            return {"encoding": "base64", "sha": "9" * 40, "content": updater_base64(value)}

    client = IntakeClient()
    merge_commit = {"commit": {"tree": {"sha": merge_tree}}}
    evidence = updater._collect_planning_intake(
        client,
        "Flow-Research/workstream",
        metadata=metadata,
        pr_number=201,
        head_sha=head_sha,
        base_sha=base_sha,
        first_parent_sha=first_parent_sha,
        merge_commit=merge_commit,
    )
    assert evidence == {
        "schema_version": updater.PLANNING_INTAKE_VERSION,
        "initiative_directory": "WS-NEW-001-example",
        "base_tree_sha": base_tree,
        "head_tree_sha": head_tree,
        "first_parent_tree_sha": first_parent_tree,
        "merge_tree_sha": merge_tree,
        "delta_sha256": evidence["delta_sha256"],
        "changed_paths": sorted(paths),
    }
    client.app_id = updater.GITHUB_ACTIONS_APP_ID
    client.mode = "100755"
    assert_loop_error(
        updater,
        lambda: updater._collect_planning_intake(
            client,
            "Flow-Research/workstream",
            metadata=metadata,
            pr_number=201,
            head_sha=head_sha,
            base_sha=base_sha,
            first_parent_sha=first_parent_sha,
            merge_commit=merge_commit,
        ),
        "file mode",
    )
    client.mode = "100644"
    cases = (
        (lambda: setattr(client, "file_status", "renamed"), "additive files only"),
        (lambda: setattr(client, "file_status", "removed"), "additive files only"),
        (lambda: setattr(client, "duplicate_pr_path", True), "path set is invalid"),
        (lambda: setattr(client, "omit_pr_path", True), "review or contract set is invalid"),
        (lambda: setattr(client, "merge_only_path", "merge-only.md"), "authoritative tree delta does not match"),
        (
            lambda: (setattr(client, "kind", "blob"), setattr(client, "mode", "120000")),
            "file mode",
        ),
        (
            lambda: (setattr(client, "kind", "commit"), setattr(client, "mode", "160000")),
            "file mode",
        ),
        (lambda: setattr(client, "extra_path", "backend/app/unsafe.py"), "foreign path"),
        (
            lambda: setattr(
                client,
                "extra_path",
                f"{root}/chunks/.hidden.md",
            ),
            "path grammar",
        ),
        (
            lambda: setattr(
                client,
                "extra_path",
                f"{root}/chunks/AGENTS.md",
            ),
            "path grammar",
        ),
        (
            lambda: setattr(
                client,
                "extra_path",
                ".agent-loop/initiatives/WS-NEW-001-.hidden/PLAN.md",
            ),
            "foreign path",
        ),
        (lambda: setattr(client, "truncated_tree", merge_tree), "tree is incomplete"),
        (
            lambda: setattr(client, "hostile_entry", {
                "path": "foreign", "type": "tag", "mode": "100644", "sha": "5" * 40,
            }),
            "unsupported entry mode",
        ),
        (
            lambda: setattr(client, "hostile_entry", {
                "path": "base.txt/child", "type": "blob", "mode": "100644", "sha": "5" * 40,
            }),
            "conflicting leaf paths",
        ),
    )
    for mutate, expected in cases:
        client = IntakeClient()
        mutate()
        assert_loop_error(
            updater,
            lambda client=client: updater._collect_planning_intake(
                client,
                "Flow-Research/workstream",
                metadata=metadata,
                pr_number=201,
                head_sha=head_sha,
                base_sha=base_sha,
                first_parent_sha=first_parent_sha,
                merge_commit=merge_commit,
            ),
            expected,
        )


def test_eng006_exact_recovery_certificate_is_consumed_and_inert_on_replay() -> None:
    """ENG-006 root recovery is exact, ephemeral, consumed, and replay inert."""
    updater = load_module("eng006_recovery", "scripts/update_post_merge_memory.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        repository_root = Path(tmpdir) / "repository"
        state_root = Path(tmpdir) / "state"
        subprocess.run(
            ["git", "init", "--initial-branch", "main", str(repository_root)],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(["git", "-C", str(repository_root), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(repository_root), "config", "user.name", "Test"], check=True)
        policy = repository_root / updater.RECOVERY_POLICY_PATH
        policy.parent.mkdir(parents=True)
        policy.write_text(
            '{"activation":{"chunk_id":"WS-ENG-006-00",'
            '"initiative_id":"WS-ENG-006"},"mode":"exact_single_target",'
            '"schema_version":2}\n',
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(repository_root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository_root), "commit", "-m", "base"], check=True, stdout=subprocess.PIPE)
        base_sha = subprocess.check_output(["git", "-C", str(repository_root), "rev-parse", "HEAD"], text=True).strip()
        (repository_root / "target.txt").write_text("target\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository_root), "add", "target.txt"], check=True)
        subprocess.run(["git", "-C", str(repository_root), "commit", "-m", "target"], check=True, stdout=subprocess.PIPE)
        target_sha = subprocess.check_output(["git", "-C", str(repository_root), "rev-parse", "HEAD"], text=True).strip()
        base = loop_record(updater, sha=base_sha)
        base["legacy_exemptions"] = []
        updater.apply_merge_record(state_root, base)
        metadata = updater.parse_loop_metadata(
            '{"schema_version":2,"initiative_id":"WS-ENG-006",'
            '"chunk_id":"WS-ENG-006-00","chunk_title":"First-New-Initiative Planning Intake",'
            '"next_chunk_id":"WS-ENG-006-01",'
            '"next_chunk_title":"Canonical Human And Agent Contribution Entry",'
            '"next_requires_explicit_start":true}'
        )
        target = loop_record(
            updater,
            sha=target_sha,
            first_parent_sha=base_sha,
            pr_number=206,
            merged_at="2026-07-22T10:00:00Z",
        )
        target["completed_chunk"] = updater.asdict(metadata)
        target["source"].update(
            intent_path=".agent-loop/merge-intents/WS-ENG-006-00.json",
            pr_url="https://github.com/Flow-Research/workstream/pull/206",
        )
        target["gate"].update(
            next_chunk_id=metadata.next_chunk_id,
            next_chunk_title=metadata.next_chunk_title,
        )
        original_collect = updater.collect_merge_record
        original_checks = updater._validate_protected_actions_checks
        updater.collect_merge_record = lambda *_args, **_kwargs: json.loads(json.dumps(target))
        checked_heads: list[str] = []
        updater._validate_protected_actions_checks = (
            lambda _client, _repository, checked_head: checked_heads.append(checked_head)
        )
        try:
            exemptions = updater.prepare_recovery_exemptions(
                object(),
                "Flow-Research/workstream",
                repository_root=repository_root,
                state_root=state_root,
                target_sha=target_sha,
                planned_shas=[target_sha],
            )
            assert exemptions == [{
                "initiative_id": "WS-ENG-006",
                "chunk_id": "WS-ENG-006-00",
                "pr_number": 206,
            }]
            assert checked_heads == [target["source"]["head_sha"]]
            assert updater.apply_merge_record(state_root, target, recovery_exemptions=exemptions)
            updater.assert_recovery_consumed(state_root, target_sha, exemptions)
            assert updater.prepare_recovery_exemptions(
                object(),
                "Flow-Research/workstream",
                repository_root=repository_root,
                state_root=state_root,
                target_sha=target_sha,
                planned_shas=[],
            ) == []
            ledger = (state_root / updater.LEDGER_PATH).read_text(encoding="utf-8")
            assert '"chunk_id":"WS-ENG-006-00","initiative_id":"WS-ENG-006","pr_number":206' not in ledger
            replay_root = Path(tmpdir) / "replay-state"
            updater.apply_merge_record(replay_root, json.loads(json.dumps(base)))
            replay_exemptions = updater.prepare_recovery_exemptions(
                object(),
                "Flow-Research/workstream",
                repository_root=repository_root,
                state_root=replay_root,
                target_sha=target_sha,
                planned_shas=[target_sha],
            )
            assert updater.apply_merge_record(
                replay_root,
                json.loads(json.dumps(target)),
                recovery_exemptions=replay_exemptions,
            )
            updater.assert_recovery_consumed(replay_root, target_sha, replay_exemptions)
            assert (replay_root / updater.STATE_PATH).read_text(encoding="utf-8") == (
                state_root / updater.STATE_PATH
            ).read_text(encoding="utf-8")
            assert (replay_root / updater.LEDGER_PATH).read_text(encoding="utf-8") == (
                state_root / updater.LEDGER_PATH
            ).read_text(encoding="utf-8")
            assert_loop_error(
                updater,
                lambda: updater.prepare_recovery_exemptions(
                    object(),
                    "Flow-Research/workstream",
                    repository_root=repository_root,
                    state_root=replay_root,
                    target_sha=target_sha,
                    planned_shas=[target_sha],
                ),
                "signed first parent",
            )
        finally:
            updater.collect_merge_record = original_collect
            updater._validate_protected_actions_checks = original_checks


def test_eng007_two_merge_recovery_binds_pr187_and_consumes_authority() -> None:
    """The exact PR187 checkpoint precedes and authorizes only its repair."""
    updater = load_module("eng007_two_merge_recovery", "scripts/update_post_merge_memory.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        repository_root = Path(tmpdir) / "repository"
        state_root = Path(tmpdir) / "state"
        subprocess.run(["git", "init", "--initial-branch", "main", str(repository_root)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(repository_root), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(repository_root), "config", "user.name", "Test"], check=True)
        (repository_root / "base.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository_root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository_root), "commit", "-m", "base"], check=True, stdout=subprocess.PIPE)
        base_sha = subprocess.check_output(["git", "-C", str(repository_root), "rev-parse", "HEAD"], text=True).strip()
        (repository_root / "plan.txt").write_text("eng plan\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository_root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository_root), "commit", "-m", "eng plan"], check=True, stdout=subprocess.PIPE)
        recovered_sha = subprocess.check_output(["git", "-C", str(repository_root), "rev-parse", "HEAD"], text=True).strip()
        policy = repository_root / updater.RECOVERY_POLICY_PATH
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps({
            "activation": {"chunk_id": "WS-ENG-007-00R1", "initiative_id": "WS-ENG-007"},
            "recovered_merge": {
                "chunk_id": "WS-ENG-007-PLAN",
                "initiative_id": "WS-ENG-007",
                "merge_sha": recovered_sha,
                "pr_number": 187,
            },
            "schema_version": 1,
        }) + "\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository_root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository_root), "commit", "-m", "eng repair"], check=True, stdout=subprocess.PIPE)
        target_sha = subprocess.check_output(["git", "-C", str(repository_root), "rev-parse", "HEAD"], text=True).strip()
        base = loop_record(updater, sha=base_sha)
        base["legacy_exemptions"] = []
        updater.apply_merge_record(state_root, base)
        recovered = loop_record(updater, sha=recovered_sha, first_parent_sha=base_sha, pr_number=187)
        recovered["completed_chunk"].update(
            initiative_id="WS-ENG-007", chunk_id="WS-ENG-007-PLAN",
            next_chunk_id="WS-ENG-007-01", next_chunk_title="Reviewed Patch and Base-Delta Reconciliation",
        )
        recovered["gate"].update(
            next_chunk_id="WS-ENG-007-01",
            next_chunk_title="Reviewed Patch and Base-Delta Reconciliation",
        )
        recovered["source"].update(
            intent_path=".agent-loop/merge-intents/WS-ENG-007-PLAN.json",
            pr_url="https://github.com/Flow-Research/workstream/pull/187",
        )
        target = loop_record(updater, sha=target_sha, first_parent_sha=recovered_sha, pr_number=188)
        target["completed_chunk"].update(
            initiative_id="WS-ENG-007", chunk_id="WS-ENG-007-00R1",
            next_chunk_id="WS-ENG-007-01", next_chunk_title="Reviewed Patch and Base-Delta Reconciliation",
        )
        target["gate"].update(
            next_chunk_id="WS-ENG-007-01",
            next_chunk_title="Reviewed Patch and Base-Delta Reconciliation",
        )
        target["source"].update(
            intent_path=".agent-loop/merge-intents/WS-ENG-007-00R1.json",
            pr_url="https://github.com/Flow-Research/workstream/pull/188",
        )
        records = {recovered_sha: recovered, target_sha: target}
        original_collect = updater.collect_merge_record
        original_checks = updater._validate_protected_actions_checks
        updater.collect_merge_record = lambda _client, _repository, sha: json.loads(json.dumps(records[sha]))
        checked_heads: list[str] = []
        updater._validate_protected_actions_checks = (
            lambda _client, _repository, head: checked_heads.append(head)
        )
        try:
            records[recovered_sha]["checks"]["all_required_passed"] = False
            assert_loop_error(
                updater,
                lambda: updater.prepare_recovery_exemptions(
                    object(), "Flow-Research/workstream",
                    repository_root=repository_root, state_root=state_root,
                    target_sha=target_sha, planned_shas=[recovered_sha, target_sha],
                ),
                "required checks",
            )
            records[recovered_sha]["checks"]["all_required_passed"] = True
            records[target_sha]["checks"]["all_required_passed"] = False
            assert_loop_error(
                updater,
                lambda: updater.prepare_recovery_exemptions(
                    object(), "Flow-Research/workstream",
                    repository_root=repository_root, state_root=state_root,
                    target_sha=target_sha, planned_shas=[recovered_sha, target_sha],
                ),
                "required checks",
            )
            records[target_sha]["checks"]["all_required_passed"] = True
            checked_heads.clear()
            exemptions = updater.prepare_recovery_exemptions(
                object(), "Flow-Research/workstream",
                repository_root=repository_root, state_root=state_root,
                target_sha=target_sha, planned_shas=[recovered_sha, target_sha],
            )
            assert [(item["initiative_id"], item["chunk_id"]) for item in exemptions] == [
                ("WS-ENG-007", "WS-ENG-007-PLAN"),
                ("WS-ENG-007", "WS-ENG-007-00R1"),
            ]
            assert checked_heads == [target["source"]["head_sha"]]
            serialized = json.loads(json.dumps({"schema_version": 1, "exemptions": exemptions}))
            reloaded = updater._validate_recovery_exemptions(serialized)
            assert reloaded == exemptions
            assert updater.apply_merge_record(state_root, recovered, recovery_exemptions=reloaded)
            reloaded = updater._validate_recovery_exemptions(serialized)
            assert updater.apply_merge_record(state_root, target, recovery_exemptions=reloaded)
            updater.assert_recovery_consumed(
                state_root, target_sha,
                updater._validate_recovery_exemptions(serialized),
            )
            duplicate = {"schema_version": 1, "exemptions": [exemptions[0], exemptions[0]]}
            assert_loop_error(
                updater,
                lambda: updater._validate_recovery_exemptions(duplicate),
                "not unique and bounded",
            )
            foreign_key = {**serialized, "unexpected": True}
            assert_loop_error(
                updater,
                lambda: updater._validate_recovery_exemptions(foreign_key),
                "invalid schema",
            )
        finally:
            updater.collect_merge_record = original_collect
            updater._validate_protected_actions_checks = original_checks


def test_post_merge_metadata_is_strict_and_bounded() -> None:
    """PR metadata rejects ambiguity, unknown keys, and inconsistent chunk facts."""
    updater = load_module("post_merge_metadata", "scripts/update_post_merge_memory.py")
    metadata = updater.parse_loop_metadata(valid_loop_intent())
    assert metadata.initiative_id == "WS-AUTH-001"
    assert metadata.chunk_id == "WS-AUTH-001-06"
    assert metadata.next_requires_explicit_start is True

    invalid_bodies = [
        "",
        valid_loop_intent() + valid_loop_intent(),
        valid_loop_intent().replace('"schema_version":2', '"schema_version":1'),
        valid_loop_intent().replace('"schema_version":2', '"schema_version":2.0'),
        valid_loop_intent().replace('"schema_version":2', '"schema_version":"2"'),
        valid_loop_intent().replace('"schema_version":2', '"schema_version":true'),
        valid_loop_intent().replace(
            '"chunk_id":"WS-AUTH-001-06"', '"chunk_id":"WS-POL-002-04"'
        ),
        valid_loop_intent().replace(
            '"next_chunk_title":"Authorization Kernel"', '"next_chunk_title":null'
        ),
        valid_loop_intent().replace(
            '"schema_version":2', '"schema_version":2,"unexpected":true'
        ),
    ]
    for body in invalid_bodies:
        try:
            updater.parse_loop_metadata(body)
        except updater.LoopMemoryError:
            continue
        raise AssertionError(f"invalid merge intent passed: {body}")

    assert_loop_error(
        updater,
        lambda: updater.parse_loop_metadata(
            valid_loop_intent().replace("WS-AUTH-001-07", "WS-ART-001-02A1")
        ),
        "next_chunk_id must belong",
    )


def test_next_chunk_contract_binding_is_exact_locally_and_remotely() -> None:
    """A non-null successor resolves to one same-title reviewed contract."""
    updater = load_module(
        "post_merge_successor_contract", "scripts/update_post_merge_memory.py"
    )
    metadata = updater.parse_loop_metadata(valid_loop_intent())
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        contract = (
            root / ".agent-loop/initiatives/WS-AUTH-001-example/chunks/"
            "WS-AUTH-001-07-authorization-kernel.md"
        )
        contract.parent.mkdir(parents=True)
        contract.write_text(
            "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n",
            encoding="utf-8",
        )
        updater._validate_local_successor_contract(root, metadata)

        contract.write_text(
            "# Chunk Contract: WS-AUTH-001-07 - Wrong Title\n", encoding="utf-8"
        )
        assert_loop_error(
            updater,
            lambda: updater._validate_local_successor_contract(root, metadata),
            "heading does not match",
        )
        contract.unlink()
        assert_loop_error(
            updater,
            lambda: updater._validate_local_successor_contract(root, metadata),
            "exactly one chunk contract",
        )
        foreign_contract = (
            root / ".agent-loop/initiatives/WS-ART-001-example/chunks/"
            "WS-AUTH-001-07-authorization-kernel.md"
        )
        foreign_contract.parent.mkdir(parents=True)
        foreign_contract.write_text(
            "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n",
            encoding="utf-8",
        )
        assert_loop_error(
            updater,
            lambda: updater._validate_local_successor_contract(root, metadata),
            "another initiative directory",
        )
        foreign_contract.unlink()
        spoof_contract = (
            root / ".agent-loop/initiatives/WS-AUTH-001-spoof/chunks/"
            "WS-AUTH-001-07-authorization-kernel.md"
        )
        spoof_contract.parent.mkdir(parents=True)
        spoof_contract.write_text(
            "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n",
            encoding="utf-8",
        )
        assert_loop_error(
            updater,
            lambda: updater._validate_local_successor_contract(root, metadata),
            "exactly one initiative directory",
        )
        spoof_contract.unlink()
        spoof_contract.parent.rmdir()
        spoof_contract.parent.parent.rmdir()
        contract.write_text(
            "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n",
            encoding="utf-8",
        )
        foreign_contract.parent.mkdir(parents=True, exist_ok=True)
        foreign_contract.write_text(
            "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n",
            encoding="utf-8",
        )
        assert_loop_error(
            updater,
            lambda: updater._validate_local_successor_contract(root, metadata),
            "another initiative directory",
        )
        foreign_contract.unlink()
        duplicate = contract.parent / "WS-AUTH-001-07-copy.md"
        duplicate.write_text(contract.read_text(encoding="utf-8"), encoding="utf-8")
        assert_loop_error(
            updater,
            lambda: updater._validate_local_successor_contract(root, metadata),
            "exactly one chunk contract",
        )

    class RemoteClient:
        def __init__(self, tree, contract_text: str, returned_sha: str = "e" * 40):
            self.tree = tree
            self.contract_text = contract_text
            self.returned_sha = returned_sha

        def get_json(self, path: str):
            if "/git/trees/" in path:
                return self.tree
            return {
                "encoding": "base64",
                "sha": self.returned_sha,
                "content": updater_base64(self.contract_text),
            }

    tree_item = {
        "type": "blob",
        "path": (
            ".agent-loop/initiatives/WS-AUTH-001-example/chunks/"
            "WS-AUTH-001-07-authorization-kernel.md"
        ),
        "sha": "e" * 40,
    }
    foreign_tree_item = dict(tree_item)
    foreign_tree_item["path"] = foreign_tree_item["path"].replace(
        "WS-AUTH-001-example", "WS-ART-001-example"
    )
    spoof_tree_item = dict(tree_item)
    spoof_tree_item["path"] = spoof_tree_item["path"].replace(
        "WS-AUTH-001-example", "WS-AUTH-001-spoof"
    )
    non_contract_tree_item = dict(tree_item)
    non_contract_tree_item["path"] = (
        non_contract_tree_item["path"].removesuffix(".md") + ".txt"
    )
    valid_tree = {
        "truncated": False,
        "tree": [non_contract_tree_item, tree_item],
    }
    updater._validate_remote_successor_contract(
        RemoteClient(
            valid_tree,
            "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n",
        ),
        "Flow-Research/workstream",
        "b" * 40,
        metadata,
    )
    remote_cases = (
        (
            {"truncated": True, "tree": [tree_item]},
            "Authorization Kernel",
            "incomplete",
        ),
        ({"truncated": False, "tree": []}, "Authorization Kernel", "exactly one"),
        (
            {"truncated": False, "tree": [foreign_tree_item]},
            "Authorization Kernel",
            "exactly one reviewed-head initiative directory",
        ),
        (
            {"truncated": False, "tree": [tree_item, foreign_tree_item]},
            "Authorization Kernel",
            "another reviewed-head initiative directory",
        ),
        (
            {"truncated": False, "tree": [tree_item, spoof_tree_item]},
            "Authorization Kernel",
            "exactly one reviewed-head initiative directory",
        ),
        (
            {"truncated": False, "tree": [tree_item, dict(tree_item)]},
            "Authorization Kernel",
            "exactly one",
        ),
        (valid_tree, "Wrong Title", "heading does not match"),
    )
    for tree, title, expected in remote_cases:
        assert_loop_error(
            updater,
            lambda tree=tree, title=title: updater._validate_remote_successor_contract(
                RemoteClient(
                    tree,
                    f"# Chunk Contract: WS-AUTH-001-07 - {title}\n",
                ),
                "Flow-Research/workstream",
                "b" * 40,
                metadata,
            ),
            expected,
        )


def test_post_merge_state_is_idempotent_and_monotonic() -> None:
    """Generated state accepts one merge, replays exactly, and rejects older/conflicting data."""
    updater = load_module("post_merge_state", "scripts/update_post_merge_memory.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        record = loop_record(updater)
        assert updater.apply_merge_record(root, record) is True
        assert updater.apply_merge_record(root, record) is False
        updater.validate_generated_state(root)

        conflict = json.loads(json.dumps(record))
        conflict["source"]["pr_title"] = "Conflicting title"
        try:
            updater.apply_merge_record(root, conflict)
        except updater.LoopMemoryError as exc:
            assert "different state" in str(exc)
        else:
            raise AssertionError("conflicting replay passed")

        successor = loop_record(
            updater,
            sha="c" * 40,
            first_parent_sha="a" * 40,
            merged_at="2026-07-14T20:00:00Z",
            pr_number=121,
        )
        assert updater.apply_merge_record(root, successor) is True
        updater.validate_generated_state(root)

        older = loop_record(
            updater,
            sha="e" * 40,
            first_parent_sha="0" * 40,
            merged_at="2026-07-14T19:59:59Z",
            pr_number=119,
        )
        try:
            updater.apply_merge_record(root, older)
        except updater.LoopMemoryError as exc:
            assert "direct first-parent successor" in str(exc)
        else:
            raise AssertionError("older merge replaced live state")


def test_loop_memory_projects_latest_gate_for_interleaved_initiatives() -> None:
    """Queue and initiative views retain each initiative's latest stopped gate."""
    updater = load_module(
        "post_merge_projections", "scripts/update_post_merge_memory.py"
    )
    checker = load_module(
        "post_merge_projection_checker", "scripts/check_loop_memory_state.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        auth_first = loop_record(updater)
        auth_first["completed_chunk"].update(
            chunk_id="WS-AUTH-001-09E",
            chunk_title="Fixed Service Runtime Admission",
            next_chunk_id="WS-AUTH-001-ART-CUSTODY",
            next_chunk_title="ART Activation Custody Transfer",
        )
        auth_first["source"]["intent_path"] = (
            ".agent-loop/merge-intents/WS-AUTH-001-09E.json"
        )
        auth_first["gate"].update(
            next_chunk_id="WS-AUTH-001-ART-CUSTODY",
            next_chunk_title="ART Activation Custody Transfer",
        )
        art = loop_record(
            updater,
            sha="b" * 40,
            first_parent_sha="a" * 40,
            pr_number=121,
            merged_at="2026-07-14T20:00:00Z",
        )
        art["completed_chunk"].update(
            initiative_id="WS-ART-001",
            chunk_id="WS-ART-001-02C1",
            chunk_title="Admission Foundation",
            next_chunk_id="WS-ART-001-02C2",
            next_chunk_title="Verification Publication And Fencing",
        )
        art["source"]["intent_path"] = ".agent-loop/merge-intents/WS-ART-001-02C1.json"
        art["gate"].update(
            next_chunk_id="WS-ART-001-02C2",
            next_chunk_title="Verification Publication And Fencing",
        )
        auth_second = loop_record(
            updater,
            sha="c" * 40,
            first_parent_sha="b" * 40,
            pr_number=122,
            merged_at="2026-07-14T21:00:00Z",
        )
        auth_second["completed_chunk"].update(
            chunk_id="WS-AUTH-001-ART-CUSTODY",
            chunk_title="ART Activation Custody Transfer",
            next_chunk_id="WS-AUTH-001-REV-CUSTODY",
            next_chunk_title="REV Activation Custody Transfer",
        )
        auth_second["source"]["intent_path"] = (
            ".agent-loop/merge-intents/WS-AUTH-001-ART-CUSTODY.json"
        )
        auth_second["gate"].update(
            next_chunk_id="WS-AUTH-001-REV-CUSTODY",
            next_chunk_title="REV Activation Custody Transfer",
        )
        for record in (auth_first, art, auth_second):
            assert updater.apply_merge_record(root, record) is True
        updater.validate_generated_state(root)
        assert checker.generated_state_failures(root) == []
        queue = (root / updater.WORK_QUEUE_PATH).read_text(encoding="utf-8")
        assert "`WS-AUTH-001-ART-CUSTODY`" in queue
        assert "`WS-AUTH-001-REV-CUSTODY`" in queue
        assert "`WS-ART-001-02C1`" in queue
        assert queue.index("`WS-ART-001`") < queue.index("`WS-AUTH-001`")
        assert (root / updater.INITIATIVE_STATE_ROOT / "WS-AUTH-001.md").is_file()
        assert (root / updater.INITIATIVE_STATE_ROOT / "WS-ART-001.md").is_file()


def test_prepare_output_migrates_authenticated_legacy_tree_without_traversal() -> None:
    """Legacy branch content is omitted from one fresh authenticated output tree."""
    updater = load_module(
        "post_merge_fresh_output", "scripts/update_post_merge_memory.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        source = root / "source"
        output = root / "output"
        source.mkdir()
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", private_key],
            check=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", private_key, "-pubout", "-out", public_key],
            check=True,
        )
        record = loop_record(updater)
        entry = updater._ledger_entry(record, None)
        (source / updater.STATE_PATH).parent.mkdir(parents=True)
        (source / updater.STATE_PATH).write_text(
            updater._canonical_json(record, pretty=True), encoding="utf-8"
        )
        (source / updater.RENDERED_PATH).write_text(
            updater.render_state(record), encoding="utf-8"
        )
        (source / updater.LEDGER_PATH).write_text(
            f"{updater._canonical_json(entry)}\n", encoding="utf-8"
        )
        sign_loop_state_with_domain(
            updater, source, private_key, b"workstream-loop-memory-signature-v2\0"
        )
        legacy = source / "backend/legacy.py"
        legacy.parent.mkdir()
        legacy.write_text("legacy\n", encoding="utf-8")
        sentinel = root / "sentinel"
        sentinel.write_text("preserve\n", encoding="utf-8")
        assert updater.prepare_generated_output(source, output, public_key) is True
        assert not (output / "backend").exists()
        assert sentinel.read_text(encoding="utf-8") == "preserve\n"
        updater.sign_generated_state(output, private_key)
        updater.verify_generated_state_signature(output, public_key, "a" * 40)
        assert {
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file()
        } == {
            *(
                item["path"]
                for item in json.loads(
                    (output / updater.MANIFEST_PATH).read_text(encoding="utf-8")
                )["payloads"]
            ),
            updater.MANIFEST_PATH.as_posix(),
            updater.SIGNATURE_PATH.as_posix(),
        }


def test_prepare_output_rebuilds_authenticated_renderer_drift() -> None:
    """A signed old projection rebuilds without relaxing strict validation."""
    updater = load_module(
        "post_merge_renderer_rebuild", "scripts/update_post_merge_memory.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        source = root / "source"
        output = root / "output"
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", private_key],
            check=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", private_key, "-pubout", "-out", public_key],
            check=True,
        )
        updater.apply_merge_record(source, loop_record(updater))
        projection = (
            source / updater.INITIATIVE_STATE_ROOT / "WS-AUTH-001.md"
        )
        projection.write_text("# Signed projection from the prior renderer\n", encoding="utf-8")
        manifest_path = source / updater.MANIFEST_PATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest["payloads"]:
            if item["path"] == projection.relative_to(source).as_posix():
                item["sha256"] = hashlib.sha256(projection.read_bytes()).hexdigest()
        manifest_path.write_text(
            updater._canonical_json(manifest, pretty=True), encoding="utf-8"
        )
        with tempfile.NamedTemporaryFile() as payload_file:
            payload_file.write(updater._signature_payload(source))
            payload_file.flush()
            signature = subprocess.run(
                [
                    "openssl", "pkeyutl", "-sign", "-rawin", "-inkey",
                    str(private_key), "-in", payload_file.name,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).stdout
        (source / updater.SIGNATURE_PATH).write_text(
            base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii"
        )

        assert_loop_error(
            updater,
            lambda: updater.verify_generated_state_signature(source, public_key),
            "initiative state does not match",
        )
        updater.verify_generated_state_rebuild_source(source, public_key)
        assert updater.prepare_generated_output(source, output, public_key) is True
        assert projection.read_text(encoding="utf-8").startswith("# Signed projection")
        assert "# Signed projection" not in (
            output / updater.INITIATIVE_STATE_ROOT / "WS-AUTH-001.md"
        ).read_text(encoding="utf-8")
        updater.validate_generated_state(output)


def test_generated_tree_publication_is_exact_fast_forward_and_bootstrappable() -> None:
    """Real Git plumbing preserves signed bytes, parentage, and root bootstrap."""
    updater = load_module(
        "post_merge_git_tree_publication", "scripts/update_post_merge_memory.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        output = root / "output"
        private_key = root / "private.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", private_key],
            check=True,
        )
        updater.apply_merge_record(output, loop_record(updater))
        updater.sign_generated_state(output, private_key)
        sentinel = root / "outside-sentinel"
        sentinel.write_text("preserve\n", encoding="utf-8")

        def initialize_repository(path: Path, *, with_parent: bool) -> str | None:
            subprocess.run(
                ["git", "init", "--initial-branch", updater.STATE_BRANCH, str(path)],
                check=True,
                stdout=subprocess.PIPE,
            )
            subprocess.run(
                ["git", "-C", str(path), "config", "user.email", "test@example.test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(path), "config", "user.name", "Test"], check=True
            )
            if not with_parent:
                return None
            legacy = path / "backend/legacy.py"
            legacy.parent.mkdir()
            legacy.write_text("legacy\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(path), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(path), "commit", "-m", "legacy"],
                check=True,
                stdout=subprocess.PIPE,
            )
            return subprocess.run(
                ["git", "-C", str(path), "rev-parse", "HEAD"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()

        def stage_tree(repository: Path, index: Path) -> str:
            env = {**os.environ, "GIT_INDEX_FILE": str(index)}
            subprocess.run(
                ["git", "-C", str(repository), "read-tree", "--empty"],
                check=True,
                env=env,
            )
            subprocess.run(
                [
                    "git",
                    f"--git-dir={repository / '.git'}",
                    f"--work-tree={output}",
                    "add",
                    "-f",
                    "--",
                    ".agent-loop",
                ],
                check=True,
                env=env,
            )
            return subprocess.run(
                ["git", "-C", str(repository), "write-tree"],
                check=True,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()

        repository = root / "state"
        parent = initialize_repository(repository, with_parent=True)
        index = root / "generated.index"
        tree = stage_tree(repository, index)
        updater.validate_generated_git_tree(repository, tree, output)
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        executable = updater.STATE_PATH.as_posix()
        object_sha = subprocess.run(
            ["git", "-C", str(repository), "ls-files", "-s", "--", executable],
            check=True,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.split()[1]
        subprocess.run(
            ["git", "-C", str(repository), "update-index", "--index-info"],
            input=f"100755 {object_sha}\t{executable}\n",
            check=True,
            env=env,
            text=True,
        )
        unsafe_tree = subprocess.run(
            ["git", "-C", str(repository), "write-tree"],
            check=True,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_git_tree(
                repository, unsafe_tree, output
            ),
            "unsafe file mode",
        )
        index.unlink()
        tree = stage_tree(repository, index)
        commit = subprocess.run(
            ["git", "-C", str(repository), "commit-tree", tree, "-p", parent],
            input="generated\n",
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        assert (
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "merge-base",
                    "--is-ancestor",
                    parent,
                    commit,
                ]
            ).returncode
            == 0
        )
        assert subprocess.run(
            ["git", "-C", str(repository), "ls-tree", "-r", "--name-only", commit],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines() == sorted(
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file()
        )
        assert sentinel.read_text(encoding="utf-8") == "preserve\n"

        root_repository = root / "root-state"
        initialize_repository(root_repository, with_parent=False)
        root_tree = stage_tree(root_repository, root / "root.index")
        updater.validate_generated_git_tree(root_repository, root_tree, output)
        root_commit = subprocess.run(
            ["git", "-C", str(root_repository), "commit-tree", root_tree],
            input="generated root\n",
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        assert subprocess.run(
            [
                "git",
                "-C",
                str(root_repository),
                "rev-list",
                "--parents",
                "-n",
                "1",
                root_commit,
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.split() == [root_commit]


def test_post_merge_reconciliation_bootstraps_and_recovers_every_commit() -> None:
    """Empty and existing state both enumerate the complete first-parent range."""
    updater = load_module(
        "post_merge_reconciliation", "scripts/update_post_merge_memory.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(
            ["git", "init", "--initial-branch", "main", str(root)],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "test@example.test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "Test"], check=True
        )

        readme = root / "README.md"
        readme.write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "base"],
            check=True,
            stdout=subprocess.PIPE,
        )
        base_sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()

        subprocess.run(
            ["git", "-C", str(root), "switch", "-c", "feature"],
            check=True,
            stdout=subprocess.PIPE,
        )
        intent_path = root / updater.BOOTSTRAP_INTENT_PATH
        intent_path.parent.mkdir(parents=True)
        intent_path.write_text(valid_loop_intent(), encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(root), "add", updater.BOOTSTRAP_INTENT_PATH],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "automation"],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "-C", str(root), "switch", "main"],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "-C", str(root), "merge", "--no-ff", "feature", "-m", "activate"],
            check=True,
            stdout=subprocess.PIPE,
        )
        activation_sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()

        readme.write_text("base\nlater\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "later"],
            check=True,
            stdout=subprocess.PIPE,
        )
        target_sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()

        assert updater.plan_reconciliation_commits(root, target_sha, None) == [
            activation_sha,
            target_sha,
        ]
        assert updater.plan_reconciliation_commits(
            root, target_sha, activation_sha
        ) == [target_sha]
        assert updater.plan_reconciliation_commits(root, target_sha, target_sha) == []
        assert_loop_error(
            updater,
            lambda: updater.plan_reconciliation_commits(root, base_sha, None),
            "no unique loop-memory bootstrap",
        )

        subprocess.run(
            ["git", "-C", str(root), "switch", "-c", "divergent", activation_sha],
            check=True,
            stdout=subprocess.PIPE,
        )
        (root / "divergent.txt").write_text("other\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "divergent.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "divergent"],
            check=True,
            stdout=subprocess.PIPE,
        )
        divergent_sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        assert_loop_error(
            updater,
            lambda: updater.plan_reconciliation_commits(
                root, divergent_sha, target_sha
            ),
            "not on the target main ancestry",
        )


def test_loop_memory_target_resolution_rejects_stale_replays() -> None:
    """Dispatch must be current; queued push may only reconcile forward."""
    updater = load_module(
        "post_merge_target_resolution", "scripts/update_post_merge_memory.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(
            ["git", "init", "--initial-branch", "main", str(root)],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "test@example.test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "Test"], check=True
        )
        tracked = root / "state.txt"
        tracked.write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "state.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "one"],
            check=True,
            stdout=subprocess.PIPE,
        )
        first = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        tracked.write_text("two\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "state.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "two"],
            check=True,
            stdout=subprocess.PIPE,
        )
        current = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        assert (
            updater.resolve_reconciliation_target(root, "push", first, current)
            == current
        )
        assert (
            updater.resolve_reconciliation_target(
                root, "repository_dispatch", current, current
            )
            == current
        )
        assert_loop_error(
            updater,
            lambda: updater.resolve_reconciliation_target(
                root, "repository_dispatch", first, current
            ),
            "replay target is stale",
        )

        subprocess.run(
            ["git", "-C", str(root), "switch", "-c", "divergent", first],
            check=True,
            stdout=subprocess.PIPE,
        )
        (root / "other.txt").write_text("other\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "other.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "divergent"],
            check=True,
            stdout=subprocess.PIPE,
        )
        divergent = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        assert_loop_error(
            updater,
            lambda: updater.resolve_reconciliation_target(
                root, "push", divergent, current
            ),
            "not on current protected-main ancestry",
        )
        assert_loop_error(
            updater,
            lambda: updater.resolve_reconciliation_target(
                root, "manual", current, current
            ),
            "unsupported loop-memory event",
        )


def test_post_merge_collection_binds_exact_pr_and_checks() -> None:
    """The collector binds one main merge SHA and final-head check evidence."""
    updater = load_module(
        "post_merge_collection", "scripts/update_post_merge_memory.py"
    )
    merge_sha = "a" * 40
    head_sha = "b" * 40
    responses = {
        f"/repos/Flow-Research/workstream/commits/{merge_sha}/pulls?per_page=100": [
            {
                "number": 120,
                "state": "closed",
                "merged_at": "2026-07-14T20:00:00Z",
                "merge_commit_sha": merge_sha,
                "html_url": "https://github.com/Flow-Research/workstream/pull/120",
                "title": "Canonical actor profile",
                "base": {"ref": "main"},
                "head": {"sha": head_sha, "ref": "codex/ws-auth-001-06"},
                "merged_by": {"login": "manager"},
            }
        ],
        "/repos/Flow-Research/workstream/pulls/120": {
            "number": 120,
            "state": "closed",
            "merged_at": "2026-07-14T20:00:00Z",
            "merge_commit_sha": merge_sha,
            "html_url": "https://github.com/Flow-Research/workstream/pull/120",
            "title": "Canonical actor profile",
            "base": {"ref": "main"},
            "head": {"sha": head_sha, "ref": "codex/ws-auth-001-06"},
            "merged_by": {"login": "manager"},
        },
        "/repos/Flow-Research/workstream/pulls/120/files?per_page=100&page=1": [
            {
                "filename": ".agent-loop/merge-intents/WS-AUTH-001-06.json",
                "status": "added",
            }
        ],
        (
            "/repos/Flow-Research/workstream/contents/"
            ".agent-loop/merge-intents/WS-AUTH-001-06.json"
            f"?ref={head_sha}"
        ): {
            "encoding": "base64",
            "sha": "d" * 40,
            "content": updater_base64(valid_loop_intent()),
        },
        f"/repos/Flow-Research/workstream/commits/{merge_sha}": {
            "parents": [{"sha": "0" * 40}]
        },
        f"/repos/Flow-Research/workstream/commits/{head_sha}/check-runs?per_page=100": {
            "check_runs": [
                {
                    "name": "agent-gates",
                    "conclusion": "success",
                    "started_at": "2026-07-14T19:49:00Z",
                    "completed_at": "2026-07-14T19:50:00Z",
                    "details_url": "https://example.test/gates",
                },
                {
                    "name": "test",
                    "conclusion": "success",
                    "started_at": "2026-07-14T19:50:00Z",
                    "completed_at": "2026-07-14T19:51:00Z",
                    "details_url": "https://example.test/test",
                },
            ]
        },
        f"/repos/Flow-Research/workstream/commits/{head_sha}/status?per_page=100": {
            "statuses": [
                {
                    "context": "CodeRabbit",
                    "state": "success",
                    "updated_at": "2026-07-14T19:52:00Z",
                    "target_url": "https://example.test/review",
                }
            ]
        },
        f"/repos/Flow-Research/workstream/git/trees/{head_sha}?recursive=1": {
            "truncated": False,
            "tree": [
                {
                    "type": "blob",
                    "path": (
                        ".agent-loop/initiatives/WS-AUTH-001-example/chunks/"
                        "WS-AUTH-001-07-authorization-kernel.md"
                    ),
                    "sha": "e" * 40,
                }
            ],
        },
        f"/repos/Flow-Research/workstream/git/blobs/{'e' * 40}": {
            "encoding": "base64",
            "sha": "e" * 40,
            "content": updater_base64(
                "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n"
            ),
        },
    }

    class FakeClient:
        def get_json(self, path: str):
            return responses[path]

        def get_paginated(self, path: str):
            return responses[f"{path}?per_page=100&page=1"]

    record = updater.collect_merge_record(
        FakeClient(), "Flow-Research/workstream", merge_sha
    )
    assert record["source"]["main_sha"] == merge_sha
    assert record["source"]["head_sha"] == head_sha
    assert record["source"]["first_parent_sha"] == "0" * 40
    assert record["source"]["intent_blob_sha"] == "d" * 40
    assert record["completed_chunk"]["chunk_id"] == "WS-AUTH-001-06"
    assert record["checks"]["all_required_passed"] is True


def test_generated_loop_memory_validator_detects_drift() -> None:
    """The independent validator detects ledger and rendered-state drift."""
    updater = load_module(
        "post_merge_validator_updater", "scripts/update_post_merge_memory.py"
    )
    checker = load_module("post_merge_validator", "scripts/check_loop_memory_state.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        updater.apply_merge_record(root, loop_record(updater))
        assert checker.generated_state_failures(root) == []
        rendered_path = root / updater.RENDERED_PATH
        rendered_path.write_text(
            rendered_path.read_text(encoding="utf-8") + "Tampered next gate.\n",
            encoding="utf-8",
        )
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(root),
            "rendered loop state does not match",
        )
        rendered_path.write_text("stale\n", encoding="utf-8")
        failures = checker.generated_state_failures(root)
        assert failures == [
            ".agent-loop/LOOP_STATE.md: rendered state does not match canonical JSON",
            ".agent-loop/LOOP_STATE.md: digest does not match manifest",
        ]


def test_generated_loop_memory_signature_authenticates_every_canonical_file() -> None:
    """Only the Actions-held private key can authenticate generated branch state."""
    updater = load_module("post_merge_signature", "scripts/update_post_merge_memory.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", private_key],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                private_key,
                "-pubout",
                "-out",
                public_key,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        updater.apply_merge_record(root, loop_record(updater))
        updater.sign_generated_state(root, private_key)
        updater.verify_generated_state_signature(root, public_key)
        manifest = json.loads(
            (root / updater.MANIFEST_PATH).read_text(encoding="utf-8")
        )
        signed_paths = tuple(Path(item["path"]) for item in manifest["payloads"]) + (
            updater.MANIFEST_PATH,
            updater.SIGNATURE_PATH,
        )
        old_signed_snapshot = {
            path: (root / path).read_bytes() for path in signed_paths
        }

        successor = loop_record(
            updater,
            sha="c" * 40,
            first_parent_sha="a" * 40,
            pr_number=121,
        )
        updater.apply_merge_record(root, successor)
        assert_loop_error(
            updater,
            lambda: updater.verify_generated_state_signature(root, public_key),
            "signature verification failed",
        )
        updater.sign_generated_state(root, private_key)
        updater.verify_generated_state_signature(root, public_key, "c" * 40)

        for path, content in old_signed_snapshot.items():
            (root / path).write_bytes(content)
        updater.verify_generated_state_signature(root, public_key)
        assert_loop_error(
            updater,
            lambda: updater.verify_generated_state_signature(
                root, public_key, "c" * 40
            ),
            "not current for protected main",
        )
        updater.apply_merge_record(root, successor)
        updater.sign_generated_state(root, private_key)
        updater.verify_generated_state_signature(root, public_key, "c" * 40)

        signature_path = root / updater.SIGNATURE_PATH
        signature_path.write_text("invalid\n", encoding="ascii")
        assert_loop_error(
            updater,
            lambda: updater.verify_generated_state_signature(root, public_key),
            "signature is unreadable",
        )
        updater.sign_generated_state(root, private_key)
        (root / updater.RENDERED_PATH).write_text(
            (root / updater.RENDERED_PATH).read_text(encoding="utf-8")
            + "forged but unsigned\n",
            encoding="utf-8",
        )
        assert_loop_error(
            updater,
            lambda: updater.verify_generated_state_signature(root, public_key),
            "rendered loop state does not match",
        )


def test_schema_v1_signed_state_is_discarded_before_clean_v2_bootstrap() -> None:
    """A valid old-domain signature cannot preserve any schema-v1 state."""
    updater = load_module(
        "post_merge_v1_clean_cut", "scripts/update_post_merge_memory.py"
    )
    checker = load_module(
        "post_merge_v1_clean_cut_checker", "scripts/check_loop_memory_state.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", private_key],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", private_key, "-pubout", "-out", public_key],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        rejected_v1_state = loop_record(updater)
        rejected_v1_state["schema_version"] = 1
        rejected_v1_state["completed_chunk"]["schema_version"] = 1
        rejected_v1_state["completed_chunk"]["next_chunk_id"] = "WS-ART-001-02A1"
        rejected_v1_state["completed_chunk"]["next_chunk_title"] = "External Adapter"
        rejected_v1_state["gate"]["next_chunk_id"] = "WS-ART-001-02A1"
        rejected_v1_state["gate"]["next_chunk_title"] = "External Adapter"
        entry = {
            "schema_version": 1,
            "previous_entry_hash": None,
            "record": rejected_v1_state,
            "entry_hash": updater._ledger_hash(None, rejected_v1_state),
        }
        agent_loop = root / ".agent-loop"
        agent_loop.mkdir()
        (root / updater.STATE_PATH).write_text(
            updater._canonical_json(rejected_v1_state, pretty=True), encoding="utf-8"
        )
        (root / updater.RENDERED_PATH).write_text(
            updater.render_state(rejected_v1_state), encoding="utf-8"
        )
        (root / updater.LEDGER_PATH).write_text(
            f"{updater._canonical_json(entry)}\n", encoding="utf-8"
        )
        sign_loop_state_with_domain(
            updater,
            root,
            private_key,
            b"workstream-loop-memory-signature-v1\0",
        )
        sentinel = root / "preserved.txt"
        sentinel.write_text("not generated\n", encoding="utf-8")

        assert updater.prepare_generated_state_root(root, public_key) is False
        for generated_path in (
            updater.STATE_PATH,
            updater.RENDERED_PATH,
            updater.LEDGER_PATH,
            updater.SIGNATURE_PATH,
        ):
            assert not (root / generated_path).exists()
        assert sentinel.read_text(encoding="utf-8") == "not generated\n"

        current = loop_record(updater)
        updater.apply_merge_record(root, current)
        updater.sign_generated_state(root, private_key)
        updater.verify_generated_state_signature(
            root, public_key, current["source"]["main_sha"]
        )
        assert checker.generated_state_failures(root) == []


def test_schema_v1_ledger_and_signature_domains_fail_independently() -> None:
    """V2 state rejects an isolated v1 ledger envelope and v1 signature domain."""
    updater = load_module(
        "post_merge_v1_isolated_rejection", "scripts/update_post_merge_memory.py"
    )
    checker = load_module(
        "post_merge_v1_isolated_checker", "scripts/check_loop_memory_state.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        ledger_root = root / "ledger"
        updater.apply_merge_record(ledger_root, loop_record(updater))
        ledger_path = ledger_root / updater.LEDGER_PATH
        ledger_entry = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger_entry["schema_version"] = 1
        ledger_path.write_text(
            f"{updater._canonical_json(ledger_entry)}\n", encoding="utf-8"
        )
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(ledger_root),
            "ledger entry has an invalid schema",
        )
        assert any(
            "invalid entry schema" in failure
            for failure in checker.generated_state_failures(ledger_root)
        )

        signature_root = root / "signature"
        updater.apply_merge_record(signature_root, loop_record(updater))
        updater.validate_generated_state(signature_root)
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", private_key],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", private_key, "-pubout", "-out", public_key],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        sign_loop_state_with_domain(
            updater,
            signature_root,
            private_key,
            b"workstream-loop-memory-signature-v1\0",
        )
        assert_loop_error(
            updater,
            lambda: updater.verify_generated_state_signature(
                signature_root, public_key, "a" * 40
            ),
            "signature verification failed",
        )


def test_live_and_historical_records_reject_cross_initiative_gates() -> None:
    """Hash-consistent state still fails when lifecycle authority crosses initiatives."""
    updater = load_module(
        "post_merge_cross_scope_state", "scripts/update_post_merge_memory.py"
    )
    checker = load_module(
        "post_merge_cross_scope_checker", "scripts/check_loop_memory_state.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        record = loop_record(updater)
        record["completed_chunk"]["next_chunk_id"] = "WS-ART-001-02A1"
        record["completed_chunk"]["next_chunk_title"] = "External Adapter"
        record["gate"]["next_chunk_id"] = "WS-ART-001-02A1"
        record["gate"]["next_chunk_title"] = "External Adapter"
        entry = updater._ledger_entry(record, None)
        (root / updater.STATE_PATH).parent.mkdir(parents=True)
        (root / updater.STATE_PATH).write_text(
            updater._canonical_json(record, pretty=True), encoding="utf-8"
        )
        (root / updater.RENDERED_PATH).write_text(
            updater.render_state(record), encoding="utf-8"
        )
        (root / updater.LEDGER_PATH).write_text(
            f"{updater._canonical_json(entry)}\n", encoding="utf-8"
        )
        updater._write_projections(root, [record])
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(root),
            "next_chunk_id must belong",
        )
        failures = checker.generated_state_failures(root)
        assert any("next chunk does not belong" in failure for failure in failures)

        valid = loop_record(updater)
        invalid_gate = json.loads(json.dumps(valid))
        invalid_gate["gate"]["next_chunk_title"] = "Mismatched"
        entry = updater._ledger_entry(invalid_gate, None)
        (root / updater.STATE_PATH).write_text(
            updater._canonical_json(invalid_gate, pretty=True), encoding="utf-8"
        )
        (root / updater.RENDERED_PATH).write_text(
            updater.render_state(invalid_gate), encoding="utf-8"
        )
        (root / updater.LEDGER_PATH).write_text(
            f"{updater._canonical_json(entry)}\n", encoding="utf-8"
        )
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(root),
            "next gate does not match",
        )
        assert any(
            "next gate does not match" in failure
            for failure in checker.generated_state_failures(root)
        )


def test_loop_memory_schema_v2_rejection_matrix_is_fail_closed() -> None:
    """Schema-v2 trust boundaries reject malformed metadata and state records."""
    updater = load_module(
        "post_merge_v2_rejection_matrix", "scripts/update_post_merge_memory.py"
    )
    checker = load_module(
        "post_merge_v2_checker_matrix", "scripts/check_loop_memory_state.py"
    )

    no_successor_text = valid_loop_intent().replace(
        '"next_chunk_id":"WS-AUTH-001-07","next_chunk_title":"Authorization Kernel"',
        '"next_chunk_id":null,"next_chunk_title":null',
    )
    no_successor = updater.parse_loop_metadata(no_successor_text)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        updater._validate_local_successor_contract(root, no_successor)
        updater._validate_remote_successor_contract(
            SimpleNamespace(get_json=lambda _path: None),
            "Flow-Research/workstream",
            "a" * 40,
            no_successor,
        )
        no_successor_record = loop_record(updater)
        no_successor_record["completed_chunk"] = updater.asdict(no_successor)
        no_successor_record["gate"] = {
            "status": "stopped_after_merge",
            "next_chunk_id": None,
            "next_chunk_title": None,
            "next_requires_explicit_start": True,
        }
        assert updater.apply_merge_record(root, no_successor_record) is True
        assert updater.apply_merge_record(root, no_successor_record) is False
        updater.validate_generated_state(root)
        assert "Next chunk: none recorded" in (root / updater.RENDERED_PATH).read_text(
            encoding="utf-8"
        )
        assert checker.generated_state_failures(root) == []

        private_key = root / "private.pem"
        public_key = root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", private_key],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", private_key, "-pubout", "-out", public_key],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        updater.sign_generated_state(root, private_key)
        updater.verify_generated_state_signature(root, public_key, "a" * 40)
        assert checker.generated_state_failures(root) == []

    assert updater._contract_title("not a contract\n", "WS-AUTH-001-07") is None
    assert (
        updater._contract_title(
            "# Chunk Contract: WS-AUTH-001-07 Authorization Kernel\n",
            "WS-AUTH-001-07",
        )
        is None
    )
    assert (
        updater._contract_title("# Chunk Contract: WS-AUTH-001-07\n", "WS-AUTH-001-07")
        is None
    )
    assert (
        updater._initiative_directory_from_path(
            ".agent-loop/initiatives/WS-AUTH-001-example/chunks/WS-AUTH-001-07.md",
            "WS-AUTH-001",
        )
        == "WS-AUTH-001-example"
    )
    assert (
        updater._initiative_directory_from_path(
            ".agent-loop/initiatives/WS-ART-001-example/chunks/WS-AUTH-001-07.md",
            "WS-AUTH-001",
        )
        is None
    )
    assert updater._is_chunk_contract_path(
        ".agent-loop/initiatives/WS-AUTH-001-example/chunks/WS-AUTH-001-07.md",
        "WS-AUTH-001-example",
    )
    assert not updater._is_chunk_contract_path(
        ".agent-loop/initiatives/WS-AUTH-001-example/chunks/WS-AUTH-001-07.txt",
        "WS-AUTH-001-example",
    )

    metadata_payload = json.loads(valid_loop_intent())
    metadata_mutations = (
        ("initiative_id", None),
        ("chunk_title", ""),
        ("next_chunk_title", 7),
        ("next_requires_explicit_start", "yes"),
    )
    for field, value in metadata_mutations:
        malformed = dict(metadata_payload)
        malformed[field] = value
        assert_loop_error(
            updater,
            lambda malformed=malformed: updater.parse_loop_metadata(
                json.dumps(malformed)
            ),
            "must" if field != "initiative_id" else "required",
        )
    oversized_id = "WS-" + ("A" * 78)
    oversized_metadata = dict(metadata_payload)
    oversized_metadata["initiative_id"] = oversized_id
    assert_loop_error(
        updater,
        lambda: updater.parse_loop_metadata(json.dumps(oversized_metadata)),
        "bounded single-line",
    )

    class RemoteClient:
        def __init__(self, tree, returned_sha: str = "e" * 40):
            self.tree = tree
            self.returned_sha = returned_sha

        def get_json(self, path: str):
            if "/git/trees/" in path:
                return self.tree
            return {
                "encoding": "base64",
                "sha": self.returned_sha,
                "content": updater_base64(
                    "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n"
                ),
            }

    valid_item = {
        "type": "blob",
        "path": (
            ".agent-loop/initiatives/WS-AUTH-001-example/chunks/"
            "WS-AUTH-001-07-authorization-kernel.md"
        ),
        "sha": "e" * 40,
    }
    assert_loop_error(
        updater,
        lambda: updater._validate_remote_successor_contract(
            RemoteClient(
                {
                    "truncated": False,
                    "tree": [None, {"type": "tree"}, {"type": "blob"}, valid_item],
                },
                returned_sha="f" * 40,
            ),
            "Flow-Research/workstream",
            "a" * 40,
            updater.parse_loop_metadata(valid_loop_intent()),
        ),
        "identity does not match",
    )
    invalid_sha_item = dict(valid_item)
    invalid_sha_item["sha"] = "invalid"
    assert_loop_error(
        updater,
        lambda: updater._validate_remote_successor_contract(
            RemoteClient({"truncated": False, "tree": [invalid_sha_item]}),
            "Flow-Research/workstream",
            "a" * 40,
            updater.parse_loop_metadata(valid_loop_intent()),
        ),
        "canonical blob SHA",
    )

    assert_loop_error(
        updater,
        lambda: updater._git_lines(Path("/not/a/repository"), ["status"], "git failed"),
        "git failed",
    )
    assert_loop_error(
        updater,
        lambda: updater._is_ancestor(Path("/not/a/repository"), "a" * 40, "b" * 40),
        "cannot resolve main commit ancestry",
    )
    assert (
        updater._latest_named(
            [
                {},
                {"name": "gate", "started_at": "2026-01-02"},
                {"name": "gate", "started_at": "2026-01-01"},
            ],
            "name",
            "started_at",
        )["gate"]["started_at"]
        == "2026-01-02"
    )
    for value, expected in (
        (None, "ISO timestamp"),
        ("not-a-time", "ISO timestamp"),
        ("2026-07-14T20:00:00", "timezone"),
    ):
        assert_loop_error(
            updater,
            lambda value=value: updater._parse_timestamp(value, "time"),
            expected,
        )

    base = loop_record(updater)
    record_mutations = (
        (lambda row: row.update(schema_version=2.0), "invalid schema"),
        (lambda row: row.update(schema_version="2"), "invalid schema"),
        (lambda row: row.update(schema_version=True), "invalid schema"),
        (lambda row: row.update(state_branch="main"), "state branch"),
        (lambda row: row.update(repository=7), "repository must be owner/name"),
        (
            lambda row: row["source"].update(main_sha=None),
            "40 lowercase hexadecimal",
        ),
        (lambda row: row["source"].update(pr_number=True), "positive PR number"),
        (lambda row: row["source"].update(pr_url="https://invalid"), "PR URL"),
        (lambda row: row.update(updated_at="2026-07-14T20:01:00Z"), "updated_at"),
        (lambda row: row.update(completed_chunk=[]), "JSON object"),
        (
            lambda row: row["completed_chunk"].update(chunk_title="valid\ninjected"),
            "single-line",
        ),
        (lambda row: row["source"].update(intent_path="wrong"), "intent path"),
        (lambda row: row.update(active={}), "active chunk state"),
        (lambda row: row.update(checks=[]), "check evidence"),
        (lambda row: row["checks"].update(required={}), "required-check"),
        (
            lambda row: row["checks"]["required"].update({"agent-gates": []}),
            "invalid for agent-gates",
        ),
        (
            lambda row: row["checks"]["required"]["agent-gates"].update(kind=7),
            "kind is invalid",
        ),
        (
            lambda row: row["checks"]["required"]["agent-gates"].update(conclusion=7),
            "conclusion is invalid",
        ),
        (
            lambda row: row["checks"]["required"]["agent-gates"].update(url=7),
            "URL is invalid",
        ),
        (
            lambda row: row["checks"].update(all_required_passed=False),
            "aggregate check evidence",
        ),
    )
    for mutate, expected in record_mutations:
        malformed = json.loads(json.dumps(base))
        mutate(malformed)
        assert_loop_error(
            updater,
            lambda malformed=malformed: updater._validate_record(malformed),
            expected,
        )
        assert checker._record_failures(malformed, "record")

    metadata_failure_mutations = (
        lambda value: value.clear(),
        lambda value: value.update(schema_version=1),
        lambda value: value.update(schema_version=2.0),
        lambda value: value.update(schema_version="2"),
        lambda value: value.update(schema_version=True),
        lambda value: value.update(initiative_id="bad"),
        lambda value: value.update(initiative_id="WS-" + ("A" * 78)),
        lambda value: value.update(chunk_id="WS-AUTH-" + ("A" * 73)),
        lambda value: value.update(chunk_id="WS-ART-001-01"),
        lambda value: value.update(chunk_title=""),
        lambda value: value.update(chunk_title="x" * 161),
        lambda value: value.update(chunk_title="valid\ninjected"),
        lambda value: value.update(next_chunk_title=None),
        lambda value: value.update(next_chunk_id="WS-ART-001-02"),
        lambda value: value.update(next_chunk_id="WS-AUTH-" + ("A" * 73)),
        lambda value: value.update(next_chunk_title=7),
        lambda value: value.update(next_chunk_title="x" * 161),
        lambda value: value.update(next_requires_explicit_start="yes"),
    )
    for mutate in metadata_failure_mutations:
        malformed = json.loads(json.dumps(base["completed_chunk"]))
        mutate(malformed)
        assert checker._metadata_failures(malformed, "metadata")


def test_generated_loop_memory_prepare_recovers_hostile_path_types() -> None:
    """Directories and symlinks cannot wedge deterministic state reconstruction."""
    updater = load_module(
        "post_merge_prepare_state", "scripts/update_post_merge_memory.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        public_key = root / "unused-public.pem"
        state_directory = root / updater.STATE_PATH
        state_directory.mkdir(parents=True)
        (state_directory / "placeholder").write_text("hostile\n", encoding="utf-8")
        outside = root / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("preserve\n", encoding="utf-8")
        (root / updater.SIGNATURE_PATH).symlink_to(sentinel)

        assert updater.prepare_generated_state_root(root, public_key) is False
        assert not state_directory.exists()
        assert not (root / updater.SIGNATURE_PATH).exists()
        assert sentinel.read_text(encoding="utf-8") == "preserve\n"

        updater.apply_merge_record(root, loop_record(updater))
        (root / updater.RENDERED_PATH).write_bytes(b"\xff\xfe")
        assert updater.prepare_generated_state_root(root, public_key) is False
        assert not (root / updater.RENDERED_PATH).exists()

        updater.apply_merge_record(root, loop_record(updater))
        malformed_state = loop_record(updater)
        malformed_state["source"] = []
        (root / updater.STATE_PATH).write_text(
            json.dumps(malformed_state), encoding="utf-8"
        )
        assert updater.prepare_generated_state_root(root, public_key) is False
        assert not (root / updater.STATE_PATH).exists()

        agent_loop = root / updater.STATE_PATH.parent
        shutil.rmtree(agent_loop)
        agent_loop.symlink_to(outside, target_is_directory=True)
        assert updater.prepare_generated_state_root(root, public_key) is False
        assert agent_loop.is_dir() and not agent_loop.is_symlink()
        assert sentinel.read_text(encoding="utf-8") == "preserve\n"


def test_generated_loop_memory_escapes_markdown_metadata() -> None:
    """PR and chunk titles cannot inject generated Markdown structure."""
    updater = load_module(
        "post_merge_markdown_escape", "scripts/update_post_merge_memory.py"
    )
    record = loop_record(updater)
    record["source"]["pr_title"] = "Title [link](https://unsafe.test) `code`"
    record["completed_chunk"]["chunk_title"] = "Chunk <unsafe>"
    rendered = updater.render_state(record)
    assert "Title \\[link\\](https://unsafe.test) \\`code\\`" in rendered
    assert "Chunk &lt;unsafe&gt;" in rendered


def test_loop_memory_workflow_isolated_write_boundary() -> None:
    """The write-capable workflow runs on trusted main and targets only the state branch."""
    workflow = (ROOT / ".github/workflows/loop-memory.yml").read_text(encoding="utf-8")
    start_workflow = (ROOT / ".github/workflows/loop-memory-start.yml").read_text(encoding="utf-8")
    agent_gates = (ROOT / ".github/workflows/agent-gates.yml").read_text(
        encoding="utf-8"
    )
    assert "pull_request_target" not in workflow
    assert "workflow_dispatch" not in workflow
    assert "repository_dispatch" in workflow
    assert "persist-credentials: false" in workflow
    assert "ref: main" in workflow
    assert "contents: write" in workflow
    assert "pull-requests: read" in workflow
    assert "LOOP_MEMORY_SIGNING_KEY" in workflow
    assert workflow.count("LOOP_MEMORY_SIGNING_KEY:") == 1
    assert "LOOP_MEMORY_PRIVATE_KEY" not in workflow
    assert "trap 'rm -f \"${private_key}\"' EXIT" in workflow
    assert "prepare-state" in workflow
    assert "prepare-output" in workflow
    assert "update_post_merge_memory.py publish" in workflow
    assert "validate-tree" not in workflow
    assert "read-tree --empty" not in workflow
    assert "commit-tree" not in workflow
    assert "rev-parse --verify HEAD" in workflow
    assert "git push" not in workflow
    assert "--expected-main-sha" in workflow
    assert "HEAD:refs/heads/${STATE_BRANCH}" not in workflow
    assert "HEAD:refs/heads/main" not in workflow
    assert "gh pr create" not in workflow
    for text in (workflow, start_workflow):
        assert text.count("update_post_merge_memory.py reconcile") == 1
        assert "prepare-recovery" not in text
        assert "update_post_merge_memory.py update" not in text
        assert "assert-recovery-consumed" not in text
    assert start_workflow.index("update_post_merge_memory.py reconcile") < start_workflow.index("apply-event")
    assert workflow.index("update_post_merge_memory.py reconcile") < workflow.index("sign-state")
    assert '--target-sha "${TARGET_SHA}"' in workflow
    assert "resolve-target" in workflow
    assert "EVENT_SHA" in workflow
    assert "TARGET_SHA" in workflow
    assert "MERGE_SHA" not in workflow
    assert "github.event.client_payload.target_sha" in workflow
    assert "github.event.client_payload.merge_sha" not in workflow
    job_environment = workflow.split("    steps:", 1)[0]
    assert "GH_TOKEN:" not in job_environment
    assert "GITHUB_TOKEN:" not in job_environment
    assert workflow.count("GH_TOKEN: ${{ github.token }}") == 3
    assert workflow.count("GITHUB_TOKEN: ${{ github.token }}") == 1
    assert "replay target is stale" in (
        ROOT / "scripts/update_post_merge_memory.py"
    ).read_text(encoding="utf-8")
    assert "update_post_merge_memory.py sign-state" in workflow
    assert "check_loop_memory_state.py" in workflow
    assert workflow.index("Resolve trusted protected-main target") < workflow.index(
        "Prepare generated state branch"
    )
    assert workflow.index("prepare-state") < workflow.index("update_post_merge_memory.py reconcile")
    assert workflow.index("update_post_merge_memory.py reconcile") < workflow.index("sign-state")
    assert workflow.index("sign-state") < workflow.index("--expected-main-sha")
    assert workflow.index("--expected-main-sha") < workflow.index(
        "check_loop_memory_state.py"
    )
    assert "validate-merge-intent" in agent_gates
    assert "github.event.pull_request.body" not in agent_gates


def assert_loop_error(module, callback, expected: str) -> None:
    """Assert one loop-memory operation fails with a bounded diagnostic."""
    try:
        callback()
    except module.LoopMemoryError as exc:
        assert expected in str(exc)
        return
    raise AssertionError(f"expected LoopMemoryError containing {expected!r}")


def test_post_merge_input_and_check_validation_fail_closed() -> None:
    """Untrusted identifiers, payload types, and incomplete checks remain bounded."""
    updater = load_module(
        "post_merge_input_validation", "scripts/update_post_merge_memory.py"
    )
    assert_loop_error(
        updater, lambda: updater.parse_loop_metadata(None), "must be text"
    )
    assert_loop_error(
        updater,
        lambda: updater.parse_loop_metadata(
            valid_loop_intent().replace(
                '"chunk_title":"Canonical Actor Profile"', '"chunk_title":7'
            )
        ),
        "chunk_title must be a string",
    )
    assert_loop_error(
        updater,
        lambda: updater.parse_loop_metadata(
            valid_loop_intent().replace("Canonical Actor Profile", "Bad\\nTitle")
        ),
        "single-line string",
    )
    assert_loop_error(
        updater,
        lambda: updater.parse_loop_metadata(
            valid_loop_intent().replace("WS-AUTH-001-06", "bad id")
        ),
        "canonical lifecycle identifier",
    )
    assert_loop_error(
        updater,
        lambda: updater.parse_loop_metadata(
            valid_loop_intent().replace(
                '"next_requires_explicit_start":true',
                '"next_requires_explicit_start":"yes"',
            )
        ),
        "must be a boolean",
    )
    assert_loop_error(
        updater,
        lambda: updater._validate_repository_and_sha("invalid", "a" * 40),
        "owner/name",
    )
    assert_loop_error(
        updater,
        lambda: updater._validate_repository_and_sha(
            "Flow-Research/workstream", "A" * 40
        ),
        "lowercase hexadecimal",
    )

    evidence = updater._check_evidence(
        [
            {
                "name": "test",
                "conclusion": "success",
                "status": "completed",
                "started_at": "2026-01-01T00:00:00Z",
            },
            {
                "name": "test",
                "conclusion": None,
                "status": "in_progress",
                "started_at": "2026-01-01T00:01:00Z",
            },
        ],
        [],
    )
    assert evidence["required"]["test"]["conclusion"] == "in_progress"
    assert evidence["required"]["agent-gates"]["kind"] == "missing"
    assert evidence["all_required_passed"] is False


def test_github_client_bounds_success_and_network_failure() -> None:
    """The stdlib client authenticates JSON requests and hides transport detail on failure."""
    updater = load_module(
        "post_merge_github_client", "scripts/update_post_merge_memory.py"
    )
    assert_loop_error(updater, lambda: updater.GitHubClient(""), "token is required")
    original_urlopen = updater.urllib.request.urlopen

    class Response(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    captured = {}

    def successful(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return Response('{"ok":true}')

    try:
        updater.urllib.request.urlopen = successful
        client = updater.GitHubClient("secret", "https://api.example.test/")
        assert client.get_json("/state") == {"ok": True}
        assert captured == {"authorization": "Bearer secret", "timeout": 30}

        def failed(_request, timeout=None):
            assert timeout == 30
            raise updater.urllib.error.URLError("secret transport detail")

        updater.urllib.request.urlopen = failed
        assert_loop_error(
            updater, lambda: client.get_json("/state"), "GitHub API request failed"
        )
    finally:
        updater.urllib.request.urlopen = original_urlopen


def test_github_client_pagination_is_complete_and_bounded() -> None:
    """List collection follows every page and rejects invalid or unbounded payloads."""
    updater = load_module(
        "post_merge_github_pagination", "scripts/update_post_merge_memory.py"
    )
    client = updater.GitHubClient("secret")
    requested = []

    def two_pages(path: str):
        requested.append(path)
        return list(range(100)) if path.endswith("page=1") else ["last"]

    client.get_json = two_pages
    assert client.get_paginated("/pulls?state=closed")[-1] == "last"
    assert requested == [
        "/pulls?state=closed&per_page=100&page=1",
        "/pulls?state=closed&per_page=100&page=2",
    ]

    client.get_json = lambda _path: {"items": []}
    assert_loop_error(
        client_module := updater, lambda: client.get_paginated("/pulls"), "not a list"
    )

    calls = 0

    def endless(_path: str):
        nonlocal calls
        calls += 1
        return [None] * 100

    client.get_json = endless
    assert_loop_error(
        client_module,
        lambda: client.get_paginated("/pulls"),
        "exceeded 100 pages",
    )
    assert calls == 100


def test_committed_merge_intent_fails_closed_on_untrusted_github_payloads() -> None:
    """The reviewed-head intent loader rejects ambiguous, corrupt, and mismatched files."""
    updater = load_module(
        "post_merge_intent_payloads", "scripts/update_post_merge_memory.py"
    )
    repository = "Flow-Research/workstream"
    head_sha = "b" * 40
    canonical_path = ".agent-loop/merge-intents/WS-AUTH-001-06.json"

    class FakeClient:
        def __init__(self, files, content=None):
            self.files = files
            self.content = content

        def get_paginated(self, _path: str):
            return self.files

        def get_json(self, path: str):
            if "/git/trees/" in path:
                return {
                    "truncated": False,
                    "tree": [
                        {
                            "type": "blob",
                            "path": (
                                ".agent-loop/initiatives/WS-AUTH-001-example/chunks/"
                                "WS-AUTH-001-07-authorization-kernel.md"
                            ),
                            "sha": "e" * 40,
                        }
                    ],
                }
            if "/git/blobs/" in path:
                return {
                    "encoding": "base64",
                    "sha": "e" * 40,
                    "content": updater_base64(
                        "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n"
                    ),
                }
            return self.content

    added = [{"filename": canonical_path, "status": "added"}]
    valid_content = {
        "encoding": "base64",
        "sha": "d" * 40,
        "content": "\n".join(
            textwrap.wrap(updater_base64(valid_loop_intent()), width=60)
        ),
    }
    metadata, path, blob_sha = updater.load_committed_merge_intent(
        FakeClient(added, valid_content), repository, 120, head_sha
    )
    assert metadata.chunk_id == "WS-AUTH-001-06"
    assert (path, blob_sha) == (canonical_path, "d" * 40)

    cases = [
        ([], valid_content, "exactly one"),
        (
            [{"filename": canonical_path, "status": "modified"}],
            valid_content,
            "exactly one",
        ),
        (added, [], "invalid shape"),
        (added, {**valid_content, "sha": "bad"}, "canonical SHA"),
        (added, {**valid_content, "content": 7}, "no encoded content"),
        (added, {**valid_content, "content": "not base64"}, "base64 UTF-8"),
        (
            added,
            {**valid_content, "content": base64.b64encode(b"\xff").decode("ascii")},
            "base64 UTF-8",
        ),
        (
            added,
            {**valid_content, "content": base64.b64encode(b"x" * 8193).decode("ascii")},
            "exceeds 8192 bytes",
        ),
        (
            [
                {
                    "filename": ".agent-loop/merge-intents/WS-AUTH-001-07.json",
                    "status": "added",
                }
            ],
            valid_content,
            "path does not match",
        ),
    ]
    for files, content, expected in cases:
        assert_loop_error(
            updater,
            lambda files=files, content=content: updater.load_committed_merge_intent(
                FakeClient(files, content), repository, 120, head_sha
            ),
            expected,
        )


def test_post_merge_collection_rejects_ambiguous_or_mismatched_prs() -> None:
    """Collector errors never guess across missing, ambiguous, or inconsistent PR facts."""
    updater = load_module(
        "post_merge_collection_errors", "scripts/update_post_merge_memory.py"
    )
    repository = "Flow-Research/workstream"
    merge_sha = "a" * 40
    association_path = f"/repos/{repository}/commits/{merge_sha}/pulls?per_page=100"
    valid_association = {
        "number": 120,
        "state": "closed",
        "merged_at": "2026-07-14T20:00:00Z",
        "merge_commit_sha": merge_sha,
        "base": {"ref": "main"},
    }

    class FakeClient:
        def __init__(self, responses):
            self.responses = responses

        def get_json(self, path: str):
            return self.responses[path]

    for payload, expected in (
        ({}, "not a list"),
        ([], "exactly one"),
        ([valid_association, valid_association], "exactly one"),
    ):
        client = FakeClient({association_path: payload})
        assert_loop_error(
            updater,
            lambda client=client: updater.collect_merge_record(
                client, repository, merge_sha
            ),
            expected,
        )

    no_number = dict(valid_association)
    no_number["number"] = 0
    assert_loop_error(
        updater,
        lambda: updater.collect_merge_record(
            FakeClient({association_path: [no_number]}), repository, merge_sha
        ),
        "positive number",
    )
    assert_loop_error(
        updater,
        lambda: updater.collect_merge_record(
            FakeClient(
                {
                    association_path: [valid_association],
                    f"/repos/{repository}/pulls/120": [],
                }
            ),
            repository,
            merge_sha,
        ),
        "not an object",
    )
    mismatched = dict(valid_association)
    mismatched.update(
        {
            "merge_commit_sha": "c" * 40,
            "body": valid_loop_intent(),
            "head": {"sha": "b" * 40},
        }
    )
    assert_loop_error(
        updater,
        lambda: updater.collect_merge_record(
            FakeClient(
                {
                    association_path: [valid_association],
                    f"/repos/{repository}/pulls/120": mismatched,
                }
            ),
            repository,
            merge_sha,
        ),
        "do not match",
    )


def test_post_merge_state_rejects_corrupt_files_and_cli_misuse() -> None:
    """Corrupt generated files and wrong-branch CLI writes fail closed."""
    updater = load_module(
        "post_merge_corrupt_state", "scripts/update_post_merge_memory.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(root),
            "state file is missing",
        )

        state_path = root / updater.STATE_PATH
        state_path.parent.mkdir(parents=True)
        state_path.write_text("[]\n", encoding="utf-8")
        assert_loop_error(
            updater, lambda: updater.validate_generated_state(root), "JSON object"
        )
        state_path.write_text("{invalid\n", encoding="utf-8")
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(root),
            "cannot read generated state",
        )

        state_path.write_text(json.dumps(loop_record(updater)), encoding="utf-8")
        ledger_path = root / updater.LEDGER_PATH
        ledger_path.write_text("[]\n", encoding="utf-8")
        assert_loop_error(
            updater, lambda: updater.validate_generated_state(root), "JSON objects"
        )
        ledger_path.write_text("{invalid\n", encoding="utf-8")
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(root),
            "cannot read merge ledger",
        )

        subprocess.run(
            ["git", "init", "--initial-branch", "wrong", str(root)],
            check=True,
            stdout=subprocess.PIPE,
        )
        assert_loop_error(
            updater, lambda: updater._assert_state_branch(root), "must be checked out"
        )

        intent_repo = root / "intent-repo"
        subprocess.run(
            ["git", "init", "--initial-branch", "main", str(intent_repo)],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(intent_repo),
                "config",
                "user.email",
                "test@example.test",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(intent_repo), "config", "user.name", "Test"],
            check=True,
        )
        (intent_repo / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(intent_repo), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(intent_repo), "commit", "-m", "base"],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "-C", str(intent_repo), "switch", "-c", "feature"],
            check=True,
            stdout=subprocess.PIPE,
        )
        intent_path = intent_repo / ".agent-loop/merge-intents/WS-AUTH-001-06.json"
        intent_path.parent.mkdir(parents=True)
        intent_path.write_text(valid_loop_intent(), encoding="utf-8")
        contract_path = (
            intent_repo / ".agent-loop/initiatives/WS-AUTH-001-example/chunks/"
            "WS-AUTH-001-07-authorization-kernel.md"
        )
        contract_path.parent.mkdir(parents=True)
        contract_path.write_text(
            "# Chunk Contract: WS-AUTH-001-07 - Authorization Kernel\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(intent_repo),
                "add",
                intent_path.relative_to(intent_repo),
                contract_path.relative_to(intent_repo),
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(intent_repo), "commit", "-m", "intent"],
            check=True,
            stdout=subprocess.PIPE,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            assert (
                updater.main(
                    [
                        "validate-merge-intent",
                        "--repository-root",
                        str(intent_repo),
                        "--base-ref",
                        "main",
                    ]
                )
                == 0
            )
        with contextlib.redirect_stderr(io.StringIO()):
            assert (
                updater.main(
                    [
                        "validate-merge-intent",
                        "--repository-root",
                        str(intent_repo),
                        "--base-ref",
                        "missing",
                    ]
                )
                == 1
            )
        with contextlib.redirect_stderr(io.StringIO()):
            assert updater.main(["validate-state", "--state-root", str(root)]) == 1


def test_post_merge_cli_updates_and_shows_generated_state() -> None:
    """The CLI update, validation, and display modes operate on the dedicated branch."""
    updater = load_module("post_merge_cli", "scripts/update_post_merge_memory.py")
    original_client = updater.GitHubClient
    original_collect = updater.collect_merge_record
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(
            ["git", "init", "--initial-branch", updater.STATE_BRANCH, str(root)],
            check=True,
            stdout=subprocess.PIPE,
        )
        os.environ["TEST_GITHUB_TOKEN"] = "secret"
        updater.GitHubClient = lambda _token, _api_url: SimpleNamespace()
        updater.collect_merge_record = lambda _client, _repository, _sha: loop_record(
            updater
        )
        try:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                assert (
                    updater.main(
                        [
                            "update",
                            "--repository",
                            "Flow-Research/workstream",
                            "--merge-sha",
                            "a" * 40,
                            "--state-root",
                            str(root),
                            "--token-env",
                            "TEST_GITHUB_TOKEN",
                        ]
                    )
                    == 0
                )
            assert "updated for PR #120" in output.getvalue()
            with contextlib.redirect_stdout(io.StringIO()):
                assert updater.main(["validate-state", "--state-root", str(root)]) == 0
            with contextlib.redirect_stdout(io.StringIO()) as output:
                assert updater.main(["show", "--state-root", str(root)]) == 0
            assert "Generated Workstream Loop State" in output.getvalue()
        finally:
            updater.GitHubClient = original_client
            updater.collect_merge_record = original_collect
            os.environ.pop("TEST_GITHUB_TOKEN", None)


def test_generated_loop_memory_validator_covers_corruption_matrix() -> None:
    """Independent state validation reports each generated-file corruption family."""
    updater = load_module(
        "post_merge_corruption_updater", "scripts/update_post_merge_memory.py"
    )
    checker = load_module(
        "post_merge_corruption_checker", "scripts/check_loop_memory_state.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        assert len(checker.generated_state_failures(root)) == len(
            checker.GENERATED_FILES
        )
        (root / ".agent-loop").mkdir()
        for relative in checker.GENERATED_FILES:
            (root / relative).write_text("not-json\n", encoding="utf-8")
        assert "unreadable" in checker.generated_state_failures(root)[0]

        (root / checker.GENERATED_FILES[0]).write_text("[]\n", encoding="utf-8")
        (root / checker.GENERATED_FILES[2]).write_text("{}\n", encoding="utf-8")
        (root / checker.GENERATED_FILES[4]).write_text(
            '{"schema_version":2,"payloads":[]}\n', encoding="utf-8"
        )
        assert "expected a JSON object" in checker.generated_state_failures(root)[0]

        valid_root = root / "valid"
        updater.apply_merge_record(valid_root, loop_record(updater))
        with contextlib.redirect_stdout(io.StringIO()):
            assert checker.main(["--state-root", str(valid_root)]) == 0

        state_path = valid_root / updater.STATE_PATH
        ledger_path = valid_root / updater.LEDGER_PATH
        valid_ledger_text = ledger_path.read_text(encoding="utf-8")
        for malformed_schema_version in (2.0, "2", True):
            malformed_ledger = json.loads(valid_ledger_text)
            malformed_ledger["schema_version"] = malformed_schema_version
            ledger_path.write_text(
                f"{json.dumps(malformed_ledger)}\n",
                encoding="utf-8",
            )
            assert any(
                "invalid entry schema" in failure
                for failure in checker.generated_state_failures(valid_root)
            )
        ledger_path.write_text(valid_ledger_text, encoding="utf-8")

        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["schema_version"] = 1
        state["state_branch"] = "main"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        failures = checker.generated_state_failures(valid_root)
        assert any("schema version" in failure for failure in failures)
        assert any("unexpected state branch" in failure for failure in failures)
        assert any("ledger tail" in failure for failure in failures)
        with contextlib.redirect_stderr(io.StringIO()):
            assert checker.main(["--state-root", str(valid_root)]) == 1

    original_root = checker.ROOT
    original_status_files = checker.INITIATIVE_STATUS_FILES
    with tempfile.TemporaryDirectory() as tmpdir:
        checker.ROOT = Path(tmpdir)
        checker.INITIATIVE_STATUS_FILES = ()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                assert checker.main() == 1
        finally:
            checker.ROOT = original_root
            checker.INITIATIVE_STATUS_FILES = original_status_files


def test_full_merge_ledger_hash_chain_detects_history_tampering() -> None:
    """Mutation or deletion of a non-tail ledger entry is detected independently."""
    updater = load_module(
        "post_merge_history_updater", "scripts/update_post_merge_memory.py"
    )
    checker = load_module(
        "post_merge_history_checker", "scripts/check_loop_memory_state.py"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        first = loop_record(updater)
        second = loop_record(
            updater,
            sha="c" * 40,
            first_parent_sha="a" * 40,
            merged_at="2026-07-14T20:01:00Z",
            pr_number=121,
        )
        updater.apply_merge_record(root, first)
        updater.apply_merge_record(root, second)
        ledger_path = root / updater.LEDGER_PATH
        original_lines = ledger_path.read_text(encoding="utf-8").splitlines()

        tampered = [json.loads(line) for line in original_lines]
        tampered[0]["record"]["source"]["pr_title"] = "tampered"
        ledger_path.write_text(
            "".join(f"{json.dumps(entry)}\n" for entry in tampered),
            encoding="utf-8",
        )
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(root),
            "entry hash is invalid",
        )
        assert any(
            "hash chain" in failure
            for failure in checker.generated_state_failures(root)
        )

        ledger_path.write_text(f"{original_lines[1]}\n", encoding="utf-8")
        assert_loop_error(
            updater,
            lambda: updater.validate_generated_state(root),
            "previous hash chain is invalid",
        )
        assert any(
            "hash chain" in failure
            for failure in checker.generated_state_failures(root)
        )

        ledger_path.write_text("\n".join(original_lines) + "\n", encoding="utf-8")
        schema_tampered = [json.loads(line) for line in original_lines]
        schema_tampered[0]["schema_version"] = 999
        ledger_path.write_text(
            "".join(f"{json.dumps(entry)}\n" for entry in schema_tampered),
            encoding="utf-8",
        )
        assert any(
            "invalid entry schema" in failure
            for failure in checker.generated_state_failures(root)
        )


def test_merge_ledger_rejects_schema_record_and_ancestry_corruption() -> None:
    """Every ledger envelope and first-parent link is validated before state changes."""
    updater = load_module(
        "post_merge_ledger_corruption", "scripts/update_post_merge_memory.py"
    )
    assert_loop_error(
        updater,
        lambda: updater._validate_ledger_entries([{}]),
        "invalid schema",
    )
    for malformed_schema_version in (2.0, "2", True):
        malformed_envelope = updater._ledger_entry(loop_record(updater), None)
        malformed_envelope["schema_version"] = malformed_schema_version
        assert_loop_error(
            updater,
            lambda malformed_envelope=malformed_envelope: (
                updater._validate_ledger_entries([malformed_envelope])
            ),
            "invalid schema",
        )
    invalid_record = {
        "schema_version": updater.SCHEMA_VERSION,
        "previous_entry_hash": None,
        "record": [],
        "entry_hash": "bad",
    }
    assert_loop_error(
        updater,
        lambda: updater._validate_ledger_entries([invalid_record]),
        "JSON object",
    )

    bad_sha_record = loop_record(updater)
    bad_sha_record["source"]["main_sha"] = "not-a-sha"
    assert_loop_error(
        updater,
        lambda: updater._validate_ledger_entries(
            [updater._ledger_entry(bad_sha_record, None)]
        ),
        "lowercase hexadecimal",
    )

    first = loop_record(updater)
    second = loop_record(
        updater,
        sha="c" * 40,
        first_parent_sha="f" * 40,
        pr_number=121,
    )
    first_entry = updater._ledger_entry(first, None)
    second_entry = updater._ledger_entry(second, first_entry["entry_hash"])
    assert_loop_error(
        updater,
        lambda: updater._validate_ledger_entries([first_entry, second_entry]),
        "first-parent chain",
    )


def test_stale_authorization_rule_examples_are_rejected() -> None:
    """Independent fixtures cover each required stale-authority family."""
    gate = load_module(
        "stale_authorization_docs_rules",
        "scripts/check_stale_authorization_docs.py",
    )
    fixtures = {
        "NON_CANONICAL_API_PREFIX": "POST /v1/projects",
        "LEGACY_ADMIN_PROJECT_MANAGER_AUTHORITY": "An admin or project_manager approves.",
        "LEGACY_ROLE_HELPER": "Call require_any_role for this route.",
        "TRUSTED_ROLE_CLAIM_AUTHORITY": "Routes use trusted role claims.",
        "CURRENT_TOKEN_ROLE_AUTHORITY": "Require the role in the current verified token.",
        "TOKEN_CARRIES_PRODUCT_ROLE": "The token also carries an authorized Workstream role.",
        "TYPED_PROFILE_AUTHORITY": 'ActorProfile(profile_type="worker") grants access.',
        "OBSOLETE_ROLE_ASSIGNMENT_MODEL": "Persist a WorkstreamRoleAssignment.",
        "OPERATOR_NOT_A_ROLE": "Operator is not a separate permission role.",
        "BROAD_ADMIN_OVERRIDE": "An admin can override a checker failure.",
        "LEGACY_ADMIN_HEADING": "### Admin",
        "LEGACY_ROLE_MATRIX": "| Admin | Project Manager | Finance | Auditor |",
        "ROLE_NAME_APPROVAL_PROVENANCE": '"approved_by_role": "project_manager"',
        "GENERIC_ADMIN_PRODUCT_AUTHORITY": "An admin can create projects.",
        "TOKEN_ROLE_PRODUCT_AUTHORITY": "A token role grants project access.",
        "NAMED_ROLE_TOKEN_AUTHORITY": "A project_manager token may approve this request.",
        "TYPED_PROFILE_PRODUCT_AUTHORITY": (
            "ActorProfile with type worker authorizes task claim."
        ),
        "HUMAN_WORKER_VOCABULARY": "## Flow 3: Worker Submits Work",
        "HUMAN_WORKER_IDENTIFIER": "worker_claim_status: fixed",
        "TECHNICAL_WORKER_HUMAN_AUTHORITY": (
            "The checker worker submits a contributor packet."
        ),
        "ACCESS_ADMIN_CATALOG_ADMINISTRATION": (
            "Access Administrator manages the permission catalog."
        ),
        "OPERATOR_CONTRIBUTION_POLICY_AUTHORITY": (
            "Operator reconciles contribution policy and compensation-adapter binding."
        ),
        "OPERATOR_COMPENSATION_MUTATION": (
            "Operator reconciles contribution records and compensation awards."
        ),
    }
    for code, sample in fixtures.items():
        failures = gate.scan_text("docs/new_active_doc.md", sample)
        assert any(failure.endswith(code) for failure in failures), (code, failures)

    unambiguous_canonical_statements = (
        "Product authority comes only from local Workstream grants.",
        "Bearer-token role metadata is identity provenance only.",
        "Typed workflow profiles are eligibility metadata only.",
        "An Access Administrator may grant administrative roles.",
        "AUTH owns the closed permission/action catalog and action availability.",
        "Operator invokes an exact registered recovery action; WS-CON mutates state.",
    )
    for sample in unambiguous_canonical_statements:
        assert gate.scan_text("docs/new_active_doc.md", sample) == [], sample

    fail_closed_authority_shapes = (
        "No current token role grants Workstream authority.",
        "Roles from the bearer token do not permit this request.",
        "ActorProfile with type worker does not authorize task claim.",
        "A token role grants project access, but email does not.",
        "A token role grants project access, not a typed profile.",
        (
            "ActorProfile with type worker authorizes task claim, but does not "
            "authorize review."
        ),
        "A token role, not email, grants project access.",
        "A token role does not merely provide context; it grants project access.",
        "ActorProfile with type worker, not reviewer, authorizes task claim.",
        "A token role does not grant profile access but authorizes project access.",
        (
            "ActorProfile with type worker does not authorize read access but "
            "permits task claim."
        ),
        (
            "A worker role from the token does not allow profile reads but may "
            "approve projects."
        ),
        "A token role does not record email but grants project access.",
        "A worker token does not carry profile metadata but authorizes task claim.",
        "ActorProfile with type worker does not store secrets but permits task claim.",
    )
    for sample in fail_closed_authority_shapes:
        assert gate.scan_text("docs/new_active_doc.md", sample), sample

    technical_worker_statements = (
        "The Celery worker runs project setup jobs.",
        "Checker execution uses a durable worker boundary.",
        "The setup worker reloads current authority before commit.",
        "The Celery worker identity is recorded for audit.",
        "The checker worker writes results.",
        "The setup worker resumes a failed job.",
        "The system worker completed reconciliation.",
        "The Celery worker submission is retried.",
        "The checker worker claim status is internal.",
        "Celery workers submit jobs.",
        "Celery worker_id identifies the background process.",
        "The checker worker_id is included in internal telemetry.",
        "See backend/app/workers/tasks.py.",
        "See app/workers/tasks.py.",
        "coverage report --include='app/workers/*' --precision=2 --fail-under=90",
        "ruff check app/workers/reviews.py",
        "review_lifecycle_live_drill.py --start-api-worker-beat --require-workers",
    )
    for sample in technical_worker_statements:
        assert gate.scan_text("docs/new_active_doc.md", sample) == [], sample

    human_worker_statements = (
        "A qualified worker claims the task.",
        "The worker opens an assigned task.",
        "Maximum active tasks per worker.",
        "Worker attestation is required.",
        "A worker submits the packet.",
        "Workers submit packets.",
        "A worker can claim a task.",
        "Persist worker_id on the assignment.",
        "POST /api/v1/workers/me/profile",
        "Celery schedules background jobs; a worker submits the packet.",
        "Celery is configured here; workers submit task packets.",
        "Celery is installed; a worker submits human work.",
        "Celery supports queues, but human workers submit tasks.",
        "Human workers use Celery.",
        "The Celery worker claims a human task using submitter authority.",
        ("The system worker receives a reviewer grant and records a review decision."),
        "The setup worker is a human product role.",
        "The system worker has a reviewer grant.",
        "The Celery worker may review a contributor submission.",
        "The checker worker is a Contributor.",
        "The setup worker uses submitter authority.",
        "The background worker approves project work.",
        "The Celery worker approves a project guide.",
        "The system worker reviews the submission.",
        "The checker worker grants itself project access.",
        "The setup worker manages contributor grants.",
        "The background worker creates a project.",
        "The system worker records a review decision.",
        "The checker worker issues a submitter grant.",
        "The setup worker revokes a reviewer grant.",
        "The Celery worker accepts the submission.",
        "The background worker rejects project work.",
        "The checker worker requests revision.",
        "review_lifecycle_live_drill.py --start-api-worker-beat-extra",
        "review_lifecycle_live_drill.py --require-workers-extra",
        "maliciousapp/workers/reviews.py",
        "maliciousapp.workers.reviews",
    )
    for sample in human_worker_statements:
        assert gate.scan_text("docs/new_active_doc.md", sample), sample


def test_feature_owned_authorization_activation_is_rejected() -> None:
    """Current AUTH/ART/REV contracts cannot assign activation to features."""
    gate = load_module(
        "activation_custody_contract_rules",
        "scripts/check_stale_authorization_docs.py",
    )
    stale_statements = (
        "Actions remain non-executable until their owning chunks activate them.",
        "Later owner chunks activate catalogue rows in typed code.",
        "An owning cutover chunk activates an action after behavior proof.",
        "Planned metadata is separate from later feature activation blueprints.",
        "Artifact service actions are activated by their owning WS-ART chunks.",
        "Each owning WS-REV chunk activates its review action.",
        "The WS-ART feature chunk owns the actions it activates.",
        "| Owning WS-ART chunk | Actions activated by that chunk |",
        "This is the owning WS-ART activation blueprint.",
        "The paired owning feature activates each action.",
        "Runtime activation remain with the listed owner.",
        "Route-owning chunks may promote an action to active after tests pass.",
    )
    for statement in stale_statements:
        failures = gate.scan_activation_custody_text("contract.md", statement)
        assert failures == ["contract.md:1: FEATURE_OWNED_AUTH_ACTIVATION"], statement

    planning_activation_statements = (
        "AUTH activates artifact actions under WS-XINT-001.",
        "WS-XINT-001 is the AUTH activation custodian.",
    )
    for statement in planning_activation_statements:
        failures = gate.scan_activation_custody_text("contract.md", statement)
        assert failures == ["contract.md:1: PLANNING_INITIATIVE_AUTH_ACTIVATION"], (
            statement
        )

    canonical_statements = (
        "AUTH activates the action after hidden ART behavior merges.",
        "ART activates API-startup scratch cleanup.",
        "This chunk neither activates its artifact action nor grants provider access.",
        "The feature owner supplies hidden behavior while AUTH owns availability.",
    )
    for statement in canonical_statements:
        assert gate.scan_activation_custody_text("contract.md", statement) == []


def test_activation_custody_discovery_includes_canonical_handoffs() -> None:
    """The fail-closed scan covers every canonical WS-XINT handoff."""
    gate = load_module(
        "activation_custody_contract_discovery",
        "scripts/check_stale_authorization_docs.py",
    )
    required = {
        "ART_REV_HANDOFF.md",
        "AUTH_ART_HANDOFF.md",
        "AUTH_ROLE_SERVICE_HANDOFF.md",
        "AUTH_REV_HANDOFF.md",
        "DISCOVERY.md",
        "INTENT.md",
        "REV_CON_HANDOFF.md",
        "chunks/WS-XINT-001-PLAN-boundary-reconciliation.md",
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        initiative = (
            root
            / ".agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation"
        )
        for relative_path in required | {"reviews/closed.md"}:
            path = initiative / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("current contract\n", encoding="utf-8")

        con_contract = (
            root
            / ".agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary"
            / "PLAN.md"
        )
        con_contract.parent.mkdir(parents=True, exist_ok=True)
        con_text = "Later owner chunks activate catalogue rows in typed code.\n"
        con_contract.write_text(con_text, encoding="utf-8")

        public_contract = root / "docs/review_current_contract.md"
        public_contract.parent.mkdir(parents=True, exist_ok=True)
        public_text = "The paired owning feature activates each action.\n"
        public_contract.write_text(public_text, encoding="utf-8")

        policy_contract = root / ".agent-loop/policies/security-boundaries.md"
        policy_contract.parent.mkdir(parents=True, exist_ok=True)
        policy_text = "Later owner chunks activate catalogue rows in typed code.\n"
        policy_contract.write_text(policy_text, encoding="utf-8")

        intent_contract = initiative / "INTENT.md"
        intent_text = "The paired owning feature activates each action.\n"
        intent_contract.write_text(intent_text, encoding="utf-8")

        historical_contracts = {root / path for path in gate.HISTORICAL_PATHS}
        for historical_contract in historical_contracts:
            historical_contract.parent.mkdir(parents=True, exist_ok=True)
            historical_contract.write_text(
                "The paired owning feature activates each action.\n",
                encoding="utf-8",
            )

        all_discovered = gate.discover_activation_custody_documents(root)
        discovered = {
            path.relative_to(initiative).as_posix()
            for path in all_discovered
            if path.is_relative_to(initiative)
        }

    assert required <= discovered
    assert "reviews/closed.md" not in discovered
    assert con_contract in all_discovered
    assert public_contract in all_discovered
    assert policy_contract in all_discovered
    assert intent_contract in all_discovered
    assert historical_contracts.isdisjoint(all_discovered)
    assert gate.scan_activation_custody_text(
        con_contract.relative_to(root).as_posix(),
        con_text,
    ) == [
        ".agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/"
        "PLAN.md:1: FEATURE_OWNED_AUTH_ACTIVATION"
    ]
    assert gate.scan_activation_custody_text(
        public_contract.relative_to(root).as_posix(),
        public_text,
    ) == ["docs/review_current_contract.md:1: FEATURE_OWNED_AUTH_ACTIVATION"]
    assert gate.scan_activation_custody_text(
        policy_contract.relative_to(root).as_posix(),
        policy_text,
    ) == [
        ".agent-loop/policies/security-boundaries.md:1: FEATURE_OWNED_AUTH_ACTIVATION"
    ]
    assert gate.scan_activation_custody_text(
        intent_contract.relative_to(root).as_posix(),
        intent_text,
    ) == [
        ".agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/"
        "INTENT.md:1: FEATURE_OWNED_AUTH_ACTIVATION"
    ]


def test_auth_spec_orders_service_admission_before_project_roles() -> None:
    """AUTH-09A through both 09D children and 09E precede project grants."""
    spec = Path("docs/spec_authorization_service.md").read_text(encoding="utf-8")
    order = spec.split("## Migration And Compatibility", maxsplit=1)[1].split(
        "## Error And Privacy Contract",
        maxsplit=1,
    )[0]
    chunk_ids = (
        "WS-AUTH-001-09A",
        "WS-AUTH-001-09B",
        "WS-AUTH-001-09C",
        "WS-AUTH-001-09D-A",
        "WS-AUTH-001-09D-B",
        "WS-AUTH-001-09E",
        "WS-AUTH-001-10",
    )
    positions = [order.index(f"`{chunk_id}`:") for chunk_id in chunk_ids]
    assert positions == sorted(positions)
    assert "without human grant\n    evaluation or feature action activation" in order


def test_parallel_initiative_status_matches_trusted_main() -> None:
    """Auth history and authored ART planning remain internally consistent."""
    auth_map = Path(
        ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/"
        "CHUNK_MAP.md"
    ).read_text(encoding="utf-8")
    auth_status = Path(
        ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md"
    ).read_text(encoding="utf-8")
    artifact_map = Path(
        ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md"
    ).read_text(encoding="utf-8")
    artifact_status = Path(
        ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/STATUS.md"
    ).read_text(encoding="utf-8")
    artifact_contract = Path(
        ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/"
        "WS-ART-001-02C2-verification-publication-fencing.md"
    ).read_text(encoding="utf-8")
    work_queue = Path(".agent-loop/WORK_QUEUE.md").read_text(encoding="utf-8")
    loop_state = Path(".agent-loop/LOOP_STATE.md").read_text(encoding="utf-8")
    contribution_guide = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    loop_guide = Path(".agent-loop/README.md").read_text(encoding="utf-8")

    # Authored main snapshots below remain historical discovery input. Live
    # active/cancel state is read only from independently verified signed
    # automation, so ART assertions use its initiative status/map rather than
    # pretending copied root projections are current authority.
    canonical_warning = (
        "Only independently verified signed automation state is canonical authority"
    )
    assert canonical_warning in " ".join(contribution_guide.split())
    assert canonical_warning in " ".join(loop_guide.split())

    assert "Merged through PR #131 as `aa0fdcd`" in auth_map
    assert "Merged through PR #143 as `053242b`" in auth_map
    assert "Merged through PR #146 as `0ffdabf`" in auth_map
    assert "| `WS-AUTH-001-08` | Merged |" in auth_status
    assert "| `WS-AUTH-001-XINT` | Merged |" in auth_status
    assert "| `WS-AUTH-001-09A` | Merged |" in auth_status
    assert "| `WS-AUTH-001-09B` | Merged |" in auth_status
    assert "| `WS-AUTH-001-09C` | Merged |" in auth_status
    assert "| `WS-AUTH-001-09D` | Split |" in auth_status
    assert "Merged through PR #148 as `99ae4c9`" in auth_map
    assert "| `WS-AUTH-001-09D-A` | Merged |" in auth_status
    assert "| `WS-AUTH-001-09D-B` | Merged |" in auth_status
    assert "Active implementation chunk\n\nNone." in auth_status
    assert "Active implementation chunk\n\n`WS-AUTH-001-CONTRIBUTOR-FOUNDATION`" not in auth_status
    assert "Current review branch\n\nNone." in auth_status
    assert "PR #148 is open" not in auth_status
    stale_auth_09d_state = (
        "Only 09D-A implementation is active",
        "Only 09D-A may proceed",
        "AUTH-09D-A's repaired contract passed required L1",
        "bounded implementation is active",
        "Bounded implementation is the current gate",
    )
    for stale_text in stale_auth_09d_state:
        assert stale_text not in auth_status
        assert stale_text not in auth_map
        assert stale_text not in work_queue
    assert (
        "Contributor Fields And Canonical-Human Lineage | L1 | Merged through PR #153 "
        "as `8d5eb15` on 2026-07-19" in work_queue
    )
    assert "Active implementation chunk: `WS-AUTH-001-CONTRIBUTOR-FOUNDATION`" not in loop_state
    assert "Merged through PR #157 as `42a89b2d`" in work_queue
    assert "ActionIds, with 17 active actions" in loop_state
    assert "candidate total of 17" not in loop_state
    assert "with 12 active actions" not in loop_state
    assert "five 09D-A/09D-B lifecycle actions" not in loop_state
    assert (
        "| `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` | Contributor Fields And "
        "Canonical-Human Lineage | L1 | Merged through PR #153 as `8d5eb15b`" in auth_map
    )
    assert "PR/external checks pending" not in auth_map
    assert "PR/external checks are current" not in auth_status
    assert "| `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` | Merged |" in auth_status
    assert (
        "| `WS-AUTH-001-09E` | Fixed Service Runtime Admission | L1 | "
        "Merged through PR #157 as `42a89b2d`"
        in auth_map
    )
    assert "| `WS-AUTH-001-09E` | Merged |" in auth_status
    assert (
        "| `WS-AUTH-001-09E` | Fixed Service Runtime Admission | L1 | "
        "Merged through PR #157 as `42a89b2d`"
        in work_queue
    )
    assert "No feature action or service call site becomes active" in " ".join(
        loop_state.split()
    )
    assert "Merged through PR #129 as `9a04434`" in artifact_map
    assert "Merged through PR #141 as `a10d901`" in artifact_map
    assert "Merged through PR #151 as `1b5422fc`" in artifact_map
    assert "Merged through PR #154 as `44f2467c`" in artifact_map
    assert "Merged through PR #159 as `bc5e6a42`" in artifact_map
    assert "Merged through PR #174 as `92b8a7aa`" in artifact_map
    assert "Merged through PR #177 as `93c14181`" in artifact_map
    assert (
        "AUTH's owner reconciliation merged through PR #140 as\n"
        "`d541521`" in artifact_status
    )
    assert "`WS-ART-001-03` received a signed implementation start" in artifact_status
    assert "recorded `stopped_after_cancel`" in artifact_status
    assert "The planning merge starts no successor" in artifact_status
    assert (
        "| `WS-AUTH-001-09C` | Actor And Identity-Link Administration Reads | L1 | "
        "Merged through PR #146 as `0ffdabf`" in work_queue
    )
    assert (
        "| `WS-AUTH-001-ART-CUSTODY` | ART Activation Custody Transfer | L1 | "
        "Merged through PR #158 as `be2a79a2`" in work_queue
    )
    assert "all 25 ART actions remain planned" in work_queue
    assert (
        "| `WS-AUTH-001-REV-CUSTODY` | REV Activation Custody Transfer | L1 | "
        "Merged through PR #160 as `fe0e4492`" in work_queue
    )
    assert "all 19 REV actions remain planned" in work_queue
    assert (
        "| `WS-AUTH-001-PREP` | Prepared Mutation Authorization Protocol | L1 | "
        "Merged through PR #162 as `c559d556`" in work_queue
    )
    assert "no feature consumer or activation" in work_queue
    assert "| `WS-ART-001-PLAN2` |" in artifact_map
    assert "Planning-only successor proposed after cancellation" in artifact_map
    assert "`WS-ART-001-03A` is the only immediate ART" in artifact_status


def test_stale_authorization_discovery_includes_new_untracked_docs() -> None:
    """A new active doc fails without being added to a hardcoded corpus."""
    gate = load_module(
        "stale_authorization_docs_discovery",
        "scripts/check_stale_authorization_docs.py",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / "docs").mkdir()
        initiative = root / ".agent-loop/initiatives/WS-CON-001-example"
        initiative.mkdir(parents=True)
        policy = root / ".agent-loop/policies/security-boundaries.md"
        policy.parent.mkdir(parents=True)
        active = root / "docs" / "new_active_doc.md"
        diagram = root / "docs" / "new_active_diagram.puml"
        initiative_contract = initiative / "PLAN.md"
        initiative_state = initiative / "STATE.json"
        active.write_text("POST /v1/projects\n", encoding="utf-8")
        diagram.write_text(
            "Workstream --> API : POST /api/v1/projects\n", encoding="utf-8"
        )
        initiative_contract.write_text("current contract\n", encoding="utf-8")
        initiative_state.write_text('{"status": "current"}\n', encoding="utf-8")
        policy.write_text("current policy\n", encoding="utf-8")
        assert active in gate.discover_documents(root)
        assert diagram in gate.discover_documents(root)
        assert initiative_contract in gate.discover_documents(root)
        assert initiative_state in gate.discover_documents(root)
        assert policy in gate.discover_documents(root)
        assert gate.scan(root) == ["docs/new_active_doc.md:1: NON_CANONICAL_API_PREFIX"]

        active.write_text("POST /api/v1/projects\n", encoding="utf-8")
        assert gate.scan(root) == []

        active.write_text(
            "The worker role from the verified token authorizes task claims.\n"
            "ActorProfile with type worker authorizes task claim.\n",
            encoding="utf-8",
        )
        failures = gate.scan(root)
        assert any(item.endswith("TOKEN_ROLE_PRODUCT_AUTHORITY") for item in failures)
        assert any(
            item.endswith("TYPED_PROFILE_PRODUCT_AUTHORITY") for item in failures
        )

        active.write_text("POST /api/v1/projects\n", encoding="utf-8")
        diagram.write_text("Workstream --> API : POST /v1/projects\n", encoding="utf-8")
        assert gate.scan(root) == [
            "docs/new_active_diagram.puml:1: NON_CANONICAL_API_PREFIX"
        ]

        diagram.write_text(
            "Workstream --> API : POST /api/v1/projects\n", encoding="utf-8"
        )
        initiative_contract.write_text("POST /v1/projects\n", encoding="utf-8")
        policy.write_text(
            "A token also carries an authorized Workstream role.\n",
            encoding="utf-8",
        )
        assert gate.scan(root) == [
            ".agent-loop/initiatives/WS-CON-001-example/PLAN.md:1: "
            "NON_CANONICAL_API_PREFIX",
            ".agent-loop/policies/security-boundaries.md:1: TOKEN_CARRIES_PRODUCT_ROLE",
        ]


def test_stale_authorization_precedence_exemption_is_line_scoped() -> None:
    """The active archive marker exempts one line, not its entire document."""
    gate = load_module(
        "stale_authorization_docs_precedence",
        "scripts/check_stale_authorization_docs.py",
    )
    marker = "archival input uses `/v1`. WS-AUTH-001 takes precedence over the current"
    assert gate.scan_text("docs/reference_specs/README.md", marker) == []
    failures = gate.scan_text(
        "docs/reference_specs/README.md",
        marker + "\nClients call POST /v1/projects.\n",
    )
    assert failures == ["docs/reference_specs/README.md:2: NON_CANONICAL_API_PREFIX"]


def test_stale_authorization_initiative_ratchet_is_position_scoped() -> None:
    """A copied stale line fails even when identical history remains unchanged."""
    gate = load_module(
        "stale_authorization_docs_initiative_baseline",
        "scripts/check_stale_authorization_docs.py",
    )
    stale_line = "POST /v1/projects"
    text = f"{stale_line}\n{stale_line}\n"

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        relative_path = ".agent-loop/initiatives/example/PLAN.md"
        contract = root / relative_path
        contract.parent.mkdir(parents=True)
        contract.write_text(f"{stale_line}\n", encoding="utf-8")
        subprocess.run(["git", "add", relative_path], cwd=root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-qm",
                "baseline",
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
            cwd=root,
            check=True,
        )
        contract.write_text(text, encoding="utf-8")
        changed_lines = gate.initiative_changed_line_numbers(root, relative_path)

    assert changed_lines == frozenset({2})

    assert gate.scan_text(
        ".agent-loop/initiatives/example/PLAN.md",
        text,
        enforced_line_numbers=changed_lines,
    ) == [".agent-loop/initiatives/example/PLAN.md:2: NON_CANONICAL_API_PREFIX"]

    multiline_text = "ActorProfile(\nprofile_type"
    assert gate.scan_text(
        ".agent-loop/initiatives/example/PLAN.md",
        multiline_text,
        enforced_line_numbers=frozenset({2}),
    ) == [".agent-loop/initiatives/example/PLAN.md:1: TYPED_PROFILE_AUTHORITY"]

    assert gate.scan_text(
        ".agent-loop/initiatives/example/PLAN.md",
        "A token role grants project access.",
        enforced_line_numbers=frozenset(),
    ) == [".agent-loop/initiatives/example/PLAN.md:1: TOKEN_ROLE_PRODUCT_AUTHORITY"]
    assert (
        gate.scan_text(
            ".agent-loop/initiatives/example/PLAN.md",
            "A worker submits the packet.",
            enforced_line_numbers=frozenset(),
        )
        == []
    )


def test_stale_authorization_full_initiative_rules_ignore_changed_line_filter() -> None:
    """Every authority-bearing initiative rule scans the complete document."""
    gate = load_module(
        "stale_authorization_docs_full_initiative_rules",
        "scripts/check_stale_authorization_docs.py",
    )
    samples = {
        "ACCESS_ADMIN_CATALOG_ADMINISTRATION": (
            "Access Administrator manages the permission catalog."
        ),
        "CURRENT_TOKEN_ROLE_AUTHORITY": "role in the current verified token",
        "NAMED_ROLE_TOKEN_AUTHORITY": "admin token can approve this operation",
        "OBSOLETE_ROLE_ASSIGNMENT_MODEL": "WorkstreamRoleAssignment",
        "OPERATOR_COMPENSATION_MUTATION": ("Operator reconciles compensation awards."),
        "OPERATOR_CONTRIBUTION_POLICY_AUTHORITY": (
            "Operator publishes contribution policy."
        ),
        "TOKEN_CARRIES_PRODUCT_ROLE": (
            "token also carries an authorized Workstream role"
        ),
        "TOKEN_ROLE_PRODUCT_AUTHORITY": "A token role grants project access.",
        "TRUSTED_ROLE_CLAIM_AUTHORITY": "trusted role claims",
        "TYPED_PROFILE_AUTHORITY": "ActorProfile(profile_type",
        "TYPED_PROFILE_PRODUCT_AUTHORITY": (
            "ActorProfile profile_type grants project access"
        ),
    }

    assert set(samples) == gate.FULL_INITIATIVE_RULE_CODES
    for code, sample in samples.items():
        failures = gate.scan_text(
            ".agent-loop/initiatives/example/PLAN.md",
            sample,
            enforced_line_numbers=frozenset(),
        )
        assert any(failure.endswith(f": {code}") for failure in failures), code


def test_stale_authorization_history_allowlist_is_exact() -> None:
    """Only reviewed exact history paths bypass active-document scanning."""
    gate = load_module(
        "stale_authorization_docs_history",
        "scripts/check_stale_authorization_docs.py",
    )
    assert "docs/spec_chunk_3_project_guide_foundation.md" in gate.HISTORICAL_PATHS
    assert (
        ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-06-canonical-actor-profile.md"
        in gate.HISTORICAL_PATHS
    )
    assert (
        ".agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-11-actor-identity-profile-registry.md"
        in gate.HISTORICAL_PATHS
    )
    assert "docs/review_architecture_review.md" not in gate.HISTORICAL_PATHS
    assert "docs/spec_chunk_999_future.md" not in gate.HISTORICAL_PATHS


def test_stale_review_contract_rule_inventory_is_complete() -> None:
    """Every prohibited review-contract category has an executable fixture."""
    gate = load_module(
        "stale_review_contract_rule_inventory",
        "scripts/check_stale_review_contracts.py",
    )
    samples = {
        "NON_CANONICAL_API_PREFIX": "POST /v1/reviews/decision",
        "ACTIVE_FLOW_NODE_PROVIDER": "Flow Node is the production provider.",
        "FULL_REVIEWER_BACKLOG": "Reviewer browses the complete review queue.",
        "LEGACY_REVIEW_SEVERITY": "ReviewFinding uses high-severity.",
        "LEGACY_FINDING_CLOSURE": "reviewer_closure_status: closed_fixed",
        "POLICY_SELECTED_LATEST_REBASE": (
            "Revision policy decides whether to use the latest active context."
        ),
        "REVIEWER_REBASE": "The reviewer performs a rebase before judgment.",
        "SYNTHETIC_REJECT": "A revision deadline sets the task to rejected.",
        "DIRECT_ACCEPT_TO_SUBMITTER_CONTRIBUTION": (
            "Acceptance creates the accepted_submission contribution."
        ),
        "AUTO_REJECT_REVISION_LIMIT": "auto_reject_after_limit: true",
        "REJECT_REQUIRES_FINDING": "Reject requires one finding.",
        "REVIEW_REPUTATION_SIDE_EFFECT": ("The review creates a reputation event."),
        "ACTIVE_REPUTATION_LEDGER": "## Day 17: Reputation Ledger",
        "UNCONDITIONAL_REVIEW_PAYMENT": ("Accepted work must have payment status."),
        "ADJUDICATION_ACTIVATION_PROMISE": (
            "Adjudication remains unavailable until enabled."
        ),
        "BROAD_REVIEW_BYPASS": ("An admin can override the review decision."),
        "HUMAN_PRE_REVIEW_ADMISSION": (
            "### Pre Review Gate\n\nOptional reviewer-simulation before review."
        ),
        "DISPUTED_REJECT_PATH": "Reviewer lead if disputed.",
    }
    assert set(samples) == {rule.code for rule in gate.RULES}
    for code, sample in samples.items():
        failures = gate.scan_text("docs/spec_review_lifecycle.md", sample)
        assert any(failure.endswith(f": {code}") for failure in failures), code

    assert not gate.scan_text(
        "docs/spec_review_lifecycle.md",
        "FinalAcceptance alone sources the submitter contribution.",
    )
    assert not gate.scan_text(
        "docs/spec_review_lifecycle.md",
        "No guide rebase occurs during review.",
    )
    assert not gate.scan_text(
        "docs/glossary.md",
        "## Reputation Ledger\n\nA future offline evidence concept.",
    )
    assert not gate.scan_text(
        "docs/operations_payment_reputation.md",
        "After the reviewer operation, Review(accept) first creates "
        "FinalAcceptance, then applies accepted task effects.",
    )
    assert not gate.scan_text(
        "docs/template_project_guide.md",
        "RevisionPolicyInput.auto_reject_after_limit: false",
    )
    assert not gate.scan_text(
        "docs/template_project_guide.md",
        '{"auto_reject_after_limit": false}',
    )
    for sample in (
        '{"auto_reject_after_limit": true}',
        "auto_reject_after_limit = 1",
        "`auto_reject_after_limit`: `yes`",
    ):
        failures = gate.scan_text("docs/template_project_guide.md", sample)
        assert any(
            failure.endswith(": AUTO_REJECT_REVISION_LIMIT") for failure in failures
        )

    adversarial_samples = {
        "NON_CANONICAL_API_PREFIX": (
            "The active production API is /v1/reviews, unlike the archival example."
        ),
        "DIRECT_ACCEPT_TO_SUBMITTER_CONTRIBUTION": (
            "Accept creates accepted_submission directly; FinalAcceptance is ignored."
        ),
        "REVIEWER_REBASE": (
            "The reviewer should not delay and performs a rebase before judgment."
        ),
        "LEGACY_REVIEW_SEVERITY": "ReviewFinding severity: high",
        "LEGACY_FINDING_CLOSURE": "resolution: closed / still open",
        "AUTO_REJECT_REVISION_LIMIT": (
            "The task automatically rejects after the revision limit."
        ),
        "REVIEW_REPUTATION_SIDE_EFFECT": (
            "Accepted and rejected review reputation events are recorded."
        ),
        "UNCONDITIONAL_REVIEW_PAYMENT": ("No accepted task missing payment/evidence."),
    }
    for code, sample in adversarial_samples.items():
        failures = gate.scan_text("docs/spec_review_lifecycle.md", sample)
        assert any(failure.endswith(f": {code}") for failure in failures), code

    for sample in (
        "Accept creates FinalAcceptance only afterward and directly creates accepted_submission first.",
        "Acceptance creates a FinalAcceptance audit row but directly creates the submitter contribution from Review.decision.",
    ):
        failures = gate.scan_text("docs/spec_review_lifecycle.md", sample)
        assert any(
            failure.endswith(": DIRECT_ACCEPT_TO_SUBMITTER_CONTRIBUTION")
            for failure in failures
        )

    for sample in (
        "Reviewer never rebases old context, then rebases production context.",
        "The reviewer must not perform a rebase in tests but performs a rebase in production.",
    ):
        failures = gate.scan_text("docs/spec_review_lifecycle.md", sample)
        assert any(failure.endswith(": REVIEWER_REBASE") for failure in failures)


def test_active_review_workflows_preserve_canonical_transaction_order() -> None:
    """Operational workflows retain the normative accept transaction order."""
    operator = (ROOT / "docs/operations_operator_workflow.md").read_text(
        encoding="utf-8"
    )
    operator_accept = operator.split("## Acceptance Workflow", maxsplit=1)[1].split(
        "## Rejection Workflow", maxsplit=1
    )[0]
    operator_markers = (
        "REV appends the immutable Review",
        "CON records reviewer `completed_review`",
        "REV records one internal FinalAcceptance",
        "REV moves the task to ACCEPTED",
        "CON records submitter `accepted_submission`",
    )
    operator_positions = [operator_accept.index(item) for item in operator_markers]
    assert operator_positions == sorted(operator_positions)

    flows = (ROOT / "docs/product_first_user_flows.md").read_text(encoding="utf-8")
    accepted_flow = flows.split(
        "## Flow 7: Accepted Work, FinalAcceptance, And Submitter Contribution",
        maxsplit=1,
    )[1]
    flow_markers = (
        "reviewer `completed_review` contribution",
        "REV creates immutable FinalAcceptance",
        "Task enters `ACCEPTED`",
        "CON submitter operation creates `accepted_submission`",
    )
    flow_positions = [accepted_flow.index(item) for item in flow_markers]
    assert flow_positions == sorted(flow_positions)

    payment = (ROOT / "docs/operations_payment_reputation.md").read_text(
        encoding="utf-8"
    )
    payment_principle = payment.split("## Compensation Principle", maxsplit=1)[1].split(
        "## Compensation Status Projection", maxsplit=1
    )[0]
    payment_markers = (
        "mandatory CON reviewer operation",
        "creates REV-owned FinalAcceptance",
        "sets the Task\nto `accepted` and the TaskAssignment to `completed`",
        "runs the CON submitter\noperation",
    )
    payment_positions = [payment_principle.index(item) for item in payment_markers]
    assert payment_positions == sorted(payment_positions)


def test_checker_admission_and_reject_sampling_remain_nonhuman_and_nonmutating() -> (
    None
):
    """Submitted-work admission and terminal sampling cannot become hidden review."""
    queue_policy = (ROOT / "docs/operations_queue_policy.md").read_text(
        encoding="utf-8"
    )
    admission = queue_policy.split("### Checker Admission Gate", maxsplit=1)[1].split(
        "### Review Pending", maxsplit=1
    )[0]
    assert "Mandatory automated admission" in admission
    assert "durable, final, current `CheckerRun` outcome of `allow_review`" in admission
    assert "human judgment begins only after admission" in admission
    assert "reviewer-simulation" not in admission
    assert "reviewer lead" not in admission
    assert "quality lead" not in admission

    flows = (ROOT / "docs/product_first_user_flows.md").read_text(encoding="utf-8")
    checker_flow = flows.split("## Flow 4: Automated Checks Run", maxsplit=1)[1].split(
        "## Flow 5: Reviewer Reviews Submission", maxsplit=1
    )[0]
    assert (
        "durable, final, current `CheckerRun` outcome of `allow_review`" in checker_flow
    )
    assert "exact immutable Submission with verified binding facts" in checker_flow
    assert "`evaluation_pending`" in checker_flow
    assert "`task_setup_blocked`" in checker_flow
    assert "Critical- or high-severity failure blocks human review" not in checker_flow

    review_flow = flows.split("## Flow 5: Reviewer Reviews Submission", maxsplit=1)[
        1
    ].split("## Flow 6: Human Review Revision Replay", maxsplit=1)[0]
    assert (
        "exact durable, final, current\n  `allow_review` CheckerRun admission"
        in review_flow
    )
    assert "verified binding facts" in review_flow

    revision_flow = flows.split("## Flow 6: Human Review Revision Replay", maxsplit=1)[
        1
    ].split(
        "## Flow 7: Accepted Work, FinalAcceptance, And Submitter Contribution",
        maxsplit=1,
    )[0]
    assert "`Review(needs_revision)`" in revision_flow
    assert "Checker-caused remediation is separate" in revision_flow
    assert "retains `CheckerResult` lineage" in revision_flow
    checker_prohibitions = revision_flow.split("creates no ", maxsplit=1)[1].split(
        "and returns through", maxsplit=1
    )[0]
    assert "Review, ReviewFinding" in checker_prohibitions
    for prohibited_record in (
        "SubmissionFindingResponse",
        "FindingResolution",
        "reviewer contribution",
    ):
        assert prohibited_record in checker_prohibitions

    rejected = queue_policy.split("### Rejected", maxsplit=1)[1].split(
        "### Compensation Fulfillment Follow-Up", maxsplit=1
    )[0]
    assert "non-mutating quality sampling only" in rejected
    assert "cannot reopen, adjudicate, replace, or change" in rejected
    assert "if disputed" not in rejected


def test_stale_review_contract_classification_is_exact() -> None:
    """Only exact supplied archives and reviewed history bypass active scanning."""
    gate = load_module(
        "stale_review_contract_classification",
        "scripts/check_stale_review_contracts.py",
    )
    assert (
        gate.classification(
            "docs/reference_specs/WS-REV-001-review-lifecycle-specification.md"
        )
        == "archival"
    )
    assert (
        gate.classification(
            "docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md"
        )
        == "historical"
    )
    assert gate.classification("docs/reference_specs/WS-REV-001-copy.md") == (
        "unclassified"
    )
    assert gate.classification("docs/spec_review_lifecycle.md") == "active"
    assert gate.classification("docs/roadmap_status.md") == "active"
    assert (
        gate.classification("docs/operations_subagent_review_protocol.md")
        == "non_product_review"
    )


def test_stale_review_contract_scan_excludes_only_exact_archives() -> None:
    """Exact archives bypass rules and unknown reference documents fail closed."""
    gate = load_module(
        "stale_review_contract_archive_scan",
        "scripts/check_stale_review_contracts.py",
    )
    original_active = gate.ACTIVE_PATHS
    original_archival = gate.ARCHIVAL_PATHS
    original_git_lines = gate.git_lines
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "docs/reference_specs").mkdir(parents=True)
        (root / "docs/spec_review_lifecycle.md").write_text(
            "Canonical /api/v1 contract.\n", encoding="utf-8"
        )
        (root / "docs/reference_specs/archive.md").write_text(
            "POST /v1/reviews\n", encoding="utf-8"
        )
        (root / "docs/reference_specs/copy.md").write_text(
            "copied archive\n", encoding="utf-8"
        )

        def fake_git_lines(_root: Path, *args: str) -> list[str]:
            if args == ("ls-files",):
                return [
                    "docs/spec_review_lifecycle.md",
                    "docs/reference_specs/archive.md",
                    "docs/reference_specs/copy.md",
                ]
            if args == ("ls-files", "--others", "--exclude-standard"):
                return []
            raise AssertionError(args)

        gate.ACTIVE_PATHS = {"docs/spec_review_lifecycle.md"}
        gate.ARCHIVAL_PATHS = {"docs/reference_specs/archive.md"}
        gate.git_lines = fake_git_lines
        try:
            assert gate.scan(root) == [
                "docs/reference_specs/copy.md:0: UNCLASSIFIED_ACTIVE_DOCUMENT"
            ]
        finally:
            gate.ACTIVE_PATHS = original_active
            gate.ARCHIVAL_PATHS = original_archival
            gate.git_lines = original_git_lines


def test_stale_review_contract_discovery_includes_tracked_and_untracked() -> None:
    """Modified/staged and newly added documents are both discovered."""
    gate = load_module(
        "stale_review_contract_discovery",
        "scripts/check_stale_review_contracts.py",
    )
    original_git_lines = gate.git_lines
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "docs").mkdir()
        (root / "docs/spec_review_lifecycle.md").write_text(
            "active\n", encoding="utf-8"
        )
        (root / "docs/review_new.md").write_text("new\n", encoding="utf-8")

        def fake_git_lines(_root: Path, *args: str) -> list[str]:
            if args == ("ls-files",):
                return ["docs/spec_review_lifecycle.md"]
            if args == ("ls-files", "--others", "--exclude-standard"):
                return ["docs/review_new.md"]
            raise AssertionError(args)

        gate.git_lines = fake_git_lines
        try:
            assert {
                path.relative_to(root).as_posix() for path in gate.discover_paths(root)
            } == {"docs/spec_review_lifecycle.md", "docs/review_new.md"}
        finally:
            gate.git_lines = original_git_lines


def test_stale_review_contracts_run_fail_closed_in_agent_gates() -> None:
    """The active repository scanner is a mandatory Agent Gates test."""
    gate = load_module(
        "stale_review_contract_current_repository",
        "scripts/check_stale_review_contracts.py",
    )
    assert gate.scan(ROOT) == []


def test_agent_gates_runs_stale_authorization_docs_fail_closed() -> None:
    """The Agent Gates workflow must retain the authorization-doc scanner."""
    workflow = (ROOT / ".github/workflows/agent-gates.yml").read_text(encoding="utf-8")
    command = "run: python3 scripts/check_stale_authorization_docs.py"
    assert workflow.count(command) == 1
    assert "continue-on-error" not in workflow


def test_agent_gates_runs_stale_artifact_contracts_fail_closed() -> None:
    """The Agent Gates workflow must retain the artifact-contract scanner."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/agent-gates.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["agent-gates"]["steps"]
    scanner_steps = [
        step
        for step in steps
        if step.get("run") == "python3 scripts/check_stale_artifact_contracts.py"
    ]
    assert scanner_steps == [
        {
            "name": "Stale artifact contract check",
            "run": "python3 scripts/check_stale_artifact_contracts.py",
        }
    ]
    assert all("continue-on-error" not in step for step in steps)
    assert all(step.get("if") not in {False, "false", "${{ false }}"} for step in steps)


def test_agent_gate_dependencies_and_workflow_are_pinned() -> None:
    """The YAML parser dependency and its installation remain deterministic."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/agent-gates.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["agent-gates"]["steps"]
    assert any(
        step.get("uses")
        == "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
        and step.get("with", {}).get("python-version") == "3.12"
        for step in steps
    )
    assert (
        sum(
            step.get("run")
            == "python -m pip install --require-hashes -r scripts/agent-gate-requirements.txt"
            for step in steps
        )
        == 1
    )
    assert all("continue-on-error" not in step for step in steps)
    requirements = (ROOT / "scripts/agent-gate-requirements.txt").read_text(
        encoding="utf-8"
    )
    requirement_lines = requirements.splitlines()
    assert {line.split("==", 1)[0].lower() for line in requirement_lines} == {
        "coverage", "iniconfig", "packaging", "pluggy", "pygments", "pytest",
        "pytest-cov", "pyyaml",
    }
    assert all(" --hash=sha256:" in line for line in requirement_lines)
    assert all(len(line.rsplit("sha256:", 1)[1]) == 64 for line in requirement_lines)


def test_local_minio_compose_is_regression_protected() -> None:
    """Keep the repository-managed MinIO proof pinned and loopback-only."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    minio = compose["services"]["minio"]
    assert set(minio) == {
        "image",
        "command",
        "environment",
        "ports",
        "healthcheck",
        "volumes",
    }
    assert minio["image"] == MINIO_IMAGE
    assert minio["command"] == "server /data --address :9000"
    assert minio["environment"] == {
        "MINIO_ROOT_USER": "workstream-minio",
        "MINIO_ROOT_PASSWORD": "workstream-minio-secret-key",
    }
    assert minio["ports"] == ["127.0.0.1:9000:9000"]


def test_backend_coverage_thresholds_are_regression_protected() -> None:
    """Keep exact-custody semantic lanes and every coverage floor fail closed."""
    workflow_path = ROOT / ".github/workflows/backend.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    parsed_workflow = yaml.safe_load(workflow)
    assert parsed_workflow["name"] == "Backend"
    assert parsed_workflow["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in workflow
    assert "paths-ignore" not in workflow and "continue-on-error" not in workflow
    jobs = parsed_workflow["jobs"]
    assert set(jobs) == {"test"}

    postgres_image = (
        "public.ecr.aws/docker/library/postgres:16@sha256:"
        "33f923b05f64ca54ac4401c01126a6b92afe839a0aa0a52bc5aeb5cc958e5f20"
    )
    test_job = jobs["test"]
    assert set(test_job) == {
        "runs-on", "timeout-minutes", "services", "steps",
    }
    assert test_job["services"]["postgres"]["image"] == postgres_image
    steps = test_job["steps"]
    assert not any(
        step.get("name") == "Isolated database runner test"
        or "tests/test_isolated_database_runner.py" in str(step.get("run", ""))
        for step in steps
    )
    checkout = [step for step in steps if "actions/checkout@" in step.get("uses", "")]
    assert checkout == [{
        "uses": "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
        "with": {"persist-credentials": False, "fetch-depth": 0},
    }]
    identity = [step for step in steps if step.get("name") == "Bind exact checked-out tree"]
    assert len(identity) == 1
    assert '${tree_sha}' in str(identity[0]["run"])
    assert '${GITHUB_SHA}' in str(identity[0]["run"])
    identity_command = str(identity[0]["run"])
    assert identity_command.index('job_start_epoch="$(date +%s)"') < (
        identity_command.index('tree_sha="$(git rev-parse HEAD)"')
    )
    assert 'job_start_epoch=${job_start_epoch}' in identity_command

    install = [step for step in steps if step.get("name") == "Install backend and exact Ruff"]
    assert len(install) == 1
    assert "python -m pip install ruff==0.15.22" in str(install[0]["run"])
    assert 'test "$(ruff --version)" = "ruff 0.15.22"' in str(install[0]["run"])

    collect = [
        step for step in steps
        if step.get("name") == "Collect canonical semantic-lane inventory"
    ]
    assert len(collect) == 1
    assert "run_test_lanes.py" in str(collect[0]["run"])
    assert "--collect-only" in str(collect[0]["run"])
    assert ".ci/test-lanes/collect-summary.json" in str(collect[0]["run"])
    validators = [
        step for step in steps
        if "validate_test_lane_evidence.py" in str(step.get("run", ""))
    ]
    assert len(validators) == 2
    assert ".ci/test-lanes/collect-summary.json" in str(validators[0]["run"])
    assert ".ci/test-lanes/run-summary.json" in str(validators[1]["run"])

    minio_steps = [
        step for step in steps if step.get("name") == "Start real MinIO artifact provider"
    ]
    assert len(minio_steps) == 1
    assert "${MINIO_IMAGE}" in str(minio_steps[0]["run"])
    run_lane_steps = [
        step for step in steps if step.get("name") == "Execute four semantic lanes"
    ]
    assert len(run_lane_steps) == 1
    assert "run_test_lanes.py" in str(run_lane_steps[0]["run"])
    assert "--timeout-seconds 1200" in str(run_lane_steps[0]["run"])
    assert ".ci/test-lanes/run.exit" in str(run_lane_steps[0]["run"])
    assert "--cov-fail-under" not in str(run_lane_steps[0]["run"])
    require_success = [
        step for step in steps
        if step.get("name") == "Require semantic-lane execution success"
    ]
    assert len(require_success) == 1
    assert 'cat .ci/test-lanes/run.exit' in str(require_success[0]["run"])
    assert "if" not in require_success[0]
    assert steps.index(run_lane_steps[0]) < steps.index(require_success[0])
    assert run_lane_steps[0]["env"]["WORKSTREAM_TEST_ADMIN_DATABASE_URL"] == (
        "postgresql+asyncpg://workstream:workstream@localhost:5433/postgres"
    )
    lane_runner = (ROOT / "backend/scripts/run_test_lanes.py").read_text(
        encoding="utf-8"
    )
    lane_validator = (
        ROOT / "backend/scripts/validate_test_lane_evidence.py"
    ).read_text(encoding="utf-8")
    assert "tests/test_isolated_database_runner.py" in lane_runner
    assert "admin_runner_self_test" in lane_runner
    assert "execution_kind" in lane_runner
    assert "run_isolated_tests.py" in lane_runner
    assert "admin_runner_self_test" in lane_validator
    assert "execution_kind" in lane_validator

    api_e2e_steps = [
        step for step in steps if step.get("name") == "API contract real API e2e"
    ]
    assert len(api_e2e_steps) == 1
    assert "scripts/run_isolated_tests.py" in str(api_e2e_steps[0]["run"])
    assert "scripts/api_contract_e2e.py" in str(api_e2e_steps[0]["run"])
    assert 1500 <= test_job["timeout-minutes"] * 60 - 300
    assert "--timeout-seconds 1500" in str(api_e2e_steps[0]["run"])
    downloads = [step for step in steps if "actions/download-artifact@" in step.get("uses", "")]
    assert downloads == []
    uploads = [
        step for step in steps
        if "actions/upload-artifact@" in step.get("uses", "")
    ]
    assert len(uploads) == 1
    assert uploads[0]["uses"] == (
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )
    assert uploads[0]["if"] == "${{ always() }}"
    assert uploads[0]["with"]["path"] == "backend/.ci/test-lanes/**"
    combines = [
        step for step in steps
        if step.get("name") == "Combine semantic-lane coverage exactly once"
    ]
    assert len(combines) == 1
    combine_command = str(combines[0]["run"])
    assert combine_command.count("coverage combine") == 1
    assert 'test "${#coverage_files[@]}" -eq 4' in combine_command
    assert "test ! -L" in combine_command
    assert "sha256sum" in combine_command
    assert steps.index(validators[1]) < steps.index(combines[0])

    full_suite_steps = [
        step for step in steps if step.get("name") == "Backend full-suite coverage"
    ]
    assert len(full_suite_steps) == 1
    assert full_suite_steps[0].get("working-directory") == "backend"
    assert full_suite_steps[0]["run"] == "coverage report --precision=2 --fail-under=78"
    for forbidden_key in ("if", "continue-on-error", "shell", "env"):
        assert forbidden_key not in full_suite_steps[0]
    full_suite_index = steps.index(full_suite_steps[0])
    auth_coverage_steps = [
        step
        for step in steps
        if str(step.get("run", "")).strip() in AUTH_09B_COVERAGE_COMMANDS
    ]
    assert tuple(str(step["run"]).strip() for step in auth_coverage_steps) == (
        AUTH_09B_COVERAGE_COMMANDS
    )
    for coverage_step in auth_coverage_steps:
        assert full_suite_index < steps.index(coverage_step)
        assert coverage_step.get("working-directory") == "backend"
        for forbidden_key in ("if", "continue-on-error", "shell", "env"):
            assert forbidden_key not in coverage_step
    hosted_steps = [
        step for step in steps
        if step.get("name") == "Record hosted timing and fail-closed coverage evidence"
    ]
    assert len(hosted_steps) == 1
    hosted_step = hosted_steps[0]
    hosted_command = str(hosted_step["run"])
    assert steps.index(hosted_step) > max(steps.index(step) for step in auth_coverage_steps)
    assert "coverage json -o .ci/test-lanes/coverage.json" in hosted_command
    assert ".ci/test-lanes/hosted-evidence.json" in hosted_command
    assert 'summary.get("head_sha") != expected_head' in hosted_command
    assert 'summary.get("canonical_node_count")' in hosted_command
    assert 'summary.get("aggregate_runner_seconds")' in hosted_command
    assert 'summary.get("slowest_lane_seconds")' in hosted_command
    assert '"timing_target_met": total_wall <= 480' in hosted_command
    assert 'total_wall > 480' not in hosted_command
    assert 'percent < 78' in hosted_command
    assert "math.isfinite" in hosted_command
    assert "Counter(collected) != Counter(completed)" in hosted_command
    assert "hosted lane digest drift" in hosted_command
    for required_field in (
        "head_sha",
        "total_backend_wall_seconds",
        "slowest_lane_seconds",
        "aggregate_runner_seconds",
        "timing_target_met",
        "canonical_collected_count",
        "completed_count",
        "global_coverage_percent",
        "global_coverage_sha256",
        "run_summary_sha256",
    ):
        assert f'"{required_field}"' in hosted_command
    assert "waiver" not in hosted_command.lower()
    operations = (ROOT / "docs/operations_backend_testing.md").read_text(
        encoding="utf-8"
    )
    assert "whether\nthe eight-minute target was met" in operations
    assert "does not override otherwise passing correctness" in operations
    assert "makes the required check fail outright" not in operations
    active_phase = active_artifact_coverage_phase()
    expected_coverage = artifact_expected_coverage_commands_for(active_phase)
    actual_coverage = tuple(
        str(step.get("run", "")).strip()
        for step in steps
        if str(step.get("run", "")).strip().startswith("coverage report ")
        and "--fail-under=90" in str(step.get("run", ""))
    )
    assert actual_coverage == (
        *expected_coverage,
        *AUTH_09B_COVERAGE_COMMANDS[:2],
        *AUTHORIZATION_READ_COVERAGE_COMMANDS,
        *AUTH_09B_COVERAGE_COMMANDS[2:],
    )
    for command in expected_coverage:
        matches = [
            step for step in steps if str(step.get("run", "")).strip() == command
        ]
        assert len(matches) == 1, (command, matches)
        coverage_step = matches[0]
        assert steps.index(coverage_step) > full_suite_index
        assert coverage_step.get("working-directory") == "backend"
        for forbidden_key in ("if", "continue-on-error", "shell", "env"):
            assert forbidden_key not in coverage_step
    later_commands = artifact_expected_coverage_commands_for("06B")
    assert later_commands[0] == FOUNDATION_ARTIFACT_COVERAGE_COMMAND
    assert any("app/modules/checkers/*" in command for command in later_commands)
    assert workflow.count("--fail-under=78") == 1
    assert "--cov-fail-under" not in workflow
    assert workflow.count("--fail-under=90") == (
        len(expected_coverage)
        + len(AUTH_09B_COVERAGE_COMMANDS)
        + len(AUTHORIZATION_READ_COVERAGE_COMMANDS)
    )
    assert "continue-on-error" not in workflow


def test_artifact_coverage_phase_is_derived_from_work_queue() -> None:
    """The queue, not a second hardcoded active-phase marker, drives CI gates."""
    global ROOT
    original_root = ROOT
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ROOT = Path(tmpdir)
            loop_dir = ROOT / ".agent-loop"
            loop_dir.mkdir()
            queue = loop_dir / "WORK_QUEUE.md"
            queue.write_text(
                "# Work Queue\n\n"
                "## In Progress\n\n"
                "| Chunk | Title | Risk | Status |\n"
                "|---|---|---:|---|\n"
                "| `WS-ART-001-02A3` | cutover | L1 | active |\n\n"
                "## Planned Next\n\n"
                "## Completed\n\n"
                "## Proposed Next\n",
                encoding="utf-8",
            )
            assert active_artifact_coverage_phase() == "02A3"

            queue.write_text(
                "# Work Queue\n\n"
                "## In Progress\n\n"
                "| Chunk | Title | Risk | Status |\n"
                "|---|---|---:|---|\n\n"
                "## Planned Next\n\n"
                "## Completed\n\n"
                "| Chunk | Title | Risk | Status |\n"
                "|---|---|---:|---|\n"
                "| `WS-ART-001-02A2` | preparation | L1 | merged |\n\n"
                "## Proposed Next\n",
                encoding="utf-8",
            )
            assert active_artifact_coverage_phase() == "02A2"
    finally:
        ROOT = original_root


def test_stale_artifact_contracts_cutover_rejects_reached_terms_only() -> None:
    """The active cutover rejects reached terms without preempting later phases."""
    gate = load_module(
        "stale_artifact_contracts_foundation",
        "scripts/check_stale_artifact_contracts.py",
    )
    assert gate.ARTIFACT_CONTRACT_PHASE == "artifact_store_cutover"
    assert (
        gate.scan_text(
            "backend/app/modules/tasks/schemas.py",
            "package_uri content_cid artifact_manifest_hash",
            gate.ARTIFACT_CONTRACT_PHASE,
        )
        == []
    )
    failures = gate.scan_text(
        "contracts/artifact-store/version_1/schema/example.json",
        '{"cid": "provider-specific"}',
        gate.ARTIFACT_CONTRACT_PHASE,
    )
    assert failures == [
        "contracts/artifact-store/version_1/schema/example.json:1: "
        "PROVIDER_SPECIFIC_GENERIC_INTERFACE"
    ]


def test_stale_artifact_contracts_active_later_phase_owns_only_reached_terms() -> None:
    """A later phase rejects reached legacy terms while leaving future ones alone."""
    gate = load_module(
        "stale_artifact_contracts_later",
        "scripts/check_stale_artifact_contracts.py",
    )
    guide_failures = gate.scan_text(
        "backend/app/modules/projects/schemas.py",
        "content_cid package_uri artifact_manifest_hash",
        "guide_source_cutover",
    )
    assert guide_failures == [
        "backend/app/modules/projects/schemas.py:1: LEGACY_GUIDE_CONTENT_CID"
    ]
    submission_failures = gate.scan_text(
        "backend/app/modules/tasks/schemas.py",
        "package_uri allowed_storage_schemes artifact_manifest_hash",
        "submission_cutover",
    )
    assert submission_failures == [
        "backend/app/modules/tasks/schemas.py:1: LEGACY_SUBMISSION_TRANSPORT",
        "backend/app/modules/tasks/schemas.py:1: LEGACY_PROJECT_STORAGE_POLICY",
    ]
    assert gate.scan_text(
        "backend/scripts/api_contract_e2e.py",
        '"allowed_storage_schemes": ["local", "s3", "r2"]',
        "submission_cutover",
    ) == [
        "backend/scripts/api_contract_e2e.py:1: LEGACY_PROJECT_STORAGE_POLICY",
        "backend/scripts/api_contract_e2e.py:1: DEFERRED_R2_RUNTIME",
    ]
    for active_caller in (
        "backend/scripts/week2_api_e2e.py",
        "examples/terminal_benchmark/terminal_benchmark_api_e2e.py",
    ):
        assert gate.scan_text(
            active_caller,
            'package_uri = "local://fixture"',
            "submission_cutover",
        ) == [
            f"{active_caller}:1: LEGACY_SUBMISSION_TRANSPORT",
            f"{active_caller}:1: LEGACY_CALLER_STORAGE_SCHEME",
        ]


def test_stale_artifact_contracts_malformed_phase_fails_closed() -> None:
    """Unknown or non-string phase markers cannot disable scanner rules."""
    gate = load_module(
        "stale_artifact_contracts_malformed",
        "scripts/check_stale_artifact_contracts.py",
    )
    for phase in ("", "submission", "foundation ", None, 1):
        try:
            gate.rules_for_phase(phase)
        except ValueError as exc:
            assert "malformed artifact contract phase" in str(exc)
        else:
            raise AssertionError(f"malformed phase was accepted: {phase!r}")

    original_phase = gate.ARTIFACT_CONTRACT_PHASE
    gate.ARTIFACT_CONTRACT_PHASE = "unknown"
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            assert gate.main() == 1
    finally:
        gate.ARTIFACT_CONTRACT_PHASE = original_phase


def test_stale_artifact_contracts_enforce_aws_first_v01() -> None:
    """Active contracts and runtime config cannot reactivate deferred R2."""
    gate = load_module(
        "stale_artifact_contracts_aws_first",
        "scripts/check_stale_artifact_contracts.py",
    )
    discovery_path = (
        ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/DISCOVERY.md"
    )
    runtime_credentials = "Runtime " + "credentials"
    assert gate.scan_text(
        discovery_path,
        runtime_credentials + " are scoped and cannot delete, " + "list, or copy.",
        "foundation",
    ) == [f"{discovery_path}:1: STALE_AWS_RUNTIME_NO_LIST"]
    for stale_statement in (
        runtime_credentials + " are scoped and could not list objects.",
        runtime_credentials + " are scoped and cannot delete,\nlist, or copy.",
        runtime_credentials + " are scoped. They cannot delete, list, or copy.",
    ):
        assert gate.scan_text(
            discovery_path,
            stale_statement,
            "foundation",
        ) == [f"{discovery_path}:1: STALE_AWS_RUNTIME_NO_LIST"]
    assert (
        gate.scan_text(
            discovery_path,
            (
                "Runtime credentials cannot delete or copy. AWS has s3:ListBucket "
                "only for missing-key classification; the app calls no list API."
            ),
            "foundation",
        )
        == []
    )
    assert gate.scan_text(
        "docs/spec_artifact_storage_service.md",
        "AWS S3 or Cloudflare R2 are supported production providers.",
        "foundation",
    ) == ["docs/spec_artifact_storage_service.md:1: ACTIVE_R2_V01_PLAN"]
    for active_statement in (
        "Cloudflare R2 is an eligible object-store provider.",
        "Enable R2 for hosted deployments.",
        "R2 is supported for hosted deployments.",
        "R2 is deferred outside v0.1, although it is the hosted provider.",
    ):
        assert gate.scan_text(
            "docs/spec_artifact_storage_service.md",
            active_statement,
            "foundation",
        ) == ["docs/spec_artifact_storage_service.md:1: ACTIVE_R2_V01_PLAN"]
    assert (
        gate.scan_text(
            "docs/spec_artifact_storage_service.md",
            "Cloudflare R2 is deferred; AWS S3 is the v0.1 production provider.",
            "foundation",
        )
        == []
    )
    assert gate.scan_text(
        "docs/spec_artifact_storage_service.md",
        "Cloudflare R2 is deferred but remains a production provider.",
        "foundation",
    ) == ["docs/spec_artifact_storage_service.md:1: ACTIVE_R2_V01_PLAN"]
    for mixed_statement in (
        (
            "Cloudflare R2 is deferred to v0.2 and Cloudflare R2 is supported "
            "for v0.1 production."
        ),
        (
            "Cloudflare R2 is a v0.1 production provider and requires a "
            "separately approved runbook."
        ),
        "Cloudflare R2 is deferred in name only but shall ship alongside AWS S3.",
    ):
        assert gate.scan_text(
            "docs/spec_artifact_storage_service.md",
            mixed_statement,
            "foundation",
        ) == ["docs/spec_artifact_storage_service.md:1: ACTIVE_R2_V01_PLAN"]
    assert gate.scan_text(
        "backend/app/core/config.py",
        'artifact_provider_profile = "cloudflare_r2"',
        "foundation",
    ) == ["backend/app/core/config.py:1: DEFERRED_R2_RUNTIME"]
    for runtime_value in (
        'artifact_provider_profile = "r2"',
        'r2_endpoint = "https://example.invalid"',
        "artifact_store = R2ArtifactStore()",
        "client = R2Client()",
        'endpoint = os.environ["WORKSTREAM_R2_ENDPOINT"]',
        'endpoint = "https://account.r2.cloudflarestorage.com"',
        "artifact_store = CloudflareArtifactStore()",
        "artifact_store = CloudflareS3CompatibleArtifactStore()",
        'artifact_provider = "cloudflare"',
    ):
        assert gate.scan_text(
            "backend/app/core/config.py",
            runtime_value,
            "foundation",
        ) == ["backend/app/core/config.py:1: DEFERRED_R2_RUNTIME"]
    for runtime_path, runtime_value in (
        ("backend/app/integrations/storage.py", 'provider = "r2"'),
        ("backend/alembic/versions/9999_r2.py", 'provider = "r2"'),
        ("backend/pyproject.toml", 'cloudflare-r2 = "1.0"'),
        ("backend/uv.lock", 'name = "cloudflare-r2"'),
        ("backend/requirements-storage.txt", "cloudflare-r2==1.0"),
        ("backend/scripts/storage_runtime.py", 'provider = "cloudflare_r2"'),
        ("frontend/src/config.ts", 'provider = "cloudflare_r2"'),
        ("services/object_storage/config.py", 'provider = "cloudflare_r2"'),
        (".github/workflows/backend.yml", "WORKSTREAM_R2_ENDPOINT: secret"),
        ("Dockerfile", "ENV WORKSTREAM_R2_ENDPOINT=secret"),
        (".env.example", "WORKSTREAM_R2_ENDPOINT=secret"),
        ("deploy/config", 'provider = "r2"'),
        ("deploy/r2.conf", 'provider = "r2"'),
        ("docker/minio/config.sh", 'provider = "r2"'),
        ("ops/runtime.yaml", 'provider: "cloudflare_r2"'),
        ("config/artifact.toml", 'provider = "r2"'),
        ("helm/storage.tpl", 'provider = "r2"'),
    ):
        assert gate.scan_text(runtime_path, runtime_value, "foundation") == [
            f"{runtime_path}:1: DEFERRED_R2_RUNTIME"
        ]
    legacy_source_line = (
        'ALLOWED_SOURCE_REF_SCHEMES = {"https", "http", "repo", "inline", '
        '"import", "s3", "r2"}'
    )
    assert (
        gate.scan_text(
            "backend/app/modules/projects/service.py",
            legacy_source_line,
            "foundation",
        )
        == []
    )
    assert gate.scan_text(
        "backend/app/modules/projects/service.py",
        legacy_source_line,
        "guide_source_cutover",
    ) == ["backend/app/modules/projects/service.py:1: DEFERRED_R2_RUNTIME"]
    assert gate.path_is_scannable("Dockerfile")
    assert gate.path_is_scannable(".env.example")
    assert gate.path_is_scannable("deploy/config")
    assert gate.path_is_scannable("deploy/r2.conf")
    assert gate.path_is_scannable("docker/minio/config.sh")
    assert gate.path_is_scannable("ops/runtime.yaml")
    assert gate.path_is_scannable("config/artifact.toml")
    assert gate.path_is_scannable("helm/storage.tpl")
    assert gate.path_is_scannable("backend/pyproject.toml")
    assert gate.path_is_scannable("backend/uv.lock")
    assert gate.path_is_scannable("frontend/src/config.ts")
    assert gate.path_is_scannable("docs/diagrams/rendered/workstream_context.svg")
    assert gate.scan_text(
        "docs/diagrams/rendered/workstream_context.svg",
        "Object Storage\\nR2/S3-compatible later",
        "foundation",
    ) == ["docs/diagrams/rendered/workstream_context.svg:1: ACTIVE_R2_V01_PLAN"]
    assert gate.scan_text(
        (".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md"),
        "WS-ART-001-02B2",
        "foundation",
    ) == [
        (
            ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/"
            "CHUNK_MAP.md:1: ACTIVE_R2_V01_PLAN"
        )
    ]
    completed_only_queue = (
        "# Work Queue\n\n## In Progress\n\nNone.\n\n"
        "## Planned Next\n\nNone.\n\n## Completed\n\n"
        "Cloudflare R2 is the hosted production provider.\n"
    )
    assert (
        gate.scan_text(".agent-loop/WORK_QUEUE.md", completed_only_queue, "foundation")
        == []
    )
    active_queue = (
        "# Work Queue\n\n## In Progress\n\n"
        "Cloudflare R2 is the hosted production provider.\n\n"
        "## Planned Next\n\nNone.\n\n## Completed\n\nNone.\n"
    )
    assert gate.scan_text(".agent-loop/WORK_QUEUE.md", active_queue, "foundation") == [
        ".agent-loop/WORK_QUEUE.md:5: ACTIVE_R2_V01_PLAN"
    ]


def test_stale_artifact_contracts_scan_only_current_initiatives() -> None:
    """Work Queue activation scans every live initiative without history."""
    gate = load_module(
        "stale_artifact_contracts_parallel",
        "scripts/check_stale_artifact_contracts.py",
    )
    prefixes = gate.active_initiative_prefixes()
    assert any("WS-ART-001-immutable-artifact-storage" in item for item in prefixes)
    assert not any(
        "WS-AUTH-001-workstream-authorization-service" in item for item in prefixes
    )
    assert gate.path_is_scannable(
        ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/PLAN.md"
    )
    assert not gate.path_is_scannable(
        ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/reviews/old.md"
    )

    auth_gate = load_module(
        "stale_authorization_docs_history",
        "scripts/check_stale_authorization_docs.py",
    )
    assert gate.HISTORICAL_PATHS == set(auth_gate.HISTORICAL_PATHS)
    assert not gate.path_is_scannable("docs/spec_chunk_3_project_guide_foundation.md")
    assert not gate.path_is_active_contract(
        "docs/spec_chunk_3_project_guide_foundation.md"
    )
    assert gate.path_is_scannable("docs/spec_artifact_storage_service.md")
    assert gate.path_is_scannable(
        ".agent-loop/policies/repository-engineering-policy.md"
    )
    assert gate.path_is_active_contract(
        ".agent-loop/policies/repository-engineering-policy.md"
    )
    assert gate.scan_text(
        ".agent-loop/policies/repository-engineering-policy.md",
        "File storage: Cloudflare R2 is the hosted production provider.",
        "foundation",
    ) == [".agent-loop/policies/repository-engineering-policy.md:1: ACTIVE_R2_V01_PLAN"]

    original_root = gate.ROOT
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".agent-loop/initiatives/WS-ART-001-artifacts").mkdir(parents=True)
            (root / ".agent-loop/initiatives/WS-AUTH-001-auth").mkdir(parents=True)
            (root / ".agent-loop/WORK_QUEUE.md").write_text(
                "# Work Queue\n\n"
                "## In Progress\n\n"
                "| Chunk | Title |\n|---|---|\n"
                "| `WS-AUTH-001-05B` | auth |\n\n"
                "## Planned Next\n\n"
                "| Chunk | Title |\n|---|---|\n"
                "| `WS-ART-001-02A1` | artifacts |\n\n"
                "## Completed\n\n"
                "| Chunk | Title |\n|---|---|\n",
                encoding="utf-8",
            )
            prefixes = gate.active_initiative_prefixes(root)
            assert prefixes == (
                ".agent-loop/initiatives/WS-ART-001-artifacts/",
                ".agent-loop/initiatives/WS-AUTH-001-auth/",
            )
            (root / ".agent-loop/WORK_QUEUE.md").write_text(
                "# Work Queue\n\n## In Progress\n\n## Completed\n",
                encoding="utf-8",
            )
            try:
                gate.active_initiative_prefixes(root)
            except ValueError as exc:
                assert "malformed Work Queue headings" in str(exc)
            else:
                raise AssertionError("malformed live queue headings were accepted")
    finally:
        gate.ROOT = original_root


def test_stale_artifact_contracts_remove_flow_node_at_store_cutover() -> None:
    """The clean cut rejects the dormant Flow Node backend at its owning phase."""
    gate = load_module(
        "stale_artifact_contracts_store_cutover",
        "scripts/check_stale_artifact_contracts.py",
    )
    assert (
        gate.scan_text(
            "backend/app/core/config.py",
            'artifact_store_backend = "flow_node"',
            "foundation",
        )
        == []
    )
    assert gate.scan_text(
        "backend/app/core/config.py",
        'artifact_store_backend = "flow_node"',
        "artifact_store_cutover",
    ) == ["backend/app/core/config.py:1: LEGACY_FLOW_NODE_RUNTIME"]
    assert (
        gate.scan_text(
            "docs/decision_0013_immutable_artifact_storage_boundary.md",
            "Flow Node is deferred and is not a v0.1 dependency.",
            "foundation",
        )
        == []
    )
    for active_statement in (
        "Flow Node is deferred but remains the v0.1 production provider.",
        "Flow Node is preserved as the v0.1 production provider.",
        "Flow Node is deferred, but continues as an approved hosted backend.",
        "Flow Node is deferred and enabled as a production backend.",
        "Flow Node is deferred, yet supported as the hosted backend.",
    ):
        assert gate.scan_text(
            "docs/decision_0013_immutable_artifact_storage_boundary.md",
            active_statement,
            "foundation",
        ) == [
            "docs/decision_0013_immutable_artifact_storage_boundary.md:1: "
            "OBSOLETE_FLOW_NODE_PLAN"
        ]
    for runtime_path in (
        "backend/app/modules/artifacts/service.py",
        "backend/app/workers/artifacts.py",
    ):
        assert gate.scan_text(
            runtime_path,
            'provider = "flow_node"',
            "artifact_store_cutover",
        ) == [f"{runtime_path}:1: LEGACY_FLOW_NODE_RUNTIME"]


def test_artifact_chunk_verification_commands_are_isolated_and_rerunnable() -> None:
    """Every implementation contract owns a cleaned unique metadata path."""
    assert (
        "coverage report --include='app/main.py' --precision=2 --fail-under=90"
        in ARTIFACT_COVERAGE_COMMAND_OWNERS["02A3"]
    )
    assert (
        "coverage report --include='app/modules/audit/*' "
        "--precision=2 --fail-under=90" in ARTIFACT_COVERAGE_COMMAND_OWNERS["02C1"]
    )
    chunk_root = (
        ROOT / ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks"
    )
    for phase in ARTIFACT_COVERAGE_ORDER[1:]:
        matches = sorted(chunk_root.glob(f"WS-ART-001-{phase}-*.md"))
        assert len(matches) == 1, (phase, matches)
        contract = matches[0].read_text(encoding="utf-8")
        assert "/tmp/ws-art-" not in contract
        assert contract.count('metadata_dir="$(mktemp -d)"') == 1
        assert contract.count("trap 'rm -rf \"$metadata_dir\"' EXIT") == 1
        assert contract.count('--metadata-json "$metadata_dir/result.json"') == 1
        verification_match = re.search(
            r"## Verification\n\n```bash\n(.*?)\n```",
            contract,
            re.DOTALL,
        )
        assert verification_match is not None, matches[0]
        verification = verification_match.group(1)
        syntax = subprocess.run(
            ["bash", "-n"],
            input=verification,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert syntax.returncode == 0, (matches[0], syntax.stderr)
        for command in verification.splitlines():
            assert not command.startswith("cd backend &&"), (matches[0], command)
            if "cd backend &&" in command:
                assert (
                    command.startswith("(cd backend &&")
                    or " && (cd backend &&" in command
                ), (
                    matches[0],
                    command,
                )
        metadata_command = next(
            command
            for command in verification.splitlines()
            if command.startswith('(metadata_dir="$(mktemp -d)"')
        )
        assert "run_isolated_tests.py" in metadata_command
        assert metadata_command.endswith("))")
        assert "alembic upgrade head" not in verification
        if phase in {"03C", "05"}:
            assert "backend/scripts/api_contract_e2e.py" in contract
            assert "scripts/api_contract_e2e.py" in verification
        expected_contract_phase = artifact_contract_phase_for(phase)
        assert expected_contract_phase in {
            "foundation",
            "artifact_store_cutover",
            "guide_source_cutover",
            "upload_admission",
            "submission_cutover",
            "checker_cutover",
        }
        assert artifact_declared_contract_phase_for(phase) == expected_contract_phase
        assert artifact_contract_coverage_commands_for(
            phase
        ) == artifact_expected_coverage_commands_for(phase)
    gate = load_module(
        "stale_artifact_contracts_phase_binding",
        "scripts/check_stale_artifact_contracts.py",
    )
    active_phase = active_artifact_coverage_phase()
    assert artifact_contract_phase_for(active_phase) == gate.ARTIFACT_CONTRACT_PHASE
    mismatched_phase = (
        "02A3" if gate.ARTIFACT_CONTRACT_PHASE == "foundation" else "foundation"
    )
    assert artifact_contract_phase_for(mismatched_phase) != gate.ARTIFACT_CONTRACT_PHASE
    with tempfile.TemporaryDirectory() as temp_dir:
        cleanup = subprocess.run(
            [
                "bash",
                "-c",
                (
                    "for run in 1 2; do "
                    f'(metadata_dir="$(mktemp -d -p {temp_dir})" && '
                    "trap 'rm -rf \"$metadata_dir\"' EXIT && "
                    'test -d "$metadata_dir"); '
                    "done; "
                    f'test -z "$(find {temp_dir} -mindepth 1 -maxdepth 1 '
                    '-print -quit)"'
                ),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        assert cleanup.returncode == 0, cleanup.stderr


def test_artifact_action_registry_has_exact_owned_mappings() -> None:
    """Artifact ActionIds have one canonical PermissionId and chunk owner."""
    text = (ROOT / "docs/spec_authorization_service.md").read_text(encoding="utf-8")
    section = text.split(
        "The following table is the single source of truth", maxsplit=1
    )[1].split("The fixed internal service identities", maxsplit=1)[0]
    rows = re.findall(
        r"^\| `([^`]+)` \| `([^`]+)` \| .* \| .* \| `([^`]+)` \|$",
        section,
        re.MULTILINE,
    )
    expected = {
        ("artifact.binding.read", "artifact.binding.read", "02D"),
        ("artifact.replica.read", "artifact.replica.read", "02D"),
        ("artifact.receipt.read", "artifact.receipt.read", "02D"),
        (
            "artifact.verification_job.read",
            "artifact.verification_job.read",
            "02D",
        ),
        (
            "artifact.verification_job.retry",
            "artifact.verification_job.retry",
            "02D",
        ),
        (
            "artifact.recovery_attempt.read",
            "artifact.recovery_attempt.read",
            "02D",
        ),
        ("artifact.audit.read", "artifact.audit.read", "02D"),
        (
            "operations.artifact_storage_admission.read",
            "operations.status.read",
            "02D",
        ),
        (
            "artifact.guide_source.ingest",
            "artifact.guide_source.ingest",
            "03",
        ),
        ("artifact.guide_source.read", "artifact.guide_source.read", "03"),
        (
            "artifact.upload_session.create",
            "artifact.upload_session.create",
            "04A",
        ),
        (
            "artifact.upload_session.read",
            "artifact.upload_session.read",
            "04A",
        ),
        ("artifact.upload_item.write", "artifact.upload_item.write", "04A"),
        (
            "artifact.upload_session.seal",
            "artifact.upload_session.seal",
            "04A",
        ),
        (
            "artifact.upload_session.cancel",
            "artifact.upload_session.cancel",
            "04A",
        ),
        (
            "artifact.upload_session.expire",
            "artifact.upload_session.expire",
            "04A",
        ),
        (
            "artifact.guide_source.binding.create",
            "artifact.binding.create",
            "03",
        ),
        (
            "artifact.submission.binding.create",
            "artifact.binding.create",
            "05",
        ),
        (
            "artifact.checker_output.binding.create",
            "artifact.binding.create",
            "06B",
        ),
        (
            "artifact.verification.execute",
            "artifact.verification.execute",
            "02D",
        ),
        (
            "artifact.pending_work.scan",
            "artifact.pending_work.scan",
            "02D",
        ),
        (
            "artifact.put_attempt.resolve",
            "artifact.put_attempt.resolve",
            "02D",
        ),
        (
            "artifact.pre_submit.checker_input.materialize",
            "artifact.checker_input.materialize",
            "04B",
        ),
        (
            "artifact.post_submit.checker_input.materialize",
            "artifact.checker_input.materialize",
            "06A",
        ),
        (
            "artifact.checker_output.write",
            "artifact.checker_output.write",
            "06B",
        ),
    }
    assert len(rows) == len({action for action, _, _ in rows})
    assert set(rows) == expected
    assert "artifact.operator.admission_usage.read" not in text


def _markdown_contract_table(
    text: str,
    header: str,
) -> list[tuple[str, ...]]:
    """Parse one closed Markdown contract table by its exact header."""
    lines = text.splitlines()
    header_index = lines.index(header)
    separator = lines[header_index + 1]
    assert re.fullmatch(r"\|(?:---\|)+", separator)
    rows: list[tuple[str, ...]] = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(tuple(cell.strip() for cell in line.strip("|").split("|")))
    assert rows
    return rows


def _code_tokens(cell: str) -> tuple[str, ...]:
    """Return ordered inline-code values from one Markdown table cell."""
    return tuple(re.findall(r"`([^`]+)`", cell))


def _assert_exact_aws_artifact_authorization_contract(spec: str) -> None:
    """Require the AWS principal and bucket-deny matrices to be closed."""
    principal_rows = _markdown_contract_table(
        spec,
        "| Principal | Exact allowed IAM actions | Exact resource |",
    )
    expected_principal_rows = {
        (
            "Workstream runtime role",
            ("s3:PutObject", "s3:GetObject"),
            ("OBJECT_ARN",),
        ),
        (
            "Workstream runtime role",
            ("s3:ListBucket",),
            ("BUCKET_ARN",),
        ),
        (
            "deployment readiness role",
            (
                "s3:GetBucketPolicy",
                "s3:GetBucketPolicyStatus",
                "s3:GetBucketAcl",
                "s3:GetBucketPublicAccessBlock",
                "s3:GetBucketOwnershipControls",
                "s3:GetBucketVersioning",
                "s3:GetLifecycleConfiguration",
                "s3:GetEncryptionConfiguration",
            ),
            ("BUCKET_ARN",),
        ),
        (
            "deployment readiness role",
            ("iam:GetRole", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies"),
            ("RUNTIME_ROLE_ARN",),
        ),
        (
            "deployment readiness role",
            ("iam:GetPolicy", "iam:GetPolicyVersion"),
            ("RUNTIME_POLICY_ARN",),
        ),
        (
            "deployment readiness role",
            (
                "access-analyzer:ValidatePolicy",
                "access-analyzer:CheckAccessNotGranted",
                "access-analyzer:CheckNoPublicAccess",
            ),
            ("*",),
        ),
        ("deployment negative-test role", (), ()),
        ("infrastructure bootstrap principal", (), ()),
    }
    actual_principal_rows = {
        (principal, _code_tokens(actions), _code_tokens(resources))
        for principal, actions, resources in principal_rows
    }
    assert len(actual_principal_rows) == len(principal_rows)
    assert actual_principal_rows == expected_principal_rows
    negative_actions = next(
        actions
        for principal, actions, _ in principal_rows
        if principal == "deployment negative-test role"
    )
    assert negative_actions == "no S3, IAM, or Access Analyzer action"

    deny_rows = _markdown_contract_table(
        spec,
        "| Sid | Effect | Exact actions | Exact resources | Exact principal | Exact condition |",
    )
    actual_denies = {
        (
            _code_tokens(sid),
            effect,
            _code_tokens(actions),
            _code_tokens(resources),
            _code_tokens(principal),
            _code_tokens(condition),
        )
        for sid, effect, actions, resources, principal, condition in deny_rows
    }
    assert len(actual_denies) == len(deny_rows)
    assert actual_denies == {
        (
            ("DenyInsecureTransport",),
            "Deny",
            ("s3:*",),
            ("BUCKET_ARN", "OBJECT_ARN"),
            ("*",),
            ('Bool: {"aws:SecureTransport": "false"}',),
        ),
        (
            ("DenyNonRuntimeObjectData",),
            "Deny",
            ("s3:*",),
            ("OBJECT_ARN",),
            ("*",),
            ('ArnNotEquals: {"aws:PrincipalArn": RUNTIME_ROLE_ARN}',),
        ),
        (
            ("DenyUnconditionalPut",),
            "Deny",
            ("s3:PutObject",),
            ("OBJECT_ARN",),
            ("*",),
            ('Null: {"s3:if-none-match": "true"}',),
        ),
    }


def test_aws_artifact_activation_contract_is_exact_and_time_bounded() -> None:
    """The AWS proof contract fixes actions, denies, identities, and TTL."""
    spec = (ROOT / "docs/spec_artifact_storage_service.md").read_text(encoding="utf-8")
    chunk = (
        ROOT / ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/"
        "WS-ART-001-07-recovery-live-proof.md"
    ).read_text(encoding="utf-8")
    _assert_exact_aws_artifact_authorization_contract(spec)
    assert "operation_total_deadline + persistence_margin +" in spec
    assert "clock_safety_margin" in spec
    assert "A 403 is always `provider_unavailable`, never `missing`" in spec
    assert "s3:if-none-match` equals `*" not in spec
    assert "aws_runtime_immutability_probe" in chunk
    assert "aws_negative_access_probe" in chunk
    assert "aws_activation_coordinator" in chunk
    assert "nonexistent opaque challenge key" in chunk

    mutations = (
        (
            "`s3:PutObject`, `s3:GetObject` | `OBJECT_ARN` only |",
            "`s3:PutObject`, `s3:GetObject`, `s3:ListBucket` | `OBJECT_ARN` only |",
        ),
        (
            "| Workstream runtime role | `s3:ListBucket` | `BUCKET_ARN` only |\n",
            "",
        ),
        (
            "| Workstream runtime role | `s3:ListBucket` | `BUCKET_ARN` only |",
            "| Workstream runtime role | `s3:ListBucket` | `OBJECT_ARN` only |",
        ),
        (
            "`s3:PutObject`, `s3:GetObject` | `OBJECT_ARN` only |",
            "`s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` | `OBJECT_ARN` only |",
        ),
        (
            "`s3:PutObject`, `s3:GetObject` | `OBJECT_ARN` only |",
            "`s3:*` | `OBJECT_ARN` only |",
        ),
        (
            "`iam:GetRole`, `iam:ListRolePolicies`, `iam:ListAttachedRolePolicies`",
            "`iam:GetRole`, `iam:ListRolePolicies`, `iam:ListAttachedRolePolicies`, `iam:GetUser`",
        ),
        (
            "`RUNTIME_ROLE_ARN` only",
            "`RUNTIME_ROLE_ARN`, `RUNTIME_POLICY_ARN`",
        ),
        (
            '`ArnNotEquals: {"aws:PrincipalArn": RUNTIME_ROLE_ARN}`',
            '`StringNotEquals: {"aws:PrincipalArn": RUNTIME_ROLE_ARN}`',
        ),
        (
            '`Null: {"s3:if-none-match": "true"}`',
            '`Null: {"s3:if-none-match": "false"}`',
        ),
    )
    for current, unsafe in mutations:
        assert current in spec
        mutated = spec.replace(current, unsafe, 1)
        try:
            _assert_exact_aws_artifact_authorization_contract(mutated)
        except AssertionError:
            continue
        raise AssertionError(f"unsafe AWS contract mutation was accepted: {unsafe}")


def main() -> int:
    """Run all local test functions."""
    tests = [
        test_required_tracks_expand_for_loop_and_ci_paths,
        test_backend_config_paths_require_review_evidence,
        test_review_evidence_files_are_not_relevant_changes,
        test_evidence_requires_completed_yes_statements,
        test_evidence_must_reference_changed_chunk,
        test_evidence_rejects_pending_or_blocking_reviewer_rows,
        test_evidence_accepts_exact_pass_and_approved_na_results,
        test_evidence_rejects_na_for_required_tracks,
        test_evidence_reviewed_revision_allows_only_evidence_status_changes,
        test_evidence_reviewed_revision_rejects_late_implementation_changes,
        test_evidence_reviewed_revision_rejects_dirty_tree_changes,
        test_evidence_reviewed_revision_rejects_invalid_provenance,
        test_evidence_main_fails_closed_on_unresolved_base_ref,
        test_evidence_main_passes_with_complete_evidence_and_pr_head,
        test_evidence_main_rejects_external_response_without_internal_evidence,
        test_evidence_main_reports_missing_evidence_file,
        test_static_sensor_counts_untracked_text_lines,
        test_static_sensor_requires_resolved_base_ref,
        test_static_sensor_accumulates_numstat_for_duplicate_paths,
        test_static_sensor_flags_backend_config_as_ci_surface,
        test_markdown_link_checker_collects_base_cached_dirty_and_untracked,
        test_stale_wording_patterns_catch_variants,
        test_active_shared_contract_rejects_retired_contracts,
        test_historical_docs_do_not_define_live_compensation_contract,
        test_current_runtime_walkthrough_rejects_unimplemented_compensation_records,
        test_stale_wording_skips_only_docs_internal_reviews_prefix,
        test_stale_wording_catches_multiline_legacy_status_reconstruction,
        test_loop_memory_state_rejects_pre_merge_status,
        test_loop_memory_state_accepts_merged_fixture,
        test_loop_memory_state_rejects_known_merged_pr_staleness,
        test_pr_templates_share_merge_intent_contract,
        test_contributor_entry_semantics_are_positive_and_fail_closed,
        test_pr_templates_share_signed_start_provenance_fields,
        test_post_merge_metadata_is_strict_and_bounded,
        test_next_chunk_contract_binding_is_exact_locally_and_remotely,
        test_post_merge_state_is_idempotent_and_monotonic,
        test_planning_intake_is_stopped_idempotent_and_new_initiative_only,
        test_planning_intake_record_schema_fails_closed,
        test_independent_checker_accepts_and_mutates_planning_intake_state,
        test_planning_tree_entries_canonicalize_recursive_directory_objects,
        test_ws_eng_007_recovery_policy_is_exactly_pinned,
        test_planning_checks_canonicalize_trusted_reruns_and_fail_closed,
        test_planning_intake_collection_binds_paths_trees_and_check_sources,
        test_eng006_exact_recovery_certificate_is_consumed_and_inert_on_replay,
        test_eng007_two_merge_recovery_binds_pr187_and_consumes_authority,
        test_post_merge_reconciliation_bootstraps_and_recovers_every_commit,
        test_loop_memory_target_resolution_rejects_stale_replays,
        test_post_merge_collection_binds_exact_pr_and_checks,
        test_generated_loop_memory_validator_detects_drift,
        test_generated_loop_memory_signature_authenticates_every_canonical_file,
        test_prepare_output_rebuilds_authenticated_renderer_drift,
        test_schema_v1_signed_state_is_discarded_before_clean_v2_bootstrap,
        test_schema_v1_ledger_and_signature_domains_fail_independently,
        test_live_and_historical_records_reject_cross_initiative_gates,
        test_loop_memory_schema_v2_rejection_matrix_is_fail_closed,
        test_generated_loop_memory_prepare_recovers_hostile_path_types,
        test_generated_loop_memory_escapes_markdown_metadata,
        test_loop_memory_workflow_isolated_write_boundary,
        test_post_merge_input_and_check_validation_fail_closed,
        test_github_client_bounds_success_and_network_failure,
        test_github_client_pagination_is_complete_and_bounded,
        test_committed_merge_intent_fails_closed_on_untrusted_github_payloads,
        test_post_merge_collection_rejects_ambiguous_or_mismatched_prs,
        test_post_merge_state_rejects_corrupt_files_and_cli_misuse,
        test_post_merge_cli_updates_and_shows_generated_state,
        test_generated_loop_memory_validator_covers_corruption_matrix,
        test_full_merge_ledger_hash_chain_detects_history_tampering,
        test_merge_ledger_rejects_schema_record_and_ancestry_corruption,
        test_stale_authorization_rule_examples_are_rejected,
        test_feature_owned_authorization_activation_is_rejected,
        test_activation_custody_discovery_includes_canonical_handoffs,
        test_auth_spec_orders_service_admission_before_project_roles,
        test_parallel_initiative_status_matches_trusted_main,
        test_stale_authorization_discovery_includes_new_untracked_docs,
        test_stale_authorization_precedence_exemption_is_line_scoped,
        test_stale_authorization_initiative_ratchet_is_position_scoped,
        test_stale_authorization_full_initiative_rules_ignore_changed_line_filter,
        test_stale_authorization_history_allowlist_is_exact,
        test_stale_review_contract_rule_inventory_is_complete,
        test_active_review_workflows_preserve_canonical_transaction_order,
        test_checker_admission_and_reject_sampling_remain_nonhuman_and_nonmutating,
        test_stale_review_contract_classification_is_exact,
        test_stale_review_contract_scan_excludes_only_exact_archives,
        test_stale_review_contract_discovery_includes_tracked_and_untracked,
        test_stale_review_contracts_run_fail_closed_in_agent_gates,
        test_agent_gates_runs_stale_authorization_docs_fail_closed,
        test_agent_gates_runs_stale_artifact_contracts_fail_closed,
        test_agent_gate_dependencies_and_workflow_are_pinned,
        test_local_minio_compose_is_regression_protected,
        test_backend_coverage_thresholds_are_regression_protected,
        test_artifact_coverage_phase_is_derived_from_work_queue,
        test_stale_artifact_contracts_cutover_rejects_reached_terms_only,
        test_stale_artifact_contracts_active_later_phase_owns_only_reached_terms,
        test_stale_artifact_contracts_malformed_phase_fails_closed,
        test_stale_artifact_contracts_enforce_aws_first_v01,
        test_stale_artifact_contracts_scan_only_current_initiatives,
        test_stale_artifact_contracts_remove_flow_node_at_store_cutover,
        test_artifact_chunk_verification_commands_are_isolated_and_rerunnable,
        test_artifact_action_registry_has_exact_owned_mappings,
        test_aws_artifact_activation_contract_is_exact_and_time_bounded,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} agent gate tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
