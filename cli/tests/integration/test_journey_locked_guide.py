"""The maintained journey verifies the current guide envelope and exact bytes."""

import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("fault", [None, "version", "bytes"])
def test_locked_guide_download_preserves_envelope_and_bytes(monkeypatch, tmp_path, fault):
    monkeypatch.setitem(sys.modules, "public_setup", SimpleNamespace(TASK="task"))
    path = Path(__file__).resolve().parents[1] / "journey/task_work.py"
    spec = importlib.util.spec_from_file_location("journey_locked_guide", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "issue_submitter", lambda *args: "grant")
    monkeypatch.setattr(module, "create_claimed_task", lambda *args, **kwargs: ("task", "assignment"))
    bodies = [b"original guide", b"original rules"]
    envelope = {
        "project_id": "project", "guide_id": "guide", "version": 1,
        "documents": [{"sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
                       "byte_count": len(body)} for body in bodies],
    }

    class Client:
        directory = tmp_path

        def call(self, token, *arguments, expected_exit=0):
            if arguments[:2] in (("project", "create"), ("project", "show")):
                return {"id": "other"}
            assert arguments[:3] == ("task", "guide", "task")
            if token == "bob":
                assert expected_exit == 1
                return {"error": {"status": 404}}
            if "--download" in arguments:
                destination = Path(arguments[-1])
                for index, body in enumerate(bodies):
                    (destination / str(index)).write_bytes(b"corrupted" if fault == "bytes" else body)
                return envelope | {"version": 2} if fault == "version" else envelope
            return envelope

    args = (Client(), {name: name for name in ("manager", "alice", "bob")},
            {"alice": "alice", "bob": "bob"}, "project")
    if fault:
        message = "listing changed" if fault == "version" else "originals differ"
        with pytest.raises(AssertionError, match=message):
            module.claim_and_read(*args)
    else:
        assert module.claim_and_read(*args) == ("task", "assignment", "grant")
