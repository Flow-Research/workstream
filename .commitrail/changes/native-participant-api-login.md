# Native participant CLI and direct API authorization

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Official native CLI login and Swagger code/PKCE authorization without a repository login helper.

## Intent

Participants with an invited Flow Identity account must be able to use the CLI or
API without Garden or a Python login helper. The public administrator console was
merged separately in #715 while this extension was being qualified. Keep issuer
password handling separate from Workstream authorization.

## Risk and review routing

L1 authentication-client change. Focused security, architecture, QA/test-delta,
docs and CI integrity reviews. Human focus: exact issuer/API binding, no password
grant, safe refresh and logout, and real browser/API evidence. Prohibited scope:
Garden chat repairs, signup/SMTP, product grants, or replacement backend authority.

## Bounded change

The same requested identity usability correction also removes dependence on a repository login helper. Native CLI `login`, `logout`, and explicit `auth token` use the existing public code/S256-PKCE client, private locally stored refresh credentials, same-subject renewal and fixed audience/issuer validation. Normal CLI commands consume the saved session unless an explicit environment bearer is supplied; reject saved credentials bound to a different API origin. Refresh is serialized and an uncertain refresh response requires fresh login rather than automatic retries. No participant passwords are handled by the CLI or Workstream.

Swagger gains a public PKCE OAuth client with one exact HTTPS callback and origin, while preserving bearer API support and the unchanged backend verifier. API consumers can sign in using Authorize or a standard OAuth client; direct participant password grants stay disabled. Allowed files: cli auth owner/commands/tests/dependency lockfiles/docs, backend Swagger/OpenAPI owner and focused tests, realm configuration/tests and hosted callback ingress/tests, identity browser/protocol proofs and affected identity CI helper references. Remove the superseded participant Python helper and replace its distinct proof with native-client and provider tests; preserve browser/provider integration coverage. No Garden, signup, SMTP, machine impersonation or human-review work.

## Acceptance criteria

Proof must cover callback state/PKCE and timeout, invalid issuer/audience/token, OS credential-store and lock custody, API-origin substitution, concurrent/uncertain refresh, logout and explicit token output; a real invited participant browser login with the built CLI and direct API call; Swagger browser authorization against the hosted provider. Review security and architecture before implementation and replay relevant QA/docs/CI tracks before readiness.

### Concrete onboarding contracts

- Default API origin is `https://workstream.flowresearch.tech`; default issuer is `https://identity.flowresearch.tech/realms/flow`. Login's explicit `--api-url`/`--issuer` bind its saved credential to those exact HTTPS origins. `WORKSTREAM_TOKEN` takes precedence for existing automation; absent that bearer, reject any configured API origin differing from the saved binding before network access. No HTTP production login endpoints.
- Store one participant session in the OS credential store (Linux Secret Service, macOS Keychain, Windows Credential Manager), not a plaintext-token file. If the store is unavailable or locked, fail with an actionable message; do not silently fall back. Use an owner-private standard user-config directory and advisory lock to serialize login/refresh/logout; reject symlink/nonregular lock paths and insecure Unix directory modes. Credential-store replacement is a single secret operation; write a refresh-in-flight marker before sending a refresh. An interrupted/failed refresh requires a fresh browser login. Logout removes the local secret even when remote logout cannot be confirmed, reporting that limitation without claiming access-token invalidation.
- Verify signed RS256 tokens with the maintained OIDC verifier and bounded, nonredirecting HTTPS transport: exact issuer, API audience, `azp=workstream-cli-login`, `typ=Bearer`, `subject_kind=human`, nonempty subject/email, issued-at/expiry and required access scope. Discovery/JWKS endpoints remain same fixed issuer paths. Refresh must retain subject/client identity. State and PKCE are fresh per login; callback binds only IPv4 loopback17843, exact method/host/path, singleton state/code parameters, and a five-minute login deadline inherited from the existing helper.
- Swagger explicitly serves `/docs/oauth2-redirect`, exposes that exact ingress path, initializes `workstream-swagger` with S256 PKCE, and adds an OAuth authorization-code alternative to bearer-secured OpenAPI operations (OR, not AND). Runtime bearer parsing/verification stays unchanged. Register only the exact API-origin callback and browser webOrigin; no client secret or token persistence in Swagger.
- Native CLI auth code owns provider/client+OS-secret-store integration; command.go owns command registration and client resolution. Existing provider/Chrome tests must invoke the built CLI, retaining forced-password-change, signed token, renewal and cleanup proof. Identity CI builds the binary instead of installing the deleted Python login helper. New tests belong to CLI auth/command and existing backend docs/OpenAPI owner; package checks and current boundary catalogues must still pass.

## Evidence

Native-client proof replaces the retired helper's callback substitution, signed
contract, foreign-origin, same-subject renewal, uncertain refresh, logout and
concurrent-operation tests. File-token permission tests are replaced by OS-secret
storage and private lock custody checks; the old memory-only child-process mode
and no-overwrite file workflow are removed rather than preserved as alternate
login paths. Browser proof invokes the built binary and keeps forced password
change, renewal and provider-session logout assertions. The hosted Linux CLI
already completed browser PKCE, OS-keyring storage, exact-email `whoami`, explicit
token output and logout; Swagger hosted qualification is recorded below.

The replacement real-provider/browser fixture passed with the built native CLI:
forced first-password change, browser code/PKCE, signed API identity, near-expiry
renewal, local logout and absence of its provider session. Its first run reached
logout but the test's final admin read used an expired operator token; renewing
that test credential fixed the proof without changing product behavior. Go package
checks and login race tests passed; the Windows binary cross-build passed, which
is not Windows credential-store runtime qualification. Hosted Linux runtime proof
uses the real Secret Service. Measured hosted access/refresh strings were 1,046
and 844 bytes; platform credential-store limits still apply and failures are
reported without plaintext fallback.


Hosted Swagger qualification passed against the deployed API image built from
`4c75c6986`: a fresh browser sent S256 authorization and exchanged the code with
its verifier, signed in through Flow Identity, and used Swagger **Try it out** to
read the invited participant's exact profile. Reload removed the browser token;
an anonymous API request remained 401. The image is pinned at
`sha256:a106607b53b92333b5ea1c1a380669c2cb531943436ec04ce473f6d09cdbe6bb`.
API and MCP returned healthy after the coordinated deployment.

The first hosted Swagger probe caught use of the local-test issuer setting. The
repair uses the canonical production `token_issuer` and its regression constructs
the real verifier configuration, without mocking validity. Local HMAC/development
configuration does not advertise browser OAuth. The initial image pull required
renewing temporary ECR authentication; the previous registry configuration was
restored after deployment. No identity accounts, product roles or retained data
were reset. Private participant credentials and browser artifacts stay outside Git.
