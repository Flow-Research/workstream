"""Exercise current public APIs over real HTTP without product-state fixtures.

Run only through run_isolated_tests.py; see docs/engineering/external-api-drill.md.
This is a field-accounted integration probe, not production Flow certification.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.parse import unquote, urlencode, urlsplit
from uuid import UUID, uuid4

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "put", "patch", "delete"}

# Frozen client expectations from spec_authorization_service.md and the closed
# administrative role contract. These are test oracles, never runtime policy.
# Do not derive them from server responses or import the server implementation.
EXPECTED_PERMISSIONS = tuple(sorted("""
actor.profile.read_self actor.profile.update_self actor.profile.read_any
actor.profile.suspend actor.profile.reactivate actor.profile.deactivate
actor.identity_link.read actor.identity_link.revoke actor.identity_link.reactivate
actor.service.provision admin_role.read admin_role.grant admin_role.revoke
project.create project.read project.setup_diagnostic.read project.effective_policy.read
project.update project.archive project.guide.manage project.guide_compilation.request
project.guide_compilation.execute project.effective_policy.manage project.task.manage
project.review_policy.manage project.role_grant.read project.role_grant.manage
task.queue.read task.claim submission.create submission.read_own submission.read_for_review
review.queue.read review.queue.inspect review.claim review.release review.decline_preference
review.decision review.lease.force_release review.chain.read review.queue.override
contribution.read_self contribution.read_project compensation.policy.manage
compensation.adapter_binding.manage compensation.award.read compensation.delivery.reconcile
operations.status.read operations.timer.run operations.reconcile.run operations.outbox.retry
operations.projection.rebuild operations.task.start_override operations.submission_gate.repair
operations.checker.retry artifact.binding.read artifact.replica.read artifact.receipt.read
artifact.verification_job.read artifact.verification_job.retry artifact.recovery_attempt.read
artifact.audit.read artifact.guide_source.ingest artifact.binding.create artifact.verification.execute
artifact.pending_work.scan artifact.put_attempt.resolve artifact.guide_source.read
artifact.checker_input.materialize artifact.checker_output.write artifact.review_packet.materialize
audit.read audit.export
""".split()))
EXPECTED_ROLE_CONTRACT = (
    ("access_administrator", ("system",), """actor.profile.read_any actor.profile.suspend actor.profile.reactivate actor.profile.deactivate
actor.identity_link.read actor.identity_link.revoke actor.identity_link.reactivate actor.service.provision
admin_role.read admin_role.grant admin_role.revoke audit.read audit.export"""),
    ("operator", ("system",), """project.read project.setup_diagnostic.read project.effective_policy.read review.queue.inspect
review.lease.force_release contribution.read_project compensation.award.read operations.status.read
operations.timer.run operations.reconcile.run operations.outbox.retry operations.projection.rebuild
operations.task.start_override operations.submission_gate.repair operations.checker.retry
artifact.binding.read artifact.replica.read artifact.receipt.read artifact.verification_job.read
artifact.verification_job.retry artifact.recovery_attempt.read artifact.audit.read audit.read"""),
    ("project_manager", ("system", "project"), """project.create project.read project.setup_diagnostic.read project.effective_policy.read project.update
project.archive project.guide.manage project.guide_compilation.request project.effective_policy.manage
project.task.manage project.review_policy.manage project.role_grant.read project.role_grant.manage
artifact.guide_source.ingest review.queue.inspect contribution.read_project compensation.award.read audit.read"""),
    ("finance_authority", ("system", "project"), """project.read contribution.read_project compensation.policy.manage compensation.adapter_binding.manage
compensation.award.read compensation.delivery.reconcile audit.read"""),
    ("audit_authority", ("system", "project"), """actor.profile.read_any actor.identity_link.read admin_role.read project.read project.setup_diagnostic.read
project.effective_policy.read project.role_grant.read review.queue.inspect review.chain.read
contribution.read_project compensation.award.read audit.read audit.export"""),
)


def catalogue_expectations():
    """Fresh expected JSON objects; callers cannot mutate the frozen oracle."""
    return {
        "permissions": {"items": [{"permission_id": value} for value in EXPECTED_PERMISSIONS], "total": 73},
        "admin-role-definitions": {"items": [
            {"role": role, "allowed_scopes": list(scopes), "permission_ids": permissions.split()}
            for role, scopes, permissions in EXPECTED_ROLE_CONTRACT], "total": 5},
    }


async def catalogue_cases(drill, admin, outsider):
    for name, expected in catalogue_expectations().items():
        route = "/api/v1/authorization/" + name
        await drill.call("catalogue_" + name, "GET", route, token=admin,
            values=expected, exact_fields=expected.keys())
        await drill.call("catalogue_unauthenticated_" + name, "GET", route, expected=401)
        await drill.call("catalogue_ungranted_" + name, "GET", route, token=outsider,
            expected=403, values={"error.code": "permission_not_granted"})


class ProbeFailure(Exception):
    """A named assertion failed; never include response bodies or credentials."""


def openapi_document(response):
    """Reject unavailable or malformed discovery without exposing response content."""
    if response.status_code != 200:
        raise ProbeFailure("openapi_document_unavailable")
    try:
        document = response.json()
    except ValueError:
        raise ProbeFailure("openapi_document_invalid") from None
    if (not isinstance(document, dict)
            or not isinstance(document.get("openapi"), str)
            or not document["openapi"].startswith("3.")
            or not isinstance(document.get("paths"), dict)):
        raise ProbeFailure("openapi_document_invalid")
    return document


def stop_server(process, *, preserving_failure):
    """Attempt bounded cleanup without replacing an existing probe failure."""
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if not preserving_failure:
                raise ProbeFailure("server_cleanup_timeout") from None


async def wait_for_server(client, process, *, timeout_seconds=90):
    """Bound local startup by elapsed time; slow imports are not API failures."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("server_startup_failed")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            response = await asyncio.wait_for(client.get("/api/v1/health"), remaining)
            if response.status_code == 200:
                return
        except (httpx.ConnectError, httpx.TimeoutException, asyncio.TimeoutError):
            pass
        await asyncio.sleep(min(0.2, max(0, deadline - time.monotonic())))
    raise ProbeFailure("server_startup_timeout")


class TokenIssuer:
    """Ephemeral local issuer; no authority grants and no production credentials."""

    def __init__(self):
        self.secret = os.urandom(32).hex()
        self.issuer = "https://flow.invalid/external-api-drill"
        self.audience = "workstream-external-api-drill"

    def issue(self, subject: str, **overrides) -> str:
        now = int(time.time())
        claims = dict(iss=self.issuer, aud=self.audience, sub=subject,
                      jti=str(uuid4()), subject_kind="human", scope="workstream:access",
                      iat=now, nbf=now - 5, exp=now + 600, roles=[])
        claims.update(overrides)

        def encode(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

        content = encode({"alg": "HS256", "typ": "JWT"}) + b"." + encode(claims)
        signature = hmac.new(self.secret.encode(), content, hashlib.sha256).digest()
        return (content + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


def schema_fields(schema, document, prefix, seen=()):
    """Inventory nested fields; recursion stops, never silently grants coverage."""
    result = {prefix}
    ref = schema.get("$ref")
    if ref:
        if ref in seen or not ref.startswith("#/"):
            return result
        target = document
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        result |= schema_fields(target, document, prefix, (*seen, ref))
    for name, value in schema.get("properties", {}).items():
        result |= schema_fields(value, document, f"{prefix}.{name}", seen)
    if "items" in schema:
        result |= schema_fields(schema["items"], document, prefix + "[]", seen)
    for kind in ("anyOf", "allOf", "oneOf"):
        for value in schema.get(kind, []):
            result |= schema_fields(value, document, prefix, seen)
    return result


def inventory(document):
    """Build a method/path manifest of request and response schema fields."""
    operations = {}
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method not in METHODS:
                continue
            fields = set()
            for parameter in item.get("parameters", []) + operation.get("parameters", []):
                fields |= schema_fields(parameter.get("schema", {}), document,
                                        f'{parameter["in"]}.{parameter["name"]}')
            for value in operation.get("requestBody", {}).get("content", {}).values():
                fields |= schema_fields(value.get("schema", {}), document, "body")
            for status, response in operation.get("responses", {}).items():
                for value in response.get("content", {}).values():
                    fields |= schema_fields(value.get("schema", {}), document,
                                            f"response.{status}")
            operations[f"{method.upper()} {path}"] = {
                "schema_fields": sorted(fields), "cases": [], "status": "untested",
                "field_cases": {}, "uncovered_fields": sorted(fields),
                "predicate_cases": {}, "shape_cases": {}, "request_cases": {},
            }
    return operations


def response_value(body, path):
    value = body
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ProbeFailure("missing_response_field")
        value = value[part]
    return value


def uuid_value(value):
    return isinstance(value, str) and str(UUID(value)) == value


def timestamp_value(value):
    if not isinstance(value, str):
        return False
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None and parsed <= datetime.now(timezone.utc)


def strict_equal(actual, expected):
    """Compare JSON containers recursively without bool/integer coercion."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            strict_equal(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            strict_equal(left, right) for left, right in zip(actual, expected, strict=True))
    return actual == expected


def equality_fields(value, prefix):
    """Index only values actually compared; an empty array proves no item fields."""
    result = {prefix}
    if isinstance(value, dict):
        for key, item in value.items():
            result |= equality_fields(item, prefix + "." + key)
    elif isinstance(value, list):
        for item in value:
            result |= equality_fields(item, prefix + "[]")
    return result


def page_matches(items, expected_rows, seen, limit, identity):
    """Validate page identities and independent expected field values, not totals alone."""
    if not isinstance(items, list) or len(items) > limit:
        return False
    ids = []
    for row in items:
        if not isinstance(row, dict) or not isinstance(row.get(identity), str):
            return False
        key = row[identity]
        if key not in expected_rows or key in seen or key in ids:
            return False
        if any(not strict_equal(row.get(field), value) or field not in row
               for field, value in expected_rows[key].items()):
            return False
        ids.append(key)
    return True


async def page_cases(drill, name, route, path, token, expected_rows, *,
                     identity, query=None, limit=1, total=False):
    """Bound traversal by known HTTP-created rows; fail on missing/foreign/repeated rows."""
    seen, cursors = set(), set()
    cursor = first_cursor = None
    query = dict(query or {}) | {"limit": limit}
    for index in range(len(expected_rows) + 1):
        params = query | ({"cursor": cursor} if cursor is not None else {})
        page_ids = set()
        def items_valid(items):
            valid = page_matches(items, expected_rows, seen, limit, identity)
            if valid:
                page_ids.update(row[identity] for row in items)
            return valid
        def cursor_valid(value):
            complete = seen | page_ids == set(expected_rows)
            if value is None:
                return complete
            return (not complete and bool(page_ids) and isinstance(value, str)
                    and 0 < len(value) <= 512 and value not in cursors)
        body = await drill.call(name + "_page_" + str(index), "GET", route,
            path=path + "?" + urlencode(params), token=token,
            values={"total": len(expected_rows)} if total else {},
            checks={"items": items_valid, "next_cursor": cursor_valid},
            exact_fields=("items", "next_cursor", "total") if total else ("items", "next_cursor"),
            fields=tuple("query." + field for field in params))
        seen |= page_ids
        cursor = body["next_cursor"]
        if cursor is None:
            return first_cursor
        first_cursor = first_cursor or cursor
        cursors.add(cursor)
    raise ProbeFailure("pagination_bound_exceeded")


def verify_response(response, expected_status, expected_values, checks=None, exact_fields=None):
    """Assert explicit status and values; malformed JSON is not a passing body."""
    if response.status_code != expected_status:
        raise ProbeFailure("unexpected_status")
    try:
        body = response.json()
    except ValueError as exc:
        raise ProbeFailure("invalid_json") from exc
    if exact_fields is not None and (not isinstance(body, dict) or set(body) != set(exact_fields)):
        raise ProbeFailure("response_shape_mismatch")
    for path, expected in expected_values.items():
        value = response_value(body, path)
        if not strict_equal(value, expected):
            raise ProbeFailure("response_value_mismatch")
    for path, check in (checks or {}).items():
        try:
            valid = check(response_value(body, path))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ProbeFailure("response_predicate_failed") from exc
        if valid is not True:
            raise ProbeFailure("response_predicate_failed")
    return body


class Drill:
    """Record actual assertions separately from schema presence and denials."""

    def __init__(self, client, document, report):
        self.client, self.report = client, report
        report["operations"] = inventory(document)
        self.results = report["cases"] = []
        self.mutations = {}

    async def call(self, name, method, route, *, path=None, token=None, payload=None,
                   expected=200, values=None, fields=(), headers=None, checks=None,
                   exact_fields=None):
        operation = self.report["operations"][f"{method} {route}"]
        request_headers = {"X-Request-ID": str(uuid4()), "X-Correlation-ID": str(uuid4())}
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if payload is not None:
            request_headers["Idempotency-Key"] = str(uuid4())
        request_headers.update(headers or {})
        request_headers = {key: value for key, value in request_headers.items() if value is not None}
        asserted = set()
        for key, value in (values or {}).items():
            asserted |= equality_fields(value, f"response.{expected}.{key}")
        asserted |= {"header.X-Request-ID", "header.X-Correlation-ID"}
        predicates = {f"response.{expected}.{key}" for key in (checks or {})}
        shapes = {f"response.{expected}.{key}" for key in (exact_fields or ())}
        row = {"name": name, "operation": f"{method} {route}", "expected": expected,
               "actual": None, "result": "failed", "asserted_fields": [],
               "request_fields": sorted(set(fields)), "predicate_fields": [], "shape_fields": []}
        if any(previous["name"] == name for previous in self.results):
            raise ProbeFailure("duplicate_case_name")
        self.results.append(row)
        operation["cases"].append(name)
        try:
            if any(not isinstance(field, str) or not field.startswith(("body.", "query.", "path.", "header."))
                   for field in fields):
                raise ProbeFailure("invalid_request_field_annotation")
            # Respect the default 30/minute mutation budget without changing server guards.
            if method in {"POST", "PUT", "PATCH", "DELETE"} and token:
                times = self.mutations.setdefault(token, [])
                times[:] = [stamp for stamp in times if time.monotonic() - stamp < 61]
                if len(times) >= 29:
                    delay = max(0, 61 - (time.monotonic() - times[0]))
                    print(f"pacing local mutation requests for {delay:.1f}s", flush=True)
                    await asyncio.sleep(delay)
                    times[:] = [stamp for stamp in times if time.monotonic() - stamp < 61]
                times.append(time.monotonic())
            response = await self.client.request(method, path or route, json=payload,
                                                 headers=request_headers)
            row["actual"] = response.status_code
            if response.status_code >= 400:
                try:
                    code = response.json().get("error", {}).get("code")
                    if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,99}", code):
                        row["actual_error_code"] = code
                except (ValueError, AttributeError):
                    pass
            body = verify_response(response, expected, values or {}, checks, exact_fields)
            for header in ("X-Request-ID", "X-Correlation-ID"):
                if response.headers.get(header) != request_headers[header]:
                    raise ProbeFailure("request_provenance_mismatch")
            row["result"] = "success" if expected < 300 else "expected_denial"
            row["asserted_fields"] = sorted(asserted)
            row["predicate_fields"] = sorted(predicates)
            row["shape_fields"] = sorted(shapes)
            if operation["status"] != "failed":
                operation["status"] = (
                    "partial_positive" if row["result"] == "success"
                    or operation["status"] == "partial_positive" else "denial_only"
                )
            for field in asserted:
                operation["field_cases"].setdefault(field, []).append(name)
            for kind, observed in (("predicate_cases", predicates), ("shape_cases", shapes),
                                   ("request_cases", fields)):
                for field in observed:
                    operation[kind].setdefault(field, []).append(name)
            operation["uncovered_fields"] = sorted(
                set(operation["schema_fields"]) - operation["field_cases"].keys()
            )
            print(f'{row["result"]}: {name}: {method} {route} -> {response.status_code}', flush=True)
            return body
        except Exception as exc:
            operation["status"] = "failed"
            row["failure_kind"] = type(exc).__name__
            if isinstance(exc, ProbeFailure):
                row["failure_code"] = str(exc)
            raise


async def health_cases(drill):
    """The public liveness contract is exact JSON, not database/provider readiness."""
    await drill.call("health", "GET", "/api/v1/health",
                     values={"status": "ok"}, exact_fields=("status",))


async def profile_readback(drill, token, name, expected, previous=None):
    """Check all profile fields without mistaking admission timestamps for mutations."""
    def not_older(value, field):
        return timestamp_value(value) and (previous is None or
            datetime.fromisoformat(value.replace("Z", "+00:00")) >=
            datetime.fromisoformat(previous[field].replace("Z", "+00:00")))

    return await drill.call(name, "GET", "/api/v1/actors/me", token=token,
        values=expected,
        checks={"updated_at": lambda value: not_older(value, "updated_at"),
                "last_seen_at": lambda value: not_older(value, "last_seen_at")},
        exact_fields=(*expected, "updated_at", "last_seen_at"))


async def profile_cases(drill, issuer, token):
    route = "/api/v1/actors/me"
    for name, bad in (("missing", None), ("signature", TokenIssuer().issue("outsider")),
                      ("expired", issuer.issue("outsider", exp=int(time.time()) - 60)),
                      ("issuer", issuer.issue("outsider", iss="https://wrong.invalid")),
                      ("audience", issuer.issue("outsider", aud="wrong")),
                      ("not_before", issuer.issue("outsider", nbf=int(time.time()) + 300))):
        await drill.call("token_" + name, "GET", route, token=bad, expected=401)
    actor = await drill.call("profile_self", "GET", route, token=token,
        values={"actor_kind": "human", "status": "active", "domains": ["contributor"],
                "admin_roles": [], "project_role_grants": [], "display_name": None,
                "contact_email": None},
        checks={"actor_profile_id": uuid_value, "created_at": timestamp_value,
                "updated_at": timestamp_value, "last_seen_at": timestamp_value},
        exact_fields=("actor_profile_id", "actor_kind", "status", "domains", "admin_roles",
                      "project_role_grants", "display_name", "contact_email", "created_at",
                      "updated_at", "last_seen_at"))
    stable = {key: actor[key] for key in ("actor_profile_id", "created_at", "actor_kind",
                                         "domains", "admin_roles", "project_role_grants", "status")}
    await drill.call("profile_stable_identity", "GET", route, token=token, values=stable)
    await drill.call("profile_both_fields", "PATCH", route, token=token,
        payload={"display_name": "  Display 名  ", "contact_email": "  opaque contact  "},
        values=stable | {"display_name": "Display 名", "contact_email": "opaque contact"})
    await drill.call("profile_patch_omission_preserves_other", "PATCH", route, token=token,
        payload={"display_name": "single"},
        values=stable | {"display_name": "single", "contact_email": "opaque contact"})
    editable = {"display_name": "single", "contact_email": "opaque contact"}
    previous = await profile_readback(drill, token, "profile_omission_readback",
                                      stable | editable, actor)
    for field, limit in (("display_name", 200), ("contact_email", 320)):
        for label, value in (("text", "example"), ("limit", "x" * limit), ("null", None)):
            await drill.call(f"{field}_{label}", "PATCH", route, token=token,
                             payload={field: value}, values={field: value},
                             fields=(f"body.{field}",))
            editable[field] = value
            previous = await profile_readback(drill, token, f"{field}_{label}_readback",
                                              stable | editable, previous)
        for label, value in (("too_long", "x" * (limit + 1)), ("blank", "  "), ("empty", ""),
                             ("type", {"unexpected": True}), ("number", 1), ("bool", True),
                             ("array", []), ("nul", "before\x00after")):
            try:
                await drill.call(f"{field}_{label}", "PATCH", route, token=token,
                                 payload={field: value}, expected=422, fields=(f"body.{field}",),
                                 values={"error.code": "invalid_request", "error.retryable": False})
            except ProbeFailure:
                # Keep the failed case red, but run independent inputs if the
                # following full-state control proves the profile is unchanged.
                pass
            previous = await profile_readback(drill, token, f"{field}_{label}_unchanged",
                                              stable | editable, previous)
        other = "contact_email" if field == "display_name" else "display_name"
        await drill.call(f"{field}_mixed_invalid_atomic", "PATCH", route, token=token,
            payload={field: "x" * (limit + 1), other: "must not persist"}, expected=422,
            values={"error.code": "invalid_request", "error.retryable": False})
        previous = await profile_readback(drill, token, f"{field}_mixed_invalid_unchanged",
                                          stable | editable, previous)
    await drill.call("empty_profile_patch", "PATCH", route, token=token, payload={}, expected=422)
    await drill.call("unknown_profile_field", "PATCH", route, token=token,
                     payload={"admin_roles": ["access_administrator"]}, expected=422)
    await drill.call("profile_unauthenticated_patch", "PATCH", route,
        payload={"display_name": "unauthorized"}, expected=401)
    await profile_readback(drill, token, "profile_failed_changes_readback",
                           stable | editable, previous)
    return actor["actor_profile_id"]


async def project_cases(drill, admin, manager, outsider, manager_id):
    grant = await drill.call("grant_manager", "POST", "/api/v1/admin-role-grants", token=admin,
        payload={"target_actor_profile_id": manager_id, "role": "project_manager",
                 "scope_type": "system", "reason": "Isolated external API drill"}, expected=201)
    await catalogue_cases(drill, admin, outsider)
    await drill.call("list_system_grants", "GET", "/api/v1/admin-role-grants",
                     path="/api/v1/admin-role-grants?scope_type=system", token=admin)
    payload = {"name": "External drill", "slug": "drill-" + uuid4().hex,
               "description": "Disposable HTTP-only project"}
    key = {"Idempotency-Key": str(uuid4())}
    project = await drill.call("create_project", "POST", "/api/v1/projects", token=manager,
        payload=payload, headers=key, expected=201, values=payload,
        fields=("body.name", "body.slug", "body.description", "header.Idempotency-Key"))
    await drill.call("replay_project", "POST", "/api/v1/projects", token=manager,
        payload=payload, headers=key, expected=201, values={"id": project["id"]})
    await drill.call("conflicting_project_replay", "POST", "/api/v1/projects", token=manager,
        payload=payload | {"name": "Changed"}, headers=key, expected=409)
    route, path = "/api/v1/projects/{project_id}", f'/api/v1/projects/{project["id"]}'
    await drill.call("read_project", "GET", route, path=path, token=manager, values=payload)
    await drill.call("ungranted_project_denied", "GET", route, path=path, token=outsider, expected=404)
    await authorization_context_input_cases(drill, manager, outsider, project)
    guide_route = route + "/guides"
    guide = await drill.call("create_guide", "POST", guide_route, path=path + "/guides",
        token=manager, expected=201, payload={"version": "initial", "content_markdown": "# Task guide",
                                            "change_summary": "Initial draft"},
        values={"version": "initial", "content_markdown": "# Task guide", "status": "draft"},
        fields=("body.version", "body.content_markdown", "body.change_summary"))
    gpath, groute = path + "/guides/" + guide["id"], guide_route + "/{guide_id}"
    await drill.call("patch_guide", "PATCH", groute, path=gpath, token=manager,
        payload={"content_markdown": "# Updated guide", "change_summary": "Updated"},
        values={"content_markdown": "# Updated guide", "change_summary": "Updated"},
        fields=("body.content_markdown", "body.change_summary"))
    await policy_cases(drill, manager, groute, gpath, outsider)
    await project_field_cases(drill, manager, outsider, project, guide, manager_id)
    await project_role_cases(drill, manager, outsider, project, manager_id)
    await authority_cases(drill, admin, manager, outsider, manager_id, project)
    await drill.call("revoke_manager", "POST", "/api/v1/admin-role-grants/{grant_id}/revoke",
        path=f'/api/v1/admin-role-grants/{grant["resource_id"]}/revoke', token=admin,
        payload={"reason": "Verify authority revocation"})
    await drill.call("revoked_project_creation", "POST", "/api/v1/projects", token=manager,
        payload=payload | {"slug": "revoked-" + uuid4().hex}, expected=403)


async def authorization_context_input_cases(drill, manager, outsider, project):
    """Use a real project, normal public validation and concealed ungranted access."""
    route = "/api/v1/actors/me/authorization-context"
    for name, query in (("missing", ""), ("empty", "?project_id="),
                        ("too_long", "?" + urlencode({"project_id": "x" * 101}))):
        await drill.call("context_selector_" + name, "GET", route, path=route + query,
            token=manager, expected=422,
            values={"error.code": "invalid_request", "error.retryable": False},
            fields=("query.project_id",))
    await drill.call("context_ungranted", "GET", route,
        path=route + "?" + urlencode({"project_id": project["id"]}), token=outsider,
        expected=404, values={"error.code": "project_authorization_resource_not_found"})
    await drill.call("context_unauthenticated", "GET", route,
        path=route + "?" + urlencode({"project_id": project["id"]}), expected=401)
    try:
        await drill.call("context_selector_nul", "GET", route, token=manager,
            path=route + "?" + urlencode({"project_id": "before\x00after"}), expected=422,
            values={"error.code": "invalid_request", "error.retryable": False}, fields=("query.project_id",))
    except ProbeFailure:
        pass
    await drill.call("context_selector_valid_control", "GET", route, token=manager,
        path=route + "?" + urlencode({"project_id": project["id"]}),
        values={"project_id": project["id"], "status": "active", "project_roles": []})
    await drill.call("context_invalid_project_unchanged", "GET", "/api/v1/projects/{project_id}",
        path=f'/api/v1/projects/{project["id"]}', token=manager, values=project)


async def policy_cases(drill, manager, groute, gpath, outsider):
    """Exercise explicit policy fields, defaults, validation and stored replay."""
    policies = {
        "review-policy": {"human_review_required": True, "review_preference_window_seconds": 3600,
                          "review_lease_duration_seconds": 1800},
        "revision-policy": {"max_revision_rounds": 2, "revision_deadline_hours": 24},
    }
    defaults = {
        "review-policy": {"max_active_review_leases_per_reviewer": 1, "self_review_allowed": False,
            "reject_policy": "close_task", "finding_evidence_requirement": "optional",
            "requires_second_review": False, "allowed_decisions": ["accept", "needs_revision", "reject"],
            "minimum_finding_fields": []},
        "revision-policy": {"allowed_resubmission_states": ["needs_revision"],
                            "reviewer_reassignment_rule": None},
    }
    for suffix, body in policies.items():
        key = {"If-Match": '"no-current-policy"', "Idempotency-Key": str(uuid4())}
        result = await drill.call("create_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body, headers=key,
            values=body | defaults[suffix] | {"policy_generation": 1},
            fields=tuple("body." + field for field in body))
        await drill.call("stored_replay_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body, headers=key, values=result)
        invalids = [("unknown", body | {"unexpected": 1})]
        for field in body:
            if field != "human_review_required":
                invalids.append((field + "_missing", {k: v for k, v in body.items() if k != field}))
                invalids.append((field + "_zero", body | {field: 0}))
            invalids.append((field + "_null", body | {field: None}))
            invalids.append((field + "_type", body | {field: {"bad": True}}))
        invalids += [(field + "_enum", body | {field: "invalid"}) for field in defaults[suffix]
                     if field not in {"reviewer_reassignment_rule"}]
        for label, invalid in invalids:
            await drill.call(suffix + "_" + label, "PUT", groute + "/" + suffix,
                path=gpath + "/" + suffix, token=manager, payload=invalid,
                headers={"If-Match": '"no-current-policy"'}, expected=422)
        await drill.call("after_rejections_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body, headers=key, values=result)
        await drill.call("stale_selector_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body,
            headers={"If-Match": '"no-current-policy"'}, expected=409)
        # A fresh update with the prior selector proves rejections did not advance it.
        selector = f'"{result["id"]}.{result["policy_generation"]}.{result["policy_hash"].removeprefix("sha256:")}"'
        replacement = (body | {"human_review_required": False, "finding_evidence_requirement": "required_for_all",
                              "requires_second_review": True, "allowed_decisions": ["accept", "reject"],
                              "minimum_finding_fields": ["summary", "evidence"]}
                       if suffix == "review-policy" else
                       body | {"max_revision_rounds": 1, "revision_deadline_hours": 1,
                               "reviewer_reassignment_rule": "same_reviewer"})
        replacement_key = {"If-Match": selector, "Idempotency-Key": str(uuid4())}
        updated = await drill.call("replace_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=replacement, headers=replacement_key,
            values=defaults[suffix] | replacement | {"policy_generation": 2,
                "supersedes_policy_id": result["id"], "project_id": result["project_id"],
                "guide_version": "initial", "semantics_status": "complete"},
            checks={"id": lambda value: uuid_value(value) and value != result["id"],
                    "created_at": timestamp_value,
                    "policy_hash": lambda value: isinstance(value, str) and
                    re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None and value != result["policy_hash"]},
            fields=tuple("body." + field for field in replacement))
        await drill.call("replacement_replay_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=replacement,
            headers=replacement_key, values=updated)
        await drill.call("superseded_selector_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body,
            headers={"If-Match": selector}, expected=409)
        await policy_field_cases(drill, manager, outsider, groute + "/" + suffix,
                                 gpath + "/" + suffix, suffix, body, defaults[suffix], updated)


def policy_selector(policy):
    """Encode the observed public policy selector without importing product code."""
    return f'"{policy["id"]}.{policy["policy_generation"]}.{policy["policy_hash"].removeprefix("sha256:")}"'


async def policy_field_cases(drill, manager, outsider, route, path, kind, required, defaults, current):
    """Prove optional fields and rejected-write selected lineage on a usable API."""
    selector = policy_selector(current)
    invalids = []
    for field in defaults:
        if field != "reviewer_reassignment_rule":
            invalids.append((field + "_null", required | {field: None}))
    if kind == "review-policy":
        invalids += [("mode_" + label, required | {"human_review_required": value})
                     for label, value in (("integer_zero", 0), ("integer_one", 1), ("string", "false"))]
        invalids += [("self_review_true", required | {"self_review_allowed": True}),
                     ("multiple_leases", required | {"max_active_review_leases_per_reviewer": 2}),
                     ("decision_item", required | {"allowed_decisions": ["approve"]}),
                     ("finding_item", required | {"minimum_finding_fields": [None]})]
    else:
        invalids += [("states_" + label, required | {"allowed_resubmission_states": value})
                     for label, value in (("empty", []), ("multiple", ["needs_revision"] * 2),
                                          ("item", ["accept"]))]
        invalids.append(("reassignment_type", required | {"reviewer_reassignment_rule": {}}))
    for label, payload in invalids:
        await drill.call(kind + "_fields_" + label, "PUT", route, path=path, token=manager,
                         payload=payload, headers={"If-Match": selector}, expected=422)
    for label, headers, status, code in (
        ("missing_selector", {"If-Match": None}, 422, "invalid_request"),
        ("unquoted_selector", {"If-Match": selector[1:-1]}, 409, "policy_precondition_invalid"),
        ("foreign_selector", {"If-Match": f'"{uuid4()}.2.{"0" * 64}"'},
         409, "policy_precondition_failed"),
        ("missing_key", {"If-Match": selector, "Idempotency-Key": None}, 422, "invalid_request"),
        ("malformed_key", {"If-Match": selector, "Idempotency-Key": "not-a-uuid"},
         422, "validation_error"),
    ):
        await drill.call(kind + "_fields_" + label, "PUT", route, path=path, token=manager,
                         payload=required, headers=headers, expected=status, values={"error.code": code})
    await drill.call(kind + "_fields_unauthorized", "PUT", route, path=path, token=outsider,
                     payload=required, headers={"If-Match": selector}, expected=403,
                     values={"error.code": "permission_not_granted"})
    # A fresh successor, not cached replay, proves the selected predecessor did
    # not advance. This does not claim that denials wrote no audit/history rows.
    omitted = {key: value for key, value in required.items() if key != "human_review_required"}
    expected = defaults | omitted
    if kind == "review-policy":
        expected |= {"human_review_required": current["human_review_required"], "semantics_format": "v2"}
    next_policy = await policy_successor(drill, manager, route, path, kind + "_fields_omission",
                                        omitted, expected, current, hash_changed=True)
    if kind == "review-policy":
        explicit = required | {"finding_evidence_requirement": "required_for_blocking",
                               "minimum_finding_fields": ["summary"]}
        expected = defaults | explicit | {"semantics_format": "v2"}
    else:
        explicit = required | {"allowed_resubmission_states": ["needs_revision"],
                               "reviewer_reassignment_rule": None}
        expected = defaults | explicit
    await policy_successor(drill, manager, route, path, kind + "_fields_explicit",
                           explicit, expected, next_policy, hash_changed=kind == "review-policy")


async def policy_successor(drill, token, route, path, name, payload, semantics, previous, *, hash_changed):
    """Require exact next selected generation, identity and full policy semantics."""
    return await drill.call(name, "PUT", route, path=path, token=token, payload=payload,
        headers={"If-Match": policy_selector(previous)},
        values=semantics | {"project_id": previous["project_id"], "guide_version": previous["guide_version"],
                           "policy_generation": previous["policy_generation"] + 1,
                           "supersedes_policy_id": previous["id"], "semantics_status": "complete"},
        checks={"id": lambda value: uuid_value(value) and value != previous["id"],
                "created_at": timestamp_value,
                "policy_hash": lambda value: isinstance(value, str) and
                re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None and
                (value != previous["policy_hash"]) == hash_changed},
        exact_fields=previous.keys(), fields=tuple("body." + field for field in payload))


async def project_field_cases(drill, manager, outsider, project, guide, manager_id):
    """Input boundaries and current-state checks using public project operations."""
    route = "/api/v1/projects"
    for field in ("name", "slug", "description"):
        body = {"name": "Type test", "slug": "type-" + uuid4().hex}
        for label, value in (("object", {}), ("number", 1), ("array", [])):
            await drill.call(f"project_{field}_{label}", "POST", route, token=manager,
                payload=body | {field: value}, expected=422, fields=("body." + field,))
        if field != "description":
            await drill.call(f"project_{field}_missing", "POST", route, token=manager,
                payload={k: v for k, v in body.items() if k != field}, expected=422)
            await drill.call(f"project_{field}_null", "POST", route, token=manager,
                payload=body | {field: None}, expected=422)
    await drill.call("project_extra", "POST", route, token=manager,
        payload={"name": "Extra", "slug": "extra", "status": "active"}, expected=422)
    await drill.call("project_duplicate_slug", "POST", route, token=manager,
        payload={"name": "Duplicate", "slug": project["slug"]}, expected=409,
        values={"error.code": "project_slug_conflict"})
    for label, key in (("missing", None), ("malformed", "bad-key")):
        await drill.call("project_key_" + label, "POST", route, token=manager,
            payload={"name": "Key test", "slug": "key-" + uuid4().hex},
            headers={"Idempotency-Key": key}, expected=422)
    at_limit = {"name": "n" * 200, "slug": "s" * 120, "description": None}
    limit_project = await drill.call("project_maximum_lengths", "POST", route, token=manager,
        payload=at_limit, expected=201, values=at_limit | {"status": "draft"},
        checks={"id": uuid_value, "created_at": timestamp_value, "updated_at": timestamp_value},
        exact_fields=("id", "name", "slug", "description", "status", "created_at", "updated_at"))
    await drill.call("project_maximum_readback", "GET", route + "/{project_id}",
        path=route + "/" + limit_project["id"], token=manager, values=limit_project)
    groute = route + "/{project_id}/guides"
    gpath = f'{route}/{project["id"]}/guides'
    gbody = {"version": "v" * 50, "content_markdown": "# Boundary guide"}
    boundary_guide = await drill.call("guide_maximum_version", "POST", groute,
        path=gpath, token=manager, payload=gbody, expected=201,
        values=gbody | {"project_id": project["id"], "status": "draft", "change_summary": None,
                       "approved_by": None, "effective_at": None, "superseded_at": None,
                       "created_by": manager_id},
        checks={"id": uuid_value, "created_at": timestamp_value, "updated_at": timestamp_value},
        exact_fields=("id", "project_id", "version", "status", "content_markdown", "change_summary",
                      "approved_by", "effective_at", "superseded_at", "created_by", "created_at", "updated_at"))
    for field in gbody:
        await drill.call("guide_" + field + "_missing", "POST", groute, path=gpath, token=manager,
            payload={k: v for k, v in gbody.items() if k != field}, expected=422)
    # These probes are independent. Preserve every failure and continue to the next field.
    # Never alter the expected 422 to match an observed server error.
    for field, maximum in (("name", 200), ("slug", 120), ("version", 50)):
        body = ({"name": "Overflow", "slug": "overflow-" + uuid4().hex}
                if field != "version" else {"version": "overflow", "content_markdown": "# Overflow"})
        failed_key = {"Idempotency-Key": str(uuid4())}
        try:
            await drill.call("overflow_" + field, "POST", route if field != "version" else groute,
                path=route if field != "version" else gpath, token=manager,
                payload=body | {field: "x" * (maximum + 1)}, expected=422, headers=failed_key,
                fields=("body." + field,))
        except ProbeFailure:
            pass
        await drill.call("overflow_" + field + "_retry_after_rollback", "POST",
            route if field != "version" else groute, path=route if field != "version" else gpath,
            token=manager, payload=body, headers=failed_key, expected=201, values=body)
    # A new-key no-op PATCH returns current guide state, not a cached replay response.
    await drill.call("guide_current_state_after_overflow", "PATCH", groute + "/{guide_id}",
        path=gpath + "/" + boundary_guide["id"], token=manager, payload={},
        values={key: value for key, value in boundary_guide.items() if key != "updated_at"})
    await drill.call("guide_foreign_actor_patch", "PATCH", groute + "/{guide_id}",
        path=gpath + "/" + guide["id"], token=outsider,
        payload={"content_markdown": "Unauthorized replacement"}, expected=403)
    await drill.call("guide_foreign_actor_patch_unchanged", "PATCH", groute + "/{guide_id}",
        path=gpath + "/" + guide["id"], token=manager, payload={},
        values={"id": guide["id"], "project_id": project["id"], "version": "initial",
                "status": "draft", "content_markdown": "# Updated guide", "change_summary": "Updated",
                "created_by": manager_id, "created_at": guide["created_at"]})
    try:
        await drill.call("guide_null_content", "PATCH", groute + "/{guide_id}",
            path=gpath + "/" + guide["id"], token=manager,
            payload={"content_markdown": None}, expected=422)
    except ProbeFailure:
        pass
    await drill.call("guide_null_content_unchanged", "PATCH", groute + "/{guide_id}",
        path=gpath + "/" + guide["id"], token=manager, payload={},
        values={"content_markdown": "# Updated guide", "change_summary": "Updated"})


async def authority_cases(drill, admin, manager, outsider, manager_id, project):
    """Prove scoped authority against a real second project and lifecycle reads."""
    other = await drill.call("second_project", "POST", "/api/v1/projects", token=manager,
        payload={"name": "Foreign project", "slug": "foreign-" + uuid4().hex}, expected=201)
    outsider_body = await drill.call("scoped_actor", "GET", "/api/v1/actors/me", token=outsider)
    scoped_id = outsider_body["actor_profile_id"]
    await drill.call("grant_scoped_manager", "POST", "/api/v1/admin-role-grants", token=admin,
        payload={"target_actor_profile_id": scoped_id, "role": "project_manager",
                 "scope_type": "project", "scope_project_id": project["id"],
                 "reason": "Exact-project test"}, expected=201)
    route = "/api/v1/projects/{project_id}"
    await drill.call("scoped_project_control", "GET", route,
                     path=f'/api/v1/projects/{project["id"]}', token=outsider,
                     values={"id": project["id"]})
    await drill.call("foreign_project_denial", "GET", route,
                     path=f'/api/v1/projects/{other["id"]}', token=outsider, expected=404)
    await drill.call("scoped_authorization_context", "GET", "/api/v1/actors/me/authorization-context",
        path=f'/api/v1/actors/me/authorization-context?project_id={project["id"]}', token=outsider,
        values={"project_id": project["id"], "admin_roles": ["project_manager"]})
    await drill.call("context_stored_foreign_project", "GET", "/api/v1/actors/me/authorization-context",
        path=f'/api/v1/actors/me/authorization-context?project_id={other["id"]}', token=outsider,
        expected=404, values={"error.code": "project_authorization_resource_not_found"})
    for suffix in ("contributor-candidates", "role-grants"):
        await drill.call("list_" + suffix, "GET", route + "/" + suffix,
            path=f'/api/v1/projects/{project["id"]}/{suffix}?limit=1', token=outsider)
        await drill.call("invalid_limit_" + suffix, "GET", route + "/" + suffix,
            path=f'/api/v1/projects/{project["id"]}/{suffix}?limit=0', token=outsider, expected=422,
            fields=("query.limit",))
    for suffix in ("", "/identity-links", "/admin-role-grants"):
        await drill.call("admin_actor_read" + suffix, "GET", "/api/v1/actors/{actor_profile_id}" + suffix,
            path=f"/api/v1/actors/{manager_id}" + suffix + ("?scope_type=system" if suffix == "/admin-role-grants" else ""),
            token=admin)
    actor_route = "/api/v1/actors/{actor_profile_id}"
    actor_path = f"/api/v1/actors/{scoped_id}"
    known = {"actor_profile_id": scoped_id, "actor_kind": "human", "status": "active",
             "provisioning_method": "automatic_first_access", "service_identity": None,
             "display_name": None, "created_at": outsider_body["created_at"],
             "suspended_at": None, "reactivated_at": None, "deactivated_at": None}
    current = await drill.call("admin_human_profile_fields", "GET", actor_route,
        path=actor_path, token=admin, values=known,
        checks={"updated_at": timestamp_value, "last_seen_at": timestamp_value},
        exact_fields=(*known, "updated_at", "last_seen_at"))
    for read_route, read_path, name in ((actor_route, actor_path, "profile"),
                                      (actor_route + "/identity-links", actor_path + "/identity-links", "identity")):
        await drill.call("admin_" + name + "_unauthenticated", "GET", read_route,
                         path=read_path, expected=401)
        await drill.call("admin_" + name + "_ungranted", "GET", read_route,
                         path=read_path, token=manager, expected=403,
                         values={"error.code": "permission_not_granted"})
    for action in ("suspend", "reactivate", "deactivate"):
        mutation_route, mutation_path = actor_route + "/" + action, actor_path + "/" + action
        for label, invalid in (("missing_reason", {}), ("reason_overflow", {"reason": "é" * 251}),
                               ("reason_nul", {"reason": "before\x00after"})):
            await drill.call("actor_" + action + "_" + label, "POST", mutation_route,
                path=mutation_path, token=admin, payload=invalid, expected=422,
                values={"error.code": "invalid_request", "error.retryable": False})
            await drill.call("actor_" + action + "_" + label + "_unchanged", "GET", actor_route,
                path=actor_path, token=admin, values=current, exact_fields=current.keys())
        key = {"Idempotency-Key": str(uuid4())}
        payload = {"reason": "é" * 250}
        changed = await drill.call("actor_" + action, "POST", mutation_route,
            path=mutation_path, token=admin, payload=payload, headers=key,
            values={"resource_type": "actor_profile", "resource_id": scoped_id,
                    "version": None, "http_status": 200},
            exact_fields=("resource_type", "resource_id", "version", "http_status"))
        state = {"suspend": "suspended", "reactivate": "active", "deactivate": "deactivated"}[action]
        transition_field = {"suspend": "suspended_at", "reactivate": "reactivated_at",
                            "deactivate": "deactivated_at"}[action]
        expected = {key: value for key, value in current.items()
                    if key not in {"updated_at", transition_field}}
        expected["status"] = state
        if action == "reactivate":
            expected["suspended_at"] = None
        current = await drill.call("actor_" + action + "_readback", "GET", actor_route,
            path=actor_path, token=admin, values=expected,
            checks={"updated_at": timestamp_value, transition_field: timestamp_value},
            exact_fields=current.keys())
        await drill.call("actor_" + action + "_replay", "POST", mutation_route,
            path=mutation_path, token=admin, payload=payload, headers=key, values=changed,
            exact_fields=changed.keys())
        await drill.call("actor_" + action + "_replay_unchanged", "GET", actor_route,
            path=actor_path, token=admin, values=current, exact_fields=current.keys())
        if action == "reactivate":
            await drill.call("reactivated_self_write", "PATCH", "/api/v1/actors/me", token=outsider,
                payload={"display_name": "Reactivated owner"}, values={"display_name": "Reactivated owner"})
            current = await drill.call("reactivated_admin_readback", "GET", actor_route,
                path=actor_path, token=admin,
                values={key: value for key, value in current.items()
                        if key not in {"display_name", "updated_at", "last_seen_at"}}
                       | {"display_name": "Reactivated owner"},
                checks={"updated_at": timestamp_value, "last_seen_at": timestamp_value},
                exact_fields=current.keys())
        else:
            if action == "suspend":
                self_read = await profile_readback(drill, outsider, "suspended_self_read_allowed",
                    {"actor_profile_id": scoped_id, "status": "suspended", "display_name": None,
                            "contact_email": None, "actor_kind": "human", "domains": ["contributor"],
                            "admin_roles": ["project_manager"], "project_role_grants": [],
                            "created_at": outsider_body["created_at"]}, current)
                # A legitimate self read touches admission timestamps, unlike
                # an administrator reading a different target.
                current = await drill.call("suspended_self_read_admin_baseline", "GET", actor_route,
                    path=actor_path, token=admin,
                    values=current | {key: self_read[key] for key in ("updated_at", "last_seen_at")},
                    exact_fields=current.keys())
            else:
                await drill.call("deactivated_self_read_denied", "GET", "/api/v1/actors/me", token=outsider,
                    expected=403, values={"error.code": "actor_deactivated"})
            await drill.call(action + "_self_write_denied", "PATCH", "/api/v1/actors/me", token=outsider,
                payload={"display_name": "Forbidden change"}, expected=403,
                values={"error.code": "actor_suspended" if action == "suspend" else "actor_deactivated"})
            await drill.call(action + "_write_unchanged", "GET", "/api/v1/actors/{actor_profile_id}",
                path=f"/api/v1/actors/{scoped_id}", token=admin,
                values=current, exact_fields=current.keys())
    await drill.call("deactivated_actor_cannot_reactivate", "POST", "/api/v1/actors/{actor_profile_id}/reactivate",
        path=f"/api/v1/actors/{scoped_id}/reactivate", token=admin,
        payload={"reason": "Attempt forbidden terminal transition"}, expected=409,
        values={"error.code": "actor_deactivated_terminal"})


def qualification_invalids(valid):
    """Independent malformed shapes and cross-field contradictions for the public input."""
    for field in valid:
        omitted = deepcopy(valid)
        del omitted[field]
        yield "missing_" + field, omitted
        for name, value in (("null", None), ("type", 7)):
            yield name + "_" + field, valid | {field: value}
    for snapshot in ("skills_snapshot", "reputation_snapshot"):
        for field in valid[snapshot]:
            omitted = deepcopy(valid)
            del omitted[snapshot][field]
            yield "missing_" + snapshot + "_" + field, omitted
        for name, changes in (
            ("no_refs", {"reference_ids": []}),
            ("available_with_reason", {"unavailable_reason": "no_record"}),
            ("unavailable_with_refs", {"availability": "unavailable", "unavailable_reason": "no_record"}),
            ("unavailable_no_reason", {"availability": "unavailable", "reference_ids": []}),
            ("unknown_availability", {"availability": "pending"}),
            ("null_refs", {"reference_ids": None}),
            ("too_many", {"reference_ids": ["ref:" + str(i) for i in range(21)]}),
            ("too_long", {"reference_ids": ["x" * 121]}),
            ("url", {"reference_ids": ["https://example.invalid/ref"]}),
            ("extra", {"private_note": "not permitted"}),
        ):
            invalid = deepcopy(valid)
            invalid[snapshot].update(changes)
            yield snapshot + "_" + name, invalid
    for name, field, value in (
        ("prior_too_many", "prior_project_work_refs", [str(uuid4()) for _ in range(21)]),
        ("prior_bad_uuid", "prior_project_work_refs", ["bad"]),
        ("prior_bool", "prior_project_work_refs", [True]),
        ("external_too_many", "external_expertise_refs", ["ref:" + str(i) for i in range(21)]),
        ("external_too_long", "external_expertise_refs", ["x" * 121]),
        ("external_url", "external_expertise_refs", ["https://example.invalid/ref"]),
        ("external_bool", "external_expertise_refs", [True]),
    ):
        yield name, valid | {field: value}
    yield "extra", valid | {"private_note": "not permitted"}


async def project_role_cases(drill, manager, contributor, project, manager_id):
    """Issue exact-project grants, observe actual access, then revoke it."""
    actor = await drill.call("role_target_identity", "GET", "/api/v1/actors/me", token=contributor)
    route = "/api/v1/projects/{project_id}/role-grants"
    path = f'/api/v1/projects/{project["id"]}/role-grants'
    qualification = {
        "skills_snapshot": {"availability": "available", "reference_ids": ["x" * 120] + ["skill:" + str(i) for i in range(19)],
                            "unavailable_reason": None},
        "reputation_snapshot": {"availability": "available", "reference_ids": ["x" * 120] + ["rep:" + str(i) for i in range(19)],
                                "unavailable_reason": None},
        "prior_project_work_refs": [str(uuid4()) for _ in range(20)],
        "external_expertise_refs": ["x" * 120] + ["expertise:" + str(i) for i in range(19)],
    }
    recovery_key = {"Idempotency-Key": str(uuid4())}
    await drill.call("qualification_empty_baseline", "GET", route,
        path=path, token=manager, values={"items": [], "next_cursor": None})
    for name, invalid in qualification_invalids(qualification):
        try:
            await drill.call("qualification_" + name, "POST", route, path=path, token=manager,
                payload={"target_actor_profile_id": actor["actor_profile_id"], "role": "submitter",
                         "qualification": invalid, "reason": "Invalid qualification probe"},
                headers=recovery_key, expected=422, fields=("body.qualification",))
        except ProbeFailure:
            pass
        await drill.call("qualification_unchanged_" + name, "GET", route,
            path=path, token=manager, values={"items": [], "next_cursor": None})
    for role in ("submitter", "reviewer"):
        before = await drill.call("qualification_before_limits_" + role, "GET", route,
            path=path, token=manager)
        try:
            boundary = await drill.call("qualification_combined_limits_" + role, "POST", route,
                path=path, token=manager, headers={"Idempotency-Key": str(uuid4())},
                payload={"target_actor_profile_id": actor["actor_profile_id"], "role": role,
                         "qualification": qualification, "reason": "Exact project contribution role"},
                expected=201, values={"role": role, "status": "active", "version": 1},
                checks={"id": uuid_value})
        except ProbeFailure:
            await drill.call("qualification_failed_state_" + role, "GET", route,
                path=path, token=manager, values=before)
            await drill.call("qualification_failed_access_" + role, "GET", "/api/v1/projects/{project_id}",
                path=f'/api/v1/projects/{project["id"]}', token=contributor, expected=404)
            continue
        await drill.call("qualification_limits_readback_" + role, "GET", route + "/{grant_id}",
            path=path + "/" + boundary["id"], token=manager,
            values={"qualification_snapshot." + field: value for field, value in qualification.items()})
        await drill.call("qualification_limits_revoke_" + role, "POST", route + "/{grant_id}/revoke",
            path=path + "/" + boundary["id"] + "/revoke", token=manager,
            payload={"reason": "End combined-boundary probe"}, values={"status": "revoked", "version": 2})
    populated = deepcopy(qualification)
    for field in ("skills_snapshot", "reputation_snapshot"):
        populated[field]["reference_ids"] = populated[field]["reference_ids"][:1]
    for field in ("prior_project_work_refs", "external_expertise_refs"):
        populated[field] = populated[field][:1]
    control = await drill.call("qualification_populated_control", "POST", route, path=path,
        token=manager, payload={"target_actor_profile_id": actor["actor_profile_id"], "role": "submitter",
                               "qualification": populated, "reason": "Independent populated field control"},
        expected=201, checks={"id": uuid_value}, values={"status": "active", "role": "submitter"})
    await drill.call("qualification_populated_readback", "GET", route + "/{grant_id}",
        path=path + "/" + control["id"], token=manager,
        values={"qualification_snapshot." + field: value for field, value in populated.items()})
    await drill.call("qualification_populated_revoke", "POST", route + "/{grant_id}/revoke",
        path=path + "/" + control["id"] + "/revoke", token=manager,
        payload={"reason": "End independent field control"}, values={"status": "revoked", "version": 2})
    # Preserve independent small positive/replay/lifecycle controls even if a
    # combined maximum exposes a product defect. Never lower its expected 201.
    qualification = {
        "skills_snapshot": {"availability": "available", "reference_ids": ["skill:drill"],
                            "unavailable_reason": None},
        "reputation_snapshot": {"availability": "unavailable", "reference_ids": [],
                                "unavailable_reason": "no_record"},
        "prior_project_work_refs": [], "external_expertise_refs": ["expertise:drill"],
    }
    for role in ("submitter", "reviewer"):
        body = {"target_actor_profile_id": actor["actor_profile_id"], "role": role,
                "qualification": qualification, "reason": "Exact project contribution role"}
        key = recovery_key if role == "submitter" else {"Idempotency-Key": str(uuid4())}
        try:
            result = await drill.call("issue_project_" + role, "POST", route, path=path, token=manager,
                payload=body, headers=key, expected=201,
                values={"project_id": project["id"], "actor_profile_id": actor["actor_profile_id"],
                        "role": role, "status": "active", "version": 1},
                checks={"id": uuid_value, "qualification_snapshot_id": uuid_value})
        except ProbeFailure:
            await drill.call("failed_grant_no_active_row_" + role, "GET", route,
                path=path + f"?role={role}&status=active", token=manager,
                values={"items": [], "next_cursor": None})
            await drill.call("failed_grant_no_access_" + role, "GET", "/api/v1/projects/{project_id}",
                path=f'/api/v1/projects/{project["id"]}', token=contributor, expected=404)
            continue
        await drill.call("replay_project_" + role, "POST", route, path=path, token=manager,
            payload=body, headers=key, expected=201, values=result)
        read_path = path + "/" + result["id"]
        stored = await drill.call("read_project_" + role, "GET", route + "/{grant_id}",
            path=read_path, token=manager,
            values={"id": result["id"], "project_id": project["id"], "actor_profile_id": actor["actor_profile_id"],
                    "role": role, "status": "active", "version": 1, "grant_method": "manual",
                    "grant_reason": body["reason"], "granted_by_actor_profile_id": manager_id,
                    "qualification_snapshot.id": result["qualification_snapshot_id"],
                    "qualification_snapshot.requested_role": role,
                    "qualification_snapshot.skills_snapshot": qualification["skills_snapshot"],
                    "qualification_snapshot.reputation_snapshot": qualification["reputation_snapshot"],
                    "qualification_snapshot.prior_project_work_refs": qualification["prior_project_work_refs"],
                    "qualification_snapshot.external_expertise_refs": qualification["external_expertise_refs"],
                    "revoked_by_actor_profile_id": None, "revoked_at": None, "revoked_reason": None},
            checks={"granted_at": timestamp_value, "granted_by_admin_role_grant_id": uuid_value,
                    "qualification_snapshot.captured_at": timestamp_value})
        await drill.call("contributor_project_access_" + role, "GET", "/api/v1/projects/{project_id}",
            path=f'/api/v1/projects/{project["id"]}', token=contributor,
            values={"id": project["id"], "name": project["name"], "status": "draft"},
            exact_fields=("id", "name", "status"))
        await drill.call("contributor_context_" + role, "GET", "/api/v1/actors/me/authorization-context",
            path=f'/api/v1/actors/me/authorization-context?project_id={project["id"]}', token=contributor,
            values={"actor_profile_id": actor["actor_profile_id"], "project_id": project["id"],
                    "status": "active", "admin_roles": [], "project_roles": [role],
                    "effective_action_ids": ["project.read"]},
            exact_fields=("actor_profile_id", "project_id", "status", "admin_roles",
                          "project_roles", "effective_action_ids"))
        revoked = await drill.call("revoke_project_" + role, "POST", route + "/{grant_id}/revoke",
            path=read_path + "/revoke", token=manager, payload={"reason": "End role probe"},
            values=result | {"status": "revoked", "version": 2})
        await drill.call("revoked_grant_readback_" + role, "GET", route + "/{grant_id}",
            path=read_path, token=manager,
            values={key: stored[key] for key in ("id", "role", "project_id", "actor_profile_id", "qualification_snapshot")}
                   | {"status": revoked["status"], "version": 2, "revoked_reason": "End role probe",
                      "revoked_by_actor_profile_id": manager_id},
            checks={"revoked_at": timestamp_value})
        await drill.call("revoked_contributor_read_" + role, "GET", "/api/v1/projects/{project_id}",
            path=f'/api/v1/projects/{project["id"]}', token=contributor, expected=404)
        await drill.call("revoked_contributor_context_" + role, "GET", "/api/v1/actors/me/authorization-context",
            path=f'/api/v1/actors/me/authorization-context?project_id={project["id"]}', token=contributor,
            expected=404, values={"error.code": "project_authorization_resource_not_found"})
    # Human-confirmed v0.1 scope has two roles. Do not implement adjudication to pass this probe.
    try:
        await drill.call("unsupported_adjudicator_rejected", "POST", route, path=path, token=manager,
            payload={"target_actor_profile_id": actor["actor_profile_id"], "role": "adjudicator",
                     "qualification": qualification, "reason": "Unsupported role negative probe"},
            expected=422)
    except ProbeFailure:
        pass
    await drill.call("unsupported_adjudicator_no_active_grant", "GET", route,
        path=path + "?status=active", token=manager, values={"items": [], "next_cursor": None})
    await drill.call("unsupported_adjudicator_no_access", "GET", "/api/v1/projects/{project_id}",
        path=f'/api/v1/projects/{project["id"]}', token=contributor, expected=404)


async def service_actor_cases(drill, issuer, admin, outsider):
    """Provision through HTTP and prove binding, replay, privacy and revocation."""
    route = "/api/v1/service-actors"
    subject = "external-drill-service"
    payload = {"service_identity": "workstream.review.projection", "subject": subject,
               "reason": "Verify exact service binding"}
    for label, token, status in (("missing_auth", None, 401), ("ungranted", outsider, 403)):
        await drill.call("service_" + label, "POST", route, token=token, payload=payload,
                         expected=status)
    for field in payload:
        invalids = (("missing", {k: v for k, v in payload.items() if k != field}),
                    ("null", payload | {field: None}), ("object", payload | {field: {}}),
                    ("empty", payload | {field: ""}))
        for label, invalid in invalids:
            await drill.call(f"service_{field}_{label}", "POST", route, token=admin,
                             payload=invalid, expected=422, fields=("body." + field,))
    for field, value, label in (("subject", " padded ", "padding"),
        ("subject", "é" * 101, "utf8_overflow"), ("reason", "é" * 251, "utf8_overflow"),
        ("service_identity", "unregistered.service", "unknown_identity"),
        ("unexpected", True, "extra")):
        await drill.call("service_" + field + "_" + label, "POST", route, token=admin,
                         payload=payload | {field: value}, expected=422)
    for label, value in (("missing_key", None), ("malformed_key", "not-a-uuid")):
        await drill.call("service_" + label, "POST", route, token=admin, payload=payload,
                         headers={"Idempotency-Key": value}, expected=422,
                         fields=("header.Idempotency-Key",))
    key = {"Idempotency-Key": str(uuid4())}
    created = await drill.call("service_provision", "POST", route, token=admin,
        payload=payload, headers=key, expected=201,
        values={"service_identity": payload["service_identity"], "actor_status": "active",
                "identity_link_status": "active", "provisioning_method": "manual_service_provisioning"},
        checks={"actor_profile_id": uuid_value, "created_at": timestamp_value, "linked_at": timestamp_value},
        exact_fields=("actor_profile_id", "service_identity", "actor_status", "identity_link_status",
                      "provisioning_method", "created_at", "linked_at"),
        fields=tuple("body." + field for field in payload))
    await drill.call("service_replay", "POST", route, token=admin, payload=payload,
                     headers=key, expected=201, values=created)
    await drill.call("service_key_conflict", "POST", route, token=admin,
                     payload=payload | {"subject": "different-subject"}, headers=key, expected=409,
                     values={"error.code": "idempotency_mismatch"})
    actor_id = created["actor_profile_id"]
    actor_route = "/api/v1/actors/{actor_profile_id}"
    actor_path = f"/api/v1/actors/{actor_id}"
    await drill.call("service_persisted_profile", "GET", actor_route, path=actor_path, token=admin,
        values={"actor_profile_id": actor_id, "actor_kind": "service", "status": "active",
                "provisioning_method": "manual_service_provisioning", "display_name": None,
                "service_identity": payload["service_identity"], "suspended_at": None,
                "reactivated_at": None, "deactivated_at": None})
    link = await drill.call("service_persisted_identity", "GET", actor_route + "/identity-links",
        path=actor_path + "/identity-links", token=admin,
        values={"actor_profile_id": actor_id, "subject_kind": "service", "status": "active",
                "revoked_at": None, "reactivated_at": None},
        checks={"identity_link_id": uuid_value, "linked_at": timestamp_value},
        exact_fields=("identity_link_id", "actor_profile_id", "subject_kind", "status", "linked_at",
                      "last_verified_at", "revoked_at", "reactivated_at"))
    service = issuer.issue(subject, subject_kind="service", scope="workstream:service")
    # An established service identity is not an administrative grant.
    await drill.call("service_cannot_provision", "POST", route, token=service,
                     payload=payload, expected=403)
    link = await drill.call("service_link_baseline", "GET", actor_route + "/identity-links",
        path=actor_path + "/identity-links", token=admin,
        values={key: value for key, value in link.items() if key != "last_verified_at"},
        checks={"last_verified_at": lambda value: value is None or timestamp_value(value)})
    for action, state in (("revoke", "revoked"), ("reactivate", "active")):
        mutation = "/api/v1/actor-identity-links/{identity_link_id}/" + action
        path = f'/api/v1/actor-identity-links/{link["identity_link_id"]}/{action}'
        for label, invalid in (("missing", {}), ("null", {"reason": None}),
                ("bool", {"reason": True}), ("nul", {"reason": "before\x00after"}),
                ("overflow", {"reason": "é" * 251}),
                ("extra", {"reason": "Valid", "unexpected": True})):
            await drill.call(f"link_{action}_{label}", "POST", mutation, path=path,
                token=admin, payload=invalid, expected=422,
                values={"error.code": "invalid_request", "error.retryable": False})
            await drill.call(f"link_{action}_{label}_unchanged", "GET", actor_route + "/identity-links",
                path=actor_path + "/identity-links", token=admin, values=link, exact_fields=link.keys())
        mutation_key = {"Idempotency-Key": str(uuid4())}
        result = await drill.call("service_link_" + action, "POST", mutation,
            path=path, token=admin, payload={"reason": " Verify binding lifecycle "}, headers=mutation_key,
            values={"resource_type": "actor_identity_link", "resource_id": link["identity_link_id"],
                    "version": None, "http_status": 200})
        changed_timestamp = "revoked_at" if action == "revoke" else "reactivated_at"
        expected_link = link | {"status": state}
        if action == "reactivate":
            expected_link["revoked_at"] = None
        link = await drill.call("service_link_" + action + "_readback", "GET", actor_route + "/identity-links",
            path=actor_path + "/identity-links", token=admin,
            values={key: value for key, value in expected_link.items() if key != changed_timestamp},
            checks={changed_timestamp: timestamp_value}, exact_fields=link.keys())
        await drill.call("service_link_" + action + "_replay", "POST", mutation,
            path=path, token=admin, payload={"reason": " Verify binding lifecycle "},
            headers=mutation_key, values=result)
        await drill.call("service_link_" + action + "_replay_unchanged", "GET", actor_route + "/identity-links",
            path=actor_path + "/identity-links", token=admin, values=link, exact_fields=link.keys())
        await drill.call("service_link_" + action + "_admission", "POST", route, token=service,
            payload=payload, expected=403,
            values={"error.code": "identity_link_revoked" if action == "revoke" else "permission_not_granted"})


async def isolation(metadata_path, *, require_empty=True):
    """Require an owned database; empty at startup, populated only for owner probes."""
    metadata = json.loads(metadata_path.read_text())
    url = os.environ.get("WORKSTREAM_DATABASE_URL", "")
    parsed = urlsplit(url)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not (parsed.scheme == "postgresql+asyncpg" and parsed.hostname == "127.0.0.1"
            and not parsed.query and not parsed.fragment
            and re.fullmatch(r"workstream_test_[a-f0-9]{12}", parsed.path[1:])
            and re.fullmatch(r"workstream_role_[a-f0-9]{12}", unquote(parsed.username or ""))
            and metadata.get("schema_version") == 2 and metadata.get("database_provisioned") is True
            and metadata.get("database_cleanup_complete") is False
            and metadata.get("tree_sha") == sha
            and metadata.get("database_name") == parsed.path[1:]
            and metadata.get("database_role") == unquote(parsed.username or "")):
        raise ProbeFailure("isolation_required")
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg:", "postgresql:", 1))
    try:
        row = await connection.fetchrow("select current_database() as db, current_user as role, "
                                        "(select count(*) from actor_profiles) as actors")
        if (row["db"] != metadata["database_name"] or row["role"] != metadata["database_role"]
                or (require_empty and row["actors"])):
            raise ProbeFailure("fresh_owned_database_required")
    finally:
        await connection.close()
    return url, sha


async def run(args, report, *, scenario=None):
    url, sha = await isolation(args.isolation_metadata)
    if (ROOT / ".env").exists():
        raise ProbeFailure("ambient_backend_env_file_forbidden")
    issuer = TokenIssuer()
    env = {"WORKSTREAM_DATABASE_URL": url, "WORKSTREAM_ENVIRONMENT": "local",
           "WORKSTREAM_AUTH_PROVIDER": "flow", "WORKSTREAM_FLOW_AUTH_ISSUER": issuer.issuer,
           "WORKSTREAM_FLOW_AUTH_AUDIENCE": issuer.audience,
           "WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET": issuer.secret,
           "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET": base64.b64encode(os.urandom(32)).decode(),
           "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET": base64.b64encode(os.urandom(32)).decode(),
           "WORKSTREAM_ARTIFACT_STORE_BACKEND": "disabled",
           "WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART": "false", "PYTHONPATH": str(ROOT)}
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    report.update(commit=sha, worktree_dirty=dirty,
        drill_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=["local synthetic Flow issuer, not deployed Flow",
        "artifact storage disabled; no provider/model calls", "no product fixtures or trigger suppression",
        "partial scenarios; no operation certified fully field-complete"], setup=[])
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
        "--host", "127.0.0.1", "--port", str(port), "--no-access-log"], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False,
                                     follow_redirects=False, timeout=20) as client:
            await wait_for_server(client, process)
            document = openapi_document(await client.get("/openapi.json"))
            drill = Drill(client, document, report)
            drill.isolation_metadata = args.isolation_metadata
            await health_cases(drill)
            if scenario is not None:
                await scenario(drill, issuer, env)
                return
            admin, manager, outsider = (issuer.issue(name) for name in ("admin", "manager", "outsider"))
            admin_id = await profile_cases(drill, issuer, admin)
            bootstrap = subprocess.run([sys.executable, "scripts/bootstrap_access_administrator.py",
                "--actor-profile-id", admin_id, "--execute"], env=env, cwd=ROOT,
                capture_output=True, timeout=30)
            if bootstrap.returncode != 0:
                raise ProbeFailure("bootstrap_failed")
            report["setup"].append("documented initial Access Administrator bootstrap CLI")
            manager_body = await drill.call("manager_profile", "GET", "/api/v1/actors/me", token=manager)
            await drill.call("outsider_profile", "GET", "/api/v1/actors/me", token=outsider)
            await project_cases(drill, admin, manager, outsider, manager_body["actor_profile_id"])
            await service_actor_cases(drill, issuer, admin, manager)
    finally:
        stop_server(process, preserving_failure=sys.exc_info()[0] is not None)


def main(*, scenario=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolation-metadata", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"result": "failed", "operations": {}, "cases": []}
    if args.report.resolve().is_relative_to(ROOT.parent):
        raise SystemExit("report must be outside repository")
    descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as output:
        try:
            if scenario is None:
                asyncio.run(run(args, report))
            else:
                asyncio.run(run(args, report, scenario=scenario))
            report["result"] = ("failed" if any(row["result"] == "failed" for row in report["cases"])
                                else "completed_partial_coverage")
        except Exception as exc:
            report["failure_kind"] = type(exc).__name__
            if isinstance(exc, ProbeFailure):
                report["failure_code"] = str(exc)
        finally:
            json.dump(report, output, indent=2)
            output.write("\n")
    print(report["result"])
    return 0 if report["result"] == "completed_partial_coverage" else 1


if __name__ == "__main__":
    raise SystemExit(main())
