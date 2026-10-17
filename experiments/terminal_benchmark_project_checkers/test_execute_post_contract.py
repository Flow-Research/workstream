#!/usr/bin/env python3
"""Regression for the strict JSON registry boundary used by the POST driver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID
import unittest

from app.core.identifiers import new_record_id
from app.modules.checkers.api.external import PostSubmitExternalCheckerIdentity
from execute_post import _post_material, _registry_entry_from_json
from prepare_contract import _registry_entry


class RegistryJsonBoundaryTests(unittest.TestCase):
    def test_registry_entry_round_trips_through_strict_json_validation(self) -> None:
        expected = _registry_entry("sha256:" + "a" * 64)

        restored = _registry_entry_from_json(expected.model_dump(mode="json"))

        self.assertEqual(restored, expected)
        self.assertIsInstance(restored.registry_entry_id, UUID)
        self.assertIsInstance(restored.registration_operation_id, UUID)
        self.assertIsInstance(restored.registered_by_actor_profile_id, UUID)
        self.assertIsInstance(restored.authorization_decision_event_id, UUID)

    def test_post_material_uses_the_runtime_grant_archive_role(self) -> None:
        identifiers = [new_record_id() for _ in range(14)]
        identity = PostSubmitExternalCheckerIdentity(
            project_id=identifiers[0],
            task_id=identifiers[1],
            assignment_id=identifiers[2],
            submission_id=identifiers[3],
            submission_version=1,
            evaluation_request_id=identifiers[4],
            evaluation_request_digest="sha256:" + "1" * 64,
            evaluation_generation=1,
            attempt_id=identifiers[5],
            result_id=identifiers[6],
            lease_id=identifiers[7],
            lease_generation=1,
            lease_expires_at=datetime(2026, 10, 17, tzinfo=timezone.utc)
            + timedelta(hours=1),
        )

        material = _post_material(
            identity,
            identifiers,
            (),
            "sha256:" + "2" * 64,
        )

        self.assertEqual(material.role, "submission_archive")


if __name__ == "__main__":
    unittest.main()
