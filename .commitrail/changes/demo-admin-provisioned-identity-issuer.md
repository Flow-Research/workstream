# Demo administrator-provisioned identity issuer

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: An isolated Rust demo issuer lets its own administrator provision human accounts and issue compatible short-lived tokens without changing Workstream authentication or authorization.

## Intent

Let issuer-approved demo participants sign in without an operator minting a token roster. This is an external demo issuer, not production Flow Identity or a Workstream login feature.

## Current behavior

`experiments/hosted_drill_identity/fixture.py` mints offline tokens for named identities. `backend/app/adapters/auth/flow.py` verifies pinned asymmetric JWTs using HTTPS JWKS. Workstream owns actor admission and grants independently of token claims. CLI and MCP clients consume a supplied bearer token.

## Bounded change

### Allowed

- `experiments/demo_identity/`: independent Rust issuer, operator bootstrap command, HTTPS service, Dockerfile, README and focused tests.
- `deploy/hosted/compose.demo-identity.yml`: opt-in hosted Compose overlay, without changing the active release composition.
- `.github/workflows/demo-identity.yml`: changed-path issuer verification, without altering existing required checks.
- `.dockerignore`: admit only the issuer's build inputs into the repository-root Docker context.
- This change record; a narrowly affected roadmap statement if capability wording requires it.

### Not allowed

- Workstream verifier, actor, admission, authorization, CLI or MCP core changes; live deployment or issuer switch; public signup; mail, OAuth, frontend or refresh tokens.

## Design and decisions

One local operator initializes a private issuer data directory and bootstraps an issuer administrator account using an email and password read from private stdin. Login issues a Workstream-audience access token, plus a distinct issuer-admin-audience token only for issuer administrators. An authenticated administrator API provisions email and initial-password accounts; an authenticated password-change API lets a user replace the initial password. There is no public signup. SQLite stores random immutable subjects and Argon2 password hashes. The issuer signs RS256 access tokens with the existing verifier's exact required claims and publishes public-only JWKS. Admin API authorization checks the issuer-admin token and current database admin flag; issuer administration never maps to Workstream grants. Bound request bodies, concurrent expensive work and failed attempts; use generic credential errors and no secret logging. Restart must preserve state and fail closed on missing state. An opt-in Compose file prepares hosted integration without switching the current drill. Email is a login identifier, not a verified mailbox claim. Existing hosted drill remains unchanged.

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
| Existing verifier contract | inspect `flow.py` and hosted fixture | RS256/JWKS and exact human claims identified | actual live issuer cutover out of scope |
| Issuer account and authority boundaries | `cargo test --locked -- --test-threads=1` | 3 passed: admin provision, duplicate rejection, password change, restart, token separation, bounds and current admin flag | single-instance demo only |
| Real verifier compatibility | `cargo build --locked --manifest-path experiments/demo_identity/Cargo.toml` then `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend python3 -m pytest -q experiments/demo_identity/test_service.py` | 1 passed over real HTTPS, including wrong issuer/audience/expiry/signature and issuer-admin expiry/nbf/iat negatives | no live EC2/DNS proof |
| Compose and repository checks | combined hosted Compose `config --quiet`; Rust clippy; stale wording and Markdown links | passed | hosted preflight and cutover deferred |
| Issuer CI | changed-path workflow runs frozen Cargo fmt/clippy/tests/build, Docker image build/smoke, Compose network assertions and real HTTPS verifier proof with frozen backend dependencies | added for pull requests | hosted result pending |

## Review findings

Plan review required separate admin and Workstream audiences. Security review found JWT leeway/nbf acceptance, a shared Docker network and a global-login rate bucket; zero-leeway validation, a private identity network and bounded per-source/account buckets resolved those findings. Architecture review found invalid short Compose mounts and a hidden SQLite file-size restart cap; long bind mounts and metadata-only DB validation resolved them. QA review found bootstrap blocking until EOF and missing denial/bound probes; bounded line input and focused API tests resolved them. CI integrity review required Docker image and Compose topology proof in the changed-path workflow; those checks were added. Exact committed-candidate replays remain PR evidence.

## Reconciliation

- Current-source reconciliation: Based on `origin/main` at `be05779ec`.
- Next usable boundary: Build a digest-qualified issuer image and coordinate DNS, TLS, persistent volume ownership, hosted preflight/readiness, firewall, and issuer cutover after the Garden drill.
- Remaining risks: Tokens remain valid until expiry; issuer administrator provisioning does not establish mailbox ownership.
