# AWS artifact-provider live activation

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Make the existing native AWS S3 artifact adapter usable only after fresh, exact live proof, while retaining the same ART storage owners and fail-closed behavior at startup, every provider operation, and terminal evidence commits.

## Intent

### Problem being solved

The first hosted MVP must retain guide and Submission bytes in native AWS S3.
Main accepts a closed `aws_s3` configuration but rejects it with
`artifact_provider_live_proof_required`. The rejection is correct until live
principal, policy, namespace, immutability, private-access, retention and
exact-byte evidence exists; the current composition cannot consume such
evidence even if the intended environment supplies it.

### Why this work matters

Issue #582 is the storage prerequisite for the hosted #555 journey. MinIO proves
the protocol locally but cannot prove AWS identity, IAM/bucket enforcement or
retained provider custody. A configuration switch or narrative receipt would
make the current fail-closed boundary forgeable.

### Current behavior

- `backend/app/adapters/artifacts/__init__.py:74` owns the sole typed
  `ArtifactStore` factory. Its `s3_compatible` registration invokes only the
  MinIO bootstrap at lines 88-112, while `require_artifact_runtime_eligible`
  rejects every AWS profile at lines 115-123.
- `backend/app/adapters/artifacts/s3_compatible.py:411` already implements the
  shared immutable S3 byte adapter and derives an `aws-s3-v1` namespace at
  lines 497-514. Lines 960-1136 already validate a closed workload-identity
  environment and build an isolated resolver, but no AWS bootstrap composes it.
- `backend/app/modules/artifacts/service.py:437` remains the sole writable
  provider owner. It calls the store outside database transactions and commits
  receipts/replicas/verification evidence in fenced terminal transactions.
  Read owners also use the same provider-neutral port after exact namespace and
  lineage checks; examples include task guide reads at
  `backend/app/modules/artifacts/task_guide_documents.py:124`, guide setup reads
  at `backend/app/modules/artifacts/guide_document_access.py:78`, post-submit
  materialization at
  `backend/app/modules/artifacts/post_submit_materialization.py:285`, and task
  import reads at `backend/app/modules/artifacts/task_import_sources.py:346`.
- `docs/spec_artifact_storage_service.md:694` currently requires three separate
  live probe identities, append-only probe results, a credential-free
  coordinator and immutable activation. Lines 720-740 require the exact
  unexpired activation at startup, before each AWS operation, and again before
  terminal success evidence.
- No `ArtifactProviderProbeResult` or `ArtifactProviderActivation` model,
  migration, repository, coordinator, operation guard or deployment proof
  command exists on main.

### Target behavior

One deployment can run the three identity-separated live probes against its
approved private bucket, coordinate their exact matching immutable results, and
thereafter start API/worker/Beat and perform AWS artifact operations only while
the matching activation is fresh. Expiry, drift, partial proof, probe failure or
unknown provider outcome fails closed and cannot commit success evidence.

## Bounded change

### Allowed

- `.commitrail/changes/aws-artifact-provider-activation.md`.
- `backend/app/core/config.py` and `backend/.env.example`: non-secret, closed AWS
  activation bindings only (release digest, exact role/policy ARNs, reviewed
  role-trust-policy digests, expected bucket-policy digest and timeout
  invariants). No credential values.
- `backend/app/adapters/artifacts/__init__.py`,
  `backend/app/adapters/artifacts/s3_compatible.py` and
  `backend/app/adapters/artifacts/internal_workers.py`: complete the existing
  single typed S3 bootstrap, keep AWS credential resolution lazy until live
  activation has been checked, and compose one guarded store for API/worker
  owners.
- `backend/app/interfaces/artifacts.py`: define the dependency-safe typed
  activation guard/lease port and the minimum operation evidence needed to
  carry the first qualifying activation ID. The interface imports no ART model,
  repository or AWS implementation.
- New `backend/app/adapters/artifacts/aws_live_proof.py`: AWS-specific live probe
  transport and strict response/policy validation only; it may not own product
  rows or activation decisions.
- New `backend/app/modules/artifacts/provider_activation.py`, plus narrowly
  required additions to `models.py`, `repository.py` and `service.py`: immutable
  proof/activation custody, exact matching, per-operation leases and terminal
  revalidation under the existing ART owner.
- `backend/app/main.py`, `backend/app/workers/celery_app.py` and
  `backend/app/workers/artifacts.py`: activation-aware API, prefork worker and
  Beat entry boundaries; direct scratch cleanup remains provider-independent.
  Beat may use its startup signal; module import must not become a credential
  or provider probe.
- One additive Alembic revision after the current head for append-only probe and
  activation records, including database immutability and exact FK/check/unique
  constraints.
- New `backend/scripts/aws_artifact_provider_proof.py`: one focused internal
  deployment command with closed `readiness`, `runtime_immutability`,
  `negative_access` and credential-free `coordinate` modes. It writes only
  results derived by the command's actual calls; it accepts no caller-supplied
  pass result or activation override.
- Focused unit, real-PostgreSQL and existing S3/entry-point tests under
  `backend/tests/`; schema manifest/custody files only where the additive
  migration requires their normal update.
- `backend/app/modules/checkers/external_registry.py` and
  `backend/tests/checkers/external/test_postgresql.py`: preserve the exact
  shared `0051_operational_read_audit` prerequisite repair while stacking the
  provider proof migration after it; no registry behavior is otherwise in
  scope.
- `backend/scripts/test_lane_catalogue.py`,
  `backend/tests/test_ci_lane_catalogue.py` and
  `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: assign the new focused tests
  to the existing shared-foundation lanes and refresh only the existing,
  shrinking artifact-admission debt facts after rehoming terminal proof.
- `backend/scripts/behavior_ownership.py`,
  `backend/tests/test_behavior_ownership.py` and
  `.ci/behavior-ownership/partition.v1.json`: register only the three new
  activation/probe targets in the existing exact-target transition inventory;
  preserve all main assignments and regenerate its digest. Verify acceptance
  of those exact additions and rejection of neighboring unapproved targets and
  reassigned existing targets. No eligibility or validation relaxation.
- `README.md`, `docs/spec_artifact_storage_service.md`,
  `docs/operations_artifact_storage.md`, `docs/engineering/local-pilot.md` and
  `docs/roadmap_status.md`: exact
  configuration, proof, recovery, exposure and remaining hosted-proof claims.
  Local ignored XLSX/CSV exports must be updated together if the roadmap changes.

### Not allowed

- No AWS/IAM/bucket creation or mutation, live deployment, credential reading,
  secret logging, committed key, or cloud spend under this change authorization.
- No boolean/configuration flag, file, environment value or manually authored
  receipt that asserts proof or bypasses live probes; MinIO never satisfies AWS
  activation.
- No second adapter factory, provider discovery, concrete S3 import in a product
  service, compatibility constructor, direct SDK call from product lifecycle
  code, or provider-specific artifact identity.
- No product CLI/API/result-protocol change, generic deployment framework, CI
  workflow change, checker/runtime ownership from #583, or full #555 journey
  ownership.
- No object delete/overwrite cleanup, retained-data deletion, product-row repair,
  migration downgrade, restore-by-rebinding, or new artifact replacement path.

## Design and decisions

### Design chosen

Keep the existing ADR 0014 factory and `ArtifactStore` contract. Replace the
MinIO-only S3 constructor with one closed S3-compatible bootstrap that maps
`minio` to the existing static local session and `aws_s3` to the existing
isolated workload-identity resolver. The AWS bootstrap pins only non-secret
namespace facts until ART validates the matching activation; absent activation
therefore still fails before credential-environment inspection, resolver loading
or provider I/O.

ART owns two append-only record types from the canonical specification. Each
proof-only transport first binds its STS-observed caller to the configured
expected identity, performs only that mode's fixed calls and then commits a
bounded pass/fail result using PostgreSQL start/completion time. The common
nonce/run ID is a non-secret deployment-orchestrator input; it groups actual
observations and cannot assert pass. The proof transport is composed only by the
deployment script, is never injected into product services or the production
`ArtifactStore`, and has a negative architecture test protecting that boundary.
The first proof calls do not require a pre-existing activation. The
credential-free coordinator loads exactly one unexpired result of each type and
writes an activation only when release, namespace, account, region, role and
policy ARNs, bucket-policy digest, nonce, proof-suite version and expiry all
match. Database constraints/triggers reject mutation, deletion, cross-result
activation and duplicate semantic ownership.

Runtime proof is the only mode that creates and verifies the common-nonce
challenge object. Coordination therefore also requires runtime proof to finish
before readiness and negative-access proof start:
`runtime.completed_at <= readiness.started_at` and
`runtime.completed_at <= negative.started_at`. ART checks this before writing
an activation, and the activation trigger independently rejects direct SQL that
violates either ordering rule. This keeps known-object denial distinct from the
missing-key `403` that S3 may return to principals without `ListBucket`.

The fixed command accepts no caller-supplied observation or pass value, and no
product/API/configuration path can create proof or activation rows. The trusted
deployment proof process, its database writer credential and database
administrators are the v0.1 trust root for those rows; v0.1 does not claim
resistance to a malicious holder of that credential. A separate database role
or external attestation mechanism would change that trust boundary and is not
introduced here.

Define a typed `ArtifactProviderActivationGuard` port in the provider-neutral
artifact interface and inject its ART-owned implementation into the existing
AWS bootstrap/adapter. The implementation reads PostgreSQL through its own
short-lived session; the adapter imports no ART model, repository or service.
The first AWS SDK call in one logical store operation asks the guard to select a
matching activation with enough remaining PostgreSQL-time TTL and returns its
ID. Every later SDK call in that operation reloads that exact ID immediately
before the call. This includes nested head/get calls inside `open`, replay and
timeout recovery. `open` performs its first check when its iterator is consumed,
not when the iterator object is constructed. Provider operation evidence and
errors carry the first activation ID without exposing AWS details.

Writable orchestration passes that captured activation ID into every existing
transaction that would store a provider-derived receipt, replica, verification
result, audit success or terminal outcome. The transaction reloads that exact
activation using PostgreSQL time before persisting success, missing,
`integrity_mismatch`, conflict or other provider-derived facts. Expiry after a
possibly successful put leaves the existing attempt recoverable/
acknowledgement-unknown; other expired observations become recoverable provider
unavailability. No path fabricates absence, success or rollback. Direct readers
receive the same guarded AWS adapter, so their four current `open` call sites
cannot bypass the check. Local and MinIO do not construct or call the AWS guard
and retain their present behavior.

Five-minute refresh intentionally creates overlapping unexpired 15-minute
batches. The coordinator matches exactly one result of each required probe type
within one common nonce/group and rejects mixed groups, releases, namespaces,
policies, roles, versions or time windows. Its unique semantic tuple includes
the group identity and the exact three result IDs; it does not require only one
globally unexpired result. The runtime guard deterministically selects an exact
eligible activation by latest expiry, then activation time and ID, and returns
that ID for the operation.

The fixed v0.1 clock safety margin is 30 seconds. The call-time guard requires
`remaining_ttl >= max(operation_total_deadline, complete_read_deadline) +
terminal_persistence_margin + 30 seconds`. To remain usable until the next
five-minute refresh, AWS-only settings validation also requires that same bound
to fit within `15-minute validity - 5-minute refresh interval`. Native AWS stays
invalid under the current 1,800-second development operation default until #583
supplies a smaller measured deadline. Local and MinIO settings are unchanged.

The live readiness probe validates the exact runtime/readiness/negative roles,
their reviewed trust-policy digests and disjoint closed workload subjects, the exact
managed policies, closed bucket policy, Block Public Access, owner-enforced
ownership, SSE-S3, versioning/retention and every lifecycle rule intersecting
the completed prefix. Runtime proof uses the deployed runtime identity for a
conditional content-addressed write, exact head/readback, replay, unconditional
overwrite denial and missing-key 404. Negative and anonymous proof deny known-
object read/write/delete. Evidence digests are bounded and contain no raw AWS
response, object locator beyond the proof challenge, token or credential.
Each five-minute group intentionally retains one 49-byte challenge in the exact
production content-addressed namespace so the proof exercises the production
resource policy and no-expiry lifecycle. These proof objects create no product
binding or receipt. Hosted operations must account for approximately 105,120
such objects and 5.15 MB of payload per year; they are not orphan-cleanup or
retained-data deletion candidates.

Final product custody proof reuses the hosted #555 public journey rather than
adding a second lifecycle harness. #582 remains incomplete until that run shows
real guide and Submission bytes, exact digest/size and recoverable failure facts
through the activated AWS path. #583 owns scheduling/topology and backup/restore
execution; this change owns the activation checks they invoke.

### Alternatives considered

- A static `live_proof=true` setting or mounted receipt: rejected because it can
  assert success without AWS observation.
- Startup-only runtime-principal probing: rejected because it cannot prove
  private access, IAM/bucket drift, lifecycle retention or unrelated-principal
  denial, and long-lived processes would outlive proof.
- One process assuming all proof roles: rejected because credential switching
  destroys independent identity evidence.
- Historical XINT activation chunks: rejected as implementation authority; the
  merged ART factory, ART service/read owners, current canonical specification
  and current tests define this plan.
- An activation-only schema PR followed by runtime wiring: rejected because the
  first PR would create unconsumed proof machinery and no usable safe path.

### Boundaries preserved / what must not change

ART remains the storage/evidence owner; ADR 0014 retains one explicit typed
factory. Namespace lineage, server-derived content keys, conditional writes,
independent digest/size verification, authorization, scratch limits, atomic
terminal facts and retained bindings remain unchanged. AWS proof grants no
product authority and never creates or changes a Submission, Review,
ContributionRecord or award.

### Expected risks

This is an L1 storage/security/schema change. The main risks are accepting a
stale or mismatched proof, checking only startup while a process remains live,
committing success after expiry, credential/provider response leakage, widening
AWS permissions, accepting a known-object denial before the challenge exists,
and missing a direct-read call path. Crossed expiry and unknown write outcomes
require real PostgreSQL concurrency tests.

## Acceptance criteria

- [x] Native AWS remains denied before credential inspection/provider I/O when
  any proof is absent, failed, stale, expired or mismatched; API, worker, Beat
  and each AWS SDK call follow the same rule. Nested head/get,
  replay/recovery and consumed `open` streams cannot bypass the guard.
- [x] The sole existing typed factory constructs MinIO or the native AWS adapter;
  no duplicate factory/constructor path exists and Local/MinIO behavior remains
  covered.
- [x] Probe and activation rows are immutable, secret-free, namespace/release/
  role/policy/time-bound and cannot be activated from mixed, replayed, expired or
  public/product/configuration-authored results. The trusted proof process and
  database writers remain an explicit v0.1 trust boundary.
- [x] Coordination and its database trigger require runtime proof to complete
  before readiness and negative-access proof start, so a missing-key `403`
  cannot satisfy known-object denial. Focused service and direct-SQL tests reject
  both out-of-order variants and retain a valid runtime-first control.
- [x] Every AWS SDK call requires sufficient PostgreSQL-time TTL; the first
  qualifying activation ID is retained across the operation and that same ID is
  rechecked before every provider-derived terminal fact, including success,
  missing and integrity mismatch. Expiry and unknown writes retain recoverable
  state with no false absence or success.
- [x] Overlapping refresh batches are valid. Coordination accepts one exact
  three-probe common-nonce group and rejects mixed nonce/result groups; runtime
  selection is deterministic and returns the exact selected activation ID.
- [x] Runbook documents non-secret prerequisites, five-minute proof execution,
  expiry/recovery, evidence inspection and the approved backup/restore boundary.
  Logs/reports contain no credentials, raw provider responses or private product
  bytes.

### Later environment proof

The bounded source implementation is complete. These environment-dependent
gates remain deliberately unchecked and are outside this PR's authorized proof
scope; they prevent claiming issue #582 or any AWS environment ready.

- [ ] Live readiness proves the approved principal/action/resource and bucket
  policy matrix, public denial, encryption/ownership, retention/lifecycle and
  bootstrap-principal denial; runtime, readiness, negative and anonymous live
  calls prove their distinct expected outcomes without role switching.
- [ ] Live runtime proof establishes conditional no-overwrite, exact digest/size
  readback, replay, missing-key classification and preservation after denied
  overwrite. Failed credential/access/interrupted/duplicate cases fail safely.
- [ ] The hosted public journey stores and rereads genuine guide and Submission
  bytes through AWS and retains exact Workstream custody/evidence; MinIO or a
  direct SDK product write cannot satisfy this criterion.

## Risk and review routing

- Risk class: L1.
- Work type: storage security, schema, infrastructure integration and operations.
- Required reviewers: `architecture`, `security`, `qa`, `test_delta`,
  `reuse_dedup`, `senior_engineering`, `documentation`, and `product_ops`.
  `ci_integrity` also reviews the exact behavior-ownership inventory additions
  and their focused transition proof; workflows remain prohibited.
- Resolved design input: the narrow IAM inspection clarification below is part
  of this bounded change. The current session authorizes bounded offline MVP
  work; it does not authorize the later named live AWS/database proof run.
  Deployment/resource/IAM mutation and merge remain separate approvals.
- Budget posture: one cohesive end-to-end slice, subject to the focused
  architecture review below. Any implementation must remain the smallest
  current vertical boundary; it may not revive historical XINT machinery or
  land inactive persistence/probe pieces that no runtime owner consumes.
- Human review focus: proof cannot be asserted, every direct AWS call is gated,
  terminal facts recheck the same activation, role permissions remain closed,
  and no #583 deployment ownership or #555 product lifecycle is duplicated.
  "Proof cannot be asserted" means no public, product, CLI-argument or
  configuration input can supply a pass; the trusted proof process and database
  writer boundary above remains explicit.

## Resolved IAM contract clarification

The readiness role may call `iam:GetRole`, `iam:ListRolePolicies` and
`iam:ListAttachedRolePolicies` on the exact configured runtime, readiness and
negative role ARNs, plus `iam:GetPolicy` and `iam:GetPolicyVersion` on the exact
required runtime and readiness managed-policy ARNs. This is sufficient to prove
the already-required absence of extra attached or inline policy, including that
the negative role has neither. It permits no arbitrary role enumeration,
mutation, broad principal authority or live IAM call under the current offline
authorization. Update the contradictory canonical matrix/sentences in this same
change; code must not infer policy absence.

The no-rebinding boundary is already normative: #582 documents and verifies
environment backup/restore without adding an in-product object replacement or
rebinding route.

## Later live-run prerequisites

- #583 supplies one immutable release digest, the exact intended role/policy
  ARNs, expected bucket-policy digest and measured AWS operation/read deadlines
  satisfying the AWS-only TTL inequality. `app_version=0.1.0` is not a
  deployment identity.
- Before live proof, the user authorizes the named target environment, AWS calls
  and activation-row writes. Current offline implementation authority does not
  authorize those external effects.

## External facts required (names only)

- immutable deployed release/image digest;
- AWS partition, account ID and region;
- dedicated artifact bucket name and private completed-object prefix;
- runtime role ARN and runtime managed-policy ARN;
- readiness role ARN and readiness managed-policy ARN;
- negative-test role ARN;
- infrastructure bootstrap principal ARN used only for policy evaluation;
- canonical bucket-policy digest;
- canonical reviewed runtime, readiness and negative role trust-policy digests;
- selected runtime workload-identity method;
- independent readiness-job and negative-job OIDC issuer/audience/service-account
  identities, plus the runtime executor's exact OIDC subject or closed EC2 VM
  service trust;
- measured connect, pool, read, write, whole-operation, complete-read and
  terminal-persistence deadlines;
- bucket versioning state, encryption mode, ownership-control state, public-
  access-block state and lifecycle/retention rules;
- environment backup mechanism, recovery objective and restore drill target;
- PostgreSQL target used for immutable proof rows and credential-free
  coordination.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current composition/guard traced | Source inspection at base `34501cd64` | AWS adapter/resolver foundations exist; factory is MinIO-only and AWS is denied before factory construction | No live AWS observation |
| Current provider call owners traced | `rg` over every `ArtifactStore` consumer and ART composition root | Writable calls remain in `ArtifactStorageOrchestrator`; four current direct-read owners also require gating | Implementation must keep this inventory closed |
| Normative activation contract traced | `docs/spec_artifact_storage_service.md:694-740` | Three live probes, immutable activation, per-I/O and terminal checks are current canonical requirements; the exact-role IAM inspection contradiction is resolved above | Measured AWS deadlines remain a later live-run prerequisite |
| Offline static proof | `py_compile`; focused Ruff; `git diff --check`; stale-wording, stale artifact/authorization contract and changed-Markdown-link checks | Initial candidate passed all checks; repaired source and all five new test modules pass `py_compile`, focused Ruff and `git diff --check`; all named documentation checks pass | Live AWS proof remains a later deployment gate |
| Offline behavior proof | Focused activation/config/startup/factory pytest batches | Initial candidate: 230 passed and seven failed; the seven repaired cases then passed. At clean source `159003fce`, one exact-head selection covering the original affected set plus native proof transport/CLI passed 278 tests with no failures, errors or skips in 164.39 seconds; lane-catalogue contract 58 passed; all nine moved terminal-test cases pass `--setup-plan` fixture closure | Live AWS proof remains a later deployment gate |
| Review repair proof | Focused exact trust-policy selection; direct-SQL test setup plan; Alembic graph/revision scan; isolated PostgreSQL batches | Closed trust grammar and IAM placement: 14 passed, followed by the three-case issuer/account scope addendum. At clean `2e4a71819`, the combined `0052` schema fingerprint is `0f38f0705b0aae59b40e1d873932c6710c2f56f2e58647f9911ae2f15deaf7e9`; hostile-search-path migration, two-loop guard, direct role/trust/principal SQL denials and put/missing/mismatch crossed-expiry terminal cases passed 8/8 in 292.96 seconds. Canonical repaired `0051` passed its 0049/0050 resume and downgrade-refusal selection 3/3; the stacked exact `91002c941` regression rebuilt `0051`, proved downgrade refusal without mutation and restored `0052` in 121.47 seconds. All isolated database cleanup completed. The graph has one `0052` head through canonical operational-read `0051` and contributor-read `0050`, and all 52 revision IDs fit the 32-character version column | Live AWS proof remains a later deployment gate |
| CI/test metadata proof | `python -m scripts.test_structure_boundary validate ...`; `pytest -q tests/test_ci_lane_catalogue.py`; AST comparison of the three moved functions; ownership partition generation | Debt transition passes while `test_artifact_admission.py` shrinks from 2,779 to 2,593 lines; 58 lane tests pass; all three moved function ASTs are identical. Latest-main reconciliation retains 529 exact ownership assignments with the existing protected base and adds the three S3 targets on top of the canonical registry/main inventory. Final architecture/documentation/CI and security/QA/test-delta reviews passed against the exact reconciled source tree. | Live AWS proof remains a separate deployment gate. |
| Post-review proof-order repair | Focused nodes `test_activation_rejects_probes_started_before_runtime_completed` and `test_activation_trigger_rejects_probes_started_before_runtime_completed`, each parameterized for readiness and negative access, plus the existing runtime-first overlapping-group control | At clean `7a97a0199`, the regenerated combined `0052` fingerprint is `444c180e173fb00f85eb376c53fb5faa1dc36964406e0d0a91beb0231bde69e3`; service and direct-SQL counterexamples plus the runtime-first control passed 5/5 in 84.28 seconds. Isolated database cleanup completed. Evidence: `/tmp/mvp-s3-582-order-final.ySd4px`; stdout SHA-256 `25534542b11d78ffbd2f2ca0c853a3d781a3e2025c4774cc5a3456363231b4e2`; JUnit SHA-256 `efc0010d37eb9bc74fca2bb23dc95fa1f556d24c86848a6745097a452bb39b4a` | No AWS call was needed; live AWS proof remains a deployment gate |
| Live proof | Three separately identified executors, credential-free coordination, then hosted public guide/Submission drill | Not authorized or run | Requires approved #583 environment and explicit live authorization |

The terminal-custody tests moved together from the oversized admission module;
their parameterized cases keep the same assertion bodies and fixture closure:

| Old node | New node |
|---|---|
| `tests/test_artifact_admission.py::test_activation_expiry_during_put_terminal_transaction_rolls_back_to_unknown` | `tests/test_artifact_provider_activation_terminal_postgresql.py::test_activation_expiry_during_put_terminal_transaction_rolls_back_to_unknown` |
| `tests/test_artifact_admission.py::test_checker_output_shared_put_and_verification_lifecycle` | `tests/test_artifact_provider_activation_terminal_postgresql.py::test_checker_output_shared_put_and_verification_lifecycle` |
| `tests/test_artifact_admission.py::test_checker_output_put_observation_terminal_outcomes` | `tests/test_artifact_provider_activation_terminal_postgresql.py::test_checker_output_put_observation_terminal_outcomes` |

The crossed-expiry test uses the normal production minimum-TTL selection path,
then shortens only its copied Settings deadlines and the test-local fixed clock
margin so real PostgreSQL time reaches terminal expiry. Production retains the
30-second fixed margin and its separate boundary test.

## Review findings

The pre-implementation focused architecture review closed its substantive
findings against plan bytes
`cf916900c8545a6a44a85ac91ca8b188108e0a198e9f13653ea1f1783c224672`.
It required per-SDK-call same-ID gating, commit-near checks for every provider-
derived terminal fact, overlapping proof groups, a non-circular proof-only
transport, and the exact narrow IAM inspection matrix now implemented by this
record. The protocol verdict remained provisional only because that plan was
then untracked; implementation review must bind to the eventual clean candidate.
No historical XINT plan is treated as authorization or copied without current
owner proof.

The first clean implementation review at `332549d05` found that the recorder
and database did not bind probe type to its configured role, the persistent
Celery store retained the initialization loop's session factory, readiness did
not validate role trust policy, ORM metadata drifted from the migration, and
transport/CLI, SDK-call and crossed-expiry coverage was incomplete. It also
identified contradictory startup/direct-cleanup wording and missing evidence
inspection and restore boundaries. The current repair derives and enforces the
probe principal in ART and PostgreSQL, resolves worker guards through the
current loop owner, binds three exact reviewed trust-policy digests and
disjoint workload subjects into activation, reconciles schema metadata, adds
the focused regressions, and corrects the documentation. Those tracks were
replayed against `159003fce`. Architecture, CI and test-delta found no further
source blocker, while security found that the trust parser still accepted
negative and unsupported principal semantics and that PostgreSQL did not
enforce pairwise-distinct role/digest tuples. This repair closes the parser to
one exact OIDC shape, adds matching model/database constraints and direct-SQL
proof, and fixes the local-pilot constructor example. The real PostgreSQL
batch at `2e4a71819` proves the migration, database constraints, per-loop guard
and crossed-expiry rollback boundaries; it does not establish live AWS
readiness. The supported trust grammar retains the current Linux VM path:
runtime may use the closed `ec2.amazonaws.com` service trust while readiness
and negative jobs require exact, disjoint OIDC subjects.

Human review of the ready candidate identified that the runbook's runtime-first
proof sequence was not enforced by ART or PostgreSQL. A denial probe could
therefore run before the challenge existed and misclassify S3's missing-key 403
as known-object denial. The coordinator and existing `0052` activation trigger
now enforce runtime completion before readiness and negative start. Focused
service and direct-SQL counterexamples reject each out-of-order probe, while a
runtime-first group remains valid. The same review clarified two existing trust
boundaries: the proof process and database writer are trusted in v0.1, and each
five-minute group intentionally retains one small challenge in the production
no-expiry namespace. The repair adds no role, privilege system, prefix,
lifecycle exception or retained-data cleanup.

Focused regressions must independently prove: a guard immediately before nested
SDK calls; `open` guarding at iterator consumption; same-ID terminal rechecks
for success, missing and integrity mismatch; crossed expiry and unknown write;
overlapping-batch coordination; mixed nonce/result rejection; and each direct
read owner. These are separate failure boundaries, not one broad mock graph.

## Reconciliation

- Current-source reconciliation: the implementation began at `34501cd64` and
  has been reconciled against `origin/main` at `60e6302f5`, which includes the
  merged canonical #589 migration. Issue #583 is
  parallel and owns hosted process topology,
  scheduling and backup execution. Merged PR #577 owns contributor-read
  migration `0050`; the canonical operational-read audit migration owns
  `0051`, and this provider-proof migration chains after it as `0052` without
  making the product features depend on each other. The repaired `0051` source
  is exact ancestry through current main; its upgrade DDL is unchanged, its downgrade
  refuses without mutation, and the stacked regression restores the current
  `0052` head. The current combined `0052` fingerprint is `444c180e...` after
  adding the proof-order trigger invariant; baseline and `0051` fingerprints
  remain owned by their existing graphs.
- Next usable boundary: after human merge and deployment, request the precise
  live environment authorization/facts listed above and run the live probes
  plus the hosted public custody drill before claiming issue or environment
  readiness.
- Remaining risks: actual AWS readiness, product custody and restore evidence do
  not exist and must not be claimed from offline tests or MinIO.
