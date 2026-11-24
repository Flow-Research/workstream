"""Current public source-intake failure boundaries on the owned native node."""

import asyncio
from pathlib import Path
import time
from uuid import uuid4

from sqlalchemy import func, select

from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
from app.modules.artifacts.models import SubmissionBundleAdmission, SubmissionBundleDurableIntent
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.tasks.models import Submission, WorkstreamTask
from experiments.pilot04_external_checker_runtime.public_probe_support import (
    _json, _public_project, _require, _secret_archive, _started_public_task, _with_fixture_file,
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


async def _source_operation(factory, key):
    async with factory() as session:
        return (await session.scalars(select(SubmissionIntakeOperation).where(
            SubmissionIntakeOperation.idempotency_key == key))).one_or_none()


async def _wait_source_state(factory, key, states, *, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        operation = await _source_operation(factory, key)
        if operation is not None and operation.state in states:
            return operation
        await asyncio.sleep(.05)
    raise RuntimeError('source operation did not reach its exact expected state')


async def _assert_source_failure(factory, task, key, size, *, sealed, code=None):
    """Failed input remains charged without PRE admission or accepted handoff."""
    row = await _wait_source_state(factory, key, {'failed', 'cancelled', 'rejected', 'abandoned'})
    _require(row.task_id == task and row.acceptance_receipt is None
             and row.finalized_submission_id is None and row.finalization_event_id is None,
             'failed source escaped into accepted custody')
    if code is not None:
        _require(row.failure_code == code, 'source failure changed its exact code')
    async with factory() as session:
        charge = await session.get(SubmissionSourceCharge, row.id)
        owner = await session.get(WorkstreamTask, task)
        _require(charge and charge.state == ('sealed' if sealed else 'reserved')
                 and charge.accounted_bytes == size > 0,
                 'failed source released or changed its exact charge')
        _require(owner.status == 'in_progress' and owner.active_submission_operation_id is None,
                 'failed source changed Task eligibility or retained its pointer')
        if not sealed:
            _require(row.raw_byte_count is None and row.selected_pre_submit_run_id is None,
                     'incomplete upload sealed bytes or reserved PRE')
            _require(await session.scalar(select(func.count()).select_from(SelectedPreSubmitRun).where(
                SelectedPreSubmitRun.task_id == task)) == 0, 'incomplete upload created a PRE run')
    await _assert_no_submission_after_intake_failure(factory, task, row.selected_pre_submit_run_id)
    return row


async def _observe_accepted_source(client, factory, task, assignment, token, archive, key, receipt):
    from experiments.pilot04_external_checker_runtime.run_public_journey_probe import _await_finalized_source

    _require(receipt['status'] == 'accepted' and receipt['replayed'] is False,
             'source trial did not retain a new accepted receipt')
    context = {'acceptance_receipt': receipt, 'idempotency_key': key}
    return await _await_finalized_source(client, factory, task, assignment, token, context, archive)


def _assert_current_pre(row, *, failure=None):
    """One selected image replaces obsolete zero/multi-image approval vectors."""
    value = row.terminal_json['execution']
    _require(row.status == 'completed' and value['required_external_count'] == 1,
             'current PRE did not retain exactly one required project image')
    members = value['external_members']
    if failure == 'secret':
        failed = [check['failure_code'] for check in value['workstream_default']['checks']
                  if check['status'] == 'failed']
        _require(not value['eligible'] and not value['workstream_default']['eligible']
                 and failed == ['high_confidence_secret_detected'] and members == [],
                 'default blocker reached project execution or lost exact feedback')
        return
    entries = row.request_json['policy']['entries']
    _require(len(entries) == 1 and entries[0]['stage'] == 'pre_submit',
             'current PRE lost its exact locked project selection')
    selected = entries[0]
    registry = selected['registry']
    _require(value['workstream_default']['eligible'] and value['eligible'] is (failure is None)
             and len(members) == 1 and members[0]['order'] == 0
             and members[0]['requirement_id'] == selected['requirement_id'],
             'one-project PRE lost its default-before-project boundary')
    member = members[0]
    _require(member['registry_entry_id'] == registry['registry_entry_id']
             and member['registry_entry_digest'] == registry['entry_digest']
             and member['isolation']['platform_manifest_digest'] == registry['image_digest']
             and member['result']['verdict'] == ('failed' if failure else 'passed')
             and member['result']['request_digest'] == member['request_digest']
             and member['isolation']['runtime'] == 'smolvm'
             and member['isolation']['isolation_mode'] == 'smol-microvm',
             'selected member lost its exact native request/result custody')
    if failure:
        _require([f['code'] for f in member['result']['findings']] == ['probe.project_rule_failed'],
                 'project PRE failure lost its exact finding')


async def _source_request(client, route, headers, token, key, content, expected):
    return await _json(client, 'POST', route, token, expected,
        headers=headers | {'Idempotency-Key': key, 'Content-Length': str(len(content))}, content=content)


async def _cancel_upload(client, factory, route, headers, token, archive, task, node_root):
    """Cancel incomplete provider upload before any native allocation is permitted."""
    key, ready, start = str(uuid4()), asyncio.Event(), len(trace_events(node_root))

    async def incomplete():
        yield archive[:1]
        await _wait_source_state(factory, key, {'receiving'})
        _require(len(trace_events(node_root)) == start, 'incomplete upload allocated native resources')
        ready.set()
        await asyncio.Event().wait()

    pending = asyncio.create_task(client.post(route, headers=headers | {
        'Authorization': 'Bearer ' + token, 'Idempotency-Key': key, 'Content-Length': str(len(archive))},
        content=incomplete()))
    try:
        await asyncio.wait_for(ready.wait(), timeout=90)
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
    row = await _assert_source_failure(factory, task, key, len(archive), sealed=False)
    assert_launches(node_root, start, creates=0, executions=0, project=False)
    assert_launches(node_root, start, creates=0, executions=0)
    cleanup = await node_command(node_root, 'drained')
    _require(cleanup['foreign_preserved'] and not any(cleanup['resources'].values()),
             'cancelled upload changed foreign resources')
    return {'case': 'cancelled_source_upload', 'operation_id': row.id,
            'failure_code': row.failure_code, 'native_allocations': 0, 'cleanup': cleanup}


async def _expire_upload(client, factory, route, headers, token, archive, task, node_root):
    """Retain the original upload deadline while real idle/total timing closes input."""
    key, start, observed = str(uuid4()), len(trace_events(node_root)), {}

    async def stalled():
        yield archive[:1]
        row = await _wait_source_state(factory, key, {'receiving'})
        observed['original_deadline'] = row.upload_deadline_at
        _require(len(trace_events(node_root)) == start, 'stalled upload allocated native resources')
        await _wait_source_state(factory, key, {'failed'}, timeout=3600)
        yield archive[1:]

    response = await client.post(route, headers=headers | {'Authorization': 'Bearer ' + token,
        'Idempotency-Key': key, 'Content-Length': str(len(archive))}, content=stalled(), timeout=3660)
    _require(response.status_code == 408 and response.json()['error']['code'] == 'submission_upload_timeout',
             'expired source upload did not return its exact timeout')
    row = await _assert_source_failure(factory, task, key, len(archive), sealed=False,
                                      code='submission_upload_timeout')
    _require(row.upload_deadline_at == observed['original_deadline'], 'stalled upload reset its original deadline')
    assert_launches(node_root, start, creates=0, executions=0, project=False)
    assert_launches(node_root, start, creates=0, executions=0)
    await _source_request(client, route, headers, token, key, archive, 408)
    return {'case': 'source_upload_timeout', 'operation_id': row.id, 'native_allocations': 0,
            'original_deadline': row.upload_deadline_at.isoformat()}


async def _drain_source_trial_posts(factory, project_id, accepted, node_root):
    from experiments.pilot04_external_checker_runtime.run_public_journey_probe import _complete_post

    for saved in accepted:
        await _complete_post(factory, submission_id=saved['submission_id'], project_id=project_id,
                             recommendation='allow_review', deliver_completion=False)
    cleanup = await node_command(node_root, 'drained')
    _require(cleanup['foreign_preserved'] and not any(cleanup['resources'].values()),
             'source-trial POST execution retained resources or changed foreign custody')


async def public_intake_trials(client, factory, env, node_root: Path, *, stop_worker, start_worker):
    """Current one-PRE default/project failures and source-before-native boundaries."""
    project, _, manager, token = await _public_project(client, factory, env, human_review_required=True)
    task, assignment = await _started_public_task(client, project_id=str(project.project_id),
        manager_token=manager, contributor_token=token, source_ref='source-intake-boundaries')
    archive = archive_with_modes('evidence/results', project.project_id)
    route = f'/api/v1/tasks/{task}/submissions'
    headers = {'Content-Type': 'application/zip', 'X-Task-Assignment-Id': assignment,
               'X-Submission-Summary': 'Completed task evidence.',
               'X-Contributor-Attestation': 'rights_confirmed; no confidential data or credentials.'}
    evidence, accepted = [], []
    stop_worker()
    try:
        start = len(trace_events(node_root))
        response = await client.post(route, headers=headers | {'Idempotency-Key': str(uuid4())}, content=archive)
        _require(response.status_code == 401 and len(trace_events(node_root)) == start,
                 'unauthenticated source upload allocated native resources')
        evidence.append(await _cancel_upload(client, factory, route, headers, token, archive, task, node_root))
        evidence.append(await _expire_upload(client, factory, route, headers, token, archive, task, node_root))
        for failure, content in (('secret', _secret_archive(archive)),
                                 ('project', _with_fixture_file(archive, 'project-rejected.txt'))):
            start, key = len(trace_events(node_root)), str(uuid4())
            result = await _source_request(client, route, headers, token, key, content, 422)
            _require(result['error']['code'] == 'pre_submission_checker_failed', 'work failure lost public feedback')
            row = await _selected(factory, key)
            _assert_current_pre(row, failure=failure)
            await _assert_source_failure(factory, task, key, len(content), sealed=True,
                                         code='pre_submission_checker_failed')
            # One VM runs trusted defaults and, only if eligible, the project phase.
            assert_launches(node_root, start, creates=1, executions=1)
            evidence.append({'case': failure + '_rejection', 'run_id': row.id})
        start, key, released = len(trace_events(node_root)), str(uuid4()), {}

        async def delayed():
            yield archive[:1]
            await _wait_source_state(factory, key, {'receiving'})
            _require(len(trace_events(node_root)) == start, 'source allocated native VM before complete body')
            released['at'] = time.monotonic()
            yield archive[1:]

        result = await _json(client, 'POST', route, token, 202, headers=headers | {
            'Idempotency-Key': key, 'Content-Length': str(len(archive))}, content=delayed())
        row = await _selected(factory, key)
        _assert_current_pre(row)
        assert_launches(node_root, start, creates=1, executions=1)
        _require(all(item['monotonic'] >= released['at'] for item in trace_events(node_root)[start:]
                     if item['operation'] == 'create'), 'native allocation preceded complete source release')
        accepted.append(await _observe_accepted_source(client, factory, task, assignment, token, archive, key, result))
        evidence.append({'case': 'complete_source_before_native', 'run_id': row.id, 'submission': accepted[-1]})
    finally:
        await start_worker()
    await _drain_source_trial_posts(factory, project.project_id, accepted, node_root)
    return evidence
