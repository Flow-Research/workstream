"""Real browser signup and recovery with fixture-only SMTP capture and real Keycloak."""
from __future__ import annotations

import asyncio
from functools import partial
import base64
from email import policy
from email.parser import BytesParser
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
from app.adapters.auth.flow import FlowAuthVerifier
from app.core.config import Settings
from app.interfaces.auth import AuthVerificationError, AuthVerificationUnavailableError
from workstream_mcp.adapters.keycloak import KeycloakCredentials
from workstream_mcp.oauth import InvalidCredential, OAuthSettings
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
        actions = self.probe.request("/admin/realms/flow/authentication/required-actions", token=self.operator)
        verification_action = next(action for action in actions if action["alias"] == "VERIFY_EMAIL")
        action_path = "/admin/realms/flow/authentication/required-actions/VERIFY_EMAIL"
        self.probe.request(action_path, {**verification_action, "enabled": False}, token=self.operator, method="PUT")
        disabled_actions = self.probe.request("/admin/realms/flow/authentication/required-actions", token=self.operator)
        with self.assertRaisesRegex(ValueError, "VERIFY_EMAIL"):
            realm_config.self_service_settings({**current, "smtpServer": {**smtp, "starttls": "true"}},
                                              server, profile, disabled_actions)
        self.probe.request(action_path, verification_action, token=self.operator, method="PUT")
        patch = realm_config.self_service_settings(
            {**current, "smtpServer": {**smtp, "starttls": "true"}}, server, profile, actions)
        self.probe.request("/admin/realms/flow", {**patch, "smtpServer": smtp, "actionTokenGeneratedByUserLifespan": 300},
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

        def grant(value, username=None):
            return self.probe.request(endpoint, {"grant_type": "password", "client_id": "workstream-api-login",
                "username": email if username is None else username, "password": value,
                "scope": "openid workstream:access workstream-api-audience"}, form=True)

        def mail_link(recipient=None):
            message = BytesParser(policy=policy.default).parsebytes(mailbox.get(timeout=20))
            self.assertEqual(message["To"], email if recipient is None else recipient)
            self.assertIn("Flow", message["Subject"])
            content = message.get_body(preferencelist=("plain",)).get_content()
            links = re.findall(r'https://[^\s<>]+', content)
            link = next(value for value in links if "/login-actions/action-token?" in value)
            self.assertTrue(link.startswith(self.origin + "/"))
            return link

        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(24)
        query = urlencode({"client_id": "workstream-cli-login", "redirect_uri": "http://127.0.0.1:17843/callback",
            "response_type": "code", "scope": "openid workstream:access workstream-api-audience",
            "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
        authorization = self.origin + "/realms/flow/protocol/openid-connect/auth?" + query
        callbacks = []
        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if urlsplit(self.path).path != "/callback":
                    self.send_error(404)
                    return
                callbacks.append(parse_qs(urlsplit(self.path).query))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Fixture callback received")

            def log_message(self, *_args):
                pass  # Authorization codes must never enter test logs.

        receiver = HTTPServer(("127.0.0.1", 17843), CallbackHandler)
        thread = Thread(target=receiver.serve_forever, daemon=True)
        thread.start()
        def close_receiver():
            receiver.shutdown()
            receiver.server_close()
            thread.join(timeout=5)
        self.addCleanup(close_receiver)
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
                page.locator("#email").wait_for(state="visible")
                for selector, value in (("#firstName", "Self"), ("#lastName", "Participant"),
                                        ("#email", email), ("#password", password), ("#password-confirm", password)):
                    if selector in ("#email", "#firstName", "#lastName") or page.locator(selector).count():
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
                page.locator("#email").wait_for(state="visible")
                for selector, value in (("#firstName", "Self"), ("#lastName", "Participant"),
                                        ("#email", email), ("#password", password), ("#password-confirm", password)):
                    if selector in ("#email", "#firstName", "#lastName") or page.locator(selector).count():
                        page.locator(selector).fill(value)
                page.locator('button[type="submit"], input[type="submit"]').first.click()
                stage = "verification-mail"
                print(json.dumps({"stage": "submitted", "path": urlsplit(page.url).path,
                    "alerts": [text.replace(password, "[redacted]") for text in page.locator(".pf-v5-c-alert__title, .kc-feedback-text").all_text_contents()]}), flush=True)
                verification = mail_link()
                self.assertEqual(callbacks, [], "Unverified registration reached the OAuth callback")
                self.assertNotIn("code", parse_qs(urlsplit(page.url).query))
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
                stage = "registration-oauth-completion"
                if page.locator('[name="accept"]').count():
                    self.assertIn("workstream-cli-login", page.locator("body").inner_text())
                    page.locator('[name="accept"]').click()
                if not callbacks:
                    back = page.get_by_role("link", name=re.compile("back to", re.I))
                    if back.count():
                        back.first.click()
                    if page.locator('[name="accept"]').count():
                        page.locator('[name="accept"]').click()
                page.wait_for_url("http://127.0.0.1:17843/callback**", timeout=15000)
                self.assertEqual(len(callbacks), 1, "Registration must finish its original authorization")
                self.assertEqual(callbacks[0].get("state"), [state])
                self.assertNotIn("error", callbacks[0])
                code_tokens = self.probe.request(endpoint, {
                    "grant_type": "authorization_code", "client_id": "workstream-cli-login",
                    "redirect_uri": "http://127.0.0.1:17843/callback",
                    "code_verifier": verifier, "code": callbacks[0]["code"][0],
                }, form=True)
                self.assertIn("access_token", code_tokens)
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
                stage = "known-password-email-verification"
                known_email = "known-password-" + secrets.token_hex(4) + "@example.invalid"
                known_password = secrets.token_urlsafe(24)
                self.probe.request("/admin/realms/flow/users", {
                    "username": known_email, "email": known_email, "enabled": True,
                    "firstName": "Known", "lastName": "Participant", "emailVerified": False,
                    "attributes": {"workstream_subject_kind": ["human"]},
                    "credentials": [{"type": "password", "value": known_password, "temporary": False}],
                }, token=self.operator, method="POST")
                known_user = self.probe.request("/admin/realms/flow/users?username=" + known_email + "&exact=true",
                                                token=self.operator)[0]
                self.assertEqual(known_user.get("requiredActions", []), [])
                with self.assertRaises(ProviderRejected) as denied:
                    grant(known_password, known_email)
                self.assertEqual(denied.exception.status, 400)
                stage = "known-password-verification-mail"
                self.probe.request("/admin/realms/flow/users/" + known_user["id"] + "/send-verify-email",
                                   token=self.operator, method="PUT")
                known_page = browser.new_page()
                known_page.goto(mail_link(known_email))
                proceed = known_page.get_by_role("link", name="Click here to proceed", exact=False)
                if proceed.count():
                    proceed.click()
                confirm = known_page.locator('form button[type="submit"], form input[type="submit"]')
                if confirm.count():
                    confirm.first.click()
                self.assertEqual(known_page.locator("#password-new").count(), 0)
                stage = "known-password-verified-grant"
                known_page.screenshot(path=str(self.root / "flow-known-verification.png"), full_page=True)
                self.assertIn("access_token", grant(known_password, known_email))
                known_page.close()
                stage = "account-console-regression"
                console = self.probe.request("/admin/realms/flow/clients?clientId=account-console", token=self.operator)[0]
                console_path = "/admin/realms/flow/clients/" + console["id"]
                mappings = self.probe.request(console_path + "/scope-mappings", token=self.operator)
                basic = next(scope for scope in self.probe.request(
                    "/admin/realms/flow/client-scopes", token=self.operator) if scope["name"] == "basic")
                basic_path = console_path + "/default-client-scopes/" + basic["id"]
                self.probe.request(basic_path, token=self.operator, method="DELETE")
                # Reproduce the missing stock scopes rather than only checking the repair.
                self.probe.request(console_path, {"protocolMappers": []},
                                   token=self.operator, method="PUT")
                broken = browser.new_page()
                broken.goto(self.origin + "/realms/flow/account/")
                broken.locator("#username").fill(email)
                broken.locator("#password").fill(password)
                broken.locator("#kc-login").click()
                broken.get_by_text("Something went wrong", exact=True).wait_for()
                broken.close()
                self.setUp()
                self.probe.request(console_path, realm_config.account_console_settings(console),
                                   token=self.operator, method="PUT")
                # Client PUT updates mappers, but scope assignment has its own endpoint.
                self.probe.request(basic_path, token=self.operator, method="PUT")
                self.assertEqual([scope["name"] for scope in self.probe.request(
                    console_path + "/default-client-scopes", token=self.operator)], ["basic"])
                self.assertEqual(self.probe.request(console_path + "/scope-mappings", token=self.operator), mappings)
                after_console = self.probe.request(console_path, token=self.operator)
                for field in ("id", "fullScopeAllowed", "redirectUris", "attributes"):
                    self.assertEqual(after_console[field], console[field])
                stage = "account-console-repaired"
                account_tokens = []
                account_id_tokens = []
                def account_response(response):
                    if response.url == self.origin + endpoint and response.status == 200:
                        value = response.json().get("id_token")
                        if value:
                            account_id_tokens.append(value)
                def account_request(request):
                    if request.url.startswith(self.origin + "/realms/flow/account/"):
                        bearer = request.headers.get("authorization", "")
                        if bearer.startswith("Bearer "):
                            account_tokens.append(bearer[7:])
                account_page = browser.new_page()
                account_page.on("request", account_request)
                account_page.on("response", account_response)
                account_page.goto(self.origin + "/realms/flow/account/")
                account_page.locator("#username").fill(email)
                account_page.locator("#password").fill(password)
                account_page.locator("#kc-login").click()
                account_page.get_by_role("heading", name="Personal info", exact=True).wait_for()
                self.assertEqual(account_page.title(), "Flow Identity")
                self.assertEqual(account_page.get_by_test_id("options-toggle").inner_text(), "Self Participant")
                # Retain the stock dark-masthead/light-label contrast.
                self.assertEqual(account_page.get_by_test_id("options-toggle").evaluate(
                    "element => getComputedStyle(element).color"), "rgb(255, 255, 255)")
                logo = account_page.locator('[data-testid="page-header"] img').first
                self.assertTrue(logo.get_attribute("src").endswith("/img/flow-logo.png"))
                self.assertEqual(logo.locator("..").get_attribute("href"), "/realms/flow/account/")
                self.assertTrue(logo.evaluate("image => image.complete && image.naturalWidth > 0"))
                self.assertTrue(account_id_tokens)
                id_claims = jwt.decode(account_id_tokens[-1], jwt.PyJWK.from_dict(next(
                    k for k in keys if k["kid"] == jwt.get_unverified_header(account_id_tokens[-1])["kid"])).key,
                    algorithms=["RS256"], audience="account-console", issuer=self.origin + "/realms/flow")
                self.assertEqual(id_claims["given_name"], "Self")
                self.assertEqual(id_claims["family_name"], "Participant")
                self.assertEqual(id_claims["preferred_username"], email)
                self.assertNotIn("resource_access", id_claims)
                self.assertTrue(account_tokens)
                console_token = account_tokens[-1]
                console_key = next(k for k in keys if k["kid"] == jwt.get_unverified_header(console_token)["kid"])
                console_claims = jwt.decode(console_token, jwt.PyJWK.from_dict(console_key).key,
                    algorithms=["RS256"], audience="account", issuer=self.origin + "/realms/flow")
                self.assertEqual(console_claims["sub"], users[0]["id"])
                self.assertIn(console_claims["aud"], ("account", ["account"]))
                self.assertEqual(set(console_claims["resource_access"]), {"account"})
                self.assertIn("manage-account", console_claims["resource_access"]["account"]["roles"])
                self.assertNotIn("realm_access", console_claims)
                self.assertNotIn("subject_kind", console_claims)
                for claim in ("given_name", "family_name", "preferred_username"):
                    self.assertNotIn(claim, console_claims)
                account_page.screenshot(path=str(self.root / "flow-account-proof.png"), full_page=True)
                stage = "account-password-update"
                account_page.get_by_test_id("accountSecurity").click()
                account_page.get_by_role("link", name="Signing in", exact=True).click()
                account_page.get_by_test_id("password/credential-list").locator('[data-testrole="update"]').click()
                # Stock application-initiated password action may require reauthentication.
                account_page.locator("#password-new, #password").first.wait_for()
                if account_page.locator("#password").count():
                    account_page.locator("#password").fill(password)
                    account_page.locator("#kc-login").click()
                changed_password = secrets.token_urlsafe(24)
                account_page.locator("#password-new").fill(changed_password)
                account_page.locator("#password-confirm").fill(changed_password)
                account_page.locator('button[type="submit"], input[type="submit"]').first.click()
                account_page.get_by_role("heading", name="Signing in", exact=True).wait_for()
                with self.assertRaises(ProviderRejected):
                    grant(password)
                self.assertIn("access_token", grant(changed_password))
                password = changed_password
                stage = "new-account-client-scopes"
                for client_id, audience_scope, audience in (
                    ("workstream-cli-login", "workstream-api-audience", "workstream-api"),
                    ("workstream-mcp-proof", "workstream-mcp-audience", "workstream-mcp"),
                ):
                    client_tokens = self.probe.login(client_id, audience_scope, email, password,
                        scopes="workstream:access " + audience_scope)
                    client_key = next(k for k in keys if k["kid"] == jwt.get_unverified_header(client_tokens["access_token"])["kid"])
                    client_claims = jwt.decode(client_tokens["access_token"], jwt.PyJWK.from_dict(client_key).key,
                        algorithms=["RS256"], audience=audience, issuer=self.origin + "/realms/flow")
                    self.assertEqual(client_claims["sub"], users[0]["id"])
                    self.assertEqual(client_claims["subject_kind"], "human")
                    self.assertNotIn("realm_access", client_claims)
                    self.assertNotIn("resource_access", client_claims)
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
                page = browser.new_page()
                callback_count = len(callbacks)
                page.goto(reset)
                self.assertRegex(page.locator("body").inner_text(), r"(?i)(invalid|expired|already been used)")
                self.assertEqual(len(callbacks), callback_count)
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
                page = browser.new_page()
                callback_count = len(callbacks)
                page.goto(expired)
                self.assertRegex(page.locator("body").inner_text(), r"(?i)(invalid|expired)")
                self.assertEqual(len(callbacks), callback_count)
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
                self.assertTrue((mail_root / "rejected-data").exists(), "SMTP must observe rejected DATA")
                self.assertTrue(mailbox.empty())
                self.assertIn("If no email arrives, retry later or contact your Flow administrator.", page.locator("body").inner_text())
                self.assertIn("access_token", grant(replacement))
                self.assertNotIn(replacement, page.locator("body").inner_text())
                self.assertEqual(page.locator("#password-new").count(), 0)
                page.screenshot(path=str(self.root / "flow-recovery-proof.png"), full_page=True)
            except Exception as error:
                # Browser exceptions can include entered passwords and link tokens.
                page.screenshot(path=str(self.root / "flow-failure.png"), full_page=True)
                print({"stage": stage, "callback_count": len(callbacks), "location": urlsplit(page.url)._replace(query="", fragment="").geturl()}, flush=True)
                raise RuntimeError("Signup qualification failed at " + stage + ": " + type(error).__name__) from None
            finally:
                browser.close()

        fresh_api_token = grant(replacement)["access_token"]

        async def deny_account_credentials():
            self.assertGreater(console_claims["exp"], time.time(), "Denial must not rely on expiry")
            settings = Settings(_env_file=None, environment="test", auth_provider="flow",
                flow_auth_local_hmac_secret=None, token_issuer=self.origin + "/realms/flow",
                token_audience="workstream-api", token_algorithms="RS256",
                token_jwks_url=self.origin + "/realms/flow/protocol/openid-connect/certs",
                token_clock_skew_seconds=0, token_introspection_mode="disabled",
                token_introspection_disabled_reason="Account audience isolation proof")
            verifier = FlowAuthVerifier(settings, jwks_client_factory=partial(httpx.AsyncClient, verify=self.context))
            await verifier.verify(fresh_api_token)
            with self.assertRaises(AuthVerificationError) as denied:
                await verifier.verify(console_token)
            self.assertNotIsInstance(denied.exception, AuthVerificationUnavailableError)
            async with httpx.AsyncClient(verify=self.context, trust_env=False, timeout=10) as http:
                provider = KeycloakCredentials(OAuthSettings(self.origin + "/realms/flow",
                    realm_config.MCP_RESOURCE, self.root / "unused"), http, "unused-denied-before-exchange")
                with self.assertRaises(InvalidCredential):
                    await provider.verify(console_token)
        asyncio.run(deny_account_credentials())


if __name__ == "__main__":
    unittest.main()
