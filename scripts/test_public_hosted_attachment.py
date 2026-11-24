"""Hosted attachment refuses substitute services and observes real native copies."""

import copy
import asyncio
import hashlib
import json
from itertools import count as sequence
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/scripts'), str(ROOT / 'backend/tests')]
from experiments.pilot04_external_checker_runtime.public_hosted_attachment import (  # noqa: E402
    validate_container,
    HostedAttachment, manager_rules, deliver_duplicate,
)


class HostedDuplicateEvents(unittest.TestCase):
    def observe(self, event_change=None, *, already_enabled=False, restore_reply=None):
        from celery import Celery
        from kombu.transport.memory import Channel

        app = Celery('hosted-duplicate-proof', broker='memory://')
        self.addCleanup(app.close)
        hostname = 'worker@owned-fixture'
        stopped = threading.Event()
        errors = []
        commands = []
        published = []
        listeners = []
        receiver_type = app.events.Receiver

        def receiver(connection, **options):
            listeners.append(connection)
            return receiver_type(connection, **options)

        def heartbeats():
            try:
                with app.connection_for_write() as connection:
                    with app.events.Dispatcher(connection, hostname=hostname) as dispatcher:
                        while not stopped.is_set():
                            dispatcher.send('worker-heartbeat')
                            stopped.wait(.01)
            except Exception as error:
                errors.append(error)

        def control(command, **options):
            if command == 'enable_events':
                # The in-memory transport's queue registry is process-global;
                # finish its heartbeat producer before queue deletion. Real Redis
                # separately qualifies concurrent worker heartbeats and control.
                stopped.set()
                heartbeat_thread.join(timeout=2)
                self.assertFalse(heartbeat_thread.is_alive())
            self.assertEqual(len(listeners), 1)
            self.assertIsNot(options['connection'], listeners[0],
                             'Redis event subscription must not share pidbox control connection')
            self.assertEqual(options['destination'], [hostname])
            self.assertTrue(options['reply'])
            self.assertEqual(options['timeout'], 5)
            commands.append(command)
            reply = ({'ok': 'task events already enabled'} if already_enabled
                     else {'ok': 'task events enabled'}) if command == 'enable_events' else (
                         restore_reply or {'ok': 'task events disabled'})
            return [{hostname: reply}]

        def publish(**options):
            published.append(options)
            self.assertEqual(commands, ['enable_events'])
            self.assertFalse(options['retry'])
            self.assertTrue(options['ignore_result'])
            identifier = options['task_id']
            queue = app.conf.event_queue_prefix + '.ws-proof-' + identifier
            self.assertIn(queue, Channel.queues)
            events = [
                ('task-received', {'uuid': str(uuid4()), 'name': 'unrelated'}),
                ('task-received', {'uuid': identifier, 'name': task.name}),
                ('task-succeeded', {'uuid': identifier, 'result': "{'status': 'delivery_unavailable'}"}),
            ]
            if event_change:
                event_change(events, identifier)
            with app.connection_for_write() as connection:
                for kind, fields in events:
                    worker = fields.pop('_worker', hostname)
                    with app.events.Dispatcher(connection, hostname=worker) as dispatcher:
                        dispatcher.send(kind, **fields)

        task = SimpleNamespace(app=app, name='workstream.outbox.deliver_event', apply_async=publish)
        heartbeat_thread = threading.Thread(target=heartbeats, daemon=True)
        heartbeat_thread.start()
        try:
            with patch.object(app.events, 'Receiver', side_effect=receiver), \
                    patch.object(app.control, 'broadcast', side_effect=control):
                result = deliver_duplicate(task, hostname, 'event-id', 'project-id')
            self.assertEqual(result, {'task_id': published[0]['task_id'],
                                     'result': {'status': 'delivery_unavailable'}})
            self.assertEqual(published[0]['args'], ('event-id', 'project-id'))
            return result
        finally:
            stopped.set()
            heartbeat_thread.join(timeout=2)
            self.assertFalse(heartbeat_thread.is_alive())
            self.assertFalse(errors)
            self.assertEqual(commands, ['enable_events'] if already_enabled
                             else ['enable_events', 'disable_events'])
            for item in published:
                self.assertNotIn(app.conf.event_queue_prefix + '.ws-proof-' + item['task_id'], Channel.queues)

    def test_real_event_queue_is_armed_before_dispatch_and_then_removed(self):
        self.observe()
        self.observe(already_enabled=True)

    def test_wrong_task_result_failure_and_terminal_before_received_are_refused(self):
        def wrong_name(events, identifier):
            events[1][1]['name'] = 'another.task'
        def wrong_result(events, identifier):
            events[2][1]['result'] = "{'status': 'delivered'}"
        def wrong_worker(events, identifier):
            events[2][1]['_worker'] = 'worker@another-fixture'
        def failed(events, identifier):
            events[2] = ('task-failed', {'uuid': identifier})
        def reversed_order(events, identifier):
            events[1], events[2] = events[2], events[1]
        for change in (wrong_name, wrong_result, wrong_worker, failed, reversed_order):
            with self.subTest(change=change.__name__), self.assertRaises(RuntimeError):
                self.observe(change)

    def test_absolute_completion_deadline_is_enforced(self):
        def elapsed(events, identifier):
            timer = patch('experiments.pilot04_external_checker_runtime.public_hosted_attachment.time.monotonic',
                          side_effect=lambda: next(ticks))
            ticks = sequence(step=121)
            timer.start()
            self.addCleanup(timer.stop)
        with self.assertRaisesRegex(RuntimeError, 'completion was not observed'):
            self.observe(elapsed)

    def test_failed_event_restore_cannot_claim_success(self):
        with self.assertRaisesRegex(RuntimeError, 'not restored'):
            self.observe(restore_reply={'error': 'not restored'})


class HostedContainerCustody(unittest.TestCase):
    def setUp(self):
        self.rendered = {
            'image': 'example/backend@sha256:' + 'a' * 64, 'user': '10001:10001',
            'command': ['python', '-m', 'celery', '-A', 'app.workers.celery_app', 'worker', '--pool=prefork'],
            'environment': {'WORKSTREAM_ENVIRONMENT': 'production',
                            'WORKSTREAM_PROJECT_AGENT_RUNTIME': 'manager_authored'},
            'volumes': [{'type': 'bind', 'source': '/owned/scratch', 'target': '/owned/scratch'}],
            'secrets': [{'source': 'database', 'target': 'database_url'}],
            'networks': {'default': None},
        }
        self.image = {'Id': 'sha256:' + 'b' * 64, 'Config': {
            'Entrypoint': ['/usr/local/bin/workstream-release-entrypoint'], 'Env': ['PATH=/usr/bin']}}
        self.container = {'Id': 'exact-worker', 'Image': self.image['Id'],
                          'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                          'Config': {'Image': self.rendered['image'], 'User': self.rendered['user'],
                                     'Cmd': self.rendered['command'],
                                     'Entrypoint': self.image['Config']['Entrypoint'],
                                     'Env': ['PATH=/usr/bin'] + [k + '=' + v for k, v in self.rendered['environment'].items()]},
                          'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False,
                                         'CapDrop': ['ALL'], 'CapAdd': None,
                                         'SecurityOpt': ['no-new-privileges:true']},
                          'NetworkSettings': {'Networks': {'owned_default': {}}},
                          'Mounts': [{'Type': 'bind', 'Source': '/owned/scratch',
                                      'Destination': '/owned/scratch', 'RW': True},
                                     {'Type': 'bind', 'Source': '/private/db',
                                      'Destination': '/run/secrets/database_url', 'RW': False}]}

    def check(self, container=None):
        validate_container('worker', self.rendered, container or self.container,
                           self.image, {'database': {'file': '/private/db'}},
                           {'default': {'name': 'owned_default'}})

    def test_exact_production_service_is_accepted(self):
        self.check()

    def test_recorded_worker_host_api_and_hmac_are_refused(self):
        for command in (
            ['python', '-m', 'celery', '-A', 'experiments.pilot04_external_checker_runtime.guide_worker', 'worker'],
            ['python', '-m', 'uvicorn', 'experiments.pilot04_external_checker_runtime.public_intake_observer:app'],
        ):
            changed = copy.deepcopy(self.container)
            changed['Config']['Cmd'] = command
            with self.assertRaisesRegex(RuntimeError, 'executable differs'):
                self.check(changed)
        for environment in ('WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET=fixture-secret',
                            'WORKSTREAM_CELERY_TASK_ALWAYS_EAGER=true',
                            'WORKSTREAM_PROBE_INTAKE_TRACE=/tmp/fake'):
            changed = copy.deepcopy(self.container)
            changed['Config']['Env'].append(environment)
            with self.assertRaisesRegex(RuntimeError, 'extra environment'):
                self.check(changed)

    def test_same_labels_cannot_hide_foreign_image_mount_or_entrypoint(self):
        changes = (
            ('Image', 'sha256:' + 'c' * 64),
            ('Mounts', self.container['Mounts'] + [{'Type': 'bind', 'Source': '/var/run/docker.sock',
                                                  'Destination': '/var/run/docker.sock', 'RW': True}]),
            ('Config', dict(self.container['Config'], Entrypoint=['/bin/sh'])),
            ('HostConfig', dict(self.container['HostConfig'], Privileged=True)),
            ('State', {'Running': True, 'Health': {'Status': 'starting'}}),
            ('NetworkSettings', {'Networks': {'foreign': {}}}),
            ('HostConfig', dict(self.container['HostConfig'], PortBindings={
                '8000/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8000'}]})),
        )
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.check(dict(self.container, **{key: value}))

    def test_tmpfs_must_match_rendered_targets_and_options(self):
        self.rendered['tmpfs'] = ['/tmp:mode=0700,uid=10001,gid=10001']
        self.container['HostConfig']['Tmpfs'] = {'/tmp': 'gid=10001,mode=0700,uid=10001'}
        self.check()
        for mutation in ('code-cover', 'extra-record', 'missing', 'wrong-owner', 'extra-option'):
            changed = copy.deepcopy(self.container)
            if mutation == 'code-cover':
                changed['HostConfig']['Tmpfs']['/app'] = 'rw,uid=10001,gid=10001'
                changed['Mounts'].append({'Type': 'tmpfs', 'Destination': '/app', 'RW': True})
            elif mutation == 'extra-record':
                changed['Mounts'].append({'Type': 'tmpfs', 'Destination': '/app', 'RW': True})
            elif mutation == 'missing':
                changed['HostConfig']['Tmpfs'] = {}
            elif mutation == 'wrong-owner':
                changed['HostConfig']['Tmpfs']['/tmp'] = 'mode=0700,uid=0,gid=10001'
            else:
                changed['HostConfig']['Tmpfs']['/tmp'] += ',exec'
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, 'tmpfs differs'):
                self.check(changed)

    def test_parser_uses_its_exact_declared_isolation_and_resource_profile(self):
        self.rendered.update(
            user='0:0', command=['python', '-m', 'app.adapters.guide_document_tools.service'],
            environment={'WORKSTREAM_RELEASE_ROLE': 'parser'}, network_mode='none',
            cap_add=['KILL', 'SETGID', 'SETUID'], mem_limit='536870912',
            memswap_limit='536870912', cpus=1.0, pids_limit=64,
            tmpfs=['/tmp:mode=0700,uid=10002,gid=10001,size=268435456,noexec,nosuid,nodev'],
        )
        del self.rendered['networks']
        self.container['Config'].update(User='0:0', Cmd=self.rendered['command'],
                                        Env=['PATH=/usr/bin', 'WORKSTREAM_RELEASE_ROLE=parser'])
        self.container['HostConfig'].update(
            CapAdd=['CAP_KILL', 'CAP_SETGID', 'CAP_SETUID'], NetworkMode='none',
            Memory=536870912, MemorySwap=536870912, NanoCpus=1_000_000_000, PidsLimit=64,
            Tmpfs={'/tmp': self.rendered['tmpfs'][0].split(':', 1)[1]},
        )
        self.container['NetworkSettings']['Networks'] = {'none': {}}
        self.check()
        for key, value in (('CapAdd', ['CAP_SYS_ADMIN']), ('NetworkMode', 'host'),
                           ('Memory', 0), ('MemorySwap', -1), ('NanoCpus', 0), ('PidsLimit', -1)):
            changed = copy.deepcopy(self.container)
            changed['HostConfig'][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.check(changed)


class NativePreparationObservation(unittest.TestCase):
    def test_only_successful_final_copy_records_completion_without_altering_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / 'wrapper'
            shutil.copyfile(ROOT / 'experiments/pilot04_external_checker_runtime/public_runtime_wrapper.py', wrapper)
            binary = root / 'smol'
            binary.write_text('#!/bin/sh\nprintf "actual-native-output\\n"\nexit "$RESULT"\n')
            binary.chmod(0o700)
            trace = root / 'trace'
            leases = root / 'smol-leases'
            leases.mkdir()
            lease = {'name': 'intake-one', 'owner': 'owned', 'epoch': 'original',
                     'expires_ms': 100000, 'lifetime_ms': 90000}
            (leases / 'intake-one.json').write_text(json.dumps(lease))
            wrapper.with_suffix('.json').write_text(json.dumps({
                'trace': str(trace), 'binary': str(binary), 'project_archive': '/project.tar',
                'socket': str(root / 'node.sock')}))
            for status, destination, completed in ((7, 'intake-one:/.workstream-guest', False),
                                                   (0, 'intake-one:/unrelated', False),
                                                   (0, 'intake-one:/.workstream-guest', True)):
                trace.write_text(json.dumps({'operation': 'create', 'name': 'intake-one',
                                             'project': False, 'lease': lease}) + '\n')
                result = subprocess.run([sys.executable, str(wrapper), 'machine', 'cp', '--mode', '0555',
                                         '/guest', destination], env={'RESULT': str(status)},
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, status)
                self.assertEqual(result.stdout, b'actual-native-output\n')
                events = [json.loads(line) for line in trace.read_text().splitlines()]
                self.assertEqual(len(events), 2 if completed else 1)
                if completed:
                    self.assertEqual(events[-1]['operation'], 'prepare_completed')
                    self.assertEqual(events[-1]['name'], 'intake-one')
                    self.assertEqual(events[-1]['lease'], lease)
                    self.assertFalse(events[-1]['project'])


class HostedFixtureContracts(unittest.TestCase):
    def test_fresh_setup_grants_operator_then_registers_exact_supplied_baseline_capabilities(self):
        import httpx
        from datetime import UTC, datetime
        from app.core.identifiers import new_record_id
        from app.modules.checkers.api.external import ExternalCheckerRegistrySpec
        from experiments.pilot04_external_checker_runtime.public_probe_support import _locked_spec

        capabilities = {'pre_submit': {'capability_id': 'probe.hosted_pre', 'capability_version': 'v1'},
                        'post_submit': {'capability_id': 'probe.hosted_post', 'capability_version': 'v1'}}
        attachment = HostedAttachment('http://127.0.0.1:8000', Path('/release'), Path('/issuer'),
                                      Path('/node'), capabilities, 'sha256:fixture')
        attachment.actors = {label: SimpleNamespace(actor_profile_id=new_record_id())
                             for label in ('access-admin', 'operator', 'manager')}
        image = {'repository': 'workstream-test/public-journey', 'platform_manifest_digest': 'sha256:' + 'a' * 64}
        attachment.native_binding = {'node_config': {'cache': [image]}}
        operations, registered_specs = [], []

        async def respond(request):
            body = json.loads(request.content)
            if request.url.path == '/api/v1/admin-role-grants':
                operations.append('grant:' + body['role'])
                return httpx.Response(201, json={'granted': True})
            self.assertIn('grant:operator', operations)
            self.assertEqual(request.url.path, '/api/v1/operations/external-checker-registry')
            self.assertEqual(request.headers['Authorization'], 'Bearer token:operator')
            spec = ExternalCheckerRegistrySpec.model_validate_json(request.content)
            operations.append('registry:' + spec.phase)
            registered_specs.append(spec)
            receipt = body | {'registry_entry_id': str(new_record_id()), 'entry_digest': spec.spec_digest,
                'registration_operation_id': request.headers['Idempotency-Key'],
                'registered_by_actor_profile_id': str(attachment.actors['operator'].actor_profile_id),
                'authorization_decision_event_id': str(new_record_id()), 'created_at': datetime.now(UTC).isoformat()}
            return httpx.Response(201, json=receipt)

        async def services(client):
            operations.append('services')

        async def transition(phase):
            operations.append(phase)

        async def exercise():
            async with httpx.AsyncClient(base_url=attachment.origin, transport=httpx.MockTransport(respond)) as client:
                await attachment.prepare_actors(client, None)

        with patch.object(attachment, 'admit_actors', new=AsyncMock()), \
                patch.object(attachment, 'setup_command', side_effect=lambda *args: operations.append('bootstrap')), \
                patch.object(attachment, 'provision_services', side_effect=services), \
                patch.object(attachment, 'transition', side_effect=transition), \
                patch.object(attachment, 'token_for_label', side_effect=lambda label: 'token:' + label):
            asyncio.run(exercise())
        self.assertEqual(operations, ['bootstrap', 'services', 'grant:operator', 'registry:pre_submit',
                                      'registry:post_submit', 'grant:project_manager', 'shadow'])
        self.assertEqual(len(registered_specs), 2)
        for spec in registered_specs:
            expected = _locked_spec(spec.phase, image).model_dump(mode='json') | capabilities[spec.phase]
            self.assertEqual(spec.model_dump(mode='json'), expected)
        selected = attachment.approval_attachments(1)
        for phase in ('pre_submit', 'post_submit'):
            published = attachment.registered_images[phase]
            self.assertEqual(selected[phase + '_attachments'], [{
                'requirement_id': 'project.' + phase,
                'registry_entry_id': str(published.registry_entry_id),
                'registry_entry_digest': published.entry_digest, 'configuration': {},
            }])
        for count in (0, 2):
            with self.subTest(count=count), self.assertRaisesRegex(RuntimeError, 'exactly one PRE'):
                attachment.approval_attachments(count)

    def test_baseline_registration_refuses_unvalidated_cache_and_substituted_receipts(self):
        import httpx
        from datetime import UTC, datetime
        from app.core.identifiers import new_record_id
        from app.modules.checkers.api.external import ExternalCheckerRegistrySpec

        capabilities = {phase: {'capability_id': 'probe.' + phase, 'capability_version': 'v1'}
                        for phase in ('pre_submit', 'post_submit')}
        attachment = HostedAttachment('http://127.0.0.1:8000', Path('/release'), Path('/issuer'),
                                      Path('/node'), capabilities, 'sha256:fixture')
        operator_id = new_record_id()
        attachment.actors['operator'] = SimpleNamespace(actor_profile_id=operator_id)
        image = {'repository': 'workstream-test/public-journey', 'platform_manifest_digest': 'sha256:' + 'a' * 64}
        requested = []

        async def refuse(request):
            requested.append(request.url.path)
            raise AssertionError('invalid cache must refuse before registration')

        async def empty_or_ambiguous():
            async with httpx.AsyncClient(base_url=attachment.origin, transport=httpx.MockTransport(refuse)) as client:
                for images in ([], [image, image], [dict(image, repository='workstream/terminal-systems-post')]):
                    attachment.native_binding = {'node_config': {'cache': images}}
                    with self.assertRaisesRegex(RuntimeError, 'absent or ambiguous'):
                        await attachment.register_baseline_capabilities(client)

        asyncio.run(empty_or_ambiguous())
        self.assertEqual(requested, [])
        attachment.native_binding = {'node_config': {'cache': [image]}}

        async def exercise(fault):
            async def respond(request):
                body = json.loads(request.content)
                if fault == 'image':
                    body['image_digest'] = 'sha256:' + 'f' * 64
                spec = ExternalCheckerRegistrySpec.model_validate(body)
                receipt = body | {'registry_entry_id': str(new_record_id()), 'entry_digest': spec.spec_digest,
                    'registration_operation_id': request.headers['Idempotency-Key'],
                    'registered_by_actor_profile_id': str(operator_id if fault != 'actor' else new_record_id()),
                    'authorization_decision_event_id': str(new_record_id()), 'created_at': datetime.now(UTC).isoformat()}
                if fault == 'operation':
                    receipt['registration_operation_id'] = str(uuid4())
                return httpx.Response(201, json=receipt)
            async with httpx.AsyncClient(base_url=attachment.origin, transport=httpx.MockTransport(respond)) as client:
                with self.assertRaisesRegex(RuntimeError, 'substituted specification or authority'):
                    await attachment.register_baseline_capabilities(client)

        with patch.object(attachment, 'token_for_label', return_value='token:operator'):
            for fault in ('image', 'actor', 'operation'):
                asyncio.run(exercise(fault))

    def test_service_setup_uses_public_owner_endpoint_and_stable_exact_replay_keys(self):
        import httpx
        from provision_local_service_actors import JOURNEY_SERVICE_IDENTITIES

        attachment = HostedAttachment('http://127.0.0.1:8000', Path('/release'), Path('/issuer'),
                                      Path('/node'), {}, 'sha256:fixture')
        attachment.actors['access-admin'] = SimpleNamespace(actor_profile_id=uuid4())
        observed = []

        async def respond(request):
            observed.append((request.method, request.url.path, request.headers['Authorization'],
                             request.headers['Idempotency-Key'], json.loads(request.content)))
            return httpx.Response(201, json={'created': True})

        async def exercise():
            async with httpx.AsyncClient(base_url=attachment.origin, transport=httpx.MockTransport(respond)) as client:
                await attachment.provision_services(client)
                await attachment.provision_services(client)

        with patch.object(attachment, 'token_for_label', return_value='scoped-rs256-token'):
            asyncio.run(exercise())
        count = len(JOURNEY_SERVICE_IDENTITIES)
        self.assertEqual(observed[:count], observed[count:])
        self.assertEqual([item[4]['service_identity'] for item in observed[:count]], list(JOURNEY_SERVICE_IDENTITIES))
        self.assertTrue(all(item[:3] == ('POST', '/api/v1/service-actors', 'Bearer scoped-rs256-token')
                            for item in observed))
        self.assertEqual(len({item[3] for item in observed}), count)

    def test_scoped_fixture_token_uses_rs256_without_embedded_product_roles(self):
        import jwt
        from experiments.hosted_drill_identity.fixture import initialize, read_private, ISSUER, AUDIENCE

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'issuer'
            initialize(root)
            attachment = HostedAttachment('http://127.0.0.1:8000', root / 'release.env', root,
                                          root / 'node', {}, 'sha256:unused')
            token = attachment.token_for_label('operator')
            key = jwt.PyJWK(json.loads(read_private(root / 'jwks.json'))['keys'][0]).key
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=ISSUER, audience=AUDIENCE)
            self.assertEqual(claims['scope'], 'workstream:access')
            self.assertEqual(claims['subject_kind'], 'human')
            self.assertEqual(claims['exp'] - claims['iat'], 900)
            self.assertNotIn('roles', claims)
            self.assertEqual(list(root.glob('token-*')), [])
            with self.assertRaises(jwt.InvalidAlgorithmError):
                jwt.decode(token, key, algorithms=['HS256'])

    def test_manager_rules_compile_with_production_dto_and_original_citation(self):
        from app.adapters.project_agents.manager_authored import _compile_rules

        original = b'Explicit synthetic hosted runtime guide.'
        document = SimpleNamespace(source_item_id=uuid4(), ingest_id=uuid4(),
                                   sha256='sha256:' + hashlib.sha256(original).hexdigest())
        rules = SimpleNamespace(source_item_id=uuid4(), ingest_id=uuid4(), sha256='sha256:' + 'f' * 64)
        context = SimpleNamespace(agent_version='v1', material=SimpleNamespace(documents=[document, rules]))
        for count in (0, 1, 2):
            authored = json.loads(manager_rules(original, count))
            result = _compile_rules(context, [(rules, authored)])
            self.assertEqual(result.status, 'draft_ready')
            self.assertEqual(len([item for item in result.requirements if item.stage == 'pre_submit']), count)
            self.assertEqual(len([item for item in result.requirements if item.stage == 'post_submit']), 1)
            self.assertEqual(len(result.requirements), count + 1)
            self.assertEqual(result.findings[0].evidence_refs[0].sha256, document.sha256)
            for suggestion in result.requirements:
                self.assertEqual([ref.sha256 for ref in suggestion.evidence_refs],
                                 [document.sha256, rules.sha256])
                self.assertTrue(suggestion.suggestion_id.startswith('suggested.'))
                self.assertTrue(suggestion.check_specification.check_steps)
                self.assertTrue(suggestion.check_specification.pass_conditions)
                self.assertTrue(suggestion.check_specification.negative_tests)
            self.assertNotIn('pre_submit_bindings', authored)
            self.assertNotIn('post_submit_bindings', authored)
            self.assertNotIn('capability_suggestions', authored)

    def test_hosted_cli_never_calls_local_launcher(self):
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe
        from experiments.pilot04_external_checker_runtime import public_hosted_attachment as hosted

        with patch.object(sys, 'argv', ['proof', '--hosted-attachment', '/private/attach.json',
                                       '--database-url', 'postgresql+asyncpg://isolated', '--broker-url', 'redis://isolated']), \
                patch.object(hosted.HostedAttachment, 'read', return_value='attached'), \
                patch.object(hosted, 'run', new=AsyncMock(return_value={'attached': True})) as attached, \
                patch.object(probe, 'run') as launch, patch('builtins.print'):
            self.assertEqual(probe.main(), 0)
            attached.assert_awaited_once_with('attached', 'postgresql+asyncpg://isolated', 'redis://isolated')
            launch.assert_not_called()
        with patch.object(sys, 'argv', ['proof', '--hosted-attachment', '/private/attach.json',
                                       '--database-url', 'postgresql+asyncpg://isolated', '--broker-url', 'redis://isolated',
                                       '--node-config', '/local/node.json']), patch.object(probe, 'run') as launch:
            with self.assertRaises(SystemExit):
                probe.main()
            launch.assert_not_called()

    def test_native_execution_refuses_early_cleanup_or_reset_deadline(self):
        from experiments.pilot04_external_checker_runtime.public_runtime_trials import _require_original_runtime_expiry

        created = {'lease': {'epoch': 'original', 'expires_ms': 1000}}
        _require_original_runtime_expiry(created, {'wall_ms': 1001, 'lease': created['lease']})
        for deletion in (
            {'wall_ms': 999, 'lease': created['lease']},
            {'wall_ms': 1001, 'lease': {'epoch': 'original', 'expires_ms': 2000}},
            {'wall_ms': 1001, 'lease': {'epoch': 'restarted', 'expires_ms': 1000}},
        ):
            with self.subTest(deletion=deletion), self.assertRaisesRegex(RuntimeError, 'original lease expiry'):
                _require_original_runtime_expiry(created, deletion)

    def test_selected_wait_failure_does_not_claim_aggregate_vm_expiry(self):
        from experiments.pilot04_external_checker_runtime import public_runtime_trials as runtime

        lease = {'epoch': 'original', 'expires_ms': 120000}
        events = [{'operation': 'create', 'project': True, 'lease': lease},
                  {'operation': 'exec', 'project': True, 'wall_ms': 1000},
                  {'operation': 'delete', 'project': True, 'wall_ms': 31000, 'lease': dict(lease)}]
        row = SimpleNamespace(terminal_json={'infrastructure_failure_code': 'implementation_unavailable'},
            request_json={'policy': {'entries': [{'registry': {'resources': {'deadline_ms': 30000}}}]}})
        def check():
            return asyncio.run(runtime._runtime_fault_evidence(Path('/operator'), 0, 'project_wait_failure', None, row))
        with patch.object(runtime, 'trace_events', return_value=events):
            check()  # Cleanup before aggregate expiry is valid for this inner wait/failure vector.
            for target, field, value in ((events[2], 'wall_ms', 30999),
                    (events[2]['lease'], 'expires_ms', 240000),
                    (row.terminal_json, 'infrastructure_failure_code', 'deadline_exceeded')):
                original = target[field]
                target[field] = value
                try:
                    with self.subTest(field=field), self.assertRaises(RuntimeError):
                        check()
                finally:
                    target[field] = original

    def test_pre_runtime_fault_vectors_use_single_vm_and_separate_tasks(self):
        from experiments.pilot04_external_checker_runtime import public_runtime_trials as runtime

        operations = []
        row = SimpleNamespace(id='run', status='infrastructure_failed', terminal_json={'infrastructure_failure_code': 'failure'})
        async def source(client, route, headers, token, key, content, expected):
            self.assertEqual(expected, 503)
            operations.append(route)
            return {'error': {'code': 'service_unavailable'}}
        async def resume():
            operations.append('start')
        async def accepted(*args):
            return {'submission_id': 'submission-' + args[10]}

        project = SimpleNamespace(project_id=uuid4())
        with patch.object(runtime, '_public_project', new=AsyncMock(return_value=(project, None, 'manager', 'actor'))), \
                patch.object(runtime, '_started_public_task', new=AsyncMock(side_effect=[(f'task-{i}', f'assignment-{i}') for i in range(4)])), \
                patch.object(runtime, 'archive_with_modes', return_value=b'zip'), \
                patch.object(runtime, '_with_fixture_file', return_value=b'wait'), \
                patch.object(runtime, '_source_request', side_effect=source), \
                patch.object(runtime, '_selected', new=AsyncMock(return_value=row)), \
                patch.object(runtime, '_runtime_fault_evidence', new=AsyncMock(return_value=[])), \
                patch.object(runtime, '_recover_failed_source', new=AsyncMock(side_effect=accepted)), \
                patch.object(runtime, 'trace_events', return_value=[]), \
                patch.object(runtime, 'node_command', new=AsyncMock(return_value={'foreign_preserved': True, 'resources': {}})), \
                patch.object(runtime, 'assert_launches', return_value=['vm']) as launches, \
                patch.object(runtime, '_drain_source_trial_posts', new=AsyncMock()) as drain, \
                patch.object(runtime, '_post_launch_trials', new=AsyncMock(return_value=[])) as posts:
            asyncio.run(runtime.public_runtime_trials(None, None, None, Path('/operator'),
                stop_worker=lambda: operations.append('stop'), start_worker=resume, operator_token='operator'))
        self.assertEqual(operations, ['stop'] + [f'/api/v1/tasks/task-{i}/submissions' for i in range(4)] + ['start'])
        self.assertEqual([(call.kwargs['creates'], call.kwargs['executions']) for call in launches.call_args_list],
                         [(1, 0), (1, 0), (1, 1), (1, 1)])
        self.assertEqual(len(drain.await_args.args[2]), 4)
        self.assertEqual(posts.await_args.args[7], 'operator')

    def test_post_native_retries_install_fault_after_t5_and_use_operator_recovery(self):
        from experiments.pilot04_external_checker_runtime import public_runtime_trials as runtime
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe

        operations = []
        async def submit(*args):
            operations.append('submit')
            self.assertEqual(args[6], 202)
            return {'accepted': True}
        async def finalized(*args):
            operations.append('T5')
            return {'submission_id': 'submission'}
        async def node(root, action):
            operations.append(action)
            return {'foreign_preserved': True, 'resources': {}}
        async def resume():
            operations.append('start')
        async def complete(*args, **kwargs):
            operations.append('POST')
        async def retry(*args):
            self.assertEqual(args[4], 'operator')
            operations.append('operator_retry')
            return object(), {'receipt_id': 'receipt'}
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.get.return_value = SimpleNamespace(evaluation_event_id='event')
        with patch.object(runtime, '_started_public_task', new=AsyncMock(side_effect=[('task1', 'assignment1'), ('task2', 'assignment2')])), \
                patch.object(runtime, '_source_request', side_effect=submit), \
                patch.object(runtime, '_selected', new=AsyncMock()), patch.object(runtime, '_assert_current_pre'), \
                patch.object(runtime, '_observe_accepted_source', side_effect=finalized), \
                patch.object(runtime, 'node_command', side_effect=node), patch.object(runtime, 'trace_events', return_value=[]), \
                patch.object(runtime, 'assert_launches', return_value=['vm']) as launches, \
                patch.object(runtime, '_wait_outbox_acknowledged', new=AsyncMock()), \
                patch.object(runtime, 'retry_post_outage', side_effect=retry), \
                patch.object(probe, '_complete_post', side_effect=complete):
            asyncio.run(runtime._post_launch_trials(None, lambda: session, 'project', 'manager', 'actor', b'zip',
                Path('/operator'), 'operator', stop_worker=lambda: operations.append('stop'), start_worker=resume))
        self.assertEqual(operations, ['stop', 'submit', 'T5', 'project_fail_once', 'start', 'POST', 'drained',
            'stop', 'submit', 'T5', 'project_fail_all', 'start', 'operator_retry', 'POST', 'drained', 'clear', 'drained'])
        self.assertEqual([(call.kwargs['creates'], call.kwargs['executions']) for call in launches.call_args_list],
                         [(2, 1), (3, 0), (1, 1)])

    def test_source_pre_retains_default_stop_and_exact_one_native_member(self):
        from experiments.pilot04_external_checker_runtime.public_intake_trials import _assert_current_pre

        requirement = 'terminal.pre.incident_summary_layout'
        registry = {'registry_entry_id': 'locked-entry', 'entry_digest': 'locked-digest',
                    'image_digest': 'sha256:' + 'a' * 64}
        member = {'order': 0, 'requirement_id': requirement, 'registry_entry_id': 'locked-entry',
                  'registry_entry_digest': 'locked-digest', 'request_digest': 'request',
                  'result': {'verdict': 'passed', 'request_digest': 'request', 'findings': []},
                  'isolation': {'runtime': 'smolvm', 'isolation_mode': 'smol-microvm',
                                'platform_manifest_digest': registry['image_digest']}}
        execution = {'required_external_count': 1, 'eligible': True,
                     'workstream_default': {'eligible': True, 'checks': []}, 'external_members': [member]}
        def row(value):
            return SimpleNamespace(status='completed', terminal_json={'execution': value},
                request_json={'policy': {'entries': [{'stage': 'pre_submit',
                    'requirement_id': requirement, 'registry': registry}]}})

        _assert_current_pre(row(execution))
        secret = copy.deepcopy(execution)
        secret.update(eligible=False, external_members=[], workstream_default={'eligible': False,
            'checks': [{'status': 'failed', 'failure_code': 'high_confidence_secret_detected'}]})
        _assert_current_pre(row(secret), failure='secret')
        project = copy.deepcopy(execution)
        project['eligible'] = False
        project['external_members'][0]['result'].update(verdict='failed', findings=[{'code': 'probe.project_rule_failed'}])
        _assert_current_pre(row(project), failure='project')
        for field, value in (('required_external_count', 0), ('external_members', []), ('eligible', False)):
            invalid = copy.deepcopy(execution)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                _assert_current_pre(row(invalid))
        for field, value in (('order', 1), ('requirement_id', 'foreign'),
                             ('registry_entry_id', 'foreign'), ('registry_entry_digest', 'foreign'),
                             ('request_digest', 'foreign')):
            invalid = copy.deepcopy(execution)
            invalid['external_members'][0][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                _assert_current_pre(row(invalid))
        invalid = copy.deepcopy(execution)
        invalid['external_members'][0]['isolation']['platform_manifest_digest'] = 'sha256:' + 'b' * 64
        with self.assertRaisesRegex(RuntimeError, 'exact native request/result custody'):
            _assert_current_pre(row(invalid))
        selected = row(execution)
        selected.request_json['policy']['entries'][0]['requirement_id'] = 'foreign'
        with self.assertRaisesRegex(RuntimeError, 'default-before-project boundary'):
            _assert_current_pre(selected)
        secret['external_members'] = [member]
        with self.assertRaisesRegex(RuntimeError, 'default blocker'):
            _assert_current_pre(row(secret), failure='secret')

    def test_local_approval_uses_exact_registry_entries_in_root_transaction(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from app.core.identifiers import new_record_id
        from app.modules.checkers import external_registry as registry
        from experiments.pilot04_external_checker_runtime.public_guide_setup import _local_approval_attachments
        from tests.checkers.external.support import registry_spec, post_registry_spec

        entries = [SimpleNamespace(capability_id=spec.capability_id, capability_version=spec.capability_version,
            phase=spec.phase, registry_entry_id=new_record_id(), entry_digest='sha256:' + digit * 64)
            for spec, digit in ((registry_spec('pre_submit'), 'a'), (post_registry_spec(), 'b'))]
        repository = AsyncMock()
        repository.all_entries.return_value = entries
        repository.by_exact_id.side_effect = lambda key: next(entry for entry in entries if entry.registry_entry_id == key)
        with patch.object(registry, 'ExternalCheckerRegistryRepository', return_value=repository), \
                patch.object(registry, '_row_entry', side_effect=lambda row: row):
            result = asyncio.run(_local_approval_attachments(async_sessionmaker()))
            for entry in entries:
                self.assertEqual(result[entry.phase + '_attachments'], [{
                    'requirement_id': 'project.' + entry.phase,
                    'registry_entry_id': str(entry.registry_entry_id),
                    'registry_entry_digest': entry.entry_digest, 'configuration': {},
                }])
            repository.all_entries.return_value = entries[:1]
            with self.assertRaisesRegex(AssertionError, 'absent or ambiguous'):
                asyncio.run(_local_approval_attachments(async_sessionmaker()))
            repository.all_entries.return_value = entries + [entries[0]]
            with self.assertRaisesRegex(AssertionError, 'absent or ambiguous'):
                asyncio.run(_local_approval_attachments(async_sessionmaker()))

    def test_current_guide_refuses_zero_or_multiple_pre_before_setup(self):
        from experiments.pilot04_external_checker_runtime.public_guide_setup import public_guide_setup

        for count in (0, 2):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'exactly one PRE'):
                asyncio.run(public_guide_setup(None, None, True, None, None, pre_requirements=count))

    def test_source_failure_preserves_exact_charge_and_releases_only_task_pointer(self):
        from experiments.pilot04_external_checker_runtime import public_intake_trials as intake

        operation = SimpleNamespace(id='source', task_id='task', acceptance_receipt=None,
            finalized_submission_id=None, finalization_event_id=None, selected_pre_submit_run_id='run',
            failure_code='submission_infrastructure_unavailable')
        charge = SimpleNamespace(state='sealed', accounted_bytes=42)
        task = SimpleNamespace(status='in_progress', active_submission_operation_id=None)
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.get.side_effect = lambda model, key: charge if key == 'source' else task
        async def exercise():
            return await intake._assert_source_failure(lambda: session, 'task', 'key', 42, sealed=True,
                code='submission_infrastructure_unavailable')

        with patch.object(intake, '_wait_source_state', new=AsyncMock(return_value=operation)), \
                patch.object(intake, '_assert_no_submission_after_intake_failure', new=AsyncMock()) as no_product:
            self.assertIs(asyncio.run(exercise()), operation)
            no_product.assert_awaited_once_with(unittest.mock.ANY, 'task', 'run')
            for target, field, value in ((charge, 'accounted_bytes', 0), (charge, 'state', 'released'),
                    (task, 'active_submission_operation_id', 'foreign'), (task, 'status', 'ready'),
                    (operation, 'acceptance_receipt', {'accepted': True})):
                original = getattr(target, field)
                setattr(target, field, value)
                try:
                    with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                        asyncio.run(exercise())
                finally:
                    setattr(target, field, original)


class RunnerFaultBridgeContracts(unittest.TestCase):
    def profile(self, root):
        from experiments.pilot04_external_checker_runtime.public_runner_faults import RunnerFaultProfile
        key, known = root / 'identity', root / 'known-hosts'
        key.write_text('dummy-private-key-never-read')
        known.write_text('pinned-public-host-key-fixture')
        key.chmod(0o600)
        known.chmod(0o600)
        return RunnerFaultProfile('13.61.148.238', key, known, '/opt/workstream/reviewed-source',
            '/var/lib/workstream-operator/fault-run', str(uuid4()), 'sha256:' + 'a' * 64, 'sha256:' + 'b' * 64)

    def root(self, directory, profile):
        import time
        from experiments.pilot04_external_checker_runtime.public_fault_files import PrivateControlDirectory
        from experiments.pilot04_external_checker_runtime.public_node_faults import CONTROL_PROTOCOL
        control = PrivateControlDirectory(directory)
        control.write('supervisor-run.json', {'protocol_version': CONTROL_PROTOCOL,
            'run_id': profile.run_id, 'maximum_seconds': 30, 'deadline_monotonic': time.monotonic() + 30,
            'binding_sha256': profile.binding_sha256, 'image_digest': profile.image_digest})
        (directory / 'runtime-trace.jsonl').write_bytes(b'')
        (directory / 'runtime-trace.jsonl').chmod(0o600)
        (directory / 'supervisor-ready').write_text('ready')
        (directory / 'supervisor-ready').chmod(0o600)
        return control

    def response(self, profile, operation, **fields):
        if operation == 'snapshot':
            fields = {'cleanup': None} | fields
        from experiments.pilot04_external_checker_runtime.public_node_faults import CONTROL_PROTOCOL
        return {'protocol_version': CONTROL_PROTOCOL, 'run_id': profile.run_id,
                'operation': operation, 'binding_sha256': profile.binding_sha256,
                'image_digest': profile.image_digest, **fields}

    def test_pinned_ssh_uses_fixed_module_and_never_reads_identity_bytes(self):
        import shlex
        with tempfile.TemporaryDirectory() as temporary:
            profile = self.profile(Path(temporary))
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('must not read key')), \
                    patch.object(Path, 'read_text', side_effect=AssertionError('must not read key')):
                command = profile.command()
            self.assertEqual(command[:3], ['ssh', '-F', '/dev/null'])
            self.assertEqual(command[-2], 'ubuntu@13.61.148.238')
            for option in ('IdentitiesOnly=yes', 'IdentityAgent=none', 'BatchMode=yes',
                           'StrictHostKeyChecking=yes', 'GlobalKnownHostsFile=/dev/null', 'UpdateHostKeys=no',
                           'UserKnownHostsFile=' + str(profile.known_hosts_file)):
                self.assertIn(option, command)
            remote = shlex.split(command[-1])
            self.assertEqual(remote[-3:], ['--root', profile.control_root, '--request'])
            self.assertIn('experiments.pilot04_external_checker_runtime.public_node_faults', remote)
            profile.identity_file.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'ownership/mode'):
                profile.command()

    def test_runner_commands_have_stable_id_and_refuse_action_or_run_substitution(self):
        from experiments.pilot04_external_checker_runtime.public_node_faults import control_request
        async def exercise():
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                profile = self.profile(directory)
                control = self.root(directory, profile)
                request = self.response(profile, 'command', command_id='b' * 32, action='clear')
                async def respond():
                    while not (directory / ('b' * 32 + '.request')).exists():
                        await asyncio.sleep(.001)
                    self.assertEqual(control.read('b' * 32 + '.request'), {'action': 'clear'})
                    control.write('b' * 32 + '.response', {'action': 'clear', 'ok': True})
                try:
                    result, _ = await asyncio.gather(control_request(directory, request), respond())
                    self.assertEqual(result['state'], 'completed')
                    with patch('experiments.pilot04_external_checker_runtime.public_node_faults.node_command',
                               new=AsyncMock(side_effect=AssertionError('duplicate mutation'))):
                        self.assertEqual(await control_request(directory, request), result)
                    for change in ({'run_id': str(uuid4())}, {'binding_sha256': 'sha256:' + 'f' * 64},
                                   {'image_digest': 'sha256:' + 'f' * 64},
                                   {'action': 'project_kill'}, {'action': 'arbitrary'}):
                        with self.subTest(change=change), self.assertRaises(ValueError):
                            await control_request(directory, request | change)
                    with patch('experiments.pilot04_external_checker_runtime.public_node_faults.node_command',
                               new=AsyncMock(side_effect=AssertionError('custody checked after dispatch'))) as dispatch:
                        with self.assertRaisesRegex(ValueError, 'custody pin'):
                            await control_request(directory, request | {'command_id': 'f' * 32,
                                'binding_sha256': 'sha256:' + 'f' * 64})
                        dispatch.assert_not_awaited()
                    self.assertFalse((directory / ('f' * 32 + '.request')).exists())
                    before = {item.name for item in directory.iterdir()}
                    unknown = await control_request(directory, request | {'operation': 'query', 'command_id': 'c' * 32})
                    self.assertEqual((unknown['state'], unknown['result']), ('unknown', None))
                    self.assertEqual({item.name for item in directory.iterdir()}, before)
                finally:
                    control.close()
        asyncio.run(exercise())

    def test_snapshot_binds_run_and_rejects_aliased_or_incomplete_trace(self):
        from experiments.pilot04_external_checker_runtime.public_node_faults import control_request
        async def exercise():
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                profile = self.profile(directory)
                control = self.root(directory, profile)
                request = self.response(profile, 'snapshot')
                request.pop('cleanup')
                trace = directory / 'runtime-trace.jsonl'
                data = b'{"operation":"create","name":"owned"}\n'
                try:
                    trace.write_bytes(data)
                    result = await control_request(directory, request)
                    self.assertEqual(result['cursor'], 1)
                    self.assertEqual(result['events'], [{'operation': 'create', 'name': 'owned'}])
                    self.assertEqual(result['trace_sha256'], 'sha256:' + hashlib.sha256(data).hexdigest())
                    trace.write_bytes(data[:-1])
                    with self.assertRaisesRegex(ValueError, 'incomplete'):
                        await control_request(directory, request)
                    trace.write_bytes(data)
                    trace.chmod(0o644)
                    with self.assertRaisesRegex(ValueError, 'ownership/mode'):
                        await control_request(directory, request)
                    trace.chmod(0o600)
                    retained = directory / 'retained-trace'
                    trace.rename(retained)
                    trace.symlink_to(retained)
                    with self.assertRaises(OSError):
                        await control_request(directory, request)
                finally:
                    control.close()
        asyncio.run(exercise())

    def test_trace_snapshot_refuses_held_writer_lock_without_waiting(self):
        import fcntl
        code = """import sys
from pathlib import Path
from experiments.pilot04_external_checker_runtime.public_fault_files import PrivateControlDirectory
control = PrivateControlDirectory(Path(sys.argv[1]))
try:
    try:
        control.trace_bytes()
    except BlockingIOError:
        print('unavailable')
    else:
        print('available')
finally:
    control.close()
"""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            trace = directory / 'runtime-trace.jsonl'
            trace.write_bytes(b'{}\n')
            trace.chmod(0o600)
            def read():
                try:
                    result = subprocess.run([sys.executable, '-c', code, str(directory)],
                        capture_output=True, text=True, timeout=5, check=True, cwd=ROOT)
                except subprocess.TimeoutExpired:
                    self.fail('trace snapshot blocked behind the held writer lock')
                return result.stdout.strip()
            self.assertEqual(read(), 'available')
            with trace.open('a') as writer:
                fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(read(), 'unavailable')
            self.assertEqual(read(), 'available')

    def test_ssh_lost_ack_is_observed_by_same_id_without_repeating_mutation(self):
        from experiments.pilot04_external_checker_runtime.public_runner_faults import RunnerFaults, FaultOutcomeUnknown
        async def exercise():
            with tempfile.TemporaryDirectory() as temporary:
                profile = self.profile(Path(temporary))
                client = RunnerFaults(profile)
                identifier = 'd' * 32
                response = self.response(profile, 'query', command_id=identifier, action='clear',
                    state='completed', result={'action': 'clear', 'ok': True})
                written = []
                def process(body, *, lost=False):
                    output, errors = asyncio.StreamReader(), asyncio.StreamReader()
                    output.feed_data(json.dumps(body).encode())
                    output.feed_eof()
                    errors.feed_eof()
                    if lost:
                        output.read = AsyncMock(side_effect=TimeoutError('lost ACK after input'))
                    return SimpleNamespace(stdin=SimpleNamespace(write=lambda data: written.append(json.loads(data)),
                        drain=AsyncMock(), close=lambda: None), stdout=output, stderr=errors,
                        returncode=None if lost else 0, wait=AsyncMock(return_value=0),
                        kill=unittest.mock.Mock(side_effect=ProcessLookupError()) if lost else unittest.mock.Mock())
                with patch('asyncio.create_subprocess_exec', new=AsyncMock(side_effect=[process({}, lost=True), process(response)])) as execute:
                    with self.assertRaises(FaultOutcomeUnknown) as unknown:
                        await client.command('clear', command_id=identifier)
                    self.assertEqual(unknown.exception.command_id, identifier)
                    observed = await client.query(identifier, 'clear')
                    self.assertEqual(observed['state'], 'completed')
                    self.assertEqual(execute.await_count, 2)
                self.assertEqual([item['operation'] for item in written], ['command', 'query'])
                for change in ({'run_id': str(uuid4())}, {'binding_sha256': 'sha256:' + 'f' * 64}):
                    with patch('asyncio.create_subprocess_exec', new=AsyncMock(return_value=process(response | change))):
                        with self.assertRaisesRegex(RuntimeError, 'observation unavailable'):
                            await client.query(identifier, 'clear')
                self.assertEqual(sum(item['operation'] == 'command' for item in written), 1)
                self.assertTrue(all(item['command_id'] == identifier for item in written))
        asyncio.run(exercise())

    def test_remote_snapshot_cannot_rewind_or_rebind_existing_prefix(self):
        from experiments.pilot04_external_checker_runtime.public_runner_faults import RunnerFaults
        async def exercise():
            with tempfile.TemporaryDirectory() as temporary:
                profile = self.profile(Path(temporary))
                client = RunnerFaults(profile)
                first = self.response(profile, 'snapshot', events=[{'name': 'exact'}], cursor=1,
                                      trace_sha256='sha256:' + 'b' * 64)
                with patch.object(client, '_exchange', new=AsyncMock(return_value=first)):
                    await client.snapshot()
                for changed in (dict(first, events=[], cursor=0),
                        dict(first, events=[{'name': 'foreign'}]), dict(first, trace_sha256='sha256:' + 'c' * 64)):
                    with self.subTest(changed=changed), patch.object(client, '_exchange', new=AsyncMock(return_value=changed)):
                        with self.assertRaisesRegex(RuntimeError, 'trace changed'):
                            await client.snapshot()
        asyncio.run(exercise())

    def test_same_run_cleanup_receipt_requires_exact_absence_and_foreign_cleanup(self):
        from experiments.pilot04_external_checker_runtime.public_runner_faults import RunnerFaults
        async def exercise():
            with tempfile.TemporaryDirectory() as temporary:
                profile = self.profile(Path(temporary))
                client = RunnerFaults(profile)
                cleanup = self.response(profile, 'snapshot')
                cleanup.pop('operation')
                cleanup.pop('cleanup')
                cleanup.update(config_sha256='sha256:' + 'c' * 64,
                    resources={'disks': [], 'leases': [], 'machines': [], 'cgroups': []},
                    foreign={'name': 'exact-foreign', 'machine_absent': True, 'disk_absent': True,
                             'cgroup_absent': True, 'process_reaped': True})
                reply = self.response(profile, 'snapshot', events=[], cursor=0,
                                      trace_sha256='sha256:' + 'd' * 64, cleanup=cleanup)
                with patch.object(client, '_exchange', new=AsyncMock(return_value=reply)):
                    self.assertEqual((await client.snapshot())['cleanup'], cleanup)
                for change in ({'run_id': str(uuid4())}, {'image_digest': 'sha256:' + 'f' * 64},
                        {'resources': dict(cleanup['resources'], leases=None)},
                        {'resources': dict(cleanup['resources'], machines=['owned-remains'])},
                        {'foreign': dict(cleanup['foreign'], process_reaped=False)}):
                    invalid = reply | {'cleanup': cleanup | change}
                    with self.subTest(change=change), patch.object(client, '_exchange', new=AsyncMock(return_value=invalid)):
                        with self.assertRaisesRegex(RuntimeError, 'cleanup is incomplete'):
                            await client.snapshot()
        asyncio.run(exercise())

    def test_mismatched_pre_pin_refuses_before_fault_setup(self):
        from experiments.pilot04_external_checker_runtime import public_node_faults as owner
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = directory / 'node.json'
            original = json.dumps({'smol': {'binary_sha256': 'sha256:' + 'a' * 64},
                'pre': {'smol_binary_sha256': 'sha256:' + 'b' * 64},
                'cache': [{'platform_manifest_digest': 'sha256:' + 'c' * 64}]}).encode()
            config.write_bytes(original)
            control_root = directory / 'control'
            with patch.object(owner, 'validate_node', return_value={'verified': True}), \
                    patch.object(owner, 'owned_resources') as resources, \
                    patch.object(owner, 'ForeignControl') as foreign:
                with self.assertRaisesRegex(ValueError, 'pins differ before fault setup'):
                    owner.serve(config, control_root, 'owned-unit', directory / 'manifest',
                                run_id=str(uuid4()), maximum_seconds=1,
                                image_digest='sha256:' + 'c' * 64)
            self.assertFalse(control_root.exists())
            self.assertEqual(config.read_bytes(), original)
            resources.assert_not_called()
            foreign.assert_not_called()

    def test_finite_supervisor_and_hup_restore_only_owned_config(self):
        from experiments.pilot04_external_checker_runtime import public_node_faults as owner
        import signal
        for hup in (False, True):
            with self.subTest(hup=hup), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                config = root / 'node.json'
                original = json.dumps({'socket_path': '/unused/native.sock', 'smol': {'binary': '/unused/smol', 'binary_sha256': 'sha256:' + 'a' * 64},
                    'cache': [{'repository': 'independent-real-registry', 'platform_manifest_digest': 'sha256:' + 'b' * 64, 'smol': {'archive': '/unused/image'}}]}).encode()
                config.write_bytes(original)
                config.chmod(0o600)
                states, handlers, clock = [], {}, [0.0]
                def monotonic():
                    clock[0] += .1
                    return clock[0]
                def sleep(_seconds):
                    if hup:
                        handlers[signal.SIGHUP](signal.SIGHUP, None)
                class Foreign:
                    created = False
                    process = None
                    def __init__(self, *args, **kwargs):
                        pass
                    def start(self):
                        self.created, self.process = True, object()
                        states.append('foreign_started')
                        self.check()
                    def check(self):
                        states.append('foreign_preserved')
                    def close(self):
                        self_test.assertEqual(handlers[signal.SIGTERM], signal.SIG_IGN)
                        self_test.assertEqual(handlers[signal.SIGHUP], signal.SIG_IGN)
                        states.append('foreign_removed')
                        return {'name': 'foreign-fixture', 'machine_absent': True, 'disk_absent': True,
                                'cgroup_absent': True, 'process_reaped': True}
                self_test = self
                control_root = root / 'control'
                with patch.object(owner, 'validate_node', return_value={'verified': True}), \
                        patch.object(owner, 'owned_resources', return_value={'machines': [], 'disks': [], 'leases': [], 'cgroups': []}), \
                        patch.object(owner, 'ForeignControl', Foreign), \
                        patch.object(owner.subprocess, 'run') as restart, \
                        patch.object(owner.time, 'monotonic', side_effect=monotonic), \
                        patch.object(owner.time, 'sleep', side_effect=sleep), \
                        patch.object(owner.signal, 'getsignal', return_value=signal.SIG_DFL), \
                        patch.object(owner.signal, 'signal', side_effect=lambda item, handler: handlers.update({item: handler})):
                    owner.serve(config, control_root, 'owned-unit', root / 'not-read-manifest',
                                run_id=str(uuid4()), maximum_seconds=1, image_digest='sha256:' + 'b' * 64)
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(restart.call_count, 2)
                self.assertTrue(all(call.args[0] == ['sudo', 'systemctl', 'restart', 'owned-unit']
                                    for call in restart.call_args_list))
                receipt = json.loads((control_root / 'supervisor-cleanup.json').read_text())
                self.assertEqual(receipt['config_sha256'], 'sha256:' + hashlib.sha256(original).hexdigest())
                self.assertTrue(receipt['foreign']['machine_absent'])
                self.assertEqual(receipt['image_digest'], 'sha256:' + 'b' * 64)
                self.assertEqual(receipt['protocol_version'], owner.CONTROL_PROTOCOL)
                self.assertFalse((control_root / 'supervisor-ready').exists())
                self.assertEqual(states, ['foreign_started', 'foreign_preserved', 'foreign_preserved', 'foreign_removed'])
                self.assertEqual(handlers[signal.SIGTERM], signal.SIG_DFL)
                self.assertEqual(handlers[signal.SIGHUP], signal.SIG_DFL)

    def test_hosted_config_root_parent_keeps_file_and_control_custody(self):
        import os
        import stat
        from experiments.pilot04_external_checker_runtime import public_node_faults as owner
        from experiments.pilot04_external_checker_runtime.public_fault_files import PrivateControlDirectory
        config = Path('/etc/workstream/checker-service.json')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'actual-fd'
            source.write_bytes(b'{"owned":true}')
            actual = source.stat()
            def info(mode, uid, gid, links=1):
                return os.stat_result((mode, actual.st_ino, actual.st_dev, links, uid, gid,
                                       actual.st_size, 0, 0, 0))
            baseline = {path: info(stat.S_IFDIR | 0o755, 0, 0) for path in config.parents}
            baseline[config] = info(stat.S_IFREG | 0o400, 10001, 10001)
            observed = dict(baseline)
            original_open, opened, resolved = os.open, source, config
            def read():
                with patch.object(owner.os, 'getuid', return_value=0), \
                        patch.object(Path, 'lstat', side_effect=lambda path: observed[path], autospec=True), \
                        patch.object(Path, 'resolve', autospec=True, side_effect=lambda path: resolved), \
                        patch.object(owner.os, 'open', side_effect=lambda *args: original_open(opened, os.O_RDONLY)):
                    return owner._read_config(config, True)
            self.assertEqual(read(), (b'{"owned":true}', (actual.st_dev, actual.st_ino)))
            observed[config.parent] = info(stat.S_IFDIR | 0o700, 10001, 10001)
            self.assertEqual(read()[0], b'{"owned":true}')
            observed = dict(baseline)
            changes = [(config.parent, info(stat.S_IFDIR | mode, 0, 0)) for mode in (0o775, 0o777, 0o1777)]
            changes += [(config.parent, info(stat.S_IFDIR | 0o755, uid, 0)) for uid in (1000, 10001)]
            changes += [(Path('/etc'), info(stat.S_IFDIR | 0o755, 10001, 0)),
                        (config, info(stat.S_IFREG | 0o600, 10001, 10001)),
                        (config, info(stat.S_IFREG | 0o400, 0, 10001)),
                        (config, info(stat.S_IFREG | 0o400, 10001, 0)),
                        (config, info(stat.S_IFREG | 0o400, 10001, 10001, 2)),
                        (config, info(stat.S_IFLNK | 0o400, 10001, 10001))]
            for path, value in changes:
                observed = dict(baseline) | {path: value}
                with self.subTest(path=path, mode=value.st_mode), self.assertRaises(ValueError):
                    read()
            observed, resolved = dict(baseline), source
            with self.assertRaisesRegex(ValueError, 'canonical'):
                read()
            resolved, opened = config, Path(directory) / 'other-fd'
            opened.write_bytes(b'foreign inode')
            with self.assertRaisesRegex(ValueError, 'identity/size'):
                read()
            with patch.object(Path, 'lstat', side_effect=lambda path: baseline[path], autospec=True), \
                    patch.object(Path, 'resolve', autospec=True, side_effect=lambda path: path):
                with self.assertRaises(ValueError):
                    PrivateControlDirectory(config.parent, uid=0, gid=0)

    def test_bounded_ssh_reader_refuses_oversized_output(self):
        from experiments.pilot04_external_checker_runtime.public_runner_faults import _bounded_read
        async def exercise():
            stream = asyncio.StreamReader()
            stream.feed_data(b'1234')
            stream.feed_eof()
            self.assertEqual(await _bounded_read(stream, 4), b'1234')
            stream = asyncio.StreamReader()
            stream.feed_data(b'12345')
            stream.feed_eof()
            with self.assertRaisesRegex(ValueError, 'output exceeds'):
                await _bounded_read(stream, 4)
        asyncio.run(exercise())


class RemotePreLaunchContracts(unittest.TestCase):
    def exercise(self, *, omit_delete=False, replay_allocates=False, wrong_image=False,
                 unknown=False, missing_create=False, wrong_source=False,
                 wrong_replay_field=False, bad_replay_correlation=False,
                 first_response_path=None):
        from experiments.pilot04_external_checker_runtime import public_runtime_trials as runtime
        from experiments.pilot04_external_checker_runtime.public_runner_faults import FaultOutcomeUnknown

        image = 'sha256:' + 'b' * 64
        def events(name, operations):
            lease = {'name': name, 'epoch': 'epoch', 'expires_ms': 100, 'lifetime_ms': 10}
            return [{'operation': operation, 'name': name, 'project': True, 'lease': lease}
                    for operation in operations]
        failed = ([] if missing_create else events('failed-vm',
                  ['create', 'start'] + ([] if omit_delete else ['delete'])))
        replay = failed + (events('unexpected', ['create']) if replay_allocates else [])
        recovered = replay + events('recovered-vm', ['create', 'start', 'exec', 'delete'])
        traces = [{'cursor': len(records), 'events': records}
                  for records in ([], failed, replay, recovered)]
        cleanup = {'result': {'foreign_preserved': 'foreign-vm',
                             'resources': {name: [] for name in ('disks', 'leases', 'machines', 'cgroups')}}}
        commands, worker_events = [], []
        async def resume():
            worker_events.append('start')
        class Runner:
            profile = SimpleNamespace(image_digest=image, run_id='run')
            async def command(self, action):
                commands.append(action)
                if unknown:
                    raise FaultOutcomeUnknown('c' * 32)
                return cleanup if action == 'drained' else {'command_id': 'c' * 32}
            async def snapshot(self):
                return traces.pop(0)
        registry = {'image_digest': 'sha256:' + 'a' * 64 if wrong_image else image}
        source_id = 'foreign-operation' if wrong_source else 'failed-operation'
        request = {'policy': {'entries': [{'registry': registry}]},
                   'source': {'location': {'operation_id': source_id}}}
        failed_row = SimpleNamespace(id='failed-pre', terminal_digest='digest', request_json=request,
            task_id='task', source_operation_id='failed-operation',
            status='infrastructure_failed', terminal_json={'execution': None,
                'infrastructure_failure_code': 'implementation_unavailable',
                'reservation': {'source': {'location': {'operation_id': 'failed-operation'}}}})
        fresh_row = SimpleNamespace(id='fresh-pre', source_operation_id='fresh-operation', request_json=request,
            status='completed', terminal_digest='fresh-digest', terminal_json={'execution': {
                'eligible': True, 'required_external_count': 1,
                'workstream_default': {'eligible': True}, 'external_members': []}})
        operation = SimpleNamespace(id='failed-operation', selected_pre_submit_run_id=None)
        failure = {'error': {'code': 'submission_infrastructure_unavailable',
            'message': 'submission_infrastructure_unavailable', 'details': {},
            'correlation_id': str(uuid4()), 'retryable': True}}
        replay_error = {'error': failure['error'] | {
            'correlation_id': 'invalid' if bad_replay_correlation else str(uuid4()),
            'message': 'changed' if wrong_replay_field else failure['error']['message'],
        }}
        receipt = {'operation_id': 'fresh-operation', 'status': 'accepted', 'replayed': False}
        source = AsyncMock(side_effect=[failure, replay_error, receipt])
        accepted = AsyncMock(return_value={'submission_id': 'submission'})
        with patch.object(runtime, '_trial_operation_ids', new=AsyncMock(side_effect=[set(),
                {'failed-operation'}, {'failed-operation'}, {'failed-operation', 'fresh-operation'}])), \
                patch.object(runtime, '_source_request', new=source), \
                patch.object(runtime, '_selected', new=AsyncMock(side_effect=[failed_row, failed_row, fresh_row])), \
                patch.object(runtime, '_assert_source_failure', new=AsyncMock(return_value=operation)) as failed_custody, \
                patch.object(runtime, '_assert_current_pre') as current_pre, \
                patch.object(runtime, '_observe_accepted_source', new=accepted):
            try:
                result = asyncio.run(runtime.public_pre_launch_failure(None, None, task='task', assignment='assignment',
                    token='private-token', archive=b'actual-zip', runner=Runner(),
                    stop_worker=lambda: worker_events.append('stop'), start_worker=resume,
                    first_response_path=first_response_path))
            finally:
                self.assertEqual(worker_events, ['stop', 'start'])
        self.assertEqual([call.args[-1] for call in source.await_args_list], [503, 503, 202])
        self.assertEqual(source.await_args_list[0].args[4], source.await_args_list[1].args[4])
        self.assertNotEqual(source.await_args_list[0].args[4], source.await_args_list[2].args[4])
        self.assertEqual(failed_custody.await_args.kwargs, {'sealed': True, 'code': 'submission_infrastructure_unavailable'})
        self.assertEqual(current_pre.call_args.args, (fresh_row,))
        self.assertEqual(accepted.await_args.args[2:7], ('task', 'assignment', 'private-token', b'actual-zip',
                                                      source.await_args_list[2].args[4]))
        self.assertEqual(commands, ['project_fail_once', 'drained', 'clear', 'drained'])
        self.assertEqual(result['failed_operation_id'], 'failed-operation')
        self.assertEqual(result['recovered_submission'], {'submission_id': 'submission'})
        return result

    def test_remote_first_pre_preserves_known_failure_replay_and_real_t5_observer(self):
        self.exercise()
        for fault, message in (('omit_delete', 'lacks deletion'),
                ('replay_allocates', 'same-key replay allocated a native machine'),
                ('wrong_image', 'failed PRE lost exact selected image'),
                ('wrong_source', 'changed its exact PRE'),
                ('wrong_replay_field', 'same-key public failure fields changed'),
                ('bad_replay_correlation', 'same-key public failure fields changed')):
            with self.subTest(fault=fault), self.assertRaisesRegex(RuntimeError, message):
                self.exercise(**{fault: True})

    def test_first_response_is_retained_before_native_count_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'first-response.json'
            with self.assertRaisesRegex(RuntimeError, 'expected fresh machines'):
                self.exercise(missing_create=True, first_response_path=path)
            body = json.loads(path.read_text())
            self.assertEqual(body['public_failure']['error']['code'],
                             'submission_infrastructure_unavailable')
            self.assertEqual(body['selected_pre']['status'], 'infrastructure_failed')
            self.assertEqual(body['selected_pre']['terminal']['infrastructure_failure_code'],
                             'implementation_unavailable')
            self.assertEqual(body['runtime_event_count'], 0)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_fresh_pre_selection_is_retained_before_recovery_assertions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'first-response.json'
            self.exercise(first_response_path=path)
            fresh = path.with_name('remote-pre-launch-fresh-pre.json')
            body = json.loads(fresh.read_text())
            self.assertEqual(body['receipt']['operation_id'], 'fresh-operation')
            self.assertEqual(body['selected']['source_operation_id'], 'fresh-operation')
            self.assertTrue(body['execution']['eligible'])
            self.assertEqual(fresh.stat().st_mode & 0o777, 0o600)

    def test_partial_owned_worker_pause_failure_still_restores_worker(self):
        from experiments.pilot04_external_checker_runtime import public_runtime_trials as runtime
        def failed_pause():
            raise RuntimeError('owned pause failed')
        resume = AsyncMock()
        with patch.object(runtime, '_remote_pre_launch_failure', new=AsyncMock()) as vector:
            with self.assertRaisesRegex(RuntimeError, 'owned pause failed'):
                asyncio.run(runtime.public_pre_launch_failure(None, None, task='task', assignment='assignment',
                    token='private-token', archive=b'actual-zip', runner=None,
                    stop_worker=failed_pause, start_worker=resume))
        resume.assert_awaited_once_with()
        vector.assert_not_awaited()

    def test_unknown_fault_command_stops_before_any_public_submission(self):
        from experiments.pilot04_external_checker_runtime.public_runner_faults import FaultOutcomeUnknown
        with self.assertRaises(FaultOutcomeUnknown) as error:
            self.exercise(unknown=True)
        self.assertEqual(error.exception.command_id, 'c' * 32)


if __name__ == '__main__':
    unittest.main()
