"""Shadow selection is diagnostic only and uncertainty cannot authorize omission."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import test_impact_shadow as shadow


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Build an isolated owner/import fixture with the canonical registry."""
    registry = tmp_path / ".ci/module-boundaries/registry.v1.json"
    registry.parent.mkdir(parents=True)
    shutil.copyfile(shadow.ROOT / ".ci/module-boundaries/registry.v1.json", registry)
    sources = {
        "backend/app/modules/artifacts/api.py": "VALUE = 1\n",
        "backend/app/modules/projects/service.py": "import app.modules.artifacts.api\n",
        "backend/app/modules/tasks/service.py": "import app.modules.projects.service\n",
        "backend/tests/test_artifacts.py": "import app.modules.artifacts.api\n",
        "backend/tests/test_tasks.py": "import app.modules.tasks.service\n",
        "backend/tests/test_reviews.py": "import app.modules.reviews.api\n",
    }
    for name, source in sources.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return tmp_path


MODULES = {"tests/test_artifacts.py", "tests/test_tasks.py", "tests/test_reviews.py"}


def test_reverse_transitive_private_and_public_consumers(repo: Path) -> None:
    report = shadow.build_report(repo, ["backend/app/modules/artifacts/api.py"], MODULES)
    assert report["impacted_owners"] == ["artifacts", "projects", "tasks"]
    assert report["mapped_candidates"] == ["tests/test_artifacts.py", "tests/test_tasks.py"]
    assert report["recommendation"] == "candidate_subset"
    assert report["execution_policy"] == "full_suite_unchanged"


def test_cycles_terminate_without_adding_unrelated_owner() -> None:
    assert shadow.impacted_owners({"a"}, {"a": {"b"}, "b": {"a"}, "c": set()}) == {"a", "b"}


@pytest.mark.parametrize("path", [
    "backend/tests/conftest.py", "backend/app/main.py", "backend/pyproject.toml",
    "backend/alembic/versions/new.py", ".commitrail/changes/example.md",
    "backend/app/modules/unknown/service.py", "backend/app/modules/tasks/__init__.py",
    "backend/app/modules/authorization/service.py", "backend/app/modules/actors/service.py",
    "backend/app/modules/compensation/service.py",
])
def test_shared_unknown_and_critical_paths_recommend_full(repo: Path, path: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("")
    report = shadow.build_report(repo, [path], MODULES)
    assert report["recommendation"] == "full_suite"
    assert report["recommended_modules"] == sorted(MODULES)
    assert report["fallback_reasons"]


@pytest.mark.parametrize("source", [
    "import app.db.models\n", "import app.modules.unknown.api\n",
    "from app.modules.tasks import *\n", "__import__('app.modules.tasks')\n",
    "def broken(\n", "from tests.helpers import value\n",
])
def test_uncertain_source_is_not_silently_omitted(repo: Path, source: str) -> None:
    (repo / "backend/tests/test_reviews.py").write_text(source)
    report = shadow.build_report(repo, ["backend/app/modules/artifacts/api.py"], MODULES)
    assert report["recommendation"] == "full_suite"
    assert report["mapped_candidates"] == ["tests/test_artifacts.py", "tests/test_tasks.py"]


def test_missing_changed_path_and_inventory_drift_recommend_full(repo: Path) -> None:
    report = shadow.build_report(repo, ["backend/app/modules/artifacts/deleted.py"], MODULES | {"tests/missing.py"})
    assert "test_catalogue_inventory_mismatch" in report["fallback_reasons"]
    assert "deleted_or_missing:backend/app/modules/artifacts/deleted.py" in report["fallback_reasons"]


def test_changed_test_is_included_without_module_imports(repo: Path) -> None:
    (repo / "backend/tests/test_reviews.py").write_text("VALUE = 1\n")
    report = shadow.build_report(repo, ["backend/tests/test_reviews.py"], MODULES)
    assert report["recommended_modules"] == ["tests/test_reviews.py"]


def test_empty_delta_and_unmapped_owner_fall_back(repo: Path) -> None:
    assert "empty_delta" in shadow.build_report(repo, [], MODULES)["fallback_reasons"]
    path = repo / "backend/app/modules/outbox/service.py"
    path.parent.mkdir(parents=True)
    path.write_text("")
    assert "no_mapped_tests_for_changed_owners" in shadow.build_report(
        repo, [path.relative_to(repo).as_posix()], MODULES
    )["fallback_reasons"]


def git(repo: Path, *args: str) -> str:
    """Use a real temporary repository for target-binding checks."""
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def test_cli_exact_target_deletion_and_dirty_rejection(repo: Path, monkeypatch, capsys) -> None:
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "backend/app/modules/artifacts/api.py").unlink()
    git(repo, "add", "-u")
    git(repo, "commit", "-m", "delete")
    head = git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(shadow, "ROOT", repo)
    monkeypatch.setattr(sys, "argv", ["shadow", "--base", base, "--head", head])
    assert shadow.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["base_sha"], report["head_sha"], report["merge_base_sha"]) == (base, head, base)
    assert "backend/app/modules/artifacts/api.py" in report["changed_files"]
    assert report["recommendation"] == "full_suite"
    assert report["catalogue_module_count"] == len({m for lane in shadow.LANES for m in lane.modules})
    (repo / "untracked").write_text("dirty")
    assert shadow.main() == 1
    assert json.loads(capsys.readouterr().out)["error"] == "dirty_checkout"
    monkeypatch.setattr(sys, "argv", ["shadow", "--base", base, "--head", base])
    assert shadow.main() == 1
    assert json.loads(capsys.readouterr().out)["error"] == "head_not_checked_out"


def test_cli_invalid_git_ref_is_visible(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["shadow", "--base", "nonexistent-shadow-ref", "--head", "HEAD"])
    assert shadow.main() == 1
    assert json.loads(capsys.readouterr().out)["recommendation"] == "full_suite"


def test_partition_registration_is_exact() -> None:
    from scripts import behavior_ownership as ownership

    current = json.loads((shadow.ROOT / ownership.PARTITION_PATH).read_text())
    trusted = json.loads(json.dumps(current))
    trusted["assignments"] = [row for row in trusted["assignments"]
                              if row["target"] != "backend/scripts/test_impact_shadow.py"]
    trusted["authority_digest"] = ownership._digest(
        {key: value for key, value in trusted.items() if key != "authority_digest"}
    )
    ownership._validate_additive_partition_transition(current, trusted)
    current["assignments"].append({"group": "shared", "target": "backend/scripts/unapproved.py"})
    with pytest.raises(ownership.BehaviorOwnershipError, match="untrusted_partition_change"):
        ownership._validate_additive_partition_transition(current, trusted)
