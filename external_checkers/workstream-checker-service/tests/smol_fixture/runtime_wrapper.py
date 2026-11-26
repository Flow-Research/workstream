#!/usr/bin/python3
"""Test-only runtime interposer: exact attempt telemetry and bounded faults."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def observe_pre_exit(binary, arguments, trace, name):
    # The trusted guest emits the fixed diagnostic on the effective project-stage deadline.
    # Forward stderr as usual. Retain only one bounded, classified observation.
    diagnostic = b'workstream guest bootstrap failed: project deadline exceeded'
    captured = bytearray()
    environment = os.environ | {'WORKSTREAM_PRE_QUALIFICATION_PRIVATE_CANARY': 'test-only'}
    with subprocess.Popen([binary, *arguments], stderr=subprocess.PIPE, env=environment) as child:
        while chunk := child.stderr.read1(4096):
            captured.extend(chunk[:max(0, 16384 - len(captured))])
            sys.stderr.buffer.write(chunk)
            sys.stderr.buffer.flush()
        code = child.wait()
    limit_unenforced = any(
        message in captured
        for message in (
            b'guest memory ceiling was not enforced',
            b'guest output ceiling was not enforced',
        )
    )
    with trace.open('a') as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.write(json.dumps({
            'operation': 'pre_exit', 'name': name, 'exit_code': code,
            'project_deadline_exceeded': diagnostic in captured.splitlines(),
            'guest_limit_unenforced': limit_unenforced,
        }) + '\n')
        output.flush()
        os.fsync(output.fileno())
    return code


settings = json.loads(Path(__file__).with_suffix('.json').read_text())
arguments = sys.argv[1:]
if len(arguments) >= 2 and arguments[0] == 'machine':
    operation = arguments[1]
    name = arguments[arguments.index('--name') + 1] if '--name' in arguments else None
    trace = Path(settings['trace'])
    source_pre = operation == 'exec' and '--pre-limits' in arguments
    if operation in {'create', 'start', 'exec', 'delete'}:
        with trace.open('a+') as output:
            fcntl.flock(output, fcntl.LOCK_EX)
            output.seek(0)
            prior = [json.loads(line)['name'] for line in output if json.loads(line)['operation'] == 'create']
            event = {'operation': operation, 'name': name}
            if operation == 'exec':
                event['source_pre'] = source_pre
            if operation == 'create':
                rows = json.loads(subprocess.check_output([settings['binary'], 'machine', 'ls', '--json']))
                event['prior_resources'] = [row['name'] for row in rows if row['name'] in prior]
                for previous in prior:
                    disk = Path(os.environ['HOME']) / '.cache/smolvm/vms' / hashlib.sha256(previous.encode()).hexdigest()[:16]
                    if (Path(settings['cgroups']) / previous).exists() or disk.exists():
                        event['prior_resources'].append(previous)
            output.write(json.dumps(event) + '\n')
            output.flush()
            os.fsync(output.fileno())
        if operation == 'start':
            mode = Path(settings['mode'])
            with mode.open('r+') as state:
                fcntl.flock(state, fcntl.LOCK_EX)
                remaining = int(state.read())
                if remaining:
                    state.seek(0)
                    state.write(str(max(-1, remaining - 1)))
                    state.truncate()
                    state.flush()
                    os.fsync(state.fileno())
                    sys.exit(93)
        if operation == 'delete' and (
            Path(settings['delete_fault']).exists()
            or (
                settings.get('fault_completed_pre_delete') is True
                and next(
                    (row['name'] for row in
                     (json.loads(line) for line in trace.read_text().splitlines())
                     if row['operation'] == 'pre_exit' and row['exit_code'] == 0),
                    None,
                ) == name
            )
        ):
            sys.exit(93)
        if source_pre and settings.get('observe_pre_exit') is True:
            sys.exit(observe_pre_exit(settings['binary'], arguments, trace, name))
os.execv(settings['binary'], [settings['binary'], *arguments])
