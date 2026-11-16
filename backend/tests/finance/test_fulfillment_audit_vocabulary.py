"""Probe actual installed audit CHECK predicates without minting an AUTH allow.

This deliberately tests only vocabulary/facts admission, not authorization or
receipt closure. No audit or product row is inserted by these probes.
"""

import json

from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.db.session import get_session_factory

CONSTRAINTS = (
    "ck_audit_events_authority_privacy_bounds",
    "ck_audit_events_authority_registries",
    "ck_audit_events_authorization_action_evidence",
)
PAIRS = (
    ("compensation.fulfillment.report", "compensation_fulfillment_report"),
    ("compensation.fulfillment.exception.report", "compensation_fulfillment_exception"),
    ("compensation.fulfillment.source.read", "compensation_fulfillment_evidence"),
    ("compensation.fulfillment.source.read", "compensation_fulfillment_report_lookup"),
)


def _event(action, resource):
    identity, project = str(new_record_id()), str(new_record_id())
    return dict(
        id=identity, entity_id=identity, entity_type="authorization_decision",
        event_type="SensitiveAuthorizationAllowed", event_domain="authority", event_version=1,
        actor_ref_kind="actor_profile", actor_id=str(new_record_id()),
        actor_roles=[], claim_snapshot={}, auth_source="local_authority", is_dev_auth=False,
        event_payload={}, request_id=str(new_record_id()), correlation_id=str(new_record_id()),
        action_id=action, permission_id=action, project_id=project,
        resource_type=resource, resource_id=str(new_record_id()),
        target_ref_kind="project", target_ref_id=project, reason="authorization_evaluation",
        after_facts={"allowed": True, "resource_context_digest": "sha256:" + "a" * 64},
    )


async def test_native_fulfillment_vocabulary_admits_exact_tokens_and_stays_closed(isolated_database_env):
    async with get_session_factory()() as session:
        expressions = {}
        for name in CONSTRAINTS:
            expressions[name] = await session.scalar(text(
                "SELECT pg_catalog.pg_get_expr(conbin,conrelid) FROM pg_catalog.pg_constraint "
                "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
            ), {"name": name})
            assert expressions[name]

        async def check(event, name):
            # Expressions come only from the exact installed trusted constraints.
            return await session.scalar(text(
                "SELECT " + expressions[name] + " FROM jsonb_populate_record("
                "NULL::public.audit_events,CAST(:event AS jsonb)) AS a"
            ), {"event": json.dumps(event)})

        for action, resource in PAIRS:
            event = _event(action, resource)
            for name in CONSTRAINTS:
                assert await check(event, name) is True, (action, resource, name)
            assert await check(event | {"resource_type": "unknown_fulfillment"}, CONSTRAINTS[0]) is False
            assert await check(event | {"permission_id": "compensation.fulfillment.unknown"}, CONSTRAINTS[1]) is False
            other = "compensation.fulfillment.exception.report" if action.endswith("source.read") else "compensation.fulfillment.source.read"
            assert await check(event | {"permission_id": other}, CONSTRAINTS[2]) is False
            leaked = event["after_facts"] | {"provider_payload": "forbidden"}
            assert await check(event | {"after_facts": leaked}, CONSTRAINTS[0]) is False
