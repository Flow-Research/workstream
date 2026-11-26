"""The maintained journey verifies the current guide envelope and exact bytes."""

import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("fault", [None, "version", "bytes", "locked_guide"])
def test_locked_guide_download_preserves_envelope_and_bytes(
    monkeypatch, tmp_path, fault
):
    monkeypatch.setitem(sys.modules, "public_setup", SimpleNamespace(TASK="task"))
    path = Path(__file__).resolve().parents[1] / "journey/task_work.py"
    spec = importlib.util.spec_from_file_location("journey_locked_guide", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "issue_submitter", lambda *args: "grant")
    monkeypatch.setattr(module, "_release_task", lambda *args, **kwargs: "task")
    events = []

    def claim(_client, token, task_id):
        assert (token, task_id) == ("alice", "task")
        assert events == [
            (scope, action)
            for scope in ("project", "task")
            for action in ("read", "denied", "download")
        ]
        events.append(("task", "claim"))
        return "assignment"

    monkeypatch.setattr(module, "_claim_task", claim)
    bodies = [b"original guide", b"original rules"]
    envelope = {
        "project_id": "project",
        "guide_id": "guide",
        "version": "v1",
    }

    class Client:
        directory = tmp_path

        def call(self, token, *arguments, expected_exit=0):
            if arguments[:2] in (("project", "create"), ("project", "show")):
                return {"id": "other"}
            scope = arguments[0]
            selector = (
                ("project", "guide", "approved", "project")
                if scope == "project"
                else ("task", "guide", "task")
            )
            assert arguments[: len(selector)] == selector
            response = envelope | {
                "documents": [
                    {
                        "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
                        "byte_count": len(body),
                        "read_reference": f"/{scope}/document-{i}",
                    }
                    for i, body in enumerate(bodies)
                ]
            }
            if scope == "task" and fault == "locked_guide":
                response["guide_id"] = "other-guide"
            if token == "bob":
                assert expected_exit == 1
                events.append((scope, "denied"))
                return {"error": {"status": 404}}
            if "--download" in arguments:
                events.append((scope, "download"))
                destination = Path(arguments[-1])
                for index, body in enumerate(bodies):
                    (destination / str(index)).write_bytes(
                        b"corrupted" if (scope, fault) == ("task", "bytes") else body
                    )
                return (
                    response | {"version": "v2"}
                    if (scope, fault) == ("task", "version")
                    else response
                )
            events.append((scope, "read"))
            return response

    args = (
        Client(),
        {name: name for name in ("manager", "alice", "bob")},
        {"alice": "alice", "bob": "bob"},
        "project",
        "guide",
    )
    if fault:
        message = {
            "version": "listing changed",
            "bytes": "originals differ",
            "locked_guide": "exact approved guide",
        }[fault]
        with pytest.raises(AssertionError, match=message):
            module.claim_and_read(*args)
        assert ("task", "claim") not in events
    else:
        assert module.claim_and_read(*args) == ("task", "assignment", "grant")
        assert events[-2:] == [("task", "claim"), ("task", "read")]
