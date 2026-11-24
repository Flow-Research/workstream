"""Destructive proof commands reject foreign units and unsafe control files."""

import hashlib
import json
from contextlib import nullcontext
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.pilot04_external_checker_runtime.public_fault_files import (  # noqa: E402
    PrivateControlDirectory,
    private_path,
)
from experiments.pilot04_external_checker_runtime import public_node_faults as faults  # noqa: E402
from experiments.pilot04_external_checker_runtime.public_node_faults import validate_node  # noqa: E402


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


class PrivateFaultControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='.ws-proof-', dir=Path.home())
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_private_control_roundtrip_rejects_links_and_mode_widening(self):
        control = PrivateControlDirectory(self.root)
        self.addCleanup(control.close)
        control.write('request', {'action': 'clear'})
        self.assertEqual(control.read('request'), {'action': 'clear'})
        (self.root / 'alias').symlink_to(self.root / 'request')
        with self.assertRaises(OSError):
            control.read('alias')
        (self.root / 'request').chmod(0o644)
        with self.assertRaises(ValueError):
            control.read('request')
        with self.assertRaises(ValueError):
            control.write('../escaped', {})
        self.assertFalse((self.root.parent / 'escaped').exists())

    def test_preexisting_broad_or_aliased_control_directory_is_refused(self):
        self.root.chmod(0o777)
        with self.assertRaises(ValueError):
            PrivateControlDirectory(self.root)
        self.root.chmod(0o700)
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            PrivateControlDirectory(alias)

    def test_root_sticky_ancestor_requires_private_anchor_and_rejects_foreign_parent(self):
        with tempfile.TemporaryDirectory(prefix='ws-sticky-proof-', dir='/tmp') as name:
            directory = Path(name)
            private_path(directory, 0o700, directory=True)
            directory.chmod(0o755)
            with self.assertRaises(ValueError):
                private_path(directory, 0o700, directory=True)
        parent = self.root / 'parent'
        parent.mkdir(mode=0o700)
        directory = parent / 'control'
        directory.mkdir(mode=0o700)
        parent.chmod(0o777)
        with self.assertRaises(ValueError):
            PrivateControlDirectory(directory)
        parent.chmod(0o755)
        original = Path.lstat

        def foreign(path):
            info = original(path)
            if path == parent:
                fields = list(info)
                fields[4] = os.getuid() + 20000
                return os.stat_result(fields)
            return info

        with patch.object(Path, 'lstat', foreign):
            with self.assertRaises(ValueError):
                PrivateControlDirectory(directory)
        parent.chmod(0o1777)
        with patch.object(Path, 'lstat', foreign):
            with self.assertRaises(ValueError):
                PrivateControlDirectory(directory)

    def test_control_hardlinks_and_foreign_bindings_are_refused(self):
        control = PrivateControlDirectory(self.root)
        self.addCleanup(control.close)
        control.write('original', {'safe': True})
        os.link(self.root / 'original', self.root / 'linked')
        with self.assertRaises(ValueError):
            control.read('linked')
        with self.assertRaises(ValueError):
            control.write('original', {})
        self.assertEqual(json.loads((self.root / 'original').read_text()), {'safe': True})
        control.write('runtime-controls.json', {'root': '/unrelated', 'uid': 10002, 'gid': 10002})
        with self.assertRaises(ValueError):
            faults.runtime_control_root(self.root)

    def test_control_fifo_is_refused_without_waiting_for_a_writer(self):
        os.mkfifo(self.root / 'pipe', 0o600)
        program = (
            'import sys; from experiments.pilot04_external_checker_runtime.public_fault_files '
            'import PrivateControlDirectory; c=PrivateControlDirectory(sys.argv[1]); '
            '\ntry: c.read("pipe")\nexcept ValueError: pass\nelse: raise RuntimeError("FIFO accepted")'
            '\nfinally: c.close()\n'
        )
        result = subprocess.run([sys.executable, '-c', program, str(self.root)], cwd=ROOT,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_hosted_config_writes_preserve_readonly_custody_and_reject_replacement(self):
        directory = self.root / 'runtime-config'
        directory.mkdir(mode=0o700)
        config = directory / 'service.json'
        config.write_bytes(b'original')
        write_descriptor = os.open(config, os.O_WRONLY)
        self.addCleanup(os.close, write_descriptor)
        config.chmod(0o400)
        actual_root = os.getuid() == 0
        uid, gid = (10001, 10001) if actual_root else (os.getuid(), os.getgid())
        if actual_root:
            os.chown(directory, uid, gid)
            os.chown(config, uid, gid)
        # EC2 runs this case as the root operator with real UID10001 files.
        # The local unprivileged run retains the real inode/mode refusal probes.
        identity_context = nullcontext() if actual_root else patch.object(
            faults, '_config_identity', return_value=(uid, gid, 0o400))
        original_open = os.open

        def operator_open(path, flags, *args, **kwargs):
            if path == config and flags & os.O_ACCMODE == os.O_WRONLY:
                # A retained descriptor supplies root's write authority locally;
                # production inode/mode/owner checks still inspect the real file.
                return os.dup(write_descriptor)
            return original_open(path, flags, *args, **kwargs)

        open_context = nullcontext() if actual_root else patch.object(os, 'open', operator_open)
        with identity_context, open_context:
            original, identity = faults._read_config(config, True)
            faults.write_node_config(config, b'changed', identity, hosted_runtime=True)
            info = config.stat()
            self.assertEqual((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)), (uid, gid, 0o400))
            self.assertEqual((info.st_dev, info.st_ino), identity)
            faults.write_node_config(config, original, identity, hosted_runtime=True)
            self.assertEqual(config.read_bytes(), b'original')
            config.chmod(0o600)
            with self.assertRaises(ValueError):
                faults.write_node_config(config, b'bad', identity, hosted_runtime=True)
            config.chmod(0o400)
            config.rename(directory / 'retained-original')
            config.write_bytes(b'replacement must survive')
            config.chmod(0o400)
            if actual_root:
                os.chown(config, uid, gid)
            with self.assertRaisesRegex(ValueError, 'custody changed'):
                faults.write_node_config(config, b'bad', identity, hosted_runtime=True)
            self.assertEqual(config.read_bytes(), b'replacement must survive')
            self.assertEqual((directory / 'retained-original').read_bytes(), b'original')

    def test_hosted_runtime_identity_is_fixed_and_drops_supplementary_groups(self):
        with patch.object(os, 'getuid', return_value=1000):
            with self.assertRaises(ValueError):
                faults._config_identity(True)
        with patch.object(os, 'getuid', return_value=0):
            self.assertEqual(faults._config_identity(True), (10001, 10001, 0o400))
            with self.assertRaises(ValueError):
                faults._runtime_user((10002, 10002))
            with patch.object(subprocess, 'check_output', return_value='{}') as command:
                faults.runtime({'smol': {'binary': '/pinned/smol', 'home': '/private/home'}},
                               'machine', 'ls', '--json', identity=(10001, 10001))
                self.assertEqual({key: command.call_args.kwargs[key]
                                  for key in ('user', 'group', 'extra_groups')},
                                 {'user': 10001, 'group': 10001, 'extra_groups': []})

    def test_runtime_sibling_binding_has_distinct_operator_and_runtime_custody(self):
        runtime = self.root.with_name(self.root.name + '-runtime')
        runtime.mkdir(mode=0o700)
        self.addCleanup(runtime.rmdir)
        control = PrivateControlDirectory(self.root)
        self.addCleanup(control.close)
        control.write('runtime-controls.json', {'root': str(runtime), 'uid': 10001, 'gid': 10001})
        original_getuid, original_getgid = os.getuid, os.getgid
        # Validate the expected-owner call independently of local chown authority.
        original_path = faults.private_path

        def validate(path, mode, **kwargs):
            if path == runtime:
                self.assertEqual(kwargs, {'directory': True, 'uid': 10001, 'gid': 10001})
                return
            return original_path(path, mode, **kwargs)

        with patch.object(faults, '_operator_controls', return_value=control), \
                patch.object(control, 'close'), patch.object(os, 'getuid', return_value=0), \
                patch.object(faults, 'private_path', validate):
            # Control.read still checks the actual local operator identity.
            self.assertEqual(faults.runtime_control_root(self.root), runtime)
        self.assertEqual(os.getuid(), original_getuid())
        self.assertEqual(os.getgid(), original_getgid())

    def test_hosted_wrapper_exec_requires_traversable_sibling_parent(self):
        """A real user process must read wrapper settings and exec through ancestry."""
        source = (
            ROOT
            / "experiments/pilot04_external_checker_runtime/public_runtime_wrapper.py"
        )
        binary = self.root / "smol-version"
        binary.write_text('#!/bin/sh\nprintf "smolvm 1.31.4\\n"\n')
        binary.chmod(0o700)

        def prepare(parent):
            runtime = parent / "workstream-pre-launch-fault-runtime"
            runtime.mkdir(mode=0o700)
            wrapper = runtime / "runtime-wrapper"
            wrapper.write_bytes(source.read_bytes())
            wrapper.chmod(0o700)
            wrapper.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "binary": str(binary),
                        "project_archive": "/unused",
                        "mode": "/unused",
                        "trace": "/unused",
                        "unit": "unused",
                        "socket": "/unused",
                    }
                )
            )
            return wrapper

        old_parent = self.root / "operator-private"
        old_parent.mkdir(mode=0o700)
        new_wrapper = prepare(self.root)
        old_wrapper = prepare(old_parent)
        with patch.object(faults, "_runtime_user", return_value={}):
            self.assertIsNone(
                faults._check_hosted_wrapper_execution(new_wrapper, str(self.root))
            )
            old_parent.chmod(0o000)
            try:
                with self.assertRaises((OSError, subprocess.CalledProcessError)):
                    faults._check_hosted_wrapper_execution(old_wrapper, str(self.root))
            finally:
                old_parent.chmod(0o700)

    def test_launch_trace_rejects_extra_execution_and_reset_deadline(self):
        trace = self.root / 'runtime-trace.jsonl'
        lease = {'epoch': 'original', 'expires_ms': 1000}
        rows = [{'operation': operation, 'name': name, 'project': True, 'lease': dict(lease, name=name, lifetime_ms=900 if name == 'first' else 650)}
                for name in ('first', 'second') for operation in ('create', 'start', 'delete')]
        rows.insert(5, {'operation': 'exec', 'name': 'second', 'project': True, 'lease': dict(lease)})
        def write(values):
            trace.write_text(''.join(json.dumps(row) + '\n' for row in values))
        write(rows)
        self.assertEqual(faults.assert_launches(self.root, 0, creates=2, executions=1), ['first', 'second'])
        write(rows + [{'operation': 'exec', 'name': 'hidden-second-checker', 'project': True, 'lease': lease}])
        with self.assertRaisesRegex(RuntimeError, 'retried an invoked guest'):
            faults.assert_launches(self.root, 0, creates=2, executions=1)
        early_execution = [row for row in rows if row['operation'] != 'exec']
        early_execution.insert(2, {'operation': 'exec', 'name': 'first', 'project': True, 'lease': dict(lease)})
        write(early_execution)
        with self.assertRaisesRegex(RuntimeError, 'retried after invocation'):
            faults.assert_launches(self.root, 0, creates=2, executions=1)
        write(rows + [rows[-1]])
        with self.assertRaisesRegex(RuntimeError, 'exact machine sequencing'):
            faults.assert_launches(self.root, 0, creates=2, executions=1)
        missing = [dict(row, lease=None) if row['name'] == 'second' else row for row in rows]
        write(missing)
        with self.assertRaisesRegex(RuntimeError, 'lacks exact lease evidence'):
            faults.assert_launches(self.root, 0, creates=2, executions=1)
        rounded = [dict(row, lease=dict(row['lease'], expires_ms=1001)) if row['name'] == 'second' else row for row in rows]
        write(rounded)
        self.assertEqual(faults.assert_launches(self.root, 0, creates=2, executions=1), ['first', 'second'])
        for reset_lifetime in (900, 1200):
            reset = [dict(row, lease=dict(row['lease'], lifetime_ms=reset_lifetime))
                     if row['name'] == 'second' else row for row in rows]
            write(reset)
            with self.assertRaisesRegex(RuntimeError, 'original lease epoch/deadline'):
                faults.assert_launches(self.root, 0, creates=2, executions=1)
        rows[3]['lease']['expires_ms'] += 1000
        write(rows)
        with self.assertRaisesRegex(RuntimeError, 'original lease epoch/deadline'):
            faults.assert_launches(self.root, 0, creates=2, executions=1)

    def test_foreign_fixture_cleanup_is_exact_and_requires_disk_absence(self):
        fixture = faults.ForeignControl.__new__(faults.ForeignControl)
        fixture.name = 'owned-proof-sentinel'
        fixture.config = {'smol': {'home': str(self.root)}}
        fixture.process = None
        fixture.group = self.root / 'group'
        fixture.created = True
        matching = [{'name': fixture.name, 'labels': {'workstream.external-checker-owner': 'foreign-control'}}]
        with patch.object(fixture, 'command') as command, patch.object(faults, 'runtime', side_effect=[matching, []]):
            receipt = fixture.close()
            command.assert_called_once_with('machine', 'delete', '--name', fixture.name, '--force')
            self.assertTrue(receipt['disk_absent'])
        disk = self.root / '.cache/smolvm/vms' / hashlib.sha256(fixture.name.encode()).hexdigest()[:16]
        disk.mkdir(parents=True)
        with patch.object(fixture, 'command'), patch.object(faults, 'runtime', side_effect=[matching, []]):
            with self.assertRaisesRegex(RuntimeError, 'cleanup is incomplete'):
                fixture.close()

    def test_busy_node_refused_before_control_or_config_mutation(self):
        config_path = self.root / 'service.json'
        image_digest = 'sha256:' + 'a' * 64
        original = json.dumps({'cache': [{'platform_manifest_digest': image_digest}]}).encode()
        config_path.write_bytes(original)
        config_path.chmod(0o600)
        control_root = self.root / 'control'
        for resource in ('leases', 'machines', 'disks', 'cgroups'):
            with self.subTest(resource=resource), patch.object(faults, 'validate_node'), \
                    patch.object(faults, 'owned_resources', return_value={resource: ['active']}), \
                    patch.object(faults, 'PrivateControlDirectory') as controls, \
                    patch.object(faults, 'ForeignControl') as foreign, \
                    patch.object(subprocess, 'run') as commands:
                with self.assertRaisesRegex(RuntimeError, 'node must be drained'):
                    faults.serve(config_path, control_root, 'owned.service', self.root / 'manifest',
                                 run_id='2f662dee-328c-4df5-8b8e-e9f934360654',
                                 maximum_seconds=30, image_digest=image_digest)
                controls.assert_not_called()
                foreign.assert_not_called()
                commands.assert_not_called()
                self.assertFalse(control_root.exists())
                self.assertEqual(config_path.read_bytes(), original)

    def test_busy_node_guard_survives_optimized_python(self):
        result = subprocess.run([
            sys.executable, '-O', '-m', 'unittest',
            'scripts.test_public_smol_proof.PrivateFaultControls.'
            'test_busy_node_refused_before_control_or_config_mutation',
        ], cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_live_unit_binding_rejects_foreign_unit_config_and_binary(self):
        binary, guest, smol = [self.root / name for name in ('service', 'guest', 'smol')]
        for path in (binary, guest, smol):
            path.write_bytes(path.name.encode())
        socket_root = self.root / 'socket'
        socket_root.mkdir(mode=0o700)
        owner = socket_root / '.workstream-checker-owner'
        owner.write_text('a' * 64)
        owner.chmod(0o600)
        config_path = self.root / 'service.json'
        config = {'socket_path': str(socket_root / 'checker.sock'), 'smol': {
            'binary': str(smol), 'guest_binary': str(guest), 'maximum_parallel': 1,
            'cgroup_root': '/sys/fs/cgroup/system.slice/ws-proof.service'}}
        config_path.write_text(json.dumps(config))
        config_path.chmod(0o600)
        manifest = {'unit': 'ws-proof.service', 'config': str(config_path),
                    'socket': config['socket_path'], 'executable': str(binary), 'owner': 'a' * 64,
                    'config_sha256': digest(config_path), 'node_config': config,
                    'service_sha256': digest(binary), 'smol_sha256': digest(smol), 'guest_sha256': digest(guest),
                    'wrapper_sha256': digest(ROOT / 'experiments/pilot04_external_checker_runtime/public_runtime_wrapper.py'),
                    'source_tree': 'independent-source'}
        manifest_path = self.root / 'custody.json'
        manifest_path.write_text(json.dumps(manifest))
        manifest_path.chmod(0o600)
        original_resolve, original_read = Path.resolve, Path.read_bytes
        argv = [str(binary), str(config_path)]

        def resolve(path, *args, **kwargs):
            return binary if str(path) == '/proc/123456/exe' else original_resolve(path, *args, **kwargs)

        def read(path):
            return ('\0'.join(argv) + '\0').encode() if str(path) == '/proc/123456/cmdline' else original_read(path)

        def output(command, **kwargs):
            if command[0] == 'systemctl':
                return 'MainPID=123456\nControlGroup=/system.slice/ws-proof.service\n'
            self.assertEqual(command[:2], ['git', 'rev-parse'])
            return 'independent-source\n'

        with patch.object(Path, 'resolve', resolve), patch.object(Path, 'read_bytes', read), patch.object(subprocess, 'check_output', output):
            self.assertEqual(validate_node(config_path, config, 'ws-proof.service', manifest_path), manifest)
            with self.assertRaises(ValueError):
                validate_node(config_path, config, 'foreign.service', manifest_path)
            argv[1] = str(self.root / 'foreign-config.json')
            with self.assertRaises(ValueError):
                validate_node(config_path, config, 'ws-proof.service', manifest_path)
            argv[1] = str(config_path)
            config['smol']['maximum_parallel'] = 2
            config_path.write_text(json.dumps(config))
            manifest['node_config'] = config
            manifest['config_sha256'] = digest(config_path)
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'one-slot'):
                validate_node(config_path, config, 'ws-proof.service', manifest_path)
            config['smol']['maximum_parallel'] = 1
            config_path.write_text(json.dumps(config))
            manifest['node_config'] = config
            manifest['config_sha256'] = digest(config_path)
            manifest_path.write_text(json.dumps(manifest))
            binary.write_bytes(b'substituted-controller')
            with self.assertRaises(ValueError):
                validate_node(config_path, config, 'ws-proof.service', manifest_path)


if __name__ == '__main__':
    unittest.main()
