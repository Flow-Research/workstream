# External demo identity issuer

This Rust service is a small, independent identity issuer for the Flow demo. It provides real persisted accounts, password verification and signed short-lived tokens. It uses the Flow authentication contract consumed by Workstream; it is not the complete Flow Identity platform. Login and passwords stay in this service. Workstream separately verifies tokens and controls actor admission and project permissions.

## Start here

The deployed demo identity API is `https://identity.flowresearch.tech`.
Workstream's API is `https://workstream.flowresearch.tech/api/v1`, its Swagger UI
is `https://workstream.flowresearch.tech/docs`, and its native bearer MCP endpoint
is `https://workstream.flowresearch.tech/mcp`.
Use your own configured hostnames for another deployment.

This issuer has **four HTTP endpoints**, listed under [API](#api). It has no web
login page, Swagger UI or OpenAPI endpoint: a 404 at `/` or `/docs` on the identity
hostname is expected. Use an HTTPS API client with JSON bodies. Workstream's
Swagger describes Workstream routes, not these separate identity routes.

| Responsibility | Where it is established | What it permits |
| --- | --- | --- |
| First identity administrator | Local issuer `init`, once for a fresh data directory | Create participant login accounts through this issuer |
| First Workstream Access Administrator | Separate local [Workstream bootstrap](../../docs/operations_authorization_service.md#bootstrap-custody), after actor admission | Manage Workstream authority through its supported APIs |
| Participant account | Issuer `POST /admin/accounts` | Change the initial password and obtain a normal access token |
| Project access | Authorized Workstream grant operations | Perform only the granted project actions |

One person may hold both administrator roles, but neither role automatically
confers the other. Account creation does not assign project permissions. In our
existing deployment initialization is already complete; do not rerun `init` or
replace its state to invite someone.

Read [initialize and run](#initialize-and-run) for a fresh installation,
[API](#api) for the complete wire contract, and
[onboard a participant](#onboard-a-participant) for daily administration.

## Initialize and run

Build with the locked Rust toolchain and dependencies:

```sh
cargo +1.99.1 build --release --locked --manifest-path experiments/demo_identity/Cargo.toml
```

The test accepts `DEMO_IDENTITY_TEST_BINARY` when reusing an external Cargo target directory. For the real HTTPS verifier test, first build the optimized binary used in deployment with `cargo build --release --locked --manifest-path experiments/demo_identity/Cargo.toml`, then run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend python3 -m pytest -q experiments/demo_identity/test_service.py` in an environment with the backend's test dependencies and OpenSSL installed.

Create a new private directory outside the checkout. The local operator's first issuer administrator account is created exclusively at initialization. Give the email as an argument and provide its password from private stdin; it must be 12–1024 bytes. Do not put a password in an argument, environment variable, script, shell history or command log. Initialization refuses an existing directory and never resets accounts or signing keys. A private Docker bind mount for `/data` must be owned by UID 12001 and mode 0700; its SQLite file and signing key must persist across container recreation.

```sh
python3 -c 'import getpass; print(getpass.getpass("Initial administrator password: "))' | \
  experiments/demo_identity/target/release/workstream-demo-identity init /private/demo-identity admin@example.test
```

The process reads one password line from stdin. It creates a 3072-bit RSA key and SQLite account database. Generate and mount a real TLS certificate and key for the exact issuer DNS hostname. Keep TLS and JWT signing keys separate in custody. `serve` refuses missing, unsafe or unupgraded state. Fresh initialization writes schema version 1. Before using a retained pre-rotation database, stop the issuer, back up the private directory securely, and run `workstream-demo-identity upgrade DATA_DIR` with the new binary. The explicit SQLite transaction preserves all subjects, password hashes and signing material and marks every retained non-admin account for first-login rotation once. Repeated upgrades or restarts do not mark completed rotations pending again. Bootstrap administrators retain their locally chosen passwords. Do not run an older binary against upgraded state. Existing access tokens remain valid until their short expiry: before reopening participant access after upgrade, wait at least the 15-minute access lifetime plus the backend configured clock skew after stopping the old issuer. Configure `DEMO_IDENTITY_ISSUER` as the canonical HTTPS origin, `DEMO_IDENTITY_AUDIENCE` as the Workstream audience, and the TLS certificate/key paths. For local runs, `DEMO_IDENTITY_BIND` defaults to `127.0.0.1:8443`.

The optional [hosted Compose overlay](../../deploy/hosted/compose.demo-identity.yml) extends the base hosted Compose file. It uses a separately built, digest-qualified `DEMO_IDENTITY_IMAGE`, mounts private persistent state and TLS files, and uses a read-only root filesystem with non-root UID. Build the image from the included Dockerfile in a controlled release process. Configure the optional issuer fields in `deploy/hosted/release.env.example`; the canonical hosted wrapper selects and validates the overlay. The issuer joins a dedicated bridge with no backend services attached, and its published port is restricted to loopback. External users connect through the separately configured HTTPS ingress. Before switching Workstream, prove the deployed issuer independently and preserve all existing actor identity links and contribution records. Pin the backend issuer, JWKS URL and RS256 audience to the chosen issuer. New accounts receive new subjects; an existing actor requires an explicitly authorized identity link, never an email-based remapping. The existing verifier has `trust_env=False`, so merely setting `SSL_CERT_FILE` is not enough for a private CA; a publicly trusted certificate avoids that exception.

### Runtime configuration

For a direct binary invocation, configure these values before running
`workstream-demo-identity serve DATA_DIR`:

| Variable | Required value |
| --- | --- |
| `DEMO_IDENTITY_ISSUER` | Exact HTTPS origin, for example `https://identity.flowresearch.tech`; match Workstream's configured issuer |
| `DEMO_IDENTITY_AUDIENCE` | Exact Workstream token audience, for example `workstream` |
| `DEMO_IDENTITY_TLS_CERT` | Path to the issuer's PEM TLS certificate |
| `DEMO_IDENTITY_TLS_KEY` | Path to its separate private PEM TLS key, with restricted file permissions |
| `DEMO_IDENTITY_BIND` | Optional listener; direct-binary default `127.0.0.1:8443` |

For the hosted Compose deployment, use the issuer section of
[`release.env.example`](../../deploy/hosted/release.env.example) instead. Its
`DEMO_IDENTITY_TLS_CERT_FILE` and `DEMO_IDENTITY_TLS_KEY_FILE` are **host paths**;
the overlay maps them to the binary's in-container paths. Set the digest-pinned
`DEMO_IDENTITY_IMAGE`, persistent `DEMO_IDENTITY_DATA_DIR` and exact hostname too.
Keep the container listener reachable through its private network/loopback
publication, not a public port. Follow the
[ordered host installation](../../deploy/hosted/SINGLE_HOST.md#identity-storage-and-application-activation)
and [public HTTPS configuration](../../deploy/hosted/PUBLIC_ACCESS.md).

The local management commands are `init DATA_DIR ADMIN_EMAIL`,
`upgrade DATA_DIR`, and `serve DATA_DIR`. `init` is only for fresh state;
`upgrade` is the explicit retained-state migration; `serve` neither initializes
nor silently upgrades. Preserve `accounts.db` and `signer.pem` together across
restarts. Never invoke `init` to create an additional participant.

## API

Send requests to the **identity origin**, without `/api/v1`.
All POSTs require `Content-Type: application/json`. Send bearer credentials in
`Authorization: Bearer <token>` only where required. Success bodies are JSON,
except the empty `204` password-change response. Handler errors use plain-text
messages; do not assume Workstream's error-envelope format here.

| Method and path | Credential | JSON request | Success |
| --- | --- | --- | --- |
| `POST /login` | Email and password in the body; no bearer required | `{"email":"person@example.org","password":"<password>"}` | `200`; one of the login responses below |
| `POST /admin/accounts` | Identity `admin_token` | `{"email":"person@example.org","password":"<initial-password>"}` | `201`, `{"subject":"<new-subject>"}`; account requires password change |
| `POST /me/password` | Pending account: `password_change_token`; completed account: normal `access_token` | `{"current_password":"<current-password>","new_password":"<different-password>"}` | `204`, no body; log in separately afterward |
| `GET /jwks.json` | None | None | `200`, `{"keys":[...]}` containing public RSA verification material only |

### Login responses and token selection

First participant login returns exactly the restricted response shape:

```json
{
  "password_change_token": "<restricted-token>",
  "must_change_password": true,
  "token_type": "Bearer",
  "expires_in": 300
}
```

There is **no** `access_token` or `admin_token` in this response. Use the token
only for `/me/password`; it cannot call Workstream or create accounts. If it
expires before the password change, log in again with the current password.

After password change, normal login returns:

```json
{
  "access_token": "<workstream-token>",
  "must_change_password": false,
  "token_type": "Bearer",
  "expires_in": 900
}
```

An identity administrator's login has this same normal shape **plus**
`"admin_token": "<identity-administration-token>"`. That separate token expires
in **600 seconds**; the response's `expires_in: 900` describes the access token,
not the admin token. Use `admin_token` for `/admin/accounts` and `access_token`
for Workstream. Obtain fresh tokens by logging in again; there is no refresh API.

### Input requirements and failures

- JSON bodies are limited to 4 KiB. Passwords must be **12–1024 UTF-8 bytes**;
  the new password must differ from the current one.
- Email identifiers are trimmed and ASCII-lowercased, with basic format/length
  checks. This is not mailbox verification. Accounts have a generated stable
  subject; callers cannot select their subject or token claims.
- `401 invalid credentials`: invalid login, missing/wrong/expired bearer,
  incorrect current password, unchanged password, consumed rotation token or
  a losing concurrent password change. A generic login error does not establish
  whether an account exists.
- `400 invalid account input`: invalid account-creation email/password.
- `409 account unavailable`: account creation could not insert the account,
  including an existing normalized email. Do not assume a lost creation response
  means the account was not created; there is no list/search or idempotent-create
  API in this issuer.
- `429 try later`: rate or concurrent password-hashing capacity limit. Wait
  rather than repeatedly issuing requests.
- JSON parsing/content-type failures, oversized requests and service failures
  can return other non-success HTTP statuses. Do not treat them as issued tokens
  or a successful account/password change.

### Onboard a participant

1. **Administrator login:** `POST /login` with the existing identity administrator's
   email/password. Keep the returned `admin_token` private.
2. **Create the account:** `POST /admin/accounts` with that admin bearer and the
   participant's email/initial password. Retain the returned subject for identity
   traceability; it is not a Workstream actor ID.
3. **Deliver initial credentials privately:** share the identity URL, email and
   initial password with that participant. No email is sent automatically.
4. **Participant first login:** `POST /login` with the initial credentials, then
   `POST /me/password` using the returned password-change bearer, the current
   password and a different chosen password. A successful change returns `204`.
5. **Normal login:** repeat `POST /login` with the chosen password. Use its
   `access_token` with Workstream API, CLI, Swagger or native bearer MCP.
6. **Workstream admission and grants:** call Workstream's `GET /api/v1/actors/me`
   with the access token. An authorized Workstream administrator then grants the
   required roles/scope through the supported APIs. Follow
   [provisioning and revocation](../../docs/operations_roles_permissions.md#provisioning-and-revocation).
   Identity account creation alone does not permit claiming project tasks.

For the very first Workstream administrator only, the restricted deployment
operator runs the separate [bootstrap procedure](../../docs/operations_authorization_service.md#bootstrap-custody)
against the admitted actor UUID, first `--dry-run`, then `--execute`. Normal
participant onboarding does not rerun either bootstrap.

Keep passwords and complete token responses in a private credential store or
private API-client session. Do not put them in URLs, command-line arguments,
shell history, shared client exports or logs. Examples above contain placeholders,
not usable credentials. Ordinary later password changes use `/me/password` with
the normal access token and current password; the subject remains unchanged.

### Available operations and limits

There is no public signup, account-list/search, email invitation delivery,
forgot-password/reset, additional-admin creation, refresh-token, logout/revocation,
introspection, OAuth or browser-session API. A forgotten password cannot be
recovered through `/me/password` without the current password; contact the
operator. Do not reinitialize the issuer, edit account rows or create replacement
identities as a documented recovery procedure. Such recovery is not implemented.

The access token has fixed `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`, `jti`, `email`, `subject_kind=human` and `scope=workstream:access` claims. The signed `email` comes from the stored canonical account record, with the same stable subject. It is issuer-owned account metadata, not proof of mailbox ownership; the issuer makes no `email_verified` assertion. Admin and first-login password-change tokens omit email. The caller cannot choose claims or a subject. Issuer administrator status is held in the issuer database and never appears in the Workstream token. Workstream still grants project and system authority through its own actor and authorization records. Admin, first-login password-change and access JWTs cannot substitute for each other because their audiences and purposes differ.

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
or the issuer's JWT signing key between services. The explicitly trusted private
ingress phase below may share the same-host TLS identity only. Monitor the private upstream
certificate's expiry and replace it before expiry, then recreate only the issuer
and restart Caddy after configuration validation. Neither action recreates
`/data`. Back up private account/signing state with encryption and restrict
backup access. Never silently initialize new identities after losing state.

DNS and a public certificate are needed for public participant access. An
authorized private deployment may switch the active API using the verified
private ingress below. Earlier isolated verifier tests remain distinct evidence
and do not by themselves prove that active deployment switched. Never
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
For automatic public TLS, Caddy receives the issuer's public upstream
certificate and manages its own frontend key. It never receives the JWT signing
key or account database. Validate the unit and configuration before enabling it.
Keep TCP 80/443 reachable for certificate issuance and HTTPS; port 8443 stays
loopback-only. Wait for DNS before starting automatic certificate issuance.

After the authorized replacement login and Workstream authorization path passes, retire the
previous fixture issuer and remove its signing keys and saved tokens. Test old
token rejection and obtain future credentials through login. Retain existing
actor history and contribution facts; changing authentication does not transfer
old work or grants to a new account.

### Private access before public DNS

The opt-in overlay maps only the API's configured issuer hostname to the Docker
host gateway. Keep that exact hostname and HTTPS issuer/JWKS origin; Caddy serves
443 on the same host and verifies the loopback issuer on 8443. The issuer network
remains isolated from backend membership. The preflight rejects missing or
substituted hostname mappings.

For an operator-authorized private deployment, configure the installed Caddy
site with an explicit certificate and key for that hostname, and disable automatic
HTTPS provisioning until public DNS is available. This same-host private phase
may copy the issuer TLS certificate and TLS key into an ingress-owned directory
with mode 0700 and files with mode 0400; the JWT signing key and account database
remain exclusive to the issuer. Public Caddy automation uses a separate frontend
key when enabled. Qualify the backend image from
its clean base with the private certificate added to its trust bundle, retaining
normal public roots and removing the retired fixture CA. Do not disable hostname
or certificate verification. Record image and deployment-configuration provenance
separately, and repeat the existing release/AWS proof after changing either.
This supplies trusted private access; it does not establish public trust for
participants. Public DNS permits replacement with Caddy-managed certificates.
