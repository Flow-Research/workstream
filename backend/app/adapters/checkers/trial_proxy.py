"""Compose durable sandbox receipt callbacks with CHECKERS and existing ART."""

import hashlib
import json

from pydantic import ValidationError

from app.interfaces.checker_trial_proxy import (
    TRIAL_PROXY_MAXIMUM_FRAME_BYTES, TRIAL_PROXY_PROTOCOL, TRIAL_PROXY_REQUEST,
    TrialPublishRequest, TrialReserveRequest,
)
from app.modules.checkers.api.external import external_checker_json_hash
from app.modules.checkers.api.output_custody import CheckerOutputUnavailable
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceArtifactRequest, TrialEvidenceBindingRequest, TrialEvidenceSelector,
    TrialEvidenceStableSubject, TrialEvidenceUnavailable,
)
from app.modules.checkers.api.trial_profiles import (
    TrialAuthorityContext,
    TrialProfileError,
    trial_selector_from_configuration,
)


def _closed_json_pairs(pairs):
    """Reject duplicate keys before any JSON receipt can become retained evidence."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate trial receipt field")
        result[key] = value
    return result


def _receipt_bytes(request: TrialPublishRequest):
    """Verify exact UTF-8 size, canonical JSON and the independently computed hash."""
    raw = request.canonical_receipt_utf8.encode("utf-8")
    if len(raw) != request.byte_count or len(raw) > 1_048_576:
        raise ValueError("trial receipt size differs")
    value = json.loads(raw, object_pairs_hook=_closed_json_pairs)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if not isinstance(value, dict) or digest != request.content_sha256 or (
        external_checker_json_hash(value) != digest
    ):
        raise ValueError("trial receipt content differs")
    return raw, value


def _receipt_subject(external, value):
    """Derive the immutable address from the trusted invocation and supplied plan."""
    identity = external.identity
    return TrialEvidenceStableSubject(
        project_id=identity.project_id, task_id=identity.task_id,
        assignment_id=identity.assignment_id, submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        requirement_id=external.input["requirement_id"],
        registry_entry_id=external.registry.registry_entry_id,
        registry_entry_digest=external.registry.entry_digest,
        configuration_sha256=external.configuration_sha256,
        trial_kind=value["trial_kind"], slot_index=0, plan_sha256=value["plan_digest"],
        input_digest=external.input_sha256,
        materials_digest=external_checker_json_hash([
            item.model_dump(mode="json") for item in external.materials
        ]),
    )


def _validate_receipt(value, ticket, external, profile):
    """Match the actual plan, immutable origin and observations before ART writes."""
    fields = {
        "schema_version", "request_identity_digest", "originating_identity",
        "material_binding_digest", "profile_id", "profile_version", "profile_digest",
        "trial_kind", "engine_identity_digest", "plan_digest", "observation_digest",
        "observation_byte_count", "slot_ids", "plan_started", "plan_completed",
        "cleanup_confirmed", "plan", "execution",
    }
    if set(value) != fields or value["schema_version"] != "workstream.checker_trial_receipt.v1":
        raise ValueError("trial receipt shape differs")
    subject = ticket.subject
    identity = value["originating_identity"]
    identity_fields = {
        "request_digest", "material_binding_digest", "input_digest", "materials_digest",
        "project_id", "task_id", "assignment_id", "submission_id", "submission_version",
        "requirement_id", "registry_entry_id", "registry_entry_digest", "checker_image_digest",
        "configuration_sha256", "evaluation_request_id", "evaluation_generation",
        "checker_run_id", "attempt_id", "result_id", "worker_lease_id",
        "worker_lease_generation", "worker_lease_expires_at",
    }
    if not isinstance(identity, dict) or set(identity) != identity_fields or any(
        value[name] is not True for name in ("plan_started", "plan_completed", "cleanup_confirmed")
    ):
        raise ValueError("trial receipt is incomplete")
    for name in (
        "project_id", "task_id", "assignment_id", "submission_id", "submission_version",
        "requirement_id", "registry_entry_id", "registry_entry_digest", "configuration_sha256",
        "input_digest", "materials_digest",
    ):
        if identity.get(name) != subject.model_dump(mode="json")[name]:
            raise ValueError("trial receipt subject differs")
    # Reservation provenance survives a crash before execution. The first
    # content must attest the actual current executor; pinned content instead
    # remains byte-identical even after its original executor is superseded.
    if ticket.content_sha256 is None:
        current = external.identity
        expected_origin = {
            "request_digest": external.request_digest,
            "checker_run_id": str(current.attempt_id),
            "attempt_id": str(current.attempt_id),
            "evaluation_request_id": str(current.evaluation_request_id),
            "evaluation_generation": current.evaluation_generation,
            "result_id": str(current.result_id),
            "worker_lease_id": str(current.lease_id),
            "worker_lease_generation": current.lease_generation,
            "worker_lease_expires_at": current.model_dump(mode="json")["lease_expires_at"],
        }
        if any(identity.get(name) != expected for name, expected in expected_origin.items()):
            raise ValueError("trial receipt origin differs")
    if value["request_identity_digest"] != identity.get("request_digest") or (
        value["material_binding_digest"] != identity.get("material_binding_digest")
        or identity.get("checker_image_digest") != external.registry.image_digest
        or value["trial_kind"] != subject.trial_kind
        or value["plan_digest"] != subject.plan_sha256
        or external_checker_json_hash(value["plan"]) != subject.plan_sha256
        or external_checker_json_hash(value["execution"]) != value["observation_digest"]
    ):
        raise ValueError("trial receipt provenance differs")
    for key in ("profile_id", "profile_version", "profile_digest"):
        if value[key] != external.configuration["trial_" + key]:
            raise ValueError("trial receipt profile differs")
    steps = value["plan"]["steps"]
    if value["slot_ids"] != [step["slot_id"] for step in steps]:
        raise ValueError("trial receipt plan slots differ")
    observations = json.dumps(value["execution"], sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False).encode("utf-8")
    if value["engine_identity_digest"] != profile.engine_identity_digest or (
        type(value["observation_byte_count"]) is not int
        or value["observation_byte_count"] != len(observations)
        or len(observations) > profile.limits.maximum_observation_bytes
    ):
        raise ValueError("trial receipt runtime differs")


class CheckerTrialProxy:
    """The trusted host callback never delegates evidence custody to an image."""

    def __init__(self, *, sessions, reservations, outputs, bindings, profiles):
        """Compose existing custody owners with the trusted trial-profile reader."""
        self._sessions, self._reservations = sessions, reservations
        self._outputs, self._bindings = outputs, bindings
        self._profiles = profiles

    async def handle(self, payload: dict) -> dict:
        """Return only closed safe failure codes; caller cancellation remains cancellation."""
        operation = payload.get("operation") if isinstance(payload, dict) else None
        if type(operation) is not str or operation not in {"reserve", "publish"}:
            operation = "reserve"
        try:
            raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            if len(raw.encode("utf-8")) > TRIAL_PROXY_MAXIMUM_FRAME_BYTES:
                return self._unavailable(operation, "trial_request_too_large")
            request = TRIAL_PROXY_REQUEST.validate_json(raw)
            if request.external_request.identity.phase != "post_submit":
                return self._unavailable(operation, "trial_request_invalid")
            if isinstance(request, TrialReserveRequest):
                return await self._reserve(request)
            return await self._publish(request)
        except (ValidationError, ValueError, TypeError, KeyError):
            return self._unavailable(operation, "trial_request_invalid")
        except (TrialEvidenceUnavailable, TrialProfileError, CheckerOutputUnavailable):
            return self._unavailable(operation, "trial_evidence_unavailable")
        except TimeoutError:
            return self._unavailable(operation, "trial_deadline")

    @staticmethod
    def _unavailable(operation, code):
        """Return a bounded protocol failure without internal exception details."""
        return {"protocol_version": TRIAL_PROXY_PROTOCOL, "operation": operation,
                "outcome": "unavailable", "failure_code": code}

    async def _reserve(self, request):
        """Reserve one stable trial slot or recover its original verified receipt."""
        async with self._sessions() as session, session.begin():
            ticket = await self._reservations(session, request.external_request).reserve(request.subject)
        retained = None
        if ticket.content_sha256 is not None:
            selector = TrialEvidenceSelector(
                trial_evidence_id=ticket.trial_evidence_id,
                project_id=ticket.subject.project_id, content_sha256=ticket.content_sha256,
            )
            outputs = self._outputs(request.external_request)
            stored = await outputs.recover_trial_evidence(selector)
            ack = await self._bind(request.external_request, selector, stored)
            raw = await outputs.read_trial_evidence(selector, ack)
            if len(raw) != ack.byte_count or "sha256:" + hashlib.sha256(raw).hexdigest() != selector.content_sha256:
                raise TrialEvidenceUnavailable("trial_evidence_content_changed")
            retained = {"canonical_receipt_utf8": raw.decode("utf-8"),
                        "content_sha256": selector.content_sha256, "byte_count": len(raw),
                        "custody_ack": ack.model_dump(mode="json")}
        return {"protocol_version": TRIAL_PROXY_PROTOCOL, "operation": "reserve",
                "outcome": "completed", "ticket": ticket.model_dump(mode="json"),
                "retained_receipt": retained, "failure_code": None}

    async def _publish(self, request):
        """Validate runtime evidence, store exact bytes through ART and bind custody."""
        raw, value = _receipt_bytes(request)
        subject = _receipt_subject(request.external_request, value)
        async with self._sessions() as session, session.begin():
            ticket = await self._reservations(session, request.external_request).reserve(subject)
            if ticket.trial_evidence_id != request.trial_evidence_id or subject.project_id != request.project_id:
                raise TrialEvidenceUnavailable("trial_evidence_unavailable")
            if ticket.content_sha256 not in {None, request.content_sha256}:
                raise TrialEvidenceUnavailable("trial_content_conflict")
            selected = trial_selector_from_configuration(request.external_request.configuration)
            external = request.external_request
            context = TrialAuthorityContext(
                registry_entry_id=external.registry.registry_entry_id,
                registry_entry_digest=external.registry.entry_digest,
                checker_image_digest=external.registry.image_digest,
                configuration_sha256=external.configuration_sha256,
            )
            bundle = self._profiles.read(context, selected) if selected is not None else None
            if bundle is None:
                raise TrialEvidenceUnavailable("trial_profile_unavailable")
            _validate_receipt(value, ticket, request.external_request, bundle[0])
        selector = TrialEvidenceSelector(
            trial_evidence_id=request.trial_evidence_id, project_id=request.project_id,
            content_sha256=request.content_sha256,
        )

        async def stream():
            """Supply the already bounded receipt to the canonical ART upload path."""
            yield raw

        stored = await self._outputs(request.external_request).store_trial_evidence(
            TrialEvidenceArtifactRequest(selector, stream()),
        )
        ack = await self._bind(request.external_request, selector, stored)
        return {"protocol_version": TRIAL_PROXY_PROTOCOL, "operation": "publish",
                "outcome": "completed", "custody_ack": ack.model_dump(mode="json"),
                "failure_code": None}

    async def _bind(self, external, selector, stored):
        """Bind verified output under fresh invocation authority in one transaction."""
        if stored is None or stored.content_id is None or stored.verification_receipt_id is None:
            raise TrialEvidenceUnavailable("trial_evidence_unavailable")
        async with self._sessions() as session, session.begin():
            return await self._bindings(session, external).bind_trial_evidence(
                TrialEvidenceBindingRequest(
                    selector, stored.put_attempt_id, stored.verification_receipt_id,
                ),
            )
