"""Produce a conservative, observational test-impact recommendation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from scripts.test_lane_catalogue import LANES  # noqa: E402

MAP_PATH = ROOT / ".ci/test-impact/impact_map.json"
CATALOGUE_PATH = ROOT / "backend/scripts/test_lane_catalogue.py"
SCRIPT_PATH = Path(__file__).resolve()
ALL_LANES = tuple(lane.name for lane in LANES)
SELECTOR_VERSION = 1
SHA_LENGTH = 40


class SelectionError(RuntimeError):
    """Raised when exact-target evidence cannot be established."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _read_map() -> dict[str, Any]:
    raw = MAP_PATH.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise SelectionError("impact map has an unsupported schema")
    return value


def _changed_paths(base: str, head: str) -> tuple[str, list[str]]:
    if len(base) != SHA_LENGTH or len(head) != SHA_LENGTH:
        raise SelectionError("PR base and head must be full commit SHAs")
    merge_base = _git("merge-base", base, head)
    raw = subprocess.run(
        ["git", "diff", "--name-only", "-z", f"{merge_base}...{head}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    paths = [item.decode("utf-8", errors="strict") for item in raw.split(b"\0") if item]
    if not paths:
        raise SelectionError("target diff contains no changed paths")
    if len(paths) != len(set(paths)):
        raise SelectionError("target diff contains duplicate paths")
    for path in paths:
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or "\\" in path:
            raise SelectionError(f"unsafe changed path: {path!r}")
    return merge_base, sorted(paths)


def _test_path_owner(path: str) -> tuple[str, ...] | None:
    if not path.startswith("backend/tests/") or not path.endswith(".py"):
        return None
    module_path = path.removeprefix("backend/")
    owners = tuple(lane.name for lane in LANES if module_path in lane.modules)
    return owners or None


def classify(paths: list[str], impact_map: dict[str, Any]) -> tuple[list[str], dict[str, list[str]]]:
    """Return lane recommendations and auditable per-lane causes."""
    groups = impact_map.get("lane_groups")
    source_paths = impact_map.get("source_paths")
    prefixes = impact_map.get("path_prefixes")
    if not all(isinstance(item, dict) for item in (groups, source_paths, prefixes)):
        raise SelectionError("impact map has an invalid structure")

    selected: set[str] = set()
    reasons: dict[str, list[str]] = {lane: [] for lane in ALL_LANES}
    full_run_reasons: list[str] = []

    for path in paths:
        mapping: dict[str, Any] | None = None
        if path in source_paths:
            mapping = source_paths[path]
        else:
            matching_prefixes = [prefix for prefix in prefixes if path.startswith(prefix)]
            if matching_prefixes:
                mapping = prefixes[max(matching_prefixes, key=len)]

        if mapping is not None:
            group_name = mapping.get("lane_group")
            lanes = groups.get(group_name)
            if not isinstance(lanes, list) or not lanes:
                raise SelectionError(f"invalid lane group for {path}")
            reason = f"{path}: {mapping.get('reason', 'explicit impact mapping')}"
            selected.update(lanes)
            for lane in lanes:
                reasons[lane].append(reason)
            continue

        test_owners = _test_path_owner(path)
        if test_owners is not None:
            selected.update(test_owners)
            for lane in test_owners:
                reasons[lane].append(f"{path}: changed test module belongs to this semantic lane")
            continue

        full_run_reasons.append(f"{path}: no reviewed impact mapping; recommend all lanes")

    if full_run_reasons:
        selected = set(ALL_LANES)
        for lane in ALL_LANES:
            reasons[lane].extend(full_run_reasons)
    elif not selected:
        selected = set(ALL_LANES)
        for lane in ALL_LANES:
            reasons[lane].append("no safely classifiable changed path; recommend all lanes")

    return [lane for lane in ALL_LANES if lane in selected], reasons


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "## Backend test-impact shadow report",
        "",
        "This is an advisory recommendation only. The complete required backend suite still runs.",
        "",
        f"- PR base: `{report['base_sha']}`",
        f"- PR head: `{report['head_sha']}`",
        f"- Workflow execution SHA/tree: `{report['execution_sha']}` / `{report['execution_tree_sha']}`",
        f"- Merge base: `{report['merge_base']}`",
        f"- Selector version: `{report['selector_version']}`",
        f"- Changed-path SHA-256: `{report['changed_paths_sha256']}`",
        f"- Lane catalogue SHA-256: `{report['lane_catalogue_sha256']}`",
        f"- Impact map SHA-256: `{report['impact_map_sha256']}`",
        f"- Classification status: **{report['classification_status']}**",
        "",
        "### Recommended lanes",
        "",
    ]
    for lane in report["lanes"]:
        if lane["selected"]:
            lines.append(f"- **{lane['name']}** — " + "; ".join(lane["reasons"]))
        else:
            lines.append(f"- {lane['name']} — omitted: {lane['omission_reason']}")
    lines.extend(["", "### Changed paths", ""])
    lines.extend(f"- `{path}`" for path in report["changed_paths"])
    if report.get("classification_error"):
        lines.extend(["", f"Fallback detail: `{report['classification_error']}`"])
    return "\n".join(lines) + "\n"


def build_report(base: str, head: str, execution_sha: str) -> dict[str, Any]:
    """Bind the recommendation to exact Git targets and selector inputs."""
    if _git("rev-parse", "HEAD") != execution_sha:
        raise SelectionError("checked-out execution SHA does not match the workflow target")
    tree_sha = _git("rev-parse", f"{execution_sha}^{{tree}}")
    execution_parents = _git("show", "-s", "--format=%P", execution_sha).split()
    if execution_parents != [base, head]:
        raise SelectionError("workflow execution commit is not the exact PR base/head merge")
    merge_base, paths = _changed_paths(base, head)
    if _git("rev-parse", f"{base}^{{commit}}") != base or _git("rev-parse", f"{head}^{{commit}}") != head:
        raise SelectionError("base or head does not resolve to the requested commit")
    impact_map = _read_map()
    selected, reasons = classify(paths, impact_map)
    lanes = []
    for name in ALL_LANES:
        is_selected = name in selected
        lanes.append(
            {
                "name": name,
                "selected": is_selected,
                "reasons": reasons[name] if is_selected else [],
                "omission_reason": "all changed paths have reviewed owners outside this lane" if not is_selected else None,
            }
        )
    return {
        "schema_version": 1,
        "selector_version": SELECTOR_VERSION,
        "classification_status": "classified",
        "base_sha": base,
        "head_sha": head,
        "execution_sha": execution_sha,
        "execution_tree_sha": tree_sha,
        "merge_base": merge_base,
        "changed_paths": paths,
        "changed_paths_sha256": _sha256("\0".join(paths).encode()),
        "selector_sha256": _sha256(SCRIPT_PATH.read_bytes()),
        "impact_map_sha256": _sha256(MAP_PATH.read_bytes()),
        "lane_catalogue_sha256": _sha256(CATALOGUE_PATH.read_bytes()),
        "selected_lanes": selected,
        "lanes": lanes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("PR_BASE_SHA", ""))
    parser.add_argument("--head", default=os.environ.get("PR_HEAD_SHA", ""))
    parser.add_argument("--execution-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    error: str | None = None
    try:
        report = build_report(args.base, args.head, args.execution_sha)
    except Exception as exc:  # noqa: BLE001 - any classifier fault falls back to all lanes.
        error = f"{type(exc).__name__}: {exc}"
        report = {
            "schema_version": 1,
            "selector_version": SELECTOR_VERSION,
            "classification_status": "fallback_all_lanes",
            "base_sha": args.base,
            "head_sha": args.head,
            "execution_sha": args.execution_sha,
            "execution_tree_sha": None,
            "merge_base": None,
            "changed_paths": [],
            "changed_paths_sha256": None,
            "selector_sha256": _sha256(SCRIPT_PATH.read_bytes()),
            "impact_map_sha256": _sha256(MAP_PATH.read_bytes()) if MAP_PATH.is_file() else None,
            "lane_catalogue_sha256": _sha256(CATALOGUE_PATH.read_bytes()),
            "selected_lanes": list(ALL_LANES),
            "lanes": [
                {"name": lane, "selected": True, "reasons": ["selection evidence unavailable; fail safe to all lanes"], "omission_reason": None}
                for lane in ALL_LANES
            ],
            "classification_error": error,
        }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown.write_text(_markdown(report), encoding="utf-8")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(args.markdown.read_text(encoding="utf-8"))
    print(f"Impact report: {args.json}")
    if error:
        print(f"Impact classification fell back safely to all lanes: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
