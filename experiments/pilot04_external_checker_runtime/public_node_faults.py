"""Owned-node fault commands for the opt-in public drill; never imported by production."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
from uuid import UUID, uuid4

from experiments.pilot04_external_checker_runtime.public_fault_files import PrivateControlDirectory, private_path


HOSTED_IDENTITY = (10001, 10001)
CONTROL_PROTOCOL = 'workstream.operator_fault.v1'
ACTIONS = frozenset({'project_fail_once', 'project_fail_all', 'project_kill', 'clear', 'drained', 'restarted'})
_COMMAND_ID = re.compile(r'[0-9a-f]{32}\Z')


def _run_id(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError('fault run ID differs')
    return value


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate fault JSON field')
        value[key] = item
    return value


def _operator_controls(root):
    return PrivateControlDirectory(root, trusted_uids=(10001,) if os.getuid() == 0 else ())


def runtime_control_root(root):
    """Resolve only the operator-written, fixed hosted sibling binding."""
    root = Path(root)
    binding = root / 'runtime-controls.json'
    if not binding.exists() and not binding.is_symlink():
        return root
    control = _operator_controls(root)
    try:
        value = control.read(binding.name)
    finally:
        control.close()
    expected = root.with_name(root.name + '-runtime')
    if os.getuid() != 0 or value != {'root': str(expected), 'uid': 10001, 'gid': 10001}:
        raise ValueError('runtime control binding differs')
    private_path(expected, 0o700, directory=True, uid=10001, gid=10001)
    return expected


def _runtime_user(identity):
    if identity is None:
        return {}
    if os.getuid() != 0 or identity != HOSTED_IDENTITY:
        raise ValueError('hosted runtime commands require the root operator')
    return {'user': identity[0], 'group': identity[1], 'extra_groups': []}


def runtime(config, *args, identity=None):
    smol = config['smol']
    return json.loads(subprocess.check_output(
        [smol['binary'], *args], env={'HOME': smol['home'], 'PATH': '/usr/bin:/bin'},
        text=True, timeout=15, **_runtime_user(identity),
    ))


def owned_resources(config, root=None, *, identity=None):
    leases = Path(config['socket_path']).parent / 'smol-leases'
    owner = (leases.parent / '.workstream-checker-owner').read_text().strip()
    machines = [row for row in runtime(config, 'machine', 'ls', '--json', identity=identity)
                if row['labels'].get('workstream.external-checker-owner') == owner]
    groups = [p.name for p in Path(config['smol']['cgroup_root']).iterdir()
              if p.is_dir() and p.name.startswith('ws-')]
    names = [] if root is None else [event['name'] for event in trace_events(root)
                                  if event['operation'] == 'create']
    disks = [name for name in names if (Path(config['smol']['home']) / '.cache/smolvm/vms'
             / hashlib.sha256(name.encode()).hexdigest()[:16]).exists()]
    return {'disks': disks, 'leases': [p.name for p in leases.iterdir()],
            'machines': [row['name'] for row in machines], 'cgroups': groups}


def _trace_require(condition, message):
    if not condition:
        raise RuntimeError(message)


def trace_events(root):
    return [json.loads(line) for line in (runtime_control_root(root) / 'runtime-trace.jsonl').read_text().splitlines()]


def assert_launches(root, start, *, creates, executions, project=True, shared_deadline=True):
    events = [event for event in trace_events(root)[start:] if event['project'] is project]
    made = [event['name'] for event in events if event['operation'] == 'create']
    _trace_require(len(made) == creates and len(set(made)) == creates,
             'runtime retry did not allocate the expected fresh machines')
    _trace_require(len([e for e in events if e['operation'] == 'exec']) == executions,
             'runtime retried an invoked guest or skipped expected execution')
    _trace_require(set(made) == {event['name'] for event in events if event['operation'] == 'delete'},
             'runtime retry lacks deletion of each exact machine')
    expected = []
    for index, name in enumerate(made):
        operations = ['create', 'start'] + (['exec'] if index >= creates - executions else []) + ['delete']
        expected.extend((name, operation) for operation in operations)
    observed = [(event['name'], event['operation']) for event in events
                if event['operation'] in {'create', 'start', 'exec', 'delete'}]
    _trace_require(observed == expected, 'runtime retried after invocation or broke exact machine sequencing')
    created = [event for event in events if event['operation'] == 'create']
    _trace_require(all(event.get('lease') and event['lease']['name'] == event['name'] for event in created),
                   'created machine lacks exact lease evidence')
    leases = [event['lease'] for event in events if event.get('lease')]
    if made and shared_deadline:
        # Rust retains one Instant deadline; each persisted wall-clock projection
        # floors both now_ms and remaining.as_millis(), so adjacent values can differ
        # by one millisecond. A new full budget is never valid on a later retry.
        expiries = [lease['expires_ms'] for lease in leases]
        lifetimes = [event['lease']['lifetime_ms'] for event in created]
        _trace_require(len({lease['epoch'] for lease in leases}) == 1
                 and max(expiries) - min(expiries) <= 1
                 and all(later < earlier for earlier, later in zip(lifetimes, lifetimes[1:])),
                 'launch retry changed its original lease epoch/deadline')
    return made


async def node_command(root, action, *, identifier=None):
    """Send one stable closed command; an uncertain ACK never changes its ID."""
    if action not in ACTIONS:
        raise ValueError('unknown fixture action')
    identifier = uuid4().hex if identifier is None else identifier
    if type(identifier) is not str or _COMMAND_ID.fullmatch(identifier) is None:
        raise ValueError('fault command ID differs')
    control = _operator_controls(root)
    try:
        request = {'action': action}
        try:
            retained = control.read(identifier + '.request')
        except FileNotFoundError:
            control.write(identifier + '.request', request)
        else:
            if retained != request:
                raise ValueError('fault command ID/action changed')
    finally:
        control.close()
    response = root / (identifier + '.response')
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if response.exists():
            control = _operator_controls(root)
            try:
                result = control.read(response.name)
            finally:
                control.close()
            if not result['ok']:
                raise RuntimeError('owned node fault command failed: ' + action)
            return result
        await asyncio.sleep(.1)
    raise RuntimeError('owned node fault command timed out: ' + action)



def _read_run(root, expected):
    """Bind all operator observations to the same private finite supervisor run."""
    _run_id(expected)
    control = _operator_controls(root)
    try:
        run = control.read('supervisor-run.json')
    finally:
        control.close()
    if (type(run) is not dict or run.get('protocol_version') != CONTROL_PROTOCOL
            or run.get('run_id') != expected or type(run.get('deadline_monotonic')) not in {int, float}
            or not math.isfinite(run['deadline_monotonic']) or run['deadline_monotonic'] <= 0
            or type(run.get('maximum_seconds')) is not int or not 1 <= run['maximum_seconds'] <= 1800
            or type(run.get('binding_sha256')) is not str
            or re.fullmatch(r'sha256:[0-9a-f]{64}', run['binding_sha256']) is None
            or type(run.get('image_digest')) is not str
            or re.fullmatch(r'sha256:[0-9a-f]{64}', run['image_digest']) is None):
        raise ValueError('fault supervisor run differs')
    return run


def _command_observation(root, identifier, action):
    if type(identifier) is not str or _COMMAND_ID.fullmatch(identifier) is None or type(action) is not str or action not in ACTIONS:
        raise ValueError('fault command selector differs')
    control = _operator_controls(root)
    try:
        try:
            request = control.read(identifier + '.request')
        except FileNotFoundError:
            return {'state': 'unknown', 'result': None}
        if request != {'action': action}:
            raise ValueError('fault command ID/action changed')
        try:
            result = control.read(identifier + '.response')
        except FileNotFoundError:
            return {'state': 'unknown', 'result': None}
        if type(result) is not dict or result.get('action') != action or type(result.get('ok')) is not bool:
            raise ValueError('fault command response differs')
        return {'state': 'completed', 'result': result}
    finally:
        control.close()


async def control_request(root, request):
    """SSH-only operator entry point; no deployment or arbitrary filesystem API."""
    if type(request) is not dict or request.get('protocol_version') != CONTROL_PROTOCOL:
        raise ValueError('fault control protocol differs')
    operation = request.get('operation')
    expected = {'protocol_version', 'run_id', 'operation', 'binding_sha256', 'image_digest'}
    if operation in {'command', 'query'}:
        expected |= {'command_id', 'action'}
    if set(request) != expected or operation not in {'command', 'query', 'snapshot'}:
        raise ValueError('fault control request differs')
    run = _read_run(root, request['run_id'])
    if request['binding_sha256'] != run['binding_sha256'] or request['image_digest'] != run['image_digest']:
        raise ValueError('fault custody pin differs')
    response = {'protocol_version': CONTROL_PROTOCOL, 'run_id': run['run_id'],
                'operation': operation, 'binding_sha256': run['binding_sha256'], 'image_digest': run['image_digest']}
    if operation == 'snapshot':
        runtime_root = runtime_control_root(root)
        identity = HOSTED_IDENTITY if runtime_root != root else (os.getuid(), os.getgid())
        trace = PrivateControlDirectory(runtime_root, uid=identity[0], gid=identity[1])
        try:
            data = trace.trace_bytes()
        finally:
            trace.close()
        events = [json.loads(line) for line in data.splitlines()]
        if len(events) > 4096 or any(type(event) is not dict for event in events):
            raise ValueError('fault trace record bound differs')
        control = _operator_controls(root)
        try:
            try:
                cleanup = control.read('supervisor-cleanup.json')
            except FileNotFoundError:
                cleanup = None
        finally:
            control.close()
        if cleanup is not None and (type(cleanup) is not dict
                or cleanup.get('protocol_version') != CONTROL_PROTOCOL
                or cleanup.get('run_id') != run['run_id']
                or cleanup.get('binding_sha256') != run['binding_sha256']
                or cleanup.get('image_digest') != run['image_digest']):
            raise ValueError('fault cleanup receipt differs')
        response.update(events=events, cursor=len(events), trace_sha256='sha256:' + hashlib.sha256(data).hexdigest(),
                        cleanup=cleanup)
        return response
    identifier, action = request['command_id'], request['action']
    observed = _command_observation(root, identifier, action)
    if operation == 'command' and observed['state'] != 'completed':
        if time.monotonic() >= run['deadline_monotonic'] or (root / 'supervisor-cleanup.json').exists():
            raise RuntimeError('fault supervisor is not available')
        private_path(root / 'supervisor-ready', 0o600)
        await node_command(root, action, identifier=identifier)
        observed = _command_observation(root, identifier, action)
    response.update(command_id=identifier, action=action, **observed)
    return response


def _config_identity(hosted_runtime):
    if hosted_runtime:
        if os.getuid() != 0:
            raise ValueError('hosted supervisor requires the root operator')
        return 10001, 10001, 0o400
    return os.getuid(), os.getgid(), 0o600


def _read_config(config_path, hosted_runtime):
    uid, gid, mode = _config_identity(hosted_runtime)
    private_path(config_path, mode, uid=uid, gid=gid)
    before = config_path.lstat()
    descriptor = os.open(config_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(descriptor, 'rb') as source:
        if not os.path.samestat(before, os.fstat(source.fileno())) or before.st_size > 1024 * 1024:
            raise ValueError('node config identity/size differs')
        data = source.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('node config exceeds bound')
    return data, (before.st_dev, before.st_ino)


def write_node_config(config_path, data, identity, *, hosted_runtime=False):
    """Write only the validated existing inode, preserving its owner and mode."""
    if len(data) > 1024 * 1024:
        raise ValueError('node config exceeds bound')
    uid, gid, mode = _config_identity(hosted_runtime)
    private_path(config_path, mode, uid=uid, gid=gid)
    descriptor = os.open(config_path, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(descriptor, 'wb') as target:
        info = os.fstat(target.fileno())
        if ((info.st_dev, info.st_ino) != identity or not stat.S_ISREG(info.st_mode)
                or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (uid, gid, mode)
                or info.st_nlink != 1 or not os.path.samestat(info, config_path.lstat())):
            raise ValueError('node config custody changed before write')
        target.seek(0)
        target.write(data)
        target.truncate()
        target.flush()
        os.fsync(target.fileno())
        if not os.path.samestat(info, config_path.lstat()):
            raise ValueError('node config custody changed during write')


def validate_node(config_path, config, unit, manifest_path, *, hosted_runtime=False):
    if config['smol'].get('maximum_parallel') != 1:
        raise ValueError('public proof requires a one-slot node')
    original, _ = _read_config(config_path, hosted_runtime)
    if json.loads(original) != config:
        raise ValueError('node config changed during validation')
    private_path(manifest_path, 0o600, trusted_uids=(10001,) if hosted_runtime else ())
    manifest = json.loads(manifest_path.read_text())
    socket = Path(config['socket_path'])
    uid, gid, _ = _config_identity(hosted_runtime)
    private_path(socket.parent, 0o700, directory=True, uid=uid, gid=gid)
    owner_path = socket.parent / '.workstream-checker-owner'
    private_path(owner_path, 0o600, uid=uid, gid=gid)
    properties = dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', 'show', unit, '-p', 'MainPID', '-p', 'ControlGroup'], text=True).splitlines())
    pid = int(properties['MainPID'])
    if hosted_runtime:
        status = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/status').read_text().splitlines())
        if (config.get('sandbox_uid'), config.get('sandbox_gid')) != HOSTED_IDENTITY or any(
                [int(value) for value in status[key].split()] != [expected] * 4
                for key, expected in [('Uid', uid), ('Gid', gid)]):
            raise ValueError('live hosted node identity differs')
    executable = str(Path(f'/proc/{pid}/exe').resolve())
    argv = Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
    expected = {'unit': unit, 'config': str(config_path), 'socket': str(socket),
                'executable': executable, 'owner': owner_path.read_text().strip(),
                'config_sha256': 'sha256:' + hashlib.sha256(original).hexdigest(),
                'node_config': config,
                'service_sha256': 'sha256:' + hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
                'smol_sha256': 'sha256:' + hashlib.sha256(Path(config['smol']['binary']).read_bytes()).hexdigest(),
                'guest_sha256': 'sha256:' + hashlib.sha256(Path(config['smol']['guest_binary']).read_bytes()).hexdigest(),
                'wrapper_sha256': 'sha256:' + hashlib.sha256(
                    Path(__file__).with_name('public_runtime_wrapper.py').read_bytes()).hexdigest(),
                'source_tree': subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).parents[2], text=True).strip()}
    if manifest != expected or argv != [executable, str(config_path)]:
        raise ValueError('unit/config/owner manifest does not match the live node')
    if config['smol']['cgroup_root'] != '/sys/fs/cgroup' + properties['ControlGroup']:
        raise ValueError('unit delegation differs from configured node')
    return expected


class ForeignControl:
    """A uniquely named foreign VM and sibling process must survive node recovery."""

    def __init__(self, config, project, *, identity=None):
        self.config = config
        self.name = 'smol-proof-foreign-' + uuid4().hex
        self.group = Path(config['smol']['cgroup_root']) / self.name
        self.process = None
        self.created = False
        self.project = project
        self.identity = identity

    def command(self, *args):
        smol = self.config['smol']
        return subprocess.run([smol['binary'], *args], check=True, capture_output=True,
                              env={'HOME': smol['home'], 'PATH': '/usr/bin:/bin'}, timeout=30,
                              **_runtime_user(getattr(self, 'identity', None)))

    def start(self):
        self.command('machine', 'create', '--name', self.name, '--image', self.project['smol']['archive'],
                     '--label', 'workstream.external-checker-owner=foreign-control', '--mem', '256', '--storage', '1')
        self.created = True
        self.group.mkdir()
        self.process = subprocess.Popen(['sleep', '1800'])
        subprocess.run(['sudo', 'tee', str(self.group / 'cgroup.procs')],
                       input=str(self.process.pid), text=True, capture_output=True, check=True, timeout=10)
        self.check()

    def check(self):
        rows = runtime(self.config, 'machine', 'ls', '--json', identity=getattr(self, 'identity', None))
        matching = [row for row in rows if row['name'] == self.name]
        if (len(matching) != 1 or matching[0]['labels'].get('workstream.external-checker-owner') != 'foreign-control'
                or self.process.poll() is not None or not self.group.exists()
                or str(self.process.pid) not in (self.group / 'cgroup.procs').read_text().splitlines()):
            raise RuntimeError('foreign recovery control was changed')

    def close(self):
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=10)
        if self.group.exists():
            self.group.rmdir()
        if self.created:
            matching = [row for row in runtime(self.config, 'machine', 'ls', '--json', identity=getattr(self, 'identity', None)) if row['name'] == self.name]
            if len(matching) != 1 or matching[0]['labels'].get('workstream.external-checker-owner') != 'foreign-control':
                raise RuntimeError('foreign fixture identity changed before exact cleanup')
            self.command('machine', 'delete', '--name', self.name, '--force')
        disk = Path(self.config['smol']['home']) / '.cache/smolvm/vms' / hashlib.sha256(self.name.encode()).hexdigest()[:16]
        remaining = [row for row in runtime(self.config, 'machine', 'ls', '--json', identity=getattr(self, 'identity', None)) if row['name'] == self.name]
        if remaining or disk.exists() or self.group.exists() or (self.process is not None and self.process.poll() is None):
            raise RuntimeError('foreign fixture cleanup is incomplete')
        return {'name': self.name, 'machine_absent': True, 'disk_absent': True,
                'cgroup_absent': True, 'process_reaped': True}

def serve(config_path, root, unit, manifest_path, *, hosted_runtime=False, run_id, maximum_seconds, image_digest):
    """Inject only project-start faults on a dedicated empty node and restore on exit."""
    from shutil import copyfile

    _run_id(run_id)
    if type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 1800:
        raise ValueError('fault supervisor requires a finite <=1800s budget')
    os.umask(0o077)
    original, config_identity = _read_config(config_path, hosted_runtime)
    config = json.loads(original)
    if type(image_digest) is not str or re.fullmatch(r'sha256:[0-9a-f]{64}', image_digest) is None:
        raise ValueError('fault image digest differs')
    matching = [entry for entry in config['cache'] if entry['platform_manifest_digest'] == image_digest]
    if len(matching) != 1:
        raise ValueError('fault image cache selection is absent or ambiguous')
    project = matching[0]
    binding = validate_node(config_path, config, unit, manifest_path, hosted_runtime=hosted_runtime)
    identity = HOSTED_IDENTITY if hosted_runtime else None
    if any(owned_resources(config, identity=identity).values()):
        raise RuntimeError('node must be drained')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    control = _operator_controls(root)
    if list(root.iterdir()):
        raise ValueError('fault root must be fresh and empty')
    control.write('node-binding.json', binding)
    run_deadline = time.monotonic() + maximum_seconds
    binding_sha256 = 'sha256:' + hashlib.sha256(json.dumps(binding, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    control.write('supervisor-run.json', {'protocol_version': CONTROL_PROTOCOL, 'run_id': run_id,
        'maximum_seconds': maximum_seconds, 'deadline_monotonic': run_deadline, 'image_digest': image_digest,
        'binding_sha256': binding_sha256})
    runtime_root = root
    runtime_control = control
    if hosted_runtime:
        runtime_root = root.with_name(root.name + '-runtime')
        runtime_root.mkdir(mode=0o700)
        os.chown(runtime_root, *HOSTED_IDENTITY)
        runtime_control = PrivateControlDirectory(runtime_root, uid=10001, gid=10001)
        control.write('runtime-controls.json', {'root': str(runtime_root), 'uid': 10001, 'gid': 10001})
    wrapper = runtime_root / 'runtime-wrapper'
    copyfile(Path(__file__).with_name('public_runtime_wrapper.py'), wrapper)
    wrapper.chmod(0o700)
    if hosted_runtime:
        os.chown(wrapper, *HOSTED_IDENTITY)
    state = runtime_root / 'runtime-mode.json'
    runtime_control.write(state.name, {'failures': 0, 'kill': False})
    trace = runtime_root / 'runtime-trace.jsonl'
    trace.touch(mode=0o600)
    if hosted_runtime:
        os.chown(trace, *HOSTED_IDENTITY)
    runtime_control.write(wrapper.with_suffix('.json').name, {
        'binary': config['smol']['binary'], 'project_archive': project['smol']['archive'],
        'mode': str(state), 'trace': str(trace), 'unit': unit,
        'socket': config['socket_path'],
    })
    changed = json.loads(original)
    changed['smol']['binary'] = str(wrapper)
    changed['smol']['binary_sha256'] = 'sha256:' + hashlib.sha256(wrapper.read_bytes()).hexdigest()

    def restart():
        subprocess.run(['sudo', 'systemctl', 'restart', unit], check=True, timeout=30)

    def stop(_signum, _frame):
        raise KeyboardInterrupt

    foreign = ForeignControl(config, project, identity=identity)
    previous_handlers = {item: signal.getsignal(item) for item in (signal.SIGTERM, signal.SIGHUP)}
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    try:
        foreign.start()
        write_node_config(config_path, json.dumps(changed).encode(), config_identity,
                          hosted_runtime=hosted_runtime)
        restart()
        (root / 'supervisor-ready').write_text('ready')
        while time.monotonic() < run_deadline:
            for request in sorted(root.glob('*.request')):
                if time.monotonic() >= run_deadline:
                    break
                response = request.with_suffix('.response')
                if response.exists():
                    continue
                action = control.read(request.name)['action']
                result = {'ok': True, 'action': action}
                try:
                    if action in {'project_fail_once', 'project_fail_all', 'project_kill', 'clear'}:
                        failures = {'project_fail_once': 1, 'project_fail_all': -1,
                                    'project_kill': 0, 'clear': 0}[action]
                        runtime_control.write(state.name, {'failures': failures, 'kill': action == 'project_kill'})
                        if action == 'project_kill':
                            result['controller_pid'] = int(subprocess.check_output(
                                ['systemctl', 'show', unit, '-p', 'MainPID', '--value'], text=True, timeout=15))
                    elif action == 'drained':
                        deadline = time.monotonic() + 25
                        while any(owned_resources(config, root, identity=identity).values()):
                            if time.monotonic() >= deadline:
                                raise RuntimeError('owned resources not drained')
                            time.sleep(.1)
                        result['resources'] = owned_resources(config, root, identity=identity)
                        foreign.check()
                        result['foreign_preserved'] = foreign.name
                    elif action == 'restarted':
                        deadline = time.monotonic() + 25
                        while True:
                            pid = int(subprocess.check_output(
                                ['systemctl', 'show', unit, '-p', 'MainPID', '--value'], text=True, timeout=15))
                            # A new owned VM after restart is the health/epoch proof; the
                            # caller compares this PID to the durably recorded kill target.
                            if pid and Path(f'/proc/{pid}/exe').resolve() == Path(binding['executable']):
                                result['controller_pid'] = pid
                                break
                            if time.monotonic() >= deadline:
                                raise RuntimeError('controller did not restart')
                            time.sleep(.1)
                    else:
                        raise ValueError('unknown fixture action')
                except Exception:
                    result['ok'] = False
                control.write(response.name, result)
            time.sleep(.1)
    except KeyboardInterrupt:
        pass
    finally:
        # Repeated disconnect/termination cannot interrupt bounded restoration.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        try:
            write_node_config(config_path, original, config_identity, hosted_runtime=hosted_runtime)
            restart()
            if foreign.created and foreign.process is not None:
                foreign.check()
        finally:
            try:
                foreign_cleanup = foreign.close()
                resources = owned_resources(config, root, identity=identity)
                if any(resources.values()) or config_path.read_bytes() != original:
                    raise RuntimeError('supervisor restore or owned cleanup is incomplete')
                control.write('supervisor-cleanup.json', {
                    'protocol_version': CONTROL_PROTOCOL, 'run_id': run_id,
                    'binding_sha256': binding_sha256, 'image_digest': image_digest,
                    'config_sha256': 'sha256:' + hashlib.sha256(original).hexdigest(),
                    'resources': resources, 'foreign': foreign_cleanup,
                })
                (root / 'supervisor-ready').unlink(missing_ok=True)
            finally:
                try:
                    if runtime_control is not control:
                        runtime_control.close()
                    control.close()
                finally:
                    for item, previous in previous_handlers.items():
                        signal.signal(item, previous)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--node-config', type=Path)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--unit')
    parser.add_argument('--owner-manifest', type=Path)
    parser.add_argument('--request', action='store_true', help='process one bounded SSH operator request on stdin')
    parser.add_argument('--run-id')
    parser.add_argument('--maximum-seconds', type=int)
    parser.add_argument('--image-digest')
    parser.add_argument('--hosted-runtime', action='store_true',
                        help='root operator with the fixed runtime identity 10001:10001')
    args = parser.parse_args()
    if args.request:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            parser.error('fault request exceeds bound')
        result = asyncio.run(control_request(args.root, json.loads(raw, object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('JSON constant')))))
        encoded = json.dumps(result, separators=(',', ':'), allow_nan=False).encode()
        if len(encoded) > 2 * 1024 * 1024:
            parser.error('fault response exceeds bound')
        sys.stdout.buffer.write(encoded + b'\n')
    else:
        if not all((args.node_config, args.unit, args.owner_manifest, args.run_id, args.maximum_seconds, args.image_digest)):
            parser.error('supervisor requires node config, unit, manifest, run ID and finite budget')
        serve(args.node_config, args.root, args.unit, args.owner_manifest, hosted_runtime=args.hosted_runtime,
              run_id=args.run_id, maximum_seconds=args.maximum_seconds, image_digest=args.image_digest)
