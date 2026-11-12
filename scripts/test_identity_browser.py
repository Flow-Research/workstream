"""Real Chrome qualification of the participant helper, with an isolated CA store.

Requires Playwright, Chrome and certutil on the qualification host. No TLS
verification or browser sandbox is disabled; no personal browser profile is used.
Run with PYTHONPATH=.:backend:mcp_server:packages/external-services and the same
built identity image used by test_identity_provider.py. The inherited provider
proof runs against this same isolated fixture.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import secrets
import shutil
import subprocess
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import ProxyHandler, build_opener

import jwt
from playwright.sync_api import sync_playwright

from scripts import identity_login as login
from scripts import test_identity_provider as provider


class IdentityBrowserTests(provider.IdentityProviderTests):
    def setUp(self):
        # Browser qualification can exceed the temporary admin token's lifetime.
        self.operator = self.probe.request("/realms/master/protocol/openid-connect/token", {
            "grant_type": "password", "client_id": "admin-cli", "username": "fixture-operator",
            "password": self.admin_password,
        }, form=True)["access_token"]

    def test_browser_password_change_callback_and_saved_renewal(self):
        chrome = shutil.which("google-chrome")
        certutil = shutil.which("certutil")
        self.assertIsNotNone(chrome, "qualification requires an installed Chrome binary")
        self.assertIsNotNone(certutil, "qualification requires certutil for isolated CA trust")
        home = self.root / "browser-home"
        database = home / ".pki/nssdb"
        database.mkdir(parents=True, mode=0o700)
        home.chmod(0o700)
        for command in (
            [certutil, "-N", "--empty-password", "-d", "sql:" + str(database)],
            [certutil, "-A", "-n", "owned-provider-fixture", "-t", "C,,", "-d",
             "sql:" + str(database), "-i", str(self.root / "cert.pem")],
        ):
            subprocess.run(command, check=True, capture_output=True, timeout=15)
        temporary_password = secrets.token_urlsafe(24)
        replacement = secrets.token_urlsafe(24)
        email = "browser-participant@example.invalid"
        self.probe.request("/admin/realms/flow/users", {
            "username": "browser-participant", "email": email, "enabled": True,
            "firstName": "Browser", "lastName": "Participant",
            "attributes": {"workstream_subject_kind": ["human"]},
            "credentials": [{"type": "password", "value": temporary_password, "temporary": True}],
        }, token=self.operator)
        authorization, token_endpoint = login.endpoints(self.origin + "/realms/flow", self.context)
        futures = []
        with ThreadPoolExecutor(max_workers=1) as executor:
            def launch(url):
                def browser():
                    stage = "browser startup"
                    with sync_playwright() as playwright:
                        chromium = playwright.chromium.launch(
                            executable_path=chrome, headless=True, chromium_sandbox=True,
                            env={**os.environ, "HOME": str(home)},
                        )
                        try:
                            page = chromium.new_page()
                            stage = "trusted HTTPS login page"
                            page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            stage = "initial login"
                            page.locator("#username").fill(email)
                            page.locator("#password").fill(temporary_password)
                            page.locator("#kc-login").click()
                            stage = "mandatory password change"
                            page.locator("#password-new").fill(replacement)
                            page.locator("#password-confirm").fill(replacement)
                            page.locator("form").first.locator(
                                'button[type="submit"], input[type="submit"]',
                            ).first.click()
                            stage = "consent"
                            page.locator('input[name="accept"], button[name="accept"]').click()
                            stage = "loopback callback"
                            page.wait_for_url(login.CALLBACK + "**", timeout=15000)
                            self.assertIn("Return to your terminal", page.locator("body").inner_text())
                        except Exception as error:
                            # Unblock the helper, then fail before any token
                            # exchange. Do not expose Playwright call logs: a
                            # failed fill operation can include a password.
                            state = parse_qs(urlsplit(url).query)["state"][0]
                            try:
                                with build_opener(ProxyHandler({})).open(
                                    login.CALLBACK + "?" + urlencode({"state": state, "code": "fixture-abort"}),
                                    timeout=5,
                                ):
                                    pass
                            except OSError:
                                pass
                            raise RuntimeError(f"Browser qualification failed at {stage}: {type(error).__name__}") from None
                        finally:
                            chromium.close()
                futures.append(executor.submit(browser))
                return True

            code, verifier = login.browser_code(authorization, launch=launch)
            futures[0].result(timeout=30)
        result = login.request_json(token_endpoint, self.context, {
            "grant_type": "authorization_code", "client_id": login.CLIENT,
            "redirect_uri": login.CALLBACK, "code": code, "code_verifier": verifier,
        })
        path = self.root / "browser-credentials.json"
        issuer = self.origin + "/realms/flow"
        login.save_credentials(login.private_path(path), issuer, result, replace=False)
        saved = login.read_credentials(path, issuer)
        keys = self.probe.request("/realms/flow/protocol/openid-connect/certs")["keys"]
        key = next(k for k in keys if k["kid"] == jwt.get_unverified_header(saved["access_token"])["kid"])
        claims = jwt.decode(saved["access_token"], jwt.PyJWK.from_dict(key).key,
                            algorithms=["RS256"], audience="workstream-api", issuer=issuer)
        self.assertEqual(claims["email"], email)
        self.assertEqual(claims["subject_kind"], "human")
        renewed = login.request_json(token_endpoint, self.context, {
            "grant_type": "refresh_token", "client_id": login.CLIENT,
            "refresh_token": saved["refresh_token"],
        })
        login.save_credentials(path, issuer, renewed, replace=True)
        self.assertNotEqual(login.read_credentials(path, issuer)["refresh_token"], saved["refresh_token"])


if __name__ == "__main__":
    unittest.main()
