# flow-self-service-signup — Verified Flow registration and branded account access

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Flow Identity supports branded self-registration, verified email and password recovery without granting Workstream permissions; the same delivery migrates always-on services to an app-only host with dedicated S3 credentials.

## Intent

Participants create their own Flow account and continue the existing Garden MCP,
CLI, Swagger or direct API login. Flow branding replaces provider branding on
participant-facing identity screens. Invited accounts remain supported.

## Current behavior

`deploy/identity/realm_config.py` disables registration, verification and recovery.
The human identity marker is administrator-owned. Keycloak owns credentials and
sessions; Workstream verifies scoped tokens and separately enforces authority.
PR716 delivered native CLI, Swagger and dedicated issuer password grants.

## Bounded change

### Allowed

- `deploy/identity/**`: provider configuration, minimal theme, registration
  marker provisioning if no stock configuration safely supports it, documentation.
- `deploy/hosted/**`: identity email configuration, app-only hosting, direct S3 credential configuration, and operator instructions.
- `scripts/*identity*`, `scripts/test_keycloak_configuration.py`, identity test
  fixtures, `.github/requirements/identity-browser.*` and `.github/workflows/identity.yml`: real provider/browser/email proofs.
- `scripts/check_stale_artifact_contracts.py` and its focused asset regression: recognize binary image assets without exempting source/configuration text.
- `docs/roadmap_status.md`, affected onboarding docs, this record.

- `mcp_server/tests/test_oauth_provider.py`: repair collection-time expiration values exposed by slow CI; retain all denial assertions.

### Not allowed

- Workstream-owned login/passwords, project/admin grants on signup, Garden primary
  authentication changes, data reset, weakened verification or browser protections.
- Public unverified registration while production mail delivery is unavailable.
- Invented Flow logo or unrelated UI/application redesign.

## Design and decisions

Use Keycloak's existing registration, verification and reset flows; inherit its
maintained login templates and override only branding/assets/messages/CSS where
possible. Theme uses the user-supplied Flow wave logo, preserved unchanged, with responsive blue-accent presentation.
Use local SMTP capture for deterministic real email-flow testing; production SMTP
credentials remain private. Activation validates mail configuration and delivery
before enabling public registration. No real participant email is marked verified
administratively. An unverified account row may exist, but browser/direct API credentials must wait for verification. Inventory existing unverified invited accounts before activation and require genuine email verification. Activation must reject a missing registration provider and bind its listener in the same activation patch. Signup gets trusted human identity without exposing its marker
as an editable form field. Pinned Keycloak26.8.2 source shows profile defaults are filtered by field edit permissions; making the marker writable would break custody. Use a minimal Flow-realm REGISTER event listener in the provider transaction to assign human only to successful self-registration. Do not handle admin-create events or alter existing accounts. Compile against the exact provider jars with a pinned JDK21 build stage, adding no runtime framework.
Preserve invited users and existing issuer/sub/audience/token-exchange contracts.

### Account-console correction

The hosted signup completes, but the provider account console has no token scopes
because the explicit realm scope import omits stock defaults. Complete the same
signup journey by configuring only the stock `account-console` client with the
basic subject scope and account-only role/audience mappers. Keep its existing
account-role scope mappings, PKCE and account-path redirects; never add Workstream
API/MCP audiences, realm-administrator roles or broad full-scope access. Let Keycloak create both built-in account clients during realm import, then
reconcile the existing `account-console` using the same bounded helper for new
and hosted realms; never import a duplicate or recreate the `account` client. Prove the real account page loads after signup and its tokens cannot enter
Workstream API/MCP. Assign `basic` through the dedicated default-client-scope endpoint; client PUT only updates the mapper representation. Existing users and permissions remain unchanged.

## Acceptance criteria

- [ ] Browser signup completes only after email verification; supplied marker or
  privilege fields cannot grant authority or choose a service identity.
- [ ] Verification/reset links are single-use and expire; wrong/replayed links,
  wrong passwords and unverified direct grants deny.
- [ ] Verified accounts use existing CLI/API/MCP scopes, with no Workstream grants.
- [ ] Browser login, signup, required password change, verify/reset and consent
  screens show Flow branding, work on mobile and retain accessible labels.
- [ ] SMTP outage preserves credentials and shows non-enumerating retry/support guidance.
- [ ] Existing invited-account login/renewal/exchange proofs remain passing.
- [ ] Deployment instructions cover SMTP, theme updates and existing realm updates
  without reset; production signup remains disabled until delivery is proven.

## Risk and review routing

- Risk class: L1
- Required reviewers: security, architecture, QA/test delta, documentation;
  CI integrity if test wiring changes.
- Human review focus: account verification, marker custody, separate Workstream
  permission grants, brand assets and production delivery readiness.

## Evidence

Real isolated Keycloak/PostgreSQL and local SMTP capture, browser form and link
flows, signed token identity/audience assertions, unchanged authorization tests,
rejection controls, responsive screenshots, links and applicable CI.

## Reconciliation

- Current-source reconciliation: based on main a2154e8a4 (merged PR716).
- Next usable boundary: qualify persistent Garden renewal and reconnection; hosted signup and recovery are enabled after real SMTP proof.
- Remaining risks: each deployment must prove its SMTP sender and delivery; enabling verification affects existing unverified accounts. Provider upgrades require repeating the registration and denial proofs.

### Signed-in account usability

Extend the same account-console correction with Flow branding inherited from
Keycloak v3, without copying its application or templates. Map only given name,
family name and preferred username into the console's ID token for its account
menu; keep account-only audience/role restrictions and API/MCP denial proofs.
Exercise the sidebar's Signing in password update, prove the old password denies
and the replacement succeeds, and check named header and Flow logo in the real
browser. Document the password navigation and collapsed menu. No user permission
changes or Workstream password endpoints.

### Persistent Garden connection correction

The user approved a 30-day offline idle timeout and a 90-day absolute maximum
for Garden's personal MCP connection. Ordinary API access tokens remain short-lived;
Garden stores and rotates the refresh credential through its existing Executor
owner. Limit the offline grant to the registered Garden MCP browser clients;
do not extend primary browser sessions or API password grants. Existing ordinary
grants require one reauthorization to obtain the new grant. Revocation and
connection removal must prevent further renewal. Garden must present a known
unusable grant as requiring reconnection, not merely as a saved connection.

Garden requests offline access through its dedicated client configuration; MCP
resource discovery continues advertising only its resource-access scopes. Verify real refresh,
audience preservation, revocation, and two-user isolation before claiming hosted
completion. Garden's status/projection repair belongs in its own repository and
must not change Garden's primary authentication or general chat-stream ordering.

The focused plan review requires explicit existing-realm reconciliation through
Admin API scope endpoints and issuer revocation before Garden disconnect succeeds.
Prove revoking a credential after concurrent rotation invalidates its successor;
retain retryable connection custody when the issuer is unavailable. Do not apply
persistent hosted grants until these checks pass.

## Operator-directed delivery consolidation

Keep identity onboarding, the cheaper app-only hosted deployment, and removal
of certificate/expiring-proof S3 dependencies in one delivery PR. The bounded
hosting and storage contracts remain in the bounded sections below; they
are implementation scopes within this delivery, not separate merge gates.
Preserve identity accounts, database state and public URLs during migration.
Verify login/API/MCP and unavailable checker behavior before moving the Elastic
IP and stopping the old host. Separate KVM execution qualification remains an
explicit follow-up boundary, not a claim made by app-only startup.

## App-only hosting scope

## Intent

Run the main API, MCP, Flow Identity, PostgreSQL, Redis, guide parser, and
inference proxy on an app host without KVM.

## Current behavior

The current
[hosted composition](../../deploy/hosted/README.md) checks for native Smol
before running the API or worker. The shared [outbox scan](../../backend/app/workers/outbox.py)
currently delivers checker requests through the same queue and PostgreSQL
delivery owner as ordinary assignment, revision and completion effects.

## Bounded change

- Add an explicit hosted app profile in `deploy/hosted/{compose.py,preflight.py,compose.yml,release.env.example}`
  and an overlay for native-only configuration if needed. The app profile
  preserves existing API, parser, inference proxy, storage qualification, database,
  broker, and identity validation and activates without local checker files,
  mounts, native systemd start, or KVM readiness. Reject conflicting native or
  trial configuration in this profile. Keep the existing single-host mode.
- Compose a fixed checker-delivery exclusion in `backend/app/core/config.py`,
  `backend/app/adapters/outbox/__init__.py`,
  `backend/app/modules/outbox/delivery.py` and `delivery_repository.py`. Filter
  the exact checker request and reconciliation event types before candidate
  pagination, including expired claims, and enforce the same filter before
  claim or recovery. Retain ordinary and unsupported expired recovery.
- Refresh the exact identifier-generation classifications for the changed outbox
  syntax. The authority fact-substitution test uses a 60-second lease to isolate
  its assertions from short-lease expiry under CI load; expiry tests retain their
  existing explicit bounds and assertions.
- Update the existing hosted release preflight test and relevant existing
  backend test owners. Document the app profile and its offline limits in
  `deploy/hosted/README.md` and reconcile the affected part of
  `docs/roadmap_status.md`.

The same public ZIP preparation route resolves the absent typed intake before
reading bytes and returns the existing retryable 503. MCP continues calling
that API. Keep event schemas, authority, receipts, lease owner, and public
contracts. Existing checker rows remain available for a later checker worker.
Private second-node routing, model relay wiring, provisioning and cloud
changes are outside this migration prerequisite.

## Acceptance criteria

- [x] App-only preflight and startup select the complete ordinary stack with
  no checker config, socket, image assets, or hardware. They enforce archive
  storage qualification, runtime identity, parser and enabled model-proxy custody.
- [x] Authorized ZIP preparation without intake returns the existing 503
  without opening the ZIP stream, creating a PRE record, or creating a Submission.
- [x] An app-only scan omits selected POST request/reconciliation work,
  including expired claims, while ordinary events progress. Direct stale
  deliveries cannot mutate the retained checker rows. The regular topology
  can subsequently select and recover those rows.
- [x] The regular hosted profile still requires native prerequisites and
  the same dedicated model credentials, intake image, and active readiness.

## Evidence

| Claim | Evidence |
|---|---|
| Render, preflight and startup roles | 80 combined hosted configuration tests passed, using real Compose rendering and controlled startup dependencies. |
| Existing retryable API contract | 53 ART tests passed, including the mounted upload route with real command composition and a guarded byte source. |
| Durable event filtering and wrong-role refusal | The repository's isolated PostgreSQL 16 runner passed the focused outbox test covering checker and completion events, due and expired states, and keyset selection. |
| Static checks | Affected backend lint, stale wording, Markdown links and whitespace passed. |

## Risk and review routing

- Risk class: L1.
- Required reviewers: architecture, security, QA, product/operations, documentation, test delta.
- Human review focus: preserved AWS and identity startup gates, explicit
  offline response, inference availability, and retained checker delivery.

## Review findings

- `ARCH-APP-001` and `QA-APPHOST-001`: the repository keeps unfiltered
  selection when the caller supplies no exclusions. The scheduled due-work
  regression exercises that call directly.
- `DOC-APP-001`: the hosted documentation scopes the native prerequisites to
  the single-host profile and describes the retryable API and MCP responses.

## Reconciliation

- Current-source reconciliation: verified against `a2154e8a`.
- Next usable boundary: qualify private checker-host ingress and worker attachment to the same durable owners.

## Dedicated S3 credentials scope

## Intent

The operator approved replacing the current deployment's manual certificate dependency with dedicated restricted access keys. Do not introduce an online CA or require EC2 hosting. Preserve product records, bucket objects and enforced storage protections; remove obsolete proof-only records with their tables.

## Current behavior

Native AWS configuration rejects static credentials. Runtime and proof evidence bind three distinct role ARNs and exact policies. MinIO static credentials are local-only. Hosted startup currently binds certificate files and Roles Anywhere checks.

## Bounded change

### Allowed

- ART provider interfaces, S3 and local adapters, backend and Celery startup,
  ART storage orchestration, and artifact readiness reporting.
- The proof-only models, operator commands, deployment scheduling and focused
  tests, plus one forward migration dropping only the two proof tables.
- Release-image workflow selections and their contract tests, native backend
  configuration example, and app-only hosted deployment integration.
- Direct IAM-user credential loading and isolated AWS authentication, IAM
  policy generation, live deployment verification, and affected operator docs.

### Not allowed

- Ambient credential fallback, provisioning credentials in runtime,
  credentials in tools/checker guests, deletion of product records or bytes,
  and weakened bucket immutability or authorization.
- New certificate services, new general-purpose credential frameworks, unrelated product work.

## Design and decisions

The user explicitly requires removing the expiring database-proof system, not
retaining an alternate activation path. Remove proof/activation models and
runtime gates, periodic jobs, proof-only configuration, obsolete tests and
current documentation. Drop proof-only tables through an explicit forward
migration after checking references. Do not rewrite old migration history.
Project/assignment/submission records, artifact metadata and stored bytes are
not part of this deletion.

Use one dedicated IAM user with direct access to the configured S3 bucket and
artifact prefix, through one isolated private credential file. No certificate
infrastructure, AssumeRole hop or three-user verification workflow. Preserve
AWS authentication, conditional writes, full-byte readback, exact namespace,
Workstream authorization, retry/recovery and terminal transaction safeguards.
Deployment qualification checks actual storage behavior without persisting an
expiring permission-to-use-storage record or running a privileged scheduler.

## Acceptance criteria

- Explicit private-file credentials authenticate on a non-EC2 host with metadata/ambient lookup disabled.
- Incorrect, disabled or missing credentials fail closed without secret-bearing errors.
- The dedicated key cannot administer IAM, change bucket protections, delete retained artifacts, or access other prefixes; deployment operator credentials are absent from application containers.
- Exact-byte upload/read, immutable-write denials, namespace custody and authorization remain enforced. Replace the expiring role-proof dependency deliberately; do not silently skip guards or invent activation receipts.
- Key replacement is verified before retiring the previous key; certificate trust is retired only after successful direct-key storage qualification.
- Operator receives exact restricted IAM configuration and private secret-file instructions; real AWS proof precedes deployment readiness claims.

## Risk and review routing

- Risk class: L1.
- Reviewers: security, architecture, QA/test delta, documentation.
- Human review focus: long-lived secret trade-off, preserved principal isolation, migration/rotation and rollback.

## Evidence

Source trace establishes certificate coupling and isolated proof-only database
references. The focused checks below cover the backend and policy implementation
and live dedicated-user storage qualification.

## Review focus

Review removal of transient activation plumbing without removing product
namespace, authorization, exact-byte, retry or terminal transaction safeguards.
The user explicitly authorized removal of proof-only tables. There are no
product foreign keys into them; the forward migration must not use CASCADE.

## Reconciliation

The operator requires one delivery PR for the identity and hosting work. Integrate app-only deployment with dedicated S3 credentials in that same change, preserving both boundaries. Certificate renewal is superseded for the replacement deployment.

## Dependency trace and scope correction

Activation UUIDs are transient runtime evidence only. No product artifact put,
replica, operation, observation, verification or recovery record stores them.
Foreign keys are confined to the proof/activation tables. Removal therefore
requires a forward cleanup migration for proof-only storage, not rewriting
artifact lineage. Preserve product data and file bytes.

The old 15-minute proof validity detected configuration drift. Removing it
removes that bounded drift-detection claim; it does not remove per-operation
AWS authorization, conditional writes, hash verification or product authority.
Update current specifications accordingly. AWS administrators remain trusted.

No new proof table, timer or receipt is allowed. Candidate review follows the
focused implementation evidence below.

## Implementation verification

- Backend credential/startup checks: 333 initial targeted tests, followed by
  120 focused tests after the prefork startup-budget correction.
- Real MinIO: 42 adapter/conformance cases passed.
- PostgreSQL 16: 13 migration/terminal/recovery/assigned-document cases passed,
  including preservation of an existing product artifact row after dropping
  the two proof-only tables.
- Hosted configuration and image checks: 97 tests passed.
- Policy generation: eight tests and focused security inspection passed.
- Backend collection found 11,551 cases.
- Ruff, whitespace and changed Markdown link checks passed.
- Live AWS qualification with the dedicated user passed conditional create,
  exact readback, missing HEAD 404, replay precondition, and denied overwrite,
  delete, wrong-prefix put and anonymous read. This used a synthetic 66-byte
  object and the generated bucket policy.

Obsolete tests exercised the removed certificate/activation mechanism. Mixed
terminal/recovery tests retain their independent product assertions under the
new storage path; no CI skip or coverage threshold was introduced.

## Integration repair evidence

The release-image workflow still selected removed activation-era tests. Replace
those selectors with the current AWS settings rejection cases and the complete
direct-user credential module; retain the image build/verification gates. A
workflow contract checks that every explicitly selected backend test exists.
The stale activation argument in the retained stale-put observation test is
removed without changing its fencing assertions. The native backend example
now documents only the dedicated credential file for this deployment path.

App-only deployment integration retains direct-key mounts for API, worker and
enabled model proxy while excluding them from Beat, MCP, parser and checker
guests. Native checker custody stays exclusive to the single-host overlay.

Relationship-conflict verification now supplies both empty observation values
the completion operation expects and preserves the submission task contexts.
Retained stale-claim and revision-error test callers use that same signature;
their fencing, retry and error-propagation assertions remain unchanged.
Direct-user credential resolution runs outside the S3 pool deadline and within
the existing identity and operation deadlines. A first upload with a six-second
identity load succeeds under the ten-second identity budget and five-second S3
pool budget. The prior client path timed out before sending the PUT.

Regression checks cover missing or mismatched conditional-write headers,
conditional replay without changing stored bytes, the full bucket-policy denial,
and the injected store receiver at each direct read. Cleanup checks isolate the
missing-key startup failure from ambient AWS settings, verify bootstrap closure,
and verify that worker operations each create and dispose their own database
engine across event loops. Ownership checks limit retirement to the seven
superseded proof paths and reject removal of retained configuration.

## Hosted migration evidence — 2026-11-23

The cheaper t3.large app host runs PostgreSQL, Redis, Flow Identity, API, MCP,
parser, model proxy, Celery worker and Beat. The migration retained the pinned
Flow Identity, MCP, PostgreSQL and Redis images. All nine containers reported
healthy, and the hosted reconciliation and HTTPS ingress units are enabled.
Existing accounts and database state were copied after stopping source writers.
Source and target account, task, assignment and submission counts matched
before qualification traffic. Redis SAVE was explicitly confirmed before its
snapshot was copied. The final migration removed only the obsolete provider-proof
tables.

The same Elastic IP/public URLs now reach the new host. A real browser
code/PKCE flow, discovery of 132 MCP tools, an authenticated profile tool call,
and direct API login/profile access passed after cutover. Dedicated S3
credentials passed synthetic create/full-byte readback and conditional-replay,
overwrite, deletion, foreign-prefix and anonymous-access checks inside the API
container. The old m7i.large was stopped, and its volume remains available for
recovery. The new 100 GiB root volume had about 91 GiB free.

The app profile intentionally has no native checker socket or execution
service. PRE remains unavailable and POST requests are excluded from ordinary
delivery, as proved by the focused API/outbox tests. Live ZIP intake and checker
execution require a qualified checker host. The complete public OAuth and MCP
drill passed on a clean Chrome rerun after a startup crash.
