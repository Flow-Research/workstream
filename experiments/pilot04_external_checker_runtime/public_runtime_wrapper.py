#!/usr/bin/python3
"""Exact project-image fault interposer; trusted intake remains available."""

import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

settings = json.loads(Path(__file__).with_suffix('.json').read_text())
arguments = sys.argv[1:]
if len(arguments) >= 2 and arguments[0] == 'machine':
    operation = arguments[1]
    name = arguments[arguments.index('--name') + 1] if '--name' in arguments else None
    with Path(settings['trace']).open('a+') as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.seek(0)
        prior = [json.loads(line) for line in output]
        project = (arguments[arguments.index('--image') + 1] == settings['project_archive']
                   if operation == 'create' else any(
                       event['name'] == name and event['project'] for event in prior))
        if operation in {'create', 'start', 'exec', 'delete'}:
            lease_path = Path(settings['socket']).parent / 'smol-leases' / (str(name) + '.json')
            lease = json.loads(lease_path.read_text()) if lease_path.exists() else None
            output.write(json.dumps({'operation': operation, 'name': name, 'project': project,
                                     'monotonic': time.monotonic(), 'wall_ms': time.time_ns() // 1_000_000,
                                     'lease': {k: lease[k] for k in ('name', 'owner', 'epoch', 'expires_ms', 'lifetime_ms')}
                                     if lease else None}) + '\n')
            output.flush()
            os.fsync(output.fileno())
    if project and operation in {'start', 'exec'}:
        with Path(settings['mode']).open('r+') as state:
            fcntl.flock(state, fcntl.LOCK_EX)
            mode = json.load(state)
            if operation == 'start' and mode['failures']:
                mode['failures'] = max(-1, mode['failures'] - 1)
                state.seek(0)
                json.dump(mode, state)
                state.truncate()
                sys.exit(93)
            if operation == 'exec' and mode['kill']:
                mode['kill'] = False
                state.seek(0)
                json.dump(mode, state)
                state.truncate()
                state.flush()
                os.fsync(state.fileno())
                pid = int(subprocess.check_output(
                    ['systemctl', 'show', settings['unit'], '-p', 'MainPID', '--value'], text=True))
                child = subprocess.Popen([settings['binary'], *arguments])
                # The sleeping project fixture has begun execution before controller loss.
                def kill_controller():
                    time.sleep(1)
                    if child.poll() is not None:
                        return
                    with Path(settings['trace']).open('a') as proof:
                        fcntl.flock(proof, fcntl.LOCK_EX)
                        proof.write(json.dumps({'operation': 'controller_kill', 'name': name,
                                                'project': True, 'controller_pid': pid,
                                                'monotonic': time.monotonic()}) + '\n')
                        proof.flush()
                        os.fsync(proof.fileno())
                    os.kill(pid, signal.SIGKILL)
                threading.Thread(target=kill_controller, daemon=True).start()
                sys.exit(child.wait())
os.execv(settings['binary'], [settings['binary'], *arguments])
