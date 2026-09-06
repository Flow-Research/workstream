"""Controlled PROJECT policy-read rows; not a database or authorization fake."""

from __future__ import annotations

from datetime import UTC, datetime
import types
from typing import Any
from uuid import uuid4

from app.core.hashing import canonical_json_hash


class _PolicyReadRepository:
    def __init__(self) -> None:
        self._initialize_source()
        self._initialize_intake()
        self._initialize_review()

    def _initialize_source(self) -> None:
        self.project_id, self.guide_id, self.snapshot_id = (str(uuid4()) for _ in range(3))
        self.project = types.SimpleNamespace(id=self.project_id, status="active")
        self.guide = types.SimpleNamespace(
            id=self.guide_id,
            project_id=self.project_id,
            version="v1",
            status="active",
        )
        source_row = {
            "item_id": str(uuid4()),
            "item_order": 0,
            "source_kind": "guide",
            "source_label": "guide.md",
            "ingestion_adapter": "test",
            "media_type": "text/markdown",
        }
        manifest = {
            "schema_version": "guide_source_snapshot.v2",
            "snapshot_id": self.snapshot_id,
            "generation": 1,
            "items": [source_row],
        }
        self.snapshot = types.SimpleNamespace(
            id=self.snapshot_id,
            project_id=self.project_id,
            guide_id=self.guide_id,
            guide_version="v1",
            manifest_schema_version="guide_source_snapshot.v2",
            creation_generation=1,
            manifest_json=manifest,
            bundle_hash=canonical_json_hash(manifest),
        )
        self.source_items = (
            types.SimpleNamespace(
                id=str(uuid4()), source_snapshot_id=self.snapshot_id, **source_row
            ),
        )

    def _initialize_intake(self) -> None:
        submission_body = {"allowed": ["zip"]}
        effective_body = {"allowed": ["zip"], "max_bytes": 10}
        checker_bundle = {"checkers": ["safe"]}
        self.effective = types.SimpleNamespace(
            id=str(uuid4()),
            project_id=self.project_id,
            guide_id=self.guide_id,
            guide_version="v1",
            source_snapshot_id=self.snapshot_id,
            source_snapshot_hash=self.snapshot.bundle_hash,
            submission_artifact_policy_id=str(uuid4()),
            submission_artifact_policy_hash=canonical_json_hash(submission_body),
            effective_policy=effective_body,
            effective_policy_hash=canonical_json_hash(effective_body),
            lifecycle_status="approved",
        )
        self.checker = types.SimpleNamespace(
            id=str(uuid4()),
            project_id=self.project_id,
            guide_id=self.guide_id,
            guide_version="v1",
            source_snapshot_id=self.snapshot_id,
            source_snapshot_hash=self.snapshot.bundle_hash,
            effective_policy_id=self.effective.id,
            effective_policy_hash=self.effective.effective_policy_hash,
            lifecycle_status="compiled",
            compiled_bundle=checker_bundle,
            compiled_bundle_hash=canonical_json_hash(checker_bundle),
        )
        self.submission = types.SimpleNamespace(
            id=self.effective.submission_artifact_policy_id,
            project_id=self.project_id,
            guide_id=self.guide_id,
            guide_version="v1",
            source_snapshot_id=self.snapshot_id,
            source_snapshot_hash=self.snapshot.bundle_hash,
            policy_body=submission_body,
            policy_hash=self.effective.submission_artifact_policy_hash,
            lifecycle_status="approved",
            approved_by_actor="actor",
            approved_at=datetime.now(UTC),
            approved_by_role="project_manager",
        )

    def _initialize_review(self) -> None:
        self.sufficiency = types.SimpleNamespace(
            id=str(uuid4()),
            project_id=self.project_id,
            guide_id=self.guide_id,
            guide_version="v1",
            source_snapshot_id=self.snapshot_id,
            source_snapshot_hash=self.snapshot.bundle_hash,
            status="passed",
            warnings_acknowledged_by_actor=None,
            warnings_acknowledged_at=None,
            warnings_acknowledged_by_role=None,
        )
        post_body = {"required_checkers": ["safe"]}
        self.post_submit = types.SimpleNamespace(
            id=str(uuid4()),
            project_id=self.project_id,
            guide_id=self.guide_id,
            guide_version="v1",
            source_snapshot_id=self.snapshot_id,
            source_snapshot_hash=self.snapshot.bundle_hash,
            effective_policy_id=self.effective.id,
            effective_policy_hash=self.effective.effective_policy_hash,
            pre_submit_checker_policy_id=self.checker.id,
            pre_submit_checker_bundle_hash=self.checker.compiled_bundle_hash,
            lifecycle_status="approved",
            approved_by_actor="actor",
            approved_at=datetime.now(UTC),
            approved_by_role="project_manager",
            policy_body=post_body,
            policy_hash=canonical_json_hash(post_body),
        )
        self.review = types.SimpleNamespace(
            id=str(uuid4()),
            project_id=self.project_id,
            guide_version="v1",
            allowed_decisions=["accept", "needs_revision", "reject"],
        )
        self.revision = types.SimpleNamespace(
            id=str(uuid4()),
            project_id=self.project_id,
            guide_version="v1",
            max_revision_rounds=2,
        )

    async def get_project(self, _project_id: str, *, for_update: bool = False) -> Any:
        assert for_update is True
        return self.project

    async def lock_project_guide(self, _guide_id: str) -> Any:
        return self.guide

    async def lock_latest_guide_source_snapshot(self, *_args: Any) -> Any:
        return self.snapshot

    async def lock_effective_submission_artifact_policy(self, *_args: Any) -> Any:
        return self.effective

    async def lock_guide_source_snapshot_items(self, *_args: Any) -> Any:
        return self.source_items

    async def lock_compiled_pre_submit_checker_policy(self, *_args: Any) -> Any:
        return self.checker

    async def lock_active_guide(self, *_args: Any) -> Any:
        return self.guide

    async def get_sufficiency_report_for_snapshot(self, *_args: Any) -> Any:
        return self.sufficiency

    async def lock_guide_sufficiency_report(self, *_args: Any) -> Any:
        return self.sufficiency

    async def lock_submission_artifact_policy(self, *_args: Any) -> Any:
        return self.submission

    async def lock_post_submit_checker_policy_for_guide(self, *_args: Any) -> Any:
        return self.post_submit

    async def lock_review_policy(self, *_args: Any) -> Any:
        return self.review

    async def lock_revision_policy(self, *_args: Any) -> Any:
        return self.revision
