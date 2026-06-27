from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from app.core.config import get_settings
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.projects.models import (
    CheckerPolicy,
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSufficiencyReport,
    PaymentPolicy,
    PreSubmitCheckerPolicy,
    ProjectGuide,
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError


@pytest.fixture
def project_database_env(
    monkeypatch: pytest.MonkeyPatch,
    postgres_database_url: str,
    migration_lock,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "project-token")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "project-manager-subject")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "flow-test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "project_manager")
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())

    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    with migration_lock():
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield postgres_database_url
        command.downgrade(config, "base")
    asyncio.run(db_session.dispose_engine())
    get_settings.cache_clear()


@pytest.fixture
async def project_client(project_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


def auth_headers(token: str = "project-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_project_guide_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in ProjectGuide.__table__.indexes
        if index.name == "uq_project_guides_one_active_per_project"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "status = 'active'" in postgres_compiled


def test_submission_policy_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in SubmissionArtifactPolicy.__table__.indexes
        if index.name == "uq_sap_one_approved_per_guide"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "lifecycle_status = 'approved'" in postgres_compiled


def test_pre_submit_checker_policy_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in PreSubmitCheckerPolicy.__table__.indexes
        if index.name == "uq_pre_submit_checker_current"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "pending_compilation" in postgres_compiled
    assert "compiled" in postgres_compiled


def test_policy_models_have_project_guide_foreign_keys() -> None:
    expected_constraints = {
        CheckerPolicy: "fk_checker_policies_project_guide",
        ReviewPolicy: "fk_review_policies_project_guide",
        RevisionPolicy: "fk_revision_policies_project_guide",
        PaymentPolicy: "fk_payment_policies_project_guide",
        PreSubmitCheckerPolicy: "fk_pre_submit_checker_policies_project_guide",
    }

    for model, constraint_name in expected_constraints.items():
        constraint = next(
            constraint
            for constraint in model.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )

        assert [column.name for column in constraint.columns] == ["project_id", "guide_version"]
        assert [element.column.table.name for element in constraint.elements] == [
            "project_guides",
            "project_guides",
        ]
        assert [element.column.name for element in constraint.elements] == ["project_id", "version"]


def test_submission_artifact_policy_models_are_registered_for_alembic_metadata() -> None:
    expected_tables = {
        "guide_source_snapshots",
        "guide_source_snapshot_items",
        "guide_sufficiency_reports",
        "submission_artifact_policies",
        "effective_project_submission_artifact_policies",
        "pre_submit_checker_policies",
    }

    assert expected_tables.issubset(Base.metadata.tables)


def test_submission_artifact_policy_models_bind_to_snapshot_hashes() -> None:
    expected_constraints = {
        GuideSufficiencyReport: "fk_guide_sufficiency_reports_source_snapshot_hash",
        SubmissionArtifactPolicy: "fk_submission_artifact_policies_source_snapshot_hash",
        EffectiveProjectSubmissionArtifactPolicy: "fk_effective_psap_source_snapshot_hash",
        PreSubmitCheckerPolicy: "fk_pre_submit_checker_policies_source_snapshot_hash",
    }

    for model, constraint_name in expected_constraints.items():
        constraint = next(
            constraint
            for constraint in model.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )

        assert [column.name for column in constraint.columns] == [
            "source_snapshot_id",
            "source_snapshot_hash",
        ]
        assert [element.column.table.name for element in constraint.elements] == [
            "guide_source_snapshots",
            "guide_source_snapshots",
        ]
        assert [element.column.name for element in constraint.elements] == ["id", "bundle_hash"]


def test_pre_submit_checker_policy_compiled_rows_require_bundle_fields() -> None:
    constraint = next(
        constraint
        for constraint in PreSubmitCheckerPolicy.__table__.constraints
        if constraint.name is not None
        and constraint.name.endswith("ck_pre_submit_checker_policies_compiled_fields")
    )

    constraint_sql = str(constraint.sqltext)

    assert "lifecycle_status" in constraint_sql
    assert "compiled_bundle_hash" in constraint_sql
    assert "compiled_bundle" in constraint_sql
    assert "compiler_version" in constraint_sql
    assert "sha256" in constraint_sql


def test_submission_artifact_policy_approval_requires_provenance() -> None:
    constraint = next(
        constraint
        for constraint in SubmissionArtifactPolicy.__table__.constraints
        if constraint.name is not None
        and constraint.name.endswith("ck_submission_artifact_policies_approval_provenance")
    )

    constraint_sql = str(constraint.sqltext)

    assert "approved_by_role" in constraint_sql
    assert "admin" in constraint_sql
    assert "project_manager" in constraint_sql
    assert "approved_by_actor" in constraint_sql
    assert "approved_at" in constraint_sql


def complete_guide_payload(version: str = "v1") -> dict:
    return {
        "version": version,
        "content_markdown": f"# Guide {version}",
        "required_task_fields": ["title", "description", "acceptance_criteria"],
        "required_submission_fields": ["summary", "evidence", "worker_attestation"],
        "task_instructions": "Do the task.",
        "output_requirements": "Submit a packet.",
        "acceptance_criteria": "Meets the guide.",
        "rejection_criteria": "Missing evidence.",
        "reviewer_rubric": "Check evidence and output.",
        "forbidden_actions": "No copied work.",
        "required_skills": ["stem"],
        "difficulty_scale": {"easy": 1, "hard": 3},
        "estimated_time_policy": {"default_minutes": 60},
        "common_rejection_reasons": ["missing evidence"],
        "evidence_policy": {"required": ["log"]},
        "unacceptable_work_policy": "Copied or unverifiable work.",
        "change_summary": f"Initial {version}",
        "checker_policy": {
            "required_checkers": ["check_policy_context_present"],
            "warning_checkers": [],
            "blocking_severities": ["high"],
        },
        "review_policy": {
            "requires_second_review": False,
            "allowed_decisions": ["accept", "needs_revision", "reject"],
            "minimum_finding_fields": ["issue", "required_fix"],
            "sla_hours": 24,
        },
        "revision_policy": {
            "max_revision_rounds": 7,
            "revision_deadline_hours": 48,
            "auto_reject_after_limit": True,
            "allowed_resubmission_states": ["needs_revision"],
            "reviewer_reassignment_rule": "same reviewer preferred",
        },
        "payment_policy": {
            "base_amount": "25.00",
            "currency": "USD",
            "payout_type": "fixed",
            "revision_payment_rule": "none",
            "rejection_payment_rule": "none",
            "accepted_payment_rule": "pay base amount",
        },
    }


async def create_project(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "STEM Eval",
            "slug": "stem-eval",
            "description": "Internal STEM evaluation tasks",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_guide(client: AsyncClient, project_id: str, payload: dict) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides",
        headers=auth_headers(),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def sha256_hash(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def source_snapshot_payload(*, durable_ref: str = "https://docs.flow.test/stem/guide.md") -> dict:
    return {
        "items": [
            {
                "source_kind": "url_doc",
                "durable_ref": durable_ref,
                "ingestion_adapter": "manual_import",
                "content_hash": sha256_hash("guide-doc"),
                "media_type": "text/markdown",
            },
            {
                "source_kind": "rubric",
                "durable_ref": "inline:/rubrics/stem-v1",
                "ingestion_adapter": "manual_import",
                "content_hash": sha256_hash("rubric"),
                "media_type": "text/markdown",
            },
        ]
    }


def project_submission_artifact_policy_body(
    *,
    artifact_path: str = "outputs/answer.md",
    manifest_required: bool = True,
    artifact_hash_required: bool = True,
    rule_hash_required: bool = True,
    packaging: dict | None = None,
) -> dict:
    return {
        "required_artifacts": [
            {
                "key": "answer",
                "path": artifact_path,
                "hash_required": rule_hash_required,
                "required": True,
                "description": "Final answer artifact.",
            }
        ],
        "required_evidence": [
            {
                "key": "reasoning_trace",
                "label": "Reasoning trace",
                "hash_required": rule_hash_required,
                "required": True,
                "description": "Evidence that supports the answer.",
            }
        ],
        "forbidden_artifacts": [
            {
                "pattern": "*.tmp",
                "reason": "Temporary files are not reviewable.",
                "worker_facing_fix": "Remove temporary files before submission.",
            }
        ],
        "attestation_terms": ["project_specific_originality"],
        "manifest_required": manifest_required,
        "artifact_hash_required": artifact_hash_required,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3", "r2"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": packaging if packaging is not None else {"package_required": False},
    }


async def create_source_snapshot(client: AsyncClient, project_id: str, guide_id: str) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots",
        headers=auth_headers(),
        json=source_snapshot_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_sufficiency_report(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    snapshot_id: str,
    *,
    status: str = "passed",
) -> dict:
    findings = []
    if status == "blocked":
        findings = [
            {
                "severity": "blocking_gap",
                "code": "missing_rubric",
                "message": "The guide needs a rubric.",
            }
        ]
    if status == "passed_with_warnings":
        findings = [
            {
                "severity": "warning",
                "code": "thin_examples",
                "message": "Examples are thin but usable.",
            }
        ]
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot_id,
            "status": status,
            "findings": findings,
            "summary": "Guide reviewed.",
            "agent_name": "ProjectGuideSufficiencyAgent",
            "agent_version": "v0.1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_submission_artifact_policy(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    snapshot_id: str,
    *,
    policy_body: dict | None = None,
    policy_version: str = "v1",
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot_id,
            "policy_version": policy_version,
            "policy_body": policy_body or project_submission_artifact_policy_body(),
            "derivation_source": "manual_admin_derivation",
            "derivation_agent_name": "SubmissionArtifactPolicyDerivationAgent",
            "derivation_agent_version": "v0.1",
            "change_summary": "Initial artifact intake policy.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def approve_submission_artifact_policy(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    policy_id: str,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/"
        f"{policy_id}/approve",
        headers=auth_headers(),
        json={"approval_note": "Approved by Workstream project manager."},
    )
    assert response.status_code == 200, response.text
    return response.json()


def canonical_json_hash(value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


async def mark_pre_submit_checker_policy_compiled(effective_policy: dict) -> dict:
    compiled_bundle = {
        "schema_version": "pre_submit_checker_bundle.v1",
        "compiler_version": "test-compiler-v0.1",
        "effective_policy_hash": effective_policy["effective_policy_hash"],
        "checks": [
            {
                "name": "require_submission_manifest",
                "severity": "blocking",
            },
            {
                "name": "require_artifact_hashes",
                "severity": "blocking",
            },
        ],
    }
    compiled_bundle_hash = canonical_json_hash(compiled_bundle)
    async with db_session.get_session_factory()() as session:
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy["id"]
            )
        )
        assert pre_submit_checker_policy is not None
        pre_submit_checker_policy.lifecycle_status = "compiled"
        pre_submit_checker_policy.compiler_version = "test-compiler-v0.1"
        pre_submit_checker_policy.compiled_bundle = compiled_bundle
        pre_submit_checker_policy.compiled_bundle_hash = compiled_bundle_hash
        pre_submit_checker_policy.checker_names = [
            "require_submission_manifest",
            "require_artifact_hashes",
        ]
        pre_submit_checker_policy.checker_configs = {}
        await session.commit()
    return {
        "compiled_bundle": compiled_bundle,
        "compiled_bundle_hash": compiled_bundle_hash,
    }


async def create_approved_policy_bundle(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    *,
    sufficiency_status: str = "passed",
    compile_pre_submit_checker: bool = True,
) -> dict:
    snapshot = await create_source_snapshot(client, project_id, guide_id)
    report = await create_sufficiency_report(
        client,
        project_id,
        guide_id,
        snapshot["id"],
        status=sufficiency_status,
    )
    policy = await create_submission_artifact_policy(client, project_id, guide_id, snapshot["id"])
    effective = await approve_submission_artifact_policy(
        client,
        project_id,
        guide_id,
        policy["id"],
    )
    compiled_pre_submit_checker = None
    if compile_pre_submit_checker:
        compiled_pre_submit_checker = await mark_pre_submit_checker_policy_compiled(effective)
    return {
        "source_snapshot": snapshot,
        "sufficiency_report": report,
        "submission_artifact_policy": policy,
        "effective_policy": effective,
        "pre_submit_checker_policy": compiled_pre_submit_checker,
    }


async def test_project_can_be_created(project_client: AsyncClient) -> None:
    project = await create_project(project_client)

    assert project["name"] == "STEM Eval"
    assert project["status"] == "draft"
    assert project["currency"] == "USD"


async def test_draft_guide_can_be_created(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    assert guide["version"] == "v1"
    assert guide["status"] == "draft"
    assert guide["created_by"]


async def test_source_snapshot_hash_is_server_computed_and_canonical(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    expected_manifest = {
        "schema_version": "guide_source_snapshot.v1",
        "items": sorted(
            [
                {
                    "source_kind": "url_doc",
                    "durable_ref": "https://docs.flow.test/stem/guide.md",
                    "ingestion_adapter": "manual_import",
                    "content_hash": sha256_hash("guide-doc"),
                    "content_cid": None,
                    "media_type": "text/markdown",
                },
                {
                    "source_kind": "rubric",
                    "durable_ref": "inline:/rubrics/stem-v1",
                    "ingestion_adapter": "manual_import",
                    "content_hash": sha256_hash("rubric"),
                    "content_cid": None,
                    "media_type": "text/markdown",
                },
            ],
            key=lambda item: (item["source_kind"], item["durable_ref"], item["content_hash"]),
        ),
    }
    expected_hash = "sha256:" + hashlib.sha256(
        json.dumps(
            expected_manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    assert snapshot["manifest_json"] == expected_manifest
    assert snapshot["bundle_hash"] == expected_hash
    assert [item["item_order"] for item in snapshot["items"]] == [0, 1]


async def test_source_snapshot_rejects_unsafe_refs(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots",
        headers=auth_headers(),
        json=source_snapshot_payload(
            durable_ref="https://docs.flow.test/guide.md?X-Amz-Signature=secret"
        ),
    )

    assert response.status_code == 422
    assert "query" in response.json()["detail"]


@pytest.mark.parametrize(
    ("durable_ref", "expected_detail"),
    [
        ("https://user:pass@docs.flow.test/guide.md", "credentials"),
        ("s3://workstream-guides/token/guide.md", "credential material"),
        ("file:///home/abiorh/guide.md", "scheme"),
        ("inline:/../guide.md", "path traversal"),
        ("inline:C:/Users/alice/guide.md", "local filesystem paths"),
        ("inline:C:\\Users\\alice\\guide.md", "local path separators"),
        ("import:\\\\server\\share\\guide.md", "local path separators"),
        ("import://server/share/guide.md", "network share authority"),
        ("inline://server/share/guide.md", "network share authority"),
        ("repo://server/share/guide.md", "network share authority"),
        ("import:////server/share/guide.md", "network share authority"),
        ("inline:////server/share/guide.md", "network share authority"),
        ("repo:////server/share/guide.md", "network share authority"),
        ("inline:~/guide.md", "local filesystem paths"),
        ("repo:~/guide.md", "local filesystem paths"),
        ("import:~/guide.md", "local filesystem paths"),
        ("s3://workstream-guides/%74oken/guide.md", "credential material"),
        ("s3://workstream-guides/%63redential/guide.md", "credential material"),
        ("s3://workstream-guides/%70assword/guide.md", "credential material"),
        ("inline:%2Fhome%2Fabiorh%2Fguide.md", "local filesystem paths"),
        ("repo:%2Ftmp%2Fguide.md", "local filesystem paths"),
        ("import:%2E%2E/guide.md", "path traversal"),
        ("inline:%5CUsers%5Calice%5Cguide.md", "local path separators"),
    ],
)
async def test_source_snapshot_rejects_credential_and_local_refs(
    project_client: AsyncClient,
    durable_ref: str,
    expected_detail: str,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots",
        headers=auth_headers(),
        json=source_snapshot_payload(durable_ref=durable_ref),
    )

    assert response.status_code == 422
    assert expected_detail in response.json()["detail"]


async def test_source_snapshot_rejects_unsafe_content_cid(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    payload = source_snapshot_payload()
    payload["items"][0]["content_cid"] = "https://storage.flow.test/doc?token=secret"

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "content CID" in response.json()["detail"]


async def test_source_snapshot_rejects_duplicate_source_items(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    payload = source_snapshot_payload()
    payload["items"][1]["source_kind"] = payload["items"][0]["source_kind"]
    payload["items"][1]["durable_ref"] = payload["items"][0]["durable_ref"]

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "duplicate source item" in response.json()["detail"]


async def test_submission_artifact_policy_approval_persists_effective_policy_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )

    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    assert policy["lifecycle_status"] == "draft"
    assert policy["policy_hash"].startswith("sha256:")
    assert effective["source_snapshot_id"] == snapshot["id"]
    assert effective["source_snapshot_hash"] == snapshot["bundle_hash"]
    assert effective["submission_artifact_policy_hash"] == policy["policy_hash"]
    assert effective["effective_policy_hash"].startswith("sha256:")
    assert effective["effective_policy"]["artifact_hash_algorithm"] == "sha256"

    async with db_session.get_session_factory()() as session:
        persisted_policy = await session.get(SubmissionArtifactPolicy, policy["id"])
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective["id"]
            )
        )

    assert persisted_policy is not None
    assert persisted_policy.lifecycle_status == "approved"
    assert persisted_policy.approved_by_role == "project_manager"
    assert persisted_policy.approved_by_actor == policy["created_by"]
    assert persisted_policy.approved_at is not None
    assert persisted_policy.derivation_source == "manual_admin_derivation"
    assert set(persisted_policy.source_material_refs) == {
        "https://docs.flow.test/stem/guide.md",
        "inline:/rubrics/stem-v1",
    }
    assert pre_submit_checker_policy is not None
    assert pre_submit_checker_policy.lifecycle_status == "pending_compilation"
    assert pre_submit_checker_policy.effective_policy_hash == effective["effective_policy_hash"]
    assert pre_submit_checker_policy.compiled_bundle_hash is None


async def test_submission_artifact_policy_approval_merges_packaging_rules(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_body=project_submission_artifact_policy_body(
            packaging={
                "package_required": True,
                "allowed_package_formats": ["zip", "tar"],
            }
        ),
    )

    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    assert effective["effective_policy"]["packaging"] == {
        "package_required": True,
        "allowed_package_formats": ["tar", "zip"],
    }
    assert "workstream_default" not in effective["effective_policy"]["packaging"]
    assert "project" not in effective["effective_policy"]["packaging"]


async def test_approved_submission_artifact_policy_is_immutable(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    await approve_submission_artifact_policy(project_client, project["id"], guide["id"], policy["id"])

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}",
        headers=auth_headers(),
        json={"change_summary": "Try to mutate approved policy."},
    )

    assert response.status_code == 409
    assert "immutable" in response.json()["detail"]


async def test_draft_submission_artifact_policy_can_be_updated(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}",
        headers=auth_headers(),
        json={
            "policy_body": project_submission_artifact_policy_body(
                artifact_path="outputs/final-answer.md"
            ),
            "change_summary": "Use final answer artifact path.",
        },
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == policy["id"]
    assert updated["lifecycle_status"] == "draft"
    assert updated["policy_hash"] != policy["policy_hash"]
    assert updated["policy_body"]["required_artifacts"][0]["path"] == (
        "outputs/final-answer.md"
    )
    assert updated["change_summary"] == "Use final answer artifact path."


async def test_approving_replacement_policy_supersedes_prior_rows(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    first_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_version="v1",
    )
    first_effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        first_policy["id"],
    )
    second_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_body=project_submission_artifact_policy_body(
            artifact_path="outputs/final-answer.md"
        ),
        policy_version="v2",
    )

    second_effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        second_policy["id"],
    )

    async with db_session.get_session_factory()() as session:
        first_persisted = await session.get(SubmissionArtifactPolicy, first_policy["id"])
        second_persisted = await session.get(SubmissionArtifactPolicy, second_policy["id"])
        first_effective_persisted = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            first_effective["id"],
        )
        second_effective_persisted = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            second_effective["id"],
        )
        pre_submit_rows = (
            await session.scalars(
                select(PreSubmitCheckerPolicy).where(
                    PreSubmitCheckerPolicy.project_id == project["id"],
                    PreSubmitCheckerPolicy.guide_version == guide["version"],
                )
            )
        ).all()

    assert len(pre_submit_rows) == 2
    assert first_persisted is not None
    assert second_persisted is not None
    assert first_effective_persisted is not None
    assert second_effective_persisted is not None
    assert first_persisted.lifecycle_status == "superseded"
    assert first_persisted.superseded_at is not None
    assert second_persisted.lifecycle_status == "approved"
    assert second_persisted.supersedes_policy_id == first_persisted.id
    assert first_effective_persisted.lifecycle_status == "superseded"
    assert first_effective_persisted.superseded_at is not None
    assert second_effective_persisted.lifecycle_status == "approved"
    assert second_effective_persisted.supersedes_effective_policy_id == (
        first_effective_persisted.id
    )
    assert {row.lifecycle_status for row in pre_submit_rows} == {
        "pending_compilation",
        "superseded",
    }
    current_pre_submit = next(
        row for row in pre_submit_rows if row.lifecycle_status == "pending_compilation"
    )
    superseded_pre_submit = next(
        row for row in pre_submit_rows if row.lifecycle_status == "superseded"
    )
    assert current_pre_submit.effective_policy_id == second_effective_persisted.id
    assert current_pre_submit.supersedes_pre_submit_checker_policy_id == (
        superseded_pre_submit.id
    )
    assert superseded_pre_submit.effective_policy_id == first_effective_persisted.id
    assert superseded_pre_submit.superseded_at is not None


async def test_material_guide_edit_after_source_snapshot_is_blocked(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    await create_source_snapshot(project_client, project["id"], guide["id"])

    response = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"content_markdown": "# Drift after snapshot"},
    )

    assert response.status_code == 409
    assert "source material" in response.json()["detail"]


async def test_activation_rejects_policy_bound_to_stale_source_snapshot(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    first_snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], first_snapshot["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        first_snapshot["id"],
    )
    await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )
    newer_payload = source_snapshot_payload(
        durable_ref="https://docs.flow.test/stem/guide-v2.md"
    )
    newer_response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/source-snapshots",
        headers=auth_headers(),
        json=newer_payload,
    )
    assert newer_response.status_code == 201, newer_response.text

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "stale" in response.json()["detail"]


async def test_draft_policy_cannot_be_approved_after_guide_activation(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    first_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_version="v1",
    )
    second_policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        policy_version="v2",
    )
    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        first_policy["id"],
    )
    await mark_pre_submit_checker_policy_compiled(effective)
    activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )
    assert activation.status_code == 200, activation.text

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{second_policy['id']}/approve",
        headers=auth_headers(),
        json={"approval_note": "late drift"},
    )

    assert response.status_code == 409
    assert "draft guides" in response.json()["detail"]


async def test_submission_artifact_policy_rejects_default_weakening(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(
                manifest_required=False,
            ),
        },
    )

    assert response.status_code == 422
    assert "manifest" in response.json()["detail"]


async def test_submission_artifact_policy_rejects_rule_hash_weakening(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(
                rule_hash_required=False,
            ),
        },
    )

    assert response.status_code == 422
    assert "hash_required" in response.text


async def test_submission_artifact_policy_rejects_arbitrary_packaging_refs(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(
                packaging={
                    "package_required": False,
                    "template_url": "https://storage.flow.test/pkg?token=secret",
                },
            ),
        },
    )

    assert response.status_code == 422
    assert "extra" in response.text


async def test_submission_artifact_policy_rejects_forbidden_required_artifacts(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": project_submission_artifact_policy_body(artifact_path=".env"),
        },
    )

    assert response.status_code == 422
    assert "forbidden artifacts" in response.json()["detail"]


async def test_blocking_sufficiency_report_prevents_activation(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    await create_approved_policy_bundle(
        project_client,
        project["id"],
        guide["id"],
        sufficiency_status="blocked",
    )

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "blocking gaps" in response.json()["detail"]


async def test_sufficiency_warnings_require_acknowledgement(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(
        project_client,
        project["id"],
        guide["id"],
        sufficiency_status="passed_with_warnings",
    )

    blocked = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )
    assert blocked.status_code == 422
    assert "warnings require acknowledgement" in blocked.json()["detail"]

    acknowledgement = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports/"
        f"{bundle['sufficiency_report']['id']}/acknowledge-warnings",
        headers=auth_headers(),
        json={"acknowledgement_note": "Accepted with known thin examples."},
    )
    assert acknowledgement.status_code == 200, acknowledgement.text
    assert acknowledgement.json()["warnings_acknowledged_by_role"] == "project_manager"

    activated = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )
    assert activated.status_code == 200, activated.text


async def test_worker_cannot_approve_submission_artifact_policy(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    policy = await create_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
    )
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "worker")
    get_settings.cache_clear()

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies/"
        f"{policy['id']}/approve",
        headers=auth_headers(),
        json={"approval_note": "forged"},
    )

    assert response.status_code == 403


async def test_activation_requires_submission_artifact_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["evidence_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "approved submission artifact policy" in response.json()["detail"]


async def test_activation_does_not_require_legacy_evidence_policy(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["evidence_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 200, response.text


async def test_activation_requires_all_policies(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["checker_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "checker policy" in response.json()["detail"]


async def test_activation_requires_review_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["review_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "review policy" in response.json()["detail"]


async def test_activation_requires_payment_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["payment_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "payment policy is required" in response.json()["detail"]


async def test_activation_requires_revision_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"] = None
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "revision policy is required" in response.json()["detail"]


async def test_review_policy_rejects_invalid_decision_names(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["review_policy"]["allowed_decisions"] = ["accept", "hold"]

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "allowed_decisions" in detail["loc"]
    assert detail["input"] == "hold"


async def test_activation_requires_complete_payment_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["payment_policy"]["accepted_payment_rule"] = None
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "payment policy is incomplete" in response.json()["detail"]


async def test_activation_requires_complete_revision_policy(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"]["allowed_resubmission_states"] = []
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "revision policy is incomplete" in response.json()["detail"]


async def test_revision_policy_requires_deadline(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    del payload["revision_policy"]["revision_deadline_hours"]

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "revision_deadline_hours" in detail["loc"]


async def test_activation_rejects_unregistered_checker_names(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["checker_policy"]["required_checkers"] = ["missing_checker"]
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "unregistered checker policy names" in response.json()["detail"]


async def test_activation_rejects_unsupported_revision_resubmission_states(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    payload = complete_guide_payload()
    payload["revision_policy"]["allowed_resubmission_states"] = ["random_state"]
    guide = await create_guide(project_client, project["id"], payload)
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "invalid resubmission states" in response.json()["detail"]


async def test_activation_rejects_pending_pre_submit_checker_policy(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    await create_approved_policy_bundle(
        project_client,
        project["id"],
        guide["id"],
        compile_pre_submit_checker=False,
    )

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "compiled project pre-submit checker policy" in response.json()["detail"]


async def test_activation_rejects_mismatched_pre_submit_checker_bundle_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(project_client, project["id"], guide["id"])
    async with db_session.get_session_factory()() as session:
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == bundle["effective_policy"]["id"]
            )
        )
        assert pre_submit_checker_policy is not None
        pre_submit_checker_policy.compiled_bundle_hash = sha256_hash("wrong-compiled-bundle")
        await session.commit()

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "compiled bundle hash mismatch" in response.json()["detail"]


async def test_guide_activation_and_active_guide_retrieval(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )
    active = await project_client.get(
        f"/api/v1/projects/{project['id']}/active-guide",
        headers=auth_headers(),
    )

    assert activation.status_code == 200, activation.text
    assert active.status_code == 200, active.text
    assert active.json()["guide"]["status"] == "active"
    assert active.json()["guide"]["version"] == "v1"
    assert active.json()["checker_policy"]["required_checkers"] == [
        "check_policy_context_present"
    ]
    assert active.json()["guide_source_snapshot"]["bundle_hash"] == (
        bundle["source_snapshot"]["bundle_hash"]
    )
    assert active.json()["guide_sufficiency_report"]["status"] == "passed"
    assert active.json()["submission_artifact_policy"]["lifecycle_status"] == "approved"
    assert active.json()["effective_submission_artifact_policy"]["effective_policy_hash"] == (
        bundle["effective_policy"]["effective_policy_hash"]
    )
    assert active.json()["pre_submit_checker_policy"]["lifecycle_status"] == "compiled"
    assert active.json()["pre_submit_checker_policy"]["effective_policy_id"] == (
        bundle["effective_policy"]["id"]
    )
    assert active.json()["pre_submit_checker_policy"]["compiled_bundle_hash"] == (
        bundle["pre_submit_checker_policy"]["compiled_bundle_hash"]
    )
    assert active.json()["revision_policy"]["max_revision_rounds"] == 7
    assert active.json()["revision_policy"]["auto_reject_after_limit"] is True
    assert active.json()["payment_policy"]["base_amount"] == "25.00"


async def test_draft_guide_edit_and_active_guide_edit_block(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())

    draft_update = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={
            "content_markdown": "# Updated draft",
            "evidence_policy": {"required": ["log", "hash"]},
        },
    )
    assert draft_update.status_code == 200, draft_update.text
    assert draft_update.json()["content_markdown"] == "# Updated draft"
    await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )
    assert activation.status_code == 200, activation.text

    active_update = await project_client.patch(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        headers=auth_headers(),
        json={"content_markdown": "# Mutate active"},
    )
    assert active_update.status_code == 409


async def test_new_active_guide_supersedes_prior_without_mutating_content(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    first = await create_guide(project_client, project["id"], complete_guide_payload("v1"))
    await create_approved_policy_bundle(project_client, project["id"], first["id"])
    first_activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{first['id']}/activate",
        headers=auth_headers(),
    )
    assert first_activation.status_code == 200, first_activation.text

    second = await create_guide(project_client, project["id"], complete_guide_payload("v2"))
    await create_approved_policy_bundle(project_client, project["id"], second["id"])
    second_activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{second['id']}/activate",
        headers=auth_headers(),
    )

    assert second_activation.status_code == 200, second_activation.text
    assert second_activation.json()["guide"]["version"] == "v2"

    async with db_session.get_session_factory()() as session:
        first_guide = await session.get(ProjectGuide, first["id"])

    assert first_guide is not None
    assert first_guide.status == "superseded"
    assert first_guide.content_markdown == "# Guide v1"


async def test_database_enforces_single_active_guide_per_project(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    first = await create_guide(project_client, project["id"], complete_guide_payload("v1"))
    second = await create_guide(project_client, project["id"], complete_guide_payload("v2"))

    async with db_session.get_session_factory()() as session:
        first_guide = await session.get(ProjectGuide, first["id"])
        second_guide = await session.get(ProjectGuide, second["id"])
        assert first_guide is not None
        assert second_guide is not None
        first_guide.status = "active"
        second_guide.status = "active"
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_active_guide_lookup_surfaces_duplicate_rows() -> None:
    guides = [
        ProjectGuide(id="guide-1", project_id="project-1", version="v1", status="active"),
        ProjectGuide(id="guide-2", project_id="project-1", version="v2", status="active"),
    ]

    class FakeScalars:
        def all(self) -> list[ProjectGuide]:
            return guides

    class FakeResult:
        def scalars(self) -> FakeScalars:
            return FakeScalars()

    class FakeSession:
        async def execute(self, statement) -> FakeResult:
            return FakeResult()

    with pytest.raises(ProjectRepositoryIntegrityError, match="multiple active guides"):
        await ProjectRepository(FakeSession()).get_active_guide("project-1")


async def test_activation_conflict_returns_conflict_response(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_project(project_client)
    first = await create_guide(project_client, project["id"], complete_guide_payload("v1"))
    await create_approved_policy_bundle(project_client, project["id"], first["id"])
    first_activation = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{first['id']}/activate",
        headers=auth_headers(),
    )
    assert first_activation.status_code == 200, first_activation.text

    second = await create_guide(project_client, project["id"], complete_guide_payload("v2"))
    await create_approved_policy_bundle(project_client, project["id"], second["id"])

    async def hide_active_guides(self: ProjectRepository, project_id: str) -> list[ProjectGuide]:
        return []

    monkeypatch.setattr(ProjectRepository, "list_active_guides", hide_active_guides)

    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{second['id']}/activate",
        headers=auth_headers(),
    )

    assert response.status_code == 409
    assert "concurrent update" in response.json()["detail"]


async def test_worker_cannot_create_project_records(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "worker")
    get_settings.cache_clear()

    response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={"name": "Worker Project", "slug": "worker-project"},
    )

    assert response.status_code == 403


async def test_project_create_validation_errors_are_structured(project_client: AsyncClient) -> None:
    response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={"slug": "missing-name"},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
