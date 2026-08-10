#!/usr/bin/env python3
"""Validate the approved guide-extractor dependency boundary."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
ALLOWLIST_PATH = BACKEND_ROOT / "config" / "guide_extractor_dependencies.json"
PYPROJECT_PATH = BACKEND_ROOT / "pyproject.toml"
ALLOWLIST_REPOSITORY_PATH = ALLOWLIST_PATH.relative_to(REPOSITORY_ROOT).as_posix()
APPROVED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
APPROVED_SCOPES = frozenset({"pdf", "ooxml", "image_metadata"})
APPROVED_NATIVE_PYTHON_RANGE = ">=3.11,<3.13"
APPROVED_NATIVE_MACHINES = frozenset({"aarch64", "x86_64"})
APPROVED_RUNTIME_PLATFORMS = [
    {"libc": "glibc>=2.27", "machine": "aarch64", "system": "Linux"},
    {"libc": "glibc>=2.27", "machine": "x86_64", "system": "Linux"},
]
MINIMUM_GLIBC_VERSION = (2, 27)
STATE_BEARING_REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})
PARSER_MODULES = (
    "guide_pdf.py",
    "guide_ooxml.py",
    "guide_docx.py",
    "guide_pptx.py",
    "guide_xlsx.py",
    "guide_images.py",
)
PARSER_MODULE_SCOPES = {
    "guide_pdf.py": frozenset({"pdf"}),
    "guide_ooxml.py": frozenset({"ooxml"}),
    "guide_docx.py": frozenset({"ooxml"}),
    "guide_pptx.py": frozenset({"ooxml"}),
    "guide_xlsx.py": frozenset({"ooxml"}),
    "guide_images.py": frozenset({"image_metadata"}),
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
VERSION_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)+(?:[a-z0-9.-]*)?", re.IGNORECASE)
PACKAGE_NAME_PATTERN = re.compile(r"[-_.]+")


class DependencyGateError(RuntimeError):
    """Raised when dependency approval evidence fails closed."""


def require(condition: bool, code: str) -> None:
    """Raise one stable failure code when ``condition`` is false."""
    if not condition:
        raise DependencyGateError(code)


def _object(value: Any, code: str) -> dict[str, Any]:
    require(isinstance(value, dict), code)
    return value


def _string(value: Any, code: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), code)
    return value


def _string_list(value: Any, code: str) -> list[str]:
    require(isinstance(value, list) and bool(value), code)
    require(all(isinstance(item, str) and item.strip() for item in value), code)
    require(len(value) == len(set(value)), code)
    return value


def normalize_package_name(value: str) -> str:
    """Return the Python packaging canonical project name."""
    return PACKAGE_NAME_PATTERN.sub("-", value).lower()


def load_manifest(path: Path = ALLOWLIST_PATH) -> tuple[dict[str, Any], bytes]:
    """Load JSON while preserving the exact bytes used for the digest."""
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyGateError("guide_dependency_allowlist_unreadable") from exc
    require(isinstance(data, dict), "guide_dependency_allowlist_not_object")
    canonical = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    require(raw == canonical, "guide_dependency_allowlist_not_canonical")
    return data, raw


def validate_manifest(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate the closed v0.1 dependency allowlist schema."""
    require(
        set(data)
        == {
            "advisory_snapshot",
            "dependencies",
            "installation_policy",
            "prohibited_packages",
            "schema_version",
        },
        "guide_dependency_allowlist_top_level_shape_invalid",
    )
    require(data["schema_version"] == 2, "guide_dependency_allowlist_schema_unsupported")

    advisory = _object(data["advisory_snapshot"], "guide_dependency_advisory_invalid")
    require(
        set(advisory) == {"checked_at", "provider", "query_url"},
        "guide_dependency_advisory_shape_invalid",
    )
    require(
        re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            _string(advisory["checked_at"], "guide_dependency_advisory_date_invalid"),
        )
        is not None,
        "guide_dependency_advisory_date_invalid",
    )
    require(advisory["provider"] == "OSV", "guide_dependency_advisory_provider_invalid")
    require(
        advisory["query_url"] == "https://api.osv.dev/v1/query",
        "guide_dependency_advisory_url_invalid",
    )

    policy = _object(data["installation_policy"], "guide_dependency_policy_invalid")
    require(
        set(policy)
        == {
            "allow_source_distributions",
            "approved_python_versions",
            "approved_runtime_platforms",
            "index",
            "require_hashes",
        },
        "guide_dependency_policy_shape_invalid",
    )
    require(policy["allow_source_distributions"] is False, "guide_dependency_sdist_allowed")
    require(policy["require_hashes"] is True, "guide_dependency_hashes_not_required")
    require(policy["index"] == "https://pypi.org/simple", "guide_dependency_index_invalid")
    require(
        policy["approved_python_versions"] == ["3.11", "3.12"],
        "guide_dependency_python_versions_invalid",
    )
    require(
        policy["approved_runtime_platforms"] == APPROVED_RUNTIME_PLATFORMS,
        "guide_dependency_platform_invalid",
    )
    prohibited_packages = _string_list(
        data["prohibited_packages"], "guide_dependency_prohibited_packages_invalid"
    )
    prohibited_canonical = {normalize_package_name(item) for item in prohibited_packages}
    require(
        len(prohibited_canonical) == len(prohibited_packages),
        "guide_dependency_prohibited_packages_duplicate",
    )

    dependencies = data["dependencies"]
    require(isinstance(dependencies, list) and dependencies, "guide_dependency_entries_missing")
    by_name: dict[str, dict[str, Any]] = {}
    observed_scopes: set[str] = set()
    observed_imports: set[str] = set()
    for entry_value in dependencies:
        entry = _object(entry_value, "guide_dependency_entry_invalid")
        require(
            set(entry)
            == {
                "advisories",
                "approved_artifacts",
                "cancellation_timeout_implications",
                "direct",
                "format_scopes",
                "import_names",
                "license",
                "maintenance",
                "malformed_input_history",
                "name",
                "native_code",
                "network_behavior",
                "source_index",
                "transitive_dependencies",
                "version",
            },
            "guide_dependency_entry_shape_invalid",
        )
        name = _string(entry["name"], "guide_dependency_name_invalid")
        canonical_name = normalize_package_name(name)
        require(canonical_name not in by_name, "guide_dependency_name_duplicate")
        version = _string(entry["version"], "guide_dependency_version_invalid")
        require(VERSION_PATTERN.fullmatch(version) is not None, "guide_dependency_version_unpinned")
        require(entry["direct"] is True, "guide_dependency_must_be_direct")
        require(isinstance(entry["native_code"], bool), "guide_dependency_native_flag_invalid")
        require(entry["source_index"] == policy["index"], "guide_dependency_source_index_invalid")
        _string(entry["license"], "guide_dependency_license_missing")
        _string(entry["malformed_input_history"], "guide_dependency_history_missing")
        _string(entry["network_behavior"], "guide_dependency_network_behavior_missing")
        _string(
            entry["cancellation_timeout_implications"],
            "guide_dependency_cancellation_implications_missing",
        )

        scopes = _string_list(entry["format_scopes"], "guide_dependency_scope_invalid")
        require(set(scopes) <= APPROVED_SCOPES, "guide_dependency_scope_unknown")
        require(not observed_scopes.intersection(scopes), "guide_dependency_scope_ambiguous")
        observed_scopes.update(scopes)

        imports = _string_list(entry["import_names"], "guide_dependency_imports_invalid")
        require(not observed_imports.intersection(imports), "guide_dependency_import_ambiguous")
        observed_imports.update(imports)

        transitive = entry["transitive_dependencies"]
        require(isinstance(transitive, list), "guide_dependency_transitive_graph_invalid")
        require(
            all(isinstance(item, str) and item.strip() for item in transitive),
            "guide_dependency_transitive_graph_invalid",
        )
        require(len(transitive) == len(set(transitive)), "guide_dependency_transitive_duplicate")

        advisories = entry["advisories"]
        require(isinstance(advisories, list), "guide_dependency_advisories_invalid")
        require(
            all(isinstance(item, str) and item.strip() for item in advisories),
            "guide_dependency_advisories_invalid",
        )

        maintenance = _object(entry["maintenance"], "guide_dependency_maintenance_invalid")
        require(
            set(maintenance) == {"assessment", "release_uploaded_at", "source_url"},
            "guide_dependency_maintenance_shape_invalid",
        )
        _string(maintenance["assessment"], "guide_dependency_maintenance_assessment_missing")
        release_uploaded_at = _string(
            maintenance["release_uploaded_at"], "guide_dependency_release_timestamp_invalid"
        )
        require(
            release_uploaded_at.endswith("Z"),
            "guide_dependency_release_timestamp_invalid",
        )
        require(
            _string(maintenance["source_url"], "guide_dependency_source_url_missing").startswith(
                "https://"
            ),
            "guide_dependency_source_url_invalid",
        )

        artifacts = entry["approved_artifacts"]
        require(isinstance(artifacts, list) and artifacts, "guide_dependency_artifacts_missing")
        filenames: set[str] = set()
        native_platforms: set[tuple[str, str]] = set()
        for artifact_value in artifacts:
            artifact = _object(artifact_value, "guide_dependency_artifact_invalid")
            expected_artifact_keys = {"filename", "sha256", "url"}
            if entry["native_code"]:
                expected_artifact_keys.update({"machine", "python_version"})
            require(
                set(artifact) == expected_artifact_keys, "guide_dependency_artifact_shape_invalid"
            )
            filename = _string(artifact["filename"], "guide_dependency_artifact_name_invalid")
            require(filename.endswith(".whl"), "guide_dependency_artifact_not_wheel")
            require(filename not in filenames, "guide_dependency_artifact_duplicate")
            filenames.add(filename)
            artifact_sha256 = _string(artifact["sha256"], "guide_dependency_artifact_hash_invalid")
            require(
                SHA256_PATTERN.fullmatch(artifact_sha256) is not None,
                "guide_dependency_artifact_hash_invalid",
            )
            wheel_prefix = f"{canonical_name.replace('-', '_')}-{version}-"
            require(
                filename.lower().startswith(wheel_prefix),
                "guide_dependency_artifact_identity_mismatch",
            )
            url = _string(artifact["url"], "guide_dependency_artifact_url_invalid")
            require(
                url.startswith("https://files.pythonhosted.org/packages/")
                and url.endswith(f"/{filename}"),
                "guide_dependency_artifact_url_invalid",
            )
            if entry["native_code"]:
                python_version = _string(
                    artifact["python_version"], "guide_dependency_artifact_python_invalid"
                )
                machine = _string(
                    artifact["machine"], "guide_dependency_artifact_platform_mismatch"
                )
                compact_python = python_version.replace(".", "")
                expected_wheel_suffix = (
                    f"-cp{compact_python}-cp{compact_python}-"
                    f"manylinux_2_27_{machine}.manylinux_2_28_{machine}.whl"
                )
                require(
                    python_version in policy["approved_python_versions"]
                    and machine in APPROVED_NATIVE_MACHINES
                    and filename.endswith(expected_wheel_suffix),
                    "guide_dependency_artifact_platform_mismatch",
                )
                native_platforms.add((python_version, machine))
            else:
                require(
                    filename.endswith("-none-any.whl"),
                    "guide_dependency_artifact_platform_mismatch",
                )
        if entry["native_code"]:
            expected_native_platforms = {
                (python_version, machine)
                for python_version in policy["approved_python_versions"]
                for machine in APPROVED_NATIVE_MACHINES
            }
            require(
                native_platforms == expected_native_platforms
                and len(artifacts) == len(expected_native_platforms),
                "guide_dependency_artifact_platform_coverage_incomplete",
            )
        by_name[canonical_name] = entry

    require(observed_scopes == APPROVED_SCOPES, "guide_dependency_scope_incomplete")
    require(
        not prohibited_canonical.intersection(by_name),
        "guide_dependency_prohibited_package_approved",
    )
    return by_name


def _dependency_name(requirement: str) -> str:
    return normalize_package_name(re.split(r"[<>=!~\s;\[]", requirement.strip(), 1)[0])


def _approved_requirements(entry: dict[str, Any]) -> set[str]:
    """Build the only hash-bound direct references approved for one package."""
    requirements: set[str] = set()
    for artifact in entry["approved_artifacts"]:
        requirement = f"{entry['name']} @ {artifact['url']}#sha256={artifact['sha256']}"
        if python_version := artifact.get("python_version"):
            requirement += (
                f' ; python_version == "{python_version}"'
                ' and sys_platform == "linux"'
                f' and platform_machine == "{artifact["machine"]}"'
                ' and platform_python_implementation == "CPython"'
            )
        requirements.add(requirement)
    return requirements


def validate_declared_dependencies(
    allowlist: dict[str, dict[str, Any]], prohibited_packages: list[str]
) -> None:
    """Require runtime parser declarations to bind exact approved wheel bytes."""
    with PYPROJECT_PATH.open("rb") as handle:
        pyproject = tomllib.load(handle)
    project = pyproject["project"]
    runtime_requirements = project.get("dependencies", [])
    optional_requirements = [
        item for group in project.get("optional-dependencies", {}).values() for item in group
    ]
    dependency_group_requirements = [
        item for group in pyproject.get("dependency-groups", {}).values() for item in group
    ]
    prohibited = {normalize_package_name(item) for item in prohibited_packages}
    for requirement in [
        *runtime_requirements,
        *optional_requirements,
        *dependency_group_requirements,
    ]:
        require(
            _dependency_name(requirement) not in prohibited,
            "guide_dependency_prohibited_package_declared",
        )
    for requirement in [*optional_requirements, *dependency_group_requirements]:
        require(
            _dependency_name(requirement) not in allowlist,
            "guide_dependency_parser_non_runtime_declaration",
        )
    requirements_by_name: dict[str, set[str]] = {}
    for requirement in runtime_requirements:
        requirements_by_name.setdefault(_dependency_name(requirement), set()).add(requirement)
    for name, entry in allowlist.items():
        requirements = requirements_by_name.get(name)
        if requirements is None:
            continue
        if entry["native_code"]:
            require(
                project.get("requires-python") == APPROVED_NATIVE_PYTHON_RANGE,
                "guide_dependency_project_python_range_unsupported",
            )
        require(
            requirements == _approved_requirements(entry),
            "guide_dependency_declared_artifact_mismatch",
        )


def validate_runtime_platform(
    *,
    python_version: tuple[int, int] | None = None,
    implementation: str | None = None,
    system: str | None = None,
    machine: str | None = None,
    libc: str | None = None,
    libc_version: str | None = None,
) -> None:
    """Fail unless this process matches the approved native-wheel runtime."""
    current_python = python_version or sys.version_info[:2]
    current_system = system or platform.system()
    current_machine = machine or platform.machine()
    current_implementation = implementation or platform.python_implementation()
    detected_libc, detected_libc_version = platform.libc_ver()
    current_libc = libc or detected_libc
    current_libc_version = libc_version or detected_libc_version
    require(
        current_python in {(3, 11), (3, 12)},
        "guide_dependency_runtime_python_unsupported",
    )
    require(
        current_implementation == "CPython"
        and current_system == "Linux"
        and current_machine in APPROVED_NATIVE_MACHINES
        and current_libc == "glibc",
        "guide_dependency_runtime_platform_unsupported",
    )
    glibc_match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", current_libc_version)
    require(
        glibc_match is not None
        and tuple(int(part) for part in glibc_match.groups()) >= MINIMUM_GLIBC_VERSION,
        "guide_dependency_runtime_platform_unsupported",
    )


def validate_parser_imports(allowlist: dict[str, dict[str, Any]]) -> None:
    """Reject undeclared third-party imports in format-specific parser modules."""
    parser_root = BACKEND_ROOT / "app" / "modules" / "artifacts"
    with PYPROJECT_PATH.open("rb") as handle:
        runtime_requirements = tomllib.load(handle)["project"].get("dependencies", [])
    declared_names = {_dependency_name(requirement) for requirement in runtime_requirements}
    for module_name in PARSER_MODULES:
        module_path = parser_root / module_name
        if not module_path.exists():
            continue
        scoped_dependencies = {
            name
            for name, entry in allowlist.items()
            if set(entry["format_scopes"]) & PARSER_MODULE_SCOPES[module_name]
        }
        require(
            scoped_dependencies <= declared_names,
            "guide_dependency_parser_runtime_declaration_missing",
        )
        approved_imports = {
            import_name.split(".", 1)[0]
            for entry in allowlist.values()
            if set(entry["format_scopes"]) & PARSER_MODULE_SCOPES[module_name]
            for import_name in entry["import_names"]
        }
        tree = ast.parse(module_path.read_text(), filename=str(module_path))
        for node in ast.walk(tree):
            imported: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    require(
                        root in sys.stdlib_module_names
                        or root == "app"
                        or root in approved_imports,
                        "guide_dependency_parser_import_undeclared",
                    )
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported = node.module.split(".", 1)[0]
            if imported is not None:
                require(
                    imported in sys.stdlib_module_names
                    or imported == "app"
                    or imported in approved_imports,
                    "guide_dependency_parser_import_undeclared",
                )


def allowlist_changed(base_sha: str, head_sha: str) -> bool:
    """Return whether the exact allowlist bytes differ across the PR range."""
    require(bool(re.fullmatch(r"[0-9a-f]{40}", base_sha)), "guide_dependency_base_sha_invalid")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", head_sha)), "guide_dependency_head_sha_invalid")
    result = subprocess.run(
        ["git", "diff", "--quiet", f"{base_sha}...{head_sha}", "--", ALLOWLIST_REPOSITORY_PATH],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    require(result.returncode in {0, 1}, "guide_dependency_git_diff_failed")
    return result.returncode == 1


def validate_reviews(
    reviews: list[dict[str, Any]], *, author: str, head_sha: str
) -> dict[str, Any]:
    """Return one current independent approval or fail closed."""
    require(bool(author), "guide_dependency_pr_author_missing")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", head_sha)), "guide_dependency_head_sha_invalid")
    latest_by_reviewer: dict[str, dict[str, Any]] = {}
    for review in reviews:
        require(isinstance(review, dict), "guide_dependency_review_shape_invalid")
        user = review.get("user")
        require(isinstance(user, dict), "guide_dependency_review_user_missing")
        login = user.get("login")
        require(isinstance(login, str) and login, "guide_dependency_review_login_missing")
        if review.get("state") not in STATE_BEARING_REVIEW_STATES:
            continue
        latest_by_reviewer[login.casefold()] = review

    candidates: list[dict[str, Any]] = []
    for login, review in latest_by_reviewer.items():
        user = review["user"]
        if login == author.casefold():
            continue
        if user.get("type") != "User" or login.endswith("[bot]"):
            continue
        if review.get("author_association") not in APPROVED_ASSOCIATIONS:
            continue
        if review.get("state") != "APPROVED":
            continue
        if review.get("commit_id") != head_sha:
            continue
        candidates.append(review)
    require(bool(candidates), "guide_dependency_independent_head_approval_missing")
    return candidates[-1]


def fetch_reviews(repository: str, pull_number: int, token: str) -> list[dict[str, Any]]:
    """Read every PR review using the minimal read-only GitHub token."""
    require(bool(re.fullmatch(r"[^/]+/[^/]+", repository)), "guide_dependency_repository_invalid")
    require(pull_number > 0, "guide_dependency_pull_number_invalid")
    require(bool(token), "guide_dependency_github_token_missing")
    reviews: list[dict[str, Any]] = []
    page = 1
    while True:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/pulls/{pull_number}/reviews?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "workstream-guide-dependency-gate",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise DependencyGateError("guide_dependency_github_reviews_unavailable") from exc
        require(isinstance(payload, list), "guide_dependency_github_reviews_invalid")
        reviews.extend(payload)
        if len(payload) < 100:
            return reviews
        page += 1


def validate_pr_approval(raw_allowlist: bytes) -> None:
    """Validate live review authority when this PR changes the allowlist."""
    base_sha = os.environ.get("WORKSTREAM_PR_BASE_SHA", "")
    head_sha = os.environ.get("WORKSTREAM_PR_HEAD_SHA", "")
    if not allowlist_changed(base_sha, head_sha):
        return
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    author = os.environ.get("WORKSTREAM_PR_AUTHOR", "")
    pull_number_value = os.environ.get("WORKSTREAM_PR_NUMBER", "")
    require(pull_number_value.isdigit(), "guide_dependency_pull_number_invalid")
    reviews = fetch_reviews(
        repository,
        int(pull_number_value),
        os.environ.get("GITHUB_TOKEN", ""),
    )
    approval = validate_reviews(reviews, author=author, head_sha=head_sha)
    digest = hashlib.sha256(raw_allowlist).hexdigest()
    print(
        "Guide dependency approval: "
        f"review={approval.get('id')} head={head_sha} allowlist_sha256={digest}"
    )


def parse_args() -> argparse.Namespace:
    """Parse the small CI-facing command surface."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-pr-approval",
        action="store_true",
        help="Require live exact-head review authority when the PR changes the allowlist.",
    )
    return parser.parse_args()


def main() -> int:
    """Run static validation and the optional live PR approval gate."""
    args = parse_args()
    try:
        data, raw = load_manifest()
        allowlist = validate_manifest(data)
        validate_declared_dependencies(allowlist, data["prohibited_packages"])
        validate_runtime_platform()
        validate_parser_imports(allowlist)
        if args.require_pr_approval:
            validate_pr_approval(raw)
    except DependencyGateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Guide extractor dependency gate passed ({hashlib.sha256(raw).hexdigest()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
