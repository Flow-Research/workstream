"""Opt-in destructive recovery proof for an isolated Smol test node only.

Requires authority over the named systemd unit. Never target a shared production
node: this intentionally kills its controller and injects a deletion failure.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import sqlite3
import stat
import struct
import subprocess
import time
import tempfile
import zipfile

from smol_runtime import Proof, canonical, exchange, smol_vm_inventory


def wait_until(predicate, description, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(description)


class NestedTrialRecovery:
    """Three opt-in owner failures using the composition's real trial custody."""

    CASES = {"caller_disconnect", "child_death", "controller_death"}
    MARKER = b"workstream-owned-nested-trial-ready-v1\n"

    def __init__(self, case):
        if case not in self.CASES:
            raise ValueError("unsupported nested recovery case")
        self.case = case
        self.completed = False
        self.replacement = None
        self.killed_controller = None
        self.pending_create_observations = 0
        self.cache_lock_identity = None
        self.last_inventory = None

    @staticmethod
    def inventory_rows(value):
        rows = value.get("machines") if isinstance(value, dict) else value
        assert isinstance(rows, list), "invalid child VM inventory shape"
        return rows

    @classmethod
    def child_inventory(cls, value, name):
        matches = [row for row in cls.inventory_rows(value)
                   if isinstance(row, dict) and row.get("name") == name]
        assert len(matches) <= 1, "duplicate exact child VM identity"
        return matches[0] if matches else None

    @staticmethod
    def validate_child(machine, owner):
        assert machine["labels"]["workstream.external-checker-owner"] == owner
        assert machine["network"] is False

    @staticmethod
    def inventory_facts(value, name, owner, home, home_identity, raw):
        # Fixed field/row/string bounds; never retain argv or guest payloads.
        def fact(item):
            if isinstance(item, str):
                return item[:256]
            return item if item is None or type(item) in (int, bool) else type(item).__name__
        rows = value.get("machines") if isinstance(value, dict) else value
        observed = []
        for row in rows[:8] if isinstance(rows, list) else ():
            if not isinstance(row, dict):
                observed.append({"row_type": type(row).__name__})
                continue
            labels = row.get("labels")
            observed.append({key: fact(row.get(key)) for key in ("name", "state", "pid", "network")} | {
                "owner": fact(labels.get("workstream.external-checker-owner")) if isinstance(labels, dict) else None,
            })
        return {"expected_name": name, "expected_owner": owner,
                "child_home": str(home), "child_home_identity": home_identity,
                "row_count": len(rows) if isinstance(rows, list) else None,
                "inventory_type": type(value).__name__, "rows_type": type(rows).__name__,
                "observed_rows": observed,
                "raw_inventory_sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}

    def retain_inventory_failure(self):
        if self.last_inventory is None:
            return
        destination = self.service_root.parent / "inventory-failure.json"
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(self.last_inventory, output, sort_keys=True)

    def archive_factory(self, original):
        def archive(evidence_path, project_id):
            # Only this recovery submission changes. A finite wait gives the
            # observer a deterministic reached-workload boundary, then fails
            # closed if no fault is injected. No production image is modified.
            data = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(original(evidence_path, project_id))) as source:
                with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as target:
                    for entry in source.infolist():
                        body = source.read(entry.filename)
                        if entry.filename == "tools/qualification-status":
                            body = (
                                b"#!/bin/sh\nset -eu\n"
                                b"grep -Eq '^Seccomp:[[:space:]]+2$' /proc/self/status\n"
                                b"printf 'workstream-owned-nested-trial-ready-v1\\n' "
                                b"> /workspace/.trial-recovery-ready\n"
                                b"sleep 20\nexit 77\n"
                            )
                        target.writestr(entry, body)
            return data.getvalue()
        return archive

    @staticmethod
    def snapshot_inventory(home, name):
        """Never open SQLite on the target: even a read-only URI can write SHM."""
        directory = home / ".local/share/smolvm/server"
        descriptors = []
        bodies = {}
        maximum = 8 * 1024 * 1024
        signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        try:
            for suffix in ("", "-wal"):
                path = directory / ("smolvm.db" + suffix)
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                except FileNotFoundError:
                    if suffix:
                        continue
                    return None
                descriptors.append((path, fd, os.fstat(fd)))
            for path, fd, before in descriptors:
                assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                assert (before.st_uid, before.st_gid) == (os.geteuid(), os.getegid())
                assert stat.S_IMODE(before.st_mode) == 0o600 and before.st_size <= maximum
                body = bytearray()
                while len(body) <= before.st_size:
                    chunk = os.read(fd, min(65536, before.st_size + 1 - len(body)))
                    if not chunk:
                        break
                    body.extend(chunk)
                if len(body) != before.st_size:
                    return None
                maximum -= len(body)
                bodies[path.name] = bytes(body)
            for path, fd, before in descriptors:
                if signature(os.fstat(fd)) != signature(before) or signature(path.lstat()) != signature(before):
                    return None
            if "smolvm.db-wal" not in bodies and (directory / "smolvm.db-wal").exists():
                return None
            with tempfile.TemporaryDirectory(prefix="ws-observer-db-") as copied:
                target = Path(copied) / "smolvm.db"
                for filename, body in bodies.items():
                    (Path(copied) / filename).write_bytes(body)
                # WAL replay and any SHM creation happen only in our private copy.
                with closing(sqlite3.connect(target, timeout=0.1)) as connection:
                    deadline = time.monotonic() + 1
                    connection.set_progress_handler(lambda: time.monotonic() >= deadline, 1000)
                    selected = connection.execute("SELECT name,data FROM vms WHERE name=?", (name,)).fetchmany(2)
                    assert len(selected) <= 1, "duplicate exact child VM identity"
                    others = connection.execute("SELECT name,data FROM vms WHERE name!=? ORDER BY name LIMIT 7", (name,)).fetchall()
                    rows = []
                    for key, data in selected + others:
                        row = json.loads(data)
                        assert isinstance(row, dict) and row.get("name") == key
                        rows.append(row)
            raw = b"".join(len(body).to_bytes(8, "big") + body for body in bodies.values())
            return rows, raw
        except (FileNotFoundError, sqlite3.DatabaseError):
            return None  # Retired or inconsistent copies stay within the original deadline.
        finally:
            for _, fd, _ in descriptors:
                os.close(fd)

    @staticmethod
    def agent_marker(home, name):
        path = home / ".cache/smolvm/vms" / hashlib.sha256(name.encode()).hexdigest()[:16] / "agent.sock"
        script = (
            "for p in $(cat /sys/fs/cgroup/workstream-trial/workload/cgroup.procs 2>/dev/null); do "
            "grep -Eq '^Seccomp:[[:space:]]+2$' /proc/$p/status 2>/dev/null || continue; "
            "f=/proc/$p/root/workspace/.trial-recovery-ready; "
            "test -r $f || continue; "
            "test \"$(cat $f)\" = workstream-owned-nested-trial-ready-v1 || exit 41; "
            "printf 'nested-workload-ready:%s\\n' $p; exit 0; done; exit 43"
        )
        request = {"method": "vm_exec", "command": ["/bin/sh", "-c", script], "env": [],
                   "workdir": None, "timeout_ms": 1000, "interactive": False, "tty": False,
                   "background": False, "stdin_data": None}
        received = 0
        try:
            before = path.lstat()
            assert stat.S_ISSOCK(before.st_mode) and before.st_nlink == 1
            assert (before.st_uid, before.st_gid) == (os.geteuid(), os.getegid())
            deadline = time.monotonic() + 2
            with socket.socket(socket.AF_UNIX) as channel:
                def budget():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("marker agent absolute deadline")
                    channel.settimeout(remaining)
                def exact(size):
                    nonlocal received
                    data = b""
                    while len(data) < size:
                        budget()
                        chunk = channel.recv(size - len(data))
                        if not chunk:
                            raise EOFError("truncated marker agent frame")
                        received += len(chunk)
                        data += chunk
                    return data
                budget();channel.connect(str(path))
                raw = canonical(request)
                budget();channel.sendall(struct.pack(">I", len(raw)) + raw)
                size = struct.unpack(">I", exact(4))[0]
                assert 0 < size <= 65536, "unbounded marker agent response"
                response = json.loads(exact(size))
            after = path.lstat()
            assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
            assert isinstance(response, dict) and set(response) in (
                {"status", "exit_code", "stdout", "stderr"},
                {"status", "exit_code", "stdout", "stderr", "trace_id"},
            )
            assert response["status"] == "completed" and type(response["exit_code"]) is int
            if "trace_id" in response:
                assert response["trace_id"] is None or (isinstance(response["trace_id"], str) and len(response["trace_id"]) <= 256)
            stdout = base64.b64decode(response["stdout"], validate=True)
            stderr = base64.b64decode(response["stderr"], validate=True)
            assert len(stdout) <= 4096 and not stderr
            if response["exit_code"] == 43:
                assert not stdout
                return None
            assert response["exit_code"] == 0
            return stdout
        except TimeoutError:
            if received:
                raise  # A partial active frame must not become ordinary pending work.
            return None
        except (FileNotFoundError, ConnectionRefusedError):
            return None

    @staticmethod
    def private_directory(path):
        identity = path.lstat()
        assert path.resolve() == path and stat.S_ISDIR(identity.st_mode)
        assert stat.S_IMODE(identity.st_mode) == 0o700
        assert (identity.st_uid, identity.st_gid) == (os.geteuid(), os.getegid())
        return {"device": identity.st_dev, "inode": identity.st_ino}

    @staticmethod
    def process_identity(pid, executable):
        assert type(pid) is int and pid > 1
        process = Path("/proc") / str(pid)
        assert (process / "exe").resolve(strict=True) == executable
        assert process.stat().st_uid == os.geteuid()
        # /proc stat's parenthesized comm may contain spaces or parentheses.
        start = int((process / "stat").read_text().rpartition(") ")[2].split()[19])
        return {"pid": pid, "start_ticks": start, "executable": str(executable)}

    @staticmethod
    def vmm_identity(pid, group, expected=None):
        # Smol deliberately makes the VMM non-dumpable: exe readlink is denied.
        # The exact lease/DB selection supplies pinned launch provenance; status,
        # start ticks and the private cgroup bind the live process without ptrace.
        assert type(pid) is int and pid > 1
        assert group.is_absolute() and str(group).startswith("/sys/fs/cgroup/")
        process = Path("/proc") / str(pid)
        status = dict(line.split(":", 1) for line in (process / "status").read_text().splitlines()
                      if ":" in line)
        uids = [int(value) for value in status["Uid"].split()]
        gids = [int(value) for value in status["Gid"].split()]
        assert uids == [os.geteuid()] * 4 and gids == [os.getegid()] * 4
        raw = (process / "stat").read_text()
        assert int(raw.split(" (", 1)[0]) == pid
        fields = raw.rpartition(") ")[2].split()
        if fields[0] == "Z":
            raise ProcessLookupError("observed VMM already retired")
        start = int(fields[19])
        assert start > 0
        membership = "0::" + str(group).removeprefix("/sys/fs/cgroup")
        assert (process / "cgroup").read_text().strip() == membership
        identity = {"pid": pid, "start_ticks": start, "uids": uids, "gids": gids,
                    "cgroup": membership, "provenance": "pinned_owned_lease_and_readonly_db"}
        assert expected is None or identity == expected
        return identity

    @staticmethod
    def observation_retired(lease, pid):
        if not lease.exists():
            return True
        try:
            state = (Path("/proc") / str(pid) / "stat").read_text().rpartition(") ")[2].split()[0]
            return state == "Z"
        except FileNotFoundError:
            return True

    def marker(self):
        if self.execution.done():
            raise AssertionError("execution ended before nested workload marker")
        owner = (self.service_root / ".workstream-checker-owner").read_text()
        assert len(owner) == 64 and all(c in "0123456789abcdef" for c in owner)
        leases = sorted(self.leases.iterdir())
        assert len(leases) <= 2, "unexpected additional active owner"
        for path in leases:
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                continue  # A prior ordinary/child operation finished between polls.
            with os.fdopen(descriptor, "rb") as source:
                identity = os.fstat(source.fileno())
                assert stat.S_ISREG(identity.st_mode) and identity.st_nlink == 1
                assert stat.S_IMODE(identity.st_mode) == 0o600
                assert (identity.st_uid, identity.st_gid) == (os.geteuid(), os.getegid())
                raw = source.read(65537)
                assert len(raw) <= 65536
            lease = json.loads(raw)
            assert lease["owner"] == owner and lease["root"] == str(self.leases)
            if lease["private_home_root"] is None:
                continue
            assert lease["private_home_root"] == str(self.child_root)
            name = lease["name"]
            assert len(name) == 35 and name.startswith("ws-")
            assert all(c in "0123456789abcdef" for c in name[3:])
            assert path == self.leases / (name + ".json")
            home = self.child_root / (name + ".home")
            assert lease["runtime"]["home"] == str(home)
            for key in ("binary", "binary_sha256", "guest_binary", "guest_sha256", "cgroup_root"):
                assert lease["runtime"][key] == self.config["smol"][key]
            try:
                home_identity = self.private_directory(home)
                snapshot = self.snapshot_inventory(home, name)
                if snapshot is None:
                    continue
                rows, inventory_bytes = snapshot
            except FileNotFoundError:
                continue
            self.last_inventory = self.inventory_facts(
                rows, name, owner, home, home_identity, inventory_bytes,
            )
            self.last_inventory["source"] = "bounded_nofollow_db_wal_snapshot_v1"
            machine = self.child_inventory(rows, name)
            if machine is None:
                self.pending_create_observations += 1
                continue
            self.validate_child(machine, owner)
            if machine["state"] != "running":
                continue
            try:
                group = self.groups / name
                vmm = self.vmm_identity(machine["pid"], group)
                observed = self.agent_marker(home, name)
                if observed is None:
                    continue
                self.vmm_identity(vmm["pid"], group, vmm)
                assert self.private_directory(home) == home_identity
                assert path.read_bytes() == raw and path.lstat().st_ino == identity.st_ino
                current = self.snapshot_inventory(home, name)
                assert current is not None
                selected = self.child_inventory(current[0], name)
                assert selected is not None and selected["pid"] == vmm["pid"]
                self.validate_child(selected, owner)
            except (FileNotFoundError, ProcessLookupError, EOFError, ConnectionResetError, BrokenPipeError, TimeoutError):
                if self.observation_retired(path, machine["pid"]):
                    continue
                raise
            assert observed.startswith(b"nested-workload-ready:") and observed.endswith(b"\n")
            workload_pid = int(observed.strip().split(b":")[1])
            self.reached = {
                "owner": owner, "lease_name": name,
                "lease_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "lease_device": identity.st_dev, "lease_inode": identity.st_ino,
                "child_home": str(home), "child_home_identity": home_identity,
                "vmm": vmm, "workload_pid_in_guest": workload_pid,
                "marker_sha256": "sha256:" + hashlib.sha256(self.MARKER).hexdigest(),
                "workload_seccomp_mode": 2, "inventory": self.last_inventory,
                "observer_transport": "copied_smolvm_db_and_fixed_agent_vm_exec_v1",
            }
            return True
        return False

    def physical_clean(self):
        vms = Path(self.config["smol"]["home"]) / ".cache/smolvm/vms"
        children, observed = smol_vm_inventory(vms)
        if children:
            return False
        if self.cache_lock_identity is not None:
            assert self.cache_lock_identity == observed, "engine cache lock identity changed"
        elif observed is not None:
            self.cache_lock_identity = observed
        return (
            not list(self.leases.iterdir())
            and not list(self.groups.glob("ws-*"))
            and not list(self.child_root.glob("ws-*.home"))
        )

    async def exercise(self, *, executor, harness, controller, service_binary,
                       config_path, config, service_log, intake, observations, creates):
        from sqlalchemy import select
        from app.interfaces.trusted_submission_intake import TrustedIntakePreparation
        from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
        from app.modules.artifacts.models import ArtifactBinding, ArtifactPutAttempt
        from app.modules.checkers.models import CheckerTrialEvidence
        from app.modules.model_usage.models import ModelUsageEffect

        self.config = config
        self.service_root = Path(config["socket_path"]).parent
        self.leases = self.service_root / "smol-leases"
        self.groups = Path(config["smol"]["cgroup_root"])
        self.child_root = Path(config["trial_runtime"]["child_home_root"])
        initial_child_identity = self.private_directory(self.child_root)
        controller_identity = self.process_identity(controller.pid, service_binary)
        self.controller = controller
        self.controller_identity = controller_identity
        assert self.physical_clean(), "recovery must start physically drained"
        self.execution = asyncio.create_task(executor.evaluate_post_submission(harness.request))
        result = None
        try:
            await asyncio.to_thread(wait_until, self.marker, "nested workload marker missing", 90)
            if self.case == "caller_disconnect":
                self.execution.cancel()  # Adapter finally closes its exact request socket.
            elif self.case == "child_death":
                victim = self.reached["vmm"]
                self.vmm_identity(victim["pid"], self.groups / self.reached["lease_name"], victim)
                os.kill(victim["pid"], signal.SIGKILL)
            else:
                assert self.process_identity(controller.pid, service_binary) == controller_identity
                self.killed_controller = controller.pid
                os.kill(controller.pid, signal.SIGKILL)
            done, _ = await asyncio.wait({self.execution}, timeout=45)
            if not done:
                self.execution.cancel()
                await asyncio.to_thread(self.stop_owned_controller)
                await asyncio.wait({self.execution}, timeout=15)
                raise AssertionError("execution did not settle within recovery deadline")
            try:
                result = self.execution.result()
            except asyncio.CancelledError:
                assert self.case == "caller_disconnect"
            if result is not None:
                assert result.outcome != "completed", "fault produced a completed work verdict"
            await asyncio.to_thread(wait_until, self.physical_clean, "nested recovery retained physical resources", 30)
            if self.case == "controller_death":
                assert controller.wait(timeout=5) == -signal.SIGKILL
                self.replacement = subprocess.Popen(
                    [str(service_binary), str(config_path)], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=service_log, text=True,
                )
                await asyncio.to_thread(wait_until, lambda: self.ready(), "restart did not reconcile", 30)
            else:
                assert controller.poll() is None
                assert self.process_identity(controller.pid, service_binary) == controller_identity

            # Two simultaneous real preparations fill this node's two slots.
            # A health response alone would not prove admission capacity reuse.
            assert config["smol"]["maximum_parallel"] == 2
            probe = io.BytesIO()
            with zipfile.ZipFile(probe, "w") as archive:
                archive.writestr("capacity-probe.txt", b"bounded capacity probe")
            sealed_probe = probe.getvalue()
            preparation = TrustedIntakePreparation(
                phase="post_submit", policy_sha256="sha256:" + "a" * 64,
                limits=SubmissionArchiveLimits(maximum_inspection_seconds=30), deadline_ms=30000,
                archive_byte_count=len(sealed_probe),
            )
            sessions = []
            try:
                prepared = await asyncio.gather(
                    intake.prepare(preparation), intake.prepare(preparation), return_exceptions=True,
                )
                sessions = [session for session in prepared if not isinstance(session, BaseException)]
                assert len(sessions) == 2, "recovery did not release both admission slots"
                assert len(list(self.leases.iterdir())) == 2
            finally:
                await asyncio.gather(*(session.close() for session in sessions))
            await asyncio.to_thread(wait_until, self.physical_clean, "capacity reuse retained resources", 30)
            assert self.private_directory(self.child_root) == initial_child_identity
            assert not [item for item in observations if "receipt" in item]
            assert len(creates) == 1, "fault caused additional controlled model calls"
            async with harness.factory() as session:
                evidence = tuple(await session.scalars(select(CheckerTrialEvidence)))
                bindings = tuple(await session.scalars(select(ArtifactBinding).where(
                    ArtifactBinding.resource_type == "checker_trial_evidence"
                )))
                puts = tuple(await session.scalars(select(ArtifactPutAttempt).where(
                    ArtifactPutAttempt.checker_trial_evidence_id.is_not(None)
                )))
                effects = tuple(await session.scalars(select(ModelUsageEffect)))
                # Reservation is an authorized durable address, not a receipt.
                # Execution failure must never commit content or start ART I/O.
                assert len(evidence) == 1 and evidence[0].content_sha256 is None
                assert not bindings and not puts
                assert len(effects) == 1 and effects[0].state == "completed"
                effect_summary = [{"effect_id": item.id, "state": item.state,
                                   "settled_nanodollars": item.settled_nanodollars} for item in effects]
            summary = {
                "schema_version": "workstream.nested_trial_recovery.v1", "case": self.case,
                "provider_mode": "controlled", "real_provider_calls": 0,
                "controller_before": controller_identity, "reached": self.reached,
                "result_outcome": None if result is None else result.outcome,
                "trial_receipts": 0, "trial_artifact_bindings": 0,
                "reserved_trial_addresses": 1, "trial_artifact_put_attempts": 0,
                "model_effects": effect_summary, "capacity_reuse_simultaneous_intakes": 2,
                "physical_cleanup_confirmed": True, "child_root_identity_unchanged": True,
                "controller_restarted": self.replacement is not None,
                "pending_create_observations": self.pending_create_observations,
            }
            path = Path(os.environ["WORKSTREAM_TS_SMOL_ROOT"]) / "recovery-summary.json"
            path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
            path.chmod(0o400)
            self.completed = True
        except BaseException as failure:
            try:
                self.retain_inventory_failure()
            except BaseException as retention_failure:
                failure.add_note("observer inventory retention also failed: " + type(retention_failure).__name__
                                 + ": " + str(retention_failure)[:512])
            try:
                await self.drain_failed_execution()
            except BaseException as cleanup_failure:
                failure.add_note("observer failure cleanup also failed: " + type(cleanup_failure).__name__
                                 + ": " + str(cleanup_failure)[:512])
            raise

    def relay_roots_clean(self):
        return all(
            {entry.name for entry in Path(self.config["trial_runtime"][key]).iterdir()}
            == {".workstream-trial-root.json"}
            for key in ("relay_root", "scratch_root")
        )

    async def drain_failed_execution(self):
        if not self.execution.done():
            self.execution.cancel()
            done, _ = await asyncio.wait({self.execution}, timeout=5)
            if not done:
                await asyncio.to_thread(self.stop_owned_controller)
                done, _ = await asyncio.wait({self.execution}, timeout=15)
                assert done, "task did not drain after exact-owned controller teardown"
        if self.controller.poll() is None:
            # Adapter cancellation closes the socket before Rust finishes its
            # relay worker. Keep the controller alive for the existing drain.
            await asyncio.to_thread(
                wait_until, lambda: self.physical_clean() and self.relay_roots_clean(),
                "failed observer retained physical or relay resources", 30,
            )

    def stop_owned_controller(self):
        if self.controller.poll() is None:
            expected = self.controller_identity
            assert self.process_identity(expected["pid"], Path(expected["executable"])) == expected
            self.controller.terminate()
            try:
                self.controller.wait(timeout=5)
            except subprocess.TimeoutExpired:
                assert self.process_identity(expected["pid"], Path(expected["executable"])) == expected
                self.controller.kill()
                self.controller.wait(timeout=5)

    def ready(self):
        try:
            return exchange(self.config["socket_path"], {
                "protocol_version": "external_checker_service.v1", "operation": "health",
            })["status"] == "ready"
        except (OSError, EOFError):
            return False

    def expected_controller_exit(self, controller):
        return self.killed_controller == controller.pid and controller.returncode == -signal.SIGKILL

    def close(self):
        if self.replacement is not None and self.replacement.poll() is None:
            self.replacement.terminate()
            try:
                self.replacement.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.replacement.kill()
                self.replacement.wait(timeout=15)


def test_nested_observation_reads_only_copies_and_never_recreates_retired_targets(tmp_path, monkeypatch):
    import shutil
    from types import SimpleNamespace

    home = tmp_path / "retired-home"
    probe = NestedTrialRecovery("caller_disconnect")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("observer invoked CLI")))
    assert probe.snapshot_inventory(home, "owned") is None
    assert probe.agent_marker(home, "owned") is None
    assert not home.exists()

    source = home / ".local/share/smolvm/server/smolvm.db"
    source.parent.mkdir(parents=True)
    connect = sqlite3.connect
    writer = connect(source)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE vms(name TEXT PRIMARY KEY,data BLOB)")
        value = {"name": "owned", "state": "running", "pid": os.getpid(),
                 "labels": {"workstream.external-checker-owner": "a" * 64}, "network": False}
        writer.execute("INSERT INTO vms VALUES(?,?)", ("owned", json.dumps(value).encode()))
        writer.commit()
        for path in source.parent.iterdir():
            path.chmod(0o600)
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                  for path in source.parent.iterdir()}

        def copied_only(path, *args, **kwargs):
            assert not Path(path).is_relative_to(home), "SQLite opened original target"
            return connect(path, *args, **kwargs)
        monkeypatch.setattr(sqlite3, "connect", copied_only)
        observed, raw = probe.snapshot_inventory(home, "owned")
        assert probe.child_inventory(observed, "owned") == value and raw
        after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                 for path in source.parent.iterdir()}
        assert after == before  # Includes the original WAL and SHM bytes.
    finally:
        writer.close()
    shutil.rmtree(home)
    assert probe.snapshot_inventory(home, "owned") is None
    assert probe.agent_marker(home, "owned") is None
    assert not home.exists()
    lease = tmp_path / "lease"
    lease.touch()
    assert probe.observation_retired(lease, 2**31 - 1)
    assert not probe.observation_retired(lease, os.getpid())
    lease.unlink()
    assert probe.observation_retired(lease, os.getpid())
    # Exercise the real polling owner, not just its read helpers. An empty HOME
    # behind a valid published lease must not acquire CLI-created DB residue.
    probe.config = {"smol": dict.fromkeys(("binary", "binary_sha256", "guest_binary", "guest_sha256", "cgroup_root"), "unused")}
    probe.service_root = tmp_path / "service"
    probe.leases = probe.service_root / "smol-leases"
    probe.leases.mkdir(parents=True)
    probe.child_root = tmp_path / "children"
    probe.child_root.mkdir(mode=0o700)
    owner = "a" * 64
    (probe.service_root / ".workstream-checker-owner").write_text(owner)
    name = "ws-" + "1" * 32
    target = probe.child_root / (name + ".home")
    target.mkdir(mode=0o700)
    published = probe.leases / (name + ".json")
    published.write_text(json.dumps({"name": name, "owner": owner, "root": str(probe.leases),
                                    "private_home_root": str(probe.child_root),
                                    "runtime": probe.config["smol"] | {"home": str(target)}}))
    published.chmod(0o600)
    probe.execution = SimpleNamespace(done=lambda: False)
    assert probe.marker() is False and not list(target.iterdir())
    target.rmdir()
    assert probe.marker() is False and not target.exists()


def test_nested_agent_marker_uses_fixed_bounded_protocol_without_target_writes():
    import pytest
    import threading
    from smol_runtime import receive

    for fault in ("none", "pending", "oversized", "truncated", "bad_base64", "stderr", "slow_partial"):
        with tempfile.TemporaryDirectory(prefix="nr-") as temporary:
            home = Path(temporary)
            path = home / ".cache/smolvm/vms" / hashlib.sha256(b"owned").hexdigest()[:16] / "agent.sock"
            path.parent.mkdir(parents=True)
            listener = socket.socket(socket.AF_UNIX)
            listener.bind(str(path));path.chmod(0o600);listener.listen(1)
            before = sorted(str(item.relative_to(home)) for item in home.rglob("*"))
            requests = []
            failures = []

            def server():
                try:
                    with listener, listener.accept()[0] as channel:
                        channel.settimeout(3)
                        length = struct.unpack(">I", receive(channel, 4))[0]
                        assert 0 < length < 4096
                        requests.append(json.loads(receive(channel, length)))
                        if fault == "oversized":
                            channel.sendall(struct.pack(">I", 65537));return
                        if fault == "truncated":
                            channel.sendall(b"\x00\x00");return
                        if fault == "slow_partial":
                            channel.sendall(b"\x00");time.sleep(2.1);return
                        response = {"status": "completed", "exit_code": 43 if fault == "pending" else 0,
                                    "stdout": base64.b64encode(b"" if fault == "pending" else b"nested-workload-ready:123\n").decode(),
                                    "stderr": base64.b64encode(b"unexpected" if fault == "stderr" else b"").decode()}
                        if fault == "bad_base64":
                            response["stdout"] = "!!!"
                        raw = canonical(response)
                        channel.sendall(struct.pack(">I", len(raw)) + raw)
                except BaseException as error:
                    failures.append(error)
            worker = threading.Thread(target=server)
            worker.start()
            started = time.monotonic()
            try:
                if fault in {"none", "pending"}:
                    result = NestedTrialRecovery.agent_marker(home, "owned")
                    assert result == (b"nested-workload-ready:123\n" if fault == "none" else None)
                else:
                    with pytest.raises((AssertionError, EOFError, ValueError, TimeoutError)):
                        NestedTrialRecovery.agent_marker(home, "owned")
            finally:
                worker.join(timeout=4)
                assert not worker.is_alive() and not failures
            assert time.monotonic() - started < 3
            assert sorted(str(item.relative_to(home)) for item in home.rglob("*")) == before
            request = requests[0]
            assert request == {"method": "vm_exec", "command": request["command"], "env": [],
                               "workdir": None, "timeout_ms": 1000, "interactive": False,
                               "tty": False, "background": False, "stdin_data": None}
            assert request["command"][:2] == ["/bin/sh", "-c"]
            assert "/workspace/.trial-recovery-ready" in request["command"][2]


def test_nested_vmm_identity_accepts_nondumpable_process_and_rejects_foreign_custody(monkeypatch):
    import select
    import sys
    import pytest

    child = subprocess.Popen([
        sys.executable, "-c",
        "import ctypes,time; libc=ctypes.CDLL(None); "
        "assert libc.prctl(4,0,0,0,0)==0 and libc.prctl(3,0,0,0,0)==0; "
        "print('ready',flush=True); time.sleep(10)",
    ], stdout=subprocess.PIPE, text=True)
    try:
        assert select.select([child.stdout], [], [], 3)[0], "non-dumpable child did not start"
        assert child.stdout.readline(32) == "ready\n"
        process = Path("/proc") / str(child.pid)
        membership = (process / "cgroup").read_text().strip()
        assert membership.startswith("0::/")
        group = Path("/sys/fs/cgroup" + membership.removeprefix("0::"))
        observed = NestedTrialRecovery.vmm_identity(child.pid, group)
        assert observed["uids"] == [os.geteuid()] * 4
        assert observed["gids"] == [os.getegid()] * 4
        assert NestedTrialRecovery.vmm_identity(child.pid, group, observed) == observed
        with pytest.raises(AssertionError):
            NestedTrialRecovery.vmm_identity(child.pid, group, observed | {
                "start_ticks": observed["start_ticks"] + 1,
            })
        with pytest.raises(AssertionError):
            NestedTrialRecovery.vmm_identity(child.pid, group / "foreign")
        original = Path.read_text
        for field, foreign in (("Uid", os.geteuid() + 1), ("Gid", os.getegid() + 1)):
            def altered(path, *args, **kwargs):
                raw = original(path, *args, **kwargs)
                if path == process / "status":
                    raw = "\n".join(
                        field + ":\t" + "\t".join([str(foreign)] * 4)
                        if row.startswith(field + ":") else row for row in raw.splitlines()
                    )
                return raw
            with monkeypatch.context() as patch:
                patch.setattr(Path, "read_text", altered)
                with pytest.raises(AssertionError):
                    NestedTrialRecovery.vmm_identity(child.pid, group)
    finally:
        child.terminate()
        child.wait(timeout=3)
        child.stdout.close()


def test_nested_vmm_zombie_requires_verified_retirement(tmp_path):
    import sys
    import pytest

    lease = tmp_path / "lease.json"
    lease.write_text("retained")
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    process = Path("/proc") / str(child.pid)
    try:
        wait_until(lambda: (process / "stat").read_text().rpartition(") ")[2].split()[0] == "Z",
                   "control child did not retire", 3)
        membership = (process / "cgroup").read_text().strip()
        group = Path("/sys/fs/cgroup" + membership.removeprefix("0::"))
        with pytest.raises(ProcessLookupError):
            NestedTrialRecovery.vmm_identity(child.pid, group)
        assert NestedTrialRecovery.observation_retired(lease, child.pid)
        assert lease.read_text() == "retained"
    finally:
        child.wait(timeout=3)


def test_nested_failed_observer_waits_for_actual_relay_drain(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace
    import pytest

    relay, scratch = tmp_path / "relay", tmp_path / "scratch"
    for root in (relay, scratch):
        root.mkdir()
        (root / ".workstream-trial-root.json").write_text("marker")
    session = relay / ".trial-owned"
    session.mkdir()
    endpoint = session / "execution.sock"
    with socket.socket(socket.AF_UNIX) as channel:
        channel.bind(str(endpoint))
    probe = NestedTrialRecovery("caller_disconnect")
    probe.config = {"trial_runtime": {"relay_root": str(relay), "scratch_root": str(scratch)}}
    probe.controller = SimpleNamespace(poll=lambda: None)
    probe.physical_clean = lambda: True
    probe.stop_owned_controller = lambda: (_ for _ in ()).throw(AssertionError("controller stopped before drain"))
    drained = threading.Event()
    def finish_runtime():
        endpoint.unlink()
        session.rmdir()
        drained.set()
    worker = threading.Timer(0.05, finish_runtime)
    async def exercise():
        probe.execution = asyncio.create_task(asyncio.sleep(3600))
        worker.start()
        await probe.drain_failed_execution()
        assert probe.execution.cancelled() and drained.is_set()
        assert probe.relay_roots_clean()
        def expired(predicate, description, timeout):
            assert timeout == 30
            raise AssertionError("bounded secondary cleanup failure")
        monkeypatch.setattr(__import__(__name__), "wait_until", expired)
        with pytest.raises(AssertionError, match="bounded secondary"):
            await probe.drain_failed_execution()
    try:
        asyncio.run(exercise())
    finally:
        worker.join(timeout=3)
        assert not worker.is_alive()


def test_nested_inventory_uses_unique_exact_name_and_selected_authority():
    import pytest

    owner = "a" * 64
    expected = {"name": "owned", "labels": {"workstream.external-checker-owner": owner}, "network": False}
    other = {"name": "other", "labels": {"workstream.external-checker-owner": "foreign"}, "network": True}
    select = NestedTrialRecovery.child_inventory
    assert select([other, expected], "owned") is expected
    assert select([other], "owned") is None
    assert select({"machines": [other, expected]}, "owned") is expected
    for invalid in ([expected, expected], {"machines": "invalid"}, {}, "invalid"):
        with pytest.raises(AssertionError):
            select(invalid, "owned")
    NestedTrialRecovery.validate_child(expected, owner)
    for invalid in (expected | {"network": True}, expected | {"labels": other["labels"]}):
        with pytest.raises(AssertionError):
            NestedTrialRecovery.validate_child(invalid, owner)


def test_nested_inventory_evidence_is_bounded_and_retained_before_failure(tmp_path):
    rows = {"machines": [{"name": "x" * 1024, "state": "running", "argv": "unretained"}] * 12}
    raw = json.dumps(rows).encode()
    facts = NestedTrialRecovery.inventory_facts(rows, "owned", "a" * 64, tmp_path, {}, raw)
    assert facts["row_count"] == 12 and len(facts["observed_rows"]) == 8
    assert len(facts["observed_rows"][0]["name"]) == 256
    assert "unretained" not in json.dumps(facts)
    assert facts["raw_inventory_sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    recovery = NestedTrialRecovery("caller_disconnect")
    recovery.service_root = tmp_path / "service"
    recovery.last_inventory = facts
    recovery.retain_inventory_failure()
    path = tmp_path / "inventory-failure.json"
    assert json.loads(path.read_text()) == facts
    assert stat.S_IMODE(path.lstat().st_mode) == 0o600


class Recovery:
    def __init__(self, config_path, fixtures, unit):
        self.path = config_path
        self.original = config_path.read_bytes()
        self.config = json.loads(self.original)
        self.unit = unit
        self.proof = Proof(self.config, fixtures)
        self.image = next(c for c in self.config['cache'] if c['repository'] == 'workstream-test/smol-python')
        self.leases = Path(self.config['socket_path']).parent / 'smol-leases'
        self.groups = Path(self.config['smol']['cgroup_root'])
        self.foreign = 'smol-recovery-foreign-control'
        self.foreign_process = None
        self.connections = []
        self.disks = set()
        self.flag = config_path.parent / 'recovery-delete-fault'
        self.wrapper = config_path.parent / 'recovery-smol-wrapper'
        self.trace = config_path.parent / 'recovery-runtime-trace.jsonl'
        self.mode = config_path.parent / 'recovery-prepare-failures'

    def runtime(self, *args):
        s = self.config['smol']
        return subprocess.run([s['binary'], *args], check=True, capture_output=True, text=True,
                              timeout=15, env={'HOME': s['home'], 'PATH': '/usr/bin:/bin'})

    def rows(self):
        return json.loads(self.runtime('machine', 'ls', '--json').stdout)

    def owned(self):
        owner = (self.leases.parent / '.workstream-checker-owner').read_text().strip()
        rows = [r for r in self.rows() if r['labels'].get('workstream.external-checker-owner') == owner]
        for row in rows:
            name_hash = hashlib.sha256(row['name'].encode()).hexdigest()[:16]
            self.disks.add(Path(self.config['smol']['home']) / '.cache/smolvm/vms' / name_hash)
        return rows

    def ready(self):
        try:
            result = exchange(self.config['socket_path'],
                              {'protocol_version': 'external_checker_service.v1', 'operation': 'health'})
            return result['status'] == 'ready'
        except (OSError, EOFError):
            return False

    def clean(self):
        return (not list(self.leases.iterdir()) and not self.owned()
                and not any(path.exists() for path in self.disks)
                and not [p for p in self.groups.iterdir() if p.is_dir() and p.name.startswith('ws-')])

    def start(self):
        envelope = self.proof.request(self.image, 'pre_submit', 'sleep', deadline_ms=30000)
        connection = socket.socket(socket.AF_UNIX)
        connection.settimeout(3)
        connection.connect(self.config['socket_path'])
        self.connections.append(connection)
        raw = canonical(envelope)
        connection.sendall(struct.pack('>I', len(raw)) + raw)
        return connection

    def running(self, count):
        return len([r for r in self.owned() if r['state'] == 'running']) == count

    def disconnect(self):
        for connection in self.connections:
            connection.close()
        self.connections.clear()

    def report(self, case):
        assert any(r['name'] == self.foreign for r in self.rows()), 'foreign VM deleted'
        assert self.foreign_process.poll() is None, 'foreign cgroup process killed'
        assert (self.groups / self.foreign).exists(), 'foreign cgroup deleted'
        print(json.dumps({'case': case, 'cleanup': 'confirmed', 'foreign_resources': 'preserved'}), flush=True)

    def restart(self):
        subprocess.run(['sudo', 'systemctl', 'reset-failed', self.unit], check=True, timeout=15)
        subprocess.run(['sudo', 'systemctl', 'restart', self.unit], check=True, timeout=30)
        wait_until(self.ready, 'node failed to become ready')

    def retry_proof(self):
        for remaining, expected_creates, case in (
            (1, 2, 'retry_after_confirmed_cleanup'),
            (-1, 3, 'preparation_retry_limit'),
            (0, 1, 'launched_deadline_never_retried'),
        ):
            self.trace.write_text('')
            self.mode.write_text(str(remaining))
            if remaining == -1:
                envelope = self.proof.request(self.image, 'pre_submit', 'pass')
                response = exchange(self.config['socket_path'], envelope)
                assert response['result']['request_digest'] == envelope['request']['request_digest']
                assert response['result']['outcome'] == 'infrastructure_failed'
                assert response['result']['infrastructure_failure_code'] == 'implementation_unavailable'
                assert response['isolation'] is None
            elif remaining:
                self.proof.execute(self.image, 'pre_submit', 'pass')
            else:
                self.proof.execute(self.image, 'pre_submit', 'sleep',
                                   expected='deadline_exceeded', deadline_ms=5000)
            wait_until(self.clean, 'retry test leaked resources')
            events = [json.loads(line) for line in self.trace.read_text().splitlines()]
            creates = [e for e in events if e['operation'] == 'create']
            executions = [e for e in events if e['operation'] == 'exec']
            assert len(creates) == expected_creates, events
            assert len({e['name'] for e in creates}) == expected_creates, events
            assert all(e['prior_resources'] == [] for e in creates), events
            assert len(executions) == (0 if remaining == -1 else 1), events
            assert len([e for e in events if e['operation'] == 'start']) == expected_creates, events
            assert len([e for e in events if e['operation'] == 'delete']) == expected_creates, events
            self.report(case)
        self.mode.write_text('0')

    def run(self):
        assert self.clean() and self.ready(), 'isolated node must start drained and ready'
        self.runtime('machine', 'create', '--name', self.foreign, '--image', self.image['smol']['archive'],
                     '--label', 'workstream.external-checker-owner=foreign-control', '--mem', '256', '--storage', '1')
        # The separate process in a foreign sibling cgroup proves restart cleanup
        # does not infer ownership merely from membership under the delegated root.
        group = self.groups / self.foreign
        group.mkdir()
        script = 'echo $$ > ' + shlex.quote(str(group / 'cgroup.procs')) + '; exec sleep 600'
        self.foreign_process = subprocess.Popen(['sudo', 'sh', '-c', script])
        wait_until(lambda: 'populated 1' in (group / 'cgroup.events').read_text(), 'foreign control failed')
        try:
            self.start()
            wait_until(lambda: self.running(1), 'first VM never started')
            self.disconnect()
            wait_until(self.clean, 'disconnect leaked resources', timeout=15)
            self.report('disconnect_cleanup')

            for _ in range(self.config['smol']['maximum_parallel']):
                self.start()
            wait_until(lambda: self.running(self.config['smol']['maximum_parallel']), 'VMs did not overlap')
            try:
                extra = self.start()
                assert extra.recv(1) == b'', 'capacity overflow was accepted'
            except (ConnectionResetError, BrokenPipeError):
                pass
            assert len(self.owned()) == self.config['smol']['maximum_parallel']
            self.disconnect()
            wait_until(self.clean, 'capacity test leaked resources', timeout=15)
            self.report('concurrent_capacity_rejection')

            self.start()
            wait_until(lambda: self.running(1), 'kill target never started')
            pid = int(subprocess.check_output(['systemctl', 'show', self.unit, '-p', 'MainPID', '--value'], text=True))
            assert Path(f'/proc/{pid}/exe').resolve() == self.path.parent / 'service'
            os.kill(pid, signal.SIGKILL)
            self.disconnect()
            wait_until(self.clean, 'guardian did not clean after controller death', timeout=15)
            wait_until(self.ready, 'startup did not reconcile after controller death')
            self.report('controller_kill_guardian_cleanup')

            # Signed/pinned wrapper is test-only configuration, not a production
            # fault switch. A failed exact-name delete must leave custody durable.
            source = Path(__file__).parent / 'smol_fixture/runtime_wrapper.py'
            self.wrapper.write_bytes(source.read_bytes())
            self.mode.write_text('0')
            self.wrapper.with_suffix('.json').write_text(json.dumps({
                'binary': self.config['smol']['binary'], 'trace': str(self.trace),
                'mode': str(self.mode), 'cgroups': str(self.groups), 'delete_fault': str(self.flag),
            }))
            self.wrapper.chmod(0o700)
            changed = json.loads(self.original)
            changed['smol']['binary'] = str(self.wrapper)
            changed['smol']['binary_sha256'] = 'sha256:' + hashlib.sha256(self.wrapper.read_bytes()).hexdigest()
            self.path.write_text(json.dumps(changed))
            self.restart()
            self.retry_proof()
            self.start()
            wait_until(lambda: self.running(1), 'cleanup fault target never started')
            self.flag.touch()
            self.disconnect()
            wait_until(lambda: not self.ready(), 'cleanup uncertainty left readiness open')
            time.sleep(3)
            assert list(self.leases.iterdir()), 'failed cleanup discarded durable lease'
            assert self.owned(), 'fault did not discriminate failed VM deletion'
            assert not self.ready(), 'restart admitted work with unsettled cleanup'
            self.flag.unlink()
            self.path.write_bytes(self.original)
            self.restart()
            wait_until(self.clean, 'startup failed to recover retained lease')
            self.report('cleanup_uncertainty_closes_readiness')
        finally:
            self.disconnect()
            self.flag.unlink(missing_ok=True)
            self.path.write_bytes(self.original)
            self.restart()
            wait_until(self.clean, 'test cleanup failed')
            self.runtime('machine', 'delete', '--name', self.foreign, '--force')
            (group / 'cgroup.kill').write_text('1')
            self.foreign_process.wait(timeout=10)
            group.rmdir()
            self.wrapper.unlink(missing_ok=True)
            self.wrapper.with_suffix('.json').unlink(missing_ok=True)
            self.mode.unlink(missing_ok=True)
            self.proof.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--fixtures', required=True, type=Path)
    parser.add_argument('--unit', required=True)
    args = parser.parse_args()
    Recovery(args.config, args.fixtures, args.unit).run()


if __name__ == '__main__':
    main()
