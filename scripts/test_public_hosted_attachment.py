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
        from experiments.pilot04_external_checker_runtime.run_selected_end_to_end_probe import _locked_spec

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
        for count in (0, 1, 2):
            selected = attachment.approval_attachments(count)
            self.assertEqual(len(selected['pre_submit_attachments']), count)
            self.assertEqual(len(selected['post_submit_attachments']), 1)
            for phase, entries in (('pre_submit', selected['pre_submit_attachments']),
                                   ('post_submit', selected['post_submit_attachments'])):
                published = attachment.registered_images[phase]
                for entry in entries:
                    self.assertEqual(entry['registry_entry_id'], str(published.registry_entry_id))
                    self.assertEqual(entry['registry_entry_digest'], published.entry_digest)
                    self.assertEqual(entry['configuration'], {})
            self.assertEqual([item['requirement_id'] for item in selected['pre_submit_attachments']],
                             ['project.pre_submit.01', 'project.pre_submit.02'] if count == 2 else
                             (['project.pre_submit'] if count == 1 else []))
            self.assertEqual(selected['post_submit_attachments'][0]['requirement_id'], 'project.post_submit')

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

    def test_stalled_upload_refuses_early_cleanup_or_reset_deadline(self):
        import time
        from experiments.pilot04_external_checker_runtime import public_intake_trials as intake

        class StreamingClient:
            async def post(self, route, *, headers, content):
                async for _ in content:
                    pass
                raise AssertionError('invalid expiry should fail before completing request')

        expires = time.time_ns() // 1_000_000 + 1000
        prepared = {'operation': 'prepare_completed', 'name': 'exact-intake', 'project': False,
                    'lease': {'epoch': 'original', 'expires_ms': expires}}
        for deletion in (
            {'wall_ms': expires - 1, 'lease': prepared['lease']},
            {'wall_ms': expires + 1, 'lease': {'epoch': 'original', 'expires_ms': expires + 1000}},
            {'wall_ms': expires + 1, 'lease': {'epoch': 'restarted', 'expires_ms': expires}},
        ):
            with self.subTest(deletion=deletion), patch.object(intake, 'trace_events', return_value=[]), \
                    patch.object(intake, '_native_event', new=AsyncMock(side_effect=[prepared, deletion])), \
                    patch.object(intake, 'node_command', new=AsyncMock()) as cleanup:
                with self.assertRaisesRegex(RuntimeError, 'original lease expiry'):
                    asyncio.run(intake._expire_upload(StreamingClient(), None, '/public', {}, 'token', b'zip',
                                                     'task', Path('/owned/control')))
                cleanup.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
