"""Closed callback inputs and actual-versus-reservation trial provenance."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from app.adapters.checkers.trial_proxy import CheckerTrialProxy, _receipt_bytes, _validate_receipt
from app.core.identifiers import new_record_id
from app.modules.checkers.api.external import external_checker_json_hash
from app.modules.checkers.api.trial_evidence import TrialEvidenceOrigin, TrialEvidenceTicket
from tests.checkers.external.support import execution_identity
from tests.checkers.external.test_trial_evidence import _subject
from tests.checkers.external.test_trial_profiles import digest, profile, projection, configuration


def _receipt_case():
    selected = profile()
    projected = projection(selected)
    identity = execution_identity("post_submit")
    external = SimpleNamespace(
        identity=identity, input={"requirement_id": "project.execution"},
        registry=SimpleNamespace(registry_entry_id=new_record_id(), entry_digest=digest("a"), image_digest=digest("b")),
        configuration=configuration(selected, projected), configuration_sha256=digest("c"),
        input_sha256=digest("d"), materials=(), request_digest=digest("e"),
    )
    plan, execution = {"steps": [{"slot_id": "reference-1"}]}, {"steps": [{"outcome": "succeeded"}]}
    subject = _subject(external, projected).model_copy(update={"plan_sha256": external_checker_json_hash(plan)})
    origin = TrialEvidenceOrigin(
        checker_run_id=identity.attempt_id, worker_lease_id=identity.lease_id,
        worker_lease_generation=identity.lease_generation, worker_lease_expires_at=identity.lease_expires_at,
        external_request_digest=external.request_digest,
    )
    ticket = TrialEvidenceTicket(
        trial_evidence_id=new_record_id(), subject=subject, origin=origin,
        slot={"maximum_bytes": 1_048_576}, content_sha256=None, replayed=False,
    )
    provenance = subject.model_dump(mode="json", exclude={"plan_sha256", "trial_kind", "slot_index"}) | {
        "request_digest": external.request_digest, "material_binding_digest": digest("f"),
        "checker_image_digest": external.registry.image_digest,
        "checker_run_id": str(identity.attempt_id), "attempt_id": str(identity.attempt_id),
        "evaluation_request_id": str(identity.evaluation_request_id),
        "evaluation_generation": identity.evaluation_generation,
        "result_id": str(identity.result_id),
        "worker_lease_id": str(identity.lease_id), "worker_lease_generation": identity.lease_generation,
        "worker_lease_expires_at": identity.model_dump(mode="json")["lease_expires_at"],
    }
    value = {
        "schema_version": "workstream.checker_trial_receipt.v1",
        "request_identity_digest": external.request_digest, "originating_identity": provenance,
        "material_binding_digest": digest("f"), "profile_id": str(selected.selector.profile_id),
        "profile_version": selected.selector.profile_version, "profile_digest": selected.selector.profile_digest,
        "trial_kind": projected.trial_kind, "engine_identity_digest": selected.engine_identity_digest,
        "plan_digest": subject.plan_sha256, "observation_digest": external_checker_json_hash(execution),
        "observation_byte_count": len(json.dumps(execution, sort_keys=True, separators=(",", ":")).encode()),
        "slot_ids": ["reference-1"], "plan_started": True, "plan_completed": True,
        "cleanup_confirmed": True, "plan": plan, "execution": execution,
    }
    return value, ticket, external, selected


def test_trial_receipt_rejects_plan_runtime_origin_and_observation_substitution():
    value, ticket, external, selected = _receipt_case()
    _validate_receipt(value, ticket, external, selected)
    for key, changed in (
        ("plan_digest", digest("0")), ("engine_identity_digest", digest("0")),
        ("observation_digest", digest("0")), ("observation_byte_count", True),
        ("plan_completed", False), ("slot_ids", ["invented"]),
        ("originating_identity", value["originating_identity"] | {"worker_lease_id": str(new_record_id())}),
        ("originating_identity", value["originating_identity"] | {"extra": "untrusted"}),
    ):
        with pytest.raises(ValueError):
            _validate_receipt(value | {key: changed}, ticket, external, selected)


def test_pending_reservation_can_publish_from_current_retry_without_fake_origin():
    value, ticket, external, selected = _receipt_case()
    old_origin = ticket.origin.model_copy(update={
        "checker_run_id": new_record_id(), "worker_lease_id": new_record_id(),
        "external_request_digest": digest("0"),
    })
    pending = ticket.model_copy(update={"origin": old_origin, "replayed": True})
    _validate_receipt(value, pending, external, selected)
    assert pending.origin != ticket.origin
    # Reservation provenance cannot be substituted for the executor that did
    # the work after recovery. It remains separate immutable historical data.
    forged = value | {"originating_identity": value["originating_identity"] | {
        "worker_lease_id": str(old_origin.worker_lease_id),
    }}
    with pytest.raises(ValueError, match="origin"):
        _validate_receipt(forged, pending, external, selected)


def test_receipt_bytes_must_be_exact_canonical_json_without_duplicate_fields():
    def command(raw):
        return SimpleNamespace(
            canonical_receipt_utf8=raw, byte_count=len(raw.encode()),
            content_sha256="sha256:" + hashlib.sha256(raw.encode()).hexdigest(),
        )

    raw, value = _receipt_bytes(command('{"result":"observed"}'))
    assert raw == b'{"result":"observed"}' and value == {"result": "observed"}
    for malformed in ('{"result":"a","result":"b"}', '{"result": "a"}', '[]', '{"result":NaN}'):
        with pytest.raises(ValueError):
            _receipt_bytes(command(malformed))


@pytest.mark.parametrize("payload", [None, [], {}, {"operation": []},
                                        {"operation": "reserve", "extra": "unknown"}])
async def test_malformed_callback_never_reaches_owner_storage_or_model(payload):
    def forbidden(*args):
        pytest.fail("invalid callback reached an effectful owner")

    proxy = CheckerTrialProxy(
        sessions=forbidden, reservations=forbidden, outputs=forbidden,
        bindings=forbidden, profiles=forbidden,
    )
    reply = await proxy.handle(payload)
    assert reply["outcome"] == "unavailable" and reply["failure_code"] == "trial_request_invalid"
    assert set(reply) == {"protocol_version", "operation", "outcome", "failure_code"}
