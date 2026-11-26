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

After import, complete [account-console configuration](#account-page-after-login)
without replacing either built-in account client.

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

Public registration starts disabled until the self-service activation procedure below is completed. Direct password grants are enabled only on the dedicated `workstream-api-login` client; CLI, Swagger, Garden and MCP clients retain their separate browser/exchange flows.
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

## Workstream feedback email claim

Fresh realm configuration includes the `account-email-verified` mapper on the
`workstream-identity` client scope. For an existing realm, add that one mapper
from the rendered `realm_config.py` output to the existing scope through the
authenticated Keycloak administration interface. Preserve the other mappings
and realm settings. The stock user-property mapper reads `emailVerified` as a
boolean `email_verified` access-token claim alongside the existing signed
`email` claim. Verify that a fresh token for a designated verified participant
includes the email and boolean `true` for the Workstream audience. False or
missing mailbox evidence leaves the participant ineligible for feedback email.

## Participant CLI and direct API access

Flow Identity issues API credentials as well as MCP credentials. A participant
uses the same invited email/password for both, and completes a mandatory initial
password change on Flow Identity's HTTPS page. Workstream does not accept passwords
or implement a separate login endpoint.

### Curl: email/password to API token

First sign in through Flow Identity in your browser and finish any required
password change. After that, POST your email/password to the **issuer**, not to
Workstream. The dedicated public client is `workstream-api-login`; it needs no
client secret. For Bash, these commands avoid putting the password into shell
history or curl's process arguments:

```bash
set +x
read -r -p 'Email: ' FLOW_EMAIL
read -r -s -p 'Password: ' FLOW_PASSWORD
printf '\n'
printf '%s' "$FLOW_PASSWORD" | curl --fail-with-body --silent --show-error \
  'https://identity.flowresearch.tech/realms/flow/protocol/openid-connect/token' \
  --data-urlencode 'grant_type=password' \
  --data-urlencode 'client_id=workstream-api-login' \
  --data-urlencode "username=$FLOW_EMAIL" \
  --data-urlencode 'password@-' \
  --data-urlencode 'scope=openid workstream:access workstream-api-audience'
unset FLOW_PASSWORD
```

The response contains `access_token`, `expires_in`, and `refresh_token`. Keep the
response private. Send the access token to Workstream as `Authorization: Bearer
<access_token>`; it lasts up to five minutes. To renew, POST `grant_type=refresh_token`,
`client_id=workstream-api-login`, and the current `refresh_token` to the same token
endpoint. Store the replacement refresh token; the old one cannot be reused.
To close that refresh session, POST the client ID and refresh token to
`https://identity.flowresearch.tech/realms/flow/protocol/openid-connect/logout`.

A temporary password, incomplete required action, wrong password or disabled
account does not produce a token. Login does not grant project or administrator
permissions. This client issues API credentials, not MCP credentials. Invited accounts and
verified self-registered accounts use the same endpoint after account setup.
Public registration remains disabled until email delivery is configured and proven.

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

A browser application calling the API uses the standard OAuth authorization-code
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

Flow Identity is the current v0.1 external authentication provider used for
hosted Workstream qualification. Use
its real Keycloak accounts and the documented CLI/API login flows; the former
simulated issuer and hosted fixture harness have been removed. Do not provision
an alternate issuer or locally mint participant tokens for a hosted drill.

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
These local proofs do not establish a hosted cutover or an actual Garden session.
Qualify those deployment boundaries separately before claiming they work live.


## Flow branding and self-service signup

The identity image contains the `flow` login and email themes. The login theme
inherits Keycloak's maintained `keycloak.v2` forms and changes presentation only;
registration, login, verification, password change, recovery and consent retain
provider security behavior. Theme assets are served locally by the issuer, without
third-party fonts or scripts. Changes to bundled assets require rebuilding and
pinning the identity image. Select **flow → Realm settings → Themes** and set the
login and email themes to **flow** for an existing realm; do not re-import it.

A small `flow-human-registration` event listener assigns `human` to successful
self-registration in the Flow realm. It reads no submitted marker and handles no
administrative account creation. Keep `workstream_subject_kind` administrator-only.
Existing participants and service identities are not rewritten. The listener is compiled
against the exact pinned Keycloak jars; a provider-version upgrade must rerun the
registration and denial proofs because this SPI can change between releases. Registration
creates an unverified identity row; it grants neither usable Workstream credentials
before email verification nor Workstream project/administrator permissions after it.

Password recovery uses the same neutral response text for unknown accounts and mail
failures. This is not a timing-indistinguishability guarantee: eligible accounts
can take longer because SMTP delivery is synchronous. Flow guidance tells participants to check spam, retry later or contact
their administrator; the response text does not disclose account existence. A failed send
does not change the existing password. Operators must inspect delivery failures.

### Configure and prove email delivery

1. Deploy the pinned identity image containing the themes and registration
   provider. Keep public signup disabled during setup.
2. In **flow → Realm settings → Email**, configure the organization's SMTP host,
   port, sender address/name, TLS and authentication. Enter the SMTP password only
   in authenticated administration; never commit it or send it in chat. Use an
   approved sender domain with the delivery provider's required DNS configuration.
3. Set a controlled mailbox as the email address of the administrator signed in
   to the console (including a named master-realm administrator). The SMTP test
   sends to that administrator, not to a Flow participant selected elsewhere.
   Send a test message and confirm receipt in that mailbox. A successful
   TCP connection or the console accepting settings is not delivery proof.
4. Inventory existing users whose email is unverified. Enabling verification also
   requires those invited users to verify their addresses on their next login.
   Do not bulk-mark addresses verified to avoid that step. Existing bearer tokens
   remain valid until their expiry, and active sessions are not silently revoked
   by this configuration patch. For a cutover requiring everyone to reverify
   immediately, explicitly end the affected sessions and allow existing access
   tokens to expire before declaring that cutover complete.
5. Export the existing Flow realm and server information through authenticated
   `GET /admin/realms/flow`, `GET /admin/serverinfo` and
   `GET /admin/realms/flow/users/profile` and
   `GET /admin/realms/flow/authentication/required-actions` to private files. The realm
   export can contain SMTP credentials; keep it private and delete it after use.
6. Render the bounded activation patch:

   ```sh
   python3 deploy/identity/realm_config.py \
     --self-service-realm-input /private/operator/flow-current.json \
     --server-info-input /private/operator/server-info.json \
     --self-service-profile-input /private/operator/flow-profile.json \
     --required-actions-input /private/operator/required-actions.json \
     --output /private/operator/flow-signup-patch.json
   ```

7. Apply the patch with authenticated `PUT /admin/realms/flow`. It enables signup,
   verified email, email-as-username and password recovery, and binds the required
   listener while preserving other listeners. It contains no SMTP password or users.
   The renderer rejects missing SMTP/TLS, a missing provider, a missing or disabled
   `VERIFY_EMAIL` required action, or user-editable/missing
   human-marker profile configuration. Delivery must still
   be confirmed by the operator before applying it.
8. Test a new account through the public browser: create account, receive and use
   verification email, complete login, then exercise password recovery. Confirm
   unverified direct token requests deny, and the new user has no Workstream grants.

Users verify their email and choose their own password through Keycloak’s
registration flow (the current provider defaults to email-first); invited users keep the
required temporary-password replacement. The login, CLI, Swagger, direct token
and Garden MCP interfaces do not change. Email delivery failures must leave the
account unverified; never bypass verification to recover from SMTP outages.
Disable **User registration** to stop new enrollment without deleting existing
accounts or changing their Workstream permissions.

### Account page after login

Complete this configuration after initial realm import and for existing realms before
opening self-service signup. Keycloak creates the built-in `account` and
`account-console` clients; do not import replacements or change user role grants.
The explicit Flow scope list needs an account-console configuration so
`https://identity.flowresearch.tech/realms/flow/account/` can display personal information.

Using authenticated administration:

1. Resolve the single client using
   `GET /admin/realms/flow/clients?clientId=account-console`, then export its full
   `GET /admin/realms/flow/clients/{id}` representation to a private file.
   Render its bounded mapper patch:

   ```sh
   python3 deploy/identity/realm_config.py \
     --account-console-input /private/operator/account-console.json \
     --output /private/operator/account-console-patch.json
   ```

2. Apply that patch with `PUT /admin/realms/flow/clients/{id}`. It supplies only
   an `account` audience and the existing account-client role claims in access
   tokens, plus given name, family name and username in the console ID token
   for its signed-in menu. It preserves
   the client's ID, restricted scope mappings, S256 PKCE and account-only redirects.
3. Resolve `basic` from `GET /admin/realms/flow/client-scopes` and attach it using
   `PUT /admin/realms/flow/clients/{id}/default-client-scopes/{basic-scope-id}`.
   A client update alone does **not** attach this scope. Read the client's
   `default-client-scopes` endpoint back and confirm only `basic` is assigned;
   its `optional-client-scopes` must be empty. Investigate unexpected assignments
   before enabling signup; never attach Workstream or administrator scopes here.
4. Select **flow** as the realm Account theme (included in the pinned identity
   image). It inherits the provider account UI and adds Flow assets without
   replacing its application. Start a fresh account-page login and confirm
   **Personal info** loads, the Flow logo appears and the menu shows your name. Existing
   browser tokens do not gain the new claims until renewed. Account-page tokens
   are for the account service only; obtain a Workstream token through the
   documented API, CLI or MCP client instead.

To change your password after login, open **Account security → Signing in**,
then choose **Update** beside **Password**. On narrow windows, open the menu at
the top left to reveal navigation. The provider may ask for your current password
before accepting the new one. **Personal info** edits name fields; it is not the
password screen. **Sign out** is in your named account menu.

### Local qualification

`scripts/test_identity_signup.py` uses real isolated Keycloak/PostgreSQL, Chrome
and SMTP capture bound only to the owned Docker network. Synthetic verification
and reset emails never leave that fixture. This proves provider behavior, not
production email delivery. The existing provider/browser tests continue covering
invited login, API-only tokens, scoped exchange, refresh and logout.

### Persistent Garden connections

Garden's dedicated MCP browser clients may request `offline_access` in addition
to the MCP access scopes. The offline grant has a **30-day idle limit** and a
**90-day absolute maximum**. Access tokens remain five minutes, refresh-token
rotation remains enabled with zero reuse, and ordinary browser sessions retain
their separate limits. Activity renews the idle window, not the absolute one.
An existing ordinary refresh grant does not become an offline grant when these
settings change: reconnect once to authorize the new grant.

For an existing realm, do not re-import it or rely on client JSON updates to
change scope assignments. Use authenticated Admin API operations:

1. Apply only `persistent_connection_settings()` from `realm_config.py` through
   `PUT /admin/realms/flow`, then read back all three offline session fields.
2. Inspect `GET /admin/realms/flow/client-scopes`. Reuse the existing named
   `offline_access` scope if present, otherwise create `offline_access_scope()`
   through `POST /admin/realms/flow/client-scopes`. Its scope must be included in
   tokens; its consent text must describe retained access without claiming any
   additional Workstream permissions.
3. Verify the scope's realm-role mapping through
   `/admin/realms/flow/client-scopes/{scope-id}/scope-mappings/realm` includes
   the stock `offline_access` role. Verify that the realm's default role includes
   that role; do not grant administrative or Workstream project roles.
4. Attach the scope only to each approved Garden client's optional scopes using
   `PUT /admin/realms/flow/clients/{client-id}/optional-client-scopes/{scope-id}`.
   Read the optional scopes back. Updating the client representation alone does
   not apply these assignments. Keep the scope out of realm-wide default/optional
   defaults and out of direct API, CLI and proof-client assignments.
5. Qualify a new Garden authorization, silent refresh with the same MCP audience,
   refresh after its browser session ends, and explicit issuer revocation.
   Existing API and non-Garden MCP login must still work without offline access.

The credential owner must distinguish a saved connection from a renewable grant.
A rejected grant requires reconnection; a transient provider outage requires a
retry and must not be treated as consent revocation. Removing a connection must
also revoke its retained grant before reporting successful disconnection. Never
print refresh tokens in logs, browser output or support messages.
