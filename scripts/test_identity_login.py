"""Participant OAuth callback and credential custody regressions."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import ssl
import stat
import subprocess
import sys
import time
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from scripts import identity_login as login


class IdentityLoginTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "credentials.json"
        self.issuer = "https://identity.example/realms/flow"
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk.update(kid="fixture", alg="RS256", use="sig")
        now = int(time.time())
        self.claims = {"iss": self.issuer, "aud": "workstream-api", "sub": "fixture-user",
                       "azp": login.CLIENT, "iat": now, "exp": now + 300,
                       "scope": "openid workstream:access", "subject_kind": "human",
                       "email": "fixture@example.invalid", "typ": "Bearer"}
        self.tokens = {"token_type": "Bearer", "access_token": self.signed(self.claims),
                       "refresh_token": "synthetic-refresh", "expires_in": 300}

    def signed(self, claims, **headers):
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "fixture", **headers})

    def test_callback_rejects_substituted_state_host_and_duplicate_code(self):
        observed = []
        opened = []
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = []

            def launch(url):
                opened.append(parse_qs(urlsplit(url).query))
                state = opened[0]["state"][0]

                def browser():
                    opener = build_opener(ProxyHandler({}))
                    requests = [
                        ({"state": "foreign", "code": "wrong"}, "127.0.0.1:17843", 400),
                        ({"state": state, "code": "wrong"}, "attacker.example", 400),
                        ({"state": state, "code": ["first", "second"]}, "127.0.0.1:17843", 400),
                        ({"state": state, "code": "expected-code"}, "127.0.0.1:17843", 200),
                    ]
                    for query, host, expected in requests:
                        request = Request(login.CALLBACK + "?" + urlencode(query, doseq=True), headers={"Host": host})
                        try:
                            with opener.open(request, timeout=5) as response:
                                status = response.status
                                self.assertEqual(response.headers["Cache-Control"], "no-store")
                        except HTTPError as error:
                            status = error.code
                            error.close()
                        observed.append(status)
                        self.assertEqual(status, expected)

                futures.append(executor.submit(browser))
                return True

            code, verifier = login.browser_code(self.issuer + "/protocol/openid-connect/auth", launch=launch)
            futures[0].result(timeout=5)
        self.assertEqual(observed, [400, 400, 400, 200])
        self.assertEqual(code, "expected-code")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(opened[0]["code_challenge"], [challenge])
        self.assertEqual(opened[0]["code_challenge_method"], ["S256"])
        self.assertEqual(opened[0]["redirect_uri"], [login.CALLBACK])
        self.assertNotIn("password", opened[0])

    def test_discovery_cannot_change_issuer_or_token_destination(self):
        expected = {"issuer": self.issuer,
                    "authorization_endpoint": self.issuer + "/protocol/openid-connect/auth",
                    "token_endpoint": self.issuer + "/protocol/openid-connect/token",
                    "jwks_uri": self.issuer + "/protocol/openid-connect/certs",
                    "revocation_endpoint": self.issuer + "/protocol/openid-connect/revoke",
                    "code_challenge_methods_supported": ["S256"]}
        with patch.object(login, "request_json", return_value=expected):
            self.assertEqual(login.endpoints(self.issuer, ssl.create_default_context()),
                             (expected["authorization_endpoint"], expected["token_endpoint"]))
        for key in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "revocation_endpoint", "code_challenge_methods_supported"):
            altered = {**expected, key: [] if key == "code_challenge_methods_supported" else "https://foreign.example"}
            with self.subTest(key=key), patch.object(login, "request_json", return_value=altered):
                with self.assertRaises(login.LoginError):
                    login.endpoints(self.issuer, ssl.create_default_context())

    def test_provider_denial_closes_the_bound_callback_without_waiting_for_timeout(self):
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = []

            def launch(url):
                state = parse_qs(urlsplit(url).query)["state"][0]

                def cancel():
                    with build_opener(ProxyHandler({})).open(
                        login.CALLBACK + "?" + urlencode({"state": state, "error": "access_denied"}),
                        timeout=5,
                    ) as response:
                        self.assertEqual(response.status, 200)

                futures.append(executor.submit(cancel))
                return True

            with self.assertRaisesRegex(login.LoginError, "did not authorize"):
                login.browser_code(self.issuer + "/protocol/openid-connect/auth", launch=launch)
            futures[0].result(timeout=5)
        self.assertFalse(self.path.exists())

    def test_saved_tokens_are_private_bound_and_never_overwritten_by_new_login(self):
        self.assertEqual(login.private_path(self.path), self.path)
        login.save_credentials(self.path, self.issuer, self.tokens, self.claims, replace=False)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)
        saved = login.read_credentials(self.path, self.issuer)
        self.assertEqual(saved["access_token"], self.tokens["access_token"])
        self.assertEqual(saved["refresh_token"], self.tokens["refresh_token"])
        self.assertNotIn("password", saved)
        with self.assertRaises(FileExistsError):
            login.save_credentials(self.path, self.issuer, {**self.tokens, "access_token": "other"}, self.claims, replace=False)
        self.assertEqual(login.read_credentials(self.path, self.issuer), saved)
        with self.assertRaises(login.LoginError):
            login.read_credentials(self.path, "https://foreign.example/realms/flow")
        login.save_credentials(self.path, self.issuer, {**self.tokens, "refresh_token": "rotated"}, self.claims, replace=True)
        self.assertEqual(login.read_credentials(self.path, self.issuer)["refresh_token"], "rotated")
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_symlink_hardlink_and_public_credentials_are_rejected(self):
        login.save_credentials(self.path, self.issuer, self.tokens, self.claims, replace=False)
        alias = self.root / "alias"
        alias.symlink_to(self.path)
        with self.assertRaises(OSError):
            login.read_credentials(alias, self.issuer)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaises(login.LoginError):
            login.read_credentials(self.path, self.issuer)
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(login.LoginError):
            login.read_credentials(self.path, self.issuer)
        self.root.chmod(0o755)
        with self.assertRaises(login.LoginError):
            login.private_path(self.path)

    def test_bad_token_response_preserves_existing_credentials(self):
        login.save_credentials(self.path, self.issuer, self.tokens, self.claims, replace=False)
        original = self.path.read_bytes()
        for change in ({"token_type": 1}, {"access_token": ""}, {"refresh_token": None}, {"expires_in": True}):
            with self.subTest(change=change), self.assertRaises(login.LoginError):
                login.save_credentials(self.path, self.issuer, {**self.tokens, **change}, self.claims, replace=True)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(json.loads(original)["client_id"], login.CLIENT)


    def test_signed_contract_rejects_each_substitution_before_publication_or_child(self):
        substitutions = ({"aud": ["workstream-api", "foreign"]}, {"azp": "foreign"},
            {"iss": "https://foreign.example/realms/flow"}, {"subject_kind": "service"},
            {"scope": "openid"}, {"typ": "ID"}, {"sub": ""}, {"email": ""},
            {"exp": int(time.time()) - 1}, {"iat": True}, {"exp": self.claims["iat"] + 301})
        with patch.object(login, "request_json", return_value={"keys": [self.jwk]}):
            self.assertEqual(login.validate_tokens(self.tokens, self.issuer, ssl.create_default_context()), self.claims)
            for changes in substitutions:
                with self.subTest(changes=changes), self.assertRaises(login.LoginError):
                    login.validate_tokens({**self.tokens, "access_token": self.signed({**self.claims, **changes})}, self.issuer, ssl.create_default_context())
            with self.assertRaises(login.LoginError):
                login.validate_tokens(self.tokens, self.issuer, ssl.create_default_context(), expected_subject="foreign")
            with self.assertRaises(login.LoginError):
                login.validate_tokens({**self.tokens, "access_token": self.signed(self.claims, jku="https://foreign.example/key")}, self.issuer, ssl.create_default_context())
            other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            forged = jwt.encode(self.claims, other, algorithm="RS256", headers={"kid": "fixture"})
            with self.assertRaises(login.LoginError):
                login.validate_tokens({**self.tokens, "access_token": forged}, self.issuer, ssl.create_default_context())
        def response(url, *_args, **_kwargs):
            return {"keys": [self.jwk]} if url.endswith("/certs") else {**self.tokens, "access_token": forged}
        with patch.object(sys, "argv", ["identity_login", "--output", str(self.path), "--exec", "workstream", "whoami"]), patch.object(login, "endpoints", return_value=("auth", "token")), patch.object(login, "browser_code", return_value=("code", "verifier")), patch.object(login, "request_json", side_effect=response), patch.object(login, "run_cli") as child:
            self.assertEqual(login.main(), 1)
            child.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_refresh_rejects_valid_signed_different_subject_without_replacing_saved_login(self):
        login.save_credentials(self.path, self.issuer, self.tokens, self.claims, replace=False)
        before = self.path.read_bytes()
        changed = {**self.tokens, "access_token": self.signed({**self.claims, "sub": "different-human"})}
        def response(url, *_args, **_kwargs):
            return {"keys": [self.jwk]} if url.endswith("/certs") else changed
        with patch.object(sys, "argv", ["identity_login", "--issuer", self.issuer, "--output", str(self.path), "--refresh", "--exec", "workstream", "whoami"]), patch.object(login, "endpoints", return_value=("auth", "token")), patch.object(login, "request_json", side_effect=response), patch.object(login, "run_cli") as child:
            self.assertEqual(login.main(), 1)
            child.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_memory_mode_and_child_use_only_verified_token_and_trusted_origin(self):
        def response(url, *_args, **_kwargs):
            return {"keys": [self.jwk]} if url.endswith("/certs") else self.tokens
        with patch.object(sys, "argv", ["identity_login", "--issuer", self.issuer, "--exec", "workstream", "whoami"]), patch.object(login, "endpoints", return_value=("auth", "token")), patch.object(login, "browser_code", return_value=("code", "verifier")), patch.object(login, "request_json", side_effect=response), patch.object(login.subprocess, "run") as child, patch.dict(os.environ, {"WORKSTREAM_TOKEN": "foreign", "WORKSTREAM_API_URL": "https://foreign.example"}):
            child.return_value.returncode = 0
            self.assertEqual(login.main(), 0)
            args, kwargs = child.call_args
            self.assertEqual(args[0], ["workstream", "whoami"])
            self.assertEqual(kwargs["env"]["WORKSTREAM_TOKEN"], self.tokens["access_token"])
            self.assertEqual(kwargs["env"]["WORKSTREAM_API_URL"], login.API_ORIGIN)
            self.assertNotIn("shell", kwargs)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_logout_failure_removes_local_credentials_without_claiming_remote_revocation(self):
        login.save_credentials(self.path, self.issuer, self.tokens, self.claims, replace=False)
        with login.credential_lock(self.path), patch.object(login, "endpoints", side_effect=login.LoginError("unavailable")):
            with self.assertRaisesRegex(login.LoginError, "remote revocation is unconfirmed"):
                login.logout(self.path, self.issuer, ssl.create_default_context())
        self.assertFalse(self.path.exists())
        self.assertTrue(self.path.with_name(self.path.name + ".lock").exists())

    def test_refresh_and_logout_processes_cannot_race_or_resurrect_credentials(self):
        login.save_credentials(self.path, self.issuer, self.tokens, self.claims, replace=False)
        fixture = self.root / "fixture.json"
        fixture.write_text(json.dumps({"tokens": {**self.tokens, "refresh_token": "new-refresh"}, "key": self.jwk}))
        code = """
import json,sys
from pathlib import Path
from unittest.mock import patch
from scripts import identity_login as login
path,issuer,operation,fixture_path,marker=sys.argv[1:]
data=json.loads(Path(fixture_path).read_text())
def response(url,*args,**kwargs):
    if url.endswith('/certs'):return {'keys':[data['key']]}
    Path(marker).write_text('network called')
    return {} if url.endswith('/revoke') else data['tokens']
with patch.object(sys,'argv',['identity_login','--issuer',issuer,'--output',path,operation]), patch.object(login,'endpoints',return_value=('auth','token')), patch.object(login,'request_json',side_effect=response):
    raise SystemExit(login.main())
"""
        marker = self.root / "network"
        def child(operation):
            return subprocess.run([sys.executable, "-c", code, str(self.path), self.issuer, operation, str(fixture), str(marker)], capture_output=True, text=True, timeout=15)
        with login.credential_lock(self.path):
            for operation in ("--refresh", "--logout"):
                result = child(operation)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Another credential operation", result.stdout)
                self.assertFalse(marker.exists())
                self.assertEqual(login.read_credentials(self.path, self.issuer)["refresh_token"], "synthetic-refresh")
        self.assertEqual(child("--refresh").returncode, 0)
        self.assertEqual(login.read_credentials(self.path, self.issuer)["refresh_token"], "new-refresh")
        self.assertEqual(child("--logout").returncode, 0)
        marker.unlink()
        self.assertEqual(child("--refresh").returncode, 1)
        self.assertFalse(marker.exists())
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
