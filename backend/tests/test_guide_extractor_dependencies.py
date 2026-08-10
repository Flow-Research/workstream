"""Tests for the guide-extractor dependency approval gate."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError

import pytest
from packaging.requirements import Requirement

from scripts import check_guide_extractor_dependencies as gate

HEAD = "a" * 40
OTHER_HEAD = "b" * 40


def _manifest() -> dict[str, object]:
    data, _ = gate.load_manifest()
    return data


def _dependency(data: dict[str, object], name: str) -> dict[str, object]:
    dependencies = data["dependencies"]
    assert isinstance(dependencies, list)
    return next(
        dependency
        for dependency in dependencies
        if isinstance(dependency, dict) and dependency.get("name", "").casefold() == name.casefold()
    )


def _review(
    login: str = "maintainer",
    *,
    state: str = "APPROVED",
    commit_id: str = HEAD,
    association: str = "MEMBER",
    user_type: str = "User",
    review_id: int = 1,
) -> dict[str, object]:
    return {
        "author_association": association,
        "commit_id": commit_id,
        "id": review_id,
        "state": state,
        "user": {"login": login, "type": user_type},
    }


def test_repository_allowlist_is_canonical_and_valid() -> None:
    data, raw = gate.load_manifest()

    allowlist = gate.validate_manifest(data)

    assert set(allowlist) == {"pypdf", "defusedxml", "pillow"}
    assert raw == (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    assert {
        scope for entry in allowlist.values() for scope in entry["format_scopes"]
    } == gate.APPROVED_SCOPES


def test_unreadable_allowlist_fails_closed(tmp_path: Path) -> None:
    invalid = tmp_path / "allowlist.json"
    invalid.write_text("not-json")

    with pytest.raises(gate.DependencyGateError, match="guide_dependency_allowlist_unreadable"):
        gate.load_manifest(invalid)


@pytest.mark.parametrize(
    ("mutation", "failure"),
    [
        (
            lambda data: _dependency(data, "pypdf").update(version=">=6"),
            "guide_dependency_version_unpinned",
        ),
        (
            lambda data: _dependency(data, "pypdf")["approved_artifacts"][0].update(
                sha256="0" * 63
            ),
            "guide_dependency_artifact_hash_invalid",
        ),
        (
            lambda data: _dependency(data, "pypdf")["approved_artifacts"][0].update(sha256=None),
            "guide_dependency_artifact_hash_invalid",
        ),
        (
            lambda data: _dependency(data, "pypdf")["maintenance"].update(release_uploaded_at=None),
            "guide_dependency_release_timestamp_invalid",
        ),
        (
            lambda data: _dependency(data, "pypdf")["approved_artifacts"][0].update(
                filename="other-6.14.2-py3-none-any.whl"
            ),
            "guide_dependency_artifact_identity_mismatch",
        ),
        (
            lambda data: _dependency(data, "pypdf")["approved_artifacts"][0].update(
                filename="pypdf-6.13.0-py3-none-any.whl"
            ),
            "guide_dependency_artifact_identity_mismatch",
        ),
        (
            lambda data: _dependency(data, "pillow")["approved_artifacts"][0].update(
                python_version="3.13"
            ),
            "guide_dependency_artifact_platform_mismatch",
        ),
        (
            lambda data: _dependency(data, "pillow")["approved_artifacts"][0].update(
                machine="riscv64"
            ),
            "guide_dependency_artifact_platform_mismatch",
        ),
        (
            lambda data: _dependency(data, "pypdf")["approved_artifacts"][0].update(
                url="https://example.invalid/pypdf.whl"
            ),
            "guide_dependency_artifact_url_invalid",
        ),
        (
            lambda data: _dependency(data, "pypdf").update(format_scopes=["submission_zip"]),
            "guide_dependency_scope_unknown",
        ),
        (
            lambda data: _dependency(data, "pypdf").update(source_index="https://example.invalid"),
            "guide_dependency_source_index_invalid",
        ),
        (
            lambda data: data["installation_policy"].update(allow_source_distributions=True),
            "guide_dependency_sdist_allowed",
        ),
    ],
)
def test_manifest_rejects_unpinned_hash_drifted_or_wrong_scope_entries(
    mutation: object, failure: str
) -> None:
    data = copy.deepcopy(_manifest())
    mutation(data)  # type: ignore[operator]

    with pytest.raises(gate.DependencyGateError, match=failure):
        gate.validate_manifest(data)


def test_native_artifacts_cover_every_approved_python_and_machine() -> None:
    data = copy.deepcopy(_manifest())
    pillow = _dependency(data, "pillow")
    artifacts = pillow["approved_artifacts"]
    assert isinstance(artifacts, list)
    artifacts.pop()

    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_artifact_platform_coverage_incomplete",
    ):
        gate.validate_manifest(data)


def test_native_artifact_rejects_a_wheel_with_a_higher_glibc_floor() -> None:
    data = copy.deepcopy(_manifest())
    pillow = _dependency(data, "pillow")
    artifact = pillow["approved_artifacts"][0]
    filename = artifact["filename"].replace("manylinux_2_27", "manylinux_2_39")
    artifact["filename"] = filename
    artifact["url"] = artifact["url"].rsplit("/", 1)[0] + f"/{filename}"

    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_artifact_platform_mismatch",
    ):
        gate.validate_manifest(data)


def test_native_artifacts_reject_an_extra_platform_artifact() -> None:
    data = copy.deepcopy(_manifest())
    pillow = _dependency(data, "pillow")
    artifacts = pillow["approved_artifacts"]
    assert isinstance(artifacts, list)
    extra_artifact = copy.deepcopy(artifacts[0])
    filename = extra_artifact["filename"].replace("-cp311-", "-1-cp311-")
    extra_artifact["filename"] = filename
    extra_artifact["url"] = extra_artifact["url"].rsplit("/", 1)[0] + f"/{filename}"
    artifacts.append(extra_artifact)

    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_artifact_platform_coverage_incomplete",
    ):
        gate.validate_manifest(data)


def test_declared_parser_dependency_must_use_exact_approved_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\ndependencies = ["pypdf>=6"]\n')
    monkeypatch.setattr(gate, "PYPROJECT_PATH", pyproject)
    data = _manifest()
    allowlist = gate.validate_manifest(data)

    with pytest.raises(
        gate.DependencyGateError, match="guide_dependency_declared_artifact_mismatch"
    ):
        gate.validate_declared_dependencies(allowlist, data["prohibited_packages"])


def test_exact_declared_parser_pin_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _manifest()
    allowlist = gate.validate_manifest(data)
    approved_requirement = next(iter(gate._approved_requirements(allowlist["pypdf"])))
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f"[project]\ndependencies = [{approved_requirement!r}]\n")
    monkeypatch.setattr(gate, "PYPROJECT_PATH", pyproject)

    gate.validate_declared_dependencies(allowlist, data["prohibited_packages"])


def test_approved_conditional_wheel_requirements_are_valid_pep508() -> None:
    allowlist = gate.validate_manifest(_manifest())
    requirements = gate._approved_requirements(allowlist["pillow"])

    assert len(requirements) == 4
    parsed = [Requirement(requirement) for requirement in requirements]
    assert {str(requirement.marker) for requirement in parsed} == {
        'python_version == "3.11" and sys_platform == "linux" and platform_machine == "aarch64" and platform_python_implementation == "CPython"',
        'python_version == "3.11" and sys_platform == "linux" and platform_machine == "x86_64" and platform_python_implementation == "CPython"',
        'python_version == "3.12" and sys_platform == "linux" and platform_machine == "aarch64" and platform_python_implementation == "CPython"',
        'python_version == "3.12" and sys_platform == "linux" and platform_machine == "x86_64" and platform_python_implementation == "CPython"',
    }


def test_native_parser_rejects_project_python_outside_approved_wheels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _manifest()
    allowlist = gate.validate_manifest(data)
    pillow = sorted(gate._approved_requirements(allowlist["pillow"]))
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nrequires-python = ">=3.11"\ndependencies = ' + repr(pillow) + "\n"
    )
    monkeypatch.setattr(gate, "PYPROJECT_PATH", pyproject)

    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_project_python_range_unsupported",
    ):
        gate.validate_declared_dependencies(allowlist, data["prohibited_packages"])


@pytest.mark.parametrize(
    "facts,failure",
    [
        ({"python_version": (3, 13)}, "guide_dependency_runtime_python_unsupported"),
        ({"implementation": "PyPy"}, "guide_dependency_runtime_platform_unsupported"),
        ({"system": "Darwin"}, "guide_dependency_runtime_platform_unsupported"),
        ({"machine": "riscv64"}, "guide_dependency_runtime_platform_unsupported"),
        ({"libc": "musl"}, "guide_dependency_runtime_platform_unsupported"),
        ({"libc_version": "2.26"}, "guide_dependency_runtime_platform_unsupported"),
    ],
)
def test_native_parser_runtime_fails_outside_approved_wheel_platform(
    facts: dict[str, object], failure: str
) -> None:
    runtime = {
        "python_version": (3, 12),
        "implementation": "CPython",
        "system": "Linux",
        "machine": "x86_64",
        "libc": "glibc",
        "libc_version": "2.36",
    }
    runtime.update(facts)
    with pytest.raises(gate.DependencyGateError, match=failure):
        gate.validate_runtime_platform(**runtime)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("python_version", "machine"),
    [
        ((3, 11), "aarch64"),
        ((3, 11), "x86_64"),
        ((3, 12), "aarch64"),
        ((3, 12), "x86_64"),
    ],
)
def test_approved_native_runtime_platform_passes(
    python_version: tuple[int, int], machine: str
) -> None:
    gate.validate_runtime_platform(
        python_version=python_version,
        implementation="CPython",
        system="Linux",
        machine=machine,
        libc="glibc",
        libc_version="2.36",
    )


@pytest.mark.parametrize("table", ["project.optional-dependencies", "dependency-groups"])
def test_optional_or_dependency_group_parser_declaration_is_forbidden(
    table: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f'[project]\ndependencies = []\n[{table}]\ndev = ["pypdf>=6"]\n')
    monkeypatch.setattr(gate, "PYPROJECT_PATH", pyproject)
    data = _manifest()

    with pytest.raises(
        gate.DependencyGateError, match="guide_dependency_parser_non_runtime_declaration"
    ):
        gate.validate_declared_dependencies(
            gate.validate_manifest(data), data["prohibited_packages"]
        )


def test_explicitly_prohibited_parser_package_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\ndependencies = ["python-docx==1.2.0"]\n')
    monkeypatch.setattr(gate, "PYPROJECT_PATH", pyproject)
    data = _manifest()

    with pytest.raises(
        gate.DependencyGateError, match="guide_dependency_prohibited_package_declared"
    ):
        gate.validate_declared_dependencies(
            gate.validate_manifest(data), data["prohibited_packages"]
        )


def test_parser_module_rejects_undeclared_third_party_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser_root = tmp_path / "app" / "modules" / "artifacts"
    parser_root.mkdir(parents=True)
    (parser_root / "guide_pdf.py").write_text("import arbitrary_pdf_plugin\n")
    monkeypatch.setattr(gate, "BACKEND_ROOT", tmp_path)
    allowlist = gate.validate_manifest(_manifest())

    with pytest.raises(gate.DependencyGateError, match="guide_dependency_parser_import_undeclared"):
        gate.validate_parser_imports(allowlist)


def test_parser_module_requires_matching_runtime_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser_root = tmp_path / "app" / "modules" / "artifacts"
    parser_root.mkdir(parents=True)
    (parser_root / "guide_images.py").write_text("from PIL import Image\n")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\ndependencies = []\n")
    monkeypatch.setattr(gate, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(gate, "PYPROJECT_PATH", pyproject)

    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_parser_runtime_declaration_missing",
    ):
        gate.validate_parser_imports(gate.validate_manifest(_manifest()))


def test_parser_module_allows_stdlib_project_and_approved_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser_root = tmp_path / "app" / "modules" / "artifacts"
    parser_root.mkdir(parents=True)
    (parser_root / "guide_pdf.py").write_text(
        "import json\nfrom app.core import config\nfrom pypdf import PdfReader\n"
    )
    monkeypatch.setattr(gate, "BACKEND_ROOT", tmp_path)

    gate.validate_parser_imports(gate.validate_manifest(_manifest()))


@pytest.mark.parametrize(
    ("module_name", "source"),
    [
        ("guide_images.py", "import pypdf\n"),
        ("guide_pdf.py", "from PIL import Image\n"),
    ],
)
def test_parser_module_rejects_approved_dependency_from_wrong_format_scope(
    module_name: str, source: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser_root = tmp_path / "app" / "modules" / "artifacts"
    parser_root.mkdir(parents=True)
    (parser_root / module_name).write_text(source)
    monkeypatch.setattr(gate, "BACKEND_ROOT", tmp_path)

    with pytest.raises(gate.DependencyGateError, match="guide_dependency_parser_import_undeclared"):
        gate.validate_parser_imports(gate.validate_manifest(_manifest()))


def test_exact_head_independent_member_approval_passes() -> None:
    approval = gate.validate_reviews([_review()], author="contributor", head_sha=HEAD)

    assert approval["id"] == 1


@pytest.mark.parametrize(
    "reviews",
    [
        [],
        [_review("contributor")],
        [_review("coderabbitai[bot]", user_type="Bot")],
        [_review(commit_id=OTHER_HEAD)],
        [_review(association="NONE")],
        [_review(state="DISMISSED")],
    ],
)
def test_missing_self_bot_stale_untrusted_or_dismissed_approval_fails(
    reviews: list[dict[str, object]],
) -> None:
    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_independent_head_approval_missing",
    ):
        gate.validate_reviews(reviews, author="contributor", head_sha=HEAD)


def test_latest_review_by_same_reviewer_must_remain_approved() -> None:
    reviews = [
        _review(review_id=1),
        _review(state="CHANGES_REQUESTED", review_id=2),
    ]

    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_independent_head_approval_missing",
    ):
        gate.validate_reviews(reviews, author="contributor", head_sha=HEAD)


def test_later_commented_review_does_not_erase_current_approval() -> None:
    reviews = [
        _review(review_id=1),
        _review(state="COMMENTED", review_id=2),
    ]

    approval = gate.validate_reviews(reviews, author="contributor", head_sha=HEAD)

    assert approval["id"] == 1


def test_changed_allowlist_requires_live_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate, "allowlist_changed", lambda _base, _head: True)
    monkeypatch.setattr(gate, "fetch_reviews", lambda *_args: [])
    monkeypatch.setenv("WORKSTREAM_PR_BASE_SHA", OTHER_HEAD)
    monkeypatch.setenv("WORKSTREAM_PR_HEAD_SHA", HEAD)
    monkeypatch.setenv("WORKSTREAM_PR_AUTHOR", "contributor")
    monkeypatch.setenv("WORKSTREAM_PR_NUMBER", "42")
    monkeypatch.setenv("GITHUB_REPOSITORY", "Flow-Research/workstream")
    monkeypatch.setenv("GITHUB_TOKEN", "read-only-test-token")

    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_independent_head_approval_missing",
    ):
        gate.validate_pr_approval(b"changed allowlist")


def test_unchanged_allowlist_needs_no_live_pr_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate, "allowlist_changed", lambda _base, _head: False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    gate.validate_pr_approval(b"unchanged allowlist")


def test_github_api_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise HTTPError("https://api.github.test", 503, "unavailable", {}, None)

    monkeypatch.setattr(gate.urllib.request, "urlopen", unavailable)

    with pytest.raises(
        gate.DependencyGateError,
        match="guide_dependency_github_reviews_unavailable",
    ):
        gate.fetch_reviews("Flow-Research/workstream", 42, "read-only-test-token")


def test_github_review_fetch_returns_valid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps([_review()]).encode()

    monkeypatch.setattr(gate.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    reviews = gate.fetch_reviews("Flow-Research/workstream", 42, "read-only-test-token")

    assert reviews == [_review()]


def test_changed_allowlist_with_current_approval_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gate, "allowlist_changed", lambda _base, _head: True)
    monkeypatch.setattr(gate, "fetch_reviews", lambda *_args: [_review()])
    monkeypatch.setenv("WORKSTREAM_PR_BASE_SHA", OTHER_HEAD)
    monkeypatch.setenv("WORKSTREAM_PR_HEAD_SHA", HEAD)
    monkeypatch.setenv("WORKSTREAM_PR_AUTHOR", "contributor")
    monkeypatch.setenv("WORKSTREAM_PR_NUMBER", "42")
    monkeypatch.setenv("GITHUB_REPOSITORY", "Flow-Research/workstream")
    monkeypatch.setenv("GITHUB_TOKEN", "read-only-test-token")

    gate.validate_pr_approval(b"approved allowlist")

    assert "allowlist_sha256=" in capsys.readouterr().out


def test_allowlist_changed_uses_exact_pr_range(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(command)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(gate.subprocess, "run", run)

    assert gate.allowlist_changed(OTHER_HEAD, HEAD) is True
    assert observed == [
        [
            "git",
            "diff",
            "--quiet",
            f"{OTHER_HEAD}...{HEAD}",
            "--",
            "backend/config/guide_extractor_dependencies.json",
        ]
    ]
