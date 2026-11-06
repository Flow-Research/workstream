"""Prove the shipped issuer overlay serves real HTTPS on its loopback port."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy/hosted/compose.demo-identity.yml"
IMAGE = os.environ.get("DEMO_IDENTITY_TEST_IMAGE", "workstream-demo-identity:ci")


def command(args, *, data=None, env=None, timeout=90):
    result = subprocess.run(args, input=data, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Neither stdin credentials nor response tokens belong in command logs.
        raise AssertionError(f"command failed ({result.returncode}): {args[0]}")
    return result.stdout


class IssuerContainerProof(unittest.TestCase):
    def test_real_image_loopback_https_and_persistent_account(self):
        project = "identity-proof-" + secrets.token_hex(6)
        password = secrets.token_urlsafe(32)
        with tempfile.TemporaryDirectory(prefix="issuer-container-") as temporary:
            root = Path(temporary)
            state = root / "state"
            state.mkdir()
            cert, key = root / "cert.pem", root / "key.pem"
            command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                     "-subj", "/CN=identity.example.test", "-addext",
                     "subjectAltName=DNS:identity.example.test,IP:127.0.0.1",
                     "-keyout", str(key), "-out", str(cert)])
            cert.chmod(0o444)
            key.chmod(0o400)
            # The image is built in this job. Only acquisition differs from
            # deployment: no registry pull; service/security/network stay exact.
            acquisition = root / "acquisition.json"
            acquisition.write_text(json.dumps({"services": {"demo-identity": {"pull_policy": "never"}}}))
            env = {**os.environ, "DEMO_IDENTITY_IMAGE": IMAGE,
                   "DEMO_IDENTITY_ISSUER": "https://identity.example.test",
                   "DEMO_IDENTITY_AUDIENCE": "workstream-demo",
                   "DEMO_IDENTITY_HOSTNAME": "identity.example.test",
                   "DEMO_IDENTITY_DATA_DIR": str(state / "accounts"),
                   "DEMO_IDENTITY_TLS_CERT_FILE": str(cert),
                   "DEMO_IDENTITY_TLS_KEY_FILE": str(key),
                   "DEMO_IDENTITY_PUBLISHED_BIND": "127.0.0.1",
                   "DEMO_IDENTITY_PUBLISHED_PORT": "8443"}
            compose = ["docker", "compose", "--project-name", project, "--file", str(OVERLAY), "--file", str(acquisition)]
            owner = ["docker", "run", "--rm", "--network", "none", "--user", "0:0", "--entrypoint", "chown",
                     "--mount", f"type=bind,src={root},dst=/proof", IMAGE]
            try:
                command([*owner, "12001:12001", "/proof/state", "/proof/key.pem"])
                command(["docker", "run", "--rm", "--interactive", "--network", "none", "--read-only",
                         "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                         "--mount", f"type=bind,src={state},dst=/state", IMAGE,
                         "init", "/state/accounts", "admin@example.test"], data=password + "\n")
                command([*compose, "up", "--detach", "--wait", "--wait-timeout", "45"], env=env)
                context = ssl.create_default_context(cafile=str(cert))

                def request(path, body=None):
                    client = http.client.HTTPSConnection("127.0.0.1", 8443, context=context, timeout=10)
                    try:
                        client.request("GET" if body is None else "POST", path,
                                       None if body is None else json.dumps(body),
                                       {"Content-Type": "application/json"})
                        response = client.getresponse()
                        return response.status, response.read(16384)
                    finally:
                        client.close()

                status, jwks = request("/jwks.json")
                self.assertEqual(status, 200)
                self.assertEqual(len(json.loads(jwks)["keys"]), 1)
                status, body = request("/login", {"email": "admin@example.test", "password": password})
                self.assertEqual(status, 200)
                self.assertIn("admin_token", json.loads(body))
                command([*compose, "up", "--detach", "--force-recreate", "--wait", "--wait-timeout", "45"], env=env)
                self.assertEqual(request("/jwks.json"), (200, jwks))
                self.assertEqual(request("/login", {"email": "admin@example.test", "password": password})[0], 200)
            finally:
                try:
                    command([*compose, "down", "--timeout", "10"], env=env)
                finally:
                    # Only this fixture's private directory is restored for
                    # deletion; never remove a deployment volume or shared state.
                    command([*owner, "-R", f"{os.getuid()}:{os.getgid()}", "/proof"])


if __name__ == "__main__":
    unittest.main()
