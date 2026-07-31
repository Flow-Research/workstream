"""Focused proofs for bounded canonical guide extraction."""

from __future__ import annotations

import asyncio
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.modules.artifacts.guide_extraction as extraction_module
import app.modules.artifacts.guide_extraction_worker as worker_module
from app.modules.artifacts.guide_extraction import (
    MAXIMUM_INPUT_BYTES,
    MAXIMUM_OUTPUT_BYTES,
    BoundGuideExtractor,
    GuideExtractionRunner,
)
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.guide_extraction_service import (
    GuideExtractionCoordinator,
    GuideExtractionPersistenceResult,
    GuideExtractionRequest,
)


async def _bytes(payload: bytes):
    yield payload


@pytest.fixture
def runner() -> GuideExtractionRunner:
    return GuideExtractionRunner()


def test_worker_controls_and_canonical_extractors_execute_in_parent_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(
        worker_module.resource, "setrlimit", lambda key, value: limits.append((key, value))
    )
    worker_module._install_limits()
    assert len(limits) >= 5

    class Function:
        def __init__(self, result):
            self.result = result

        def __call__(self, *_args):
            return self.result

    library = SimpleNamespace(
        seccomp_init=Function(1),
        seccomp_rule_add=Function(0),
        seccomp_syscall_resolve_name=Function(0),
        seccomp_load=Function(0),
        seccomp_release=Function(None),
    )
    monkeypatch.setattr(worker_module.ctypes, "CDLL", lambda *_args, **_kwargs: library)
    worker_module._install_seccomp()
    library.seccomp_syscall_resolve_name.result = -1
    with pytest.raises(worker_module.ExtractionFailure) as unresolved:
        worker_module._install_seccomp()
    assert (unresolved.value.status, unresolved.value.code) == (
        "parser_failure",
        "isolation_unavailable",
    )

    assert worker_module._extract(b"\xef\xbb\xbfhello\r\n", "plain_text") == "hello\n"
    assert worker_module._extract(b'{"z":2,"a":1}', "json") == '{"a":1,"z":2}'
    assert worker_module._extract(b"a,b\r\n1,2\r\n", "csv") == '[["a","b"],["1","2"]]'
    with pytest.raises(worker_module.ExtractionFailure):
        worker_module._extract(b"opaque", "unsupported_binary")
    with pytest.raises(worker_module.ExtractionFailure):
        worker_module._extract(b'{"a":1,"a":2}', "json")
    with pytest.raises(worker_module.ExtractionFailure):
        worker_module._extract(b"\xff", "plain_text")


def test_ooxml_loader_maps_security_failures_without_activating_an_adapter() -> None:
    validate = worker_module._load_ooxml_security()
    with pytest.raises(worker_module.ExtractionFailure) as raised:
        validate(b"not-a-package", "docx")
    assert (raised.value.status, raised.value.code) == (
        "malformed",
        "ooxml_invalid_directory",
    )


@pytest.mark.parametrize(
    ("failure", "status", "error_code"),
    [
        (worker_module.ExtractionFailure("malformed", "invalid_json"), "malformed", "invalid_json"),
        (MemoryError(), "limit_exceeded", "memory_limit"),
        (RuntimeError("private"), "parser_failure", "parser_failure"),
    ],
)
def test_worker_main_bounds_every_exception_class(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
    status: str,
    error_code: str,
) -> None:
    writes: list[bytes] = []
    monkeypatch.setattr(worker_module, "_install_limits", lambda: None)
    monkeypatch.setattr(worker_module, "_install_seccomp", lambda: None)
    monkeypatch.setattr(worker_module, "_extract", lambda *_args: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(worker_module.sys, "argv", ["worker", "json"])
    monkeypatch.setattr(worker_module.sys, "stdin", SimpleNamespace(buffer=BytesIO(b"{}")))

    def write(_fd, value):
        writes.append(bytes(value))
        return len(value)

    monkeypatch.setattr(worker_module.os, "write", write)

    assert worker_module.main() == 0
    assert json.loads(writes[0]) == {
        "status": status,
        "error_code": error_code,
        "output": None,
        "omission_facts": {"truncated": False, "omitted": False},
    }


def test_worker_main_writes_the_complete_result_after_short_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[bytes] = []
    monkeypatch.setattr(worker_module, "_install_limits", lambda: None)
    monkeypatch.setattr(worker_module, "_install_seccomp", lambda: None)
    monkeypatch.setattr(worker_module, "_extract", lambda *_args: "complete")
    monkeypatch.setattr(worker_module.sys, "argv", ["worker", "plain_text"])
    monkeypatch.setattr(worker_module.sys, "stdin", SimpleNamespace(buffer=BytesIO(b"guide")))

    def short_write(_fd, value):
        chunk = bytes(value[:7])
        writes.append(chunk)
        return len(chunk)

    monkeypatch.setattr(worker_module.os, "write", short_write)

    assert worker_module.main() == 0
    assert json.loads(b"".join(writes)) == {
        "status": "extracted",
        "error_code": None,
        "output": "complete",
        "omission_facts": {"truncated": False, "omitted": False},
    }


def test_pdf_worker_orders_limits_trusted_import_seccomp_then_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    writes: list[bytes] = []
    monkeypatch.setattr(worker_module, "_install_limits", lambda: events.append("limits"))

    def load_pdf():
        events.append("trusted_import")

        def parse(_payload: bytes) -> str:
            events.append("parse")
            return '{"pages":[]}'

        return parse

    monkeypatch.setattr(worker_module, "_load_pdf_extractor", load_pdf)
    monkeypatch.setattr(worker_module, "_install_seccomp", lambda: events.append("seccomp"))
    monkeypatch.setattr(worker_module.sys, "argv", ["worker", "pdf"])
    monkeypatch.setattr(worker_module.sys, "stdin", SimpleNamespace(buffer=BytesIO(b"%PDF-1.7")))
    monkeypatch.setattr(
        worker_module.os,
        "write",
        lambda _fd, value: (writes.append(bytes(value)), len(value))[1],
    )

    assert worker_module.main() == 0
    assert events == ["limits", "trusted_import", "seccomp", "parse"]
    assert json.loads(b"".join(writes))["status"] == "extracted"


def test_docx_worker_orders_limits_trusted_import_seccomp_then_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    writes: list[bytes] = []
    omissions = {
        "truncated": False,
        "omitted": False,
        "headers": False,
        "footers": False,
        "comments": False,
        "tracked_deletions": False,
        "embedded_objects": False,
        "hidden_text": False,
        "field_instructions": False,
    }
    monkeypatch.setattr(worker_module, "_install_limits", lambda: events.append("limits"))

    def load_ooxml():
        events.append("validator_import")
        return lambda _payload, _detected_format: object()

    def load_docx(validate_ooxml):
        events.append("adapter_import")
        assert validate_ooxml(b"PK", "docx") is not None

        def parse(_payload: bytes) -> tuple[str, dict[str, bool]]:
            events.append("parse")
            return '{"blocks":[]}', omissions

        return parse

    monkeypatch.setattr(worker_module, "_load_ooxml_security", load_ooxml)
    monkeypatch.setattr(worker_module, "_load_docx_extractor", load_docx)
    monkeypatch.setattr(worker_module, "_install_seccomp", lambda: events.append("seccomp"))
    monkeypatch.setattr(worker_module.sys, "argv", ["worker", "docx"])
    monkeypatch.setattr(worker_module.sys, "stdin", SimpleNamespace(buffer=BytesIO(b"PK")))
    monkeypatch.setattr(
        worker_module.os,
        "write",
        lambda _fd, value: (writes.append(bytes(value)), len(value))[1],
    )

    assert worker_module.main() == 0
    assert events == ["limits", "validator_import", "adapter_import", "seccomp", "parse"]
    assert json.loads(b"".join(writes)) == {
        "status": "extracted",
        "error_code": None,
        "output": '{"blocks":[]}',
        "omission_facts": omissions,
    }


@pytest.mark.parametrize(
    ("detected_format", "payload", "expected"),
    [
        ("plain_text", b"\xef\xbb\xbfhello\r\nworld\r", "hello\nworld\n"),
        ("markdown", b"# Guide\r\n\r\nBody\n", "# Guide\n\nBody\n"),
        ("json", b'{"z":2,"a":[true,null]}', '{"a":[true,null],"z":2}'),
        ("csv", b"name,value\r\na,1\r\n", '[["name","value"],["a","1"]]'),
    ],
)
def test_runner_produces_canonical_content(
    runner: GuideExtractionRunner,
    tmp_path: Path,
    detected_format: str,
    payload: bytes,
    expected: str,
) -> None:
    result = runner.extract(BytesIO(payload), detected_format=detected_format, workspace=tmp_path)

    assert result.status == "extracted"
    assert result.error_code is None
    assert result.canonical_output == expected
    assert result.output_sha256 is not None
    assert result.omission_facts == {"truncated": False, "omitted": False}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("detected_format", "payload", "status", "error_code"),
    [
        ("plain_text", b"bad\x00text", "malformed", "invalid_control_character"),
        ("plain_text", b"\xff", "malformed", "invalid_encoding"),
        ("plain_text", b"a\xef\xbb\xbfb", "malformed", "invalid_encoding"),
        ("markdown", b"\xef\xbb\xbf\xef\xbb\xbf", "malformed", "invalid_encoding"),
        ("json", b'{"a":1,"a":2}', "malformed", "duplicate_json_key"),
        ("json", b'{"a":NaN}', "malformed", "invalid_json_number"),
        ("unsupported_binary", b"opaque", "unsupported", "unsupported_format"),
    ],
)
def test_runner_returns_bounded_failures(
    runner: GuideExtractionRunner,
    tmp_path: Path,
    detected_format: str,
    payload: bytes,
    status: str,
    error_code: str,
) -> None:
    result = runner.extract(BytesIO(payload), detected_format=detected_format, workspace=tmp_path)

    assert (result.status, result.error_code) == (status, error_code)
    assert result.canonical_output is None
    assert result.output_sha256 is None


def test_json_accepts_64_containers_and_rejects_65(
    runner: GuideExtractionRunner, tmp_path: Path
) -> None:
    accepted = ("[" * 64 + "0" + "]" * 64).encode()
    rejected = ("[" * 65 + "0" + "]" * 65).encode()

    assert (
        runner.extract(BytesIO(accepted), detected_format="json", workspace=tmp_path).status
        == "extracted"
    )
    result = runner.extract(BytesIO(rejected), detected_format="json", workspace=tmp_path)
    assert (result.status, result.error_code) == (
        "limit_exceeded",
        "json_nesting_limit",
    )


def test_csv_cell_boundary_is_exact(runner: GuideExtractionRunner, tmp_path: Path) -> None:
    assert (
        runner.extract(
            BytesIO(("x" * 32_768).encode()), detected_format="csv", workspace=tmp_path
        ).status
        == "extracted"
    )
    result = runner.extract(
        BytesIO(("x" * 32_769).encode()), detected_format="csv", workspace=tmp_path
    )
    assert (result.status, result.error_code) == (
        "limit_exceeded",
        "csv_cell_size_limit",
    )
    module_limit_over = runner.extract(
        BytesIO(("x" * 200_000).encode()), detected_format="csv", workspace=tmp_path
    )
    assert (module_limit_over.status, module_limit_over.error_code) == (
        "limit_exceeded",
        "csv_cell_size_limit",
    )


def test_csv_row_and_total_cell_boundaries_are_exact(
    runner: GuideExtractionRunner, tmp_path: Path
) -> None:
    assert (
        runner.extract(BytesIO(b"\n" * 100_000), detected_format="csv", workspace=tmp_path).status
        == "extracted"
    )
    row_over = runner.extract(BytesIO(b"\n" * 100_001), detected_format="csv", workspace=tmp_path)
    assert (row_over.status, row_over.error_code) == (
        "limit_exceeded",
        "csv_row_limit",
    )
    million_cells = (("," * 999) + "\n") * 1000
    assert (
        runner.extract(
            BytesIO(million_cells.encode()), detected_format="csv", workspace=tmp_path
        ).status
        == "extracted"
    )
    cell_over = runner.extract(
        BytesIO((million_cells + ",\n").encode()),
        detected_format="csv",
        workspace=tmp_path,
    )
    assert (cell_over.status, cell_over.error_code) == (
        "limit_exceeded",
        "csv_cell_limit",
    )


def test_input_and_output_byte_boundaries_are_exact(
    runner: GuideExtractionRunner, tmp_path: Path
) -> None:
    assert (
        runner.extract(
            BytesIO(b"x" * MAXIMUM_OUTPUT_BYTES),
            detected_format="plain_text",
            workspace=tmp_path,
        ).status
        == "extracted"
    )
    output_over = runner.extract(
        BytesIO(b"x" * (MAXIMUM_OUTPUT_BYTES + 1)),
        detected_format="plain_text",
        workspace=tmp_path,
    )
    assert (output_over.status, output_over.error_code) == (
        "limit_exceeded",
        "output_limit",
    )
    input_over = runner.extract(
        BytesIO(b"x" * (MAXIMUM_INPUT_BYTES + 1)),
        detected_format="plain_text",
        workspace=tmp_path,
    )
    assert (input_over.status, input_over.error_code) == (
        "limit_exceeded",
        "input_limit",
    )


def test_worker_kernel_isolation_denies_network_process_and_filesystem(
    tmp_path: Path,
) -> None:
    worker = Path(__file__).parent / "fixtures/guide_extraction_probe_worker.py"
    completed = subprocess.run(
        [sys.executable, "-I", str(worker), "__isolation_probe__"],
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        check=True,
        timeout=10,
    )
    envelope = json.loads(completed.stdout)
    assert envelope["status"] == "extracted"
    assert json.loads(envelope["output"]) == {
        "network": True,
        "outside_read": True,
        "outside_write": True,
        "process": True,
        "workspace_write": True,
    }
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("probe", "status", "error_code"),
    [
        ("__cpu_probe__", "limit_exceeded", "cpu_time_limit"),
        ("__memory_probe__", "limit_exceeded", "memory_limit"),
        ("__abnormal_probe__", "parser_failure", "executor_lost"),
    ],
)
def test_real_executor_resource_and_loss_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe: str,
    status: str,
    error_code: str,
) -> None:
    monkeypatch.setattr(extraction_module, "_SUPPORTED", frozenset({probe}))
    runner = GuideExtractionRunner()
    runner._worker_path = Path(__file__).parent / "fixtures/guide_extraction_probe_worker.py"
    result = runner.extract(BytesIO(b""), detected_format=probe, workspace=tmp_path)
    assert (result.status, result.error_code) == (status, error_code)


def test_wall_timeout_kills_and_reaps_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(extraction_module, "_SUPPORTED", frozenset({"__wall_probe__"}))
    monkeypatch.setattr(extraction_module, "WALL_TIMEOUT_SECONDS", 0.05)
    runner = GuideExtractionRunner()
    runner._worker_path = Path(__file__).parent / "fixtures/guide_extraction_probe_worker.py"
    result = runner.extract(BytesIO(b""), detected_format="__wall_probe__", workspace=tmp_path)
    assert (result.status, result.error_code) == (
        "limit_exceeded",
        "wall_time_limit",
    )


def test_runner_fails_closed_when_worker_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*_args, **_kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr(subprocess, "Popen", unavailable)
    runner = GuideExtractionRunner()
    result = runner.extract(BytesIO(b"hello"), detected_format="plain_text", workspace=tmp_path)

    assert result.status == "parser_failure"
    assert result.error_code == "executor_unavailable"
    assert result.canonical_output is None


def test_runner_launch_is_secret_free_and_process_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, object] = {}

    class CompletedProcess:
        returncode = 0
        pid = 123

        def __init__(self, *_args, **kwargs) -> None:
            observed.update(kwargs)

        def communicate(self, _payload, timeout):
            observed["timeout"] = timeout
            return (
                b'{"status":"extracted","error_code":null,"output":"ok",'
                b'"omission_facts":{"truncated":false,"omitted":false}}',
                b"",
            )

    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-leak")
    monkeypatch.setenv("HTTPS_PROXY", "must-not-leak")
    monkeypatch.setattr(subprocess, "Popen", CompletedProcess)
    result = GuideExtractionRunner().extract(
        BytesIO(b"ok"), detected_format="plain_text", workspace=tmp_path
    )

    assert result.status == "extracted"
    assert observed["shell"] is False
    assert observed["close_fds"] is True
    assert observed["start_new_session"] is True
    assert observed["cwd"] == tmp_path
    environment = observed["env"]
    assert isinstance(environment, dict)
    assert set(environment) == {"LANG", "LC_ALL", "PATH"}


@pytest.mark.parametrize(
    "omission_facts",
    [
        {},
        {"truncated": False, "omitted": "no"},
        {"truncated": False, "omitted": False, "unexpected": False},
        {
            "truncated": False,
            "omitted": False,
            "headers": True,
            "footers": False,
            "comments": False,
            "tracked_deletions": False,
            "embedded_objects": False,
            "hidden_text": False,
            "field_instructions": False,
        },
    ],
)
def test_runner_rejects_invalid_omission_fact_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    omission_facts: object,
) -> None:
    class CompletedProcess:
        returncode = 0
        pid = 123

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def communicate(self, _payload, timeout):
            del timeout
            return json.dumps(
                {
                    "status": "extracted",
                    "error_code": None,
                    "output": '{"blocks":[]}',
                    "omission_facts": omission_facts,
                }
            ).encode(), b""

    monkeypatch.setattr(subprocess, "Popen", CompletedProcess)
    result = GuideExtractionRunner().extract(
        BytesIO(b"guide"), detected_format="docx", workspace=tmp_path
    )
    assert (result.status, result.error_code) == (
        "parser_failure",
        "invalid_executor_output",
    )


@pytest.mark.parametrize(
    "worker_result",
    [
        {**result, "omission_facts": {"truncated": False, "omitted": False}}
        for result in (
            {"status": "extracted", "error_code": "conflict", "output": "ok"},
            {"status": "extracted", "error_code": None, "output": None},
            {"status": "extracted", "error_code": None, "output": 7},
            {"status": "malformed", "error_code": None, "output": None},
            {"status": "malformed", "error_code": 7, "output": None},
            {"status": "malformed", "error_code": "x" * 81, "output": None},
            {"status": "malformed", "error_code": "invalid", "output": "unexpected"},
            {"status": "malformed", "error_code": "invalid", "output": 7},
        )
    ],
)
def test_runner_rejects_invalid_worker_result_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker_result: dict[str, object],
) -> None:
    class CompletedProcess:
        returncode = 0
        pid = 123

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def communicate(self, _payload, timeout):
            del timeout
            return json.dumps(worker_result).encode(), b""

    monkeypatch.setattr(subprocess, "Popen", CompletedProcess)

    result = GuideExtractionRunner().extract(
        BytesIO(b"guide"), detected_format="plain_text", workspace=tmp_path
    )

    assert (result.status, result.error_code, result.canonical_output) == (
        "parser_failure",
        "invalid_executor_output",
        None,
    )


@pytest.mark.asyncio
async def test_prepared_extraction_uses_and_cleans_scratch_workspace(tmp_path: Path) -> None:
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=1,
            maximum_concurrency=1,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30,
            total_deadline_seconds=10,
            cleanup_margin_seconds=1,
            stream_buffer_bytes=1024,
            maximum_source_bytes=1024,
        ),
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        _bytes(b'{"b":2,"a":1}'), media_type="application/json"
    )
    try:
        result = await prepared.extract_guide(
            BoundGuideExtractor(runner=GuideExtractionRunner(), detected_format="json")
        )
        assert result.canonical_output == '{"a":1,"b":2}'
        assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_cancelled_extraction_finishes_child_cleanup_before_returning(
    tmp_path: Path,
) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingRunner:
        def extract(self, _reader, *, detected_format: str, workspace: Path):
            del detected_format
            assert workspace.is_dir()
            started.set()
            assert release.wait(timeout=5)
            return GuideExtractionRunner._result("plain_text", "extracted", None, "ok")

    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=1,
            maximum_concurrency=1,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30,
            total_deadline_seconds=10,
            cleanup_margin_seconds=1,
            stream_buffer_bytes=1024,
            maximum_source_bytes=1024,
        ),
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        _bytes(b"text"), media_type="text/plain"
    )
    task = asyncio.create_task(
        prepared.extract_guide(
            BoundGuideExtractor(
                runner=BlockingRunner(),  # type: ignore[arg-type]
                detected_format="plain_text",
            )
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    finally:
        release.set()
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_failed_extractor_residue_is_removed_before_workspace_release(
    tmp_path: Path,
) -> None:
    class DirtyRunner:
        def extract(self, _reader, *, detected_format: str, workspace: Path):
            del detected_format
            nested = workspace / "nested"
            nested.mkdir()
            (nested / "partial").write_bytes(b"untrusted")
            raise RuntimeError("parser failed")

    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=2,
            maximum_concurrency=1,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30,
            total_deadline_seconds=10,
            cleanup_margin_seconds=1,
            stream_buffer_bytes=1024,
            maximum_source_bytes=1024,
        ),
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        _bytes(b"text"), media_type="text/plain"
    )
    try:
        with pytest.raises(RuntimeError, match="parser failed"):
            await prepared.extract_guide(
                BoundGuideExtractor(
                    runner=DirtyRunner(),  # type: ignore[arg-type]
                    detected_format="plain_text",
                )
            )
        assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
        assert manager.pending_cleanup_count == 0
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_stale_cleanup_reaps_crashed_extraction_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=2,
            maximum_concurrency=1,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30,
            total_deadline_seconds=10,
            cleanup_margin_seconds=1,
            stream_buffer_bytes=1024,
            maximum_source_bytes=1024,
        ),
    )
    workspace_name = "extract_" + "a" * 32
    manager._reserve_workspace_sync(workspace_name)
    workspace = tmp_path / "scratch" / "workspaces" / workspace_name
    workspace.mkdir(mode=0o700)
    (workspace / "partial").write_bytes(b"untrusted")
    monkeypatch.setattr(manager, "_owner_process_matches", lambda *_: False)

    cleaned = await manager.cleanup_stale(now_unix_ns=2**63)

    assert cleaned == 1
    assert not workspace.exists()
    assert manager._read_ledger()["workspaces"] == []
    manager.close()


@pytest.mark.asyncio
async def test_executor_failure_retries_once_with_fresh_authority_and_materialization() -> None:
    request = GuideExtractionRequest(
        project_id=uuid4(),
        guide_id=uuid4(),
        source_snapshot_id=uuid4(),
        source_item_id=uuid4(),
        project_setup_run_id=uuid4(),
        setup_generation=1,
        binding_id=uuid4(),
        classification_id=uuid4(),
    )
    prepared_sources: list[SimpleNamespace] = []

    class Materializer:
        async def materialize_with_fresh_authority(self, actual_request):
            assert actual_request is request

            async def close() -> None:
                source.closed = True

            source = SimpleNamespace(closed=False, close=close)
            prepared_sources.append(source)
            return source

    class Service:
        calls = 0

        async def claim_materialization_slot(self, actual_request):
            assert actual_request is request
            return None

        async def extract_prepared(self, actual_request, prepared):
            assert actual_request is request
            assert prepared is prepared_sources[-1]
            self.calls += 1
            status = "parser_failure" if self.calls == 1 else "extracted"
            return GuideExtractionPersistenceResult(
                attempt_id=uuid4(),
                status=status,
                error_code="executor_lost" if status == "parser_failure" else None,
                extracted_content_id=uuid4() if status == "extracted" else None,
                usage_id=uuid4() if status == "extracted" else None,
                replayed=False,
            )

    service = Service()
    result = await GuideExtractionCoordinator(  # type: ignore[arg-type]
        service,
        Materializer(),  # type: ignore[arg-type]
    ).extract(request)

    assert result.status == "extracted"
    assert service.calls == 2
    assert len(prepared_sources) == 2
    assert all(source.closed for source in prepared_sources)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["malformed", "limit_exceeded", "unsupported"])
async def test_terminal_extraction_replay_does_not_materialize_again(status: str) -> None:
    request = GuideExtractionRequest(
        project_id=uuid4(),
        guide_id=uuid4(),
        source_snapshot_id=uuid4(),
        source_item_id=uuid4(),
        project_setup_run_id=uuid4(),
        setup_generation=1,
        binding_id=uuid4(),
        classification_id=uuid4(),
    )
    terminal = GuideExtractionPersistenceResult(
        attempt_id=uuid4(),
        status=status,
        error_code="terminal",
        extracted_content_id=None,
        usage_id=None,
        replayed=False,
    )

    class Service:
        async def claim_materialization_slot(self, actual_request):
            assert actual_request is request
            return terminal

    class Materializer:
        async def materialize_with_fresh_authority(self, _request):
            raise AssertionError("terminal extraction must not materialize again")

    result = await GuideExtractionCoordinator(  # type: ignore[arg-type]
        Service(),
        Materializer(),  # type: ignore[arg-type]
    ).extract(request)
    assert result is terminal
