# Public identity, API and native MCP access

The API, MCP and external identity issuer remain bound to host loopback. The
existing Caddy host service terminates trusted HTTPS for two DNS names and
proxies only their intended paths. PostgreSQL, Redis and the checker socket
remain private. Keycloak supplies browser login; MCP validates resource-scoped
OAuth tokens and exchanges them for API tokens under the same user identity.

## Prepare the deployment

First complete the [hosted deployment](README.md) and configure the independent
[identity provider](../identity/README.md). Retain its PostgreSQL account,
configuration and signing state. An issuer account is not Workstream admission or a project
grant. Email is an unverified login identifier; send initial credentials through
a private channel, not email-service automation or source control.

Create A records for the identity and Workstream hostnames pointing to the host's
stable public IP. Remove conflicting AAAA records unless IPv6 reaches the same
service. Keep the root domain unchanged. Permit inbound TCP 80/443; keep SSH
restricted to administrators and all application ports loopback-only.

Use the existing [Caddy service](workstream-ingress.service) with
[public.Caddyfile](public.Caddyfile), using the two public virtual hosts and the private administration listener.
Do not start a second listener on 443. In its root-owned environment file set:

```dotenv
FLOW_IDENTITY_HOSTNAME=identity.example.org
FLOW_IDENTITY_UPSTREAM_CERT=/etc/workstream-identity-ingress/upstream.cert.pem
WORKSTREAM_PUBLIC_HOSTNAME=workstream.example.org
WORKSTREAM_API_HOST_PORT=18027
XDG_DATA_HOME=/var/lib/workstream-identity-ingress/data
XDG_CONFIG_HOME=/var/lib/workstream-identity-ingress/config
```

Use the actual API port from the release configuration. The issuer stays on
127.0.0.1:18443 and MCP on 127.0.0.1:8080. The upstream certificate file contains
only the issuer's public certificate, with its correct DNS name; the ingress
never receives the issuer signing key or account database. Preserve Caddy's
private, writable certificate data directory. Validate the configuration using
the service environment and installed Caddy binary before restarting that service.
Caddy obtains and renews public certificates once DNS and network checks succeed.

The API verifier must trust the public certificate chain using normal public CA
roots. Its exact issuer, audience and JWKS URL remain pinned. A private test
certificate is not a substitute for public HTTPS; never disable verification.
After switching, test a fresh verifier connection so a cached JWKS cannot hide
an inaccessible issuer. Retire obsolete private frontend certificate copies
only after the public path passes; retain the separate upstream TLS certificate.

## Participant workflow

1. A named identity administrator uses Keycloak's private administration UI to
   create the email account, set the administrator-only human marker, and assign
   a temporary password with `UPDATE_PASSWORD`. Transfer it privately.
2. The participant signs in through Keycloak's browser page and replaces the
   temporary password. The application never receives or stores their password.
3. Direct API/CLI clients complete authorization code with S256 PKCE for
   `workstream-api`. Keep access and refresh tokens out of URLs, process arguments,
   logs and shell history.
4. Garden uses its registered OAuth client and exact callback to obtain a token
   for `https://HOST/mcp`. MCP exchanges that token into a bounded API token for
   the same person before each tool call. An API-only token is not an MCP token.
   Both paths still require current Workstream admission and appropriate grants.

Swagger is available at `https://HOST/docs` and loads its schema from
`https://HOST/openapi.json`. These are public API documentation, not login or
authorization endpoints. Obtain a normal Workstream access token through the
issuer flow above and use Swagger's **Authorize** button for protected calls;
Keycloak administration tokens do not grant Workstream access.
The API routes remain under `/api/*`. Other documentation/debug paths are not
exposed by this profile. MCP retains its exact upstream Host validation, request bounds and
browser-Origin rejection. Caddy accepts the configured public virtual host and
sets the fixed loopback MCP Host; it preserves Origin so browsers cannot bypass
that rejection. The protected-resource metadata endpoint is public; initialization and tool
discovery require an MCP-scoped token. Product authority is checked separately
for every operation. Actual Garden interoperability requires its registered
client and live connection proof, not metadata discovery alone.

## Bounds and verification

Public identity request bodies are capped at 64 KiB; private administration has
a separate 1 MiB bound. Binary API bodies are streamed with a 500 MiB
proxy ceiling; the owning API applies its per-operation policy limits. MCP uses
its 96 MiB transport ceiling and stricter owner limits. The proxy applies finite
read/header/write and upstream response deadlines without retrying mutations.
The 600-second upload budget plus 3600-second API response budget fit within
the 4200-second write deadline; keep the configured preparation deadline at or
below 3600 seconds. Identity upstream response time is limited to 15 seconds
and MCP to 180 seconds.
It has no request-body or response-body buffering configured. Browser origins
are not removed, and untrusted forwarding headers do not determine identity or
authority. Request access logging is off and upstream error logging is excluded
to avoid retaining credentials or submitted URLs in diagnostic payloads.

Before sharing access, verify public certificate/hostname validation for both
names, fresh JWKS fetch, first-login rotation and old-password rejection, normal
login and real Workstream authorization, CLI calls and SDK MCP initialization/
representative authorized tools. Check missing bearer denial, hostile Host and
Origin rejection, and retained service health. A successful DNS lookup or
`tools/list` alone does not establish authenticated end-to-end access. Record
exact live proof separately from fixtures and state remaining limitations.

Swagger's JavaScript and CSS use an exact release with SHA-384 subresource integrity.
The browser requires access to jsDelivr, but rejects changed asset bytes. Upgrade
asset URLs and integrity digests together; bearer authorization is not persisted.
