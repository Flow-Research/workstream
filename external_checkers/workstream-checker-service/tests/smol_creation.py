"""Opt-in recoverable creation-failure proof for an isolated Smol test unit.

Temporarily removes lease-directory write permission and disallows new child
cgroups. Existing work must survive, cleanup must finish, and admission must
remain usable. Never target a shared production node.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess

from smol_recovery import wait_until
from smol_runtime import Proof, background_slots, exchange


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--unit', required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if config['sandbox_uid'] != os.geteuid() or os.geteuid() == 0:
        raise RuntimeError('run as the non-root node identity')
    leases = Path(config['socket_path']).parent / 'smol-leases'
    groups = Path(config['smol']['cgroup_root'])
    if groups.name != args.unit or background_slots(config) < 2:
        raise RuntimeError('expected isolated unit with two background slots')
    depth = groups / 'cgroup.max.depth'
    original_depth = depth.read_text()
    original_mode = leases.stat().st_mode & 0o777
    if list(leases.iterdir()) or original_mode != 0o700:
        raise RuntimeError('node must start drained with private leases')
    proof = Proof(config, args.fixtures)
    image = next(c for c in config['cache'] if c['repository'] == 'workstream-test/smol-python')

    def pid():
        value = subprocess.check_output(['systemctl', 'show', '--property=MainPID',
                                         '--value', args.unit], text=True).strip()
        if int(value) <= 0:
            raise AssertionError('controller stopped')
        return value

    def running():
        return any((p / 'cgroup.events').exists() and
                   'populated 1' in (p / 'cgroup.events').read_text()
                   for p in groups.glob('ws-*'))

    def set_depth(value):
        subprocess.run(['sudo', 'tee', '--', str(depth)], input=value,
                       text=True, capture_output=True, check=True, timeout=10)

    controller = pid()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            active = pool.submit(proof.execute, image, 'post_submit', 'sleep',
                                 expected='deadline_exceeded', deadline_ms=10000)
            wait_until(running, 'unrelated workload did not start')
            proof.execute(image, 'pre_submit', 'pass')
            if active.done() or not running():
                raise AssertionError('parallel capacity control did not overlap unrelated work')
            for case in ('lease_create_denied', 'cgroup_create_denied'):
                try:
                    if case == 'lease_create_denied':
                        leases.chmod(0o500)
                    else:
                        set_depth('0')
                    envelope = proof.request(image, 'pre_submit', 'pass')
                    response = exchange(config['socket_path'], envelope)
                    result = response['result']
                    if (result['infrastructure_failure_code'] != 'implementation_unavailable'
                            or response['isolation'] is not None or pid() != controller
                            or not running()):
                        raise AssertionError((case, response))
                    print(json.dumps({'case': case, 'controller_unchanged': True,
                                      'unrelated_work_running': True}), flush=True)
                finally:
                    leases.chmod(original_mode)
                    set_depth(original_depth)
            active.result()
        proof.execute(image, 'pre_submit', 'pass')
        if pid() != controller or list(leases.iterdir()) or list(groups.glob('ws-*')):
            raise AssertionError('controller changed or capacity remained occupied')
        print(json.dumps({'creation_failures': 'recoverable', 'cleanup': 'confirmed'}), flush=True)
    finally:
        leases.chmod(original_mode)
        set_depth(original_depth)
        proof.close()


if __name__ == '__main__':
    main()
