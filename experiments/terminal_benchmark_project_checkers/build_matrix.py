#!/usr/bin/env python3
"""Reduce trusted runtime observations to the fixed WS493 proof matrix."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path


SCHEMA = "workstream.terminal_benchmark_project_checker_proof.v1"
SOURCE_IDENTITIES = {
    "checker": {"/work/input": "art_workspace"},
    "builder": {
        "/cache": "sealed_cache",
        "/out/candidate.tar": "art_runtime_candidate_tar",
        "/project": "art_runtime_build_context",
    },
    "candidate": {"/tests": "art_workspace_tests"},
    "reference": {
        "/tests": "art_workspace_tests",
        "/workspace/program.py": "art_workspace_reference_solution",
    },
}


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError(f"invalid object: {path.name}")
    return value


def _ndjson(path: Path) -> list[dict[str, object]]:
    values = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    if not values or any(type(value) is not dict for value in values):
        raise ValueError(f"invalid NDJSON: {path.name}")
    return values


def _write(path: Path, value: object) -> None:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def reduce_matrix(raw: Path, head: str) -> dict[str, object]:
    interrupted = _json(raw / "interrupt.json")
    art_interrupted = _json(raw / "art-interrupt.json")
    restart = _json(raw / "restart-cleanup.json")
    complete = _json(raw / "complete-result.json")
    art_complete = _json(raw / "art-complete.json")
    launches = _ndjson(raw / "launches.ndjson")
    results = _ndjson(raw / "command-results.ndjson")

    checker_launches = [
        launch for launch in launches if launch.get("kind") == "checker"
    ]
    if (
        len(launches) != 8
        or len(checker_launches) != 2
        or len({item.get("container_id") for item in checker_launches}) != 2
        or len({item.get("name") for item in checker_launches}) != 2
        or any(
            item.get("mount_source_identities") != SOURCE_IDENTITIES["checker"]
            for item in checker_launches
        )
    ):
        raise ValueError("checker launches were not fresh")
    terminal_launches = [
        launch for launch in launches if launch.get("kind") != "checker"
    ]
    by_attempt: dict[str, list[dict[str, object]]] = defaultdict(list)
    for launch in terminal_launches:
        attempt = launch.get("attempt")
        if type(attempt) is not str or launch.get("kind") not in {
            "builder",
            "candidate",
            "reference",
        }:
            raise ValueError("launch attempt missing")
        if launch.get("mount_source_identities") != SOURCE_IDENTITIES[launch["kind"]]:
            raise ValueError("launch source identity differs")
        by_attempt[attempt].append(launch)
    complete_attempts = [
        (attempt, items)
        for attempt, items in by_attempt.items()
        if sorted(str(item.get("kind")) for item in items)
        == ["builder", "candidate", "reference", "reference", "reference"]
    ]
    interrupted_attempts = [
        (attempt, items)
        for attempt, items in by_attempt.items()
        if [str(item.get("kind")) for item in items] == ["builder"]
    ]
    if (
        len(terminal_launches) != 6
        or len(by_attempt) != 2
        or len(complete_attempts) != 1
        or len(interrupted_attempts) != 1
    ):
        raise ValueError("launch matrix differs")
    complete_attempt, _ = complete_attempts[0]
    interrupted_attempt, _ = interrupted_attempts[0]
    if (
        complete_attempt == interrupted_attempt
        or len({item.get("container_id") for item in terminal_launches}) != 6
        or len({item.get("name") for item in terminal_launches}) != 6
    ):
        raise ValueError("terminal containers were not fresh")

    starts: dict[str, list[int]] = defaultdict(list)
    for result in results:
        argv = result.get("argv")
        status = result.get("status")
        if not isinstance(argv, list) or not argv or argv[0] != "start":
            continue
        if len(argv) == 3 and argv[:2] == ["start", "--attach"]:
            name = argv[2]
        elif len(argv) == 4 and argv[:3] == ["start", "-a", "-i"]:
            name = argv[3]
        else:
            name = None
        if type(name) is not str or type(status) is not int:
            raise ValueError("container start observation is invalid")
        starts[name].append(status)
    builder_name = f"ws-terminal-builder-{complete_attempt}"
    candidate_name = f"ws-terminal-candidate-{complete_attempt}"
    reference_names = [
        f"ws-terminal-reference-{complete_attempt}-{index}" for index in range(3)
    ]
    checker_names = [str(item.get("name")) for item in checker_launches]
    interrupted_builder = f"ws-terminal-builder-{interrupted_attempt}"
    expected_starts = {
        checker_names[0]: [0],
        checker_names[1]: [0],
        builder_name: [0],
        candidate_name: [1],
        reference_names[0]: [0],
        reference_names[1]: [0],
        reference_names[2]: [0],
    }
    if dict(starts) != expected_starts or interrupted_builder in starts:
        raise ValueError("container start observations differ")

    expected_terminal_names = {
        interrupted_builder,
        builder_name,
        candidate_name,
        *reference_names,
    }
    if {str(item.get("name")) for item in terminal_launches} != expected_terminal_names:
        raise ValueError("terminal create observations differ")

    result = complete.get("result")
    if (
        interrupted.get("adapter_failure") is not True
        or art_interrupted != {"ledger_empty": True, "workspace_empty": True}
        or restart
        != {
            "owned_containers_absent": True,
            "owned_images_absent": True,
            "unowned_control_preserved": True,
        }
        or type(result) is not dict
        or result.get("outcome") != "completed"
        or result.get("verdict") != "passed"
        or result.get("findings") != []
        or art_complete != {"ledger_empty": True, "workspace_empty": True}
    ):
        raise ValueError("POST proof outcome differs")

    return {
        "schema_version": SCHEMA,
        "head_sha": head,
        "interrupted": {
            "adapter_failure": True,
            "art_unwound": True,
            "restart_swept_owned": True,
            "unowned_control_preserved": True,
        },
        "complete": {
            "builder_exit": 0,
            "candidate_exit": 1,
            "outcome": "completed",
            "owned_resources_absent": True,
            "reference_exits": [0, 0, 0],
            "stable": True,
            "verdict": "passed",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    matrix = reduce_matrix(arguments.raw, arguments.head)
    _write(arguments.output, matrix)


if __name__ == "__main__":
    main()
