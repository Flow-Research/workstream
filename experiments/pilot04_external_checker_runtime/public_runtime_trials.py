"""Real project-launch faults through current public source intake and durable retry."""

import json
from pathlib import Path
import time
from uuid import uuid4

from app.modules.checkers.api.execution import CheckerRetryPublicResult
from app.modules.checkers.models import CheckerRun
from app.modules.tasks.models import SubmissionDispatch
from experiments.pilot04_external_checker_runtime.public_intake_trials import (
    _assert_current_pre, _assert_source_failure, _drain_source_trial_posts,
    _observe_accepted_source, _selected, _source_request,
)
from experiments.pilot04_external_checker_runtime.public_node_faults import assert_launches, node_command, trace_events
from experiments.pilot04_external_checker_runtime.public_probe_support import (
    _assert_task_has_no_effects, _json, _public_project, _require, _started_public_task,
    _wait_outbox_acknowledged, _with_fixture_file,
)
from tests.post_submit_materialization_helpers import archive_with_modes


def _require_original_runtime_expiry(created, deleted):
    """Deletion must reach the original native epoch/deadline without resetting it."""
    original, final = created['lease'], deleted['lease']
    _require(deleted['wall_ms'] >= original['expires_ms']
             and final['epoch'] == original['epoch']
             and final['expires_ms'] == original['expires_ms'],
             'native execution did not reach its original lease expiry')


async def _runtime_fault_evidence(root, start, action, control, row):
    events = [event for event in trace_events(root)[start:] if event['project']]
    leases = [event['lease'] for event in events if event.get('lease')]
    if action == 'project_kill':
        killed = [event for event in events if event['operation'] == 'controller_kill']
        _require(len(killed) == 1 and killed[0]['controller_pid'] == control['controller_pid'],
                 'controller-death trial did not record the exact kill target')
        restarted = await node_command(root, 'restarted')
        _require(restarted['controller_pid'] != control['controller_pid'],
                 'controller-death trial retained the original controller')
        _require(leases and len({lease['epoch'] for lease in leases}) == 1
                 and len({lease['expires_ms'] for lease in leases}) == 1,
                 'interrupted execution changed its original lease epoch/deadline')
    if action == 'project_wait_failure':
        created = next(event for event in events if event['operation'] == 'create')
        deleted = next(event for event in events if event['operation'] == 'delete')
        # The inner selected-image deadline may precede the aggregate VM expiry.
        # Full aggregate expiry needs a separate native receipt, never this marker.
        _require(deleted['lease']['epoch'] == created['lease']['epoch']
                 and deleted['lease']['expires_ms'] == created['lease']['expires_ms'],
                 'selected deadline changed its aggregate native lease')
        execution = next(event for event in events if event['operation'] == 'exec')
        selected_ms = row.request_json['policy']['entries'][0]['registry']['resources']['deadline_ms']
        _require(deleted['wall_ms'] >= execution['wall_ms'] + selected_ms
                 and row.terminal_json['infrastructure_failure_code'] == 'implementation_unavailable',
                 'selected wait did not retain bounded execution and its current infrastructure failure')
    return leases


async def _recover_failed_source(client, factory, route, headers, token, content, archive,
                                  key, result, row, task, assignment, root, action, leases):
    _require(row.status == 'infrastructure_failed' and row.terminal_json['execution'] is None,
             'runtime outage was represented as a work verdict')
    await _assert_source_failure(factory, task, key, len(content), sealed=True,
                                 code='submission_infrastructure_unavailable')
    await node_command(root, 'clear')
    replay_start = len(trace_events(root))
    replay = await _source_request(client, route, headers, token, key, content, 503)
    _require(replay['error']['code'] == result['error']['code'], 'failure replay changed code')
    assert_launches(root, replay_start, creates=0, executions=0)
    assert_launches(root, replay_start, creates=0, executions=0, project=False)
    repeated = await _selected(factory, key)
    _require((repeated.id, repeated.terminal_digest) == (row.id, row.terminal_digest),
             'same-key replay replaced terminal failure custody')
    recovery_start, fresh_key = len(trace_events(root)), str(uuid4())
    accepted = await _source_request(client, route, headers, token, fresh_key, archive, 202)
    fresh = await _selected(factory, fresh_key)
    _assert_current_pre(fresh)
    assert_launches(root, recovery_start, creates=1, executions=1)
    _require(fresh.id != row.id, 'fresh request reused terminal failed PRE')
    if action == 'project_kill':
        new_leases = [event['lease'] for event in trace_events(root)[recovery_start:]
                      if event['project'] and event.get('lease')]
        _require(new_leases and all(lease['epoch'] != leases[0]['epoch'] for lease in new_leases),
                 'fresh execution did not use the restarted controller epoch')
    return await _observe_accepted_source(client, factory, task, assignment, token, archive, fresh_key, accepted)


async def public_runtime_trials(client, factory, env, root: Path, *, stop_worker, start_worker, operator_token):
    """Separate tasks retain one PRE per accepted source and independent fault trials."""
    project, _, manager, token = await _public_project(client, factory, env, human_review_required=True)
    archive = archive_with_modes('evidence/results', project.project_id)
    evidence, accepted = [], []
    stop_worker()
    try:
        for action, creates, executions in (
            ('project_fail_once', 1, 0), ('project_fail_all', 1, 0),
            ('project_kill', 1, 1), ('project_wait_failure', 1, 1),
        ):
            task, assignment = await _started_public_task(client, project_id=str(project.project_id),
                manager_token=manager, contributor_token=token, source_ref='source-' + action)
            route = f'/api/v1/tasks/{task}/submissions'
            headers = {'Content-Type': 'application/zip', 'X-Task-Assignment-Id': assignment,
                       'X-Submission-Summary': 'Completed task evidence.',
                       'X-Contributor-Attestation': 'rights_confirmed; no confidential data or credentials.'}
            control = await node_command(root, 'clear' if action == 'project_wait_failure' else action)
            start, key, began = len(trace_events(root)), str(uuid4()), time.monotonic()
            content = (_with_fixture_file(archive, 'runtime-wait.txt')
                       if action in {'project_kill', 'project_wait_failure'} else archive)
            result = await _source_request(client, route, headers, token, key, content, 503)
            drained = await node_command(root, 'drained')
            _require(drained['foreign_preserved'] and not any(drained['resources'].values()),
                     'exact cleanup or foreign preservation is absent')
            names = assert_launches(root, start, creates=creates, executions=executions)
            row = await _selected(factory, key)
            leases = await _runtime_fault_evidence(root, start, action, control, row)
            saved = await _recover_failed_source(client, factory, route, headers, token, content, archive,
                key, result, row, task, assignment, root, action, leases)
            accepted.append(saved)
            evidence.append({'case': action, 'run_id': row.id, 'machines': names,
                             'elapsed_seconds': round(time.monotonic() - began, 3),
                             'status': row.status, 'failure_code': row.terminal_json.get('infrastructure_failure_code'),
                             'cleanup': drained, 'recovered_submission_id': saved['submission_id']})
    finally:
        try:
            await node_command(root, 'clear')
            await node_command(root, 'drained')
        finally:
            await start_worker()
    await _drain_source_trial_posts(factory, project.project_id, accepted, root)
    evidence.extend(await _post_launch_trials(client, factory, project.project_id, manager, token,
        archive, root, operator_token, stop_worker=stop_worker, start_worker=start_worker))
    return evidence


async def _post_launch_trials(client, factory, project_id, manager, token, archive, root, operator_token,
                              *, stop_worker, start_worker):
    """POST retains native launch retries; PRE itself never retries a VM create."""
    from experiments.pilot04_external_checker_runtime.run_public_journey_probe import _complete_post

    evidence = []
    try:
        for action, creates, executions in (('project_fail_once', 2, 1), ('project_fail_all', 3, 0)):
            task, assignment = await _started_public_task(client, project_id=str(project_id),
                manager_token=manager, contributor_token=token, source_ref='post-' + action)
            route = f'/api/v1/tasks/{task}/submissions'
            headers = {'Content-Type': 'application/zip', 'X-Task-Assignment-Id': assignment,
                       'X-Submission-Summary': 'Completed task evidence.',
                       'X-Contributor-Attestation': 'rights_confirmed; no confidential data or credentials.'}
            stop_worker()
            try:
                key = str(uuid4())
                receipt = await _source_request(client, route, headers, token, key, archive, 202)
                _assert_current_pre(await _selected(factory, key))
                saved = await _observe_accepted_source(client, factory, task, assignment, token, archive, key, receipt)
                start = len(trace_events(root))
                await node_command(root, action)
            finally:
                await start_worker()
            if action == 'project_fail_once':
                await _complete_post(factory, submission_id=saved['submission_id'], project_id=project_id,
                                     recommendation='allow_review', deliver_completion=False)
                names = assert_launches(root, start, creates=creates, executions=executions)
                recovery = None
            else:
                async with factory() as session:
                    dispatch = await session.get(SubmissionDispatch, saved['submission_id'])
                    event_id = dispatch.evaluation_event_id
                await _wait_outbox_acknowledged(factory, event_id, project_id)
                names = assert_launches(root, start, creates=creates, executions=executions)
                recovery_start = len(trace_events(root))
                successor, recovery = await retry_post_outage(
                    client, factory, saved['submission_id'], project_id, operator_token, root)
                await _complete_post(factory, submission_id=saved['submission_id'], project_id=project_id,
                                     recommendation='allow_review', deliver_completion=False, successor=successor)
                assert_launches(root, recovery_start, creates=1, executions=1)
            cleanup = await node_command(root, 'drained')
            _require(cleanup['foreign_preserved'] and not any(cleanup['resources'].values()),
                     'POST launch retry changed foreign resources or leaked owned resources')
            evidence.append({'case': 'post_' + action, 'submission_id': saved['submission_id'],
                             'machines': names, 'operator_recovery': recovery, 'cleanup': cleanup})
    finally:
        await node_command(root, 'clear')
        await node_command(root, 'drained')
    return evidence


async def retry_post_outage(client, factory, submission_id, project_id, operator_token, root):
    async with factory() as session:
        dispatch = await session.get(SubmissionDispatch, submission_id)
        run_id, event_id = dispatch.evaluation_attempt_id, dispatch.evaluation_event_id
    await _wait_outbox_acknowledged(factory, event_id, project_id)
    async with factory() as session:
        failed = await session.get(CheckerRun, run_id)
        _require(failed.status == 'infrastructure_failed' and failed.completion_event_id is None
                 and failed.failure_code == 'implementation_unavailable'
                 and failed.finalize_evidence_id is not None,
                 'project POST outage lacks terminal infrastructure custody')
        await _assert_task_has_no_effects(session, failed.task_id)
    await node_command(root, 'clear')
    await node_command(root, 'drained')
    base = f'/api/v1/operations/projects/{project_id}'
    page = await _json(client, 'GET', base + '/checker-retry-sources', operator_token, 200)
    _require([item['source']['source_run_id'] for item in page['items']] == [run_id],
             'public recovery discovery did not return the exact failed run')
    route = base + f'/checker-runs/{run_id}/retry'
    headers = {'Idempotency-Key': str(uuid4())}
    payload = {'reason': 'Restored dedicated Smol project execution'}
    raw = await _json(client, 'POST', route, operator_token, 201, headers=headers, json=payload)
    replay = await _json(client, 'POST', route, operator_token, 201, headers=headers, json=payload)
    _require(replay == raw, 'authorized POST retry replay changed receipt')
    receipt = CheckerRetryPublicResult.model_validate_json(json.dumps(raw))
    _require(receipt.successor.generation == failed.evaluation_generation + 1,
             'POST retry did not allocate exactly the next evaluation generation')
    return receipt.successor, {'entry': 'public_operator_checker_retry',
                              'failed_run_id': run_id, 'receipt_id': str(receipt.receipt_id),
                              'successor_run_id': str(receipt.successor.run_id),
                              'generation': receipt.successor.generation}
