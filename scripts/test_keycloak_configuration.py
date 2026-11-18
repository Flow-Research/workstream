"""Pure desired-state checks; provider/browser correctness needs real integration."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from scripts import check_stale_artifact_contracts as artifact_scan

PATH = Path(__file__).resolve().parents[1] / "deploy/identity/realm_config.py"
spec = importlib.util.spec_from_file_location("identity_realm_config", PATH)
assert spec is not None and spec.loader is not None
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class KeycloakConfigurationTests(unittest.TestCase):
    def test_theme_images_do_not_bypass_runtime_text_scan(self):
        assets = PATH.parent / "themes/flow/login/resources/img"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = []
            for name in ("flow-logo.png", "favicon.ico"):
                target = root / name
                target.write_bytes((assets / name).read_bytes())
                files.append(target)
            with patch.object(artifact_scan, "discover_paths", return_value=files):
                self.assertEqual(artifact_scan.scan(root), [])
            for name, data in (("runtime.py", files[0].read_bytes()), ("corrupt.png", b"\xffinvalid")):
                target = root / name
                target.write_bytes(data)
                with patch.object(artifact_scan, "discover_paths", return_value=[target]):
                    self.assertEqual(artifact_scan.scan(root),
                        [f"{name}:0: UNREADABLE_ACTIVE_TEXT (UnicodeDecodeError)"])

    def test_account_console_is_account_only_and_preserves_builtin_boundaries(self):
        existing = {"clientId": "account-console", "publicClient": True,
                    "standardFlowEnabled": True, "fullScopeAllowed": False,
                    "directAccessGrantsEnabled": False,
                    "attributes": {"pkce.code.challenge.method": "S256"},
                    "redirectUris": ["/realms/flow/account/*"]}
        result = config.account_console_settings(existing)
        self.assertEqual(set(result), {"protocolMappers"})
        audience, roles = result["protocolMappers"]
        self.assertEqual(audience["config"]["included.client.audience"], "account")
        self.assertEqual(roles["config"]["usermodel.clientRoleMapping.clientId"], "account")
        self.assertEqual(roles["config"]["claim.name"], "resource_access.account.roles")
        self.assertNotIn("account-console", [c["clientId"] for c in config.realm()["clients"]])
        for change in ({"clientId": "workstream-mcp"}, {"fullScopeAllowed": True},
                       {"directAccessGrantsEnabled": True}, {"redirectUris": ["*"]},
                       {"attributes": {"pkce.code.challenge.method": "plain"}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                config.account_console_settings({**existing, **change})

    def test_self_service_activation_requires_provider_and_secure_email(self):
        existing = {"realm": "flow", "eventsListeners": ["jboss-logging"],
                    "smtpServer": {"host": "smtp.example.test", "from": "identity@example.test", "starttls": "true"}}
        server = {"providers": {"eventsListener": {"providers": {"flow-human-registration": {}}}}}
        profile = {"attributes": [{"name": "workstream_subject_kind", "permissions": {"view": ["admin"], "edit": ["admin"]}}]}
        patch = config.self_service_settings(existing, server, profile)
        self.assertTrue(patch["registrationAllowed"])
        self.assertTrue(patch["verifyEmail"])
        self.assertTrue(patch["resetPasswordAllowed"])
        self.assertTrue(patch["registrationEmailAsUsername"])
        self.assertFalse(patch["duplicateEmailsAllowed"])
        self.assertEqual(patch["eventsListeners"], ["jboss-logging", "flow-human-registration"])
        self.assertNotIn("smtpServer", patch)
        self.assertEqual(existing["eventsListeners"], ["jboss-logging"])
        for realm, info in ((existing, {}), ({**existing, "realm": "master"}, server),
                            ({**existing, "smtpServer": {}}, server),
                            ({**existing, "smtpServer": {**existing["smtpServer"], "starttls": "false"}}, server)):
            with self.subTest(realm=realm.get("realm")), self.assertRaises(ValueError):
                config.self_service_settings(realm, info, profile)

    def test_signup_activation_rejects_user_editable_or_missing_marker(self):
        realm = {"realm": "flow", "smtpServer": {"host": "smtp.example.test", "from": "identity@example.test", "ssl": "true"}}
        server = {"providers": {"eventsListener": {"providers": {"flow-human-registration": {}}}}}
        for profile in ({"attributes": []}, {"attributes": [{"name": "workstream_subject_kind",
                           "permissions": {"view": ["admin"], "edit": ["admin", "user"]}}]}):
            with self.assertRaises(ValueError):
                config.self_service_settings(realm, server, profile)

    def test_fresh_realm_has_branding_and_listener_but_signup_stays_closed(self):
        realm = config.realm()
        self.assertEqual(realm["loginTheme"], "flow")
        self.assertEqual(realm["emailTheme"], "flow")
        self.assertIn("flow-human-registration", realm["eventsListeners"])
        self.assertFalse(realm["registrationAllowed"])

    def test_password_grant_is_confined_to_direct_api_client(self):
        clients = {c["clientId"]: c for c in config.realm()["clients"]}
        for client in clients.values():
            self.assertEqual(client["directAccessGrantsEnabled"], client["clientId"] == "workstream-api-login")
            self.assertFalse(client["serviceAccountsEnabled"])
            self.assertFalse(client["implicitFlowEnabled"])
            self.assertFalse(client["fullScopeAllowed"])
            self.assertNotIn("secret", client)
        for name in ("workstream-cli-login", "workstream-mcp-proof"):
            client = clients[name]
            self.assertTrue(client["standardFlowEnabled"])
            self.assertTrue(client["publicClient"])
            self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
            self.assertEqual(len(client["redirectUris"]), 1)
            self.assertNotIn("*", client["redirectUris"][0])

    def test_direct_api_client_has_no_mcp_or_machine_authority(self):
        client = config.direct_api_client()
        self.assertTrue(client["publicClient"])
        self.assertTrue(client["directAccessGrantsEnabled"])
        self.assertFalse(client["consentRequired"])
        self.assertFalse(client["standardFlowEnabled"])
        self.assertEqual(client["redirectUris"], [])
        self.assertEqual(client["webOrigins"], [])
        self.assertEqual(client["optionalClientScopes"], ["workstream:access", "workstream-api-audience"])
        self.assertEqual(client["attributes"]["standard.token.exchange.enabled"], "false")
        self.assertEqual(client["attributes"]["access.token.lifespan"], "300")
        self.assertTrue(config.realm()["bruteForceProtected"])

    def test_swagger_has_exact_callback_origin_and_api_scope_only(self):
        client = config.swagger_client("https://api.example.test")
        self.assertEqual(client["redirectUris"], ["https://api.example.test/docs/oauth2-redirect"])
        self.assertEqual(client["webOrigins"], ["https://api.example.test"])
        self.assertEqual(client["optionalClientScopes"], ["workstream:access", "workstream-api-audience"])
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertTrue(client["publicClient"])
        self.assertFalse(client["directAccessGrantsEnabled"])
        for origin in ("http://api.example.test", "https://user@api.example.test", "https://api.example.test/other", "https://api.example.test?x=1"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                config.swagger_client(origin)

    def test_exchange_cannot_issue_refresh_or_extend_source(self):
        exchange = next(c for c in config.realm()["clients"] if c["clientId"] == "workstream-mcp")
        self.assertFalse(exchange["publicClient"])
        self.assertFalse(exchange["standardFlowEnabled"])
        self.assertEqual(exchange["optionalClientScopes"], [])
        self.assertIn("workstream-api-audience", exchange["defaultClientScopes"])
        self.assertNotIn("workstream-mcp-audience", exchange["defaultClientScopes"])
        attributes = exchange["attributes"]
        self.assertEqual(attributes["access.token.lifespan"], "120")
        self.assertEqual(attributes["standard.token.exchange.enableRefreshRequestedTokenType"], "NO")
        self.assertEqual(attributes["standard.token.exchange.allowTokenExpirationAfterSubjectTokenExpiration"], "false")
        profile, policy = config.exchange_policy()
        executors = {e["executor"]: e["configuration"] for e in profile["profiles"][0]["executors"]}
        self.assertIn("downscope-assertion-grant-enforcer", executors)
        self.assertEqual(executors["jwt-claim-enforcer"], {"claim-name": "subject_kind", "allowed-value": "^human$"})
        condition = policy["policies"][0]["conditions"][0]
        self.assertEqual(json.loads(condition["configuration"]["attributes"]), [{"key": config.EXCHANGE_MARKER, "value": "human-only"}])

    def test_marker_is_not_user_editable_and_email_is_required(self):
        original = {"attributes": [
            {"name": "email", "validations": {"email": {}}, "permissions": {"view": ["admin", "user"]}},
            {"name": "firstName", "permissions": {"edit": ["admin", "user"]}},
        ], "groups": [{"name": "existing"}]}
        result = config.human_profile(original)
        self.assertEqual(result["groups"], original["groups"])
        self.assertEqual(result["attributes"][1], original["attributes"][1])
        marker = result["attributes"][-1]
        self.assertEqual(marker["permissions"], {"view": ["admin"], "edit": ["admin"]})
        self.assertNotIn("defaultValue", marker)
        self.assertEqual(result["attributes"][0]["required"], {"roles": ["user", "admin"]})
        self.assertNotIn("unmanagedAttributePolicy", result)
        self.assertEqual(len(original["attributes"]), 2)
        self.assertEqual(config.human_profile(result), result)

    def test_profile_claims_are_on_access_tokens_without_hardcoded_human(self):
        scope = next(s for s in config.realm()["clientScopes"] if s["name"] == "workstream-identity")
        self.assertEqual(scope["attributes"]["include.in.token.scope"], "false")
        mappers = {m["name"]: m for m in scope["protocolMappers"]}
        self.assertEqual(mappers["account-email"]["config"]["user.attribute"], "email")
        self.assertEqual(mappers["account-email"]["config"]["claim.name"], "email")
        self.assertEqual(mappers["subject-kind"]["protocolMapper"], "oidc-usermodel-attribute-mapper")
        for mapper in mappers.values():
            self.assertEqual(mapper["config"]["access.token.claim"], "true")
            self.assertEqual(mapper["config"]["id.token.claim"], "false")

    def test_garden_never_receives_api_audience_scope(self):
        client = config.garden_client("garden-workstream", "https://garden.example/api/oauth/callback")
        self.assertEqual(client["optionalClientScopes"], ["workstream:access", "workstream-mcp-audience"])
        self.assertFalse(client["serviceAccountsEnabled"])
        for callback in ("http://garden.example/api/oauth/callback", "https://garden.example/*", "https://garden.example/api/oauth/callback?redirect=evil", "https://user:password@garden.example/api/oauth/callback"):
            with self.subTest(callback=callback), self.assertRaises(ValueError):
                config.garden_client("garden-workstream", callback)

    def test_realm_contains_no_retained_accounts_or_credentials(self):
        realm = config.realm()
        self.assertNotIn("users", realm)
        self.assertFalse(realm["registrationAllowed"])
        self.assertFalse(realm["resetPasswordAllowed"])
        self.assertFalse(realm["verifyEmail"])
        self.assertTrue(realm["revokeRefreshToken"])
        self.assertEqual(realm["refreshTokenMaxReuse"], 0)

    def test_consent_shows_access_once_without_losing_mcp_refresh_scope(self):
        scopes = {scope["name"]: scope for scope in config.realm()["clientScopes"]}
        client = config.garden_client("garden-dev", "https://garden.example/api/oauth/callback")
        requested = [scopes[name] for name in client["optionalClientScopes"]]
        self.assertEqual(
            [scope["name"] for scope in requested
             if scope["attributes"]["display.on.consent.screen"] == "true"],
            ["workstream:access"],
        )
        self.assertEqual(
            [scope["name"] for scope in requested
             if scope["attributes"]["include.in.token.scope"] == "true"],
            ["workstream:access", "workstream-mcp-audience"],
        )

    def test_import_defines_every_assigned_scope_including_subject(self):
        realm = config.realm()
        scopes = {scope["name"]: scope for scope in realm["clientScopes"]}
        for client in realm["clients"]:
            for name in client["defaultClientScopes"] + client["optionalClientScopes"]:
                self.assertIn(name, scopes)
        self.assertTrue(any(mapper["protocolMapper"] == "oidc-sub-mapper"
                            for mapper in scopes["basic"]["protocolMappers"]))


if __name__ == "__main__":
    unittest.main()
