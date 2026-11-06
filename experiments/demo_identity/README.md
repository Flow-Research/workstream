# External demo identity issuer

This Rust service is a small, independent identity issuer for the Flow demo. It provides real persisted accounts, password verification and signed short-lived tokens. It uses the Flow authentication contract consumed by Workstream; it is not the complete Flow Identity platform. Login and passwords stay in this service. Workstream separately verifies tokens and controls actor admission and project permissions.

## Initialize and run

Build with the locked Rust toolchain and dependencies:

```sh
cargo build --release --locked --manifest-path experiments/demo_identity/Cargo.toml
```

For the real HTTPS verifier test, first build the debug binary with `cargo build --locked --manifest-path experiments/demo_identity/Cargo.toml`, then run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend python3 -m pytest -q experiments/demo_identity/test_service.py` in an environment with the backend's test dependencies and OpenSSL installed.

Create a new private directory outside the checkout. The local operator's first issuer administrator account is created exclusively at initialization. Give the email as an argument and provide its password from private stdin; it must be 12–1024 bytes. Do not put a password in an argument, environment variable, script, shell history or command log. Initialization refuses an existing directory and never resets accounts or signing keys. A private Docker bind mount for `/data` must be owned by UID 12001 and mode 0700; its SQLite file and signing key must persist across container recreation.

```sh
experiments/demo_identity/target/release/workstream-demo-identity init /private/demo-identity admin@example.test
```

The process reads one password line from stdin. It creates a 3072-bit RSA key and SQLite account database. Generate and mount a real TLS certificate and key for the exact issuer DNS hostname. Keep TLS and JWT signing keys separate in custody. `serve` refuses missing or unsafe state. Configure `DEMO_IDENTITY_ISSUER` as the canonical HTTPS origin, `DEMO_IDENTITY_AUDIENCE` as the Workstream audience, and the TLS certificate/key paths. For local runs, `DEMO_IDENTITY_BIND` defaults to `127.0.0.1:8443`.

The optional [hosted Compose overlay](../../deploy/hosted/compose.demo-identity.yml) extends the base hosted Compose file. It uses a separately built, digest-qualified `DEMO_IDENTITY_IMAGE`, mounts private persistent state and TLS files, and uses a read-only root filesystem with non-root UID. Build the image from the included Dockerfile in a controlled release process. Configure the optional issuer fields in `deploy/hosted/release.env.example`; the canonical hosted wrapper selects and validates the overlay. The issuer joins a dedicated internal network shared only with the API, and its published port defaults to loopback. Setting a public bind for external users requires separately reviewed DNS, TLS, firewall and deployment configuration. Before switching Workstream, prove the deployed issuer independently and preserve all existing actor identity links and contribution records. Pin the backend issuer, JWKS URL and RS256 audience to the chosen issuer. New accounts receive new subjects; an existing actor requires an explicitly authorized identity link, never an email-based remapping. The existing verifier has `trust_env=False`, so merely setting `SSL_CERT_FILE` is not enough for a private CA; a publicly trusted certificate avoids that exception.

## API

All endpoints require HTTPS. Request bodies are limited to 4 KiB and passwords to 1024 bytes. `POST /login` takes JSON `{"email":"...","password":"..."}` and returns a 15-minute Workstream access token. An issuer administrator also receives a separate 10-minute `admin_token` with a distinct audience and `issuer_admin` purpose. `POST /admin/accounts` takes the same JSON and requires `Authorization: Bearer <admin_token>`; it creates a normal user with a random stable subject and rejects an existing normalized email. There is no public signup or admin creation endpoint. `POST /me/password` requires a Workstream access token and JSON `{"current_password":"...","new_password":"..."}`. `GET /jwks.json` exposes only the public RSA key. Account email is a login identifier, not evidence that the mailbox was verified.

For participants after the verified deployment cutover:

1. The issuer operator runs `init` once and enters the administrator password on stdin.
2. The administrator sends their email/password to `POST /login`, then uses the returned `admin_token` to call `POST /admin/accounts` with the participant's email and initial password.
3. The participant sends that email/password to `POST /login` and receives `access_token` for Workstream CLI, MCP or API calls. They can use it with their current password at `POST /me/password` to replace the initial password.

Send credentials only in HTTPS JSON bodies and bearer tokens only in Authorization headers. Keep request/response files private; do not place passwords or tokens in command arguments, URLs, logs, or shell history. Provisioning an account gives no Workstream project or administrator grant.

The access token has fixed `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`, `jti`, `subject_kind=human` and `scope=workstream:access` claims. The caller cannot choose claims or a subject. Issuer administrator status is held in the issuer database and never appears in the Workstream token. Workstream still grants project and system authority through its own actor and authorization records. Admin and access JWTs cannot substitute for each other because their audiences and purposes differ.

The service uses Argon2 with a random salt for each password, generic login errors, bounded per-source/account rate buckets with a global overload ceiling, and a four-operation hashing limit. It is a single-instance demo service; its in-memory rate limits reset on restart. A future reverse proxy must preserve the intended source-IP throttle semantics. Place an ingress rate limit ahead of any public deployment. Password changes do not revoke previously issued JWTs; tokens remain valid until their short expiry. There is no refresh or introspection endpoint. Set `WORKSTREAM_TOKEN_INTROSPECTION_MODE=disabled` with a documented validity-until-expiry reason if this issuer is selected. Do not log request bodies, Authorization headers, passwords or tokens.

## Hosted HTTPS and cutover

Use a dedicated hostname, such as `identity.flowresearch.tech`, with an A record
pointing to the deployment host. Keep the root website's DNS record unchanged.
The canonical issuer is the HTTPS origin without a trailing slash; its JWKS URL
is that origin plus `/jwks.json`. Keep the audience identical to Workstream's
configured token audience.

The issuer itself publishes only loopback port 8443. The supplied
[NGINX ingress example](../../deploy/hosted/demo-identity.nginx.conf) exposes the
four supported API paths on HTTPS port 443, with request-size, connection,
request-rate and timeout limits. It verifies TLS to the issuer and disables
request logging. Render its hostname and certificate paths for your deployment
and validate it with `nginx -t` before reload. The HTTP listener serves only
ACME challenges; it never accepts passwords. Do not expose the issuer's port
8443 or Workstream's database to the internet.

Issue a publicly trusted certificate for the selected hostname. The ingress
retains its own root-readable key; install the issuer's certificate/key copies
with owner UID 12001 and key mode 0400 in its private TLS directory. Do not mount
the entire ACME state directory into the container. Arrange certificate renewal
to replace the mounted copies, recreate the issuer and reload NGINX after
validation; neither action recreates `/data`. Back up private account/signing
state with encryption and restrict backup access. Losing the signing key or
account database cannot be repaired by silently initializing new identities.

DNS and the trusted certificate are needed for public access and the live
Workstream issuer switch. Private-host compatibility tests may use an explicitly
trusted private certificate with the existing verifier's client-factory seam;
that is separate evidence, not public TLS or active Workstream API proof. Never
use `verify=False`, insecure curl flags, or unverified JWT decoding for access.
