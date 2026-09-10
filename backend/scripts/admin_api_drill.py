"""Twenty-actor real HTTP authority drill; only bootstrap uses a local command."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

import asyncpg

from external_api_drill import (ROOT, ProbeFailure, catalogue_expectations, main,
                               page_cases, page_matches, strict_equal, timestamp_value, uuid_value)
from urllib.parse import urlencode

ROSTER = (
    "bootstrap_a", "bootstrap_b", "manager_system", "manager_a", "manager_b",
    "operator", "finance_system", "finance_a", "audit_system", "audit_a",
    "submitter_a", "reviewer_a", "submitter_b", "reviewer_b", "dual_a",
    "outsider", "suspend_target", "deactivate_target", "link_target", "grant_target",
)
ROLES = ("access_administrator", "operator", "project_manager", "finance_authority", "audit_authority")
GRANTS = "/api/v1/admin-role-grants"
PROFILE = "/api/v1/actors/{actor_profile_id}"
LINKS = PROFILE + "/identity-links"
PROJECT = "/api/v1/projects/{project_id}"
REASON = {"reason": "Isolated twenty-actor authority drill"}


def grant_body(actor_id, role="operator", project_id=None):
    return dict(target_actor_profile_id=actor_id, role=role,
                scope_type="project" if project_id else "system", scope_project_id=project_id,
                **REASON)


def one_winner(outcomes):
    """No fixed winner and no false success if both calls win or both lose."""
    return sorted(outcomes) == [0, 3]


def exact_role_list(items):
    return len(items) == len(ROLES) and {row["role"] for row in items} == set(ROLES)


def one_grant_matches(items, expected, timestamp_fields=("granted_at",)):
    """Full single-row contract, with only newly observed timestamps as predicates."""
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        return False
    row = items[0]
    return (row.keys() == expected.keys() | set(timestamp_fields)
        and strict_equal({key: row[key] for key in expected}, expected)
        and all(timestamp_value(row[field]) for field in timestamp_fields))


class AuthorityDrill:
    def __init__(self, drill, issuer, env):
        self.drill, self.issuer, self.env = drill, issuer, env
        self.actors, self.tokens, self.grants, self.projects = {}, {}, {}, {}
        self.admin_rows, self.project_rows = {}, {}
        self.candidate_names = {}
        self.admin = self.second = None

    def proof(self, name, condition):
        row = {"name": name, "operation": "local_evidence", "result": "success" if condition else "failed"}
        self.drill.results.append(row)
        if not condition:
            raise ProbeFailure(name)
        print("evidence passed:", name, flush=True)

    def remember_grant(self, name, rows, key, expected):
        """A repeated response identity must not shrink independently expected truth."""
        try:
            valid = uuid_value(key)
        except (ValueError, TypeError, AttributeError):
            valid = False
        self.proof(name + "_distinct_identity", valid and key not in rows)
        rows[key] = expected

    async def snapshot(self, *, audit=False):
        connection = await asyncpg.connect(self.env["WORKSTREAM_DATABASE_URL"].replace(
            "postgresql+asyncpg:", "postgresql:", 1))
        try:
            async with connection.transaction(readonly=True, isolation="repeatable_read"):
                result = {}
                for table in ("authority_control", "admin_role_grants", "authority_idempotency_records",
                              "project_role_grants", "project_role_qualification_snapshots", "projects", "project_guides"):
                    result[table] = await connection.fetchval(
                        f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id), '[]')::text FROM {table} t")
                result["actors"] = await connection.fetchval(
                    "SELECT coalesce(jsonb_agg(jsonb_build_array(id,status) ORDER BY id),'[]')::text FROM actor_profiles")
                result["links"] = await connection.fetchval(
                    "SELECT coalesce(jsonb_agg(jsonb_build_array(id,status) ORDER BY id),'[]')::text FROM actor_identity_links")
                if audit:
                    result["audit"] = await connection.fetchval(
                        "SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]')::text FROM audit_events t")
                return result
        finally:
            await connection.close()

    async def command(self, actor_id, mode):
        process = await asyncio.create_subprocess_exec(sys.executable,
            "scripts/bootstrap_access_administrator.py", "--actor-profile-id", actor_id, mode,
            cwd=ROOT, env=self.env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 40)
            return process.returncode, json.loads(output)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def owner_guards(self, label, count, target=None, *, mutants=False):
        target = target or self.admin
        variants = ("none", "grant", "profile", "link") if mutants else ("none",)
        for variant in variants:
            before = await self.snapshot(audit=True)
            env = {key: self.env[key] for key in ("WORKSTREAM_DATABASE_URL", "WORKSTREAM_ENVIRONMENT", "PYTHONPATH")}
            process = await asyncio.create_subprocess_exec(sys.executable, "scripts/admin_guard_probe.py",
                "--isolation-metadata", str(self.drill.isolation_metadata),
                "--actor-id", self.actors[target], "--grant-id", self.grants[target],
                "--expected-count", str(count), "--mutant", variant,
                cwd=ROOT, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                output, _ = await asyncio.wait_for(process.communicate(), 35)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            result = json.loads(output)
            self.proof(label + "_" + variant + "_rollback", before == await self.snapshot(audit=True))
            expected_failures = {"none": [], "grant": ["grant_revoke"],
                "profile": ["profile_deactivate", "profile_suspend"], "link": ["link_revoke"]}[variant]
            self.drill.report.setdefault("owner_guard_probes", []).append({"state": label, **result})
            self.proof(label + "_" + variant + "_exact_result",
                process.returncode == (0 if variant == "none" else 2)
                and result.get("effective_count") == count
                and result.get("failed_checks") == expected_failures
                and set(result.get("checks", {})) == {"grant_revoke", "profile_suspend", "profile_deactivate", "link_revoke"})
            if variant == "none":
                for name, value in result["checks"].items():
                    self.proof(label + "_" + name, value == ("last_access_administrator" if count == 1 else None))

    async def call(self, name, method, route, actor=None, **kwargs):
        return await self.drill.call(name, method, route,
                                    token=self.tokens.get(actor), **kwargs)

    async def deny(self, name, method, route, actor, *, expected=403, code=None, **kwargs):
        before = await self.snapshot()
        error = None
        try:
            await self.call(name, method, route, actor, expected=expected,
                            values={"error.code": code} if code else {}, **kwargs)
        except ProbeFailure as exc:
            error = exc
        self.proof(name + "_no_authority_change", before == await self.snapshot())
        if error:
            raise error

    async def issue(self, name, caller, target, role, project=None):
        body = grant_body(self.actors[target], role, project)
        result = await self.call(name, "POST", GRANTS, caller, payload=body, expected=201,
            values={"resource_type": "admin_role_grant", "version": 1, "http_status": 201},
            checks={"resource_id": uuid_value})
        self.grants[target] = result["resource_id"]
        self.remember_grant(name, self.admin_rows, result["resource_id"], {
            "target_actor_profile_id": self.actors[target], "role": role,
            "scope_type": body["scope_type"], "scope_project_id": project, "status": "active"})
        return result

    async def bootstrap(self):
        for label in ROSTER:
            self.tokens[label] = self.issuer.issue("admin-drill-" + label)
            body = await self.call("profile_" + label, "GET", "/api/v1/actors/me", label,
                values={"actor_kind": "human", "status": "active", "admin_roles": [],
                        "project_role_grants": []}, checks={"actor_profile_id": uuid_value})
            self.actors[label] = body["actor_profile_id"]
        self.proof("twenty_distinct_profiles", len(set(self.actors.values())) == 20)
        self.drill.report["actor_roster"] = [{"label": label, "actor_profile_id": actor}
                                             for label, actor in self.actors.items()]
        before = await self.snapshot(audit=True)
        code, body = await self.command(str(uuid4()), "--execute")
        self.proof("bootstrap_missing_target", code == 2 and body["result_code"] == "target_ineligible")
        self.proof("bootstrap_invalid_unchanged", before == await self.snapshot(audit=True))
        code, body = await self.command(self.actors["bootstrap_a"], "--dry-run")
        self.proof("bootstrap_dry_run_eligible", code == 0 and body["would_change"] is True)
        self.proof("bootstrap_dry_run_unchanged", before == await self.snapshot(audit=True))
        for label in ("bootstrap_a", "bootstrap_b"):
            await self.deny("before_bootstrap_" + label, "GET", "/api/v1/authorization/permissions",
                            label, code="permission_not_granted")
        results = await asyncio.gather(*(self.command(self.actors[label], "--execute")
                                        for label in ("bootstrap_a", "bootstrap_b")))
        self.proof("bootstrap_concurrent_one_winner", one_winner([r[0] for r in results]))
        win = next(i for i, r in enumerate(results) if r[0] == 0)
        self.admin, self.second = (("bootstrap_a", "bootstrap_b") if win == 0 else ("bootstrap_b", "bootstrap_a"))
        grant_id = results[win][1]["grant_id"]
        self.grants[self.admin] = grant_id
        self.remember_grant("bootstrap", self.admin_rows, grant_id, {
            "target_actor_profile_id": self.actors[self.admin], "role": "access_administrator",
            "scope_type": "system", "scope_project_id": None, "status": "active"})
        self.proof("bootstrap_loser_binds_winner", results[1-win][1]["grant_id"] == grant_id)
        state = await self.snapshot(audit=True)
        grants, control, events = (json.loads(state[k]) for k in ("admin_role_grants", "authority_control", "audit"))
        self.proof("bootstrap_atomic_state", len(grants) == 1 and grants[0]["role"] == "access_administrator"
                   and grants[0]["target_actor_profile_id"] == self.actors[self.admin]
                   and control[0]["bootstrap_completed"] is True and control[0]["bootstrap_grant_id"] == grant_id
                   and sum(e["event_type"] == "InitialAccessAdministratorBootstrapped" for e in events) == 1)
        before = await self.snapshot()
        code, body = await self.command(self.actors["outsider"], "--execute")
        self.proof("bootstrap_later_conflict", code == 3 and body["grant_id"] == grant_id)
        self.proof("bootstrap_later_no_authority_change", before == await self.snapshot())
        await self.owner_guards("initial_single_admin", 1, mutants=True)
        await self.issue("second_access_admin", self.admin, self.second, "access_administrator")
        await self.owner_guards("two_active_admins", 2)
        await self.call("suspend_second_admin", "POST", PROFILE + "/suspend", self.admin,
            path=f'/api/v1/actors/{self.actors[self.second]}/suspend', payload=REASON)
        await self.owner_guards("second_admin_suspended", 1)
        await self.call("restore_second_admin", "POST", PROFILE + "/reactivate", self.admin,
            path=f'/api/v1/actors/{self.actors[self.second]}/reactivate', payload=REASON)
        await self.owner_guards("second_admin_reactivated", 2)
        second_link = await self.call("second_admin_link", "GET", LINKS, self.admin,
            path=f'/api/v1/actors/{self.actors[self.second]}/identity-links')
        for action, count in (("revoke", 1), ("reactivate", 2)):
            await self.call("second_admin_link_" + action, "POST",
                "/api/v1/actor-identity-links/{identity_link_id}/" + action, self.admin,
                path=f'/api/v1/actor-identity-links/{second_link["identity_link_id"]}/{action}', payload=REASON)
            await self.owner_guards("second_admin_link_" + action, count)
        await self.issue("system_manager", self.admin, "manager_system", "project_manager")
        for label in ("a", "b"):
            body = await self.call("project_" + label, "POST", "/api/v1/projects", "manager_system",
                payload={"name": "Authority project " + label, "slug": "authority-" + uuid4().hex},
                expected=201, checks={"id": uuid_value})
            self.projects[label] = body["id"]
        for label, role, scope in (("manager_a", "project_manager", "a"),
                ("manager_b", "project_manager", "b"), ("operator", "operator", None),
                ("finance_system", "finance_authority", None), ("finance_a", "finance_authority", "a"),
                ("audit_system", "audit_authority", None), ("audit_a", "audit_authority", "a")):
            await self.issue("grant_" + label, self.admin, label, role, self.projects.get(scope))

    async def role_matrix(self):
        for label in ROSTER:
            allowed = label in (self.admin, self.second, "audit_system")
            route = "/api/v1/authorization/admin-role-definitions"
            if allowed:
                expected_body = catalogue_expectations()["admin-role-definitions"]
                body = await self.call("role_definitions_" + label, "GET", route, label,
                    values=expected_body, exact_fields=expected_body.keys())
                self.proof("closed_role_list_" + label, exact_role_list(body["items"]))
                for row in body["items"]:
                    expected = {"system"} if row["role"] in ROLES[:2] else {"system", "project"}
                    self.proof("role_scopes_" + label + "_" + row["role"], set(row["allowed_scopes"]) == expected)
            else:
                await self.deny("role_definitions_" + label, "GET", route, label, code="permission_not_granted")
        for label in ("operator", "manager_system", "manager_a", "finance_system", "finance_a",
                      "audit_system", "audit_a", "outsider"):
            await self.deny("cannot_issue_admin_" + label, "POST", GRANTS, label,
                            payload=grant_body(self.actors["grant_target"]), code="permission_not_granted")
        for label in (self.admin, "operator", "manager_system", "manager_a", "manager_b",
                      "finance_system", "finance_a", "audit_system", "audit_a", "outsider"):
            for project in ("a", "b"):
                allowed = label in ("operator", "manager_system", "finance_system", "audit_system") or (
                    label in ("manager_a", "finance_a", "audit_a") and project == "a") or (
                    label == "manager_b" and project == "b")
                kwargs = dict(path=f'/api/v1/projects/{self.projects[project]}')
                if allowed:
                    await self.call("project_read_" + label + project, "GET", PROJECT, label,
                                    values={"id": self.projects[project]}, **kwargs)
                else:
                    await self.deny("project_read_" + label + project, "GET", PROJECT, label, expected=404, **kwargs)
        for label in (self.admin, "operator", "manager_a", "finance_system", "audit_system", "outsider"):
            await self.deny("cannot_create_project_" + label, "POST", "/api/v1/projects", label,
                payload={"name": "Forbidden creation", "slug": "denied-" + uuid4().hex}, expected=403)
        forged = "forged_claims"
        self.tokens[forged] = self.issuer.issue("admin-drill-outsider", roles=["admin", "access_administrator"])
        await self.deny("token_claims_cannot_grant_authority", "GET", "/api/v1/authorization/permissions",
                        forged, code="permission_not_granted")

    async def grant_edges(self):
        for role in ROLES:
            await self.deny("self_grant_" + role, "POST", GRANTS, self.admin,
                payload=grant_body(self.actors[self.admin], role), code="self_grant_forbidden")
        await self.deny("self_admin_revoke", "POST", GRANTS + "/{grant_id}/revoke", self.admin,
            path=GRANTS + "/" + self.grants[self.admin] + "/revoke", payload=REASON,
            code="self_role_revoke_forbidden")
        body = grant_body(self.actors["grant_target"])
        invalids = [("missing_" + field, {k:v for k,v in body.items() if k != field})
                    for field in ("target_actor_profile_id", "role", "scope_type", "reason")]
        invalids += [("null_" + field, body | {field: None})
                     for field in ("target_actor_profile_id", "role", "scope_type", "reason")]
        invalids += [("unknown_role", body | {"role": "owner"}), ("unknown_scope", body | {"scope_type": "all"}),
                     ("extra", body | {"admin": True}), ("empty_reason", body | {"reason": ""}),
                     ("invalid_actor", body | {"target_actor_profile_id": "bad"})]
        for name, invalid in invalids:
            await self.deny("grant_" + name, "POST", GRANTS, self.admin, payload=invalid, expected=422)
        for role in ROLES[:2]:
            await self.deny("system_only_" + role, "POST", GRANTS, self.admin,
                payload=grant_body(self.actors["grant_target"], role, self.projects["a"]), expected=422)
        await self.deny("missing_scope_project", "POST", GRANTS, self.admin,
            payload=body | {"role": "project_manager", "scope_type": "project"}, expected=400)
        key = {"Idempotency-Key": str(uuid4())}
        result = await self.call("grant_exact", "POST", GRANTS, self.admin, payload=body, headers=key, expected=201,
            values={"resource_type": "admin_role_grant", "version": 1, "http_status": 201},
            checks={"resource_id": uuid_value},
            exact_fields=("resource_type", "resource_id", "version", "http_status"))
        history_route = PROFILE + "/admin-role-grants"
        history_path = f'/api/v1/actors/{self.actors["grant_target"]}/admin-role-grants?scope_type=system&status=all'
        expected_row = {
            "grant_id": result["resource_id"], "target_actor_profile_id": self.actors["grant_target"],
            "role": body["role"], "scope_type": "system", "scope_project_id": None,
            "status": "active", "version": 1, "granted_by_ref_kind": "actor_profile",
            "granted_by_ref": self.actors[self.admin],
            "granted_by_admin_role_grant_id": self.grants[self.admin], "grant_reason": body["reason"],
            "revoked_by_actor_profile_id": None, "revoked_by_admin_role_grant_id": None,
            "revoked_reason": None, "revoked_at": None,
        }
        active = await self.call("grant_before_replay_full_history", "GET", history_route, self.admin,
            path=history_path, values={"total": 1, "next_cursor": None},
            checks={"items": lambda items: one_grant_matches(items, expected_row)},
            exact_fields=("items", "total", "next_cursor"))
        before = await self.snapshot(audit=True)
        await self.call("grant_exact_replay", "POST", GRANTS, self.admin, payload=body,
                        headers=key, expected=201, values=result)
        # Replay may record decision evidence; authority itself must not change.
        self.proof("grant_replay_no_duplicate", {k:v for k,v in before.items() if k != "audit"} == await self.snapshot())
        await self.call("grant_replay_full_history_unchanged", "GET", history_route, self.admin,
            path=history_path, values=active, exact_fields=active.keys())
        await self.deny("grant_key_mismatch", "POST", GRANTS, self.admin,
            payload=body | {"reason": "Different reason"}, headers=key, expected=409, code="idempotency_mismatch")
        await self.deny("grant_duplicate", "POST", GRANTS, self.admin, payload=body, expected=409)
        self.grants["grant_target"] = result["resource_id"]
        self.remember_grant("grant_target", self.admin_rows, result["resource_id"], {
            "target_actor_profile_id": self.actors["grant_target"], "role": "operator",
            "scope_type": "system", "scope_project_id": None, "status": "active"})
        for label in (self.admin, "audit_system"):
            history = PROFILE + "/admin-role-grants"
            read = await self.call("grant_history_" + label, "GET", history, label,
                path=history_path, values=active, exact_fields=active.keys())
            rows = read["items"]
            self.proof("grant_history_exact_" + label, len(rows) == 1 and rows[0]["grant_id"] == result["resource_id"]
                       and rows[0]["role"] == "operator" and rows[0]["status"] == "active"
                       and rows[0]["granted_by_ref"] == self.actors[self.admin])
        route = GRANTS + "/{grant_id}/revoke"
        path = GRANTS + "/" + result["resource_id"] + "/revoke"
        revoke_key = {"Idempotency-Key": str(uuid4())}
        revoked = await self.call("grant_target_revoke", "POST", route, self.admin,
            path=path, payload=REASON, headers=revoke_key,
            values={"resource_id": result["resource_id"], "version": 2, "http_status": 200})
        self.admin_rows[result["resource_id"]]["status"] = "revoked"
        expected_revoked = active["items"][0] | {
            "status": "revoked", "version": 2,
            "revoked_by_actor_profile_id": self.actors[self.admin],
            "revoked_by_admin_role_grant_id": self.grants[self.admin], "revoked_reason": REASON["reason"],
        }
        del expected_revoked["revoked_at"]
        revoked_history = await self.call("revoke_before_replay_full_history", "GET", history_route, self.admin,
            path=history_path, values={"total": 1, "next_cursor": None},
            checks={"items": lambda items: one_grant_matches(items, expected_revoked, ("revoked_at",))},
            exact_fields=("items", "total", "next_cursor"))
        before = await self.snapshot()
        await self.call("grant_target_revoke_replay", "POST", route, self.admin,
            path=path, payload=REASON, headers=revoke_key, values=revoked)
        self.proof("revoke_replay_no_change", before == await self.snapshot())
        await self.call("revoke_replay_full_history_unchanged", "GET", history_route, self.admin,
            path=history_path, values=revoked_history, exact_fields=revoked_history.keys())
        await self.deny("grant_target_revoke_mismatch", "POST", route, self.admin,
            path=path, payload={"reason": "Changed revoke reason"}, headers=revoke_key,
            expected=409, code="idempotency_mismatch")
        stored = await self.call("revoked_grant_history", "GET", PROFILE + "/admin-role-grants", self.admin,
            path=history_path, values=revoked_history, exact_fields=revoked_history.keys())
        self.proof("revocation_history_retained", len(stored["items"]) == 1
                   and stored["items"][0]["status"] == "revoked" and stored["items"][0]["version"] == 2)
        await self.deny("revoked_operator_no_project_access", "GET", PROJECT, "grant_target",
            path=f'/api/v1/projects/{self.projects["a"]}', expected=404)

    async def contributor_roles(self):
        qualification = {"skills_snapshot": {"availability": "unavailable", "reference_ids": [],
                         "unavailable_reason": "not_collected"},
            "reputation_snapshot": {"availability": "unavailable", "reference_ids": [],
                         "unavailable_reason": "no_record"},
            "prior_project_work_refs": [], "external_expertise_refs": []}
        for label, role, project in (("submitter_a", "submitter", "a"), ("reviewer_a", "reviewer", "a"),
                ("submitter_b", "submitter", "b"), ("reviewer_b", "reviewer", "b"),
                ("dual_a", "submitter", "a"), ("dual_a", "reviewer", "a")):
            route = PROJECT + "/role-grants"
            result = await self.call("project_grant_" + label + role, "POST", route, "manager_" + project,
                path=f'/api/v1/projects/{self.projects[project]}/role-grants', expected=201,
                payload=dict(target_actor_profile_id=self.actors[label], role=role, qualification=qualification, **REASON),
                values={"actor_profile_id": self.actors[label], "project_id": self.projects[project],
                        "role": role, "status": "active"})
            self.remember_grant("project_grant_" + label + role, self.project_rows, result["id"], {
                "actor_profile_id": self.actors[label], "project_id": self.projects[project],
                "role": role, "status": "active"})
        for label in ("submitter_a", "reviewer_a", "submitter_b", "reviewer_b", "dual_a"):
            own = "b" if label.endswith("b") else "a"
            for project in ("a", "b"):
                await self.call("contributor_read_" + label + project, "GET", PROJECT, label,
                    path=f'/api/v1/projects/{self.projects[project]}', expected=200 if project == own else 404)
            await self.deny("contributor_no_admin_grant_" + label, "POST", GRANTS, label,
                payload=grant_body(self.actors["grant_target"]), code="permission_not_granted")
            expected_roles = ["reviewer", "submitter"] if label == "dual_a" else [label.split("_")[0]]
            await self.call("contributor_context_" + label, "GET", "/api/v1/actors/me/authorization-context", label,
                path=f'/api/v1/actors/me/authorization-context?project_id={self.projects[own]}',
                values={"admin_roles": [], "project_roles": expected_roles})
        route = PROJECT + "/role-grants"
        path = f'/api/v1/projects/{self.projects["a"]}/role-grants'
        for role in ("submitter", "reviewer"):
            await self.deny("manager_self_project_grant_" + role, "POST", route, "manager_a",
                path=path, payload=dict(target_actor_profile_id=self.actors["manager_a"],
                role=role, qualification=qualification, **REASON), code="self_grant_forbidden")

    async def candidate_visibility(self, name, excluded=(), *, limit=100):
        """Known human membership and exact privacy-safe rows, not task eligibility."""
        rows = {actor: {"display_name": self.candidate_names.get(label)}
                for label, actor in self.actors.items()
                if label != "manager_a" and label not in excluded}
        return await page_cases(self.drill, name, PROJECT + "/contributor-candidates",
            f'/api/v1/projects/{self.projects["a"]}/contributor-candidates',
            self.tokens["manager_a"], rows, identity="actor_profile_id", limit=limit,
            exact_item_fields=("actor_profile_id", "display_name"))

    async def pagination(self):
        """Exercise populated pages with expected identities owned by HTTP setup."""
        admin_cursor = None
        for scope in (None, "a", "b"):
            project = self.projects.get(scope)
            query = {"scope_type": "project" if project else "system"}
            if project:
                query["scope_project_id"] = project
            for status in ("all", "active", "revoked"):
                rows = {key: row for key, row in self.admin_rows.items()
                        if row["scope_project_id"] == project
                        and (status == "all" or row["status"] == status)}
                cursor = await page_cases(self.drill, f"admin_pages_{scope}_{status}",
                    GRANTS, GRANTS, self.tokens[self.admin], rows, identity="grant_id",
                    query=query | {"status": status}, limit=2, total=True)
                if scope is None and status == "all":
                    admin_cursor = cursor
        if not admin_cursor:
            self.proof("populated_admin_cursor_required", False)
        for cursor in ("!invalid", "x" * 513):
            await self.deny("admin_bad_cursor_" + str(len(cursor)), "GET", GRANTS, self.admin,
                path=GRANTS + "?" + urlencode({"scope_type": "system", "cursor": cursor}),
                expected=422 if len(cursor) > 512 else 400,
                fields=("query.cursor",))
        scoped_rows = {key: row for key, row in self.admin_rows.items()
                       if row["scope_project_id"] == self.projects["a"]}
        # Admin cursors are positional, not signed query authority. Filters still apply.
        await self.call("admin_cursor_cannot_widen_scope", "GET", GRANTS, "audit_a",
            path=GRANTS + "?" + urlencode(dict(scope_type="project",
                scope_project_id=self.projects["a"], status="all", cursor=admin_cursor)),
            values={"total": len(scoped_rows)},
            checks={"items": lambda rows: page_matches(rows, scoped_rows, set(), 50, "grant_id")})
        await self.deny("admin_cursor_no_foreign_authority", "GET", GRANTS, "audit_a",
            path=GRANTS + "?" + urlencode(dict(scope_type="project",
                scope_project_id=self.projects["b"], cursor=admin_cursor)), code="scope_not_authorized")
        history = PROFILE + "/admin-role-grants"
        await page_cases(self.drill, "admin_target_history", history,
            f'/api/v1/actors/{self.actors["grant_target"]}/admin-role-grants', self.tokens[self.admin],
            {key: row for key, row in self.admin_rows.items()
             if row["target_actor_profile_id"] == self.actors["grant_target"]}, identity="grant_id",
            query={"scope_type": "system", "status": "all"}, total=True)
        route = PROJECT + "/role-grants"
        path = f'/api/v1/projects/{self.projects["a"]}/role-grants'
        rows = {key: row for key, row in self.project_rows.items() if row["project_id"] == self.projects["a"]}
        cursor = await page_cases(self.drill, "project_pages", route, path,
            self.tokens["manager_a"], rows, identity="id")
        if not cursor:
            self.proof("populated_project_cursor_required", False)
        for role in ("submitter", "reviewer"):
            await page_cases(self.drill, "project_filtered_" + role, route, path,
                self.tokens["manager_a"], {key: row for key, row in rows.items() if row["role"] == role},
                identity="id", query={"role": role, "status": "active"})
        await page_cases(self.drill, "project_revoked_empty", route, path,
            self.tokens["manager_a"], {}, identity="id", query={"status": "revoked"})
        variants = {"malformed": {"cursor": "!invalid"},
                    "tampered": {"cursor": ("A" if cursor[0] != "A" else "B") + cursor[1:]},
                    "role": {"role": "submitter"}, "status": {"status": "active"},
                    "limit": {"limit": 2}}
        for name, changes in variants.items():
            await self.deny("project_cursor_" + name, "GET", route, "manager_a",
                path=path + "?" + urlencode(dict(limit=1, cursor=cursor) | changes),
                expected=400, code="invalid_cursor", fields=tuple("query." + key for key in changes))
        await self.deny("project_cursor_foreign_query", "GET", route, "manager_system",
            path=f'/api/v1/projects/{self.projects["b"]}/role-grants?' + urlencode(dict(limit=1, cursor=cursor)),
            expected=400, code="invalid_cursor")
        await self.deny("project_cursor_foreign_authority", "GET", route, "manager_a",
            path=f'/api/v1/projects/{self.projects["b"]}/role-grants?' + urlencode(dict(limit=1, cursor=cursor)),
            expected=404)
        candidate_route = PROJECT + "/contributor-candidates"
        candidate_path = f'/api/v1/projects/{self.projects["a"]}/contributor-candidates'
        await self.call("candidate_populated_profile", "PATCH", "/api/v1/actors/me", "outsider",
            payload={"display_name": "Candidate 名", "contact_email": "Private candidate contact"},
            values={"display_name": "Candidate 名", "contact_email": "Private candidate contact"})
        self.candidate_names["outsider"] = "Candidate 名"
        candidate_cursor = await self.candidate_visibility("candidate_pages", limit=3)
        self.proof("candidate_cursor_present", isinstance(candidate_cursor, str) and bool(candidate_cursor))
        for name, changes in (("malformed", {"cursor": "!invalid"}),
                              ("tampered", {"cursor": ("A" if candidate_cursor[0] != "A" else "B") + candidate_cursor[1:]}),
                              ("limit_binding", {"limit": 2})):
            await self.deny("candidate_cursor_" + name, "GET", candidate_route, "manager_a",
                path=candidate_path + "?" + urlencode(dict(limit=3, cursor=candidate_cursor) | changes),
                expected=400, code="invalid_cursor")
        other_candidates = f'/api/v1/projects/{self.projects["b"]}/contributor-candidates'
        await self.deny("candidate_cursor_project_binding", "GET", candidate_route, "manager_system",
            path=other_candidates + "?" + urlencode(dict(limit=3, cursor=candidate_cursor)),
            expected=400, code="invalid_cursor")
        await self.deny("candidate_foreign_project", "GET", candidate_route, "manager_a",
            path=other_candidates, expected=404)
        await self.deny("candidate_ungranted_actor", "GET", candidate_route, "outsider",
            path=candidate_path, expected=404)
        await self.drill.call("candidate_no_auth", "GET", candidate_route,
            path=candidate_path, expected=401)
        for name, changes in (("zero_limit", {"limit": 0}), ("large_limit", {"limit": 101}),
                              ("bad_limit", {"limit": "abc"}), ("long_cursor", {"cursor": "x" * 513})):
            await self.deny("candidate_query_" + name, "GET", candidate_route, "manager_a",
                path=candidate_path + "?" + urlencode(changes), expected=422,
                fields=tuple("query." + key for key in changes))
        await self.deny("cursor_cannot_cross_operation", "GET", candidate_route, "manager_a",
            path=candidate_path + "?" + urlencode(dict(limit=1, cursor=cursor)),
            expected=400, code="invalid_cursor")
        for name, changes in (("zero_limit", {"limit": 0}), ("large_limit", {"limit": 101}),
                              ("bad_limit", {"limit": "abc"}), ("bad_role", {"role": "adjudicator"}),
                              ("bad_status", {"status": "all"}), ("long_cursor", {"cursor": "x" * 513})):
            await self.deny("project_query_" + name, "GET", route, "manager_a",
                path=path + "?" + urlencode(changes), expected=422,
                fields=tuple("query." + key for key in changes))

    async def lifecycle(self):
        excluded_candidates = set()
        for label, action, state in (("suspend_target", "suspend", "suspended"),
                                    ("deactivate_target", "deactivate", "deactivated")):
            await self.issue("lifecycle_grant_" + label, self.admin, label, "audit_authority")
            await self.call("before_lifecycle_" + label, "GET", "/api/v1/authorization/permissions", label)
            await self.call("lifecycle_" + action, "POST", PROFILE + "/" + action, self.admin,
                path=f'/api/v1/actors/{self.actors[label]}/{action}', payload=REASON)
            await self.call("lifecycle_read_" + label, "GET", PROFILE, self.admin,
                path=f'/api/v1/actors/{self.actors[label]}', values={"status": state})
            excluded_candidates.add(label)
            await self.candidate_visibility("candidates_after_" + action, excluded_candidates)
            await self.deny("inactive_catalogue_" + label, "GET", "/api/v1/authorization/permissions", label,
                            code="actor_" + state)
        await self.call("reactivate_suspended", "POST", PROFILE + "/reactivate", self.admin,
            path=f'/api/v1/actors/{self.actors["suspend_target"]}/reactivate', payload=REASON)
        await self.call("reactivated_catalogue", "GET", "/api/v1/authorization/permissions", "suspend_target")
        excluded_candidates.remove("suspend_target")
        await self.candidate_visibility("candidates_after_actor_reactivate", excluded_candidates)
        await self.deny("terminal_deactivated", "POST", PROFILE + "/reactivate", self.admin,
            path=f'/api/v1/actors/{self.actors["deactivate_target"]}/reactivate', payload=REASON,
            expected=409, code="actor_deactivated_terminal")
        await self.issue("link_target_grant", self.admin, "link_target", "audit_authority")
        link = await self.call("link_target_read", "GET", LINKS, self.admin,
            path=f'/api/v1/actors/{self.actors["link_target"]}/identity-links', values={"status": "active"})
        for action, state in (("revoke", "revoked"), ("reactivate", "active")):
            await self.call("human_link_" + action, "POST", "/api/v1/actor-identity-links/{identity_link_id}/" + action,
                self.admin, path=f'/api/v1/actor-identity-links/{link["identity_link_id"]}/{action}', payload=REASON)
            await self.call("human_link_read_" + action, "GET", LINKS, self.admin,
                path=f'/api/v1/actors/{self.actors["link_target"]}/identity-links', values={"status": state})
            await self.candidate_visibility("candidates_after_link_" + action,
                excluded_candidates | ({"link_target"} if action == "revoke" else set()))
            if action == "revoke":
                await self.deny("revoked_link_catalogue", "GET", "/api/v1/authorization/permissions", "link_target")
            else:
                await self.call("reactivated_link_catalogue", "GET", "/api/v1/authorization/permissions", "link_target")

    async def last_admin(self):
        # Actual simultaneous HTTP requests; no claim of forced database lock overlap.
        print("Waiting for a fresh mutation-rate window before cross-admin calls", flush=True)
        await asyncio.sleep(61)
        async def revoke(caller, target):
            headers = {"Authorization": "Bearer " + self.tokens[caller], "Idempotency-Key": str(uuid4()),
                       "X-Request-ID": str(uuid4()), "X-Correlation-ID": str(uuid4())}
            response = await self.drill.client.post(GRANTS + "/" + self.grants[target] + "/revoke",
                                                    json=REASON, headers=headers)
            return caller, target, response
        results = await asyncio.gather(revoke(self.admin, self.second), revoke(self.second, self.admin))
        self.proof("cross_admin_one_revocation", sorted(r[2].status_code for r in results) == [200, 403])
        survivor, loser, response = next(r for r in results if r[2].status_code == 200)
        self.proof("cross_admin_revoked_exact_target", response.json()["resource_id"] == self.grants[loser])
        self.proof("cross_admin_loser_current_authority", next(r[2] for r in results if r[2].status_code == 403)
                   .json()["error"]["code"] == "permission_not_granted")
        state = await self.snapshot()
        active = [r for r in json.loads(state["admin_role_grants"]) if r["role"] == "access_administrator"
                  and r["status"] == "active"]
        self.proof("one_active_admin_remains", len(active) == 1 and active[0]["target_actor_profile_id"] == self.actors[survivor])
        await self.call("survivor_still_authorized", "GET", "/api/v1/authorization/permissions", survivor)
        await self.deny("loser_no_longer_authorized", "GET", "/api/v1/authorization/permissions", loser,
                        code="permission_not_granted")
        await self.deny("last_admin_self_revoke", "POST", GRANTS + "/{grant_id}/revoke", survivor,
            path=GRANTS + "/" + self.grants[survivor] + "/revoke", payload=REASON, code="self_role_revoke_forbidden")
        for action in ("suspend", "deactivate"):
            await self.deny("last_admin_self_" + action, "POST", PROFILE + "/" + action, survivor,
                path=f'/api/v1/actors/{self.actors[survivor]}/{action}', payload=REASON, code="resource_guard_denied")
        link = await self.call("last_admin_link", "GET", LINKS, survivor,
            path=f'/api/v1/actors/{self.actors[survivor]}/identity-links')
        await self.deny("last_admin_own_link_revoke", "POST", "/api/v1/actor-identity-links/{identity_link_id}/revoke",
            survivor, path=f'/api/v1/actor-identity-links/{link["identity_link_id"]}/revoke',
            payload=REASON, code="resource_guard_denied")
        await self.owner_guards("after_cross_revoke", 1, target=survivor)
        self.drill.report["limitations"].append("HTTP self-removal uses self guards; count guards separately executed with real stored facts in rollback-only owner probes")


async def scenario(drill, issuer, env):
    drill.report["scenario"] = "twenty_actor_authority"
    drill.report["scenario_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    audit = AuthorityDrill(drill, issuer, env)
    await audit.bootstrap()
    for name in ("role_matrix", "grant_edges", "contributor_roles", "pagination", "lifecycle", "last_admin"):
        try:
            await getattr(audit, name)()
        except ProbeFailure:
            drill.report.setdefault("incomplete_groups", []).append(name)
    drill.report["setup"].append("Twenty HTTP human profiles; actual local bootstrap CLI; all later grants via HTTP")


if __name__ == "__main__":
    raise SystemExit(main(scenario=scenario))
