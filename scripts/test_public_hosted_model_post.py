"""Bounded hosted model proof: public authority, no second paid project or fake grading."""

import asyncio
import copy
from datetime import UTC, datetime
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend'), str(ROOT / 'backend/scripts'), str(ROOT / 'backend/tests')]
from app.core.identifiers import new_record_id  # noqa: E402
from app.modules.model_usage.api import ProjectModelProfile  # noqa: E402
from experiments.pilot04_external_checker_runtime.public_hosted_model_post import (  # noqa: E402
    CEILING, CHECK, MODEL, ModelPostQualification, canonical, digest, fixture_archive,
    profile_spec, registry_spec, require_completed_effect, specification, POST_IMAGE, POST_CONFIG, POST_ARCHIVE,
    POST_CONTEXT_TREE,
    account_snapshot, validate_runtime_window, observe_model_post, paid_custody, model_grant_snapshot,
)


class HostedModelAuthority(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def qualification(self):
        value = ModelPostQualification(POST_IMAGE, POST_CONFIG, POST_ARCHIVE, self.root / 'proof.json',
                    'earlier setup effect remains unresolved in its original account')
        value.claim()
        self.addCleanup(value.close)
        return value

    def test_planned_model_window_fits_both_actual_custody_and_socket_limits(self):
        def check(artifact, socket, *, driver_artifact=None):
            values = {'WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS': str(artifact),
                      'WORKSTREAM_EXTERNAL_CHECKER_SERVICE_TIMEOUT_SECONDS': str(socket)}
            settings = SimpleNamespace(
                artifact_preparation_total_deadline_seconds=artifact if driver_artifact is None else driver_artifact,
                external_checker_service_timeout_seconds=socket,
            )
            return validate_runtime_window(values, settings)

        self.assertEqual(check(3400, 3660), 720000)
        self.assertEqual(check(3400.0, 3660.0), 720000)
        self.assertEqual(check(720, 660), 720000)
        for artifact in (360, 719):
            with self.assertRaisesRegex(RuntimeError, 'ART custody window'):
                check(artifact, 3660)
        with self.assertRaisesRegex(RuntimeError, 'checker socket window'):
            check(3400, 659)
        with self.assertRaisesRegex(RuntimeError, 'differ from inspected hosted roles'):
            check(3400, 3660, driver_artifact=360)

    def test_short_rehearsal_window_refuses_before_claim_or_public_work(self):
        from experiments.pilot04_external_checker_runtime import public_hosted_attachment as hosted

        attachment = SimpleNamespace(inspect=Mock(), node_root=self.root, values={
            'WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS': '360',
            'WORKSTREAM_EXTERNAL_CHECKER_SERVICE_TIMEOUT_SECONDS': '3660',
        })
        settings = SimpleNamespace(artifact_preparation_total_deadline_seconds=360,
                                   external_checker_service_timeout_seconds=3660)
        with patch('app.core.config.get_settings', return_value=settings), \
                patch.object(ModelPostQualification, 'read_and_claim') as claim, \
                patch.object(hosted, '_run', new_callable=AsyncMock) as public_work:
            with self.assertRaisesRegex(RuntimeError, 'ART custody window'):
                asyncio.run(hosted.run(attachment, 'unused', 'unused', self.root / 'input.json'))
        attachment.inspect.assert_called_once_with()
        claim.assert_not_called()
        public_work.assert_not_called()
        self.assertFalse((self.root / 'model-post-qualification.json').exists())

    def test_hosted_socket_timeout_uses_the_canonical_default_when_not_overridden(self):
        from app.core.config import Settings

        values = {'WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS': '3400'}
        settings = Settings.model_construct(artifact_preparation_total_deadline_seconds=3400)
        self.assertEqual(validate_runtime_window(values, settings), 720000)
        settings.external_checker_service_timeout_seconds -= 1
        with self.assertRaisesRegex(RuntimeError, 'differ from inspected hosted roles'):
            validate_runtime_window(values, settings)

    def test_prepared_effect_recovery_retains_one_exact_predecessor_grant(self):
        def exercise(change=None, *, history=True):
            project, submission, prior_run_id, run_id, registry_id, profile_id = (new_record_id() for _ in range(6))
            now = datetime.now(UTC)
            effect_id, request_hash = str(new_record_id()), 'sha256:' + 'a' * 64
            def grant(identifier):
                return SimpleNamespace(id=str(new_record_id()), checker_run_id=str(identifier),
                    registry_entry_id=registry_id, token_hash='sha256:' + 'b' * 64,
                    external_request_digest='sha256:' + 'c' * 64,
                    execution_facts={'run': str(identifier)}, paid_slot={'submission': str(submission)},
                    authorization_evidence_id=str(new_record_id()), issued_at=now, expires_at=now)
            previous, current = grant(prior_run_id), grant(run_id)
            def call():
                return SimpleNamespace(call_index=0, attempt_id=effect_id,
                                       request_sha256=request_hash, bound_at=now)
            prior_call, current_call = call(), call()
            snapshot = model_grant_snapshot(previous, [prior_call])
            slot = SimpleNamespace(id=str(new_record_id()), submission_id=str(submission), requirement_id=CHECK,
                profile_id=str(profile_id), profile_digest='profile', registry_entry_digest='registry',
                first_request_sha256=request_hash)
            prior_run = SimpleNamespace(id=str(prior_run_id), status='infrastructure_failed',
                                        project_id=str(project), submission_id=str(submission))
            run = SimpleNamespace(project_id=str(project), submission_id=str(submission),
                                  supersedes_checker_run_id=str(prior_run_id))
            grants = [previous, current]
            if change == 'history_mutated':
                previous.execution_facts = {'changed': True}
            elif change == 'new_effect':
                current_call.attempt_id = str(new_record_id())
            elif change == 'unrelated_run':
                run.supersedes_checker_run_id = str(new_record_id())
            elif change == 'extra_grant':
                grants.append(grant(new_record_id()))
            elif change == 'initial':
                grants = [current]
            session = AsyncMock()
            session.__aenter__.return_value = session
            session.scalars.side_effect = [Mock(all=Mock(return_value=rows)) for rows in
                                            (grants, [slot], [current_call], [prior_call])]
            session.get.side_effect = [prior_run, run]
            qualification = SimpleNamespace(state={'prior_model_grant': snapshot} if history else {},
                registry={'registry_entry_id': str(registry_id), 'entry_digest': 'registry'},
                profile=SimpleNamespace(profile_id=profile_id, profile_digest='profile'))
            with patch('app.modules.checkers.execution_repository.stored_request',
                       return_value=SimpleNamespace(policy='same immutable policy')):
                return asyncio.run(paid_custody(Mock(return_value=session), str(project), run_id,
                    str(submission), SimpleNamespace(request_digest=current.external_request_digest), qualification))

        receipt = exercise()
        self.assertEqual(receipt['effect_id'], receipt['prior_model_grant']['effect_id'])
        self.assertNotIn('prior_model_grant', exercise('initial', history=False))
        for change in ('history_mutated', 'new_effect', 'unrelated_run', 'extra_grant'):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                exercise(change)
        with self.assertRaisesRegex(RuntimeError, 'unexpected grant/paid-slot count'):
            exercise(history=False)

    def test_observation_refuses_a_run_from_another_project_task_or_submission(self):
        project, task, submission = (str(new_record_id()) for _ in range(3))
        for field in ('project_id', 'task_id', 'submission_id'):
            run = SimpleNamespace(project_id=project, task_id=task, submission_id=submission)
            setattr(run, field, str(new_record_id()))
            session = AsyncMock()
            session.__aenter__.return_value = session
            session.get.return_value = run
            with self.subTest(field=field), \
                    patch('app.modules.checkers.execution_repository.stored_request') as request:
                with self.assertRaisesRegex(RuntimeError, 'differs from the retained project and Submission'):
                    asyncio.run(observe_model_post(
                        None, None, Mock(return_value=session), None,
                        project=SimpleNamespace(project_id=project), contributor=None,
                        task=task, assignment=None, archive=b'', summary=None, attestation=None,
                        saved={'submission_id': submission}, event_id=new_record_id(), run_id=new_record_id(),
                    ))
                request.assert_not_called()

    def test_observation_checks_real_policy_budget_with_float_settings(self):
        from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy

        policy = LockedExternalPostSubmitPolicy(entries=(), policy_sha256=digest(canonical({
            'schema_version': 'external_post_submit_policy.v1', 'entries': [],
        })))
        project, task, submission = (str(new_record_id()) for _ in range(3))
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.get.return_value = SimpleNamespace(project_id=project, task_id=task, submission_id=submission)
        attachment = SimpleNamespace(values={
            'WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS': '3400.0',
            'WORKSTREAM_EXTERNAL_CHECKER_SERVICE_TIMEOUT_SECONDS': '3660.0',
        })
        settings = SimpleNamespace(artifact_preparation_total_deadline_seconds=3400.0,
                                   external_checker_service_timeout_seconds=3660.0)
        with patch('app.core.config.get_settings', return_value=settings), \
                patch('app.modules.checkers.execution_repository.stored_request',
                      return_value=SimpleNamespace(policy=policy)):
            with self.assertRaisesRegex(RuntimeError, 'locked model qualification execution budget differs'):
                asyncio.run(observe_model_post(
                    attachment, None, Mock(return_value=session), None,
                    project=SimpleNamespace(project_id=project), contributor=None,
                    task=task, assignment=None, archive=b'', summary=None, attestation=None,
                    saved={'submission_id': submission}, event_id=new_record_id(), run_id=new_record_id(),
                ))

    def test_cache_requires_exact_qualified_production_image_not_a_substitute(self):
        from experiments.pilot04_external_checker_runtime import public_hosted_attachment as hosted

        qualification = self.qualification()
        binding = {'node_config': {'cache': [{'repository': 'workstream/terminal-systems-post',
            'platform_manifest_digest': POST_IMAGE.rsplit('@', 1)[1], 'config_image_id': POST_CONFIG,
            'smol': {'archive_sha256': POST_ARCHIVE}}]}}
        (self.root / 'node-binding.json').write_bytes(canonical(binding))
        attachment = SimpleNamespace(node_root=self.root, values={'WORKSTREAM_MODEL_PROXY_ENABLED': 'true'},
                                     custody={'model-proxy': {'image_id': 'verified-by-attachment'}})
        # Supply the qualified source fact independently of this checkout's
        # model-tree content; historical image qualification is not refreshed.
        with patch.object(hosted, '_command', return_value=(POST_CONTEXT_TREE + '\n').encode()) as command:
            qualification.verify_cache(attachment)
            command.assert_called_once_with(['git', 'rev-parse', 'HEAD:pilots/terminal_systems/checkers/post/model'])
            self.assertEqual(qualification.state['image_context_tree'], POST_CONTEXT_TREE)
            qualification.image_config_digest = 'sha256:' + '0' * 64
            with self.assertRaisesRegex(RuntimeError, 'image identity differs'):
                qualification.verify_cache(attachment)
            self.assertEqual(command.call_count, 1)
            qualification.image_config_digest = POST_CONFIG
            binding['node_config']['cache'][0]['smol']['archive_sha256'] = 'sha256:' + '0' * 64
            (self.root / 'node-binding.json').write_bytes(canonical(binding))
            with self.assertRaisesRegex(RuntimeError, 'absent or substituted'):
                qualification.verify_cache(attachment)
            self.assertEqual(command.call_count, 2)

    def test_cache_rejects_changed_source_tree_before_checkpoint(self):
        from experiments.pilot04_external_checker_runtime import public_hosted_attachment as hosted

        qualification = self.qualification()
        binding = {'node_config': {'cache': [{'repository': 'workstream/terminal-systems-post',
            'platform_manifest_digest': POST_IMAGE.rsplit('@', 1)[1], 'config_image_id': POST_CONFIG,
            'smol': {'archive_sha256': POST_ARCHIVE}}]}}
        (self.root / 'node-binding.json').write_bytes(canonical(binding))
        attachment = SimpleNamespace(node_root=self.root, values={'WORKSTREAM_MODEL_PROXY_ENABLED': 'true'},
                                     custody={'model-proxy': {'image_id': 'verified-by-attachment'}})
        retained = qualification.proof_state.read_bytes()
        state = copy.deepcopy(qualification.state)
        with patch.object(hosted, '_command', return_value=('0' * 40 + '\n').encode()) as command, \
                patch.object(qualification, 'checkpoint') as checkpoint:
            with self.assertRaisesRegex(RuntimeError, 'production model image context changed after qualification'):
                qualification.verify_cache(attachment)
            command.assert_called_once_with(['git', 'rev-parse', 'HEAD:pilots/terminal_systems/checkers/post/model'])
            checkpoint.assert_not_called()
        self.assertEqual(qualification.state, state)
        self.assertEqual(qualification.proof_state.read_bytes(), retained)

    def test_one_literal_profile_reserves_full_context_within_the_total_authorization(self):
        profile = profile_spec(new_record_id(), new_record_id())
        self.assertEqual((profile.provider, profile.api, profile.model_snapshot), ('openrouter', 'chat_completions', MODEL))
        self.assertEqual(profile.maximum_input_tokens, 1050000)
        self.assertEqual(profile.maximum_calls, 1)
        self.assertEqual(profile.allowed_tools, ())
        self.assertEqual(profile.maximum_reservation_nanodollars, 5_323_728_000)
        self.assertLessEqual(profile.maximum_reservation_nanodollars, CEILING)
        self.assertEqual(profile.maximum_dispatch_reservation_nanodollars, profile.maximum_reservation_nanodollars)
        with self.assertRaises(ValueError):
            type(profile).model_validate(profile.model_dump(mode='python') | {'maximum_response_bytes': 200703})

    def test_existing_claim_or_alias_cannot_create_another_paid_project(self):
        value = self.qualification()
        value.checkpoint(project_id=str(new_record_id()), phase='authority_published')
        retained = value.proof_state.read_bytes()
        mode = value.proof_state.stat().st_mode
        with self.assertRaises(FileExistsError):
            self.qualification()
        self.assertEqual(value.proof_state.read_bytes(), retained)
        self.assertEqual(value.proof_state.stat().st_mode, mode)
        alias = self.root / 'alias'
        alias.symlink_to(value.proof_state)
        other = ModelPostQualification(value.image_reference, value.image_config_digest, value.image_archive_sha256,
                                       alias, 'unresolved')
        with self.assertRaisesRegex(RuntimeError, 'canonical'):
            other.claim()
        self.assertEqual(value.proof_state.read_bytes(), retained)

    def test_provider_override_is_rejected_before_claim_or_mutation(self):
        config = self.root / 'input.json'
        config.write_bytes(canonical({'image_reference': 'workstream/terminal-systems-post@sha256:' + 'a' * 64,
            'image_config_digest': 'sha256:' + 'b' * 64, 'image_archive_sha256': 'sha256:' + 'c' * 64,
            'proof_state': str(self.root / 'claim'), 'historical_uncertain_reference': 'unresolved',
            'provider': 'openai'}))
        config.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'fields differ'):
            ModelPostQualification.read_and_claim(config, self.root)
        self.assertFalse((self.root / 'claim').exists())

    def test_claim_creation_flushes_its_parent_before_any_public_mutation(self):
        import stat

        flushed = []
        original = os.fsync

        def fsync(descriptor):
            flushed.append('directory' if stat.S_ISDIR(os.fstat(descriptor).st_mode) else 'file')
            original(descriptor)

        with patch('os.fsync', side_effect=fsync):
            self.qualification()
        self.assertEqual(flushed, ['file', 'directory'])

    def test_changing_the_state_path_cannot_reset_the_deployment_authorization(self):
        config = self.root / 'input.json'
        config.write_bytes(canonical({'image_reference': POST_IMAGE, 'image_config_digest': POST_CONFIG,
            'image_archive_sha256': POST_ARCHIVE, 'proof_state': str(self.root / 'another-claim'),
            'historical_uncertain_reference': 'unresolved'}))
        config.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'single fixed state path'):
            ModelPostQualification.read_and_claim(config, self.root)
        self.assertFalse((self.root / 'another-claim').exists())

    def test_public_authority_publication_and_real_rules_bind_the_exact_profile(self):
        import httpx
        from app.adapters.project_agents.manager_authored import _compile_rules
        from app.core.hashing import canonical_json_hash

        qualification = self.qualification()
        project_id = str(new_record_id())
        requests = []
        actor_id, profile_id = new_record_id(), new_record_id()

        async def handler(request):
            body = json.loads(request.content)
            requests.append((request.method, request.url.path, request.headers['Idempotency-Key'], body))
            if request.url.path.endswith('/model-profiles'):
                spec = type(profile_spec(UUID(project_id), new_record_id())).model_validate_json(request.content)
                response = ProjectModelProfile(operation_id=UUID(request.headers['Idempotency-Key']),
                    actor_profile_id=actor_id, spec=spec, profile_digest=canonical_json_hash(body),
                    profile_id=profile_id, authorization_evidence_id=new_record_id(), created_at=datetime.now(UTC)).model_dump(mode='json')
            elif request.url.path.endswith('/model-budget-configurations'):
                response = {'spec': body, 'configuration_id': str(new_record_id()),
                            'lifetime_reserved_nanodollars': 0, 'lifetime_settled_nanodollars': 0}
            else:
                spec = registry_spec(body['image_digest'])
                self.assertEqual(body, spec.model_dump(mode='json'))
                response = {**body, 'entry_digest': spec.spec_digest, 'registry_entry_id': str(new_record_id())}
            return httpx.Response(201, json=response)

        baseline_pre = {'requirement_id': 'project.pre_submit', 'registry_entry_id': str(new_record_id()),
                        'registry_entry_digest': 'sha256:' + 'b' * 64, 'configuration': {}}
        attachment = SimpleNamespace(token_for_label=lambda label: 'scoped-rs256-fixture',
            approval_attachments=lambda count: {'pre_submit_attachments': [baseline_pre]})

        async def exercise():
            async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', transport=httpx.MockTransport(handler)) as client:
                await qualification.bind_project(client, project_id, attachment)
                with self.assertRaisesRegex(RuntimeError, 'already owns one project'):
                    await qualification.bind_project(client, str(new_record_id()), attachment)

        asyncio.run(exercise())
        self.assertEqual([item[1] for item in requests], [
            f'/api/v1/operations/projects/{project_id}/model-profiles',
            f'/api/v1/operations/projects/{project_id}/model-budget-configurations',
            '/api/v1/operations/external-checker-registry'])
        self.assertTrue(all(item[0] == 'POST' for item in requests))
        budget = requests[1][3]
        self.assertEqual(budget['authorized_total_nanodollars'], CEILING)
        self.assertEqual(budget['lifetime_limit_nanodollars'], CEILING)
        self.assertEqual(budget['configuration_version'], 1)
        self.assertEqual(qualification.state['historical_charge']['status'], 'unresolved_separate')
        selected = qualification.approval_attachments()
        self.assertEqual(selected['pre_submit_attachments'], [baseline_pre])
        [attachment] = selected['post_submit_attachments']
        self.assertEqual(attachment['requirement_id'], CHECK)
        self.assertEqual(attachment['registry_entry_id'], qualification.registry['registry_entry_id'])
        self.assertEqual(attachment['registry_entry_digest'], qualification.registry['entry_digest'])
        configuration = attachment['configuration']
        registry_spec('sha256:' + 'a' * 64).configuration_schema.validate_instance(configuration)
        self.assertEqual(configuration['check'], CHECK)
        self.assertEqual(configuration['model_profile_id'], str(profile_id))
        self.assertEqual(configuration['model_profile_digest'], qualification.profile.profile_digest)
        original = qualification.guide_bytes()
        rules = json.loads(qualification.rules(original, 1))
        self.assertNotIn('pre_submit_bindings', rules)
        self.assertNotIn('post_submit_bindings', rules)
        doc = SimpleNamespace(source_item_id=new_record_id(), ingest_id=new_record_id(), sha256=digest(original))
        authored = SimpleNamespace(source_item_id=new_record_id(), ingest_id=new_record_id(), sha256=digest(canonical(rules)))
        result = _compile_rules(SimpleNamespace(agent_version='v1', material=SimpleNamespace(documents=[doc, authored])), [(authored, rules)])
        self.assertEqual([item.stage for item in result.requirements], ['pre_submit', 'post_submit'])
        [suggestion] = [item for item in result.requirements if item.stage == 'post_submit']
        self.assertNotEqual(suggestion.suggestion_id, attachment['requirement_id'])
        self.assertEqual([ref.sha256 for ref in suggestion.evidence_refs], [doc.sha256, authored.sha256])
        self.assertEqual(suggestion.check_specification, specification()[0])
        self.assertTrue(suggestion.check_specification.implementation_needs)
        for count in (0, 2):
            with self.assertRaisesRegex(RuntimeError, 'exactly one baseline PRE'):
                qualification.rules(original, count)

    def test_ambiguous_effect_or_outstanding_reservation_cannot_claim_model_proof(self):
        good = {'reserved_nanodollars': 0, 'effects': [{'state': 'completed', 'provider_response_known': True,
                                                      'request_binding_id': 'request', 'response_binding_id': 'response'}]}
        require_completed_effect(good)
        for state in ('prepared', 'dispatching', 'uncertain', 'known_failed', 'known_no_effect'):
            changed = copy.deepcopy(good)
            changed['effects'][0]['state'] = state
            with self.assertRaisesRegex(RuntimeError, 'ambiguous paid effect'):
                require_completed_effect(changed)
        for changed in ({**good, 'reserved_nanodollars': 1}, {**good, 'effects': []},
                        {**good, 'effects': good['effects'] * 2}):
            with self.assertRaises(RuntimeError):
                require_completed_effect(changed)

    def test_account_snapshot_joins_real_checker_and_setup_slot_owners_without_mutation(self):
        from sqlalchemy.dialects import postgresql

        statements = []

        class ReadOnlySession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, model, identifier):
                return SimpleNamespace(lifetime_reserved_nanodollars=0, lifetime_settled_nanodollars=123,
                                       current_configuration_id='retained-budget')

            async def scalars(self, statement):
                statements.append(str(statement.compile(dialect=postgresql.dialect())))
                return SimpleNamespace(all=lambda: [])

        result = asyncio.run(account_snapshot(ReadOnlySession, str(new_record_id())))
        self.assertEqual(result['settled_nanodollars'], 123)
        self.assertEqual(result['reserved_nanodollars'], 0)
        self.assertFalse(result['provider_invoice_qualified'])
        self.assertIn('LEFT OUTER JOIN checker_model_usage_slots', statements[0])
        self.assertIn('LEFT OUTER JOIN setup_model_usage_slots', statements[0])
        self.assertNotIn('model_usage_effects.project_id', statements[0])

    def test_fixture_is_deterministic_and_its_disclosed_commands_are_coherent(self):
        first = fixture_archive()
        self.assertEqual(first, fixture_archive())
        with ZipFile(BytesIO(first)) as archive:
            self.assertTrue(all(not name.startswith('/') and '..' not in Path(name).parts for name in archive.namelist()))
            archive.extractall(self.root)
        before = subprocess.run(['sh', 'tests/run.sh'], cwd=self.root, capture_output=True, timeout=5)
        self.assertNotEqual(before.returncode, 0)
        subprocess.run(['sh', 'solution/apply.sh'], cwd=self.root, capture_output=True, check=True, timeout=5)
        subprocess.run(['sh', 'tests/run.sh'], cwd=self.root, capture_output=True, check=True, timeout=5)
        self.assertIn(b'no execution or trial measurement is claimed', (self.root / 'evidence/results').read_bytes())

    def test_stalled_source_finalization_does_not_inject_a_worker_task(self):
        from app.core.config import get_settings

        with patch.dict(os.environ, {'WORKSTREAM_CELERY_BROKER_URL': 'redis://127.0.0.1:6379/15'}):
            get_settings.cache_clear()
            try:
                from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe
                from app.workers.outbox import finalize_submission

                task, assignment, operation, key = (str(new_record_id()) for _ in range(4))
                context = {'acceptance_receipt': {'operation_id': operation}, 'idempotency_key': key}
                progress = {'operation_id': operation, 'task_id': task, 'assignment_id': assignment,
                            'idempotency_key': key, 'operation_state': 'finalization_pending',
                            'operationally_stalled': False}
                ticks = iter(range(0, 1000, 101))
                with patch.object(probe, '_json', new=AsyncMock(return_value=progress)) as reads, \
                        patch.object(probe.time, 'monotonic', side_effect=lambda: next(ticks)), \
                        patch.object(probe.asyncio, 'sleep', new=AsyncMock()), \
                        patch.object(finalize_submission, 'apply_async') as dispatch:
                    with self.assertRaisesRegex(RuntimeError, 'source finalization did not complete'):
                        asyncio.run(probe._await_finalized_source(
                            None, None, task, assignment, 'token', context, b'zip'))
                    self.assertEqual(reads.await_count, 2)
                    self.assertTrue(all(call.args[1] == 'GET' for call in reads.await_args_list))
                    dispatch.assert_not_called()
            finally:
                get_settings.cache_clear()

    def test_model_stage_requires_and_uses_the_existing_hosted_attachment(self):
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe
        from experiments.pilot04_external_checker_runtime import public_hosted_attachment as hosted

        args = ['proof', '--database-url', 'postgresql+asyncpg://isolated', '--broker-url', 'redis://isolated',
                '--hosted-model-post', '/private/model.json']
        with patch.object(sys, 'argv', args), patch.object(probe, 'run') as local:
            with self.assertRaises(SystemExit):
                probe.main()
            local.assert_not_called()
        with patch.object(sys, 'argv', args + ['--hosted-attachment', '/private/attachment.json']), \
                patch.object(hosted.HostedAttachment, 'read', return_value='inspected-later'), \
                patch.object(hosted, 'run', new=AsyncMock(return_value={'scope': 'hosted'})) as attach, \
                patch.object(probe, 'run') as local, patch('builtins.print'):
            self.assertEqual(probe.main(), 0)
            attach.assert_awaited_once_with('inspected-later', 'postgresql+asyncpg://isolated', 'redis://isolated',
                                           Path('/private/model.json'))
            local.assert_not_called()


class PublicSourceCommandContracts(unittest.TestCase):
    def test_raw_zip_acceptance_replays_once_then_observes_finalization(self):
        import httpx
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe

        task, assignment, operation = (str(new_record_id()) for _ in range(3))
        accepted = {'operation_id': operation, 'task_id': task, 'assignment_id': assignment,
                    'status': 'accepted', 'replayed': False, 'pre_submission_results': [{}]}
        posts, reads = [], []
        graph = {'submission_id': str(new_record_id()), 'submission_version': 1,
                 'evaluation_request_id': str(new_record_id()), 'admission_id': str(new_record_id())}

        async def respond(request):
            self.assertNotIn('submission-bundle-preparations', request.url.path)
            if request.method == 'POST':
                self.assertEqual(request.headers['Content-Type'], 'application/zip')
                self.assertEqual(request.headers['Content-Length'], '7')
                self.assertEqual(request.content, b'raw-zip')
                posts.append(dict(request.headers))
                return httpx.Response(202, json=accepted | {'replayed': len(posts) > 1})
            self.assertEqual(request.method, 'GET')
            self.assertEqual(dict(request.url.params), {'operation_id': operation})
            reads.append(request.url.path)
            return httpx.Response(200, json={
                'operation_id': operation, 'task_id': task, 'assignment_id': assignment,
                'idempotency_key': posts[0]['idempotency-key'], 'operationally_stalled': False,
                'operation_state': 'finalized' if len(reads) == 2 else 'finalization_pending', **graph})

        async def exercise():
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url='http://test') as client:
                return await probe._submit(client, None, task_id=task, assignment_id=assignment,
                    contributor_token='token', archive=b'raw-zip', summary='summary',
                    attestation='attestation', predecessor_id=None)

        with patch.object(probe, '_finalized_source_evidence', new=AsyncMock(return_value=graph)) as retained, \
                patch.object(probe, '_fixture_hashes', return_value={'expected': 'hashes'}), \
                patch.object(probe.asyncio, 'sleep', new=AsyncMock()):
            saved = asyncio.run(exercise())
        self.assertEqual(posts[0], posts[1])
        self.assertEqual(len(posts), 2)
        self.assertEqual(len(reads), 2)
        self.assertEqual(saved['acceptance_receipt'], accepted)
        self.assertEqual(saved['submission_id'], graph['submission_id'])
        retained.assert_awaited_once()

    def test_progress_selector_substitution_fails_before_retained_reads(self):
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe

        task, assignment, operation, key = (str(new_record_id()) for _ in range(4))
        context = {'acceptance_receipt': {'operation_id': operation}, 'idempotency_key': key}
        valid = {'task_id': task, 'assignment_id': assignment, 'operation_id': operation,
                 'idempotency_key': key, 'operation_state': 'finalized', 'operationally_stalled': False,
                 'submission_id': str(new_record_id()), 'submission_version': 1,
                 'evaluation_request_id': str(new_record_id())}
        with patch.object(probe, '_fixture_hashes', return_value={}), \
                patch.object(probe, '_finalized_source_evidence', new=AsyncMock(return_value={'control': True})) as retained:
            with patch.object(probe, '_json', new=AsyncMock(return_value=valid)):
                self.assertEqual(asyncio.run(probe._await_finalized_source(
                    None, None, task, assignment, 'token', context, b'zip')), {'control': True})
            retained.reset_mock()
            for field in ('task_id', 'assignment_id', 'operation_id', 'idempotency_key'):
                with self.subTest(field=field), \
                        patch.object(probe, '_json', new=AsyncMock(return_value=valid | {field: str(new_record_id())})):
                    with self.assertRaisesRegex(RuntimeError, 'substituted command selectors'):
                        asyncio.run(probe._await_finalized_source(None, None, task, assignment, 'token', context, b'zip'))
                    retained.assert_not_awaited()

    def test_public_claim_starts_work_without_retired_routes(self):
        from app.modules.tasks.schemas import AssignmentResponse
        from experiments.pilot04_external_checker_runtime import public_probe_support as support

        self.assertIn('accepted_at', AssignmentResponse.model_fields)
        self.assertNotIn('started_at', AssignmentResponse.model_fields)
        task, assignment = (str(new_record_id()) for _ in range(2))
        for accepted in ('2026-01-01T00:00:00Z', None):
            replies = [{'id': task}, {}, {}, {'task': {'status': 'in_progress'},
                       'assignment': {'id': assignment, 'accepted_at': accepted}}, {}]
            with self.subTest(accepted=accepted), patch.object(support, '_json', new=AsyncMock(side_effect=replies)) as requests:
                call = support._started_public_task(None, project_id='project', manager_token='manager',
                    contributor_token='contributor', source_ref='claim-contract')
                if accepted is None:
                    with self.assertRaisesRegex(RuntimeError, 'immediately start'):
                        asyncio.run(call)
                else:
                    self.assertEqual(asyncio.run(call), (task, assignment))
                    self.assertTrue(requests.await_args.args[2].endswith('/work-context'))
                paths = [item.args[2] for item in requests.await_args_list]
                self.assertFalse(any(path.endswith('/start') or path.endswith('/submission-requirements') for path in paths))

    def test_finalization_worker_is_exclusive_and_uses_production_app(self):
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe

        with patch.object(probe, '_process', return_value='owned') as launch:
            process, _ = probe._start_finalization_worker({}, Path('/private/proof'))
        self.assertEqual(process, 'owned')
        command = launch.call_args.args[0]
        self.assertEqual(command[command.index('-A') + 1], 'app.workers.celery_app')
        self.assertEqual([x for x in command if x.startswith('--queues=')],
                         ['--queues=workstream.submission_finalization'])

    def test_source_profile_cannot_exceed_the_supplied_runner_window(self):
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe
        from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

        runtime = _source_reservation().runtime_profile
        profile = {'capacity': {'maximum_total_bytes': 4 * 1024**2},
                   'runtime': runtime.model_dump(mode='json'), 'upload_total_seconds': 300.0,
                   'upload_idle_seconds': 10.0, 'foreground_lease_seconds': 10.0,
                   'heartbeat_seconds': 1.0, 'replay_total_seconds': 30.0, 'part_bytes': 5 * 1024**2}
        window = runtime.aggregate_deadline_ms / 1000
        settings = SimpleNamespace(submission_execution_profile=profile, external_checker_service_timeout_seconds=window)
        self.assertEqual(probe._require_source_runtime_window(settings).runtime, runtime)
        settings.external_checker_service_timeout_seconds = window - 0.1
        with self.assertRaisesRegex(RuntimeError, 'exceeds the configured runner request timeout'):
            probe._require_source_runtime_window(settings)

    def test_parser_requires_an_existing_socket_without_starting_a_service(self):
        import socket
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'guide.sock'
            settings = SimpleNamespace(guide_document_parser_socket=path)
            with self.assertRaisesRegex(RuntimeError, 'existing guide parser socket'):
                probe._require_parser_socket(settings)
            with socket.socket(socket.AF_UNIX) as bound:
                bound.bind(str(path))
                self.assertEqual(probe._require_parser_socket(settings), path)
                alias = Path(directory) / 'alias.sock'
                alias.symlink_to(path)
                with self.assertRaisesRegex(RuntimeError, 'existing guide parser socket'):
                    probe._require_parser_socket(SimpleNamespace(guide_document_parser_socket=alias))


if __name__ == '__main__':
    unittest.main()
