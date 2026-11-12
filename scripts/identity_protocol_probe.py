"""Real-provider test client; HTTP form proof is not a browser or Garden proof.

Only synthetic fixture accounts belong here. This is not participant onboarding,
an OAuth server, or a replacement for Keycloak's login UI.
"""

from __future__ import annotations

import base64
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import json
import secrets
import ssl
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import (
    HTTPCookieProcessor, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener,
)


class ProviderRejected(Exception):
    """Retain only status; provider bodies can include confidential values."""

    def __init__(self, status: int):
        super().__init__(f"identity provider rejected request ({status})")
        self.status = status


class LoginRejected(Exception):
    """The provider returned its login form again after submitted credentials."""


class _Forms(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.forms: list[dict] = []
        self.current: dict | None = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form":
            self.current = {"action": attributes.get("action"), "inputs": {}}
            self.forms.append(self.current)
        if (tag == "input" and self.current is not None and attributes.get("name")
                and attributes.get("type") not in {"submit", "button"}):
            self.current["inputs"][attributes["name"]] = attributes.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class _Callback(Exception):
    def __init__(self, url: str):
        super().__init__("authorization callback captured")
        self.url = url


class _Redirects(HTTPRedirectHandler):
    def __init__(self, origin: str, callback: str | None = None):
        self.origin = origin
        self.callback = callback

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        destination = urlsplit(newurl)
        if self.callback and destination._replace(query="", fragment="").geturl() == self.callback:
            raise _Callback(newurl)
        if destination.scheme + "://" + destination.netloc != self.origin:
            raise RuntimeError("provider attempted an unexpected redirect")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class IdentityProtocolProbe:
    """Bounded HTTPS requests and code/PKCE login against an owned fixture."""

    def __init__(self, origin: str, context: ssl.SSLContext):
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.path
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("fixture origin must be an exact HTTPS origin")
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise ValueError("fixture must verify provider certificate and hostname")
        self.origin = origin
        self.context = context

    def request(self, path: str, data=None, *, token=None, form=False, method=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("provider path must be origin-relative")
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        if data is not None:
            headers["Content-Type"] = (
                "application/x-www-form-urlencoded" if form else "application/json"
            )
            data = (urlencode(data) if form else json.dumps(data)).encode()
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=self.context), _Redirects(self.origin))
        try:
            with opener.open(Request(self.origin + path, data=data, headers=headers,
                                     method=method), timeout=30) as response:
                body = response.read(2 * 1024 * 1024 + 1)
                if len(body) > 2 * 1024 * 1024:
                    raise RuntimeError("fixture response exceeds bound")
                return json.loads(body) if body else None
        except HTTPError as error:
            error.close()
            raise ProviderRejected(error.code) from None

    def login(self, client: str, audience_scope: str, email: str, password: str,
              *, new_password: str | None = None, profile_changes: dict | None = None) -> dict:
        callback = {
            "workstream-cli-login": "http://127.0.0.1:17843/callback",
            "workstream-mcp-proof": "http://127.0.0.1:17844/callback",
        }[client]
        verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = urlencode({
            "client_id": client, "redirect_uri": callback, "response_type": "code",
            "scope": "openid workstream:access " + audience_scope, "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        browser = build_opener(
            ProxyHandler({}), HTTPSHandler(context=self.context),
            HTTPCookieProcessor(http.cookiejar.CookieJar()),
            _Redirects(self.origin, callback),
        )
        url = self.origin + "/realms/flow/protocol/openid-connect/auth?" + query
        data = None
        credentials_submitted = False
        try:
            for _ in range(6):
                with browser.open(Request(url, data=data), timeout=30) as response:
                    html = response.read(1024 * 1024 + 1)
                if len(html) > 1024 * 1024:
                    raise RuntimeError("authentication form exceeds bound")
                forms = _Forms(html.decode()).forms
                if not forms:
                    raise RuntimeError("expected an authentication form")
                fields = forms[0]["inputs"]
                url = urljoin(self.origin, forms[0]["action"])
                if urlsplit(url).netloc != urlsplit(self.origin).netloc or urlsplit(url).scheme != "https":
                    raise RuntimeError("authentication form changed origin")
                if "firstName" in fields and "lastName" in fields:
                    # A rejected malicious update may return the same form.
                    # Submit the hostile fields once, then complete a clean
                    # update so the test can inspect retained profile/claims.
                    fields.pop("workstream_subject_kind", None)
                    fields.pop("user.attributes.workstream_subject_kind", None)
                    fields.update(profile_changes or {})
                    profile_changes = None
                elif "username" in fields:
                    if credentials_submitted:
                        raise LoginRejected("provider rejected fixture login")
                    fields.update(username=email, password=password)
                    credentials_submitted = True
                elif "password-new" in fields and new_password:
                    fields.update({"password-new": new_password, "password-confirm": new_password})
                else:
                    fields["accept"] = "Yes"
                data = urlencode(fields).encode()
        except _Callback as callback_result:
            result = parse_qs(urlsplit(callback_result.url).query)
            if result.get("state") != [state] or len(result.get("code", [])) != 1:
                raise RuntimeError("authorization callback failed validation") from None
            return self.request("/realms/flow/protocol/openid-connect/token", {
                "grant_type": "authorization_code", "client_id": client,
                "redirect_uri": callback, "code_verifier": verifier, "code": result["code"][0],
            }, form=True)
        except HTTPError as error:
            error.close()
            raise ProviderRejected(error.code) from None
        raise RuntimeError("authentication did not finish within its step bound")
