"""Owned Keycloak/PostgreSQL HTTPS integration proof (not Garden/browser UI).

Build deploy/identity/Dockerfile as workstream-keycloak:test first. Run using the
backend environment with PYTHONPATH=.:backend:mcp_server. All accounts, secrets,
containers and networks are fixture-owned and removed, including on failure.
"""
from __future__ import annotations

import asyncio
from functools import partial
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from urllib.error import URLError
from uuid import uuid4

import httpx
import jwt

from app.adapters.auth.flow import FlowAuthVerifier
from app.core.config import Settings
from app.interfaces.auth import AuthVerificationError
from deploy.identity import realm_config
from scripts.identity_protocol_probe import IdentityProtocolProbe, ProviderRejected, LoginRejected
from workstream_mcp.adapters.keycloak import KeycloakCredentials
from workstream_mcp.oauth import InvalidCredential, OAuthSettings

ROOT = Path(__file__).resolve().parents[1]
POSTGRES = "postgres@sha256:5264710be20f409750ac6dc4e5706dcef929c87e241605463f0f9aefa932a8d9"
SPEC = importlib.util.spec_from_file_location(
    "identity_database_initializer", ROOT / "deploy/hosted/initialize-local-data.py",
)
assert SPEC and SPEC.loader
initializer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(initializer)


class IdentityProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="workstream-keycloak-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.name = "workstream-keycloak-" + uuid4().hex[:12]
        cls.pg = cls.name + "-pg"
        cls.identity = cls.name + "-id"
        cls.bootstrap = cls.name + "-bootstrap"
        cls.docker("network", "create", cls.name)
        cls.addClassCleanup(cls.docker, "network", "rm", cls.name)
        cls.addClassCleanup(cls.cleanup_containers)
        cls.admin_password = secrets.token_urlsafe(24)
        cls.identity_password = secrets.token_hex(32)
        cls.workstream_password = secrets.token_hex(32)
        cls.private("postgres-password", secrets.token_hex(32))
        cls.private("identity-password", cls.identity_password)
        cls.private("bootstrap-password", cls.admin_password)
        cls.private("init.sql", initializer.postgres_initialization_sql(
            cls.workstream_password, cls.identity_password,
        ))
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout", str(cls.root / "key.pem"), "-out", str(cls.root / "cert.pem"),
        ], check=True, capture_output=True, timeout=30)
        (cls.root / "key.pem").chmod(0o444)
        cls.context = ssl.create_default_context(cafile=str(cls.root / "cert.pem"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.origin = f"https://localhost:{port}"
        cls.probe = IdentityProtocolProbe(cls.origin, cls.context)
        cls.docker(
            "run", "-d", "--name", cls.pg, "--network", cls.name,
            "--network-alias", "postgres", "--memory", "512m", "--cpus", "1",
            "--pids-limit", "128", *cls.mount("postgres-password", "/run/password"),
            *cls.mount("init.sql", "/docker-entrypoint-initdb.d/init.sql"),
            "-e", "POSTGRES_PASSWORD_FILE=/run/password", "-e", "POSTGRES_DB=workstream",
            POSTGRES,
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            result = subprocess.run(["docker", "exec", cls.pg, "pg_isready", "-h", "127.0.0.1"],
                                    capture_output=True, timeout=10)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("fixture PostgreSQL failed to become ready")
        runtime = [
            "--network", cls.name,
            "--user", "1000:1000", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--memory", "1536m",
            "--memory-swap", "1536m", "--cpus", "1", "--pids-limit", "256",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=128m,mode=0700,uid=1000,gid=1000",
            "--tmpfs", "/opt/keycloak/data:rw,noexec,nosuid,nodev,size=128m,mode=0700,uid=1000,gid=1000",
            *cls.mount("identity-password", "/run/db-password"),
            *cls.mount("cert.pem", "/run/cert.pem"), *cls.mount("key.pem", "/run/key.pem"),
            "-e", "KC_DB=postgres", "-e", "KC_DB_URL=jdbc:postgresql://postgres:5432/flow_identity",
            "-e", "KC_DB_USERNAME=flow_identity", "-e", "KC_DB_PASSWORD_FILE=/run/db-password",
            "-e", "KC_DB_POOL_INITIAL_SIZE=1", "-e", "KC_DB_POOL_MIN_SIZE=1",
            "-e", "KC_DB_POOL_MAX_SIZE=10", "-e", f"KC_HOSTNAME={cls.origin}",
            "-e", "KC_HOSTNAME_STRICT=true", "-e", "KC_HOSTNAME_BACKCHANNEL_DYNAMIC=false",
            "-e", "KC_HTTPS_CERTIFICATE_FILE=/run/cert.pem", "-e", "KC_HTTPS_CERTIFICATE_KEY_FILE=/run/key.pem",
            "-e", "KC_CACHE=local",
            "-e", "JAVA_OPTS_KC_HEAP=-XX:MaxRAMPercentage=60 -XX:InitialRAMPercentage=30",
        ]
        image = os.environ.get("WORKSTREAM_TEST_IDENTITY_IMAGE", "workstream-keycloak:test")
        cls.docker(
            "run", "--rm", "--name", cls.bootstrap, *runtime,
            *cls.mount("bootstrap-password", "/run/bootstrap-password"),
            "-e", "KC_BOOTSTRAP_ADMIN_PASSWORD_FILE=/run/bootstrap-password", image,
            "bootstrap-admin", "user", "--optimized", "--username", "fixture-operator",
            "--password:env", "KC_BOOTSTRAP_ADMIN_PASSWORD", "--no-prompt", timeout=390,
        )
        cls.docker(
            "run", "-d", "--name", cls.identity, *runtime,
            "-p", f"127.0.0.1:{port}:8443", image,
        )
        cls.wait_ready()
        cls.operator = cls.probe.request("/realms/master/protocol/openid-connect/token", {
            "grant_type": "password", "client_id": "admin-cli", "username": "fixture-operator",
            "password": cls.admin_password,
        }, form=True)["access_token"]
        cls.probe.request("/admin/realms", realm_config.realm(), token=cls.operator)
        profile = cls.probe.request("/admin/realms/flow/users/profile", token=cls.operator)
        cls.probe.request("/admin/realms/flow/users/profile", realm_config.human_profile(profile),
                          token=cls.operator, method="PUT")

    @classmethod
    def docker(cls, *args, timeout=120):
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            # No command, provider log or response body enters a failure report.
            raise RuntimeError(f"fixture Docker operation {args[0]} failed")
        return result.stdout.strip()

    @classmethod
    def cleanup_containers(cls):
        for name in (cls.bootstrap, cls.identity, cls.pg):
            exists = subprocess.run(["docker", "container", "inspect", name],
                                    capture_output=True, timeout=15)
            if exists.returncode == 0:
                cls.docker("rm", "-fv", name)

    @classmethod
    def private(cls, name, value):
        # Container-readable exact bind; the containing host directory is 0700.
        path = cls.root / name
        path.write_text(value + "\n")
        path.chmod(0o444)

    @classmethod
    def mount(cls, name, target):
        return ["--mount", f"type=bind,source={cls.root / name},target={target},readonly"]

    @classmethod
    def wait_ready(cls):
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            try:
                cls.probe.request("/realms/master/.well-known/openid-configuration")
                return
            except (URLError, ProviderRejected, TimeoutError):
                time.sleep(2)
        raise RuntimeError("fixture Keycloak failed to become ready within 360 seconds")

    def setUp(self):
        self.operator = self.probe.request("/realms/master/protocol/openid-connect/token", {
            "grant_type": "password", "client_id": "admin-cli", "username": "fixture-operator",
            "password": self.admin_password,
        }, form=True)["access_token"]

    def test_provider_denies_marker_tampering_exchange_widening_and_closed_sessions(self):
        password = secrets.token_urlsafe(24)
        email = "negative-participant@example.invalid"
        self.probe.request("/admin/realms/flow/users", {
            "username": "negative-participant", "email": email, "enabled": True,
            "firstName": "Negative", "lastName": "Participant",
            "requiredActions": ["UPDATE_PROFILE"],
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        }, token=self.operator)
        users = self.probe.request("/admin/realms/flow/users?username=negative-participant&exact=true",
                                   token=self.operator)
        self.assertEqual(len(users), 1)
        user_path = "/admin/realms/flow/users/" + users[0]["id"]
        # Reach the actual participant profile form, then attempt both ordinary
        # and attribute-prefixed submissions of the admin-only marker.
        unmarked = self.probe.login("workstream-mcp-proof", "workstream-mcp-audience", email,
            password, profile_changes={"firstName": "Edited", "lastName": "Participant",
                "email": email, "workstream_subject_kind": "human",
                "user.attributes.workstream_subject_kind": "human"})
        stored = self.probe.request(user_path, token=self.operator)
        self.assertEqual(stored["firstName"], "Edited")
        self.assertFalse(stored.get("attributes", {}).get("workstream_subject_kind"))
        clients = self.probe.request("/admin/realms/flow/clients", token=self.operator)
        client = next(c for c in clients if c["clientId"] == "workstream-mcp")
        secret = self.probe.request(f"/admin/realms/flow/clients/{client['id']}/client-secret",
                                    token=self.operator)["value"]
        keys = self.probe.request("/realms/flow/protocol/openid-connect/certs")["keys"]

        def claims(token, audience):
            key = next(k for k in keys if k["kid"] == jwt.get_unverified_header(token)["kid"])
            return jwt.decode(token, jwt.PyJWK.from_dict(key).key, algorithms=["RS256"],
                              audience=audience, issuer=self.origin + "/realms/flow")

        self.assertNotIn("subject_kind", claims(unmarked["access_token"], realm_config.MCP_RESOURCE))

        def exchange(source, **overrides):
            data = {"grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "subject_token": source, "audience": "workstream-api",
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "scope": "workstream:access", **overrides}
            with httpx.Client(verify=self.context, trust_env=False, timeout=15) as http:
                response = http.post(self.origin + "/realms/flow/protocol/openid-connect/token",
                                     data=data, auth=("workstream-mcp", secret))
            body = response.json()
            return response.status_code, body

        def denied(status, body):
            self.assertIn(status, (400, 401, 403))
            self.assertFalse(any(name in body for name in ("access_token", "refresh_token", "id_token")),
                             "denied provider operation returned credentials")

        denied(*exchange(unmarked["access_token"]))
        def update_user(changes):
            current = self.probe.request(user_path, token=self.operator)
            current.update(changes)
            self.probe.request(user_path, current, token=self.operator, method="PUT")

        update_user({"attributes": {"workstream_subject_kind": ["human"]}})
        human = self.probe.login("workstream-mcp-proof", "workstream-mcp-audience", email, password)
        status, result = exchange(human["access_token"])
        self.assertEqual(status, 200)
        actual = claims(result["access_token"], "workstream-api")
        source = claims(human["access_token"], realm_config.MCP_RESOURCE)
        self.assertEqual(actual["sub"], source["sub"])
        self.assertLessEqual(actual["exp"], source["exp"])
        self.assertLessEqual(actual["exp"] - actual["iat"], 120)
        self.assertNotIn("refresh_token", result)
        # A fresh five-minute source cannot discriminate the source-expiry
        # ceiling from the exchange client's independent two-minute limit.
        source_client = next(c for c in clients if c["clientId"] == "workstream-mcp-proof")
        source_path = f"/admin/realms/flow/clients/{source_client['id']}"
        original_client = self.probe.request(source_path, token=self.operator)
        short_client = json.loads(json.dumps(original_client))
        short_client.setdefault("attributes", {})["access.token.lifespan"] = "60"
        try:
            self.probe.request(source_path, short_client, token=self.operator, method="PUT")
            short_login = self.probe.login(
                "workstream-mcp-proof", "workstream-mcp-audience", email, password,
            )
            short_source = claims(short_login["access_token"], realm_config.MCP_RESOURCE)
            self.assertGreater(short_source["exp"] - time.time(), 0)
            self.assertLess(short_source["exp"] - time.time(), 120)
            short_status, short_result = exchange(short_login["access_token"])
            self.assertEqual(short_status, 200)
            short_actual = claims(short_result["access_token"], "workstream-api")
            self.assertEqual(short_actual["sub"], short_source["sub"])
            self.assertLessEqual(short_actual["exp"], short_source["exp"])
            self.assertNotIn("refresh_token", short_result)
        finally:
            self.probe.request(source_path, original_client, token=self.operator, method="PUT")
        for override in (
            {"audience": "workstream-mcp"}, {"scope": "workstream:access workstream:admin"},
            {"requested_token_type": "urn:ietf:params:oauth:token-type:refresh_token"},
        ):
            denied(*exchange(human["access_token"], **override))

        # A fixture-only service client produces a real provider-signed,
        # nonhuman source with the same requested audience and scope.
        service = realm_config.restricted_client("negative-service")
        service.update(serviceAccountsEnabled=True,
            defaultClientScopes=["basic", "workstream:access", "workstream-mcp-audience"],
            protocolMappers=[realm_config.claim_mapper("service-kind", "oidc-hardcoded-claim-mapper", {
                "claim.name": "subject_kind", "claim.value": "service", "jsonType.label": "String",
            })])
        self.probe.request("/admin/realms/flow/clients", service, token=self.operator)
        clients = self.probe.request("/admin/realms/flow/clients", token=self.operator)
        service_id = next(c["id"] for c in clients if c["clientId"] == "negative-service")
        service_secret = self.probe.request(
            f"/admin/realms/flow/clients/{service_id}/client-secret", token=self.operator)["value"]
        service_token = self.probe.request("/realms/flow/protocol/openid-connect/token", {
            "grant_type": "client_credentials", "client_id": "negative-service",
            "client_secret": service_secret,
        }, form=True)["access_token"]
        self.assertEqual(claims(service_token, realm_config.MCP_RESOURCE)["subject_kind"], "service")
        denied(*exchange(service_token))
        # Prove the actual claim guard is discriminating, not an unrelated
        # client/audience rejection: temporarily remove only that executor in
        # this owned provider, then restore it before any subsequent assertion.
        profiles, _ = realm_config.exchange_policy()
        without_claim = json.loads(json.dumps(profiles))
        without_claim["profiles"][0]["executors"] = [
            e for e in without_claim["profiles"][0]["executors"]
            if e["executor"] != "jwt-claim-enforcer"
        ]
        try:
            self.probe.request("/admin/realms/flow/client-policies/profiles", without_claim,
                               token=self.operator, method="PUT")
            status, mutant = exchange(service_token)
            self.assertEqual(status, 200, "counterexample did not reach the removed claim guard")
            self.assertTrue(isinstance(mutant.get("access_token"), str))
        finally:
            self.probe.request("/admin/realms/flow/client-policies/profiles", profiles,
                               token=self.operator, method="PUT")
        denied(*exchange(service_token))

        # Terminate this exact user's sessions, not other fixture users.
        self.probe.request(user_path + "/logout", {}, token=self.operator)
        with self.assertRaises(ProviderRejected) as rejected:
            self.probe.request("/realms/flow/protocol/openid-connect/token", {
                "grant_type": "refresh_token", "client_id": "workstream-mcp-proof",
                "refresh_token": human["refresh_token"],
            }, form=True)
        self.assertEqual(rejected.exception.status, 400)
        renewed = self.probe.login("workstream-mcp-proof", "workstream-mcp-audience", email, password)
        update_user({"enabled": False})
        with self.assertRaises(LoginRejected):
            self.probe.login("workstream-mcp-proof", "workstream-mcp-audience", email, password)
        with self.assertRaises(ProviderRejected) as rejected:
            self.probe.request("/realms/flow/protocol/openid-connect/token", {
                "grant_type": "refresh_token", "client_id": "workstream-mcp-proof",
                "refresh_token": renewed["refresh_token"],
            }, form=True)
        self.assertEqual(rejected.exception.status, 400)
        update_user({"enabled": True})
        restored = self.probe.login("workstream-mcp-proof", "workstream-mcp-audience", email, password)
        self.assertEqual(claims(restored["access_token"], realm_config.MCP_RESOURCE)["sub"], source["sub"])

    def test_real_login_exchange_renewal_restart_and_database_isolation(self):
        container = json.loads(self.docker("inspect", self.identity))[0]
        self.assertFalse(any(value.startswith("KC_BOOTSTRAP_ADMIN") for value in container["Config"]["Env"]))
        self.assertFalse(any(mount["Destination"] == "/run/bootstrap-password" for mount in container["Mounts"]))
        password = secrets.token_urlsafe(24)
        email = "participant@example.invalid"
        self.probe.request("/admin/realms/flow/users", {
            "username": "participant", "email": email, "enabled": True,
            "firstName": "Test", "lastName": "Participant", "emailVerified": False,
            "attributes": {"workstream_subject_kind": ["human"]},
            "credentials": [{"type": "password", "value": password, "temporary": True}],
        }, token=self.operator)
        replacement = secrets.token_urlsafe(24)
        direct = self.probe.login("workstream-cli-login", "workstream-api-audience", email,
                                  password, new_password=replacement)
        mcp = self.probe.login("workstream-mcp-proof", "workstream-mcp-audience", email, replacement)
        clients = self.probe.request("/admin/realms/flow/clients", token=self.operator)
        client = next(c for c in clients if c["clientId"] == "workstream-mcp")
        secret = self.probe.request(f"/admin/realms/flow/clients/{client['id']}/client-secret",
                                    token=self.operator)["value"]

        async def boundaries():
            settings = Settings(_env_file=None, environment="test", auth_provider="flow",
                flow_auth_local_hmac_secret=None, token_issuer=self.origin + "/realms/flow",
                token_audience="workstream-api", token_algorithms="RS256",
                token_jwks_url=self.origin + "/realms/flow/protocol/openid-connect/certs",
                token_clock_skew_seconds=0, token_introspection_mode="disabled",
                token_introspection_disabled_reason="Bounded tokens; live Workstream authority checks")
            verifier = FlowAuthVerifier(settings, jwks_client_factory=partial(httpx.AsyncClient, verify=self.context))
            async with httpx.AsyncClient(verify=self.context, trust_env=False, timeout=10) as http:
                provider = KeycloakCredentials(OAuthSettings(self.origin + "/realms/flow",
                    realm_config.MCP_RESOURCE, self.root / "unused"), http, secret)
                identity = await provider.verify(mcp["access_token"])
                exchanged = await provider.exchange(identity)
                direct_facts = (await verifier.verify(direct["access_token"])).token
                facts = (await verifier.verify(exchanged[7:])).token
                self.assertEqual((facts.subject, facts.email, facts.subject_kind),
                                 (direct_facts.subject, email, "human"))
                self.assertEqual(facts.audience, ("workstream-api",))
                self.assertLessEqual(facts.expires_at, identity.expires_at)
                self.assertLessEqual(facts.expires_at - facts.issued_at, 120)
                with self.assertRaises(InvalidCredential):
                    await provider.verify(direct["access_token"])
                with self.assertRaises(AuthVerificationError):
                    await verifier.verify(mcp["access_token"])
                return identity.subject

        subject = asyncio.run(boundaries())
        refreshed = self.probe.request("/realms/flow/protocol/openid-connect/token", {
            "grant_type": "refresh_token", "client_id": "workstream-mcp-proof",
            "refresh_token": mcp["refresh_token"],
        }, form=True)
        self.assertNotEqual(refreshed["refresh_token"], mcp["refresh_token"])
        with self.assertRaises(ProviderRejected) as denied:
            self.probe.request("/realms/flow/protocol/openid-connect/token", {
                "grant_type": "refresh_token", "client_id": "workstream-mcp-proof",
                "refresh_token": mcp["refresh_token"],
            }, form=True)
        self.assertEqual(denied.exception.status, 400)
        keys = self.probe.request("/realms/flow/protocol/openid-connect/certs")
        self.docker("restart", self.identity)
        self.wait_ready()
        restarted_keys = self.probe.request("/realms/flow/protocol/openid-connect/certs")
        self.assertEqual(sorted(restarted_keys["keys"], key=lambda key: key["kid"]),
                         sorted(keys["keys"], key=lambda key: key["kid"]))
        persisted = self.probe.login("workstream-cli-login", "workstream-api-audience", email, replacement)
        # Verify the restarted provider signature and subject independently.
        raw = persisted["access_token"]
        key = next(k for k in keys["keys"] if k["kid"] == jwt.get_unverified_header(raw)["kid"])
        claims = jwt.decode(raw, jwt.PyJWK.from_dict(key).key, algorithms=["RS256"],
                            audience="workstream-api", issuer=self.origin + "/realms/flow")
        self.assertEqual(claims["sub"], subject)
        # Real privilege checks against production initialization SQL, not string matching.
        facts = self.docker("exec", self.pg, "psql", "-U", "postgres", "-d", "workstream", "-Atc",
            "SELECT has_database_privilege('workstream','flow_identity','CONNECT'), "
            "has_database_privilege('flow_identity','workstream','CONNECT'), "
            "has_database_privilege('workstream','workstream','CONNECT'), "
            "has_database_privilege('flow_identity','flow_identity','CONNECT');")
        self.assertEqual(facts, "f|f|t|t")


if __name__ == "__main__":
    unittest.main()
