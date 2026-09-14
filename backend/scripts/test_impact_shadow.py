"""Report conservative test-module candidates; never control test execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from scripts.authorization_boundary import AuthorizationBoundaryError, source_imports
from scripts.module_boundaries import ModuleBoundaryError, load_registry
from scripts.test_lane_catalogue import LANES

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "scripts"))
from git_delta import resolve_commit, resolve_merge_base, run_checked  # noqa: E402


def owner(path: str, names: frozenset[str]) -> str | None:
    """Recognize only a registered canonical module path."""
    parts = path.split("/")
    if len(parts) > 4 and parts[:3] == ["backend", "app", "modules"]:
        return parts[3] if parts[3] in names else None
    return None


def impacted_owners(changed: set[str], dependencies: dict[str, set[str]]) -> set[str]:
    """Follow reverse dependencies to a fixed point, including cycles."""
    result = set(changed)
    while True:
        expanded = result | {name for name, imports in dependencies.items() if imports & result}
        if expanded == result:
            return result
        result = expanded


def build_report(root: Path, changed: list[str], modules: set[str]) -> dict:
    """Inspect sources without executing them; uncertainty recommends the full suite."""
    reasons: set[str] = set()
    changed_owners: set[str] = set()
    selected: set[str] = set()
    names = load_registry(root / ".ci/module-boundaries/registry.v1.json").names
    dependencies = {name: set() for name in names}
    test_owners: dict[str, set[str]] = {}

    for path in changed:
        module_owner = owner(path, names)
        if not (root / path).is_file():
            reasons.add(f"deleted_or_missing:{path}")
        elif module_owner and path.endswith(".py") and not path.endswith("/__init__.py"):
            changed_owners.add(module_owner)
            if module_owner in {"authorization", "actors", "compensation"}:
                reasons.add(f"critical_owner:{module_owner}")
        elif path.startswith("backend/") and path.removeprefix("backend/") in modules:
            selected.add(path.removeprefix("backend/"))
        else:
            reasons.add(f"shared_or_unclassified:{path}")

    inventory = {p.relative_to(root / "backend").as_posix()
                 for p in (root / "backend/tests").rglob("test_*.py")}
    if inventory != modules:
        reasons.add("test_catalogue_inventory_mismatch")

    # This deliberately does not guess at dynamic imports, fixtures or composition.
    # Even one unknown dependency makes the proposed subset unsuitable for execution.
    paths = sorted((root / "backend/app/modules").rglob("*.py"))
    paths += [root / "backend" / name for name in sorted(modules)]
    for path in paths:
        relative = path.relative_to(root).as_posix()
        source_owner = owner(relative, names)
        imports: set[str] = set()
        try:
            targets = source_imports(path, root)
        except AuthorizationBoundaryError:
            reasons.add(f"unresolved_source:{relative}")
            continue
        for target in targets:
            parts = target.split(".")
            if len(parts) >= 3 and parts[:2] == ["app", "modules"] and parts[2] in names:
                imports.add(parts[2])
            elif target == "app" or target.startswith(("app.", "tests", "scripts")):
                reasons.add(f"shared_or_unresolved_import:{relative}:{target}")
        if source_owner:
            dependencies[source_owner].update(imports - {source_owner})
        elif relative.startswith("backend/tests/"):
            test_owners[relative.removeprefix("backend/")] = imports
        else:
            reasons.add(f"unclassified_source:{relative}")

    affected = impacted_owners(changed_owners, dependencies)
    selected.update(name for name, imports in test_owners.items() if imports & affected)
    if changed_owners and not selected:
        reasons.add("no_mapped_tests_for_changed_owners")
    if not changed:
        reasons.add("empty_delta")
    candidates = sorted(selected)
    return {
        "mode": "shadow_only",
        "execution_policy": "full_suite_unchanged",
        "recommendation": "full_suite" if reasons else "candidate_subset",
        "changed_files": sorted(changed),
        "impacted_owners": sorted(affected),
        "mapped_candidates": candidates,
        "recommended_modules": sorted(modules) if reasons else candidates,
        "catalogue_module_count": len(modules),
        "fallback_reasons": sorted(reasons),
        "limitations": "Static owner mapping is not proof of safe omission or measured runtime savings.",
    }


def main() -> int:
    """Bind the read-only report to the exact checked-out committed target."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        head = resolve_commit(args.head, repository_root=ROOT)
        base = resolve_commit(args.base, repository_root=ROOT)
        if resolve_commit("HEAD", repository_root=ROOT) != head:
            raise ValueError("head_not_checked_out")
        if run_checked(["git", "status", "--porcelain"], repository_root=ROOT).strip():
            raise ValueError("dirty_checkout")
        merge_base = resolve_merge_base(base, head, repository_root=ROOT)
        # No rename folding: a removed path must remain visible to the fallback.
        delta = run_checked(["git", "diff", "--no-renames", "--name-only", "-z",
                             merge_base, head], repository_root=ROOT)
        modules = {module for lane in LANES for module in lane.modules}
        report = build_report(ROOT, [path for path in delta.split("\0") if path], modules)
        report.update(base_sha=base, merge_base_sha=merge_base, head_sha=head)
    except (RuntimeError, ValueError, OSError, ModuleBoundaryError) as exc:
        print(json.dumps({"mode": "shadow_only", "execution_policy": "full_suite_unchanged",
                          "recommendation": "full_suite", "error": str(exc)}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
