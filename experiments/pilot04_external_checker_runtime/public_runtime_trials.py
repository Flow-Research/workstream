"""Real project-launch faults through current public source intake and durable retry."""

import json
from pathlib import Path
import time
from uuid import UUID, uuid4

from sqlalchemy import select

from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from app.modules.checkers.api.execution import CheckerRetryPublicResult
from app.modules.checkers.models import CheckerRun
from app.modules.tasks.models import SubmissionDispatch
from experiments.pilot04_external_checker_runtime.public_intake_trials import (
    _assert_current_pre, _assert_source_failure, _drain_source_trial_posts,
    _observe_accepted_source, _selected, _source_request,
)
from experiments.pilot04_external_checker_runtime.public_node_faults import (
    assert_launches, assert_trace_launches, node_command, trace_events,
)
from experiments.pilot04_external_checker_runtime.public_probe_support import (
    _assert_task_has_no_effects, _json, _public_project, _require, _started_public_task,
    _wait_outbox_acknowledged, _with_fixture_file,
)
from experiments.pilot04_external_checker_runtime.public_runner_faults import RunnerFaults
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


async def _trial_operation_ids(factory, task):
    async with factory() as session:
        return set(await session.scalars(select(SubmissionIntakeOperation.id).where(
            SubmissionIntakeOperation.task_id == task)))


def _same_public_failure(first, replay):
    """Compare durable error fields while validating request-scoped IDs."""
    def stable(value):
        if type(value) is not dict or set(value) != {'error'}:
            return None
        error = value['error']
        expected = {'code', 'message', 'details', 'correlation_id', 'retryable'}
        if type(error) is not dict or set(error) != expected:
            return None
        correlation = error['correlation_id']
        try:
            if type(correlation) is not str or str(UUID(correlation)) != correlation:
                return None
        except ValueError:
            return None
        return {key: item for key, item in error.items() if key != 'correlation_id'}

    left, right = stable(first), stable(replay)
    return left is not None and left == right


def _retain_fresh_pre(path, row, receipt):
    """Keep bounded selection and outcome facts before the recovery assertion."""
    entries = row.request_json.get('policy', {}).get('entries', [])
    execution = row.terminal_json.get('execution') or {}
    members = execution.get('external_members', [])
    observation = {
        'receipt': {key: receipt.get(key) for key in ('operation_id', 'status', 'replayed')},
        'selected': {'id': str(row.id), 'status': row.status,
                     'source_operation_id': row.source_operation_id,
                     'terminal_digest': row.terminal_digest},
        'policy': [{'requirement_id': entry.get('requirement_id'), 'stage': entry.get('stage'),
                    'registry_entry_id': entry.get('registry', {}).get('registry_entry_id'),
                    'registry_entry_digest': entry.get('registry', {}).get('entry_digest'),
                    'image_digest': entry.get('registry', {}).get('image_digest')}
                   for entry in entries],
        'execution': {'eligible': execution.get('eligible'),
                      'required_external_count': execution.get('required_external_count'),
                      'default_eligible': execution.get('workstream_default', {}).get('eligible'),
                      'members': [{'order': member.get('order'),
                                   'requirement_id': member.get('requirement_id'),
                                   'registry_entry_id': member.get('registry_entry_id'),
                                   'registry_entry_digest': member.get('registry_entry_digest'),
                                   'verdict': member.get('result', {}).get('verdict'),
                                   'runtime': member.get('isolation', {}).get('runtime'),
                                   'platform_manifest_digest': member.get('isolation', {}).get('platform_manifest_digest')}
                                  for member in members]},
    }
    with path.open('x', encoding='utf-8') as stream:
        path.chmod(0o600)
        json.dump(observation, stream, sort_keys=True)


async def _runner_drained(runner):
    observed = await runner.command('drained')
    result = observed['result']
    _require(type(result.get('foreign_preserved')) is str and bool(result['foreign_preserved'])
             and type(result.get('resources')) is dict
             and set(result['resources']) == {'disks', 'leases', 'machines', 'cgroups'}
             and all(type(value) is list and not value for value in result['resources'].values()),
             'remote cleanup or exact foreign preservation is absent')
    return observed


async def public_pre_launch_failure(client, factory, *, task, assignment, token, archive,
                                    runner: RunnerFaults, stop_worker, start_worker,
                                    first_response_path: Path | None = None):
    """Pause/restore only the isolated fixture's owned general POST consumer."""
    try:
        stop_worker()
        return await _remote_pre_launch_failure(client, factory, task=task, assignment=assignment,
            token=token, archive=archive, runner=runner, first_response_path=first_response_path)
    finally:
        await start_worker()


async def _remote_pre_launch_failure(client, factory, *, task, assignment, token, archive, runner,
                                     first_response_path=None):
    """One remote launch fault on an already approved/claimed current public task.

    The actual locked-image-compatible ZIP is supplied by the caller. The general
    POST worker must be paused for this exclusive trace window; the production
    finalization worker remains live. Unknown command outcome propagates without
    replaying that command or submitting a fresh candidate.
    """
    _require(not await _trial_operation_ids(factory, task), 'launch trial task already has intake custody')
    route = f'/api/v1/tasks/{task}/submissions'
    headers = {'Content-Type': 'application/zip', 'X-Task-Assignment-Id': assignment,
               }
    installed = await runner.command('project_fail_once')
    before = await runner.snapshot()
    key = str(uuid4())
    failure = await _source_request(client, route, headers, token, key, archive, 503)
    _require(failure['error']['code'] == 'submission_infrastructure_unavailable',
             'remote launch failure was not a known infrastructure refusal')
    failed_cleanup = await _runner_drained(runner)
    failed_trace = await runner.snapshot()
    records = failed_trace['events'][before['cursor']:]
    row = await _selected(factory, key)
    if first_response_path is not None:
        with first_response_path.open('x', encoding='utf-8') as stream:
            first_response_path.chmod(0o600)
            json.dump({'public_failure': failure, 'selected_pre': {'id': str(row.id),
                       'status': row.status, 'terminal_digest': row.terminal_digest,
                       'terminal': row.terminal_json}, 'runtime_event_count': len(records)},
                      stream, default=str, sort_keys=True)
    machines = assert_trace_launches(records, creates=1, executions=0)
    assert_trace_launches(records, creates=0, executions=0, project=False)
    _require(row.status == 'infrastructure_failed' and row.terminal_json['execution'] is None
             and row.terminal_json['infrastructure_failure_code'] == 'implementation_unavailable'
             and row.request_json['policy']['entries'][0]['registry']['image_digest'] == runner.profile.image_digest,
             'remote failed PRE lost exact selected image or terminal infrastructure custody')
    operation = await _assert_source_failure(factory, task, key, len(archive), sealed=True,
                                             code='submission_infrastructure_unavailable')
    _require(operation.selected_pre_submit_run_id is None
             and row.task_id == task and row.source_operation_id == operation.id
             and row.request_json['source']['location']['operation_id'] == operation.id
             and row.terminal_json['reservation']['source']['location']['operation_id'] == operation.id
             and await _trial_operation_ids(factory, task) == {operation.id},
             'launch failure created another operation or changed its exact PRE')
    await runner.command('clear')
    replay = await _source_request(client, route, headers, token, key, archive, 503)
    repeated = await _selected(factory, key)
    replay_trace = await runner.snapshot()
    _require(_same_public_failure(failure, replay), 'same-key public failure fields changed')
    _require((repeated.id, repeated.terminal_digest) == (row.id, row.terminal_digest),
             'same-key selected PRE identity or digest changed')
    _require(replay_trace['cursor'] == failed_trace['cursor'],
             'same-key replay allocated a native machine')
    _require(await _trial_operation_ids(factory, task) == {operation.id},
             'same-key replay created another source operation')
    await _assert_source_failure(factory, task, key, len(archive), sealed=True,
                                 code='submission_infrastructure_unavailable')
    fresh_key = str(uuid4())
    receipt = await _source_request(client, route, headers, token, fresh_key, archive, 202)
    fresh = await _selected(factory, fresh_key)
    if first_response_path is not None:
        _retain_fresh_pre(first_response_path.with_name('remote-pre-launch-fresh-pre.json'), fresh, receipt)
    _assert_current_pre(fresh)
    _require(fresh.id != row.id and fresh.source_operation_id == receipt['operation_id']
             and fresh.request_json['policy']['entries'][0]['registry']['image_digest']
             == runner.profile.image_digest, 'recovery changed the exact selected image or reused failed PRE')
    recovered_cleanup = await _runner_drained(runner)
    recovered_trace = await runner.snapshot()
    records = recovered_trace['events'][replay_trace['cursor']:]
    assert_trace_launches(records, creates=1, executions=1)
    assert_trace_launches(records, creates=0, executions=0, project=False)
    saved = await _observe_accepted_source(client, factory, task, assignment, token, archive, fresh_key, receipt)
    _require(await _trial_operation_ids(factory, task) == {operation.id, receipt['operation_id']},
             'fresh-key recovery created extra operations')
    return {'case': 'remote_pre_launch_failure', 'run_id': runner.profile.run_id,
            'command': installed, 'failed_operation_id': operation.id, 'failed_pre_id': row.id,
            'failure_key': key, 'recovery_key': fresh_key, 'recovery_receipt': receipt,
            'failed_machines': machines, 'recovered_submission': saved,
            'trace_before': before, 'trace_failed': failed_trace,
            'trace_replay': replay_trace, 'trace_recovered': recovered_trace,
            'failed_cleanup': failed_cleanup, 'recovered_cleanup': recovered_cleanup}


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
                       }
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
                       }
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
