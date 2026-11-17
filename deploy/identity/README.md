# Flow Identity with Keycloak

Keycloak owns accounts, passwords, browser login and OAuth credentials. Workstream
verifies those credentials and independently decides product authority. Being a
Keycloak administrator grants no Workstream role. Email comes from the issuer;
Workstream display names remain locally editable.

The managed provider uses the same PostgreSQL instance as the optional hosted
local-data profile, with a separate database and database role. No account or
signing state lives in the identity container's temporary filesystem. The
runtime image is built from the pinned upstream digest in `Dockerfile`.

## Fresh host configuration

1. Build and publish `deploy/identity/Dockerfile` from the repository root. Set
   `FLOW_IDENTITY_IMAGE` to the published `repository@sha256:...` reference.
2. For a fresh local-data installation, run
   `deploy/hosted/initialize-local-data.py` with `--with-keycloak` in addition to
   its existing required arguments. It refuses existing state. Do not rerun it
   to reset an installed database.
3. Set the `FLOW_IDENTITY_*` paths and hostname in the hosted release environment.
   The database password and upstream TLS files must be regular files owned by
   UID/GID `1000:1000`, mode `0400`. Use a certificate matching the identity
   hostname; Caddy verifies that certificate on its upstream connection.
4. Configure the existing [public Caddy ingress](../hosted/public.Caddyfile).
   `FLOW_IDENTITY_PROXY_ADDRESS` is the one source address actually observed from
   that proxy, not a trusted subnet or arbitrary forwarded header. Public access
   exposes the `flow` realm and login assets. The administration console and master-realm login use the same public HTTPS
   hostname. Keycloak enforces administrator authentication and permissions; health,
   metrics and dynamic client registration are not exposed.
5. Start the local database services using the checked hosted wrapper:

   ```sh
   python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env start local-data
   ```

## First identity administrator

Use Keycloak's stock offline bootstrap, which requires the identity node to be
stopped. Create a separate single-line temporary password file, owned by
`1000:1000`, mode `0400`; do not reuse a database password or put its value in
shell arguments, release configuration or Git.

```sh
python3 deploy/hosted/bootstrap-identity.py \
  --env-file /etc/workstream/release.env \
  --password-file /etc/workstream/identity/bootstrap-password
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env start identity
```

The helper creates `workstream-bootstrap` using the validated image and database
configuration. It refuses a running hosted identity node, publishes no port, and
cleans up its one-off container. Routine identity configuration contains no
bootstrap secret. A failed or repeated bootstrap requires inspection; it does
not reset accounts or choose a different administrator automatically.

Open `https://IDENTITY_HOST/admin/` in your browser (for this deployment,
`https://identity.flowresearch.tech/admin/`). Sign in to the **master** realm.
The console uses the same fixed HTTPS hostname as participant login; no SSH
login or tunnel is required for routine account administration. Keep administrator
passwords private and require MFA for every administrator.

For an existing deployment previously using a private admin origin, authenticate
through that origin before cutover and change only the master realm's
`attributes.frontendUrl` to `https://IDENTITY_HOST`, preserving its other
attributes. Remove the obsolete `KC_HOSTNAME_ADMIN` override and private ingress
listener. Then authenticate again at the public origin: tokens issued under the
old master issuer must not be reused. The flow realm must have no `frontendUrl`
override; its public issuer, participant accounts and OAuth clients do not change.
Never recreate either realm or rerun bootstrap to change this URL.

Establish a named administrator with MFA, verify recovery access, delete the
temporary `workstream-bootstrap` account, and remove its password file. This
does not replace Workstream's independently guarded first Access Administrator
bootstrap. See [Keycloak's bootstrap and recovery documentation](https://www.keycloak.org/server/bootstrap-admin-recovery).

For recovery-code login, enrollment alone is insufficient. In the master
realm's Authentication → Browser flow, set the existing **Recovery Authentication
Code Form** inside **Browser - Conditional 2FA** from Disabled to Alternative.
Leave the password, OTP and conditional checks unchanged. Enroll the named
administrator's recovery codes, store them privately, and prove a fresh recovery
login before removing the bootstrap account. This is Keycloak's
[documented recovery-code configuration](https://www.keycloak.org/docs/latest/server_admin/),
not a change to Workstream roles or the participant realm.

## Realm and clients

Render the sanitized initial realm with:

```sh
python3 deploy/identity/realm_config.py --output /private/operator/flow-realm.json
```

The output contains no users, passwords, client secrets or signing keys. Import
it into a fresh provider through authenticated administration; do not overwrite an
existing realm as a reconciliation shortcut. The `human_profile()` operation
in the same module merges the administrator-only `workstream_subject_kind`
attribute into the stock user profile and makes email required. Apply that
profile before provisioning participants. Export the stock profile from
`GET /admin/realms/flow/users/profile` through authenticated administration, then render
its replacement without discarding other fields:

```sh
python3 deploy/identity/realm_config.py \
  --profile-input /private/operator/stock-profile.json \
  --output /private/operator/flow-profile.json
```

Apply that document with `PUT /admin/realms/flow/users/profile`. Assign `human`
explicitly only to human accounts; a user cannot assign the marker themselves.

## Invite a participant in the browser

1. Open `https://IDENTITY_HOST/admin/` and sign in with your named **master**
   administrator account and MFA. Select **flow** in the realm selector.
2. Choose **Users → Add user**. Set **Username** to their email, enter **Email**
   and their name, and enable the account. Do not mark email verified unless
   its ownership has actually been verified.
3. Set the administrator-only **workstream_subject_kind** attribute to `human`.
   This attribute comes from the user-profile configuration above; participants
   cannot set it themselves. Save the user.
4. Open **Credentials → Set password**, choose a unique initial password and
   leave **Temporary** enabled. Confirm **Update Password** is required.
5. Transfer the username and temporary password privately. No invitation email
   is sent. They connect Workstream in Garden or run `workstream login`
   below, then replace the password on the Flow Identity page before receiving
   usable access credentials.

Keep public registration and participant direct password grants disabled.
Creating an identity grants no Workstream admission or project role. An existing
Workstream Access Administrator must admit the participant and arrange the
required project grants through Workstream's APIs. Keycloak administration is
not Workstream administration.

The direct client requests `workstream:access workstream-api-audience`; its
callback is exactly `http://127.0.0.1:17843/callback`. An inspected Garden client
requests `workstream:access workstream-mcp-audience` with its exact HTTPS callback.
The MCP audience scope is included in the returned scope set. Garden's existing
OAuth client renews that set explicitly; omitting the audience scope from that set
would remove the MCP audiences on refresh. This token setting is independent of consent-page
display: show only the user-facing access permission, keeping the internal MCP
audience scope hidden on that page. The API audience and identity mapper scopes remain
hidden. This does not grant additional Workstream permissions.
The current integration drill uses Garden dev. Render its registration separately:

```sh
python3 deploy/identity/realm_config.py \
  --garden-client-id garden-dev \
  --garden-callback https://garden-dev.flow-research.workers.dev/api/oauth/callback \
  --output /private/operator/garden-client.json
```

Create it through `POST /admin/realms/flow/clients` using authenticated administration.
The Garden dev operator must set `WORKSTREAM_MCP_CLIENT_ID=garden-dev` for the
Workstream connector; generating this document alone does not connect Garden.
Other deployment environments require their own exact client/callback registration.
Do not enable open dynamic registration or give Garden the API audience scope.
The confidential MCP client exchanges an MCP token into a short-lived API token
for the same subject. Its secret is mounted only into MCP through
`WORKSTREAM_MCP_EXCHANGE_SECRET_FILE`; it is not a backend or browser credential.

## Participant CLI and direct API access

Flow Identity issues API credentials as well as MCP credentials. A participant
uses the same invited email/password for both, and completes a mandatory initial
password change on Flow Identity's HTTPS page. Workstream does not accept passwords
or implement a separate login endpoint.

### CLI

Install the Workstream binary, then run:

```sh
workstream login
workstream whoami
```

`login` opens Flow Identity in your browser and uses authorization code with PKCE.
Run it on the computer running that browser; the callback temporarily listens on
`127.0.0.1:17843`. It stores verified access/refresh credentials in your operating
system credential store (macOS Keychain, Windows Credential Manager, or Linux
Secret Service). Unlock that store first. There is no plaintext credential fallback.
Ordinary commands renew the saved session when needed and never print its tokens.
An uncertain refresh requires a fresh login rather than repeating the old refresh.

For an explicit API bearer token:

```sh
workstream auth token
```

This command deliberately prints a secret. Do not paste its output into chat,
logs or source control. API requests use `Authorization: Bearer <access token>`.
Use `workstream logout` to remove the local login and close its refresh session.
Already-issued access tokens remain valid until expiry; logout does not end the
browser's Flow Identity SSO session.

For another deployment use `workstream login --issuer
https://IDENTITY_HOST/realms/flow --api-url https://API_HOST`. Saved credentials are
bound to that exact API origin. An explicit `WORKSTREAM_TOKEN` remains supported
for automation; it takes precedence over saved login. `WORKSTREAM_API_URL` selects
its destination and defaults to the official Workstream API when omitted.

### Direct API, without the CLI

Open `https://workstream.flowresearch.tech/docs`, choose **Authorize**, select
**FlowIdentity**, and sign in with your Flow Identity email/password. Swagger
performs the code/PKCE exchange and attaches the API bearer to **Try it out**
requests. Tokens are not persisted across page reloads. The OAuth callback is
`https://workstream.flowresearch.tech/docs/oauth2-redirect`.

An application calling the API uses the same standard OAuth authorization-code
flow with PKCE. Its operator must register its own public client and exact callback
in the Flow realm, using the API audience scope. Request `openid`,
`workstream:access`, and `workstream-api-audience`; exchange the returned code at
the issuer's token endpoint with its original verifier. Use the returned
`access_token` as the API bearer and the refresh credential only at the issuer.
Do not reuse the Swagger callback for a different client, send passwords to
Workstream, or copy an API-only token into MCP.

Login creates or resolves the Workstream actor; it does not grant admission,
project roles, or administrative authority. Keycloak administration and
Workstream Access Administrator grants are separate.

## First Workstream Access Administrator

After the intended administrator signs in and calls `workstream whoami`, use
their returned actor UUID with the existing guarded bootstrap. This is separate
from Keycloak administration. On the deployment host, replace the qualified
example container `workstream-api-1` with your deployment's API container:

```sh
sudo docker exec workstream-api-1 /usr/local/bin/workstream-release-entrypoint \
  python -m scripts.bootstrap_access_administrator \
  --actor-profile-id '<actor UUID returned by whoami>' --dry-run

sudo docker exec workstream-api-1 /usr/local/bin/workstream-release-entrypoint \
  python -m scripts.bootstrap_access_administrator \
  --actor-profile-id '<actor UUID returned by whoami>' --execute
```

The release entrypoint loads its mounted database secret; a bare `docker exec …
python` does not inherit the running API process's loaded secret environment.
Do not print or copy database credentials to work around this. Bootstrap grants
only Access Administrator, refuses repetition, and does not grant project roles.
Use the normal role-grant APIs afterward. See the
[bootstrap contract and exit codes](../../docs/operations_authorization_service.md).

## Verification scope

`scripts/test_identity_provider.py` creates isolated Keycloak/PostgreSQL resources
and synthetic accounts. It exercises real TLS, code/PKCE login, forced password
change, the production MCP adapter, the unchanged backend verifier, audience
denial, refresh rotation, restart and database privilege isolation. It is an HTTP
protocol/form test, not proof of a rendered browser UI or actual Garden session.
`scripts/test_identity_browser.py` also runs real Chrome with the browser sandbox
and TLS verification enabled, using an isolated trust store. Build the CLI first,
set `WORKSTREAM_TEST_CLI` to its absolute path, and run the browser test inside an
isolated D-Bus session with an unlocked test Secret Service. It covers the
native CLI login, initial password change, consent and renewal without
using a personal browser profile.
`scripts/test_public_ingress.py` separately exercises the pinned Caddy routes.
Hosted cutover and actual Garden qualification remain separate required evidence
before this change can be reported ready.
