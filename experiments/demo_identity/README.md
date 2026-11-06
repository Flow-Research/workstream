# External demo identity issuer

This Rust service is a small, independent identity issuer for the Flow demo. It provides real persisted accounts, password verification and signed short-lived tokens. It uses the Flow authentication contract consumed by Workstream; it is not the complete Flow Identity platform. Login and passwords stay in this service. Workstream separately verifies tokens and controls actor admission and project permissions.

## Initialize and run

Build with the locked Rust toolchain and dependencies:

```sh
cargo +1.99.1 build --release --locked --manifest-path experiments/demo_identity/Cargo.toml
```

For the real HTTPS verifier test, first build the debug binary with `cargo build --locked --manifest-path experiments/demo_identity/Cargo.toml`, then run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend python3 -m pytest -q experiments/demo_identity/test_service.py` in an environment with the backend's test dependencies and OpenSSL installed.

Create a new private directory outside the checkout. The local operator's first issuer administrator account is created exclusively at initialization. Give the email as an argument and provide its password from private stdin; it must be 12–1024 bytes. Do not put a password in an argument, environment variable, script, shell history or command log. Initialization refuses an existing directory and never resets accounts or signing keys. A private Docker bind mount for `/data` must be owned by UID 12001 and mode 0700; its SQLite file and signing key must persist across container recreation.

```sh
experiments/demo_identity/target/release/workstream-demo-identity init /private/demo-identity admin@example.test
```

The process reads one password line from stdin. It creates a 3072-bit RSA key and SQLite account database. Generate and mount a real TLS certificate and key for the exact issuer DNS hostname. Keep TLS and JWT signing keys separate in custody. `serve` refuses missing or unsafe state. Configure `DEMO_IDENTITY_ISSUER` as the canonical HTTPS origin, `DEMO_IDENTITY_AUDIENCE` as the Workstream audience, and the TLS certificate/key paths. For local runs, `DEMO_IDENTITY_BIND` defaults to `127.0.0.1:8443`.

The optional [hosted Compose overlay](../../deploy/hosted/compose.demo-identity.yml) extends the base hosted Compose file. It uses a separately built, digest-qualified `DEMO_IDENTITY_IMAGE`, mounts private persistent state and TLS files, and uses a read-only root filesystem with non-root UID. Build the image from the included Dockerfile in a controlled release process. Configure the optional issuer fields in `deploy/hosted/release.env.example`; the canonical hosted wrapper selects and validates the overlay. The issuer joins a dedicated bridge with no backend services attached, and its published port is restricted to loopback. External users connect through the separately configured HTTPS ingress. Before switching Workstream, prove the deployed issuer independently and preserve all existing actor identity links and contribution records. Pin the backend issuer, JWKS URL and RS256 audience to the chosen issuer. New accounts receive new subjects; an existing actor requires an explicitly authorized identity link, never an email-based remapping. The existing verifier has `trust_env=False`, so merely setting `SSL_CERT_FILE` is not enough for a private CA; a publicly trusted certificate avoids that exception.

## API

All endpoints require HTTPS. Request bodies are limited to 4 KiB and passwords to 1024 bytes. `POST /login` takes JSON `{"email":"...","password":"..."}` and returns a 15-minute Workstream access token. An issuer administrator also receives a separate 10-minute `admin_token` with a distinct audience and `issuer_admin` purpose. `POST /admin/accounts` takes the same JSON and requires `Authorization: Bearer <admin_token>`; it creates a normal user with a random stable subject and rejects an existing normalized email. There is no public signup or admin creation endpoint. `POST /me/password` requires a Workstream access token and JSON `{"current_password":"...","new_password":"..."}`. `GET /jwks.json` exposes only the public RSA key. Account email is a login identifier, not evidence that the mailbox was verified.

For participants after the verified deployment cutover:

1. The issuer operator runs `init` once and enters the administrator password on stdin.
2. The administrator sends their email/password to `POST /login`, then uses the returned `admin_token` to call `POST /admin/accounts` with the participant's email and initial password.
3. The participant sends that email/password to `POST /login` and receives `access_token` for Workstream CLI, MCP or API calls. They can use it with their current password at `POST /me/password` to replace the initial password.

Send credentials only in HTTPS JSON bodies and bearer tokens only in Authorization headers. Keep request/response files private; do not place passwords or tokens in command arguments, URLs, logs, or shell history. Provisioning an account gives no Workstream project or administrator grant.

The access token has fixed `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`, `jti`, `subject_kind=human` and `scope=workstream:access` claims. The caller cannot choose claims or a subject. Issuer administrator status is held in the issuer database and never appears in the Workstream token. Workstream still grants project and system authority through its own actor and authorization records. Admin and access JWTs cannot substitute for each other because their audiences and purposes differ.

The service uses Argon2 with a random salt for each password, generic login errors, bounded per-account rate buckets with a global overload ceiling, and a four-operation hashing limit. It is a single-instance demo service; its in-memory rate limits reset on restart. The issuer does not trust forwarded IP headers or apply a shared proxy-peer login bucket. The test deployment relies on these account/global bounds; Caddy adds request-size, connection and timeout bounds, not a per-client rate-limit plugin. Password changes do not revoke previously issued JWTs; tokens remain valid until their short expiry. There is no refresh or introspection endpoint. Set `WORKSTREAM_TOKEN_INTROSPECTION_MODE=disabled` with a documented validity-until-expiry reason if this issuer is selected. Do not log request bodies, Authorization headers, passwords or tokens.

## Hosted HTTPS and cutover

Use a dedicated hostname, such as `identity.flowresearch.tech`, with an A record
pointing to the deployment host. Keep the root website's DNS record unchanged.
The canonical issuer is the HTTPS origin without a trailing slash; its JWKS URL
is that origin plus `/jwks.json`. Keep the audience identical to Workstream's
configured token audience.

The issuer itself publishes only loopback port 8443. Its dedicated bridge is
not Docker `internal`: that mode suppresses the host port on the qualified
host. No backend service joins the bridge and no public issuer port is allowed. The supplied
[Caddy configuration](../../deploy/hosted/demo-identity.Caddyfile) exposes only
the four supported paths. Caddy obtains and renews the public certificate
automatically once DNS and ports 80/443 are configured. Keep Caddy's certificate
data persistent and private. Its administrator API is disabled; request access
logging is not enabled.

Caddy verifies the issuer's private HTTPS certificate using an explicit local
trust file and server name. Generate a separate private TLS key/certificate for
the issuer hostname, keep the key owned by UID 12001 with mode 0400, and give
Caddy only the public certificate. Do not copy Caddy's public-site private keys
or the issuer's JWT signing key between services. Monitor the private upstream
certificate's expiry and replace it before expiry, then recreate only the issuer
and restart Caddy after configuration validation. Neither action recreates
`/data`. Back up private account/signing state with encryption and restrict
backup access. Never silently initialize new identities after losing state.

DNS and the public certificate are needed for participant access and the live
Workstream issuer switch. Private-host compatibility tests may use an explicitly
trusted private certificate with the existing verifier's client-factory seam;
that is separate evidence, not public TLS or active Workstream API proof. Never
use `verify=False`, insecure curl flags, or unverified JWT decoding for access.

The supplied [Caddy host unit](../../deploy/hosted/demo-identity-caddy.service)
runs as `workstream-identity-ingress`, with only the bind-service capability,
256 MiB memory and a finite restart rate. Install the reviewed Caddy binary at
`/usr/local/libexec/workstream-identity-ingress/caddy` and the configuration at
`/etc/workstream-identity-ingress/Caddyfile`. The unit's root-owned `ingress.env`
contains `DEMO_IDENTITY_HOSTNAME`, `DEMO_IDENTITY_UPSTREAM_CERT`,
`XDG_DATA_HOME=/var/lib/workstream-identity-ingress/data` and
`XDG_CONFIG_HOME=/var/lib/workstream-identity-ingress/config`; none is a secret.
Create the state directory with that service user's ownership and mode 0700.
Caddy receives the issuer's public certificate, never its private keys or
account database. Validate the unit and configuration before enabling it.
Keep TCP 80/443 reachable for certificate issuance and HTTPS; port 8443 stays
loopback-only. Wait for DNS before starting automatic certificate issuance.

After the new public login and Workstream authorization path passes, retire the
previous fixture issuer and remove its signing keys and saved tokens. Test old
token rejection and obtain future credentials through login. Retain existing
actor history and contribution facts; changing authentication does not transfer
old work or grants to a new account.
