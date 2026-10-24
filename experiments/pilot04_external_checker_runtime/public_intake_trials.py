"""Public zero/two-binding and upload-overlap evidence on the real one-slot node."""

import asyncio
import json
from pathlib import Path
import time
from uuid import uuid4

from sqlalchemy import func, select

from app.modules.artifacts.models import SubmissionBundleAdmission, SubmissionBundleDurableIntent
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.tasks.models import Submission
from experiments.pilot04_external_checker_runtime.public_probe_support import (
    _json, _public_project, _require, _started_public_task, _with_fixture_file,
)
from experiments.pilot04_external_checker_runtime.public_node_faults import assert_launches, node_command, trace_events
from tests.post_submit_materialization_helpers import archive_with_modes


async def _assert_no_submission_after_intake_failure(factory, task_id, run_id=None):
    async with factory() as session:
        _require(await session.scalar(select(func.count()).select_from(Submission).where(
            Submission.task_id == task_id)) == 0, "failed intake created a Submission")
        if run_id is not None:
            for model in (SubmissionBundleAdmission, SubmissionBundleDurableIntent):
                _require(await session.scalar(select(func.count()).select_from(model).where(
                    model.selected_pre_submit_run_id == run_id)) == 0,
                    "failed intake created artifact admission custody")


async def _selected(factory, key):
    async with factory() as session:
        row = (await session.scalars(select(SelectedPreSubmitRun).where(
            SelectedPreSubmitRun.idempotency_key == key))).one()
        _require(row.finalize_evidence_id is not None and row.terminal_digest is not None,
                 "selected PRE omitted finalized custody")
        return row


def _assert_default_only_pre(row):
    value = row.terminal_json["execution"]
    _require(row.status == "completed" and value["eligible"]
             and value["workstream_default"]["eligible"]
             and value["required_external_count"] == 0 and value["external_members"] == [],
             "default-only policy did not retain its exact zero-project execution")


def _assert_ordered_pre_and_stop(row, *, failed):
    value = row.terminal_json["execution"]
    members = value["external_members"]
    expected = ["project.pre_submit.01"] if failed else ["project.pre_submit.01", "project.pre_submit.02"]
    _require(row.status == "completed" and value["workstream_default"]["eligible"]
             and value["required_external_count"] == 2 and value["eligible"] is not failed
             and [member["requirement_id"] for member in members] == expected
             and [member["order"] for member in members] == list(range(len(expected)))
             and len({member["request_digest"] for member in members}) == len(expected),
             "two-binding policy did not retain its ordered executed prefix")
    for member in members:
        _require(member["result"]["verdict"] == ("failed" if failed else "passed")
                 and member["result"]["request_digest"] == member["request_digest"]
                 and member["isolation"]["runtime"] == "smolvm",
                 "selected member lost its real isolated request/result custody")


def _events(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _assert_project_invocations(row, trace, observer_start, node_root, runtime_start):
    members = row.terminal_json['execution']['external_members']
    expected = [member['request_digest'] for member in members]
    observed = _events(trace)[observer_start:]
    starts = [event for event in observed if event['event'] == 'project_started']
    ends = [event for event in observed if event['event'] == 'project_completed']
    _require([event['session'] for event in starts] == expected
             and [event['session'] for event in ends] == expected,
             'project adapter invocations differ from retained ordered members')
    order = [(event['event'], event['session']) for event in observed
             if event['event'] in {'project_started', 'project_completed'}]
    _require(order == [(kind, digest) for digest in expected
                       for kind in ('project_started', 'project_completed')],
             'project checker invocations overlap or run outside canonical order')
    machines = assert_launches(node_root, runtime_start, creates=len(expected),
                               executions=len(expected), shared_deadline=False)
    executions = [event for event in trace_events(node_root)[runtime_start:]
                  if event['project'] and event['operation'] == 'exec']
    _require([event['name'] for event in executions] == machines,
             'project guest execution order differs from fresh allocation order')
    for started, ended, executed in zip(starts, ends, executions, strict=True):
        _require(started['monotonic'] <= executed['monotonic'] <= ended['monotonic'],
                 'project VM execution is outside its exact adapter request')
    return machines


async def _wait_event(path, start, event, session=None):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        found = [item for item in _events(path)[start:] if item["event"] == event
                 and (session is None or item["session"] == session)]
        if found:
            return found[0]
        await asyncio.sleep(0.05)
    raise RuntimeError("real intake adapter did not acknowledge " + event)


async def _cancel_upload(client, factory, route, headers, token, archive, trace, task, node_root):
    start = len(_events(trace))
    key = str(uuid4())
    ready = asyncio.Event()
    session_id = None
    runtime_start = len(trace_events(node_root))

    async def incomplete():
        nonlocal session_id
        yield archive[:1]
        session_id = (await _wait_event(trace, start, "prepare_ready"))["session"]
        ready.set()
        await asyncio.Event().wait()

    pending = asyncio.create_task(client.post(
        route, headers=headers | {"Authorization": "Bearer " + token, "Idempotency-Key": key},
        content=incomplete(),
    ))
    try:
        await asyncio.wait_for(ready.wait(), timeout=45)
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
    await _wait_event(trace, start, "close_confirmed", session_id)
    cleanup = await node_command(node_root, "drained")
    _require(cleanup["foreign_preserved"] and not any(cleanup["resources"].values()),
             "cancelled upload retained owned resources or changed the foreign control")
    machines = assert_launches(node_root, runtime_start, creates=1, executions=0, project=False)
    assert_launches(node_root, runtime_start, creates=0, executions=0)
    async with factory() as session:
        _require(await session.scalar(select(func.count()).select_from(SelectedPreSubmitRun).where(
            SelectedPreSubmitRun.idempotency_key == key)) == 0,
            "incomplete upload reserved a selected checker run")
    await _assert_no_submission_after_intake_failure(factory, task)
    return {"case": "cancelled_upload", "session": session_id, "machines": machines,
            "cleanup": cleanup, "reserved_runs": 0}


async def public_intake_trials(client, factory, env, trace: Path, node_root: Path):
    evidence = []
    for count in (0, 2):
        project, _, manager, contributor = await _public_project(
            client, factory, env, human_review_required=True, pre_requirements=count,
        )
        task, assignment = await _started_public_task(
            client, project_id=str(project.project_id), manager_token=manager,
            contributor_token=contributor, source_ref=f"intake-bindings-{count}",
        )
        archive = archive_with_modes("evidence/results", project.project_id)
        route = f"/api/v1/tasks/{task}/submission-bundle-preparations"
        headers = {"Content-Type": "application/zip", "X-Task-Assignment-Id": assignment,
                   "X-Submission-Summary": "Completed task evidence.",
                   "X-Contributor-Attestation": "rights_confirmed; no confidential data or credentials."}
        if count == 0:
            start = len(_events(trace))
            response = await client.post(route, headers=headers | {"Idempotency-Key": str(uuid4())}, content=archive)
            _require(response.status_code == 401,
                     f"unauthenticated upload returned {response.status_code}; expected 401")
            _require(len(_events(trace)) == start, "unauthenticated upload allocated an intake session")
            evidence.append(await _cancel_upload(
                client, factory, route, headers, contributor, archive, trace, task, node_root,
            ))
            start = len(_events(trace))
            runtime_start = len(trace_events(node_root))
            key = str(uuid4())
            async def delayed_upload():
                yield archive[:1]
                ready = await _wait_event(trace, start, "prepare_ready")
                evidence.append({"case": "upload_overlap", "ready": ready,
                                 "upload_finished_at": time.monotonic()})
                yield archive[1:]
            result = await _json(client, "POST", route, contributor, 202,
                                 headers=headers | {"Idempotency-Key": key}, content=delayed_upload())
            await _wait_event(trace, start, "close_confirmed")
            row = await _selected(factory, key)
            _assert_default_only_pre(row)
            _assert_project_invocations(row, trace, start, node_root, runtime_start)
            evidence.append({"case": "default_only", "run_id": row.id,
                             "preparation_status": result["submission_bundle_preparation_status"]})
        else:
            for failed in (True, False):
                runtime_start = len(trace_events(node_root))
                observer_start = len(_events(trace))
                key = str(uuid4())
                result = await _json(client, "POST", route, contributor, 422 if failed else 202,
                                     headers=headers | {"Idempotency-Key": key},
                                     content=_with_fixture_file(archive, "project-rejected.txt") if failed else archive)
                row = await _selected(factory, key)
                _assert_ordered_pre_and_stop(row, failed=failed)
                machines = _assert_project_invocations(
                    row, trace, observer_start, node_root, runtime_start)
                if failed:
                    await _assert_no_submission_after_intake_failure(factory, task, row.id)
                evidence.append({"case": "ordered_stop" if failed else "ordered_pass", "run_id": row.id, "machines": machines,
                                 "request_digests": [member["request_digest"]
                                                     for member in row.terminal_json["execution"]["external_members"]]})
    return evidence
