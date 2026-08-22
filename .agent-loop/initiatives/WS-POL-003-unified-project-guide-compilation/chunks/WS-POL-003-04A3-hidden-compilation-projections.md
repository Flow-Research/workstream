# Chunk Contract: WS-POL-003-04A3 - Hidden Compilation-Derived Projections

## Status and authority

Status: executable against protected-main base
`a95a0b02d7c546b2440f6b8dd8215a4be07671ff`, where `WS-POL-003-04A` is
merged through PR #356. Risk: L1.

## Merge state

- Outcome on merge: `complete`

This chunk creates hidden PROJECTS behavior only. It activates no action and
changes no route, queue, provider call, or setup ledger.

## Goal

Project the immutable unified-compilation result into the two canonical product
objects needed by setup completion:

```text
project_guide_sufficiency(attempt_id)
project_submission_artifact_policy(attempt_id)
```

The methods are separate purpose-specific operations. There is no generic
component selector and no caller-supplied status, hash, output, action, actor,
or service identity.

Both return an immutable receipt containing operation ID, attempt ID,
component, output ID, output digest, and `projected` or `replayed`. A bounded
`ProjectionError` exposes only `attempt_unavailable`, `component_forbidden`,
`component_unprojectable`, `source_state_unavailable`,
`service_authority_denied`, or `storage_unavailable`; it carries no raw result,
material, database, provider, or authorization detail.

## Closed behavior

| Compilation result | Sufficiency projection | Artifact-policy projection |
|---|---|---|
| `guide_blocked` | required | forbidden |
| `draft_ready` | required | required |
| `draft_ready_with_warnings` | required | required |
| `compilation_invalid_terminal` | forbidden | forbidden |
| `compilation_provider_uncertain` | forbidden | forbidden |

Each projection is deterministic from the exact validated component stored in
the compilation. It performs zero model calls. It preserves bounded safe text,
uses the existing canonical product model, and stores immutable provenance for
the exact project, guide/version, source snapshot/hash, setup run/generation,
attempt, compilation, result hash, component hash, schema, and derived object
ID/content digest.

The trusted transforms are closed:

- `guide_blocked` maps to a `blocked` report, `draft_ready` to `passed`, and
  `draft_ready_with_warnings` to `passed_with_warnings`. Finding severity,
  code, and message are preserved with `location=null`; report summary is null.
  Business-row producer identity is fixed to
  `ProjectGuideCompilationProjection` version `v1`; the operation custody
  retains the exact compilation agent/name/version. The immutable compilation
  remains the source for evidence references and the complete result.
- The artifact proposal maps to the existing submission-policy body through
  one closed pure transform. Proposal strings are already unique and are
  tightened at the compilation boundary as follows: required artifacts are
  canonical relative paths of at most 500 characters; required evidence and
  attestation terms are canonical identifiers of at most 100 characters; and
  forbidden patterns are bounded safe text of at most 500 characters.
  Input tuple order is authoritative. Required artifact item `i` becomes
  `{key: "required-artifact-%03d", path: raw, hash_required: true, required:
  true, description: null}` and evidence item `i` becomes
  `{key: "required-evidence-%03d", label: raw, hash_required: true, required:
  true, description: null}`, with one-based indexes. Forbidden items become
  `{pattern: raw, reason: raw, worker_facing_fix: null}`. No transform can
  collide because ordered ordinal keys are server-owned. Rule collections are
  canonicalized by the existing policy-body canonicalizer; attestation terms
  are copied and canonicalized there. File/package limits
  are copied; packaging is required with sole format `zip`; manifest and
  SHA-256 checks are required; and allowed storage is the canonical sorted
  `local`, `r2`, `s3` set. The transform validates
  `SubmissionArtifactPolicyInput`, then reuses unchanged
  `ProjectService.canonical_agent_submission_policy_body` to canonicalize and
  prove the default floor before write. Effective-policy and checker
  compilation remain deferred to their existing approval-stage owner. No
  truncation, slugging, best-effort repair, or collision suffix is permitted.
- The policy row uses server-owned version
  `unified-<first 16 snapshot-hash hex>-g<setup generation>`, derivation source
  `unified_compilation`, fixed projector name/version above,
  source references from the exact verified report usages in item order, and
  change summary `Projected from unified project guide compilation.`. Its body
  and hash are the canonical pure-helper outputs. A generation therefore has
  one stable policy identity even when it reuses an immutable source snapshot.
- A blocked compilation has no artifact proposal and the policy method denies
  before authorization or product writes.

Add one closed custody table,
`project_guide_component_projection_operations`, with component constrained to
`guide_sufficiency` or `submission_artifact_policy`. One exact operation exists
per setup generation and component. Update/delete/truncate and changed replay
fail closed. The existing business rows remain canonical; the operation row is
their provenance and replay receipt.

Verified sufficiency identity becomes generation-aware: the verified unique
index is `(source_snapshot_id, setup_generation)` while the diagnostic
snapshot-only index remains unchanged. The current-report repository read
orders verified reports by descending setup generation and then creation/ID;
callers that require an exact generation use an exact generation lookup.
Submission-policy identity remains its existing project/guide/version unique
key, with the server-owned version above incorporating setup generation.
Migration downgrade refuses when any projection operation, generation-reused
report, or unified policy exists; an empty database downgrades and re-upgrades.

For a report or policy referenced by an 04A3 operation, database triggers make
the canonical content and creation provenance immutable. A report may later
change only warning-acknowledgement fields. A policy may later change only its
closed approval/supersession lifecycle fields. Exact source-usage rows for a
referenced report are immutable. Direct SQL update/delete/truncate of protected
content or provenance fails; immutable receipt hashes can never drift from the
canonical object.

## Exact setup precondition

Both projection methods lock and require the latest active setup generation in
exact unified source state:

```text
status = queued
current_step = queued
celery_task_id = deterministic task ID for the attempt/setup generation
continuation_verification_job_id / continuation_started_at = both null or the
  exact stored ART continuation pair for this snapshot/setup generation
error_code = null
error_artifact_incident_id = null
error_summary = null
post_submit_derivation_summary = null
started_at = null
finished_at = null
every setup-row output ID = null
```

The guide must be the exact locked draft guide/version from the attempt. The
setup-bound snapshot ID/hash must be exact and no newer snapshot may exist for
that guide/version. Legacy `running_*`, `dispatch_pending`, enqueue
failure/mismatch, terminal, mismatched/partial continuation, error-bearing,
started/finished, wrong-task,
stale-generation, stale-snapshot, or setup-output-bearing rows deny before
authorization consumption or projection creation. 04A3 never writes setup-row
output IDs. When the artifact-policy projection follows sufficiency, it may
observe only the exact first 04A3 custody row and its canonical report; all
setup-row output fields must remain null. Any foreign, changed, partial, or
unreceipted first component denies. POL-04A2 later binds the canonical output
IDs into the terminal setup transition.

A pre-existing legacy report or policy row without the exact immutable 04A3
operation is not reusable and denies. Component replay is valid only while the
setup remains in the exact source state and the own operation/decision/output
tuple is unchanged. A whole-task replay after setup finalization must return
through the finalization receipt before calling either projection method.

## Authorization and lock order

AUTH's dependency-free public API exposes two distinct semantic ports, one for
each existing action boundary. Each follows the same AUTH-first pattern:

```text
with authorization.prepare_sufficiency_projection(locator) as capability:
    capability.consume_new(final_facts) -> authority_receipt
    capability.validate_replay(final_facts, stored_decision_id) -> None

with authorization.prepare_artifact_policy_projection(locator) as capability:
    capability.consume_new(final_facts) -> authority_receipt
    capability.validate_replay(final_facts, stored_decision_id) -> None
```

A non-locking attempt lookup provides only the project locator. AUTH prepares
before PROJECTS locks product rows. PROJECTS then recomposes final facts and
chooses exactly one mutually exclusive terminal method. Capabilities are
nominal, process-local, single-use, non-serializable, and closed in `finally`.
Replay performs current service preflight and validates the stored decision
without PREP consumption or new evidence.

Production implementations remain deny-default until `WS-AUTH-001-12J`.
Following POL-03A, this chunk may add only the exact inactive audit/resource
vocabulary for compilation-derived sufficiency and artifact-policy projections.
Vocabulary does not activate an action, evaluator, or service membership.
Test adapters may stage vocabulary-valid decisions to prove atomic PostgreSQL
custody and may not borrow another resource type.

The two exact vocabularies are:

| Component | Action | Permission | Resource type | Facts domain | Authority domain |
|---|---|---|---|---|---|
| sufficiency | `project.guide_sufficiency.run` | `project.guide.manage` | `project_guide_sufficiency_projection` | `workstream.project_guide_sufficiency_projection.facts.v1` | `workstream.project_guide_sufficiency_projection.authority.v1` |
| artifact policy | `project.submission_artifact_policy.derive` | `project.effective_policy.manage` | `project_submission_artifact_policy_projection` | `workstream.project_submission_artifact_policy_projection.facts.v1` | `workstream.project_submission_artifact_policy_projection.authority.v1` |

Both use audit domain `authority`, event type
`SensitiveAuthorizationAllowed`, service identity `workstream.project.setup`,
scope type `service`, and the exact project scope. For component `C`, operation
ID is UUIDv5 URL namespace over
`workstream.project-guide-projection:operation:<attempt-id>:<C>`; correlation ID
uses the same input with `correlation`; output ID uses the same input with
`output`; resource ID is the operation UUID.
Component-specific final facts include project/guide/version, snapshot ID/hash,
setup run/generation/task ID and complete source-state digest, attempt/request
operation/provider key, compilation/result/component/schema hashes, prior
component operation/output/digest when required, derived output ID/digest, and
locked material digest and byte count for sufficiency. The component-specific
AUTH port injects and validates the exact component/action/permission/resource/
domain/service/operation/correlation constants and current service actor/link
facts. Python and PostgreSQL canonical JSON digest vectors must match for every
field and reject every one-field mutation.

All hashes are `sha256:<64 lowercase hex>` over canonical JSON (UTF-8, sorted
keys, compact separators, no non-finite values); no key is omitted.
Sufficiency final facts contain exactly:

```text
project_id, attempt_id, request_operation_id, provider_idempotency_key,
compilation_id, guide_id, guide_version, source_snapshot_id,
source_snapshot_hash, setup_run_id, setup_generation, celery_task_id,
source_state_digest, result_hash, component_hash, result_schema_version,
compilation_agent_name, compilation_agent_version, material_sha256,
material_byte_count, report_id, report_content_digest
```

Policy final facts contain the same common lineage through
`compilation_agent_version`, then exactly `prior_operation_id`,
`sufficiency_report_id`, `sufficiency_report_digest`, `policy_id`, and
`policy_content_digest`.

The source-state envelope is exactly
`{"domain":"workstream.project_guide_projection.source_state.v1","facts":...}`
with facts keys `celery_task_id`, `continuation_started_at`,
`continuation_verification_job_id`, `current_step`,
`error_artifact_incident_id`, `error_code`, `error_summary`, `finished_at`,
`guide_id`, `guide_status`, `guide_version`,
`output_post_submit_checker_policy_id`,
`output_submission_artifact_policy_id`, `output_sufficiency_report_id`,
`post_submit_derivation_summary`, `setup_generation`, `setup_run_id`,
`source_snapshot_hash`, `source_snapshot_id`, `started_at`, and `status`.
Sufficiency/policy facts envelopes use the exact facts domains in the table and
the exact corresponding field lists above.

The sufficiency output envelope uses domain
`workstream.project_guide_sufficiency_projection.output.v1` and exact business
keys `id`, `project_id`, `guide_id`, `guide_version`, `source_snapshot_id`,
`source_snapshot_hash`, `status`, `findings`, `summary`, `agent_name`,
`agent_version`, `project_setup_run_id`, `setup_generation`,
`agent_material_sha256`, `agent_material_byte_count`, and `created_by`; report
`created_by` is the exact authority actor-profile ID. The policy output envelope
uses domain
`workstream.project_submission_artifact_policy_projection.output.v1` and exact
keys `id`, `project_id`, `guide_id`, `guide_version`, `source_snapshot_id`,
`source_snapshot_hash`, `policy_version`, `lifecycle_status`, `policy_body`,
`policy_hash`, `derivation_source`, `source_material_refs`,
`derivation_agent_name`, `derivation_agent_version`, `created_by`, and
`change_summary`. Authority envelopes use the exact authority domain in the
table and keys `action_id`, `permission_id`, `resource_type`, `resource_id`,
`scope_project_id`, `actor_profile_id`, `identity_link_id`, `service_identity`,
and `facts_digest`.

Null is retained, UUID/date values are canonical strings, arrays retain their
declared order, and no optional field is omitted. The material digest is the
attempt's existing `guide_material_hash`. After the single locked ART load,
PROJECTS rebuilds `VerifiedGuideMaterialSnapshot` with the existing
`build_verified_guide_sufficiency_material` and
`VerifiedGuideMaterialSnapshot.from_material`, requires its SHA-256 to equal
that attempt digest, and records `len(canonical_payload)` as material byte
count. Both values enter sufficiency facts, output digest, custody, and replay.
Policy source-material references are derived from the same locked ART usage
rows in item order using exact format
`artifact-content:{content_id}#extraction-usage:{extraction_usage_id}`. Output
ID UUIDv5 input is
`workstream.project-guide-projection:output:<attempt-id>:<component>`.

The persisted `project_guide_compilation_result.v1` schema is unchanged. The
pure projection transform applies the width/path/identifier checks above. A
parseable accepted v1 component that cannot project returns stable
`component_unprojectable` with zero AUTH consumption, material load, business
row, or custody row; it is never rewritten. Operators correct it through a new
guide/setup generation.

AUTH public API defines nominal frozen component-specific locator,
`ProjectionIdentity`, `FinalFacts`, `AuthorityReceipt`, and prepared capability
protocols. Each locator contains only project ID and attempt ID. Successful
prepare exposes a frozen capability-issued identity containing operation ID,
correlation ID, output ID, actor-profile ID, identity-link ID, and fixed service
identity before product facts are constructed.
Receipt is only decision-event ID, actor-profile ID, identity-link ID, fixed
service identity, and resource-context digest. The two final-facts types expose
only the locked lineage/output data listed above and cannot accept ORM,
session, component, action, permission, resource/domain, service, operation,
correlation, output-ID selectors, or arbitrary mappings. The AUTH public module
owns pure component-specific operation/correlation/output-ID derivation
functions. PROJECTS uses only the identity issued by the prepared capability to
construct business content, output digest, and final facts; these fields are
capability-issued, never caller-selected. Each purpose-specific AUTH port
independently re-derives and checks the identity plus its
component/action/permission/resource/domain/service constants. None originates
in the public command. Port swapping is therefore structurally invalid, not a
caller-selectable branch.

The custody row stores exactly: operation/correlation/component; exact project,
guide/version, snapshot ID/hash, setup run/generation/task ID; attempt, request
operation, provider key, compilation, result hash, component hash, result
schema and compilation agent name/version; nullable prior projection operation,
output ID/digest for the policy component; mutually exclusive report/policy
output IDs and output digest; facts digest; authority-resource digest; actor
profile, identity link, fixed service, action, permission, decision event; and
creation time. Composite foreign keys bind the attempt/compilation/setup
lineage. Unique constraints cover `(setup_run_id, setup_generation, component)`,
`(compilation_id, component)`, each non-null output ID, and decision event.
Replay compares this complete tuple and calls only `validate_replay`; it creates
no new event or product row.

## Boundary and reuse

- Reuse the validated `ProjectGuideCompilationResult`, existing canonical
  report/policy models, and existing sanitizers.
- Do not call the legacy sufficiency or policy agents.
- Do not require legacy `running_*` setup states or mutate `ProjectSetupRun`.
- Do not approve the draft policy, compile effective policy, or project the
  post-submit component.
- Do not reuse the broad mutation services if they require caller-selected
  state or legacy step truth. Extract only pure canonical construction helpers
  proven reusable by tests.

The exact transaction order is: non-locking attempt/project/compilation lookup
and pure component transform; forbidden or unprojectable components stop here
with no AUTH or ART effect. Then prepare the component-specific AUTH capability;
lock attempt then request custody; call
the unchanged `GuideSufficiencyMaterialPort.load`, which takes its existing
grouped header lock on guide, snapshot, and setup and then locks snapshot items
and ART extraction rows in adapter order; lock the prior 04A3
operation/report for the policy component; lock own operation/output replay
candidate; recompose exact facts; consume new or validate replay; flush the
business row, source-usage rows, operation, and AUTH evidence; commit once; close
the capability in `finally`. ART loading here is transaction-local database
material validation, not provider/object-store I/O. No network/provider I/O or
serialized material/capability may cross the transaction.

The existing `WS-POL-003-04B` file remains an inactive, non-executable planning
skeleton and is superseded for sequencing/ownership by this executable
contract, PLAN, CHUNK_MAP, STATUS, and CURRENT_STATE. The atomic chunk-state
rule forbids rewriting a second chunk contract in this PR. 04B must receive its
own exact current-main contract after 04A3, 04A2, AUTH-12J, and AUTH-12B2 merge;
it may only cut over to those already-owned hidden operations.

## Allowed files

The complete implementation surface is:

```text
backend/app/modules/projects/api/__init__.py
backend/app/modules/projects/api/guide_compilation_projections.py
backend/app/modules/projects/guide_compilation/projections.py
backend/app/modules/projects/guide_compilation/models.py
backend/app/modules/projects/guide_compilation/repository.py
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/authorization/api/__init__.py
backend/app/modules/authorization/api/project_guide_projections.py
backend/app/modules/audit/schemas.py
backend/app/db/models.py
backend/alembic/versions/0009_guide_compilation_projections.py
backend/alembic/env.py
backend/tests/projects/guide_compilation/helpers.py
backend/tests/projects/guide_compilation/test_projection_contracts.py
backend/tests/projects/guide_compilation/test_projection_service.py
backend/tests/projects/guide_compilation/test_projection_postgresql.py
backend/tests/projects/guide_compilation/test_projection_migration.py
backend/tests/projects/guide_compilation/test_projection_call_graph.py
backend/tests/projects/guide_compilation/test_projection_policy.py
backend/tests/projects/guide_compilation/test_migration_contract.py
backend/tests/projects/guide_compilation/test_migration_authorized_persistence.py
backend/tests/authorization/guide_compilation/test_migration_contract.py
backend/tests/architecture/test_authorization_boundary.py
backend/tests/test_alembic.py
backend/scripts/run_test_lanes.py
backend/tests/test_ci_test_lanes.py
backend/scripts/behavior_ownership.py
backend/tests/test_behavior_ownership.py
.ci/behavior-ownership/partition.v1.json
.ci/behavior-ownership/auth/project-guide-compilation-projection-ports.json
.ci/behavior-ownership/lifecycle/project-guide-compilation-projections.json
.github/workflows/backend.yml
docs/architecture_data_model.md
docs/operations_project_operating_manual.md
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/**
.agent-loop/CURRENT_STATE.md
```

No directory wildcard is implicit except the initiative documents. Migration
`0009` is valid only while `0008_guide_compilation_authorized_persistence` is
the sole protected-main head. If any other runtime, schema, test, CI, ownership,
or documentation path becomes necessary, stop and amend/re-review this
contract before editing it.

## Not allowed

- Any provider/model call, route, task, queue, outbox, live composition, setup
  state/output mutation, approval, effective policy, checker policy, guide
  activation, or post-submit projection.
- Any AUTH evaluator, catalogue availability, fixed-service membership,
  permission, action, grant, private import, generic authorization method, or
  serializable prepared handle.
- Any generic component selector, generic operation framework, new canonical
  report/policy model, compatibility fallback, or legacy inference reuse.
- Any caller-supplied actor, service, action, project, guide, setup state,
  output ID, content, hash, or policy truth. The public command contains only
  the immutable compilation attempt ID.
- Any transaction, row lock, ORM object, or authorization capability crossing
  external I/O. The unchanged ART material port performs transaction-local
  PostgreSQL reads in the exact lock order above; it performs no object-store
  or provider call while locks or the AUTH capability are held.

## Acceptance and trustworthy tests

- Unit tests prove the closed outcome table, exact canonical transforms,
  sanitization, digest vectors, extra-field denial, and mutually exclusive
  component methods.
- Real PostgreSQL tests prove exact creation, immutable provenance, exact
  replay with zero new event, changed replay denial, two independent-session
  same-component and cross-component races, cross-lineage denial, rollback
  after authorization/product flush, and migration upgrade/downgrade guards.
- Every disallowed setup status, step, error code, error summary, incident ID,
  post-submit summary, start/finish timestamp, output ID, task ID, guide state,
  source snapshot, and generation shape denies with zero product/event rows.
  Cross-component tests prove only the exact first 04A3 receipt can precede
  the second projection and rollback removes partial effects.
- Migration tests cover a populated-database downgrade refusal, empty
  downgrade/re-upgrade, exact 0008 round-trip preservation while restoring
  0009 as current head, generation reuse of one source snapshot, and direct
  SQL UPDATE/DELETE/TRUNCATE rejection for the operation and protected
  canonical report/policy/source-usage content.
- Negative-effect assertions prove zero model calls, setup writes, approval,
  post-submit output, or wrong component rows.
- A counting ART material-port test proves prepare/current-service denial,
  forbidden component, and unprojectable legacy-v1 output each perform zero
  material loads. Changed replay or stored-decision mismatch performs exactly
  one bounded material load but zero AUTH consumption, new evidence, product,
  or custody effect. A seeded order mutant that loads ART material before AUTH
  preparation must be killed.
- Architecture tests prove route-unreachability, deny-default production,
  public-boundary direction, and no call to the three legacy inference methods.
- Seeded faults remove one source/generation/result/component/task/correlation
  guard, swap the two authorization ports, create output before validation,
  permit a legacy/error/output-bearing setup, accept a foreign first component,
  consume on replay, or restore a legacy-state dependency; each exact test
  must fail.
- Every materially changed production file has at least 90 percent branch
  coverage, repository coverage remains at least 78 percent, all seven
  semantic lanes reconcile with zero skips/retries, and exact-head nine-lens
  review plus hosted CI pass.

## Verification commands

```bash
cd backend
uv run ruff check \
  alembic/env.py alembic/versions/0009_guide_compilation_projections.py \
  app/db/models.py \
  app/modules/audit/schemas.py app/modules/authorization/api \
  app/modules/projects/api app/modules/projects/guide_compilation \
  app/modules/projects/models.py app/modules/projects/repository.py \
  scripts/behavior_ownership.py scripts/run_test_lanes.py \
  tests/projects/guide_compilation/test_projection_*.py \
  tests/projects/guide_compilation/test_migration_authorized_persistence.py \
  tests/authorization/guide_compilation/test_migration_contract.py \
  tests/architecture/test_authorization_boundary.py tests/test_alembic.py \
  tests/test_behavior_ownership.py tests/test_ci_test_lanes.py
uv run pytest -q \
  tests/projects/guide_compilation/test_projection_contracts.py \
  tests/projects/guide_compilation/test_projection_service.py \
  tests/projects/guide_compilation/test_projection_postgresql.py \
  tests/projects/guide_compilation/test_projection_migration.py \
  tests/projects/guide_compilation/test_projection_call_graph.py \
  tests/projects/guide_compilation/test_projection_policy.py \
  tests/projects/guide_compilation/test_migration_contract.py \
  tests/projects/guide_compilation/test_migration_authorized_persistence.py \
  tests/authorization/guide_compilation/test_migration_contract.py \
  tests/architecture/test_authorization_boundary.py tests/test_alembic.py \
  tests/test_behavior_ownership.py tests/test_ci_test_lanes.py
uv run docstr-coverage --config .docstr.yaml
uv run python -m scripts.authorization_boundary validate \
  --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
uv run python -m scripts.behavior_ownership validate
cd ..
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_chunk_state_sync.py \
  --base-ref a95a0b02d7c546b2440f6b8dd8215a4be07671ff
git diff --check a95a0b02d7c546b2440f6b8dd8215a4be07671ff
```

With the repository-pinned PostgreSQL and MinIO services healthy and
`WORKSTREAM_TEST_ADMIN_DATABASE_URL` and `WORKSTREAM_TEST_MINIO_ENDPOINT` set,
the final implementation executes this exact semantic proof from `backend/`:

```bash
set -euo pipefail
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
rm -rf -- .ci/test-lanes/04a3
mkdir -p .ci/test-lanes/04a3/lanes .ci/test-lanes/04a3/combined
uv run python scripts/run_test_lanes.py --collect-only \
  --metadata-dir .ci/test-lanes/04a3/collect \
  --summary-json .ci/test-lanes/04a3/collect-summary.json
uv run python scripts/validate_test_lane_evidence.py \
  --metadata-dir .ci/test-lanes/04a3/collect \
  --summary-json .ci/test-lanes/04a3/collect-summary.json
for lane in shared_foundations_a shared_foundations_b schema_contracts_a \
  schema_contracts_b schema_contracts_c project_lifecycle task_lifecycle
do
  mkdir -p ".ci/test-lanes/04a3/lanes/${lane}"
  uv run python scripts/run_test_lanes.py --lane "${lane}" \
    --metadata-dir ".ci/test-lanes/04a3/lanes/${lane}/metadata" \
    --summary-json ".ci/test-lanes/04a3/lanes/${lane}/summary.json" \
    --timeout-seconds 1200
done
uv run python -m scripts.merge_test_lane_evidence \
  --input-root .ci/test-lanes/04a3/lanes \
  --metadata-dir .ci/test-lanes/04a3/run \
  --summary-json .ci/test-lanes/04a3/run-summary.json
uv run python scripts/validate_test_lane_evidence.py \
  --metadata-dir .ci/test-lanes/04a3/run \
  --summary-json .ci/test-lanes/04a3/run-summary.json
shopt -s nullglob
coverage_files=(.ci/test-lanes/04a3/run/.coverage.*)
test "${#coverage_files[@]}" -eq 7
for source in "${coverage_files[@]}"
do
  test -f "${source}"
  test ! -L "${source}"
done
export COVERAGE_FILE=.ci/test-lanes/04a3/combined/.coverage
test ! -e "${COVERAGE_FILE}"
uv run coverage combine --keep .ci/test-lanes/04a3/run
uv run coverage report --precision=2 --fail-under=78
for source in \
  app/modules/audit/schemas.py \
  app/modules/authorization/api/__init__.py \
  app/modules/authorization/api/project_guide_projections.py \
  app/modules/projects/api/__init__.py \
  app/modules/projects/api/guide_compilation_projections.py \
  app/modules/projects/guide_compilation/models.py \
  app/modules/projects/guide_compilation/repository.py \
  app/modules/projects/guide_compilation/projections.py \
  app/modules/projects/models.py \
  app/modules/projects/repository.py
do
  uv run coverage report --include="${source}" --precision=2 --fail-under=90
done
```

Hosted CI enforces the same exact per-file 90 percent floors; aggregate
coverage cannot hide a weak changed file.

## Required reviews

Preimplementation and exact-final-head review require nine tracks:

1. architecture and module ownership;
2. simplicity, reuse, and deduplication;
3. security and authorization;
4. QA and lifecycle correctness;
5. test-delta and false-green resistance;
6. senior engineering feasibility;
7. CI and evidence integrity;
8. product and operations truth; and
9. documentation and state consistency.

## Stop conditions

Stop and re-plan if a projection requires a model call, generic selector,
caller-supplied truth, setup-row mutation, cross-component authority, legacy
step, AUTH-private import, held lock across external I/O, second canonical
business object, a source state broader than exact `queued/queued`, or
provenance that cannot be enforced from immutable rows.
