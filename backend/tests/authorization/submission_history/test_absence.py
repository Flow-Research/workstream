"""Removed authority and alternate execution cannot re-enter the v0.1 surface."""

from pathlib import Path

from app.main import create_app
from app.schemas.auth import AuthVerificationResult


def test_removed_mutation_and_worker_surface():
    root = Path(__file__).resolve().parents[3] / "app"
    forbidden = (
        "get_registered_actor", "LegacyAuthorizationCompatibilityContext", "ActorContext",
        "normalize_legacy_roles", "dev_auth_roles", "require_any_role", "legacy_actor(",
        "refresh_legacy_identity", "upsert_legacy_identity", "pre_review_gate_system_actor",
        "enqueue_pre_review_gate", "app.workers.checkers",
    )
    for path in root.rglob("*.py"):
        source = path.read_text()
        assert not any(symbol in source for symbol in forbidden), path
    for relative in ("core/permissions.py", "modules/tasks/authorization.py", "modules/checkers/service.py",
                     "modules/checkers/gate_queue.py", "modules/checkers/pre_review_gate.py", "workers/checkers.py"):
        assert not (root / relative).exists()
    paths = create_app().openapi()["paths"]
    assert "/api/v1/submissions/{submission_id}/finalize" not in paths
    assert "post" not in paths["/api/v1/submissions/{submission_id}/checker-runs"]
    assert set(AuthVerificationResult.model_fields) == {"token"}


def test_fixed_public_history_schemas():
    schemas = create_app().openapi()["components"]["schemas"]
    for name in ("ContributorSubmissionHistory", "ManagementSubmissionHistory",
                 "ContributorCheckerHistory", "ManagementCheckerHistory",
                 "ContributorCheckerResult", "ManagementCheckerResult", "SubmissionEvidenceDescriptor"):
        fields = schemas[name]["properties"]
        assert schemas[name]["additionalProperties"] is False
        assert not set(fields) & {"package_uri", "package_hash", "metadata", "artifact_hash_manifest",
                                  "worker_attestation", "locked_payment_policy_version", "triggered_by_subject",
                                  "triggered_by_issuer", "audit_event_id", "worker_evidence_refs"}
    assert "message" not in schemas["ContributorCheckerResult"]["properties"]
    assert "routing_recommendation" not in schemas["ContributorCheckerHistory"]["properties"]
    assert "contributor_id" not in schemas["ContributorSubmissionHistory"]["properties"]
