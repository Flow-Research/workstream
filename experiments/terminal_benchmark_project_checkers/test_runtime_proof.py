#!/usr/bin/env python3
"""Focused fixtures for the WS493 launch boundary and matrix reducer."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_matrix
import image_facts


HEAD = "a" * 40
GRANT_ID = "extract_" + "b" * 32


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_ndjson(path: Path, values: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


class OciLayoutFactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.layout = Path(self.temporary.name)
        blobs = self.layout / "blobs" / "sha256"
        blobs.mkdir(parents=True)
        (self.layout / "oci-layout").write_text(
            '{"imageLayoutVersion":"1.0.0"}', encoding="utf-8"
        )
        config = b'{"architecture":"amd64","os":"linux"}'
        layer = b"exact compressed layer bytes"
        config_digest = self._blob(config)
        self.layer_digest = self._blob(layer)
        self.layer_bytes = layer
        manifest = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {
                    "mediaType": "application/vnd.oci.image.config.v1+json",
                    "digest": config_digest,
                    "size": len(config),
                },
                "layers": [
                    {
                        "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                        "digest": self.layer_digest,
                        "size": len(layer),
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()
        self.manifest_digest = self._blob(manifest)
        _write_json(
            self.layout / "index.json",
            {
                "schemaVersion": 2,
                "manifests": [
                    {
                        "mediaType": "application/vnd.oci.image.manifest.v1+json",
                        "digest": self.manifest_digest,
                        "size": len(manifest),
                    }
                ],
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _blob(self, value: bytes) -> str:
        digest = hashlib.sha256(value).hexdigest()
        (self.layout / "blobs" / "sha256" / digest).write_bytes(value)
        return f"sha256:{digest}"

    def test_exact_single_manifest_layout_is_accepted(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            image_facts.layout_fact(
                self.layout, self.manifest_digest, "registry.example/image"
            )
        self.assertEqual(
            json.loads(output.getvalue())["platform_manifest_digest"],
            self.manifest_digest,
        )

    def test_substituted_manifest_is_rejected_before_transport(self) -> None:
        manifest = json.loads((self.layout / "index.json").read_text())
        digest = manifest["manifests"][0]["digest"].removeprefix("sha256:")
        (self.layout / "blobs" / "sha256" / digest).write_bytes(b"substituted")
        with self.assertRaisesRegex(ValueError, "manifest digest differs"):
            image_facts.layout_fact(
                self.layout, self.manifest_digest, "registry.example/image"
            )

    def test_substituted_referenced_layer_is_rejected_before_transport(self) -> None:
        layer = (
            self.layout / "blobs" / "sha256" / self.layer_digest.removeprefix("sha256:")
        )
        layer.write_bytes(b"x" * len(self.layer_bytes))
        with self.assertRaisesRegex(ValueError, "OCI layout blob digest differs"):
            image_facts.layout_fact(
                self.layout, self.manifest_digest, "registry.example/image"
            )

    def test_symlinked_referenced_blob_is_rejected(self) -> None:
        layer = (
            self.layout / "blobs" / "sha256" / self.layer_digest.removeprefix("sha256:")
        )
        target = (
            self.layout
            / "blobs"
            / "sha256"
            / self.manifest_digest.removeprefix("sha256:")
        )
        layer.unlink()
        layer.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "non-regular file"):
            image_facts.layout_fact(
                self.layout, self.manifest_digest, "registry.example/image"
            )

    def test_unreferenced_blob_is_rejected(self) -> None:
        (self.layout / "blobs" / "sha256" / ("f" * 64)).write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "unexpected entry"):
            image_facts.layout_fact(
                self.layout, self.manifest_digest, "registry.example/image"
            )

    def test_index_media_type_substitution_is_rejected(self) -> None:
        index_path = self.layout / "index.json"
        index = json.loads(index_path.read_text())
        index["manifests"][0]["mediaType"] = "application/vnd.oci.image.index.v1+json"
        _write_json(index_path, index)
        with self.assertRaisesRegex(ValueError, "manifest media type differs"):
            image_facts.layout_fact(
                self.layout, self.manifest_digest, "registry.example/image"
            )


class MatrixReducerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.raw = Path(self.temporary.name)
        self.launches = [
            {
                "kind": "checker",
                "container_id": "c1",
                "name": "ws-checker-a",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["checker"],
            },
            {
                "kind": "checker",
                "container_id": "c2",
                "name": "ws-checker-b",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["checker"],
            },
            {
                "kind": "builder",
                "attempt": "dead",
                "container_id": "b0",
                "name": "ws-terminal-builder-dead",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["builder"],
            },
            {
                "kind": "builder",
                "attempt": "good",
                "container_id": "b1",
                "name": "ws-terminal-builder-good",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["builder"],
            },
            {
                "kind": "candidate",
                "attempt": "good",
                "container_id": "c3",
                "name": "ws-terminal-candidate-good",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["candidate"],
            },
            *[
                {
                    "kind": "reference",
                    "attempt": "good",
                    "container_id": f"r{index}",
                    "name": f"ws-terminal-reference-good-{index}",
                    "mount_source_identities": build_matrix.SOURCE_IDENTITIES[
                        "reference"
                    ],
                }
                for index in range(3)
            ],
        ]
        self.starts = [
            {"argv": ["start", "-a", "-i", "ws-checker-a"], "status": 0},
            {"argv": ["start", "-a", "-i", "ws-checker-b"], "status": 0},
            {
                "argv": ["start", "--attach", "ws-terminal-builder-good"],
                "status": 0,
            },
            {
                "argv": ["start", "--attach", "ws-terminal-candidate-good"],
                "status": 1,
            },
            *[
                {
                    "argv": [
                        "start",
                        "--attach",
                        f"ws-terminal-reference-good-{index}",
                    ],
                    "status": 0,
                }
                for index in range(3)
            ],
        ]
        _write_json(self.raw / "interrupt.json", {"adapter_failure": True})
        _write_json(
            self.raw / "restart-cleanup.json",
            {
                "owned_containers_absent": True,
                "owned_images_absent": True,
                "unowned_control_preserved": True,
            },
        )
        for name in ("art-interrupt.json", "art-complete.json"):
            _write_json(
                self.raw / name,
                {"ledger_empty": True, "workspace_empty": True},
            )
        _write_json(
            self.raw / "complete-result.json",
            {
                "result": {
                    "findings": [],
                    "outcome": "completed",
                    "verdict": "passed",
                }
            },
        )
        self._flush()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _flush(self) -> None:
        _write_ndjson(self.raw / "launches.ndjson", self.launches)
        _write_ndjson(self.raw / "command-results.ndjson", self.starts)

    def test_exact_matrix_is_accepted(self) -> None:
        value = build_matrix.reduce_matrix(self.raw, HEAD)
        self.assertEqual(value["head_sha"], HEAD)

    def test_extra_partial_attempt_is_rejected(self) -> None:
        self.launches.append(
            {
                "kind": "candidate",
                "attempt": "extra",
                "container_id": "extra",
                "name": "ws-terminal-candidate-extra",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["candidate"],
            }
        )
        self._flush()
        with self.assertRaisesRegex(ValueError, "launch"):
            build_matrix.reduce_matrix(self.raw, HEAD)

    def test_duplicate_start_is_rejected(self) -> None:
        self.starts.append(self.starts[3].copy())
        self._flush()
        with self.assertRaisesRegex(ValueError, "start observations differ"):
            build_matrix.reduce_matrix(self.raw, HEAD)


class DockerWrapperSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.raw = self.root / "raw"
        self.work = self.root / "work"
        self.art = self.root / "art"
        self.cache = self.root / "cache"
        self.workspace = self.art / "workspaces" / GRANT_ID / "workspace"
        self.tests = self.workspace / "tests"
        self.tests.mkdir(parents=True)
        (self.workspace / "solution").mkdir()
        (self.workspace / "solution" / "program.py").write_text("pass\n")
        self.raw.mkdir()
        self.work.mkdir()
        self.cache.mkdir()
        self.inspect = self.root / "inspect.json"
        self.fake_docker = self.root / "fake-docker"
        self.fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ ${1:-} == exec && ${3:-} == docker "
            "&& ${4:-} == container && ${5:-} == inspect ]]; then\n"
            '  cat "${WS493_TEST_INSPECT:?}"\n'
            "fi\n",
            encoding="utf-8",
        )
        self.fake_docker.chmod(0o755)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _environment(self) -> dict[str, str]:
        return {
            **os.environ,
            "WS493_REAL_DOCKER": str(self.fake_docker),
            "WS493_DIND_NAME": "ws-pilot00-test-dind",
            "WS493_RAW_DIR": str(self.raw),
            "WS493_WRAPPER_WORK_DIR": str(self.work),
            "WS493_SERVICE_PID_FILE": str(self.work / "service.pid"),
            "WS493_SERVICE_BINARY": str(self.work / "service"),
            "WS493_BARRIER_ENABLE": str(self.work / "barrier.enable"),
            "WS493_BARRIER_READY": str(self.work / "barrier.ready"),
            "WS493_BARRIER_RELEASE": str(self.work / "barrier.release"),
            "WS493_BARRIER_TOKEN": "token",
            "WS493_SANDBOX_USER": "65532:65532",
            "WS493_ART_ROOT": str(self.art),
            "WS493_CACHE_ROOT": str(self.cache),
            "WS493_TEST_INSPECT": str(self.inspect),
        }

    def _run_item(
        self, item: dict[str, object], name: str
    ) -> subprocess.CompletedProcess[str]:
        _write_json(self.inspect, [item])
        return subprocess.run(
            [
                str(Path(__file__).with_name("docker-wrapper.sh")),
                "create",
                "--name",
                name,
            ],
            env=self._environment(),
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

    def _run(self, source: Path) -> subprocess.CompletedProcess[str]:
        return self._run_item(
            {
                "Id": "candidate-id",
                "Name": "/ws-terminal-candidate-abc",
                "Config": {
                    "Labels": {
                        "workstream.owner": "terminal-benchmark-checker-service-v1",
                        "workstream.resource-kind": "candidate",
                        "workstream.attempt": "abc",
                        "workstream.grant-id": GRANT_ID,
                    },
                    "User": "65532:65532",
                },
                "HostConfig": {
                    "Runtime": "runsc",
                    "NetworkMode": "none",
                    "CapDrop": ["ALL"],
                    "CapAdd": [],
                    "SecurityOpt": ["no-new-privileges"],
                    "ReadonlyRootfs": True,
                    "PidsLimit": 32,
                    "Memory": 536_870_912,
                    "NanoCpus": 1_000_000_000,
                    "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=16777216"},
                },
                "Mounts": [
                    {
                        "Type": "bind",
                        "Source": str(source),
                        "Destination": "/tests",
                        "RW": False,
                    }
                ],
            },
            "ws-terminal-candidate-abc",
        )

    def _builder_item(self, project_source: Path) -> dict[str, object]:
        grant_root = self.art / "workspaces" / GRANT_ID
        runtime = grant_root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "candidate.tar").write_bytes(b"")
        return {
            "Id": "builder-id",
            "Name": "/ws-terminal-builder-abc",
            "Config": {
                "Labels": {
                    "workstream.owner": "terminal-benchmark-checker-service-v1",
                    "workstream.resource-kind": "builder",
                    "workstream.attempt": "abc",
                    "workstream.grant-id": GRANT_ID,
                },
                "User": "0:0",
            },
            "HostConfig": {
                "Runtime": "runsc",
                "NetworkMode": "none",
                "CapDrop": ["ALL"],
                "CapAdd": [
                    "CAP_CHOWN",
                    "CAP_DAC_OVERRIDE",
                    "CAP_FOWNER",
                    "CAP_SYS_CHROOT",
                ],
                "SecurityOpt": ["no-new-privileges"],
                "ReadonlyRootfs": False,
                "PidsLimit": 128,
                "Memory": 536_870_912,
                "NanoCpus": 1_000_000_000,
                "StorageOpt": {"size": "402653184"},
                "Tmpfs": {"/busybox": "rw,noexec,nosuid,nodev,size=16777216"},
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": str(self.cache),
                    "Destination": "/cache",
                    "RW": False,
                },
                {
                    "Type": "bind",
                    "Source": str(runtime / "candidate.tar"),
                    "Destination": "/out/candidate.tar",
                    "RW": True,
                },
                {
                    "Type": "bind",
                    "Source": str(project_source),
                    "Destination": "/project",
                    "RW": False,
                },
            ],
        }

    def test_exact_art_source_is_recorded_without_raw_path(self) -> None:
        result = self._run(self.tests)
        self.assertEqual(result.returncode, 0, result.stderr)
        [launch] = [
            json.loads(line)
            for line in (self.raw / "launches.ndjson").read_text().splitlines()
        ]
        self.assertEqual(
            launch["mount_source_identities"], {"/tests": "art_workspace_tests"}
        )
        self.assertNotIn(str(self.root), json.dumps(launch))

    def test_parent_source_substitution_is_rejected(self) -> None:
        result = self._run(Path("/run"))
        self.assertEqual(result.returncode, 70)
        self.assertFalse((self.raw / "launches.ndjson").exists())
        arguments = [
            json.loads(line)["argv"]
            for line in (self.raw / "argv.ndjson").read_text().splitlines()
        ]
        self.assertEqual(arguments[-1], ["launch_rejection:candidate:source"])
        self.assertNotIn(str(self.root), arguments[-1][0])

    def test_noncanonical_builder_source_is_rejected_with_fixed_labels(self) -> None:
        grant_root = self.art / "workspaces" / GRANT_ID
        runtime = grant_root / "runtime"
        missing_project = runtime / "missing-build-context"
        item = self._builder_item(missing_project)

        result = self._run_item(item, "ws-terminal-builder-abc")

        self.assertEqual(result.returncode, 70, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.raw / "launches.ndjson").exists())
        arguments = [
            json.loads(line)["argv"]
            for line in (self.raw / "argv.ndjson").read_text().splitlines()
        ]
        [rejection] = arguments[-1]
        self.assertTrue(rejection.startswith("launch_rejection:builder:"))
        self.assertIn("source", rejection.split(":", 2)[2].split(","))
        self.assertIn("project_source", rejection.split(":", 2)[2].split(","))
        self.assertNotIn(str(self.root), rejection)

    def test_normalized_builder_profile_is_recorded_without_anonymous_volume(
        self,
    ) -> None:
        project = self.art / "workspaces" / GRANT_ID / "runtime" / "build-context"
        project.mkdir(parents=True)

        result = self._run_item(self._builder_item(project), "ws-terminal-builder-abc")

        self.assertEqual(result.returncode, 0, result.stderr)
        [launch] = [
            json.loads(line)
            for line in (self.raw / "launches.ndjson").read_text().splitlines()
        ]
        self.assertEqual(
            launch["cap_add"],
            ["CAP_CHOWN", "CAP_DAC_OVERRIDE", "CAP_FOWNER", "CAP_SYS_CHROOT"],
        )
        self.assertEqual(
            launch["mount_destinations"],
            ["/cache", "/out/candidate.tar", "/project"],
        )
        self.assertNotIn("/busybox", launch["mount_source_identities"])

    def test_anonymous_builder_volume_is_rejected(self) -> None:
        project = self.art / "workspaces" / GRANT_ID / "runtime" / "build-context"
        project.mkdir(parents=True)
        item = self._builder_item(project)
        mounts = item["Mounts"]
        assert isinstance(mounts, list)
        mounts.append(
            {
                "Type": "volume",
                "Source": "/var/lib/docker/volumes/unowned/_data",
                "Destination": "/busybox",
                "RW": True,
            }
        )

        result = self._run_item(item, "ws-terminal-builder-abc")

        self.assertEqual(result.returncode, 70, result.stderr)
        self.assertFalse((self.raw / "launches.ndjson").exists())
        arguments = [
            json.loads(line)["argv"]
            for line in (self.raw / "argv.ndjson").read_text().splitlines()
        ]
        [rejection] = arguments[-1]
        self.assertTrue(rejection.startswith("launch_rejection:builder:"))
        failed = rejection.split(":", 2)[2].split(",")
        self.assertIn("source", failed)
        self.assertIn("mount_count", failed)
        self.assertNotIn(str(self.root), rejection)

    def test_checker_start_forwards_request_stdin_into_dind(self) -> None:
        capture = self.root / "checker-request.json"
        self.fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "[[ $# -eq 8 && $1 == exec && $2 == -i "
            "&& $3 == ws-pilot00-test-dind && $4 == docker "
            "&& $5 == start && $6 == -a && $7 == -i "
            "&& $8 == ws-checker-test ]]\n"
            'cat > "${WS493_TEST_STDIN_CAPTURE:?}"\n',
            encoding="utf-8",
        )
        request = '{"schema_version":"external_checker_request.v1"}'
        environment = self._environment()
        environment["WS493_TEST_STDIN_CAPTURE"] = str(capture)

        result = subprocess.run(
            [
                str(Path(__file__).with_name("docker-wrapper.sh")),
                "start",
                "-a",
                "-i",
                "ws-checker-test",
            ],
            input=request,
            env=environment,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(capture.read_text(), request)


if __name__ == "__main__":
    unittest.main()
