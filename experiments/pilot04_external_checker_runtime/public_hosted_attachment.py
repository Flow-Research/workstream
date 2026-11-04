"""Attach the public runtime fixture to an already running hosted deployment.

This module never launches an API, worker, Beat, issuer or model provider. The
RS256 issuer is an explicitly simulated identity fixture. Manager-authored guide
rules prove runtime wiring, not a setup-agent rehearsal or a real pilot project.

Invoke the existing run_public_journey_probe module with --hosted-attachment,
--database-url and --broker-url. The private JSON attachment names origin,
release_env, identity_directory, node_root, fixture_ca_sha256 and capabilities
({pre_submit,post_submit}, each with capability_id/capability_version). These
identities name the baseline registry publications; they are not guide setup
inputs. The manager selects the exact published images at policy approval.
The fixture-only derived release images must already contain the public CA
appended to their ordinary certifi bundle and pass the canonical image verifier.

The driver environment supplies the same isolated database/broker settings for
the established bootstrap/lifecycle setup tools and duplicate broker delivery.
It does not replace any running service's environment. Original-lease expiry
uses WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS (default 3400s),
including the real wait. Existing Settings require ZIP inspection < preparation
and preparation + cleanup margin < scratch TTL; AWS operation/complete-read and
terminal persistence bounds remain independently enforced by hosted preflight.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import partial
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _command(arguments, *, timeout=30, environment=None, combined=False):
    """Keep secret-bearing child output out of exception diagnostics."""
    result = subprocess.run(arguments, capture_output=True, timeout=timeout,
                            env=environment, check=False, cwd=ROOT)
    require(result.returncode == 0, "hosted proof management command failed")
    output = result.stdout + result.stderr if combined else result.stdout
    require(len(output) <= 4 * 1024 * 1024, "hosted proof command output exceeded bound")
    return output


def deliver_duplicate(task, hostname, event_id, project_id):
    """Observe one real broker delivery without changing production logging."""
    from kombu import Consumer

    identifier = str(uuid4())
    ready = False
    received = False
    completed = False

    def observe(event):
        nonlocal ready, received, completed
        if event['type'] == 'worker-heartbeat' and event.get('hostname') == hostname:
            ready = True
            return
        if event.get('uuid') != identifier or event['type'] not in {
            'task-received', 'task-succeeded', 'task-failed', 'task-rejected',
            'task-revoked', 'task-retried',
        }:
            return
        require(event.get('hostname') == hostname, 'duplicate ran on another worker')
        if event['type'] == 'task-received':
            require(event.get('name') == task.name, 'duplicate task name differs')
            received = True
        elif event['type'] == 'task-succeeded':
            require(received and event.get('result') == "{'status': 'delivery_unavailable'}",
                    'duplicate terminal result differs')
            completed = True
        elif event['type'] in {'task-failed', 'task-rejected', 'task-revoked', 'task-retried'}:
            raise RuntimeError('duplicate task did not succeed')

    def control(command):
        replies = task.app.control.broadcast(command, destination=[hostname], reply=True,
                                            timeout=5, connection=control_connection)
        require(len(replies) == 1 and set(replies[0]) == {hostname},
                'owned worker event-control acknowledgement differs')
        return replies[0][hostname]

    restore = False
    options = {'connect_timeout': 5, 'transport_options': {
        'max_retries': 0, 'socket_connect_timeout': 5, 'socket_timeout': 5,
        'retry_on_timeout': False,
    }}
    # Redis's event subscription and control replies use distinct consumers.
    # Sharing their connection can lose the restoration acknowledgement.
    with task.app.connection_for_read(**options) as connection, \
            task.app.connection_for_write(**options) as control_connection:
        connection.ensure_connection(max_retries=0, timeout=5)
        control_connection.ensure_connection(max_retries=0, timeout=5)
        receiver = task.app.events.Receiver(
            connection, handlers={'*': observe}, node_id='ws-proof-' + identifier,
            routing_key='#', queue_ttl=30, queue_expires=180,
            queue_exclusive=True, queue_durable=False, accept={'json'},
        )
        try:
            # Redis installs its fanout subscription on the first drain, not
            # basic_consume. A real heartbeat proves this queue is listening.
            with receiver.get_consumers(partial(Consumer, receiver.channel), receiver.channel)[0]:
                deadline = time.monotonic() + 15
                while not ready:
                    require(time.monotonic() < deadline, 'owned worker event subscription is not ready')
                    try:
                        connection.drain_events(timeout=max(.01, min(1, deadline - time.monotonic())))
                    except socket.timeout:
                        pass
                reply = control('enable_events')
                require(reply in ({'ok': 'task events enabled'}, {'ok': 'task events already enabled'}),
                        'owned worker did not enable task events')
                restore = reply == {'ok': 'task events enabled'}
                task.apply_async(args=(str(event_id), str(project_id)), task_id=identifier,
                                 ignore_result=True, retry=False,
                                 producer=task.app.amqp.Producer(control_connection))
                deadline = time.monotonic() + 120
                while not completed:
                    require(time.monotonic() < deadline, 'exact duplicate completion was not observed')
                    try:
                        connection.drain_events(timeout=max(.01, min(1, deadline - time.monotonic())))
                    except socket.timeout:
                        pass
        finally:
            try:
                if restore:
                    require(control('disable_events') == {'ok': 'task events disabled'},
                            'owned worker task events were not restored')
            finally:
                receiver.queue(connection.default_channel).delete(if_unused=False, if_empty=False)
    return {'task_id': identifier, 'result': {'status': 'delivery_unavailable'}}


def validate_container(service, rendered, container, image, secrets, networks):
    """Compare actual container custody with the validated production render."""
    actual = container['Config']
    host = container['HostConfig']
    require(container['State']['Running'] and container['State'].get('Health', {}).get('Status') == 'healthy',
            "hosted service is not healthy: " + service)
    require(actual['Image'] == rendered['image'] and container['Image'] == image['Id'],
            "hosted service image differs: " + service)
    require(actual['Cmd'] == rendered['command']
            and actual['Entrypoint'] == image['Config']['Entrypoint']
            and actual['User'] == rendered['user'], "hosted service executable differs: " + service)
    require(host['ReadonlyRootfs'] is True
            and host['Privileged'] is False
            and set(host.get('CapDrop') or []) == {'ALL'}
            and {item.removeprefix('CAP_') for item in host.get('CapAdd') or []}
            == set(rendered.get('cap_add') or [])
            and 'no-new-privileges:true' in (host.get('SecurityOpt') or []),
            "hosted service isolation differs: " + service)
    environment = dict(item.split('=', 1) for item in actual['Env'])
    expected = {key: str(value) for key, value in rendered['environment'].items()}
    require(all(environment.get(key) == value for key, value in expected.items()),
            "hosted service environment differs: " + service)
    image_environment = dict(item.split('=', 1) for item in image['Config'].get('Env', []))
    require(environment == image_environment | expected, "hosted service has extra environment: " + service)
    require(not environment.get('WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET')
            and environment.get('WORKSTREAM_CELERY_TASK_ALWAYS_EAGER', 'false') == 'false'
            and not any(key.startswith('WORKSTREAM_PROBE_') for key in environment),
            "hosted service contains local proof substitution")
    expected_mounts = {(item['source'], item['target'], not item.get('read_only', False))
                       for item in rendered.get('volumes', []) if item['type'] == 'bind'}
    for item in rendered.get('secrets', []):
        expected_mounts.add((secrets[item['source']]['file'], '/run/secrets/' + item['target'], False))
    mounts = {(item['Source'], item['Destination'], item['RW'])
              for item in container['Mounts'] if item['Type'] == 'bind'}
    require(mounts == expected_mounts
            and all(item['Type'] in {'bind', 'tmpfs'} for item in container['Mounts']),
            "hosted service mounts differ: " + service)
    expected_tmpfs = {}
    for specification in rendered.get('tmpfs', []):
        target, separator, options = specification.partition(':')
        require(separator and target not in expected_tmpfs,
                'rendered tmpfs is ambiguous: ' + service)
        expected_tmpfs[target] = set(options.split(','))
    actual_tmpfs = {target: set(options.split(','))
                    for target, options in (host.get('Tmpfs') or {}).items()}
    # Docker reports configured tmpfs mounts in HostConfig.Tmpfs, usually omitting
    # them from Mounts. If it also lists one there, it must name the same target.
    require(actual_tmpfs == expected_tmpfs
            and all(item['Destination'] in expected_tmpfs
                    and item['RW'] == ('ro' not in expected_tmpfs[item['Destination']])
                    for item in container['Mounts'] if item['Type'] == 'tmpfs'),
            'hosted service tmpfs differs: ' + service)
    if rendered.get('network_mode') == 'none':
        require(host.get('NetworkMode') == 'none', 'hosted service network mode differs: ' + service)
        expected_networks = {'none'}
    else:
        expected_networks = {networks[name]['name'] for name in rendered['networks']}
    require(set(container['NetworkSettings']['Networks']) == expected_networks,
            'hosted service networks differ: ' + service)
    for setting, field_name, multiplier in (
        ('mem_limit', 'Memory', 1), ('memswap_limit', 'MemorySwap', 1),
        ('pids_limit', 'PidsLimit', 1), ('cpus', 'NanoCpus', 1_000_000_000),
    ):
        if setting in rendered:
            require(host.get(field_name) == int(float(rendered[setting]) * multiplier),
                    'hosted service resource limit differs: ' + service)
    expected_ports = {}
    for port in rendered.get('ports', []):
        key = str(port['target']) + '/' + port.get('protocol', 'tcp')
        expected_ports.setdefault(key, []).append({'HostIp': port.get('host_ip', ''),
                                                  'HostPort': str(port['published'])})
    require((host.get('PortBindings') or {}) == expected_ports,
            'hosted service published ports differ: ' + service)


@dataclass
class HostedAttachment:
    origin: str
    release_env: Path
    identity_directory: Path
    node_root: Path
    capabilities: dict
    fixture_ca_sha256: str
    actors: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)
    custody: dict = field(default_factory=dict)
    docker_environment: dict = field(default_factory=dict)
    native_binding: dict = field(default_factory=dict)
    registered_images: dict = field(default_factory=dict)
    model_post: object | None = None

    @classmethod
    def read(cls, path):
        from experiments.hosted_drill_identity.fixture import read_private

        value = json.loads(read_private(path))
        require(set(value) == {'origin', 'release_env', 'identity_directory', 'node_root',
                               'capabilities', 'fixture_ca_sha256'}, "hosted attachment fields differ")
        origin = urlparse(value['origin'])
        require(origin.scheme == 'http' and origin.hostname in {'127.0.0.1', 'localhost'}
                and origin.port and not origin.username and not origin.password
                and origin.path == '' and not origin.query and not origin.fragment,
                "hosted proof must attach to its loopback published API")
        for key in ('release_env', 'identity_directory', 'node_root'):
            path_value = Path(value[key])
            require(path_value.is_absolute() and path_value.resolve() == path_value,
                    "hosted attachment path must be canonical")
            value[key] = path_value
        require(set(value['capabilities']) == {'pre_submit', 'post_submit'}, "hosted capability stages differ")
        for stage, capability in value['capabilities'].items():
            require(set(capability) == {'capability_id', 'capability_version'}
                    and all(isinstance(item, str) and item for item in capability.values()),
                    "hosted capability identity is incomplete: " + stage)
        return cls(**value)

    def inspect(self):
        """Reuse hosted validation; inspect exact running services, never replace them."""
        from experiments.hosted_drill_identity.fixture import ISSUER, AUDIENCE, read_private
        from experiments.pilot04_external_checker_runtime.public_node_faults import runtime_control_root

        name = '_public_hosted_preflight'
        spec = importlib.util.spec_from_file_location(name, ROOT / 'deploy/hosted/preflight.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        values = module.parse_environment(self.release_env)
        module.validate_environment(values)
        rendered = module.render_compose(self.release_env, values)
        module.validate_compose(rendered, values)
        config = module.load_checker_config(Path(values['WORKSTREAM_CHECKER_CONFIG_FILE']))
        module.validate_checker_config(config, values)
        module.validate_private_host_inputs(values)
        module.validate_smol_runtime(config, values)
        module.validate_trusted_intake(values)
        require(values['WORKSTREAM_PROJECT_AGENT_RUNTIME'] == 'manager_authored',
                "hosted runtime fixture requires explicit manager-authored rules")
        require(values['WORKSTREAM_TOKEN_ISSUER'] == ISSUER
                and values['WORKSTREAM_TOKEN_AUDIENCE'] == AUDIENCE
                and values['WORKSTREAM_TOKEN_JWKS_URL'] == ISSUER + '/jwks.json'
                and values['WORKSTREAM_TOKEN_ALGORITHMS'] == 'RS256',
                "hosted verifier does not match the simulated RS256 fixture")
        require(self.fixture_ca_sha256 == 'sha256:' + hashlib.sha256(
            read_private(self.identity_directory / 'ca.pem')).hexdigest(), "fixture public CA differs")
        port = urlparse(self.origin).port
        require(port == int(values.get('WORKSTREAM_API_HOST_PORT', '8000')), "published API port differs")
        environment = module.compose_environment(values)
        services = ['api', 'worker', 'beat', 'guide-document-parser']
        if values['WORKSTREAM_MODEL_PROXY_ENABLED'] == 'true':
            services.append('model-proxy')
        observed = {}
        for service in services:
            ids = _command(['docker', 'ps', '--filter', 'label=com.docker.compose.project=' +
                            values['COMPOSE_PROJECT_NAME'], '--filter',
                            'label=com.docker.compose.service=' + service, '--format', '{{.ID}}'],
                           environment=environment).decode().splitlines()
            require(len(ids) == 1, "hosted service is absent or duplicated: " + service)
            container = json.loads(_command(['docker', 'inspect', ids[0]], environment=environment))[0]
            image = json.loads(_command(['docker', 'image', 'inspect',
                               rendered['services'][service]['image']], environment=environment))[0]
            validate_container(service, rendered['services'][service], container, image,
                               rendered['secrets'], rendered['networks'])
            observed[service] = {'container_id': container['Id'], 'image_id': container['Image'],
                                 'image_reference': container['Config']['Image']}
        require((self.node_root / 'supervisor-ready').exists(), "owned node supervisor is absent")
        binding = json.loads((self.node_root / 'node-binding.json').read_text())
        require(binding['source_tree'] == _command(['git', 'rev-parse', 'HEAD']).decode().strip(),
                "native proof source differs")
        wrapper = runtime_control_root(self.node_root) / 'runtime-wrapper'
        original = json.loads(json.dumps(config))
        require(config['smol']['binary'] == str(wrapper)
                and config['smol']['binary_sha256'] == binding['wrapper_sha256']
                == 'sha256:' + hashlib.sha256(wrapper.read_bytes()).hexdigest(), "native trace wrapper differs")
        original['smol']['binary'] = binding['node_config']['smol']['binary']
        original['smol']['binary_sha256'] = binding['node_config']['smol']['binary_sha256']
        require(original == binding['node_config'], "native proof configuration differs")
        self.values, self.custody, self.docker_environment = values, observed, environment
        self.native_binding = binding
        return {'containers': observed, 'native': binding,
                'fixture_ca_sha256': self.fixture_ca_sha256,
                'identity_scope': 'simulated RS256 issuer; fixture-only derived image trust'}

    def token_for_label(self, label):
        from experiments.hosted_drill_identity.fixture import mint, read_private

        path = self.identity_directory / ('token-' + uuid4().hex)
        try:
            mint(self.identity_directory, label, path)
            return read_private(path).decode()
        finally:
            path.unlink(missing_ok=True)

    def token(self, actor):
        labels = [label for label, facts in self.actors.items()
                  if facts.actor_profile_id == actor.actor_profile_id]
        require(len(labels) == 1, "actor is outside the hosted fixture")
        return self.token_for_label(labels[0])

    async def grant(self, client, label, role, project_id=None):
        from experiments.pilot04_external_checker_runtime.public_probe_support import _json

        await _json(client, 'POST', '/api/v1/admin-role-grants', self.token_for_label('access-admin'), 201,
                    headers={'Idempotency-Key': str(uuid4())}, json={
                        'target_actor_profile_id': str(self.actors[label].actor_profile_id),
                        'role': role, 'scope_type': 'project' if project_id else 'system',
                        'scope_project_id': str(project_id) if project_id else None,
                        'reason': 'Assign authority for this isolated hosted runtime fixture.'})

    async def admit_actors(self, client, factory):
        from sqlalchemy import select
        from app.modules.actors.models import ActorIdentityLink
        from app.modules.authorization.api import ActorIdentityFacts, ActorKind
        from experiments.hosted_drill_identity.fixture import ISSUER, IDENTITIES
        from experiments.pilot04_external_checker_runtime.public_probe_support import _json

        for label in IDENTITIES:
            admitted = await _json(client, 'GET', '/api/v1/actors/me', self.token_for_label(label), 200)
            async with factory() as session:
                link = (await session.scalars(select(ActorIdentityLink).where(
                    ActorIdentityLink.actor_profile_id == admitted['actor_profile_id'],
                    ActorIdentityLink.issuer == ISSUER, ActorIdentityLink.status == 'active'))).one()
            self.actors[label] = ActorIdentityFacts(UUID(admitted['actor_profile_id']), UUID(link.id), ActorKind.HUMAN)

    async def prepare_actors(self, client, factory):
        await self.admit_actors(client, factory)
        # Deployment setup uses the established local trust-root operation. Every
        # subsequent grant, guide, task and submission uses the running public API.
        await asyncio.to_thread(self.setup_command, 'bootstrap_access_administrator.py',
                                '--actor-profile-id', str(self.actors['access-admin'].actor_profile_id), '--execute')
        await self.provision_services(client)
        await self.grant(client, 'operator', 'operator')
        await self.register_baseline_capabilities(client)
        await self.grant(client, 'manager', 'project_manager')
        await self.transition('shadow')

    async def register_baseline_capabilities(self, client):
        """Register only the two requested fixture identities under public Operator authority."""
        from app.modules.checkers.api.external import ExternalCheckerRegistryEntry
        from experiments.pilot04_external_checker_runtime.public_probe_support import _json
        from experiments.pilot04_external_checker_runtime.run_selected_end_to_end_probe import _locked_spec

        images = [item for item in self.native_binding.get('node_config', {}).get('cache', [])
                  if item['repository'] == 'workstream-test/public-journey']
        require(len(images) == 1, 'validated generic public image is absent or ambiguous')
        specs = []
        for phase in ('pre_submit', 'post_submit'):
            base = _locked_spec(phase, images[0])
            values = base.model_dump(mode='json') | self.capabilities[phase]
            values['image_digest'] = images[0]['platform_manifest_digest']
            spec = type(base).model_validate(values)
            require(spec.phase == phase, 'baseline fixture registry phase differs')
            specs.append(spec)
        require(len({(spec.capability_id, spec.capability_version) for spec in specs}) == 2,
                'baseline PRE and POST capability identities must be distinct')
        for spec in specs:
            operation_id = str(uuid4())
            value = await _json(client, 'POST', '/api/v1/operations/external-checker-registry',
                self.token_for_label('operator'), 201, headers={'Idempotency-Key': operation_id},
                json=spec.model_dump(mode='json'))
            registered = ExternalCheckerRegistryEntry.model_validate_json(json.dumps(value))
            require(registered.entry_digest == spec.spec_digest
                    and str(registered.registration_operation_id) == operation_id
                    and registered.registered_by_actor_profile_id == self.actors['operator'].actor_profile_id,
                    'public baseline registration substituted specification or authority')
            self.registered_images[spec.phase] = registered

    def approval_attachments(self, pre_requirements):
        """Select exact published fixture images as the human manager."""
        from app.modules.checkers.api.external_policy import ExternalCheckerImageAttachment

        require(pre_requirements in (0, 1, 2), 'unsupported hosted PRE fixture count')
        require(set(self.registered_images) == {'pre_submit', 'post_submit'},
                'baseline registry publications are incomplete')

        def attach(phase, requirement_id):
            entry = self.registered_images[phase]
            return ExternalCheckerImageAttachment(
                requirement_id=requirement_id, registry_entry_id=entry.registry_entry_id,
                registry_entry_digest=entry.entry_digest, configuration={},
            ).model_dump(mode='json')

        pre_ids = ('project.pre_submit.01', 'project.pre_submit.02') if pre_requirements == 2 else (
            ('project.pre_submit',) if pre_requirements == 1 else ()
        )
        return {'pre_submit_attachments': [attach('pre_submit', key) for key in pre_ids],
                'post_submit_attachments': [attach('post_submit', 'project.post_submit')]}

    async def provision_services(self, client):
        from provision_local_service_actors import JOURNEY_SERVICE_IDENTITIES, idempotency_key, subject_for
        from experiments.pilot04_external_checker_runtime.public_probe_support import _json

        prefix = 'hosted-' + str(self.actors['access-admin'].actor_profile_id)
        for identity in JOURNEY_SERVICE_IDENTITIES:
            subject = subject_for(identity, prefix)
            await _json(client, 'POST', '/api/v1/service-actors', self.token_for_label('access-admin'), 201,
                        headers={'Idempotency-Key': idempotency_key(identity, subject)},
                        json={'service_identity': identity, 'subject': subject,
                              'reason': 'Provision this isolated hosted runtime fixture.'})

    def setup_command(self, script, *arguments):
        require(script in {'bootstrap_access_administrator.py', 'transition_review_lifecycle.py'},
                "unsupported hosted setup operation")
        _command([sys.executable, str(ROOT / 'backend/scripts' / script), *arguments], timeout=120)

    async def transition(self, phase):
        require(phase in {'shadow', 'live'}, "unsupported hosted activation phase")
        await asyncio.to_thread(self.setup_command, 'transition_review_lifecycle.py', '--actor-profile-id',
                                str(self.actors['operator'].actor_profile_id), '--phase', phase,
                                '--reason', 'Activate this isolated hosted runtime fixture.')

    def stop_worker(self):
        _command([sys.executable, str(ROOT / 'deploy/hosted/compose.py'), '--env-file',
                  str(self.release_env), 'stop', 'worker'], timeout=7380)

    async def start_worker(self):
        old = self.custody['worker']['container_id']
        await asyncio.to_thread(_command, [sys.executable, str(ROOT / 'deploy/hosted/compose.py'),
                                '--env-file', str(self.release_env), 'start', 'worker'], timeout=150)
        # Compose may restart the same container. Its worker process is a new
        # generation; OUTBOX claim custody proves consumption after this boundary.
        self.inspect()
        return {'previous_container': old, 'container': self.custody['worker']['container_id']}

    async def deliver_duplicate(self, event_id, project_id):
        from app.workers.outbox import deliver_event

        hostname = (await asyncio.to_thread(
            _command, ['docker', 'inspect', '--format', '{{.Config.Hostname}}',
                       self.custody['worker']['container_id']], environment=self.docker_environment,
        )).decode().strip()
        require(hostname and len(hostname) <= 253
                and all(c.isascii() and (c.isalnum() or c in '.-_') for c in hostname),
                'owned worker hostname is invalid')
        return await asyncio.to_thread(deliver_duplicate, deliver_event, 'worker@' + hostname,
                                       event_id, project_id)


def manager_rules(original, count):
    """Describe synthetic marker checks without selecting an implementation."""
    from experiments.pilot04_external_checker_runtime.guide_runtime import _recorded_specification

    refs = [{'document': 'sha256:' + hashlib.sha256(original).hexdigest(), 'start_page': 1, 'end_page': 1}]
    requirements = []
    for stage in ('pre_submit', 'post_submit'):
        total = count if stage == 'pre_submit' else 1
        for index in range(total):
            key = 'suggested.' + stage + (f'.{index + 1:02d}' if total == 2 else '')
            requirements.append({'suggestion_id': key, 'statement': 'Check the fixture marker rule.',
                                 'stage': stage, 'evidence_refs': refs,
                                 'classification_rationale': 'Inspect the intake fixture before submission.'
                                    if stage == 'pre_submit' else 'Evaluate the submitted fixture after intake.',
                                 'check_specification': _recorded_specification(stage, index=index).model_dump(mode='json')})
    return json.dumps({'format': 'workstream.project_guide_rules.v1', 'status': 'draft_ready',
                       'findings': [{'severity': 'info', 'code': 'probe.runtime_fixture',
                                    'message': 'Synthetic hosted runtime proof, not setup-agent inference.',
                                    'evidence_refs': refs}],
                       'submission_artifact_policy': {'maximum_file_size_bytes': 1_000_000,
                            'maximum_package_size_bytes': 5_000_000, 'required_artifacts': ['task.toml'],
                            'required_evidence': ['results'], 'attestation_terms': ['rights_confirmed']},
                       'requirements': requirements,
                       'setup_notes': []}, sort_keys=True, separators=(',', ':')).encode()


async def run(attachment, database_url, broker_url, model_post_path=None):
    from experiments.pilot04_external_checker_runtime.public_hosted_model_post import (
        ModelPostQualification, validate_runtime_window,
    )

    if model_post_path:
        from app.core.config import get_settings

        attachment.inspect()
        validate_runtime_window(attachment.values, get_settings())
    qualification = ModelPostQualification.read_and_claim(model_post_path, attachment.node_root) if model_post_path else None
    try:
        return await _run(attachment, database_url, broker_url, qualification)
    finally:
        if qualification:
            qualification.close()


async def _run(attachment, database_url, broker_url, qualification):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from api_contract_e2e import assert_isolated_database_url
    from experiments.pilot04_external_checker_runtime.public_intake_trials import public_intake_trials
    from experiments.pilot04_external_checker_runtime.public_runtime_trials import public_runtime_trials
    from experiments.pilot04_external_checker_runtime.run_public_journey_probe import (
        _one_mode, _scan_audit_count, _celery_config_mismatches,
    )
    from app.core.config import get_settings

    assert_isolated_database_url(database_url)
    require(os.environ.get('WORKSTREAM_DATABASE_URL') == database_url
            and os.environ.get('WORKSTREAM_CELERY_BROKER_URL') == broker_url,
            'hosted proof setup must use the explicit isolated DB and broker')
    require(not os.environ.get('WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET'), 'hosted proof refuses HMAC')
    require(get_settings().celery_task_always_eager is False
            and not _celery_config_mismatches(get_settings()), 'hosted proof broker publisher configuration differs')
    custody = attachment.inspect()
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with httpx.AsyncClient(base_url=attachment.origin, timeout=180, trust_env=False) as client:
            if qualification:
                from experiments.pilot04_external_checker_runtime.public_hosted_model_post import run_model_post
                attachment.model_post = qualification
                await attachment.admit_actors(client, factory)
                model_result = await run_model_post(attachment, client, factory, qualification)
                from experiments.pilot04_external_checker_runtime.public_node_faults import node_command
                cleanup = await node_command(attachment.node_root, 'drained')
                require(cleanup['foreign_preserved'] and not any(cleanup['resources'].values()),
                        'hosted model proof retained runtime resources or changed foreign custody')
                attachment.inspect()
                return {'scope': 'public hosted model POST engineering fixture', 'custody': custody,
                        'provider_calls_by_driver': 0, 'model_post': model_result, 'cleanup': cleanup}
            await attachment.prepare_actors(client, factory)
            scans_before = await _scan_audit_count(factory)
            deadline = time.monotonic() + 300
            while await _scan_audit_count(factory) <= scans_before:
                require(time.monotonic() < deadline, 'hosted Beat did not dispatch an authorized artifact scan')
                await asyncio.sleep(2)
            intake = await public_intake_trials(client, factory, attachment, None, attachment.node_root)
            runtime = await public_runtime_trials(client, factory, attachment, attachment.node_root)
            human = await _one_mode(client, factory, attachment, human_review_required=True,
                                    operator_id=attachment.actors['operator'].actor_profile_id)
            automatic = await _one_mode(client, factory, attachment, human_review_required=False,
                                        operator_id=attachment.actors['operator'].actor_profile_id,
                                        stop_worker=attachment.stop_worker, start_worker=attachment.start_worker,
                                        fault_root=attachment.node_root,
                                        operator_token=attachment.token_for_label('operator'))
        from experiments.pilot04_external_checker_runtime.public_node_faults import node_command
        cleanup = await node_command(attachment.node_root, 'drained')
        require(cleanup['foreign_preserved'] and not any(cleanup['resources'].values()),
                'hosted journey retained owned runtime resources or changed the foreign control')
        attachment.inspect()
        return {'scope': 'hosted API/Celery/Beat runtime fixture', 'custody': custody,
                'guide_runtime': 'manager_authored', 'setup_agent_rehearsal': False,
                'model_enabled_post_qualification': False,
                'scheduled_artifact_scans': True,
                'provider_calls_by_driver': 0, 'compensation_policy': 'unpaid',
                'intake_trials': intake, 'runtime_trials': runtime, 'human': human,
                'automatic': automatic, 'cleanup': cleanup}
    except BaseException as error:
        if qualification:
            fields = {'phase': 'stopped', 'stopped_after': qualification.state['phase'],
                      'error_type': type(error).__name__, 'automatic_paid_retry': False}
            if 'project_id' in qualification.state:
                from experiments.pilot04_external_checker_runtime.public_hosted_model_post import account_snapshot
                try:
                    fields['ledger'] = await account_snapshot(factory, qualification.state['project_id'])
                except Exception:
                    fields['ledger_observation_unavailable'] = True
            qualification.checkpoint(**fields)
        raise
    finally:
        await engine.dispose()
