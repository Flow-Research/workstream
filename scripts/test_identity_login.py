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
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from scripts import identity_login as login


class IdentityLoginTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "credentials.json"
        self.issuer = "https://identity.example/realms/flow"
        self.tokens = {"token_type": "Bearer", "access_token": "synthetic-access",
                       "refresh_token": "synthetic-refresh", "expires_in": 300}

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
                    "code_challenge_methods_supported": ["S256"]}
        with patch.object(login, "request_json", return_value=expected):
            self.assertEqual(login.endpoints(self.issuer, ssl.create_default_context()),
                             (expected["authorization_endpoint"], expected["token_endpoint"]))
        for key in ("issuer", "authorization_endpoint", "token_endpoint", "code_challenge_methods_supported"):
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
        login.save_credentials(self.path, self.issuer, self.tokens, replace=False)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)
        saved = login.read_credentials(self.path, self.issuer)
        self.assertEqual(saved["access_token"], self.tokens["access_token"])
        self.assertEqual(saved["refresh_token"], self.tokens["refresh_token"])
        self.assertNotIn("password", saved)
        with self.assertRaises(FileExistsError):
            login.save_credentials(self.path, self.issuer, {**self.tokens, "access_token": "other"}, replace=False)
        self.assertEqual(login.read_credentials(self.path, self.issuer), saved)
        with self.assertRaises(login.LoginError):
            login.read_credentials(self.path, "https://foreign.example/realms/flow")
        login.save_credentials(self.path, self.issuer, {**self.tokens, "refresh_token": "rotated"}, replace=True)
        self.assertEqual(login.read_credentials(self.path, self.issuer)["refresh_token"], "rotated")
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_symlink_hardlink_and_public_credentials_are_rejected(self):
        login.save_credentials(self.path, self.issuer, self.tokens, replace=False)
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
        login.save_credentials(self.path, self.issuer, self.tokens, replace=False)
        original = self.path.read_bytes()
        for change in ({"token_type": 1}, {"access_token": ""}, {"refresh_token": None}, {"expires_in": True}):
            with self.subTest(change=change), self.assertRaises(login.LoginError):
                login.save_credentials(self.path, self.issuer, {**self.tokens, **change}, replace=True)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(json.loads(original)["client_id"], login.CLIENT)


if __name__ == "__main__":
    unittest.main()
