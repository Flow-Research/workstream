from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULES = [importlib.import_module("api_contract_e2e"), importlib.import_module("week2_api_e2e")]


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize(
    "name", ["workstream_test", "test_workstream", "workstream_test_012345abcdef"]
)
def test_api_drill_database_guard_accepts_only_supported_local_names(module, name: str) -> None:
    """The destructive drill accepts historical and isolated local test DB names."""
    module.assert_local_database_url(
        f"postgresql+asyncpg://workstream:secret@127.0.0.1:5433/{name}"
    )


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize(
    ("host", "name"),
    [
        ("db.example.com", "workstream_test_012345abcdef"),
        ("localhost", "workstream_test_012345abcdef_extra"),
        ("localhost", "workstream_test_012345ABCDEf"),
        ("localhost", '"workstream_test_012345abcdef"'),
    ],
)
def test_api_drill_database_guard_rejects_lookalikes_without_leaking_url(
    monkeypatch: pytest.MonkeyPatch, module, host: str, name: str
) -> None:
    """Remote and lookalike targets fail closed with a non-secret diagnostic."""
    monkeypatch.delenv("WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE", raising=False)
    url = f"postgresql+asyncpg://workstream:secret@{host}:5433/{name}"
    with pytest.raises(RuntimeError) as exc_info:
        module.assert_local_database_url(url)
    assert url not in str(exc_info.value)
    assert "Refusing to run" in str(exc_info.value)


def test_api_contract_drill_requires_isolated_database_without_leaking_url() -> None:
    """The complete API drill refuses a shared persistent test database."""
    isolated_url = (
        "postgresql+asyncpg://workstream:secret@127.0.0.1:5433/workstream_test_012345abcdef"
    )
    api_contract = MODULES[0]
    api_contract.assert_isolated_database_url(isolated_url)

    persistent_url = "postgresql+asyncpg://workstream:secret@127.0.0.1:5433/workstream_test"
    with pytest.raises(RuntimeError) as exc_info:
        api_contract.assert_isolated_database_url(persistent_url)
    assert persistent_url not in str(exc_info.value)
    assert "persistent test database" in str(exc_info.value)
