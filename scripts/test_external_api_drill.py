"""Focused evidence-integrity tests for the standalone external-client drill."""

import importlib.util
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx

SOURCE = Path(__file__).resolve().parents[1] / "backend/scripts/external_api_drill.py"
SPEC = importlib.util.spec_from_file_location("external_api_drill", SOURCE)
drill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drill)


class ContractTests(unittest.TestCase):
    def test_guide_oracle_normalizes_and_binds_exact_ordered_examples(self):
        body = drill.guide_payload("initial") | {"task_examples": [{"content": "名 claim"}, {"content": "Second"}]}
        expected = drill.guide_expectations(body, "project", "manager")
        self.assertEqual(expected["values"]["task_examples"], [
            {"content": "名 claim", "title": None, "labels": []},
            {"content": "Second", "title": None, "labels": []}])
        digest = expected["values"]["task_examples_hash"]
        for examples in (list(reversed(body["task_examples"])), [{"content": "changed"}],
                         [{"content": "名 claim", "title": "Title"}, {"content": "Second"}],
                         [{"content": "名 claim", "labels": ["tag"]}, {"content": "Second"}]):
            self.assertNotEqual(drill.example_commitment(examples)[1], digest)
        self.assertNotIn("content_markdown", expected["exact_fields"])
        self.assertEqual(set(expected["exact_fields"]), {"id", "project_id", "version", "status",
            "change_summary", "task_examples", "task_examples_hash", "approved_by", "effective_at",
            "superseded_at", "created_by", "created_at", "updated_at", "documents", "setup"})
        wrong = dict(expected["values"], created_by="foreign")
        self.assertFalse(drill.strict_equal(wrong, expected["values"]))

    def test_guide_declaration_oracle_rejects_wrong_or_leaked_fields(self):
        from uuid import uuid4
        body = drill.guide_payload("initial")
        checks = drill.guide_expectations(body, "project", "manager")["checks"]
        document = dict(document_id=str(uuid4()), order=0, **body["documents"][0])
        self.assertTrue(checks["documents"]([document]))
        for changes in ({"label": "other.pdf"}, {"media_type": "text/plain"},
                        {"order": True}, {"document_id": "bad"}, {"snapshot_id": "private"}):
            with self.assertRaises(drill.ProbeFailure):
                drill.verify_response(httpx.Response(201, json={"documents": [document | changes]}),
                                      201, {}, {"documents": checks["documents"]})
        self.assertFalse(checks["documents"]([]))
        setup = {"id": str(uuid4()), "status": "awaiting_documents"}
        self.assertTrue(checks["setup"](setup))
        self.assertFalse(checks["setup"](setup | {"status": "queued"}))
        self.assertFalse(checks["setup"](setup | {"celery_task_id": "private"}))
        self.assertEqual(drill.guide_metadata({"id": "guide", "documents": [document], "setup": setup}),
                         {"id": "guide"})

    def test_project_grant_contract_rejects_wrong_provenance_and_extra_fields(self):
        receipt = dict(id="grant", qualification_snapshot_id="snapshot", project_id="project",
                       actor_profile_id="contributor", role="reviewer", status="active", version=1)
        qualification = dict(skills_snapshot={"availability": "unavailable", "reference_ids": [],
                                               "unavailable_reason": "not_collected"},
                             reputation_snapshot={"availability": "unavailable", "reference_ids": [],
                                                   "unavailable_reason": "no_record"},
                             prior_project_work_refs=[], external_expertise_refs=[])
        contract = drill.project_grant_read_expectations(receipt, qualification, "manager", "manager-grant", "Reason")
        row = {key: value for key, value in receipt.items() if key != "qualification_snapshot_id"}
        row.update(grant_method="manual", granted_by_actor_profile_id="manager",
                   granted_by_admin_role_grant_id="manager-grant", grant_reason="Reason",
                   granted_at="2026-01-01T00:00:00+00:00", revoked_by_actor_profile_id=None,
                   revoked_at=None, revoked_reason=None,
                   qualification_snapshot=dict(id="snapshot", requested_role="reviewer", **qualification,
                       captured_by_actor_profile_id="manager", captured_by_admin_role_grant_id="manager-grant",
                       captured_at="2026-01-01T00:00:00+00:00"))
        def verify(value):
            return drill.verify_response(httpx.Response(200, json=value), 200,
                contract["values"], contract["checks"], contract["exact_fields"])
        verify(row)
        mutants = [row | {"private": "unexpected"}, row | {"granted_by_admin_role_grant_id": "other-grant"}]
        for field in ("captured_by_actor_profile_id", "captured_by_admin_role_grant_id", "requested_role", "private"):
            changed = deepcopy(row)
            changed["qualification_snapshot"][field] = "wrong"
            mutants.append(changed)
        for changed in mutants:
            with self.subTest(changed=changed), self.assertRaises(drill.ProbeFailure):
                verify(changed)
        for field in ("granted_at", "revoked_at"):
            changed = deepcopy(row)
            changed[field] = "2026-01-02T00:00:00+00:00"
            with self.subTest(field=field), self.assertRaises(drill.ProbeFailure):
                drill.verify_response(httpx.Response(200, json=changed), 200, row, exact_fields=row.keys())
        changed = deepcopy(row)
        changed["qualification_snapshot"]["captured_at"] = "2026-01-02T00:00:00+00:00"
        with self.assertRaises(drill.ProbeFailure):
            drill.verify_response(httpx.Response(200, json=changed), 200, row, exact_fields=row.keys())

    def test_candidate_page_rejects_private_fields_and_wrong_membership(self):
        row = {"actor_profile_id": "known", "display_name": "Candidate 名"}
        expected = {"known": {"display_name": "Candidate 名"}}
        def matches(rows):
            return drill.page_matches(rows, expected, set(), 100, "actor_profile_id",
                                      ("actor_profile_id", "display_name"))
        self.assertTrue(matches([row]))
        for mutant in ([row | {"contact_email": "private"}], [row | {"status": "active"}],
                       [row | {"display_name": None}], [row | {"actor_profile_id": "foreign"}],
                       [{"actor_profile_id": "known"}], [row, row]):
            with self.subTest(mutant=mutant):
                self.assertFalse(matches(mutant))
        # Existing callers may still intentionally assert only a known subset.
        self.assertTrue(drill.page_matches([row | {"status": "active"}], expected,
                                          set(), 100, "actor_profile_id"))

    def test_catalogue_oracle_rejects_nested_changes_and_duplicates(self):
        expected = drill.catalogue_expectations()
        self.assertEqual(len(drill.EXPECTED_PERMISSIONS), 73)
        self.assertEqual(len(set(drill.EXPECTED_PERMISSIONS)), 73)
        for name, body in expected.items():
            drill.verify_response(httpx.Response(200, json=body), 200, body, exact_fields=body.keys())
            variants = []
            duplicate = deepcopy(body)
            duplicate["items"].append(deepcopy(duplicate["items"][0]))
            variants.append(duplicate)
            missing = deepcopy(body)
            missing["items"].pop()
            variants.append(missing)
            extra = deepcopy(body)
            extra["items"][0]["unexpected"] = True
            variants.append(extra)
            changed = deepcopy(body)
            if name == "permissions":
                changed["items"][0]["permission_id"] = "unregistered.permission"
            else:
                changed["items"][0]["permission_ids"][0] = "unregistered.permission"
            variants.append(changed)
            for mutant in variants:
                with self.subTest(name=name, mutant=mutant), self.assertRaises(drill.ProbeFailure):
                    drill.verify_response(httpx.Response(200, json=mutant), 200, body, exact_fields=body.keys())
        expected["permissions"]["items"].clear()
        self.assertEqual(len(drill.catalogue_expectations()["permissions"]["items"]), 73)

    def test_validation_retryability_is_strict(self):
        expected = {"error.code": "invalid_request", "error.retryable": False}
        drill.verify_response(httpx.Response(422, json={"error": {
            "code": "invalid_request", "retryable": False}}), 422, expected)
        for retryable in (True, None, 0, "false"):
            with self.subTest(retryable=retryable), self.assertRaises(drill.ProbeFailure):
                drill.verify_response(httpx.Response(422, json={"error": {
                    "code": "invalid_request", "retryable": retryable}}), 422, expected)

    def test_openapi_discovery_has_stable_failure_codes(self):
        cases = (
            (httpx.Response(503, json={"paths": {}}), "openapi_document_unavailable"),
            (httpx.Response(200, text="not JSON"), "openapi_document_invalid"),
            (httpx.Response(200, json=[]), "openapi_document_invalid"),
            (httpx.Response(200, json={"openapi": "3.1.0"}), "openapi_document_invalid"),
            (httpx.Response(200, json={"openapi": "3.1.0", "paths": []}),
             "openapi_document_invalid"),
        )
        for response, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(drill.ProbeFailure, "^" + code + "$"):
                drill.openapi_document(response)
        document = {"openapi": "3.1.0", "paths": {}}
        self.assertEqual(drill.openapi_document(httpx.Response(200, json=document)), document)

    def test_startup_accepts_eventual_health_without_ignoring_failures(self):
        client = SimpleNamespace(get=AsyncMock(side_effect=[
            httpx.ConnectError("not listening"), httpx.Response(503), httpx.Response(200)]))
        process = Mock()
        process.poll.return_value = None
        with patch.object(drill.asyncio, "sleep", new_callable=AsyncMock):
            drill.asyncio.run(drill.wait_for_server(client, process))
        self.assertEqual(client.get.await_count, 3)
        self.assertEqual(process.poll.call_count, 3)

    def test_startup_deadline_and_exited_server_remain_failures(self):
        client = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200)))
        process = Mock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(drill.ProbeFailure, "^server_startup_failed$"):
            drill.asyncio.run(drill.wait_for_server(client, process))
        client.get.assert_not_awaited()
        process.poll.return_value = None
        with self.assertRaisesRegex(drill.ProbeFailure, "^server_startup_timeout$"):
            drill.asyncio.run(drill.wait_for_server(client, process, timeout_seconds=0))
        client.get.assert_not_awaited()

    def test_hanging_health_request_cannot_escape_deadline(self):
        async def hang(*args):
            await drill.asyncio.sleep(10)
        client = SimpleNamespace(get=AsyncMock(side_effect=hang))
        process = Mock()
        process.poll.return_value = None
        with self.assertRaisesRegex(drill.ProbeFailure, "^server_startup_timeout$"):
            drill.asyncio.run(drill.wait_for_server(client, process, timeout_seconds=0.01))
        client.get.assert_awaited_once()

    def test_cleanup_timeout_preserves_original_failure_and_rejects_success(self):
        for preserving_failure in (True, False):
            process = Mock()
            process.wait.side_effect = drill.subprocess.TimeoutExpired("server", 10)
            with self.subTest(preserving_failure=preserving_failure):
                if preserving_failure:
                    with self.assertRaisesRegex(drill.ProbeFailure, "^original_probe_failure$"):
                        try:
                            raise drill.ProbeFailure("original_probe_failure")
                        finally:
                            drill.stop_server(process, preserving_failure=True)
                else:
                    with self.assertRaisesRegex(drill.ProbeFailure, "^server_cleanup_timeout$"):
                        drill.stop_server(process, preserving_failure=False)
                process.terminate.assert_called_once_with()
                process.kill.assert_called_once_with()
                self.assertEqual(process.wait.call_count, 2)


    def test_collected_failure_keeps_cli_nonzero(self):
        async def failed_run(args, report):
            report["cases"].append({"result": "failed"})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            args = SimpleNamespace(report=output, isolation_metadata=Path(directory) / "db.json")
            with patch.object(drill.argparse.ArgumentParser, "parse_args", return_value=args), \
                 patch.object(drill, "run", failed_run):
                self.assertEqual(drill.main(), 1)
            self.assertEqual(json.loads(output.read_text())["result"], "failed")

    def test_nested_field_inventory_does_not_claim_execution(self):
        document = {"paths": {"/items": {"post": {
            "requestBody": {"content": {"application/json": {"schema": {
                "$ref": "#/components/schemas/Input"}}}}, "responses": {}}}},
            "components": {"schemas": {"Input": {"properties": {"rules": {
                "type": "array", "items": {"properties": {"enabled": {"type": "boolean"}}}
            }}}}}}
        item = drill.inventory(document)["POST /items"]
        self.assertIn("body.rules[].enabled", item["uncovered_fields"])
        self.assertEqual(item["status"], "untested")
        self.assertEqual(item["field_cases"], {})

    def test_wrong_body_status_and_boolean_coercion_fail(self):
        for body, status in (({"enabled": False}, 200), ({"enabled": True}, 500),
                             ({"enabled": 1}, 200), ({}, 200)):
            with self.subTest(body=body, status=status):
                with self.assertRaises(drill.ProbeFailure):
                    drill.verify_response(httpx.Response(status, json=body), 200, {"enabled": True})
        self.assertEqual(drill.verify_response(httpx.Response(200, json={"enabled": True}),
                                              200, {"enabled": True}), {"enabled": True})

    def test_nested_containers_do_not_coerce_boolean_integer_or_float(self):
        for actual, expected in (({"enabled": 1}, {"enabled": True}), ([1], [True]),
                                 ([{"values": [1.0]}], [{"values": [1]}]),
                                 ([1], [1, 2]), ({"a": 1, "b": 2}, {"a": 1})):
            with self.subTest(actual=actual, expected=expected), self.assertRaises(drill.ProbeFailure):
                drill.verify_response(httpx.Response(200, json={"nested": actual}),
                                      200, {"nested": expected})
        valid = {"nested": [{"enabled": True, "values": [1, None, "value"]}]}
        self.assertEqual(drill.verify_response(httpx.Response(200, json=valid), 200, valid), valid)

    def test_token_has_no_implicit_administrator(self):
        import base64
        issuer = drill.TokenIssuer()
        token = issuer.issue("contributor")
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        self.assertEqual(claims["roles"], [])
        self.assertEqual(claims["scope"], "workstream:access")
        self.assertEqual(claims["exp"] - claims["iat"], 600)
        self.assertNotIn(issuer.secret, token)

    def test_response_predicates_reject_missing_malformed_and_extra_fields(self):
        from uuid import uuid4
        valid = {"id": str(uuid4()), "created_at": "2026-01-01T00:00:00Z"}
        checks = {"id": drill.uuid_value, "created_at": drill.timestamp_value}
        for invalid in (valid | {"id": "not-uuid"}, valid | {"created_at": "yesterday"},
                        valid | {"created_at": "2026-01-01T00:00:00"},
                        valid | {"created_at": "9999-01-01T00:00:00Z"},
                        valid | {"secret": "should not appear"}, {"id": valid["id"]}):
            with self.subTest(invalid=invalid), self.assertRaises(drill.ProbeFailure):
                drill.verify_response(httpx.Response(200, json=invalid), 200, {}, checks, valid)
        self.assertEqual(drill.verify_response(httpx.Response(200, json=valid), 200, {},
                                              checks, valid), valid)


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_link_reason_failure_is_retained_and_readback_still_guards_continuation(self):
        mutation = "/api/v1/actor-identity-links/{identity_link_id}/revoke"
        actor_route = "/api/v1/actors/{actor_profile_id}"
        link = {"identity_link_id": "link", "status": "active"}
        for state_changed in (False, True):
            with self.subTest(state_changed=state_changed):
                posts = 0

                def handler(request):
                    nonlocal posts
                    if request.method == "POST":
                        posts += 1
                        status = 500 if posts == 1 else 422
                        body = {"error": {"code": "invalid_request", "retryable": False}}
                    else:
                        status, body = 200, link | ({"status": "revoked"} if state_changed else {})
                    return httpx.Response(status, json=body, headers={name: request.headers[name]
                        for name in ("X-Request-ID", "X-Correlation-ID")})

                async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                            base_url="http://127.0.0.1") as client:
                    report = {}
                    probe = drill.Drill(client, {"paths": {mutation: {"post": {}},
                        actor_route + "/identity-links": {"get": {}}}}, report)
                    operation = drill.identity_link_reason_cases(
                        probe, None, "revoke", mutation, "/api/v1/actor-identity-links/link/revoke",
                        actor_route, "/api/v1/actors/actor", link,
                    )
                    if state_changed:
                        with self.assertRaisesRegex(drill.ProbeFailure, "response_value_mismatch"):
                            await operation
                    else:
                        await operation
                    self.assertEqual(report["cases"][0]["result"], "failed")
                    self.assertEqual(report["cases"][1]["name"], "link_revoke_missing_unchanged")
                    self.assertEqual(posts, 1 if state_changed else 6)
                    self.assertEqual(len(report["cases"]), 2 if state_changed else 12)
                    self.assertEqual(report["cases"][-1]["result"], "failed" if state_changed else "success")

    async def test_binary_body_is_exact_and_cannot_be_combined_with_json(self):
        original = b"%PDF-1.7\n\x00\xff exact original bytes"
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.content, original)
            self.assertEqual(request.headers["Content-Type"], "application/pdf")
            self.assertTrue(request.headers["Idempotency-Key"])
            return httpx.Response(202, json={"stored": True}, headers={
                name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/upload": {"post": {}}}}, report)
            await probe.call("binary", "POST", "/upload", content=original,
                headers={"Content-Type": "application/pdf"}, expected=202, values={"stored": True})
            with self.assertRaisesRegex(drill.ProbeFailure, "ambiguous_request_body"):
                await probe.call("ambiguous", "POST", "/upload", content=original, payload={"bad": True})
            self.assertEqual(len(requests), 1)
            self.assertEqual(report["cases"][-1]["result"], "failed")

    async def test_health_requires_exact_public_body(self):
        for body in ({"status": "ok"}, {"status": "down"}, {},
                     {"status": "ok", "secret": "unexpected"}):
            def handler(request):
                self.assertNotIn("authorization", request.headers)
                return httpx.Response(200, json=body, headers={
                    key: request.headers[key] for key in ("X-Request-ID", "X-Correlation-ID")})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                         base_url="http://127.0.0.1") as client:
                report = {}
                probe = drill.Drill(client, {"paths": {"/api/v1/health": {"get": {}}}}, report)
                if body == {"status": "ok"}:
                    await drill.health_cases(probe)
                    self.assertIn("response.200.status",
                                  report["operations"]["GET /api/v1/health"]["field_cases"])
                else:
                    with self.assertRaises(drill.ProbeFailure):
                        await drill.health_cases(probe)
                    self.assertEqual(report["cases"][0]["result"], "failed")

    async def test_profile_readback_rejects_cross_field_and_time_regressions(self):
        from uuid import uuid4
        expected = {"actor_profile_id": str(uuid4()), "actor_kind": "human", "status": "active",
                    "domains": ["contributor"], "admin_roles": [], "project_role_grants": [],
                    "display_name": None, "contact_email": "unchanged",
                    "created_at": "2026-01-01T00:00:00Z"}
        previous = expected | {"updated_at": "2026-01-01T00:00:01Z",
                               "last_seen_at": "2026-01-01T00:00:01Z"}
        good = previous | {"updated_at": "2026-01-01T00:00:02Z",
                           "last_seen_at": "2026-01-01T00:00:02Z"}
        for change in ({}, {"contact_email": "silently changed"},
                       {"admin_roles": ["access_administrator"]}, {"status": "suspended"},
                       {"actor_profile_id": str(uuid4())}, {"unexpected": True},
                       {"updated_at": "2026-01-01T00:00:00Z"}, {"last_seen_at": None}):
            def handler(request):
                return httpx.Response(200, json=good | change, headers={
                    key: request.headers[key] for key in ("X-Request-ID", "X-Correlation-ID")})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                         base_url="http://127.0.0.1") as client:
                report = {}
                probe = drill.Drill(client, {"paths": {"/api/v1/actors/me": {"get": {}}}}, report)
                call = drill.profile_readback(probe, "test-token", "readback", expected, previous)
                if not change:
                    self.assertEqual(await call, good)
                else:
                    with self.assertRaises(drill.ProbeFailure):
                        await call
                    self.assertEqual(report["operations"]["GET /api/v1/actors/me"]["field_cases"], {})

    async def test_policy_successor_rejects_changed_generation_or_semantics(self):
        """A denied-write mutation or wrong replacement cannot become field proof."""
        from uuid import uuid4
        previous = {"id": str(uuid4()), "project_id": str(uuid4()), "guide_version": "draft",
                    "policy_generation": 2, "policy_hash": "sha256:" + "a" * 64,
                    "supersedes_policy_id": None, "semantics_status": "complete",
                    "human_review_required": False, "created_at": "2026-01-01T00:00:00Z"}
        good = previous | {"id": str(uuid4()), "policy_generation": 3,
                           "policy_hash": "sha256:" + "b" * 64,
                           "supersedes_policy_id": previous["id"]}
        for change in ({}, {"policy_generation": 4}, {"human_review_required": True},
                       {"supersedes_policy_id": str(uuid4())}, {"id": previous["id"]},
                       {"policy_hash": previous["policy_hash"]}):
            def handler(request):
                self.assertEqual(request.headers["If-Match"], drill.policy_selector(previous))
                return httpx.Response(200, json=good | change, headers={
                    key: request.headers[key] for key in ("X-Request-ID", "X-Correlation-ID")})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                         base_url="http://127.0.0.1") as client:
                report = {}
                probe = drill.Drill(client, {"paths": {"/policy": {"put": {}}}}, report)
                async def run_case():
                    return await drill.policy_successor(probe, "manager", "/policy", "/policy",
                        "successor", {}, {"human_review_required": False}, previous, hash_changed=True)
                if change:
                    with self.assertRaises(drill.ProbeFailure):
                        await run_case()
                    self.assertEqual(report["operations"]["PUT /policy"]["field_cases"], {})
                    self.assertEqual(report["cases"][0]["result"], "failed")
                else:
                    self.assertEqual(await run_case(), good)
        for returned_hash in (previous["policy_hash"], "sha256:" + "b" * 64):
            def handler(request):
                return httpx.Response(200, json=good | {"policy_hash": returned_hash}, headers={
                    key: request.headers[key] for key in ("X-Request-ID", "X-Correlation-ID")})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                         base_url="http://127.0.0.1") as client:
                probe = drill.Drill(client, {"paths": {"/policy": {"put": {}}}}, {})
                call = drill.policy_successor(probe, "manager", "/policy", "/policy", "same_semantics",
                    {}, {"human_review_required": False}, previous, hash_changed=False)
                if returned_hash == previous["policy_hash"]:
                    self.assertEqual((await call)["policy_hash"], returned_hash)
                else:
                    with self.assertRaises(drill.ProbeFailure):
                        await call

    async def test_actual_response_assertions_are_mapped_and_header_can_be_omitted(self):
        def handler(request):
            self.assertNotIn("Idempotency-Key", request.headers)
            return httpx.Response(200, json={"enabled": True}, headers={
                name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/items": {"post": {}}}}, report)
            await probe.call("assert_enabled", "POST", "/items", payload={},
                             headers={"Idempotency-Key": None}, values={"enabled": True})
            self.assertEqual(report["operations"]["POST /items"]["field_cases"],
                             {"response.200.enabled": ["assert_enabled"],
                              "header.X-Request-ID": ["assert_enabled"],
                              "header.X-Correlation-ID": ["assert_enabled"]})
            with self.assertRaisesRegex(drill.ProbeFailure, "duplicate_case_name"):
                await probe.call("assert_enabled", "POST", "/items", payload={})

    async def test_denial_does_not_mark_operation_working(self):
        def handler(request):
            return httpx.Response(403, json={"error": {"code": "denied"}}, headers={
                name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/items": {"get": {}}}}, report)
            await probe.call("deny", "GET", "/items", expected=403,
                             values={"error.code": "denied"})
            self.assertEqual(report["operations"]["GET /items"]["status"], "denial_only")
            with self.assertRaises(drill.ProbeFailure):
                await probe.call("false_success", "GET", "/items", expected=200)
            self.assertEqual(report["cases"][-1]["result"], "failed")
            await probe.call("later_valid_denial", "GET", "/items", expected=403)
            self.assertEqual(report["operations"]["GET /items"]["status"], "failed")

    async def test_field_evidence_separates_annotations_shape_predicates_and_values(self):
        def handler(request):
            return httpx.Response(200, json={"items": [{"enabled": True}], "empty": [], "count": 1},
                headers={name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/items": {"get": {}}}}, report)
            await probe.call("proof", "GET", "/items", values={"items": [{"enabled": True}], "empty": []},
                checks={"count": lambda value: type(value) is int}, exact_fields=("items", "empty", "count"),
                fields=("body.unchecked",))
            operation = report["operations"]["GET /items"]
            self.assertIn("response.200.items[].enabled", operation["field_cases"])
            self.assertIn("response.200.empty", operation["field_cases"])
            for field in ("response.200.empty[]", "body.unchecked", "response.200.count"):
                self.assertNotIn(field, operation["field_cases"])
            self.assertEqual(operation["request_cases"], {"body.unchecked": ["proof"]})
            self.assertEqual(operation["predicate_cases"], {"response.200.count": ["proof"]})
            self.assertIn("response.200.count", operation["shape_cases"])
            with self.assertRaises(drill.ProbeFailure):
                await probe.call("defective", "GET", "/items", values={"items": [{"enabled": False}]})
            self.assertEqual(report["cases"][-1]["asserted_fields"], [])
            self.assertEqual(operation["field_cases"]["response.200.items[].enabled"], ["proof"])
            with self.assertRaisesRegex(drill.ProbeFailure, "invalid_request_field_annotation"):
                await probe.call("misindexed", "GET", "/items", fields=("response.200.count",))
            self.assertNotIn("response.200.count", operation["request_cases"])
            self.assertEqual(report["cases"][-1]["asserted_fields"], [])

    async def test_qualification_denial_detects_a_forbidden_revoked_history_row(self):
        await self._assert_forbidden_qualification_history(422)

    async def test_failed_valid_boundary_detects_a_forbidden_revoked_history_row(self):
        await self._assert_forbidden_qualification_history(500)

    async def _assert_forbidden_qualification_history(self, mutation_status):
        mutated = False
        route = "/api/v1/projects/{project_id}/role-grants"
        def handler(request):
            nonlocal mutated
            status = 200
            if request.url.path == "/api/v1/actors/me":
                body = {"actor_profile_id": "target"}
            elif request.method == "POST":
                mutated = True
                status, body = mutation_status, {"error": {"code": "probe_error"}}
            else:
                body = {"items": [{"id": "rogue", "status": "revoked"}]
                        if mutated and request.url.params.get("status") != "active" else [],
                        "next_cursor": None}
            return httpx.Response(status, json=body, headers={name: request.headers[name]
                for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/api/v1/actors/me": {"get": {}},
                                                route: {"get": {}, "post": {}}}}, report)
            with self.assertRaisesRegex(drill.ProbeFailure, "response_value_mismatch"):
                if mutation_status == 500:
                    with patch.object(drill, "qualification_invalids", return_value=()):
                        await drill.project_role_cases(probe, None, None, {"id": "project"}, "manager", "manager-grant")
                else:
                    await drill.project_role_cases(probe, None, None, {"id": "project"}, "manager", "manager-grant")
            self.assertEqual(report["cases"][-1]["name"], "qualification_failed_state_submitter"
                             if mutation_status == 500 else "qualification_unchanged_missing_skills_snapshot")
            self.assertEqual(report["cases"][-1]["result"], "failed")

    async def test_pagination_detects_missing_duplicate_foreign_and_nonterminating_pages(self):
        good = [{"items": [{"id": "a", "role": "submitter"}], "next_cursor": "next"},
                {"items": [{"id": "b", "role": "reviewer"}], "next_cursor": None}]
        variants = {
            "valid": good,
            "missing": [good[0] | {"next_cursor": None}],
            "duplicate": [good[0], good[1] | {"items": good[0]["items"]}],
            "foreign": [good[0] | {"items": [{"id": "foreign", "role": "submitter"}]}],
            "wrong_role": [good[0] | {"items": [{"id": "a", "role": "reviewer"}]}],
            "empty_continuation": [good[0] | {"items": []}],
            "repeat_cursor": [good[0], good[1] | {"next_cursor": "next"}],
            "extra_continuation": [good[0], good[1] | {"next_cursor": "third"}],
        }
        for label, bodies in variants.items():
            responses = iter(bodies)
            requests = []
            def handler(request):
                requests.append(request)
                return httpx.Response(200, json=next(responses), headers={
                    name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1") as client:
                report = {}
                probe = drill.Drill(client, {"paths": {"/items": {"get": {}}}}, report)
                async def run():
                    return await drill.page_cases(probe, "pages", "/items", "/items", None,
                        {"a": {"role": "submitter"}, "b": {"role": "reviewer"}}, identity="id")
                with self.subTest(label=label):
                    if label == "valid":
                        self.assertEqual(await run(), "next")
                        self.assertEqual(requests[1].url.params["cursor"], "next")
                    else:
                        with self.assertRaises(drill.ProbeFailure):
                            await run()
                        self.assertEqual(report["operations"]["GET /items"]["status"], "failed")
                        self.assertEqual(report["cases"][-1]["asserted_fields"], [])

    def test_qualification_mutations_are_independent_and_include_boundaries(self):
        valid = {"skills_snapshot": {"availability": "available", "reference_ids": ["skill:1"], "unavailable_reason": None},
                 "reputation_snapshot": {"availability": "available", "reference_ids": ["rep:1"], "unavailable_reason": None},
                 "prior_project_work_refs": [], "external_expertise_refs": []}
        original = json.loads(json.dumps(valid))
        cases = dict(drill.qualification_invalids(valid))
        self.assertEqual(valid, original)
        self.assertEqual(len(cases["skills_snapshot_too_many"]["skills_snapshot"]["reference_ids"]), 21)
        self.assertEqual(len(cases["external_too_long"]["external_expertise_refs"][0]), 121)
        self.assertNotIn("unavailable_reason", cases["missing_reputation_snapshot_unavailable_reason"]["reputation_snapshot"])

    async def test_success_cannot_erase_prior_failure(self):
        def handler(request):
            return httpx.Response(200, json={"enabled": False}, headers={
                name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/items": {"get": {}}}}, report)
            with self.assertRaises(drill.ProbeFailure):
                await probe.call("bad_body", "GET", "/items", values={"enabled": True})
            await probe.call("later_success", "GET", "/items", values={"enabled": False})
            self.assertEqual(report["operations"]["GET /items"]["status"], "failed")

    async def test_external_database_rejected_before_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text("{}")
            with patch.dict("os.environ", {"WORKSTREAM_DATABASE_URL":
                 "postgresql+asyncpg://test:secret@remote.invalid/production"}), \
                 patch.object(drill.asyncpg, "connect") as connect:
                with self.assertRaises(drill.ProbeFailure):
                    await drill.isolation(path)
                connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
