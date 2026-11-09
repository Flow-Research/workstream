"""Opt-in trusted-intake creation failures on an isolated, drained test node.

Requires sudo for the named unit's cgroup control. Checks the real wire response,
controller continuity and recovery of the single reserved intake slot.
"""
import argparse
import json
from pathlib import Path
import subprocess

from smol_recovery import wait_until
from smol_runtime import exchange


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--unit', required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    leases = Path(config['socket_path']).parent / 'smol-leases'
    groups = Path(config['smol']['cgroup_root'])
    if groups.name != args.unit or list(leases.iterdir()) or list(groups.glob('ws-*')):
        raise RuntimeError('expected drained isolated unit')
    depth = groups / 'cgroup.max.depth'
    original_depth = depth.read_text()
    original_mode = leases.stat().st_mode & 0o777
    if original_mode != 0o700:
        raise RuntimeError('lease directory must be private')

    def set_depth(value):
        subprocess.run(['sudo', 'tee', '--', str(depth)], input=value, text=True,
                       capture_output=True, check=True, timeout=10)

    def pid():
        return int(subprocess.check_output(['systemctl', 'show', '--property=MainPID',
                                           '--value', args.unit], text=True))

    def ready():
        try:
            response = exchange(config['socket_path'], {
                'protocol_version': 'trusted_submission_intake.v1',
                'operation': 'health', 'lease': None, 'payload': {},
            })
            return response['status'] == 'ok'
        except (OSError, EOFError):
            return False

    wait_until(ready, 'intake node did not become ready')
    controller = pid()
    if controller <= 0:
        raise RuntimeError('controller is not active')
    limits = {name: 100 for name in ('maximum_entries', 'maximum_path_bytes',
              'maximum_path_depth', 'maximum_central_directory_bytes',
              'maximum_entry_bytes', 'maximum_expanded_bytes', 'maximum_compression_ratio')}
    limits['maximum_inspection_seconds'] = 30
    envelope = {'protocol_version': 'trusted_submission_intake.v1',
                'operation': 'prepare', 'lease': None,
                'payload': {'phase': 'pre_submit', 'policy_sha256': 'sha256:' + 'a' * 64,
                            'limits': limits, 'deadline_ms': 30000, 'archive_byte_count': 1}}
    try:
        for case in ('lease_create_denied', 'cgroup_create_denied'):
            try:
                if case == 'lease_create_denied':
                    leases.chmod(0o500)
                else:
                    set_depth('0')
                response = exchange(config['socket_path'], envelope)
                expected = {'protocol_version': 'trusted_submission_intake.v1',
                            'operation': 'prepare', 'lease': None, 'status': 'error',
                            'payload': {'code': 'runtime_unavailable'}}
                if response != expected or pid() != controller:
                    raise AssertionError((case, response))
            finally:
                leases.chmod(original_mode)
                set_depth(original_depth)
            # exchange closes the socket after ready; the guardian must release
            # the reserved slot on EOF so the next preparation can run.
            ready = exchange(config['socket_path'], envelope)
            if ready['status'] != 'ok' or not ready['lease'] or pid() != controller:
                raise AssertionError(ready)
            wait_until(lambda: not list(leases.iterdir()) and not list(groups.glob('ws-*')),
                       'intake creation failure retained capacity')
            print(json.dumps({'case': case, 'intake_response': 'runtime_unavailable',
                              'controller_unchanged': True, 'next_prepare': 'ok',
                              'cleanup': 'confirmed'}), flush=True)
    finally:
        leases.chmod(original_mode)
        set_depth(original_depth)


if __name__ == '__main__':
    main()
