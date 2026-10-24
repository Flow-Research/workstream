"""Explicit in-process intake fake for owner/transaction tests, never isolation proof."""

from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from pathlib import Path
import tempfile

from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.interfaces.trusted_submission_intake import TrustedIntakeIdentity
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
    SealedSubmissionTree,
)
from app.modules.checkers.api.default_checker import WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
from app.modules.checkers.api.material import SubmissionMaterialEntry
from app.modules.checkers.default_checker import evaluate_verified_archive


class LocalIntakeSession:
    def __init__(self, inspector=None):
        self.inspector = inspector or SubmissionArchiveInspector(SubmissionArchiveLimits())
        self.closed = False
        self.aborted = False
        self.tree = None
        self.data = None
        self.inspection = None
        self.events = []
        self.default_bindings = []
        self.identity = TrustedIntakeIdentity(
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
            "smolvm",
            "smol-microvm",
            1000,
            2 * 1024**3,
        )

    def inspect(self, reader, *, archive_sha256, archive_byte_count):
        import hashlib

        self.data = reader.read()
        assert len(self.data) == archive_byte_count
        assert "sha256:" + hashlib.sha256(self.data).hexdigest() == archive_sha256
        self.inspection = self.inspector.inspect(BytesIO(self.data))
        self.events.append("inspect")
        return self.inspection

    def export(self, sink):
        assert self.inspection is not None and not self.closed
        with tempfile.TemporaryDirectory(prefix="test-intake-guest-") as directory:
            workspace = Path(directory)
            with self.inspector._projected_tree(
                BytesIO(self.data), workspace, expected=self.inspection
            ) as tree:
                content = {}
                for entry in tree.entries:
                    if entry.entry_type == "file":
                        data = tree.read_file(entry.normalized_path, maximum_bytes=entry.byte_count)
                        content[entry.normalized_path] = data
                        sink(entry, data)
                self.tree = SealedSubmissionTree(entries=tree.entries, content=content)
        self.events.append("export")

    @property
    def entries(self):
        return tuple(SubmissionMaterialEntry(**asdict(entry)) for entry in self.tree.entries)

    def read_file(self, normalized_path, *, maximum_bytes):
        return self.tree.read_file(normalized_path, maximum_bytes=maximum_bytes)

    async def evaluate_default(self, binding, value):
        assert self.events[-1] == "export" and not self.closed
        self.default_bindings.append(binding)
        self.events.append("default")
        return evaluate_verified_archive(value, self)

    def abort(self):
        self.aborted = True

    async def close(self):
        if not self.closed:
            self.closed = True
            self.events.append("close")
            if self.tree is not None:
                self.tree._close()


class LocalIntakeAdapter:
    identity = ExternalServiceAdapterIdentity("trusted_submission_intake", "test_in_process")

    def __init__(self, inspector=None):
        self.inspector = inspector
        self.sessions = []

    async def prepare(self, request):
        session = LocalIntakeSession(self.inspector or SubmissionArchiveInspector(request.limits))
        self.sessions.append(session)
        return session

    async def health(self):
        return LocalIntakeSession().identity


def assert_sealed_export(root):
    """Revoked grants restore sealed modes before another binding can publish."""
    assert root.stat().st_mode & 0o777 == 0o500
    for entry in root.rglob("*"):
        mode = entry.stat().st_mode & 0o777
        assert mode == 0o500 if entry.is_dir() else mode in {0o400, 0o500}
