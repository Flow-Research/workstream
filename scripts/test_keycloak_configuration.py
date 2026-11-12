"""Pure desired-state checks; provider/browser correctness needs real integration."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "deploy/identity/realm_config.py"
spec = importlib.util.spec_from_file_location("identity_realm_config", PATH)
assert spec is not None and spec.loader is not None
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class KeycloakConfigurationTests(unittest.TestCase):
    def test_human_credentials_require_browser_pkce(self):
        clients = {c["clientId"]: c for c in config.realm()["clients"]}
        for client in clients.values():
            self.assertFalse(client["directAccessGrantsEnabled"])
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
