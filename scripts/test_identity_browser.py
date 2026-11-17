"""Real Chrome qualification of the native participant CLI, with an isolated CA store.

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
import time

import jwt
from playwright.sync_api import sync_playwright

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
        binary = os.environ.get("WORKSTREAM_TEST_CLI")
        self.assertTrue(binary and os.path.isfile(binary), "build the native CLI and set WORKSTREAM_TEST_CLI")
        self.assertTrue(os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "run with an isolated unlocked Secret Service")
        clients = self.probe.request("/admin/realms/flow/clients?clientId=workstream-cli-login", token=self.operator)
        self.assertEqual(len(clients), 1)
        client = clients[0]
        client["attributes"]["access.token.lifespan"] = "35"
        self.probe.request("/admin/realms/flow/clients/" + client["id"], client, token=self.operator, method="PUT")
        launcher = self.root / "bin"
        launcher.mkdir()
        (launcher / "xdg-open").write_text("#!/bin/sh\nexit 1\n")
        (launcher / "xdg-open").chmod(0o700)
        env = {**os.environ, "XDG_CONFIG_HOME": str(self.root / "cli-config"),
               "SSL_CERT_FILE": str(self.root / "cert.pem"), "PATH": str(launcher) + ":" + os.environ["PATH"]}
        env.pop("WORKSTREAM_TOKEN", None)
        env.pop("WORKSTREAM_API_URL", None)
        command = subprocess.Popen([binary, "login", "--issuer", self.origin + "/realms/flow"],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                line = executor.submit(command.stderr.readline).result(timeout=20)
            self.assertTrue(line.startswith("Sign in using your browser: "), "CLI failed before browser login")
            address = line.split("Sign in using your browser: ", 1)[1].strip()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=chrome, headless=True,
                    chromium_sandbox=True, env={**os.environ, "HOME": str(home)})
                try:
                    page = browser.new_page()
                    page.goto(address, wait_until="domcontentloaded", timeout=30000)
                    page.locator("#username").fill(email)
                    page.locator("#password").fill(temporary_password)
                    page.locator("#kc-login").click()
                    page.locator("#password-new").fill(replacement)
                    page.locator("#password-confirm").fill(replacement)
                    page.locator("form").first.locator('button[type="submit"], input[type="submit"]').first.click()
                    page.locator('input[name="accept"], button[name="accept"]').click()
                    page.wait_for_url("http://127.0.0.1:17843/callback**", timeout=15000)
                except Exception as error:
                    raise RuntimeError("Native browser qualification failed: " + type(error).__name__) from None
                finally:
                    browser.close()
            command.wait(timeout=30)
            self.assertEqual(command.returncode, 0, "native CLI login failed")
            def cli(*args):
                result = subprocess.run([binary, *args], env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, "native CLI command failed")
                return result.stdout.strip()
            first = cli("auth", "token")
            keys = self.probe.request("/realms/flow/protocol/openid-connect/certs")["keys"]
            key = next(k for k in keys if k["kid"] == jwt.get_unverified_header(first)["kid"])
            claims = jwt.decode(first, jwt.PyJWK.from_dict(key).key, algorithms=["RS256"],
                                audience="workstream-api", issuer=self.origin + "/realms/flow")
            self.assertEqual(claims["email"], email)
            self.assertEqual(claims["subject_kind"], "human")
            time.sleep(max(0, claims["exp"] - time.time() - 29))
            renewed = cli("auth", "token")
            self.assertNotEqual(first, renewed, "near-expiry token was not renewed")
            cli("logout")
            result = subprocess.run([binary, "auth", "token"], env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.setUp()  # Refresh the short-lived operator token after browser/renewal work.
            sessions = self.probe.request("/admin/realms/flow/users/" + claims["sub"] + "/sessions", token=self.operator)
            self.assertFalse(any("workstream-cli-login" in item.get("clients", {}).values() for item in sessions),
                             "CLI logout retained its provider session")
        finally:
            if command.poll() is None:
                command.kill()
                command.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
