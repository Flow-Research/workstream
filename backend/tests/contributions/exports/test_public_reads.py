"""Public signed read/export proof against real canonical source and retained AUTH."""

import csv
import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.core.config import decode_pagination_cursor_hmac_secret, get_settings
from app.db.session import get_session_factory
from app.modules.actors.models import ActorIdentityLink
from app.modules.actors.api import ServiceIdentity
from app.modules.contributions.records.pagination import ContributionExportCursorCodec
from tests.authentication.support import issue_asymmetric_token
from tests.contributions.records.support import (
    authorized_submitter_source, reviewer_contribution_source, insert_record,
    award_values, insert_award, rows,
)
from tests.authorization.admin_access.support import create_project
from .support import source_actor, export_path, export_audits, prepared_reviewer_sibling
from uuid import uuid4


@pytest.mark.parametrize("paid", [False, True])
async def test_project_json_and_csv_pages_have_the_same_complete_contributions(
    tmp_path, auth_database_env, admin_access, paid,
):
    """A CSV award row never consumes another contribution's page position."""
    async with reviewer_contribution_source(tmp_path, auth_database_env, paid=paid) as h:
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
            for award in await award_values(session, h.reviewer_record):
                await insert_award(session, award)
        sibling = await prepared_reviewer_sibling(h)
        async with h.factory() as session, session.begin():
            await insert_record(session, sibling)
            for award in await award_values(session, sibling):
                await insert_award(session, award)
        project = h.reviewer_record.project_id
        reader = await admin_access.signed.actor(f"paged-project-reader-{paid}")
        await admin_access.signed.grant(admin_access.admin, reader,
                                       role="project_manager", project_id=project)
        path = export_path(project)

        json_items = []
        cursor = None
        for page_number in range(2):
            params = {"limit": 1}
            if cursor is not None:
                params["cursor"] = cursor
            response = await admin_access.signed.client.get(path, params=params, headers=reader.headers)
            assert response.status_code == 200, response.text
            body = response.json()
            assert len(body["items"]) == 1
            json_items.extend(body["items"])
            cursor = body["next_cursor"]
            assert bool(cursor) is (page_number == 0)

        csv_rows = []
        cursor = None
        for page_number in range(2):
            params = {"limit": 1, "format": "csv"}
            if cursor is not None:
                params["cursor"] = cursor
            response = await admin_access.signed.client.get(path, params=params, headers=reader.headers)
            assert response.status_code == 200, response.text
            page_rows = list(csv.DictReader(StringIO(response.text, newline="")))
            assert len({row["contribution_id"] for row in page_rows}) == 1
            assert len(page_rows) == (2 if paid else 1)
            csv_rows.extend(page_rows)
            cursor = response.headers.get("X-Workstream-Next-Cursor")
            assert bool(cursor) is (page_number == 0)

        expected_ids = {str(h.reviewer_record.id), str(sibling.id)}
        assert {item["contribution_id"] for item in json_items} == expected_ids
        assert [row["contribution_id"] for row in csv_rows[::(2 if paid else 1)]] == [
            item["contribution_id"] for item in json_items
        ]
        for item in json_items:
            selected = [row for row in csv_rows if row["contribution_id"] == item["contribution_id"]]
            assert {(row["award_id"], row["quantity"]) for row in selected if row["award_id"]} == {
                (award["award_id"], award["quantity"]) for award in item["awards"]
            }
            if not paid:
                assert item["awards"] == []
                assert selected[0]["award_id"] == selected[0]["quantity"] == ""
        assert len(await export_audits(h.factory)) == 4


async def test_project_cursor_is_bound_to_caller_project_filters_format_and_limit(
    tmp_path, auth_database_env, admin_access,
):
    async with reviewer_contribution_source(tmp_path, auth_database_env) as h:
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
        sibling = await prepared_reviewer_sibling(h)
        async with h.factory() as session, session.begin():
            await insert_record(session, sibling)
        project = h.reviewer_record.project_id
        reader = await admin_access.signed.actor("cursor-project-reader")
        other = await admin_access.signed.actor("cursor-other-reader")
        foreign = await create_project("Cursor foreign project")
        for actor, scope in ((reader, project), (reader, foreign), (other, project)):
            await admin_access.signed.grant(admin_access.admin, actor,
                                           role="project_manager", project_id=scope)
        path = export_path(project)
        first = await admin_access.signed.client.get(
            path, params={"limit": 1}, headers=reader.headers,
        )
        assert first.status_code == 200, first.text
        cursor = first.json()["next_cursor"]
        assert cursor and len(first.json()["items"]) == 1
        replay = await admin_access.signed.client.get(
            path, params={"limit": 1, "cursor": cursor}, headers=reader.headers,
        )
        assert replay.status_code == 200, replay.text
        repeated = await admin_access.signed.client.get(
            path, params={"limit": 1, "cursor": cursor}, headers=reader.headers,
        )
        assert repeated.status_code == 200 and repeated.json()["items"] == replay.json()["items"]
        assert repeated.json()["next_cursor"] == replay.json()["next_cursor"] is None
        assert {first.json()["items"][0]["contribution_id"], replay.json()["items"][0]["contribution_id"]} == {
            str(h.reviewer_record.id), str(sibling.id)
        }

        middle = len(cursor) // 2
        altered = cursor[:middle] + ("A" if cursor[middle] != "A" else "B") + cursor[middle + 1:]
        cases = (
            (path, reader.headers, {"limit": 1, "cursor": altered}),
            (path, reader.headers, {"limit": 1, "cursor": "x" * 513}),
            (path, other.headers, {"limit": 1, "cursor": cursor}),
            (export_path(foreign), reader.headers, {"limit": 1, "cursor": cursor}),
            (path, reader.headers, {"limit": 1, "cursor": cursor,
                                    "contribution_type": "accepted_submission"}),
            (path, reader.headers, {"limit": 1, "cursor": cursor,
                                    "recorded_from": "2026-01-01T00:00:00Z"}),
            (path, reader.headers, {"limit": 1, "cursor": cursor, "format": "csv"}),
            (path, reader.headers, {"limit": 2, "cursor": cursor}),
        )
        errors = []
        for selected_path, headers, params in cases:
            response = await admin_access.signed.client.get(selected_path, params=params, headers=headers)
            assert response.status_code == 422, response.text
            errors.append(response.json()["error"]["code"])
        assert len(set(errors)) == 1
        assert errors[0] == "contribution_export_cursor_invalid"


async def test_expired_cursor_is_rejected_and_successful_first_page_prunes_its_slot(
    tmp_path, auth_database_env, admin_access,
):
    """Expiry cannot be replayed; a committed later read reclaims the stale slot."""
    async with reviewer_contribution_source(tmp_path, auth_database_env) as h:
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
        sibling = await prepared_reviewer_sibling(h)
        async with h.factory() as session, session.begin():
            await insert_record(session, sibling)
        project = h.reviewer_record.project_id
        reader = await admin_access.signed.actor("expired-cursor-project-reader")
        await admin_access.signed.grant(admin_access.admin, reader,
                                       role="project_manager", project_id=project)
        path = export_path(project)
        first = await admin_access.signed.client.get(
            path, params={"limit": 1}, headers=reader.headers,
        )
        assert first.status_code == 200 and first.json()["next_cursor"], first.text
        original_cursor = first.json()["next_cursor"]
        async with h.factory() as session, session.begin():
            stored = (await session.execute(text("""
                SELECT id,actor_profile_id,allocation_slot,query_digest,member_ids
                FROM public.contribution_export_snapshots WHERE actor_profile_id=:actor
            """), {"actor": str(reader.id)})).mappings().one()
            await session.execute(text("""
                DELETE FROM public.contribution_export_snapshots WHERE id=:id
            """), {"id": stored["id"]})
            created = datetime.now(UTC) - timedelta(hours=2)
            expires = created + timedelta(hours=1)
            await session.execute(text("""
                INSERT INTO public.contribution_export_snapshots
                  (id,actor_profile_id,allocation_slot,query_digest,member_ids,created_at,expires_at)
                VALUES (:id,:actor,:slot,:digest,CAST(:members AS uuid[]),:created,:expires)
            """), {"id": stored["id"], "actor": stored["actor_profile_id"],
                   "slot": stored["allocation_slot"], "digest": stored["query_digest"],
                   "members": stored["member_ids"], "created": created, "expires": expires})
        secret = get_settings().pagination_cursor_hmac_secret
        assert secret is not None
        expired_cursor = ContributionExportCursorCodec(
            decode_pagination_cursor_hmac_secret(secret),
        ).encode(query_digest=stored["query_digest"], snapshot_id=stored["id"],
                 next_offset=1, expires_at=expires)
        expired = await admin_access.signed.client.get(
            path, params={"limit": 1, "cursor": expired_cursor}, headers=reader.headers,
        )
        assert expired.status_code == 422, expired.text
        assert expired.json()["error"]["code"] == "contribution_export_cursor_invalid"
        fresh = await admin_access.signed.client.get(
            path, params={"limit": 1}, headers=reader.headers,
        )
        assert fresh.status_code == 200 and fresh.json()["next_cursor"], fresh.text
        async with h.factory() as session:
            rows = (await session.execute(text("""
                SELECT id,allocation_slot FROM public.contribution_export_snapshots
                WHERE actor_profile_id=:actor
            """), {"actor": str(reader.id)})).all()
        assert len(rows) == 1 and rows[0][0] != stored["id"] and rows[0][1] == 1
        for cursor in (original_cursor, expired_cursor):
            replay = await admin_access.signed.client.get(
                path, params={"limit": 1, "cursor": cursor}, headers=reader.headers,
            )
            assert replay.status_code == 422, replay.text
            assert replay.json()["error"]["code"] == "contribution_export_cursor_invalid"


async def test_revoked_project_reader_cannot_continue_even_with_a_malformed_cursor(
    tmp_path, auth_database_env, admin_access,
):
    async with reviewer_contribution_source(tmp_path, auth_database_env) as h:
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
        sibling = await prepared_reviewer_sibling(h)
        async with h.factory() as session, session.begin():
            await insert_record(session, sibling)
        project = h.reviewer_record.project_id
        reader = await admin_access.signed.actor("revoked-cursor-project-reader")
        grant = await admin_access.signed.grant(admin_access.admin, reader,
                                              role="project_manager", project_id=project)
        first = await admin_access.signed.client.get(
            export_path(project), params={"limit": 1}, headers=reader.headers,
        )
        assert first.status_code == 200 and first.json()["next_cursor"], first.text
        revoked = await admin_access.signed.revoke(admin_access.admin, grant)
        assert revoked.status_code == 200, revoked.text
        for cursor in (first.json()["next_cursor"], "not-a-cursor", "x" * 513):
            denied = await admin_access.signed.client.get(
                export_path(project), params={"limit": 1, "cursor": cursor}, headers=reader.headers,
            )
            assert denied.status_code == 404, denied.text
            assert denied.json()["error"]["code"] == "contribution_export_not_found"
        evidence = await export_audits(h.factory)
        assert [row["after_facts"]["allowed"] for row in evidence] == [
            True, False, False, False,
        ]
        assert all(row["project_id"] is row["target_ref_id"] is None for row in evidence[1:])


@pytest.mark.parametrize("instruments", [(), ("money",), ("project_points",)])
async def test_self_export_preserves_real_source_and_complete_json_csv_awards(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle, instruments,
):
    async with authorized_submitter_source(tmp_path, auth_database_env, contribution_awards=instruments) as h:
        actor = await source_actor(signed_access, h)
        async with h.factory() as session:
            before = {table: await rows(session, table) for table in
                      ("contribution_records", "compensation_awards", "final_acceptances")}
        json = await signed_access.client.get("/api/v1/actors/me/contributions", headers=actor.headers)
        assert json.status_code == 200, json.text
        item, = json.json()["items"]
        assert item["contribution_id"] == str(h.submitter_record.id)
        assert item["source_final_acceptance_id"] == str(h.acceptance.id)
        assert item["acceptance_routing_manifest_id"] == str(h.acceptance.source_routing_manifest_id)
        assert {award["instrument"] for award in item["awards"]} == set(instruments)
        csv_response = await signed_access.client.get("/api/v1/actors/me/contributions?format=csv", headers=actor.headers)
        assert csv_response.status_code == 200, csv_response.text
        exported = list(csv.DictReader(StringIO(csv_response.text, newline="")))
        assert len(exported) == max(1, len(instruments))
        assert {row["contribution_id"] for row in exported} == {item["contribution_id"]}
        assert {(row["award_id"], row["quantity"]) for row in exported if row["award_id"]} == {
            (award["award_id"], award["quantity"]) for award in item["awards"]
        }
        async with h.factory() as session:
            assert {table: await rows(session, table) for table in before} == before
        evidence = await export_audits(h.factory)
        assert len(evidence) == 2 and all(row["after_facts"]["allowed"] for row in evidence)
        assert all(row["after_facts"].get("resource_context_digest") for row in evidence)


@pytest.mark.parametrize("role,scope,expected", [
    ("project_manager", "system", 200), ("project_manager", "project", 200),
    ("finance_authority", "project", 200), ("finance_authority", "system", 404),
    ("finance_authority", "foreign", 404), ("operator", "system", 404),
    ("audit_authority", "project", 404),
])
async def test_project_export_requires_covering_pm_or_exact_project_finance(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle, role, scope, expected,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        project = h.submitter_record.project_id
        foreign = await create_project("Foreign export scope") if scope == "foreign" else None
        reader = await admin_access.signed.actor(f"export-reader-{role}-{scope}")
        await admin_access.signed.grant(admin_access.admin, reader, role=role,
                                       project_id=project if scope == "project" else foreign)
        response = await admin_access.signed.client.get(export_path(project), headers=reader.headers)
        assert response.status_code == expected, response.text
        event, = await export_audits(h.factory)
        assert event["after_facts"]["allowed"] is (expected == 200)
        if expected == 200:
            assert response.json()["items"][0]["contribution_id"] == str(h.submitter_record.id)
            assert event["project_id"] == str(project) and event["target_ref_id"] == str(project)
        else:
            assert event["project_id"] is event["resource_type"] is event["target_ref_id"] is None


async def test_self_read_cannot_substitute_another_contributor(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        other = await signed_access.actor("different-contributor")
        response = await signed_access.client.get(
            "/api/v1/actors/me/contributions", params={"actor_profile_id": str(h.submitter_record.contributor_id)},
            headers=other.headers,
        )
        assert response.status_code == 200 and response.json()["items"] == []
        event, = await export_audits(get_session_factory())
        assert event["resource_id"] == str(other.id)


@pytest.mark.parametrize("transition", ["profile", "identity_link"])
async def test_fresh_self_read_refuses_real_inactive_identity(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle, transition,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        actor = await source_actor(admin_access.signed, h)
        allowed = await admin_access.signed.client.get("/api/v1/actors/me/contributions", headers=actor.headers)
        assert allowed.status_code == 200, allowed.text
        path = f"/api/v1/actors/{actor.id}/suspend"
        if transition == "identity_link":
            async with h.factory() as session:
                link = await session.scalar(select(ActorIdentityLink).where(
                    ActorIdentityLink.actor_profile_id == str(actor.id),
                ))
                path = f"/api/v1/actor-identity-links/{link.id}/revoke"
        withdrawn = await admin_access.signed.client.post(
            path, headers=admin_access.admin.headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Withdraw contribution read identity"},
        )
        assert withdrawn.status_code == 200, withdrawn.text
        denied = await admin_access.signed.client.get("/api/v1/actors/me/contributions", headers=actor.headers)
        assert denied.status_code == 404, denied.text
        evidence = await export_audits(h.factory)
        assert len([row for row in evidence if row["after_facts"]["allowed"]]) == 1


async def test_service_claims_cannot_provision_a_contribution_reader(signed_access):
    token = issue_asymmetric_token(signed_access.private_key, scope="workstream:service", claims={
        "sub": "unprovisioned-contribution-reader", "subject_kind": "service",
        "roles": ["project_manager", "finance_authority"],
    })
    response = await signed_access.client.get(
        "/api/v1/actors/me/contributions", headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "service_actor_not_provisioned", response.text
    async with get_session_factory()() as session:
        assert await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.subject == "unprovisioned-contribution-reader",
        )) is None


async def test_provisioned_service_cannot_read_project_contribution_facts(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        subject = "provisioned-contribution-denial-" + uuid4().hex
        provisioned = await admin_access.signed.client.post(
            "/api/v1/service-actors", headers=admin_access.admin.headers | {"Idempotency-Key": str(uuid4())},
            json={"service_identity": ServiceIdentity.REVIEW_PROJECTION.value, "subject": subject,
                  "reason": "Prove fixed service cannot disclose contribution evidence"},
        )
        assert provisioned.status_code == 201, provisioned.text
        token = issue_asymmetric_token(admin_access.signed.private_key, scope="workstream:service", claims={
            "sub": subject, "subject_kind": "service", "roles": ["project_manager", "finance_authority"],
        })
        denied = await admin_access.signed.client.get(
            export_path(h.submitter_record.project_id), headers={"Authorization": f"Bearer {token}"},
        )
        assert denied.status_code == 404, denied.text
        event, = await export_audits(h.factory)
        assert event["after_facts"]["allowed"] is False
        assert event["target_ref_id"] is event["project_id"] is None


async def test_export_audit_sql_requires_each_exact_allow_and_deny_pair(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle,
):
    """Bypass schema validation with real decision templates; roll all probes back."""
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        own = await source_actor(signed_access, h)
        other = await signed_access.actor("export-audit-sql-ungranted-human")
        allowed = await signed_access.client.get("/api/v1/actors/me/contributions", headers=own.headers)
        denied = await signed_access.client.get(export_path(h.submitter_record.project_id), headers=other.headers)
        assert allowed.status_code == 200, allowed.text
        assert denied.status_code == 404, denied.text
        before = await export_audits(h.factory)
        assert len(before) == 2
        statement = text("""
            INSERT INTO public.audit_events
            SELECT (jsonb_populate_record(NULL::public.audit_events,
                to_jsonb(a) || CAST(:changes AS jsonb))).*
            FROM public.audit_events a WHERE a.id=:source
        """)
        async with h.factory() as session:
            await session.begin()
            templates = (await session.execute(text("""
                SELECT id,event_type FROM public.audit_events
                WHERE action_id IN ('contribution.read_self','contribution.read_project')
                ORDER BY created_at,id
            """))).all()
            assert {row.event_type for row in templates} == {
                "SensitiveAuthorizationAllowed", "SensitiveAuthorizationDenied",
            }
            for template in templates:
                for action in ("contribution.read_self", "contribution.read_project"):
                    identity = new_record_id()
                    changes = {"id": str(identity), "entity_id": str(identity),
                               "action_id": action, "permission_id": action}
                    # These staged clones prove only SQL pair vocabulary, not runtime authority.
                    await session.execute(statement, {"source": template.id, "changes": json.dumps(changes)})
                    assert await session.scalar(text(
                        "SELECT count(*) FROM public.audit_events WHERE id=:id AND action_id=:action AND permission_id=:action"
                    ), {"id": identity, "action": action}) == 1
                    crossed = "contribution.read_project" if action.endswith("self") else "contribution.read_self"
                    for permission in (crossed, "project.read"):
                        refused_id = new_record_id()
                        changed = changes | {"id": str(refused_id), "entity_id": str(refused_id),
                                             "permission_id": permission}
                        with pytest.raises(DBAPIError, match="ck_audit_events_authorization_action_evidence"):
                            async with session.begin_nested():
                                await session.execute(statement, {
                                    "source": template.id, "changes": json.dumps(changed),
                                })
                        assert await session.scalar(text(
                            "SELECT count(*) FROM public.audit_events WHERE id=:id"
                        ), {"id": refused_id}) == 0
            await session.rollback()
        assert await export_audits(h.factory) == before
