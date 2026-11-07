# Demo administrator-provisioned identity issuer

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: An isolated Rust demo issuer lets its own administrator provision human accounts and issue compatible short-lived tokens without changing Workstream authentication or authorization.

## Intent

Let issuer-approved demo participants sign in without an operator minting a token roster. This is an external demo issuer, not production Flow Identity or a Workstream login feature.

## Current behavior

`experiments/hosted_drill_identity/fixture.py` mints offline tokens for named identities. `backend/app/adapters/auth/flow.py` verifies pinned asymmetric JWTs using HTTPS JWKS. Workstream owns actor admission and grants independently of token claims. CLI and MCP clients consume a supplied bearer token.

## Bounded change

### Allowed

- `experiments/demo_identity/`: independent Rust issuer, operator bootstrap command, HTTPS service, Dockerfile, README and focused tests.
- `deploy/hosted/compose.demo-identity.yml`, `preflight.py`, `compose.py`, `release.env.example`, `demo-identity.Caddyfile`, `demo-identity-caddy.service`, and `README.md`: opt-in issuer integration through the existing hosted wrapper, bounded resources, private state/TLS mounts and readiness checks.
- `scripts/test_hosted_release_config.py`: focused configuration, topology and rejection proof.
- `docs/reports/`: sanitized hosted account/login and Workstream authorization proof, with no credentials.
- `.github/workflows/demo-identity.yml`: changed-path issuer verification, without altering existing required checks.
- `.dockerignore`: admit only the issuer's build inputs into the repository-root Docker context.
- This change record; a narrowly affected roadmap statement if capability wording requires it.

### Not allowed

- Workstream verifier, actor, admission or authorization core changes; public signup; mail, OAuth, frontend or refresh tokens. CLI/MCP additions are restricted to the two already-public guide request operations below.

## Design and decisions

One local operator initializes a private issuer data directory and bootstraps an issuer administrator account using an email and password read from private stdin. Login issues a Workstream-audience access token, plus a distinct issuer-admin-audience token only for issuer administrators. An authenticated administrator API provisions email and initial-password accounts; an authenticated password-change API lets a user replace the initial password. There is no public signup. SQLite stores random immutable subjects and Argon2 password hashes. The issuer signs RS256 access tokens with the existing verifier's exact required claims and publishes public-only JWKS. Admin API authorization checks the issuer-admin token and current database admin flag; issuer administration never maps to Workstream grants. Bound request bodies, concurrent expensive work and failed attempts; use generic credential errors and no secret logging. Restart must preserve state and fail closed on missing state. An opt-in Compose file integrates the external issuer through the canonical hosted checks. After the completed Garden drill, a coordinated hosted cutover verifies real account/login tokens against Workstream without changing retained subjects or evidence. Email is a login identifier, not a verified mailbox claim. Preserve existing Garden records and authorization; new issuer subjects acquire no project authority merely by signing in.

## Acceptance criteria

- [x] Only a valid issuer administrator can provision a unique account; the user logs in and changes the initial password.
- [x] Wrong passwords, unknown emails and unauthorized provisioning fail without account disclosure.
- [x] Generated short-lived JWTs pass the unchanged Flow verifier; wrong issuer/audience, expiry and foreign signatures reject. Issuer admin status does not grant Workstream authority.
- [x] Subjects and signing keys survive restart; secrets and passwords stay out of arguments, logs and committed files; API and operator input are bounded.
- [x] HTTPS JWKS exposes only the public key, with no public administrative operation.

## Risk and review routing

- Risk class: L1 (credential issuance and authentication).
- Required reviewers: security, architecture, QA and CI integrity; focused plan review before implementation.
- Human review focus: isolated demo boundary, issuer operational custody, admin-token separation and the deliberate absence of email ownership proof.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing verifier contract | inspect `flow.py` and hosted fixture | RS256/JWKS and exact human claims identified | public issuer cutover still requires DNS/TLS |
| Issuer account and authority boundaries | `cargo test --locked -- --test-threads=1` | 4 passed: admin provision, duplicate rejection, password change, stale-password-update rejection, restart, token separation, bounds and current admin flag | single-instance demo only |
| Real verifier compatibility | `cargo build --release --locked --manifest-path experiments/demo_identity/Cargo.toml` then `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend python3 -m pytest -q experiments/demo_identity/test_service.py` | 3 passed over real HTTPS, including wrong issuer/audience/expiry/signature and issuer-admin expiry/nbf/iat negatives | private EC2 account/verifier proof passed; public DNS access pending |
| Compose and repository checks | combined hosted Compose `config --quiet`; Rust clippy; stale wording and Markdown links | passed | canonical hosted configuration proof now passes 66 tests; public cutover pending DNS/TLS |
| Actual container networking and persistence | `python3 experiments/demo_identity/test_container.py -q` with the built candidate image | passed; replacing the bridge with the earlier internal network fails at the host HTTPS connection | public DNS/TLS remains separate |
| Issuer CI | changed-path workflow runs frozen Cargo fmt/clippy/tests/build, Docker image build/smoke, Compose network assertions and real HTTPS verifier proof with frozen backend dependencies | workflow added | hosted executions are PR evidence |

## Review findings

Plan review required separate admin and Workstream audiences. Security review found JWT leeway/nbf acceptance, a shared Docker network and a global-login rate bucket; zero-leeway validation, a private identity network and bounded per-account limits with a global overload ceiling resolved those findings. Architecture review found invalid short Compose mounts and a hidden SQLite file-size restart cap; long bind mounts and metadata-only DB validation resolved them. QA review found bootstrap blocking until EOF and missing denial/bound probes; bounded line input and focused API tests resolved them. CI integrity review required Docker image and Compose topology proof in the changed-path workflow; those checks were added. Exact committed-candidate replays remain PR evidence.

## Reconciliation

- Current-source reconciliation: Reconciled with `origin/main` at `03f7f379c` after Garden merge.
- Next usable boundary: Qualify public DNS/TLS participant access. Known old credentials, fixture containers and obsolete operator mint/startup paths were removed after the successful active private issuer cutover. The normal API now accepts Rust-issued logins and rejects a previously accepted, unexpired fixture token; the canonical release/AWS proof and retained-data checks passed.
- Remaining risks: Tokens remain valid until expiry; issuer administrator provisioning does not establish mailbox ownership.

## Hosted completion authorized after Garden merge

The user requested completion of this same PR through real hosted deployment and account/login proof. Reconcile current main first. Integrate the existing overlay with the existing wrapper rather than bypassing its release checks. Test private persistent account/signing state, exact issuer/audience/JWKS configuration, resource bounds and readiness. Deploy the digest-qualified issuer with HTTPS, then prove administrator provisioning, participant login/password change, restart persistence and unchanged Workstream authentication plus denied access without admission/grants. Never remap the Garden fixture subjects to new accounts or invent authorization. Public DNS/TLS requires the operator-selected hostname; test private hosted transport meanwhile and distinguish that evidence from public reachability. Run focused security/architecture/QA/CI review on the final candidate and fresh CI before ready-for-merge status. No new login logic in Workstream core; the later explicit client completion below extends this same PR.

## Ingress refinement

The operator selected Caddy for the test deployment so public certificate
issuance and renewal are automatic. The NGINX candidate was removed. Caddy
exposes only the four issuer paths, bounds bodies/connections/timeouts and
verifies the private upstream TLS certificate. It has no per-client rate-limit
plugin; the issuer retains per-account limits, a global overload ceiling and
four concurrent password operations. It never trusts forwarded identity.
Security review reproduced an all-clients lockout caused by a shared proxy-peer
bucket. Removing that bucket preserves the stated account/global limits; a real
HTTP regression fails on the previous binary with 429 and passes after repair.

A real EC2 run caught a second deployment mismatch: Docker marked the issuer
healthy but suppressed its loopback port on an `internal` network. The issuer
now has an ordinary dedicated bridge with no backend service attached; the
exact loopback publication remains enforced. The container integration test
starts the shipped image/overlay, connects over host HTTPS, recreates only the
issuer and proves account/signing persistence. CI runs this proof, not only
Compose rendering. Retained account state and existing backend containers are
preserved during the correction.

After authorized replacement login and Workstream authority proof succeeds, retire the fixture
issuer container, signing keys and saved drill tokens, and update current
operator/client references. Prove the old tokens are denied by the new verifier.
Do not erase retained Garden identity links, audit facts or contributions.
Credential retirement is conditional on the new authorized path working.

[Private hosted proof](../../docs/reports/demo-identity-hosted-2026-11-06.md) records real account, restart, verifier and Caddy transport evidence and the remaining public cutover boundary.

The user additionally authorized private CLI/MCP testing while DNS is pending.
The existing clients use real login tokens and the existing API without client
core changes. The [bounded client proof](../../docs/reports/demo-identity-clients-2026-11-07.md)
covers authority denials, one shared draft-task receipt, cross-client replay and
revocation; it does not claim full client catalogue or native connector coverage.

## Active private cutover and client completion

The user requires retirement of the previous runtime credentials now, without
waiting for public DNS, and all changes remain in this PR. Preserve the canonical
HTTPS issuer identity. Resolve that hostname to the same host from the API through
a fixed, validated issuer-overlay mapping. Caddy temporarily serves the trusted
private certificate on 443 and verifies the issuer upstream. Qualified images
start from the recorded clean base and trust only the new private certificate in
addition to normal public roots; never disable TLS verification. Public DNS/TLS
remains a distinct participant-access claim.

Use the existing deployment drain, release descriptor, AWS proof and generation
marker owners. Record deployment configuration and image source separately when
they differ. Prove fresh account login and retained grants through the active API,
then reject old tokens and remove fixture signing keys, token copies, runtime
container/helpers and old CA trust. Preserve original actors, immutable records
and non-secret historical evidence. Do not delete business data or fabricate an
identity mapping. Remove obsolete runtime paths rather than leave a fallback.

Client additions are exactly the existing POST guide `/setup` and
`/requirements/compile` operations. The former explicitly requests optional
assistance; the latter compiles uploaded manager rules without inference. Reuse
CLI guide commands and MCP guide-lifecycle ports, with caller-owned UUID keys,
strict 202 receipt validation, unchanged bearer forwarding and no automatic retry.
The receipt contains operation/run/generation/status, not project/guide selectors;
clients must not invent a selector comparison or another lookup.

Additional allowed files: `cli/internal/api/`, `cli/internal/command/`, their
focused tests and `cli/README.md`; `mcp_server/` tools, gateway, schemas, packaged
contracts, tests and README; the MCP workflow's exact catalogue assertion only.
Deployment changes remain within the existing issuer overlay/preflight/tests and
operator documentation. Required proof includes missing/malformed keys, exact
forwarding, invalid/uncertain responses, denials, and explicit no-inference
compilation; actual deployed login, old-token rejection and credential retirement.
Focused security/architecture, QA/test-delta, docs and CI review apply to affected
boundaries. No native connector/OAuth claim or expansion to unrelated tools.

The [active private cutover report](../../docs/reports/demo-identity-active-cutover-2026-11-07.md) records canonical release/AWS proof, retained-data checks, fresh login, unexpired old-token rejection, bounded credential retirement and actual CLI/MCP SDK calls against the normal API. Public DNS/TLS and native connector integration remain separate.

External review identified a shared database lock held during password hashing. Login and password replacement now read an owned snapshot, release the database lock during Argon2 work, and apply password changes through a subject/current-hash conditional update. A stale update cannot overwrite the winning change. The HTTP proxy-limit regression uses valid-format unknown addresses so normalization cannot bypass the throttle, and the issuer workflow includes its base Compose and environment inputs.

## Hosted client completion in the same PR

The user explicitly extends this PR to make MCP a managed hosted Compose service,
verify deployed client workflows with Rust-issued login tokens, and establish CLI
binary publication readiness. Reuse the existing MCP gateway, strict caller-token
forwarding and hosted preflight. Do not introduce login into Workstream, OAuth
claims, a shared MCP token, or change product authorization. Public DNS is still a
separate prerequisite; private authenticated SSH transport is valid drill access.

Additional allowed files: `deploy/hosted/compose.mcp.yml`, existing hosted wrapper,
preflight, environment example and operator documentation; focused hosted config
and MCP container tests; MCP deployment documentation; affected roadmap/report
claims. Preserve all existing deployment checks and service isolation. Qualify
images before deployment and retain active backend data and workers. Review
network topology and recreation behavior before implementation. Security and
architecture review cover caller-token custody and service isolation; QA/CI/docs
review covers transport, negative cases, unchanged gates and accurate exposure.

Acceptance: Compose starts a digest-qualified, bounded, non-root MCP service with
no mounted credentials; it connects to the existing API without weakening TLS
rules. Real authenticated MCP initialization/list/calls and CLI calls use fresh
Rust-issued credentials, with unauthorized/expired/foreign credentials denied and
no cross-caller state. Prove restart and a bounded representative authorized
workflow; map remaining catalogue coverage to tests rather than claim every tool
ran live. Verify four-platform CLI release proofs and repository publication
controls. Publishing a binary or merging this PR remains a separate explicit
human action. Do not describe native connector compatibility as proven through
an SDK test.

Hosted transport proof additionally owns `scripts/test_hosted_mcp_container.py`
and its invocation in the existing MCP image job. It tests the shipped overlay
and real container replacement against a controlled API fixture; that evidence
is separate from deployed Rust-token authorization proof. No test gates or caps
are weakened. The reviewed private topology shares API loopback; the wrapper
stops MCP before API replacement, recreates it after success, and verifies the
actual current container namespace.

The [managed hosted qualification](../../docs/reports/managed-mcp-hosted-2026-11-07.md)
records deployment, real Rust-account CLI/MCP calls, restart, malformed-PRE
rejection/no Submission, verified admission, durable Garden POST, shared
acceptance and a stable single 100 FLOW award across exact replay. Temporary
grants and bearer files were retired after fresh revocation checks. A physical
disk-capacity refusal was diagnosed without relaxing intake limits; obsolete
unused build images were removed and the same request then reached the checker.
The operator guide now distinguishes resource capacity from health readiness.
Four-platform CLI preview evidence is separate from protected binary publication;
public DNS/TLS and native connector integration remain unqualified.
