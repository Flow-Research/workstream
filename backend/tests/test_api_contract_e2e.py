from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest

from app.core.config import Settings

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULES = [importlib.import_module("api_contract_e2e")]


def test_scripted_guide_broker_acknowledgement_binds_exact_delivery() -> None:
    """The API drill cannot acknowledge a different generation or task ID."""
    from uuid import uuid4

    from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

    args = [str(uuid4()) for _ in range(4)] + [1]
    task_id = project_guide_compilation_task_id(args[3], args[4])
    acknowledge = MODULES[0].acknowledge_guide_delivery
    assert acknowledge(args=args, task_id=task_id).id == task_id
    with pytest.raises(ValueError):
        acknowledge(args=[*args[:4], 2], task_id=task_id)
    with pytest.raises(ValueError):
        acknowledge(args=args, task_id=str(uuid4()))
    with pytest.raises(ValueError):
        acknowledge(args=args[:4], task_id=task_id)


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


def test_api_contract_uses_runner_owned_minio_namespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The hosted fan-in maps its isolated MinIO namespace into real ART settings."""
    api_contract = MODULES[0]
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_ENDPOINT", "http://127.0.0.1:9000")
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_BUCKET", "workstream-ci-isolated-012345abcdef")
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_PREFIX", "ci/isolated/012345abcdef")

    env = api_contract.api_environment()

    assert env["WORKSTREAM_ARTIFACT_STORE_BACKEND"] == "s3_compatible"
    assert env["WORKSTREAM_ARTIFACT_S3_PROVIDER_PROFILE"] == "minio"
    assert env["WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL"] == "http://127.0.0.1:9000"
    assert env["WORKSTREAM_ARTIFACT_S3_BUCKET"] == "workstream-ci-isolated-012345abcdef"
    assert env["WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX"] == "ci/isolated/012345abcdef"
    assert env["WORKSTREAM_ARTIFACT_SCRATCH_ROOT"] == str(
        tmp_path / "workstream-api-contract-scratch"
    )
    for key, value in env.items():
        if key.startswith("WORKSTREAM_ARTIFACT_"):
            monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None, environment=env["WORKSTREAM_ENVIRONMENT"])
    assert settings.artifact_store_backend == "s3_compatible"
    assert settings.artifact_s3_bucket == "workstream-ci-isolated-012345abcdef"


def test_real_api_drill_provisions_exact_guide_artifact_pipeline_services() -> None:
    """The fan-in owns every fixed principal required before guide setup can run."""
    api_contract = MODULES[0]

    assert api_contract.GUIDE_ARTIFACT_PIPELINE_SERVICE_IDENTITIES == (
        "workstream.artifact.put_resolver",
        "workstream.artifact.verifier",
        "workstream.artifact.scheduler",
        "workstream.artifact.binding",
        "workstream.artifact.guide_reader",
        "workstream.project.setup",
    )


@pytest.mark.parametrize(
    "selected",
    [None, [], ["check_acceptance_criteria_present"], ["check_policy_context_present"]],
)
@pytest.mark.parametrize("severity_floor", [None, ["critical", "high", "medium"]])
async def test_api_drill_seeds_one_canonical_post_submit_policy(
    monkeypatch,
    selected,
    severity_floor,
) -> None:
    """The real drill compiler accepts additions but cannot reclassify defaults."""
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy
    from app.modules.projects.post_submit_policy import PostSubmitCheckerCompilerError
    from tests.projects.post_submit_fixtures import seed_post_submit_policy_for_downstream_tests
    from app.db import session as db_session

    api_contract = MODULES[0]
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=SimpleNamespace(version="v1"))
    session.commit = AsyncMock()
    monkeypatch.setattr(db_session, "get_session_factory", lambda: lambda: session)
    pre = {"id": str(uuid4()), "compiled_bundle_hash": "sha256:" + "a" * 64,
           "effective_policy_id": str(uuid4()), "effective_policy_hash": "sha256:" + "c" * 64}
    payload = dict(
        project_id=str(uuid4()), guide_id=str(uuid4()), approved_by_actor="manager",
        source_snapshot={"id": str(uuid4()), "bundle_hash": "sha256:" + "b" * 64},
        pre_submit_checker_policy=pre,
    )
    if severity_floor is not None:
        payload["blocking_severities"] = severity_floor
    if selected is not None:
        payload["required_checkers"] = selected
    if selected == ["check_policy_context_present"]:
        with pytest.raises(
            PostSubmitCheckerCompilerError, match="project selection is unavailable"
        ):
            await seed_post_submit_policy_for_downstream_tests(**payload)
        session.get.assert_awaited_once()
        session.add.assert_not_called()
        session.commit.assert_not_awaited()
        return

    result = await seed_post_submit_policy_for_downstream_tests(**payload)
    session.add.assert_called_once()
    policy = session.add.call_args.args[0]
    parsed = CompiledPostSubmitPolicy.model_validate_json(json.dumps(policy.policy_body))
    assert policy.required_checkers == ([] if selected is None else selected)
    assert policy.blocking_severities == (
        ["critical", "high"] if severity_floor is None else severity_floor
    )
    parsed.validate_sidecars(
        required_checkers=policy.required_checkers,
        warning_checkers=policy.warning_checkers,
        blocking_severities=policy.blocking_severities,
    )
    assert set(parsed.default_checkers) == api_contract.EXPECTED_DURABLE_CHECKERS
    assert result["id"] == policy.id
    assert result["policy_hash"] == parsed.policy_hash
    assert policy.approved_by_actor == policy.created_by == "manager"
    assert policy.lifecycle_status == "approved"
    assert policy.pre_submit_checker_policy_id == pre["id"]
    session.get.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_api_drill_action_expectations_use_current_catalogue():
    """Retired actions cannot remain in the drill's independent exact inventories."""
    import ast
    from app.modules.authorization.catalogue import ActionId

    source = ast.parse(Path(MODULES[0].__file__).read_text())
    inventories = [node.comparators[0] for node in ast.walk(source)
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Subscript)
        and isinstance(node.left.slice, ast.Constant)
        and node.left.slice.value == "effective_action_ids"
        and isinstance(node.comparators[0], ast.List)]
    assert inventories
    current_actions = {action.value for action in ActionId}
    for inventory in inventories:
        assert set(ast.literal_eval(inventory)) <= current_actions
