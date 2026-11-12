#!/usr/bin/env python3
"""Obtain a Workstream API credential through Flow Identity's browser OAuth flow.

Passwords are entered only in the provider's browser UI. This standard-library
client stores the returned credentials in a private file, never stdout.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import ssl
import stat
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener
import webbrowser

CLIENT = "workstream-cli-login"
CALLBACK = "http://127.0.0.1:17843/callback"
SCOPES = "openid workstream:access workstream-api-audience"
MAX_RESPONSE = 65536


class LoginError(Exception):
    """A sanitized participant-facing failure."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise LoginError("Identity endpoint redirected; check the configured issuer.")


def issuer_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path != "/realms/flow"
            or any(ord(char) < 33 for char in value)):
        raise LoginError("Use the exact HTTPS Flow realm issuer ending in /realms/flow.")
    return value


def request_json(url: str, context: ssl.SSLContext, data: dict | None = None) -> dict:
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), _NoRedirect())
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urlencode(data).encode()
    try:
        with opener.open(Request(url, data=body, headers=headers), timeout=20) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise LoginError("Identity response exceeds the supported limit.")
            value = json.loads(raw)
    except HTTPError as error:
        error.close()
        raise LoginError(f"Identity request was rejected (HTTP {error.code}); sign in again if renewal expired.") from None
    except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
        raise LoginError("Cannot read a valid response from the trusted identity endpoint.") from None
    if not isinstance(value, dict):
        raise LoginError("Identity returned an invalid response.")
    return value


def endpoints(issuer: str, context: ssl.SSLContext) -> tuple[str, str]:
    metadata = request_json(issuer + "/.well-known/openid-configuration", context)
    authorization = issuer + "/protocol/openid-connect/auth"
    token = issuer + "/protocol/openid-connect/token"
    if (metadata.get("issuer") != issuer or metadata.get("authorization_endpoint") != authorization
            or metadata.get("token_endpoint") != token
            or "S256" not in metadata.get("code_challenge_methods_supported", [])):
        raise LoginError("Discovery does not match the configured issuer and code/PKCE endpoints.")
    return authorization, token


def private_path(path: Path) -> Path:
    path = path.absolute()
    parent = path.parent
    if parent != parent.resolve(strict=True):
        raise LoginError("Credential directory must not contain symbolic links.")
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise LoginError("Create a directory owned by you with mode 0700 for the credential file.")
    return path


def read_credentials(path: Path, issuer: str) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > MAX_RESPONSE):
            raise LoginError("Credentials must be a private, bounded regular file owned by you.")
        value = json.loads(os.read(descriptor, MAX_RESPONSE + 1))
    finally:
        os.close(descriptor)
    if (not isinstance(value, dict) or value.get("issuer") != issuer
            or value.get("client_id") != CLIENT or not isinstance(value.get("refresh_token"), str)
            or not value["refresh_token"]):
        raise LoginError("Saved credentials do not match this issuer/client or cannot be renewed.")
    return value


def save_credentials(path: Path, issuer: str, tokens: dict, *, replace: bool) -> None:
    if (not isinstance(tokens.get("token_type"), str) or tokens["token_type"].lower() != "bearer"
            or not isinstance(tokens.get("access_token"), str) or not tokens["access_token"]
            or not isinstance(tokens.get("refresh_token"), str) or not tokens["refresh_token"]
            or type(tokens.get("expires_in")) is not int or tokens["expires_in"] <= 0):
        raise LoginError("Identity did not return complete usable OAuth credentials.")
    saved = {"issuer": issuer, "client_id": CLIENT, "access_token": tokens["access_token"],
             "refresh_token": tokens["refresh_token"], "token_type": "Bearer",
             "expires_at": int(time.time()) + tokens["expires_in"]}
    payload = (json.dumps(saved) + "\n").encode()
    if len(payload) > MAX_RESPONSE:
        raise LoginError("Saved credentials would exceed their size bound.")
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".identity-", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Exclusive publication of a complete file; never overwrite another
            # login's credentials or expose a partially written JSON document.
            os.link(temporary, path, follow_symlinks=False)
            os.unlink(temporary)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def browser_code(authorization: str, *, launch=webbrowser.open) -> tuple[str, str]:
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    result: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        timeout = 5

        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8)
            except ValueError:
                query = {}
            bound = (len(self.path) <= 8192 and self.headers.get_all("Host") == ["127.0.0.1:17843"]
                     and parsed.path == "/callback" and not parsed.netloc and not parsed.fragment
                     and query.get("state") == [state])
            accepted = bound and len(query.get("code", [])) == 1 and bool(query["code"][0]) and "error" not in query
            denied = bound and len(query.get("error", [])) == 1 and bool(query["error"][0]) and "code" not in query
            valid = accepted or denied
            body = b"Login received. Return to your terminal." if accepted else b"Login was not authorized. Return to your terminal."
            if not valid:
                body = b"Invalid login callback."
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)
            if accepted:
                result["code"] = query["code"][0]
            elif denied:
                result["error"] = "denied"

    with HTTPServer(("127.0.0.1", 17843), Callback) as server:
        server.timeout = 1
        query = urlencode({"client_id": CLIENT, "redirect_uri": CALLBACK, "response_type": "code",
                           "scope": SCOPES, "state": state, "code_challenge": challenge,
                           "code_challenge_method": "S256"})
        url = authorization + "?" + query
        if not launch(url):
            print("Open this authorization URL in a browser on this computer:\n" + url)
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
        if not result:
            raise LoginError("Login timed out. No credentials were saved.")
        if "error" in result:
            raise LoginError("Identity did not authorize this login. No credentials were saved.")
    return result["code"], verifier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", default="https://identity.flowresearch.tech/realms/flow")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--refresh", action="store_true", help="Renew this private credential file")
    args = parser.parse_args()
    try:
        issuer = issuer_url(args.issuer)
        path = private_path(args.output)
        previous = read_credentials(path, issuer) if args.refresh else None
        if not args.refresh and path.exists():
            raise LoginError("Output exists; use --refresh or choose a new private file.")
        context = ssl.create_default_context()
        authorization, token = endpoints(issuer, context)
        if previous:
            form = {"grant_type": "refresh_token", "client_id": CLIENT,
                    "refresh_token": previous["refresh_token"]}
        else:
            code, verifier = browser_code(authorization)
            form = {"grant_type": "authorization_code", "client_id": CLIENT,
                    "redirect_uri": CALLBACK, "code": code, "code_verifier": verifier}
        tokens = request_json(token, context, form)
        save_credentials(path, issuer, tokens, replace=bool(previous))
    except (LoginError, OSError, ValueError, KeyboardInterrupt) as error:
        print(str(error) if isinstance(error, LoginError) else "Login could not finish; no credential values were printed.")
        return 1
    print(f"Credentials saved privately to {path}. Keep this file secret; no password was stored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
