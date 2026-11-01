"""Isolated drill issuer: offline minting and static HTTPS JWKS, never product auth."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import ssl
import stat
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ISSUER = "https://flow-drill.test:8443"
AUDIENCE = "workstream-drill"
IDENTITIES = (
    "access-admin",
    "manager",
    "finance",
    "operator",
    "contributor",
    "foreign-contributor",
)
LIFETIME_SECONDS = 900
REASON = "isolated simulated issuer drill; short-lived tokens; no revocation proof"


def read_private(path: Path) -> bytes:
    """Refuse links, devices and files accessible by another account."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
            or info.st_size > 65536
        ):
            raise ValueError("unsafe fixture file")
        return stream.read(65537)


def write_private(path: Path, data: bytes) -> None:
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or parent.st_mode & 0o077
    ):
        raise ValueError("output directory must be private and owned")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def pem_key(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def initialize(directory: Path) -> None:
    directory.mkdir(
        mode=0o700
    )  # Exclusive: never rotate an existing issuer implicitly.
    signer = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = signer.public_key()
    kid = hashlib.sha256(
        public.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    ).hexdigest()
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public, as_dict=True)
    jwk.update(kid=kid, use="sig", key_ops=["verify"], alg="RS256")
    write_private(directory / "signer.pem", pem_key(signer))
    write_private(directory / "jwks.json", json.dumps({"keys": [jwk]}).encode())
    write_private(
        directory / "subjects.json",
        json.dumps({name: str(uuid4()) for name in IDENTITIES}).encode(),
    )
    _write_transport(directory)


def initialize_transport(directory: Path) -> None:
    """Create independent TLS files without reading or changing issuer identity."""
    directory.mkdir(mode=0o700)
    _write_transport(directory)


def _write_transport(directory: Path) -> None:
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    now = datetime.now(UTC)
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Workstream isolated drill CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "flow-drill.test")])
        )
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("flow-drill.test"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    # The CA signer is not retained; renew transport explicitly in a new directory.
    write_private(directory / "ca.pem", ca.public_bytes(serialization.Encoding.PEM))
    write_private(directory / "tls.pem", leaf.public_bytes(serialization.Encoding.PEM))
    write_private(directory / "tls-key.pem", pem_key(leaf_key))


def mint(directory: Path, identity: str, output: Path) -> None:
    if identity not in IDENTITIES:
        raise ValueError("unknown drill identity")
    subjects = json.loads(read_private(directory / "subjects.json"))
    kid = json.loads(read_private(directory / "jwks.json"))["keys"][0]["kid"]
    now = int(time.time())
    claims = dict(
        iss=ISSUER,
        sub=subjects[identity],
        aud=AUDIENCE,
        iat=now,
        nbf=now,
        exp=now + LIFETIME_SECONDS,
        jti=str(uuid4()),
        subject_kind="human",
        scope="workstream:access",
    )
    token = jwt.encode(
        claims,
        read_private(directory / "signer.pem"),
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )
    write_private(output, token.encode())


def make_server(
    jwks: Path, certificate: Path, key: Path, bind: str, port: int
) -> HTTPServer:
    document = json.loads(read_private(jwks))
    # Reconstruct public fields: a mistakenly supplied private JWK must never be exported.
    keys = document["keys"]
    allowed = {"kty", "kid", "use", "key_ops", "alg", "n", "e"}
    if len(keys) != 1 or set(keys[0]) != allowed or keys[0]["kty"] != "RSA":
        raise ValueError("expected one public RSA key")
    payload = json.dumps(document).encode()
    read_private(certificate)
    read_private(key)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, key)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log request content or headers.

        def send_error(self, code, message=None, explain=None):
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

        def do_GET(self):
            if self.path != "/jwks.json":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    class Server(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(3)
            try:
                return context.wrap_socket(connection, server_side=True), address
            except BaseException:
                connection.close()
                raise

        def handle_error(self, request, client_address):
            pass  # No request or secret-bearing exception dumps.

    return Server((bind, port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--directory", type=Path, required=True)
    transport = commands.add_parser("init-transport")
    transport.add_argument("--directory", type=Path, required=True)
    issue = commands.add_parser("mint")
    issue.add_argument("--directory", type=Path, required=True)
    issue.add_argument("--identity", choices=IDENTITIES, required=True)
    issue.add_argument("--output", type=Path, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--jwks", type=Path, required=True)
    serve.add_argument("--certificate", type=Path, required=True)
    serve.add_argument("--key", type=Path, required=True)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.directory)
        elif args.command == "init-transport":
            initialize_transport(args.directory)
        elif args.command == "mint":
            mint(args.directory, args.identity, args.output)
        else:
            with make_server(
                args.jwks, args.certificate, args.key, args.bind, args.port
            ) as server:
                server.serve_forever()
    except (OSError, ValueError, KeyError, TypeError, jwt.PyJWTError):
        parser.exit(
            1,
            "Drill fixture failed; inspect private inputs without exposing their contents.\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
