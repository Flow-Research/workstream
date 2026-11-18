"""Real browser signup and recovery with fixture-only SMTP capture and real Keycloak."""
from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import unittest
from urllib.parse import urlencode, urlsplit

import jwt
from playwright.sync_api import sync_playwright

from deploy.identity import realm_config
from scripts.identity_mail_fixture import FileMessages
from scripts.identity_protocol_probe import ProviderRejected
from scripts.test_identity_provider import IdentityProviderTests


class IdentitySignupTests(IdentityProviderTests):
    def test_verified_signup_and_password_recovery(self):
        mail_root = self.root / ("mail-" + secrets.token_hex(4))
        mail_root.mkdir(mode=0o700)
        mail_name = self.name + "-mail-" + secrets.token_hex(4)
        self.addCleanup(self.docker, "rm", "-f", mail_name)
        self.docker("run", "-d", "--name", mail_name, "--network", self.name,
            "--user", f"{os.getuid()}:{os.getgid()}", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "64m", "--cpus", "0.25",
            "--pids-limit", "32", "--mount", f"type=bind,src={mail_root},dst=/mail",
            "--mount", f"type=bind,src={os.path.abspath('scripts/identity_mail_fixture.py')},dst=/fixture.py,readonly",
            "python@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df",
            "python", "/fixture.py")
        mailbox = FileMessages(mail_root)
        smtp = {"host": mail_name, "port": "1025",
                "from": "identity@example.invalid", "fromDisplayName": "Flow Identity",
                "ssl": "false", "starttls": "false", "auth": "false"}
        # Plain SMTP is restricted to this owned fixture network, never deployment config.
        current = self.probe.request("/admin/realms/flow", token=self.operator)
        server = self.probe.request("/admin/serverinfo", token=self.operator)
        profile = self.probe.request("/admin/realms/flow/users/profile", token=self.operator)
        patch = realm_config.self_service_settings(
            {**current, "smtpServer": {**smtp, "starttls": "true"}}, server, profile)
        self.probe.request("/admin/realms/flow", {**patch, "smtpServer": smtp},
                           token=self.operator, method="PUT")
        home = self.root / ("signup-browser-" + secrets.token_hex(4))
        database = home / ".pki/nssdb"
        database.mkdir(parents=True, mode=0o700)
        chrome, certutil = shutil.which("google-chrome"), shutil.which("certutil")
        self.assertIsNotNone(chrome)
        self.assertIsNotNone(certutil)
        for cmd in ([certutil, "-N", "--empty-password", "-d", "sql:" + str(database)],
                    [certutil, "-A", "-n", "fixture", "-t", "C,,", "-d", "sql:" + str(database),
                     "-i", str(self.root / "cert.pem")]):
            subprocess.run(cmd, check=True, capture_output=True, timeout=15)
        email, password = "self-signup-" + secrets.token_hex(4) + "@example.invalid", secrets.token_urlsafe(24)
        endpoint = "/realms/flow/protocol/openid-connect/token"

        def grant(value):
            return self.probe.request(endpoint, {"grant_type": "password", "client_id": "workstream-api-login",
                "username": email, "password": value,
                "scope": "openid workstream:access workstream-api-audience"}, form=True)

        def mail_link():
            message = BytesParser(policy=policy.default).parsebytes(mailbox.get(timeout=20))
            self.assertEqual(message["To"], email)
            self.assertIn("Flow", message["Subject"])
            content = message.get_body(preferencelist=("plain",)).get_content()
            links = re.findall(r'https://[^\s<>]+', content)
            link = next(value for value in links if "/login-actions/action-token?" in value)
            self.assertTrue(link.startswith(self.origin + "/"))
            return link

        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = urlencode({"client_id": "workstream-cli-login", "redirect_uri": "http://127.0.0.1:17843/callback",
            "response_type": "code", "scope": "openid workstream:access workstream-api-audience",
            "state": secrets.token_urlsafe(24), "code_challenge": challenge, "code_challenge_method": "S256"})
        authorization = self.origin + "/realms/flow/protocol/openid-connect/auth?" + query
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=chrome, headless=True,
                chromium_sandbox=True, env={**os.environ, "HOME": str(home)})
            stage = "registration"
            try:
                page = browser.new_page()
                page.goto(authorization)
                self.assertIn("Flow", page.title())
                self.assertEqual(page.locator("#kc-header-wrapper").evaluate(
                    "element => getComputedStyle(element).color"), "rgb(21, 42, 56)")
                logo = page.locator("#kc-header-wrapper").evaluate(
                    "element => getComputedStyle(element, '::before').backgroundImage")
                self.assertIn("flow-logo.png", logo)
                page.screenshot(path=str(self.root / "flow-login-desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"))
                page.screenshot(path=str(self.root / "flow-login-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 1280, "height": 900})
                page.get_by_role("link", name="Register", exact=True).click()
                for selector, value in (("#firstName", "Self"), ("#lastName", "Participant"),
                                        ("#email", email), ("#password", password), ("#password-confirm", password)):
                    if page.locator(selector).count():
                        page.locator(selector).fill(value)
                # Submitted privilege-like attributes must not become trusted identity.
                page.locator("form").first.evaluate("form => { for (const name of ['workstream_subject_kind', 'user.attributes.workstream_subject_kind']) { const field=document.createElement('input'); field.type='hidden'; field.name=name; field.value='service'; form.appendChild(field); } }")
                with page.expect_response(lambda response: response.request.method == "POST" and "/login-actions/" in response.url):
                    page.locator('button[type="submit"], input[type="submit"]').first.click()
                page.wait_for_load_state("domcontentloaded")
                page.screenshot(path=str(self.root / "flow-signup-preview.png"), full_page=True)
                self.setUp()
                rejected_users = self.probe.request("/admin/realms/flow/users?username=" + email + "&exact=true", token=self.operator)
                self.assertEqual(rejected_users, [])
                self.assertTrue(mailbox.empty())
                # Start a clean registration after the deliberately rejected tampering.
                page.goto(authorization)
                page.get_by_role("link", name="Register", exact=True).click()
                for selector, value in (("#firstName", "Self"), ("#lastName", "Participant"),
                                        ("#email", email), ("#password", password), ("#password-confirm", password)):
                    if page.locator(selector).count():
                        page.locator(selector).fill(value)
                page.locator('button[type="submit"], input[type="submit"]').first.click()
                stage = "verification-mail"
                print(json.dumps({"stage": "submitted", "path": urlsplit(page.url).path,
                    "alerts": [text.replace(password, "[redacted]") for text in page.locator(".pf-v5-c-alert__title, .kc-feedback-text").all_text_contents()]}), flush=True)
                verification = mail_link()
                with self.assertRaises(ProviderRejected) as denied:
                    grant(password)
                self.assertEqual(denied.exception.status, 400)
                stage = "verification-link"
                page.goto(verification)
                # Email verification may require an explicit confirmation on a new tab.
                confirm = page.locator('form button[type="submit"], form input[type="submit"]')
                if confirm.count() and page.locator('#password-new').count() == 0 and not page.locator('[name="accept"]').count():
                    confirm.first.click()
                if page.locator('#password-new').count():
                    page.locator('#password-new').fill(password)
                    page.locator('#password-confirm').fill(password)
                    page.locator('button[type="submit"], input[type="submit"]').first.click()
                stage = "verified-grant"
                tokens = grant(password)
                keys = self.probe.request("/realms/flow/protocol/openid-connect/certs")["keys"]
                key = next(k for k in keys if k["kid"] == jwt.get_unverified_header(tokens["access_token"])["kid"])
                claims = jwt.decode(tokens["access_token"], jwt.PyJWK.from_dict(key).key,
                    algorithms=["RS256"], audience="workstream-api", issuer=self.origin + "/realms/flow")
                self.setUp()
                users = self.probe.request("/admin/realms/flow/users?username=" + email + "&exact=true", token=self.operator)
                self.assertEqual(len(users), 1)
                self.assertTrue(users[0]["emailVerified"])
                self.assertEqual(claims["sub"], users[0]["id"])
                self.assertEqual(claims["subject_kind"], "human")
                self.assertEqual(claims["email"], email)
                self.assertEqual(users[0]["attributes"]["workstream_subject_kind"], ["human"])
                self.assertNotIn("realm_access", claims)
                self.assertNotIn("resource_access", claims)
                stage = "password-recovery"
                # A new browser context tests recovery without the registration session.
                page = browser.new_page()
                page.goto(authorization)
                page.get_by_role("link", name="Forgot Password?", exact=False).click()
                page.locator("#username").fill(email)
                page.locator('button[type="submit"], input[type="submit"]').first.click()
                reset = mail_link()
                page.goto(reset)
                replacement = secrets.token_urlsafe(24)
                page.locator("#password-new").fill(replacement)
                page.locator("#password-confirm").fill(replacement)
                page.locator('button[type="submit"], input[type="submit"]').first.click()
                with self.assertRaises(ProviderRejected) as denied:
                    grant(password)
                self.assertEqual(denied.exception.status, 400)
                self.assertIn("access_token", grant(replacement))
                page.goto(reset)
                self.assertEqual(page.locator("#password-new").count(), 0)
                self.assertIn("access_token", grant(replacement))
                stage = "expired-reset"
                self.setUp()
                self.probe.request("/admin/realms/flow", {"actionTokenGeneratedByUserLifespan": 1},
                                   token=self.operator, method="PUT")
                page = browser.new_page()
                page.goto(authorization)
                page.get_by_role("link", name="Forgot Password?", exact=False).click()
                page.locator("#username").fill(email)
                page.locator('button[type="submit"], input[type="submit"]').first.click()
                expired = mail_link()
                time.sleep(2)
                page.goto(expired)
                self.assertEqual(page.locator("#password-new").count(), 0)
                self.assertIn("access_token", grant(replacement))
                stage = "mail-outage"
                (mail_root / "unavailable").touch()
                page = browser.new_page()
                page.goto(authorization)
                page.get_by_role("link", name="Forgot Password?", exact=False).click()
                page.locator("#username").fill(email)
                with page.expect_response(lambda response: response.request.method == "POST" and "/login-actions/" in response.url):
                    page.locator('button[type="submit"], input[type="submit"]').first.click()
                page.wait_for_load_state("domcontentloaded")
                self.assertTrue(mailbox.empty())
                self.assertIn("access_token", grant(replacement))
                self.assertNotIn(replacement, page.locator("body").inner_text())
                self.assertEqual(page.locator("#password-new").count(), 0)
                page.screenshot(path=str(self.root / "flow-recovery-proof.png"), full_page=True)
            except Exception as error:
                # Browser exceptions can include entered passwords and link tokens.
                raise RuntimeError("Signup qualification failed at " + stage + ": " + type(error).__name__) from None
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
