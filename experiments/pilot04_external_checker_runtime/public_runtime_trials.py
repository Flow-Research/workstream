"""Real project-launch outage and authorized durable retry in the isolated public drill."""

import json
from pathlib import Path
import time
from uuid import uuid4

from app.modules.checkers.api.execution import CheckerRetryPublicResult
from app.modules.checkers.models import CheckerRun
from app.modules.tasks.models import SubmissionDispatch
from experiments.pilot04_external_checker_runtime.public_intake_trials import (
    _assert_no_submission_after_intake_failure, _selected,
)
from experiments.pilot04_external_checker_runtime.public_node_faults import assert_launches, node_command, trace_events
from experiments.pilot04_external_checker_runtime.public_probe_support import (
    _assert_task_has_no_effects, _json, _public_project, _require, _started_public_task,
    _wait_outbox_acknowledged, _with_fixture_file,
)
from tests.post_submit_materialization_helpers import archive_with_modes


async def public_runtime_trials(client, factory, env, root: Path):
    project, _, manager, contributor = await _public_project(
        client, factory, env, human_review_required=True,
    )
    task, assignment = await _started_public_task(
        client, project_id=str(project.project_id), manager_token=manager,
        contributor_token=contributor, source_ref='runtime-failure-recovery',
    )
    archive = archive_with_modes('evidence/results', project.project_id)
    route = f'/api/v1/tasks/{task}/submission-bundle-preparations'
    headers = {'Content-Type': 'application/zip', 'X-Task-Assignment-Id': assignment,
               'X-Submission-Summary': 'Completed task evidence.',
               'X-Contributor-Attestation': 'rights_confirmed; no confidential data or credentials.'}
    evidence = []
    try:
        for action, expected, creates, executions in (
            ('project_fail_once', 202, 2, 1),
            ('project_fail_all', 503, 3, 0),
            ('project_kill', 503, 1, 1),
            ('project_deadline', 503, 1, 1),
        ):
            control = await node_command(root, 'clear' if action == 'project_deadline' else action)
            start = len(trace_events(root))
            key = str(uuid4())
            content = _with_fixture_file(archive, 'runtime-wait.txt') if action in {'project_kill', 'project_deadline'} else archive
            began = time.monotonic()
            result = await _json(client, 'POST', route, contributor, expected,
                                 headers=headers | {'Idempotency-Key': key}, content=content)
            drained = await node_command(root, 'drained')
            _require(bool(drained['foreign_preserved']) and not any(drained['resources'].values()),
                     'exact cleanup or foreign preservation is absent')
            names = assert_launches(root, start, creates=creates, executions=executions)
            if action == 'project_kill':
                events = [e for e in trace_events(root)[start:] if e['project']]
                killed = [e for e in events if e['operation'] == 'controller_kill']
                _require(len(killed) == 1 and killed[0]['controller_pid'] == control['controller_pid'],
                         'controller-death trial did not record the exact kill target')
                restarted = await node_command(root, 'restarted')
                _require(restarted['controller_pid'] != control['controller_pid'],
                         'controller-death trial retained the original controller')
                leases = [e['lease'] for e in events if e.get('lease')]
                _require(leases and len({lease['epoch'] for lease in leases}) == 1
                         and len({lease['expires_ms'] for lease in leases}) == 1,
                         'interrupted execution changed its original lease epoch/deadline')
            row = await _selected(factory, key)
            if action == 'project_deadline':
                events = [event for event in trace_events(root)[start:] if event['project']]
                created = next(event for event in events if event['operation'] == 'create')
                deleted = next(event for event in events if event['operation'] == 'delete')
                _require(row.terminal_json['infrastructure_failure_code'] == 'deadline_exceeded'
                         and deleted['wall_ms'] >= created['lease']['expires_ms'],
                         'deadline trial did not reach its original expiry with exact timeout custody')
            if expected == 503:
                _require(row.status == 'infrastructure_failed' and row.terminal_json['execution'] is None,
                         'runtime outage was represented as a work verdict')
                await _assert_no_submission_after_intake_failure(factory, task, row.id)
                await node_command(root, 'clear')
                replay_start = len(trace_events(root))
                replay = await _json(client, 'POST', route, contributor, 503,
                                     headers=headers | {'Idempotency-Key': key}, content=content)
                _require(replay['error']['code'] == result['error']['code'], 'failure replay changed code')
                # Re-upload and trusted inspection may occur; selected project execution may not.
                assert_launches(root, replay_start, creates=0, executions=0)
                repeated = await _selected(factory, key)
                _require((repeated.id, repeated.terminal_digest) == (row.id, row.terminal_digest),
                         'same-key replay replaced terminal failure custody')
                recovery_start = len(trace_events(root))
                fresh_key = str(uuid4())
                await _json(client, 'POST', route, contributor, 202,
                            headers=headers | {'Idempotency-Key': fresh_key}, content=archive)
                fresh = await _selected(factory, fresh_key)
                if action == 'project_kill':
                    new_leases = [e['lease'] for e in trace_events(root)[recovery_start:]
                                  if e['project'] and e.get('lease')]
                    _require(new_leases and all(lease['epoch'] != leases[0]['epoch'] for lease in new_leases),
                             'fresh execution did not use the restarted controller epoch')
                _require(fresh.id != row.id and fresh.eligible is True,
                         'fresh request did not repeat intake successfully after recovery')
            evidence.append({'case': action, 'run_id': row.id, 'machines': names,
                             'elapsed_seconds': round(time.monotonic() - began, 3),
                             'status': row.status, 'failure_code': row.terminal_json.get('infrastructure_failure_code'),
                             'cleanup': drained})
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
