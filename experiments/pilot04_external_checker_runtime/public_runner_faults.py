"""Operator-only SSH attachment to one already verified finite runner fault run.

No credentials enter API/worker settings. This module never deploys or starts a
remote supervisor, changes a node configuration, or retries a command after an
uncertain acknowledgement.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
from uuid import UUID, uuid4

from experiments.pilot04_external_checker_runtime.public_node_faults import ACTIONS, CONTROL_PROTOCOL, _unique_object

_SHA256 = re.compile(r'sha256:[0-9a-f]{64}\Z')
_COMMAND_ID = re.compile(r'[0-9a-f]{32}\Z')


class FaultOutcomeUnknown(RuntimeError):
    """Keep the original ID so the operator observes it instead of resending."""

    def __init__(self, command_id):
        self.command_id = command_id
        super().__init__('runner fault outcome unknown; query the original command ID')


def _private_file(path, *, secret):
    if not isinstance(path, Path) or not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('SSH pin path differs')
    info = path.lstat()
    modes = {0o400, 0o600} if secret else {0o400, 0o600, 0o644}
    owners = {os.getuid()} if secret else {0, os.getuid()}
    if (not stat.S_ISREG(info.st_mode) or info.st_uid not in owners
            or stat.S_IMODE(info.st_mode) not in modes or info.st_nlink != 1
            or not 0 < info.st_size <= 1024 * 1024):
        raise ValueError('SSH pin ownership/mode differs')


def _remote_path(value):
    if (type(value) is not str or not value.startswith('/') or '\x00' in value
            or len(value) > 4096 or '\n' in value or '\r' in value
            or str(PurePosixPath(value)) != value or '..' in PurePosixPath(value).parts):
        raise ValueError('remote fault path differs')
    return value


@dataclass(frozen=True)
class RunnerFaultProfile:
    """Explicit operator pins; callers must obtain custody independently."""

    host: str
    identity_file: Path
    known_hosts_file: Path
    source_root: str
    control_root: str
    run_id: str
    binding_sha256: str
    image_digest: str

    def validate(self):
        """Check explicit operator pins without reading identity key bytes."""
        if (type(self.host) is not str or type(self.run_id) is not str
                or str(ipaddress.IPv4Address(self.host)) != self.host or str(UUID(self.run_id)) != self.run_id):
            raise ValueError('SSH runner/run identity differs')
        if (type(self.binding_sha256) is not str or _SHA256.fullmatch(self.binding_sha256) is None
                or type(self.image_digest) is not str or _SHA256.fullmatch(self.image_digest) is None):
            raise ValueError('runner custody pin differs')
        _private_file(self.identity_file, secret=True)
        _private_file(self.known_hosts_file, secret=False)
        _remote_path(self.source_root)
        _remote_path(self.control_root)

    def command(self):
        """Reuse the approved pinned transport pattern, with a fixed remote action."""
        self.validate()
        remote = shlex.join(['/usr/bin/sudo', '-n', '/usr/bin/env', 'PYTHONPATH=' + self.source_root,
            '/usr/bin/python3', '-m', 'experiments.pilot04_external_checker_runtime.public_node_faults',
            '--root', self.control_root, '--request'])
        return ['ssh', '-F', '/dev/null', '-i', str(self.identity_file),
            '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none', '-o', 'BatchMode=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(self.known_hosts_file),
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'UpdateHostKeys=no',
            '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            'ubuntu@' + self.host, remote]


async def _bounded_read(stream, limit):
    chunks, count = [], 0
    while True:
        chunk = await stream.read(min(65536, limit + 1 - count))
        if not chunk:
            return b''.join(chunks)
        count += len(chunk)
        if count > limit:
            raise ValueError('SSH output exceeds bound')
        chunks.append(chunk)



class RunnerFaults:
    """One SSH operator context with append-only trace observation."""

    def __init__(self, profile: RunnerFaultProfile):
        profile.validate()
        self.profile, self._events, self._trace_sha256 = profile, (), None

    async def _exchange(self, request):
        process, readers = None, []
        try:
            encoded = json.dumps(request, separators=(',', ':'), allow_nan=False).encode()
            async with asyncio.timeout(60):
                process = await asyncio.create_subprocess_exec(*self.profile.command(),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                process.stdin.write(encoded)
                await process.stdin.drain()
                process.stdin.close()
                readers = [asyncio.create_task(_bounded_read(process.stdout, 2 * 1024 * 1024)),
                           asyncio.create_task(_bounded_read(process.stderr, 16384))]
                output, _ = await asyncio.gather(*readers)
                if await process.wait() != 0:
                    raise RuntimeError('SSH fault request failed')
            response = json.loads(output, object_pairs_hook=_unique_object,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('JSON constant')))
            if (type(response) is not dict or response.get('protocol_version') != CONTROL_PROTOCOL
                    or response.get('run_id') != self.profile.run_id
                    or response.get('operation') != request['operation']
                    or response.get('binding_sha256') != self.profile.binding_sha256
                    or response.get('image_digest') != self.profile.image_digest):
                raise ValueError('fault response identity differs')
            return response
        except BaseException as error:
            if process is not None and process.returncode is None:
                try:
                    process.kill()  # Only the owned local SSH process, never a remote controller PID.
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    pass
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            if request['operation'] == 'command':
                raise FaultOutcomeUnknown(request['command_id']) from None
            raise RuntimeError('runner fault observation unavailable') from error

    def _request(self, operation, **fields):
        return {'protocol_version': CONTROL_PROTOCOL, 'run_id': self.profile.run_id,
                'operation': operation, 'binding_sha256': self.profile.binding_sha256,
                'image_digest': self.profile.image_digest, **fields}

    async def command(self, action, *, command_id=None):
        """Issue once; any uncertain completion retains the original command ID."""
        identifier = uuid4().hex if command_id is None else command_id
        if type(action) is not str or action not in ACTIONS or type(identifier) is not str or _COMMAND_ID.fullmatch(identifier) is None:
            raise ValueError('fault command selector differs')
        response = await self._exchange(self._request('command', command_id=identifier, action=action))
        observed = self._command_response(response, identifier, action)
        if observed['state'] != 'completed' or observed['result']['ok'] is not True:
            raise FaultOutcomeUnknown(identifier)
        return observed

    async def query(self, command_id, action):
        """Observe the original command without enqueuing another mutation."""
        if type(command_id) is not str or _COMMAND_ID.fullmatch(command_id) is None or type(action) is not str or action not in ACTIONS:
            raise ValueError('fault command selector differs')
        response = await self._exchange(self._request('query', command_id=command_id, action=action))
        return self._command_response(response, command_id, action)

    @staticmethod
    def _command_response(response, identifier, action):
        if (set(response) != {'protocol_version', 'run_id', 'operation', 'binding_sha256', 'image_digest',
                             'command_id', 'action', 'state', 'result'}
                or response['command_id'] != identifier or response['action'] != action
                or response['state'] not in {'unknown', 'completed'}):
            raise FaultOutcomeUnknown(identifier)
        result = response['result']
        if response['state'] == 'unknown':
            if result is not None:
                raise FaultOutcomeUnknown(identifier)
        elif type(result) is not dict or result.get('action') != action or type(result.get('ok')) is not bool:
            raise FaultOutcomeUnknown(identifier)
        return response

    async def snapshot(self):
        """Read a bounded trace prefix and same-run cleanup observation."""
        response = await self._exchange(self._request('snapshot'))
        if (set(response) != {'protocol_version', 'run_id', 'operation', 'binding_sha256', 'image_digest',
                             'events', 'cursor', 'trace_sha256', 'cleanup'}
                or type(response['events']) is not list or len(response['events']) > 4096
                or type(response['cursor']) is not int or response['cursor'] != len(response['events'])
                or type(response['trace_sha256']) is not str or _SHA256.fullmatch(response['trace_sha256']) is None
                or any(type(event) is not dict for event in response['events'])
                or response['events'][:len(self._events)] != list(self._events)
                or len(response['events']) == len(self._events) and self._trace_sha256 is not None
                and response['trace_sha256'] != self._trace_sha256):
            raise RuntimeError('runner trace changed or exceeded its bound')
        cleanup = response['cleanup']
        if cleanup is not None:
            if (type(cleanup) is not dict or cleanup.get('protocol_version') != CONTROL_PROTOCOL
                    or cleanup.get('run_id') != self.profile.run_id
                    or cleanup.get('binding_sha256') != self.profile.binding_sha256
                    or cleanup.get('image_digest') != self.profile.image_digest
                    or type(cleanup.get('config_sha256')) is not str
                    or _SHA256.fullmatch(cleanup['config_sha256']) is None
                    or type(cleanup.get('resources')) is not dict
                    or set(cleanup['resources']) != {'disks', 'leases', 'machines', 'cgroups'}
                    or any(type(value) is not list or value for value in cleanup['resources'].values())
                    or type(cleanup.get('foreign')) is not dict
                    or type(cleanup['foreign'].get('name')) is not str or not cleanup['foreign']['name']
                    or any(cleanup['foreign'].get(field) is not True for field in
                           ('machine_absent', 'disk_absent', 'cgroup_absent', 'process_reaped'))):
                raise RuntimeError('runner cleanup is incomplete or belongs to another run')
        self._events = tuple(response['events'])
        self._trace_sha256 = response['trace_sha256']
        return response
