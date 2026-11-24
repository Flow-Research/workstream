"""Run one remote PRE launch fault through the existing public journey fixture."""

import asyncio
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import urlsplit

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from experiments.pilot04_external_checker_runtime.public_runner_faults import (
    RunnerFaultProfile,
    RunnerFaults,
)
from submission_work import _package


PROFILE_FIELDS = frozenset(
    {
        "host",
        "identity_file",
        "known_hosts_file",
        "source_root",
        "control_root",
        "run_id",
        "binding_sha256",
        "image_digest",
    }
)


def load_fault_profile(environment: dict[str, str]) -> RunnerFaultProfile:
    """Require an independently prepared, private runner pin before fixture startup."""
    raw = environment.get("WORKSTREAM_CLI_JOURNEY_FAULT_PROFILE_FILE", "")
    path = Path(raw)
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
        or not 0 < path.stat().st_size <= 16_384
    ):
        raise RuntimeError("journey requires a private fault profile")

    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate fault profile field")
            value[key] = item
        return value

    body = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    if type(body) is not dict or set(body) != PROFILE_FIELDS:
        raise RuntimeError("fault profile fields differ")
    profile = RunnerFaultProfile(
        **(body | {
            "identity_file": Path(body["identity_file"]),
            "known_hosts_file": Path(body["known_hosts_file"]),
        })
    )
    profile.validate()
    if profile.image_digest != environment.get("WORKSTREAM_CLI_JOURNEY_CHECKER_IMAGE_DIGEST"):
        raise RuntimeError("fault profile image differs from approved guide")
    return profile


async def _run(
    origin: str,
    environment: dict[str, str],
    task: str,
    assignment: str,
    token: str,
    archive: bytes,
    profile: RunnerFaultProfile,
    stop_worker,
    start_worker,
):
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / "backend" / "tests"))
    sys.path.insert(0, str(root / "backend" / "scripts"))
    from experiments.pilot04_external_checker_runtime.public_runtime_trials import (
        public_pre_launch_failure,
    )

    database_url = environment["WORKSTREAM_DATABASE_URL"]
    if not urlsplit(database_url).path.lstrip("/").startswith("workstream_test_"):
        raise RuntimeError("fault trial requires an isolated database")
    execution = json.loads(
        Path(environment["WORKSTREAM_CLI_JOURNEY_EXECUTION_PROFILE_FILE"]).read_text(
            encoding="utf-8"
        )
    )
    timeout = (
        execution["upload_total_seconds"]
        + execution["runtime"]["aggregate_deadline_ms"] / 1000
    )
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with httpx.AsyncClient(base_url=origin, timeout=timeout, trust_env=False) as client:
            return await public_pre_launch_failure(
                client,
                factory,
                task=task,
                assignment=assignment,
                token=token,
                archive=archive,
                runner=RunnerFaults(profile),
                stop_worker=stop_worker,
                start_worker=start_worker,
            )
    finally:
        await engine.dispose()


def run_pre_launch_fault(
    client,
    origin: str,
    environment: dict[str, str],
    task: str,
    assignment: str,
    token: str,
    controls,
    profile: RunnerFaultProfile,
) -> None:
    """Keep remote evidence private; report only the bounded case completion."""
    archive = _package(client, "correct").read_bytes()
    result = asyncio.run(
        _run(
            origin,
            environment,
            task,
            assignment,
            token,
            archive,
            profile,
            *controls,
        )
    )
    evidence = Path(os.environ["WORKSTREAM_CLI_JOURNEY_EVIDENCE"])
    evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = evidence / "remote-pre-launch-fault.json"
    with path.open("x", encoding="utf-8") as stream:
        path.chmod(0o600)
        json.dump(result, stream, default=str, sort_keys=True)
    client.complete_stage("remote_pre_launch_failure")
