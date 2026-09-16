# WS-ARCH-001-03A — Complete active and frozen guide context

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: the existing PROJECTS internal context port resolves
  the complete approved, activated guide graph for new work or exact frozen work.

## Intent

Give TASK one canonical source for the complete guide-bound policy context.
An active guide supplies a new task lock; an existing task resolves its exact
stored guide/source/pre-policy selectors without adopting a newer guide or CON
publication. This is an internal port, not a new HTTP surface or task writer.

## Current behavior and sequence correction

Main `ad0e6b68` includes CP07 activation and AUTH-12H live manager authority.
`ProjectLockedPolicyContextPort` and `ProjectLockedPolicyRepository` currently
resolve only guide/source/effective/pre-submit facts, without activation,
post-submit, review/revision or contribution-policy custody. ART admission and
pre-submit evidence already consume this port. Some downstream fixtures mark a
guide active by disabling custody triggers instead of executing activation.

The user approved ARCH-03A before CP08 after reviewing these concrete defects:
CP08 prohibited every writer needed to satisfy its required lineage constraints;
03A's CP08 prerequisite was artificial; and contribution-only schema tests cannot
prove a complete human revision rebase while old Submission foreign keys still
point to mutable Task context. CP08 will add its fields and minimal existing
writers together after this port. Full authorized revision preparation and its
immutable-context FK replacement remain with the later revision operation.
Retained work must never acquire invented lineage from a current selector.

## Bounded change

### Allowed

- `backend/app/modules/projects/api/locked_policy.py` and exports: extend the
  existing immutable facts and port with an active-for-new-work read; retain the
  exact frozen selector operation with one canonical result contract.
- `backend/app/modules/projects/locked_policy_repository.py` and a small same-owner
  context projection helper if needed; existing PROJECTS adapter root wiring.
- Existing activation, proposal/finalization and post-policy custody readers:
  narrowly reuse their exact validation for active/superseded guide reads,
  refresh cached ORM values, and preserve draft-only mutation guards.
- The existing post-policy body parser and its CHECKERS/activation callers:
  separate retained schema/hash custody from live catalogue eligibility; preserve
  current execution and activation rejection behavior without a second parser.
- `backend/app/modules/tasks/service.py`: preserve the current-catalogue checks
  inherited by existing screening/ready helpers from the shared parser; remove
  its uncalled pre-Submission helper. No new TASK writer or cutover belongs here.
- Exact affected ART consumers only if a required type adaptation is necessary;
  no ART business/authority behavior. Existing TASK selector persistence is not
  changed in this chunk.
- Focused PROJECTS contract/PostgreSQL tests and affected downstream shared
  fixtures, ART/AUTH regression tests, exact test-lane/behavior registrations and
  genuinely shrinking structural-debt measurements if required.
- Current guide architecture/operations/data-model documentation, roadmap and
  initiative navigation; adopted ARCH03A/CP08/03B sequence contracts. Preserve
  main's MCP row and unrelated ongoing work.

### Not allowed

New HTTP endpoints, AUTH grants/actions, migrations or Task/Assignment/Submission
lineage fields/writers; CON selection/evaluation; checker execution; provider
calls; a new guide activation operation; compatibility aliases or a partial
context fallback; historical evidence fabrication or retained-data deletion;
claiming complete human revision rebase or introducing activation chronology.

## Design and decisions

1. Extend `ProjectLockedPolicyContextPort` with `lock_active_policy_context` for
   an exact project. Both active and frozen reads share the same complete loader.
   Frozen lookup continues to use the exact existing guide/version/source and
   effective/pre-submit IDs/hashes. These select one immutable activated guide;
   they do not select current CON or silently substitute another setup.
2. Require CP07 activation custody, its exact post-policy projection/approval,
   unified finalization and separate pre-policy approval, canonical stored
   bodies, selected review/revision policies and same-project contribution
   identity. Reuse existing owner validation rather than another compiler or
   policy-selection algorithm. Active reads require the sole active guide;
   frozen reads admit active/superseded exact custody, including later CON
   retirement, without rerunning current eligibility.
3. Extend the current fact type with required immutable activation receipt and
   canonical artifact/post-submit/review/revision bodies. Catalogue facts are the
   exact saved ID/version/schema-version/manifest-hash tuples in that receipt,
   compared with the compilation attempt; full historical catalogue bodies are
   not persisted and must not be reconstructed from the current registry.
   The receipt supplies exact setup/finalization/result/component identities,
   approval custody and contribution-policy selectors. Existing direct pre-policy
   projections remain validated against that same receipt for ART consumption.
   No ORM, session, mutable body, raw guide content or provider handle escapes.
4. Use actual CP07 operation ID, per-guide activation generation and timestamp.
   Do not rename per-guide generation as project-wide chronology. The old planned
   activation-sequence field has no source and is deferred with revision semantics.
5. Require a caller root transaction; never commit or mutate product state.
   Lock Project first and discover the candidate guide without a Guide row lock.
   Read its exact activation target, then reuse the canonical order: Attempt ->
   Request -> Guide -> exact source/setup/compilation/projections and approval
   custody -> finalization -> post-policy custody -> review/revision policies.
   Re-fetch and validate the guide and activation receipt after waiting. Project
   fencing stabilizes active selection; exact frozen selection never changes its
   target. Refresh reused custody rows rather than trusting the identity map.
   Never hold Guide while newly acquiring Attempt. Existing ART TASK/actor/link
   locks remain before PROJECT; this reader acquires no AUTH locks.
6. Reuse `policy_lineage.require_complete_policy` and its persisted-format-aware
   digest for exact review/revision bodies. Do not call activation-time
   `validate_activation_ready`, consult current CON eligibility, or apply today's
   automated-acceptance availability as a historical-read condition. Persisted
   business policy/hash formats are evidence, not a second implementation.
   Mutation callers retain their existing draft-only defaults; only this complete
   context read supplies active/superseded eligibility.
7. Replace affected fabricated-positive guide fixtures with real saved approval,
   CON publication and CP07 activation. Retain deliberate unbound/corrupt fixtures
   only as negative or migration-preservation tests. No guard disabling to make a
   positive complete-context test pass.

## Acceptance criteria

- Active and exact frozen reads return the same complete immutable graph for a
  valid guide; frozen reads remain exact after a successor guide or CON retirement.
- Missing activation, either approval, finalization/source/catalogue mismatch,
  foreign or substituted selectors, invalid bodies/hashes and unsupported
  lifecycle states deny with the existing bounded context-unavailable error.
- A new active read returns the successor while the old frozen request still
  returns its original graph; a newer publication alone selects nothing.
- Active/superseded context reads cannot broaden proposal/approval mutation
  eligibility. Tests retain valid draft operations and active mutation denials.
- Real PostgreSQL readers refresh preloaded rows and serialize against guide
  replacement/archival in both orders, with observed waiter/blocker evidence.
- Existing ART consumers use the sole strengthened port; no second partial path
  or compatibility fixtures remain in the affected scope.

## Risk and review routing

- Risk: L1.
- Plan: architecture/reuse and security/QA feasibility reviews before code.
- Implementation: architecture/reuse, security, QA/test-delta, docs/product-ops;
  CI-integrity for test ownership and final hosted proof.
- Human focus: complete source custody, frozen versus active selection, caller
  transaction/lock order, no task/HTTP scope expansion, and corrected sequence.

## Evidence

Lead runs relevant unit and real isolated PostgreSQL tests, Ruff, module/AUTH
boundaries, Markdown links, stale wording, Commitrail records, exact inventories
and hosted complete coverage. New/materially changed modules remain at least 90%.
Current migration head is `0023_guide_activation_custody`; no migration changes.
Required falsification:
remove the activation receipt/ledger digest check and prove the otherwise-valid
activation-custody negative fails; substitute one exact receipt/policy selector while preserving all
other valid fields; and remove row refresh to expose a stale identity-map read.
Full suite and aggregate coverage remain hosted. Local evidence records exact
head and resource cleanup; no private guide documents or live providers are used.


## Exact implementation and proof map

Product edit paths (unused paths need no change):

- `backend/app/modules/projects/api/locked_policy.py`
- `backend/app/modules/projects/api/__init__.py`
- `backend/app/modules/projects/locked_policy_repository.py`
- `backend/app/modules/projects/locked_policy_projection.py` (same-owner canonical projection)
- `backend/app/modules/projects/guide_activation/custody.py`
- `backend/app/modules/projects/guide_compilation/proposal_repository.py`
- `backend/app/modules/projects/guide_compilation/repository.py`
- `backend/app/modules/projects/guide_compilation/approval_custody.py`
- `backend/app/modules/projects/post_policy/repository.py`
- `backend/app/modules/projects/post_policy/custody.py`
- `backend/app/modules/projects/post_submit_policy.py`
- `backend/app/modules/checkers/service.py` (preserve live catalogue validation at execution)
- `backend/app/modules/tasks/service.py` (preserve affected live caller guards only)
- `backend/app/modules/projects/repository.py`

The composition root and ART callers already consume the port and are inspection
scope, not new business behavior. `policy_lineage.py` is a reused unchanged owner.
Any additional product file requires an explicit contract correction first.

Test edits are limited to `backend/tests/` paths below:

- `projects/test_locked_policy_contract.py`, `projects/test_locked_policy_context.py`
- `projects/test_locked_policy_custody.py`, `projects/test_locked_policy_concurrency.py`
- `projects/locked_policy_fixtures.py` (shared real activation fixture)
- `projects/guide_activation/source_fixtures.py`, `projects/guide_activation/pg_support.py`
- `projects/guide_activation/test_successor.py` (extract reusable successor setup)
- `projects/unified_policy_fixtures.py`, `project_create_fixtures.py`
- `pre_submit_test_helpers.py`, `test_default_pre_submit_execution.py`
- `test_pre_submit_attempt_recovery.py`, `test_artifact_admission.py`, `test_artifact_recovery.py`
- `test_pre_submit_attempt_lock_order.py`, `test_pre_submit_related_lock_order.py`
- `authorization/contribution_policies/test_cross_owner_lock_order.py`
- `test_checkers.py`, `checkers/post_submit/test_compiled_policy.py` (saved parsing versus live validation)
- `test_ci_lane_catalogue.py` (exact owner set maintenance)
- `test_tasks.py` (catalogue-rollout screening/ready atomic denial)
- `test_review_lease_persistence.py` (reuse real guide-bound publication)
- `test_pre_submit_attempt_migration.py`, `migration_fixtures.py`
  (isolate the 0021 retained-evidence boundary from later 0023 activation custody)

Replace the affected complete-context positives, not every historical fixture.
The existing `activation_case` and real AUTH `guide_activation.pg_support.activate`
provide valid controls. Shared ART packet policy customization remains explicit.
No fake activation, disabled guide guards, or incomplete semantics may support a
positive complete-context proof. Existing deliberate SQL corruption fixtures may
remain only for negative or retention tests.

Named verification:

| Test | Required behavior and discriminating control |
| --- | --- |
| `test_active_and_frozen_context_are_complete` | Real finalization, separate approvals, CON publication and CP07 activation; compare every returned body and exact receipt/catalogue identity with stored source. |
| `test_frozen_context_survives_successor_and_retirement` | Activate a genuine successor; active read returns successor, frozen read returns original; retire CON version and preserve frozen facts. |
| `test_catalogue_rollout_preserves_context_but_blocks_new_activation` | Change current catalogue after saving exact custody; historical and active reads retain their bodies, while new activation denies and rolls back. Restoring current-registry validation inside the parser must make this test fail. |
| `test_catalogue_rollout_blocks_task_transition_without_writes` | Real HTTP screening/release denies the obsolete installed catalogue; independent PostgreSQL reads prove unchanged task fields and audit rows. Removing the live checks must make the exact cases fail. |
| `test_canonical_policy_sidecars_deny_before_manual_execution[catalogue-crossed]` | Valid saved policy cannot execute against a different installed catalogue; denial precedes lifecycle changes, audit writes and checker invocation. |
| `test_project_context_contract_does_not_cycle_agent_port_import` | Import the agent port in a fresh interpreter without relying on test collection order. |
| `test_new_publication_does_not_reselect_context` | Publish a new CON version while guide binding remains unchanged; both reads retain exact activation binding. |
| `test_context_rejects_missing_or_substituted_custody` | Parameterized missing activation/pre approval/post approval/finalization, crossed project or policy, catalogue mismatch, invalid body/hash and lifecycle; start with valid activated graph and alter only the selected boundary through controlled read corruption where DB forbids direct mutation. Assert bounded context error and no mutation. |
| `test_context_result_is_deeply_immutable` | Attempt nested receipt/body changes and show source/result identities cannot be mutated. |
| `test_context_preserves_persisted_review_semantics` | Format-aware stored review/revision hashes match exact bodies; incomplete semantics and altered human-review mode deny. Preserve retained policy hash identities, without adding runtime compatibility code. |
| `test_context_read_does_not_allow_activated_proposal_mutations` | Read valid active/superseded guides, then invoke proposal approve/correct defaults and require denial; valid draft operations still pass. |
| `test_context_refreshes_preloaded_custody` | Preload rows, change the test-visible cached state, reread persisted exact state; removing the required refresh makes the exact assertion fail. |
| `test_context_serializes_guide_replacement` | Reader-first and activation-first transactions, observed waiter/blocker PIDs, no Guide/Attempt inversion, successor freshness after wait. |
| `test_context_serializes_project_archival` | Reader-first and writer-first Project lifecycle change; frozen read cannot return stale active Project state. |
| `test_context_and_finalization_share_lock_order` | Real finalization replay on an activated target and context read in both orders: finalizer denies state normally; no deadlock, partial writes or hidden provider calls. Observe database locks before releasing participants. |

ART admission, execution/recovery and real-AUTH cross-owner lock regressions run
through the strengthened port with real activation fixtures. Retain their original
ownership, replay, rollback and actual-ZIP assertions. Contract-only fake-session
coverage of the superseded partial reader is replaced by complete-graph tests.

Required test-of-the-test probes: remove the activation receipt/ledger digest
comparison and require its otherwise-valid negative to fail; substitute one receipt selector
while keeping every other field valid; remove required fresh-read behavior and
require its named stale-cache test to fail. Record exact modified guard and test
output, then restore before the review candidate. Missing activation is also tested
separately; it cannot supply the exact target for this port and has no fallback.

Lead commands: `pytest` on the four locked-policy modules plus affected ART/AUTH
modules through `backend/scripts/run_isolated_tests.py`; Ruff on touched Python;
`python3 scripts/check_commitrail_records.py --base-ref origin/main`;
`python3 scripts/check_markdown_links.py`; stale wording/authorization/artifact
contract checks; module/AUTH boundary validators; hosted complete test/coverage
lanes. Exact inventory edits may touch `backend/scripts/test_lane_catalogue.py`,
`backend/scripts/behavior_ownership.py`, `.ci/behavior-ownership/partition.v1.json`,
`.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` and the existing
`.ci/behavior-ownership/lifecycle/project-guide-compilation-repository.json` only
when changed ownership or shrinking measurements require it, never weaker gates.

Current documentation edits are README, `docs/roadmap_status.md`,
`docs/architecture_data_model.md`, `docs/architecture_checker_framework.md`,
`docs/operations_project_operating_manual.md`, ARCH/AUTH/CON/POL overviews,
`.commitrail/INDEX.md`, and adopted ARCH/AUTH planning dependency tables. Preserve
main's MCP entries. Assess local sheet exports only if present.


## Implementation outcome and proof custody

ARCH-03A replaces the partial context reader with one complete active/frozen
loader and immutable result. Existing ART callers keep the same port and exact
request selectors. Shared approval reads retain effective/pre-policy locks and
refresh exact rows; mutation callers retain draft-only defaults. Exact-source
selection is extracted inside the existing finalization repository, keeping its
method below the existing structural limit without changing the limit.

Affected ART fixtures now create real guide/source/finalization, separate
approvals, selected review/revision policies, published CON policy and real AUTH
activation. The old trigger-disabled positive activation helper is replaced,
and the partial-reader fake-session tests are replaced by complete graph tests.
Required JSON-value, failure, row-lock, immutable-history, authority, real-ZIP,
replay and rollback assertions remain. One artifact receipt assertion now targets
its exact put attempt instead of assuming how many guide documents exist.

Local discriminating probes executed in an owned isolated PostgreSQL database:
removing the activation digest comparison made the named `activation_digest`
negative fail with DID NOT RAISE; removing activation-ledger refresh made the
preloaded-custody test fail; adding Guide-before-Attempt locking made the
finalization/context test fail with an actual PostgreSQL deadlock. All mutations
were restored. These are guard-specific test-of-the-test results, not claims of
production defects in the restored candidate. Shared final verification and
hosted aggregate custody belong to the PR trust bundle.

The approved plan was reviewed at `936080ee` by architecture/reuse and security/QA.
Its lock-order, catalogue-identity, exact-scope/proof and sequence findings were
resolved before implementation. This record describes its intended merged
outcome; CP08 is the next bounded change and is not implemented here. No local
spreadsheet exports are present, so no XLSX or CSV update applies.


Review corrections separate saved post-policy schema/hash/sidecar custody from
live catalogue eligibility. The saved catalogue tuple is bound to the immutable
proposal/attempt; activation and execution retain explicit current-catalogue
validation. No optional bypass flag or second parser is introduced. The public
facts keep their typed, validated receipt while deferring its runtime import to
construction, removing a collection-order-dependent cycle through the agent port.
Exact ownership registries include the projection and tests without changing
thresholds or weakening equality. The orphaned trigger-disabled Project helper
and stale sequence wording are removed within this affected scope.


Shared-caller reconciliation preserves current-catalogue validation in both
existing TASK screening and locked-context helpers, including the latter's ready
transition and reads. Their intentional custody/readiness separation belongs to
CP08's port cutover. The uncalled `_validate_locked_post_submit_policy_context`
helper is removed; it supplied no live Submission protection and has no callers
or tests to preserve. A PROJECTS active-context read supplies saved facts, not
permission or execution eligibility for a new task. CP08 requires CHECKERS-owned
pre/post installed-capability validation before its initial lineage/status writes.


Downstream fixture repairs reuse the real guide-bound published CON version for
ReviewLease prerequisites instead of publishing a second active policy. Checker
output admission compares attempt/content/replica/receipt counts with the exact
starting graph; denial adds nothing and admit/replay adds one prepared attempt.
The 0021 retention tests execute only that revision's unchanged upgrade/downgrade
bodies in transactions, preserving later 0023 activation rows, authority events
and the Alembic head marker. They still prove byte-exact retained evidence,
absence of invented new fields, downgrade refusal and result bounds. No
production migration or retained data is changed by this fixture reconciliation.
