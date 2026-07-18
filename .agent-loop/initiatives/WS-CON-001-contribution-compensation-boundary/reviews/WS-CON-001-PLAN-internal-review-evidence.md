# Internal Review Evidence: WS-CON-001-PLAN

## 2026-07-17 AUTH And REV Current-Main Provenance Rebind

Reviewed code SHA: a69fad3a32ad47e3bd60a79cd75f5867eefc52b3
Reviewed at: 2026-07-17T18:14:54Z
Reviewer run IDs: auth08_arch_review/final-a69fad3, auth08_qa_product_review/final-a69fad3, auth08_security_review/final-a69fad3

This provenance-only addendum binds the earlier substantive PLAN review chain to
the final reviewed cumulative planning snapshot. PLAN3 authorizes this evidence
rebind because the PR-level gate validates every evidence file added by the
branch. It changes no historical finding or product conclusion. The exact-SHA
re-review confirmed that the merged AUTH runtime and REV plan, exact
FinalAcceptance/CON participant boundary, joint release-control contract,
CodeRabbit contract repairs, and evidence-schema update introduce no remaining
blocker.

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | None | The cumulative specification remains coherent after current-main and external-review repairs. |
| qa/test | PASS | None | Exact two-operation ordering, branch effects, rollback coverage, and deterministic gates pass. |
| security/auth | PASS | None | Current AUTH catalogue facts, prepared semantics, and AUTH-only identifier/evaluator/activation ownership pass. |
| product/ops | PASS | None | Review outcomes, FinalAcceptance lineage, contribution atomicity, release cutoff, and no-adjudication boundary pass. |
| architecture | PASS AFTER FIXES | None | Ownership, executable chunk gates, transaction, rollout, joint release control, and successor boundaries remain coherent. |
| ci integrity | PASS | None | The rebind changes evidence only; no CI, runtime, test, script, workflow, dependency, or threshold changes. |
| docs | PASS AFTER FIXES | None | Runtime-versus-planned identifiers, merged REV dependencies, CodeRabbit dispositions, and cumulative evidence provenance are explicit. |
| reuse/dedup | PASS | None | No duplicate service, evaluator, registry, or transaction abstraction is introduced. |
| test delta | PASS | None | No test delta; all 80 agent-gate tests pass. |

Valid findings addressed: yes

Open sub-agent sessions: none

## 2026-07-17 WS-XINT-001 Boundary Reconciliation

This addendum is the current authoritative review state and supersedes the
older policy-model, mandatory-evidence, service-assignment, partial-custody,
trusted-main, and chunk-order statements below. Trusted `main`
`5d353b6d3f8a36b9b9ffdc1959487a150ac25fd1` merges WS-XINT-001 PR #139.

Reviewed code SHA: `c4242e0b7c3441c23ce8b3a3facc45ae00de848a`

Reviewed non-review planning-tree SHA-256:
`586658fb55eadcc36f8095051ed7ff3281a714672456221de7d7041c6f040465`

The digest excludes `reviews/**` and is reproduced from the repository root:

```bash
find .agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary \
  -type f -name '*.md' ! -path '*/reviews/*' -print0 \
  | sort -z | xargs -0 sha256sum | sha256sum
```

Reviewed at: 2026-07-17T05:16:47Z

Reviewer run IDs: senior/architecture/reuse=`/root/auth08_arch_review`;
QA/test/product/ops/docs/test-delta=`/root/auth08_qa_product_review`;
security/auth/CI-integrity=`/root/auth08_security_review`

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | None | Operation-specific lifecycle-before-policy locking, chunk gates, and hidden-before-activation sequencing are executable. |
| QA/test | PASS AFTER FIXES | None | Contribution/award cardinality, exact uniqueness/enums, chunk file scopes, and deleted-contract evidence regressions are explicit. |
| security/auth | PASS AFTER FIXES | None | Human grants, fixed-service static authority, AUTH-only activation custody, callback isolation, and optional evidence separation are fail closed. |
| product/ops | PASS AFTER FIXES | None | Every valid human Review recognizes reviewer work; accept alone recognizes submitter work; policy, award, fulfillment, and legacy cutover boundaries are coherent. |
| architecture | PASS AFTER FIXES | None | ContributionPolicy is the eligibility aggregate, ART is absent from the core transaction, and dispatcher authority cannot leak to feature handlers. |
| CI integrity | PASS AFTER FIXES | None | Scanner changes are exact; deleted contract provenance is recovered index to HEAD to base; regular-file enforcement prevents path/symlink bypass. |
| docs | PASS AFTER FIXES | None | PR #139 precedence, optional evidence, complete ART/REV custody references, open AUTH decisions, and inherited loop-memory failure are truthful. |
| reuse/dedup | PASS AFTER FIXES | None | Existing AUTH kernel, static matrix, outbox, lifecycle, audit, adapter-factory, and PostgreSQL truth boundaries are reused. |
| test delta | PASS AFTER FIXES | None | Added regressions preserve failure for missing, malformed, unreadable, non-file, dangling/resolvable-symlink, pure-deletion, and replacement contracts. |

Open sub-agent sessions: none

Valid findings addressed: yes

- Replaced the obsolete policy model with `ContributionPolicy`, immutable
  `ContributionPolicyVersion`, exact `ContributionRule`, and
  `ContributionAwardDefinition`; `CompensationAward` is only the evaluated
  downstream result. PaymentPolicy has no compatibility path.
- Removed ART and evidence projection from the atomic Review-to-contribution
  transaction. CON copies the stabilized versioned `Submission.artifact_hash`;
  it does not introduce SubmissionVersion or make an ART/provider call.
- Fixed product cardinality: every valid committed human Review creates one
  reviewer `completed_review`; only `accept` additionally creates submitter
  `accepted_submission`; automated outcomes create neither.
- Replaced combined role semantics with independent exact `submitter`,
  `reviewer`, and `adjudicator` grants.
- Reconciled 22 core proposed ActionIds to existing stable PermissionIds where
  present. Policy actions use `contribution.policy.*` while retaining
  `compensation.policy.manage`; optional evidence and unapproved executor
  candidates are outside the core count.
- Fixed service authorization now requires provisioned ActorProfile/link,
  immutable closed ServiceIdentity, exact static matrix row, AUTH-09E, typed
  context, prepared mutation protocol, and later AUTH activation. There is no
  persisted service grant/action-assignment row.
- Kept complete 25-action ART and 19-action REV activation-custody transfer in
  WS-XINT/AUTH ownership. WS-CON references those complete handoffs and does not
  restate partial subsets.
- Split human operations requests/reads/drain observation in CON-10B from
  independently authorized async executors in new CON-10C. Outbox dispatch owns
  mechanics only and never grants delivery, callback, reconciliation, or
  rebuild authority.
- Deferred CON-09A/09B as optional successors. Neither ART nor evidence
  projection gates core reads, readiness, or joint REV/CON release.
- Repaired the internal-review evidence gate for renamed/deleted contracts:
  deleted headings are recovered from index, HEAD, then review base and retain
  their chunk ID; missing provenance, invalid content, non-regular files, and
  symlinks fail closed.

Deterministic evidence passed: Markdown links for 44 changed Markdown files;
stale Workstream wording; stale authorization documentation; stale artifact
contracts; `git diff --check`; Python compilation for all five changed gate
files; 80/80 agent-gate tests; trusted-main ancestry; no backend diff; exact
74 PermissionId / 57 ActionId / nine active / 48 planned runtime catalogue;
and the 22-action proposal audit. The repository-wide loop-memory check has one
inherited failure: merged `origin/main` leaves the unchanged WS-AUTH status at
the human merge checkpoint. WS-CON does not edit that externally owned file to
conceal the failure.

Application/runtime code changed: no. The original PDF deletion remains the
pre-existing unstaged user-worktree change and is excluded from both commits.

## 2026-07-16 ART-02A2 PR #129 And Exact Custody Reconciliation

This addendum is the current authoritative review state and supersedes older
trusted-main, ART readiness, REV worktree and ActionOwner statements below.
Trusted `main` `9a04434e2f23c5dec8939dadb943bba4d85110c0` merges ART-02A2 PR #129 and
includes AUTH-08 merge `aa0fdcd6912e66609e39a2fbd7b65f67be6c62f3`.

Reviewed code SHA: `5538e94a66718b867280f806c9beac97ac212972`

Reviewed non-review planning-tree SHA-256:
`b44c0685e842c57694ba0e3b4af34cbcdcaa6a423f965af3cd8d71f9fad9ea92`

The digest excludes `reviews/**` and is reproduced from the repository root:

```bash
find .agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary \
  -type f -name '*.md' ! -path '*/reviews/*' -print0 \
  | sort -z | xargs -0 sha256sum | sha256sum
```

Reviewed at: 2026-07-16T11:00:58Z

Reviewer run IDs: architecture/senior/reuse=`/root/auth08_arch_review`;
QA/test/product/ops/docs=`/root/auth08_qa_product_review`;
security/auth/privacy=`/root/auth08_security_review`

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS | None | Pre-lock preparation, bounded Transaction A, explicit caller commit and ART-owned post-commit execution form one executable protocol. |
| QA/test | PASS | None | Exact ART write/read/recovery/media/receipt gates and concurrent-sibling discovery rules are testable. |
| security/auth | PASS | None | All eleven ART-02D actions retain exact mappings and move to closed AUTH custody without dual availability writers. |
| product/ops | PASS | None | Contribution truth remains PostgreSQL-canonical and complete PaymentPolicy removal remains unchanged. |
| architecture | PASS | None | ART owns preparation/storage; AUTH owns registration/evaluators/availability; CON owns deterministic evidence facts only. |
| docs | PASS | None | PR #129 is described as inactive preparation only and later gates are named exactly. |
| reuse/dedup | PASS | None | Canonical ART scratch/preparation, AUTH D10, shared outbox, sessions and recovery paths are reused. |
| CI integrity | N/A - with approved reason | None | Planning Markdown only; no workflow, dependency, test, threshold or runner changed. |
| test delta | N/A - with approved reason | None | No runtime test file changed; focused merged-code tests are dependency evidence only. |

Open sub-agent sessions: none

Valid findings addressed: yes

- Classified merged ART-02A2 final head `32aab89262a3944f305e9e5dc4c65a2d31e2e144`
  correctly: inactive `ArtifactPreparationService`, canonical bounded scratch and
  sealed one-shot source only. ArtifactStore v1, providers, schema, admission,
  verification, binding, contribution behavior and authorization are unchanged.
- Replaced the unsafe long-lock draft with ART-owned pre-transaction
  `prepare_source`; locked AUTH -> CON -> ART staging and commitment
  revalidation; caller-owned commit; a fresh committed-attempt claim; and
  one-shot provider I/O outside every database transaction. Rollback,
  cancellation, process loss, stale cleanup, acknowledgement loss and
  deterministic replay serialize no scratch handle and retain cleanup custody
  fail closed when release cannot complete.
- Made the dependency chain exact: AUTH-09 fixed identities/assignments; ART
  02A2 -> 02A3 -> 02B1 -> 02C1 -> 02C2 -> 02C3 -> hidden 02D behavior;
  AUTH-owned Operator/internal evaluator activation; then the separately
  approved `WS-ART-001-CON-EVIDENCE` write/read ports. CON-09A, 09B and 11 gate
  the exact owning symbols separately.
- Froze media type
  `application/vnd.workstream.contribution-evidence+json;version=1`, zero-I/O
  rejection for invalid media or digest/size mismatch, and exact returned
  binding/receipt digest, size, media, owner, project, role, schema and
  idempotency validation before projection success.
- Extended D12 without changing canonical identifiers. All eight current
  Operator-facing `ART_02D` ActionIds retain their existing PermissionIds under
  proposed `AUTH_ART_02D_OPERATOR`; all three internal ActionIds retain theirs
  under `AUTH_ART_02D_INTERNAL`. In the recommended model, AUTH atomically
  removes now-unused `ART_02D` and `REV_08`, retains `REV_06`, and preserves
  `{definition.owner} == set(ActionOwner)` across typed/SQL/audit parity. The
  global alternative must keep feature owners and add a separate exact closed
  activation-custody catalogue; mixed models and dual writers are forbidden.
- Preserved AUTH ownership. ART-02D supplies hidden feature/resource behavior
  only; AUTH-09 owns service identities/assignments and later AUTH chunks alone
  integrate evaluators and change availability. The three internal actions do
  not imply Operator `artifact.verification_job.retry`, and the later
  contribution binding action cannot substitute for either authority family.
- Inspected REV evidence-bound baseline `6faccc0`, then observed its owner begin
  later external-review repairs. The live sibling is discovery only and is not
  pinned by WS-CON verification; only a reviewed merge on trusted `main` may be
  consumed.

Deterministic evidence passed: `git diff --check`; Markdown links for 38 changed
Markdown files; stale Workstream wording; artifact-contract and loop-memory
state; 71 agent-gate tests; seven focused ART commitment/single-stream/
cancellation/cleanup tests; exact trusted-main ancestry; no backend diff;
direct proof of all eleven current `ART_02D` ActionId -> PermissionId mappings;
and exact proposed owner/removal/parity assertions. The authorization stale-doc
scanner continues to flag exactly ten `HUMAN_WORKER_VOCABULARY` occurrences in
the explicitly non-canonical generation-2 working transcription. CON-01 owns
its byte-preserving archive classification and active-spec reconciliation; no
active documentation waiver was added.

Application/runtime code changed: no. The original PDF deletion remains the
pre-existing unstaged user-worktree change and is excluded from the reviewed
content/evidence commits.

## 2026-07-16 AUTH-08 And Parallel-REV Reconciliation

This addendum is the current authoritative review state and supersedes older
AUTH counts, trusted-main SHAs, ActionOwner assumptions, role-candidate outcomes
and REV freshness statements below. Trusted `main`
`aa0fdcd6912e66609e39a2fbd7b65f67be6c62f3` includes AUTH-08 through PR #131.

Reviewed code SHA: 9df6eace4921755cdd39759cece8e49c9a885382

Reviewed planning-tree SHA-256:
`7c49d006f505fe923e0194e1331e6e9ab7fb7da36ff506c8785f3c955ec2e372`

The tree digest excludes this evidence file and is reproduced from the
initiative directory with:

```bash
find . -type f ! -path './reviews/WS-CON-001-PLAN-internal-review-evidence.md' -print0 | sort -z | xargs -0 sha256sum | sha256sum
```

Reviewed at: 2026-07-16T09:17:13Z

Reviewer run IDs: architecture/senior/reuse=`/root/auth08_arch_review`;
QA/test/product/ops/docs=`/root/auth08_qa_product_review`;
security/auth/privacy=`/root/auth08_security_review`

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS | None | Chunk gates, conditional human decisions, exact ownership and operational commit boundaries are coherent. |
| QA/test | PASS | None | AUTH/source/REV freshness assertions, conditional role outcomes, chunk-local evidence and release proof are executable. |
| security/auth | PASS | None | D10, D11, D12, exact matched evidence, service separation and no-CON-auth boundaries are fail-closed. |
| product/ops | PASS | None | PaymentPolicy removal remains complete; delivery/award/audit role conflicts remain explicit human decisions rather than silent policy. |
| architecture | PASS | None | All 23 actions map once to proposed activation custody; feature ownership, AUTH activation, route commits, ART and outbox boundaries do not cross. |
| CI integrity | N/A - with approved reason | None | Planning Markdown only; no workflow, dependency, runner, threshold, test or coverage configuration changed. |
| docs | PASS | None | Main, source hashes, clean REV head, planning-versus-runtime language and blockers are truthful. |
| reuse/dedup | PASS | None | One prepared D10 protocol and existing AUTH grant, outbox, ART, session, fence and composition abstractions are reused. |
| test delta | N/A - with approved reason | None | No runtime test file changed; every later runtime chunk retains test-delta review and isolated evidence gates. |

Open sub-agent sessions: none

Valid findings addressed: yes

- Rebased the branch onto merged AUTH-08. Canonical main now has 74
  PermissionIds, 57 ActionIds, nine active self/admin actions, 48 planned
  actions, eight resource-context variants and actor-self/AdminRoleGrant matched
  authorities. All 23 proposed WS-CON actions, both proposed service permissions
  and the upstream `task.claim` ActionId remain absent.
- Reused AUTH-08's resource-context digest, matched grant/project evidence,
  rollback-only dependency teardown and typed retryable evidence-failure path.
  Hidden domain services flush without committing; every actual route owns its
  complete decision/business transaction. The service callback commits its
  decision, receipt and idempotency state atomically inside its fence.
- Kept D10 AUTH-owned and single-use: authority locks first, final product facts
  are evaluated once, AUTH stages one decision and never commits, and CON never
  queries AUTH state or supplies role policy.
- Added D11 as an unresolved human cross-spec decision. Merged AUTH gives
  Finance—but not Operator—delivery-reconcile candidacy and gives Project
  Manager the broad award-read candidate; audit candidates also differ. Later
  gates support either human outcome and require only the AUTH amendments or
  CON-01 active-matrix changes that outcome selects.
- Added D12 because canonical ActionOwner means the chunk allowed to activate.
  The recommended model proposes eight exact AUTH activation owners mapping all
  23 WS-CON actions once plus two AUTH review-action custodians. The globally
  reviewed alternative must add a separate closed activation-custody type.
  Missing, dual or feature-side activation custody is forbidden.
- Moved role-selection and negative grant tests to AUTH activation. CON chunks
  validate typed decision causation against canonical product facts and do not
  grow role-aware fakes or a second policy engine.
- Refreshed the parallel REV dependency to clean committed head
  `a13bf352147cbb2c65742802e7c74a9478e5013b`. Its AUTH-08 dependency review is
  accurate, but it remains non-consumable pending ART/final evidence plus
  review choreography, D12 custody and handler-claims-OutboxEvent repair.
- Preserved the human-approved complete PaymentPolicy semantic cutover in
  CON-05A and physical removal in CON-05B. Only legacy-row treatment remains a
  separate human decision.

Deterministic evidence passed: `git diff --check`; Markdown links for 38 changed
Markdown files; stale Workstream wording; artifact-contract and loop-memory
state; 71 agent-gate tests; two focused synchronous AUTH catalogue/role-policy
tests; exact trusted-main ancestry; all three WS-CON source hashes including the
tracked original through `git show`; clean REV head assertion; direct AUTH
catalogue/runtime/role assertions; and exact D12 23/23 unique owner coverage.
The two focused AUTH tests emitted only expected environment warnings because
the local system interpreter lacks the async pytest plugin; no async test was
claimed. The authorization stale-doc scan continues to flag exactly ten
`HUMAN_WORKER_VOCABULARY` occurrences in the explicitly non-canonical working
transcription. CON-01 owns its byte-preserving archive classification and
active-spec reconciliation; this is not a waiver for active documentation.

Application/runtime code changed: no. The original PDF deletion remains the
pre-existing unstaged user-worktree change and is excluded from the reviewed
content/evidence commits.

## 2026-07-15 AUTH-07B Executable-Boundary Reconciliation

This addendum is the current authoritative review state. It supersedes the
older trusted-main SHA, AUTH runtime assumptions, activation choreography and
parallel-REV freshness statements below. The reviewed plan is based on trusted
`main` `90eca12f6398f2ef168e634244d912765572c3e5` (merged AUTH-07B).

Reviewed code SHA: 31f7350be4a964faed4f3f0487a53de65c3f6840

Reviewed planning-tree SHA-256:
`07f8ed891ff15302b7b1a8e223cc122d98298d99ab0dd35660699866fff63cac`

The tree digest excludes this evidence file and includes the final initiative
status. It is reproduced from the initiative directory with:

```bash
find . -type f ! -path './reviews/WS-CON-001-PLAN-internal-review-evidence.md' -print0 | sort -z | xargs -0 sha256sum | sha256sum
```

Reviewed at: 2026-07-15T20:22:23Z

Reviewer run IDs: architecture/senior/reuse=`/root/plan_arch_senior`;
QA/test/product/ops/docs=`/root/plan_qa_product_docs`;
security/auth/privacy=`/root/plan_security_auth`

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS | None | Activation waves, prepared mutation seams, transaction ownership and chunk boundaries are executable. |
| QA/test | PASS | None | Local gates, failure cases, races, real-kernel denial and post-activation proof are explicit. |
| security/auth | PASS | None | Canonical identifiers, grants, fixed service identities, one-decision semantics and AUTH-only activation are coherent. |
| product/ops | PASS | None | Complete PaymentPolicy removal, legacy-row human gate, callback/delivery behavior and release dependencies remain explicit. |
| architecture | PASS | None | Review choreography is non-circular; outbox, ART, REV, AUTH and CON ownership boundaries do not cross. |
| CI integrity | N/A - with approved reason | None | This delta changes planning Markdown only and does not modify CI, dependencies, tests or coverage gates. |
| docs | PASS | None | Trusted-main facts, sibling freshness, source provenance, blockers and ownership language are truthful. |
| reuse/dedup | PASS | None | The plan reuses the central prepared protocol, shared dispatcher, ART capability, `workstream.artifact.binding` and existing grants/permissions. |
| test delta | N/A - with approved reason | None | No runtime test file changed; every later runtime chunk still requires test-delta review and retained evidence. |

Open sub-agent sessions: none

Valid findings addressed: yes

- Recorded the exact merged AUTH-07B state: 74 PermissionIds, 50 ActionIds,
  two active and 48 planned actions. All 23 proposed WS-CON ActionIds remain
  absent. The two proposed service-only PermissionIds remain absent.
- Kept authorization implementation entirely AUTH-owned: catalogue/owner/audit
  parity, closed typed contexts, evaluator dispatch, matched authority, grant
  loading/revalidation, service actors/assignments, composition dependencies and
  availability changes.
- Added an AUTH-owned D10 prepared-mutation protocol for every `T` operation:
  authority rows lock first, an opaque caller-session-bound handle is finalized
  once against locked product facts, one decision is staged, and AUTH never
  commits. Missing, reused, mismatched and cross-session/action handles deny.
- Repaired activation into registration -> hidden fail-closed feature behavior
  -> AUTH evaluator/activation waves. Review actions add the required REV-owned
  composition stage: AUTH registration -> CON capability/participant -> REV
  hidden composition while planned -> AUTH activation -> later readiness/public
  activation.
- Added the missing upstream dependency that `task.claim` has an existing
  PermissionId but no ActionId. AUTH-13 or a reviewed AUTH successor must order
  registration/typed-prepared contract, task resource behavior and evaluator/
  activation before CON-05A.
- Required the callback ActionId/new PermissionId and active binding-specific
  service actor/link/exact assignment before CON-04A so binding creation is
  executable while the callback action remains planned. Binding retirement
  remains planned until its CON-10B dependency guards exist and a later AUTH
  gate activates it.
- Put the D10 call site in CON-02B before OutboxEvent claim and made the active
  `outbox.dispatch` evaluator/assignment proof a local CON-08A gate.
- Repaired evidence ownership: CON prepares authority and locks only CON facts;
  ART locks/composes admission facts and performs the one final evaluation in
  durable Transaction A without commit/provider I/O. Provider continuation is
  post-commit under ART authority. The exact action reuses the existing fixed
  `workstream.artifact.binding` principal and existing
  `artifact.binding.create` PermissionId.
- Recorded sibling REV head `e59e2bbe823bc0ee2b0e59ff35f8352349618b2e`
  as non-consumable until its AUTH-07B choreography, outbox claim wording,
  source SHA and commit-bound evidence are refreshed and reviewed.
- Preserved the approved complete PaymentPolicy semantic cutover and physical
  removal. Only the legacy-row rebuild-versus-classified-backfill choice remains
  a human decision.

Deterministic evidence passed: `git diff --check`; Markdown links for 38 changed
Markdown files; stale Workstream wording; artifact-contract state; loop-memory
state; 71 agent-gate tests; and direct AUTH catalogue/runtime assertions for the
counts, availability, absent WS-CON IDs, absent service permissions,
`task.claim`, resource variants and matched-authority state. The authorization
stale-doc scan continues to flag exactly ten `HUMAN_WORKER_VOCABULARY`
occurrences in the explicitly non-canonical working transcription; CON-01 owns
its exact byte-preserving archival rename/classification and active-spec
reconciliation. This is not a waiver for an active document.

The focused async AUTH test environment was unavailable at final rerun because
this worktree's `backend/.venv` lacked an interpreter/plugin installation. That
does not weaken the planning proof: runtime files are byte-unchanged from
trusted main, the catalogue assertion passed with the available interpreter,
and no runtime completion is claimed.

Application/runtime code changed: no. The original PDF deletion remains an
unstaged user-worktree change and is excluded from both reviewed commits.

## 2026-07-15 Final Trusted-Main And Parallel-Dependency Review

This addendum is the current authoritative review state and supersedes older
statements below about D2, AUTH-07A merge status, REV joint-release adoption, or
an uncommitted planning candidate. D2 is approved:
`CompensationPolicyVersion` completely supersedes `PaymentPolicy`; only the
legacy-row reset-versus-classified-backfill rule remains a human gate.

Reviewed code SHA: ebdd21d231207845d44832a502de9dc56f237fd9

Reviewed planning-tree SHA-256:
`c3a82c1d5db19038709ff844a3bbde6cc77b21d525f408f2768d71c34883181d`

The tree digest excludes this evidence file and is reproduced from the
initiative directory with:

```bash
find . -type f ! -path './reviews/WS-CON-001-PLAN-internal-review-evidence.md' -print0 | sort -z | xargs -0 sha256sum | sha256sum
```

Reviewed at: 2026-07-15T17:08:45Z

Reviewer run IDs: architecture/senior/reuse=`/root/plan_arch_senior`;
QA/test/product/ops/docs=`/root/plan_qa_product_docs`;
security/auth/privacy=`/root/plan_security_auth`

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS | None | The chunk map, ownership seams, stop conditions, and long-term boundaries are coherent. |
| QA/test | PASS | None | Gates, races, failure cases, evidence retention, and the exact scanner regression contract are executable. |
| security/auth | PASS | None | Merged AUTH has 74 PermissionIds/50 ActionIds; 23 WS-CON actions and two service permissions remain absent/proposed; all 12 reused permissions exist. |
| product/ops | PASS | None | Complete PaymentPolicy removal, legacy-row gate, fulfillment lifecycle, drain, and joint release behavior are explicit. |
| architecture | PASS | None | CON-02B solely owns outbox transitions; CON owns narrow ports; REV supplies only hidden release-control composition. |
| CI integrity | N/A - with approved reason | None | This reviewed delta changes planning Markdown only; CON-01 itself requires CI-integrity review when its script/test files change. |
| docs | PASS | None | Source provenance, active/archive precedence, current REV status, and PaymentPolicy removal are truthful. |
| reuse/dedup | PASS | None | Claim validation, drain observation, and lifecycle fences reuse sole owners through narrow ports without repository duplication. |
| test delta | N/A - with approved reason | None | No test file changes in this planning delta; CON-01 requires test-delta review for its planned gate regression. |

Open sub-agent sessions: none

Valid findings addressed: yes

- Rebased onto trusted `main` `e9d72a1`, including merged ADR 0014 and AUTH-07A
  catalogue/audit foundations, and validated exact AUTH counts/mappings.
- Preserved complete PaymentPolicy removal in split semantic-cutover and physical
  removal chunks; no advisory, compatibility, or execution fallback survives.
- Made merged REV-02 exact `Submission.task_assignment_id` lineage a hard
  CON-05A prerequisite.
- Preserved CON-02B as the sole OutboxEvent claim/retry/finalization owner. A
  feature handler only validates immutable claim generation through
  `OutboxClaimValidationPort`, never locks or mutates OutboxEvent, and returns a
  typed outcome after CON work.
- Added canonical lifecycle-fence lock ordering, durable pre-I/O state, and the
  prohibition on provider I/O under a database transaction, lifecycle fence,
  or OutboxEvent lock.
- Assigned `FulfillmentDispatchFence`, `FulfillmentCallbackFence`, and
  `FulfillmentLifecycleDrainObservationPort` to CON-owned chunks while limiting
  REV-12A to hidden composition and REV-13 to sole activation/live drill.
- Recorded the content-reviewed but dirty REV snapshot atop `3e09e99` as
  non-consumable. Its stale handler-claim wording must be repaired, committed,
  commit-freshness reviewed, refreshed, and merged before use.
- Made CON-01 own the exact authorization-scanner history entry created by its
  hash-proven archival rename plus fail-closed tests. The cross-scanner equality
  assertion subtracts only that named auth-only path and separately proves the
  unchanged artifact scanner already excludes reference specs by prefix.
- Preserved AUTH ownership: WS-CON proposes identifiers and supplies resource
  facts/guards only; it does not implement the authorization service.

Deterministic evidence passed: Markdown links for 38 changed Markdown files,
general stale wording, artifact-contract state, loop-memory state, 71 agent-gate
tests, reference hashes, and `git diff --check`. The authorization stale-doc
scan continues to flag ten human-worker vocabulary occurrences only in the
explicitly non-canonical working transcription. CON-01 now owns its exact
byte-preserving archive rename/classification and the reconciled active spec;
this is not a waiver for an active document.

Application/runtime code changed: no. The original PDF deletion remains an
unstaged user-worktree change and was excluded from both reviewed commits.

## 2026-07-15 End-to-End Reference Reconciliation Addendum

The supplied generation-2 Markdown was audited against AUTH head `3ab25cf`,
canonical ART/REV decisions, ADR 0014, the shared-outbox plan, and current
PaymentPolicy consumers. Final internal delta reviews passed:

| Track | Result | Closed findings |
|---|---|---|
| security/auth + senior engineering | PASS | Exact ActionId/PermissionId handoff, request-scoped AUTH boundary, service-only callback/outbox authority, human/request versus dispatcher execution, bounded callback data, split award routes |
| product/ops + QA/test | PASS | 05A/05B executable removal scope, contribution/evidence disclosure, delivery retry and callback transitions, conformance traceability |
| architecture + docs | PASS | ART typed capabilities/recovery/provider matrix, centralized adapter factory, shared outbox ownership, source provenance/hash, stale-prefix and Markdown-link checks |

The reconciled Markdown remains a non-normative working transcription. CON-01
still owns creation and review of the active specification/ADR; no runtime chunk
is activated by this addendum.

## Chunk

`WS-CON-001-PLAN` - Contribution And Compensation Planning

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: f5995518a0d1723be5600d4bb306d99d3ba077a7

Reviewed planning-tree SHA-256: `367a43d2913276b1b700f9d55ae30ff812d8478c520bf338035c3b8671048f43`

Reviewed at: 2026-07-15T14:24:59Z

Reviewer run IDs: senior-engineering/architecture/reuse=`/root/plan_arch_senior`;
QA/test/product/ops/docs=`/root/plan_qa_product_docs`;
security/auth/privacy=`/root/plan_security_auth`

The planning-tree digest excludes this post-review evidence file. After the
reviewed digest, only this evidence and initiative status/chunk-status fields
changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Cross-initiative ownership, PR sizing, reusable infrastructure, and executable contracts repaired. |
| QA/test | PASS AFTER FIXES | None | Traceability, isolated PostgreSQL evidence, separate subsystem coverage, retained attempts, and release handoff repaired. |
| security/auth | PASS AFTER FIXES | None | Proposed action/resource contracts, service actor, binding states, rate controls, retirement and privacy repaired. |
| product/ops | PASS AFTER FIXES | None | Current re-review confirms complete PaymentPolicy removal, the open legacy-row gate, REV-02 ordering, fence ownership, and joint activation operations. |
| architecture | PASS AFTER FIXES | None | REV ownership, sole activation, outbox/audit/factory boundaries and ART/AUTH ownership are coherent. |
| CI integrity | N/A - with approved reason | None | Planning Markdown only; no workflow, script, dependency, test, or coverage gate changed. |
| docs | PASS AFTER FIXES | None | Archive provenance, active-doc inventory and generated-companion release ownership are explicit. |
| reuse/dedup | PASS AFTER FIXES | None | Shared hashing, idempotency, workers, rate control, audit, outbox, typed factory and existing Submission are reused. |
| test delta | N/A - with approved reason | None | No runtime test file changed; runtime contracts prohibit weakening and require same-run evidence. |

## Valid Findings Addressed

- Removed all REV-owned ReviewLease schema/claim/composition work from WS-CON;
  REV-03/06/10 retain their exact ownership.
- Made REV-13 the sole joint production activation/live-drill owner and added an
  exact evidence-driven release handoff without editing the sibling worktree.
- Split shared outbox truth from its dispatcher, added a shared lifecycle-audit
  participant owner, and kept feature handlers separate.
- At the original pre-merge review point, reconciled trusted-main 73
  PermissionIds versus AUTH-07A's 74/50 candidate state. The current addendum
  records AUTH-07A merged through `e9d72a1`; every WS-CON ActionId remains
  proposed with exact target/principal/facts/
  guard/revalidation/registry/resource/activation ownership.
- Added canonical service ActorProfile binding, exact callback assignment,
  actor/link/binding state distinctions, per actor+binding rate control, and
  dependency-safe deferred retirement.
- Extended the accepted REV lock order and assigned every cross-feature race to
  a chunk where both sides exist.
- Superseded the advisory PaymentPolicy direction with complete semantic and
  physical removal plus TaskAssignment compensation freeze
  one atomic cutover with drain/rebuild/downgrade rules.
- Split persistence, services, delivery, callback, evidence, reads, operations,
  and release readiness into explicit contracts with exact allowed/not-allowed
  paths and reviewer requirements.
- Added deterministic ADR-0014 compensation adapter/factory composition and
  prohibited provider-specific/fallback/service-locator construction.
- Added exact versioned event names and a conformance matrix for retained source
  invariants, role/privacy cases, races, failures, replays and live evidence.
- Added a normative runtime proof that erases stale coverage, retains immutable
  attempt-specific isolated-PostgreSQL metadata, preserves the 78-percent global
  floor, and runs a separate 90-percent report for every changed subsystem.

## Commands Run

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_loop_memory_state.py
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
git diff --check
sha256sum <revised WS-CON pair>
git show HEAD:<original WS-CON PDF> | sha256sum
python3 scripts/check_stale_authorization_docs.py
```

Results:

- Markdown links passed for 35 changed Markdown files.
- General stale wording, artifact-contract and loop-memory checks passed.
- Agent gate regression suite passed: 71 tests.
- The internal-evidence gate correctly remains red in this uncommitted planning
  worktree because its reviewed-SHA protocol accepts only a committed candidate,
  not the supplementary planning-tree digest. Before any PR, commit the approved
  planning candidate, rerun exact-head reviewers/evidence, and require this gate
  to pass; this local evidence is not PR-ready proof.
- `git diff --check` passed.
- Superseded after the 2026-07-15 end-to-end reconciliation: the Markdown is
  now an editable working transcription with a new truthful hash in
  `SOURCE_MANIFEST.md`; the generation-2 PDF hash remains unchanged.
- Authorization stale-contract scan intentionally rejects the unadopted raw
  candidate Markdown for `/v1` and legacy human-worker vocabulary. This is the
  evidence requiring archival treatment and a reconciled active spec in CON-01,
  not a gate waiver for an active document.

## Remaining Risks

- D1/D7/D8 and the callback/outbox service PermissionIds require explicit human
  approval. D2 removal is approved; only legacy-row handling remains open.
- Original PDF disposition remains a pre-existing user-worktree concern;
  generation-2 PDF preservation and working-Markdown provenance remain CON-01
  gates.
- AUTH, ART and REV prerequisites are unmerged. The active REV working delta
  incorporates `JOINT_RELEASE_HANDOFF.md` but must become a branch-reachable
  reviewed commit, rebase, and merge before either public surface can activate.
- Exact migration numbers, merged symbols, production adapter/provider and live
  values must be refreshed at each approved implementation chunk.
- This uncommitted reviewed plan still requires a committed exact-head review
  cycle before it can be published or treated as PR evidence.

## Stop Condition

Planning is internally reviewed. No implementation/specification chunk is
active. Await explicit human approval; do not start WS-CON-001-01 automatically.
