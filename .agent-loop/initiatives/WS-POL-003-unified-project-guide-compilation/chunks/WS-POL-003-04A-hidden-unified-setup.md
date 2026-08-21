# Chunk Contract: WS-POL-003-04A - Hidden Unified Setup

Status: Preimplementation contract review. Runtime implementation has not
started. Risk: L1.

## Merge state

- Outcome on merge: `planned`

## Outcome

Build one hidden PROJECTS-owned execution command that starts from an already
authorized POL-03B attempt, reconstructs its exact current guide-compilation
context, and drives that custody through one unified `compile_project_guide`
call.

For one setup generation, the command must produce one of these bounded
outcomes:

- one immutable complete `ProjectGuideCompilation` containing the full strict
  result envelope and every component hash;
- one terminal invalid-result classification with no compilation; or
- `provider_outcome_unresolved` with no redispatch when the current provider
  boundary cannot prove whether a call completed.

Stale or unavailable context, revoked service authority, and storage failure
return a bounded execution error while preserving the durable attempt state.
They do not invent another durable state or imply that provider execution is
safe to retry.

The command remains hidden. It is composed behind a typed PROJECTS port but is
not called by a route, Celery task, queue, continuation, approval path, or live
setup service in this chunk.

## Authoritative starting point

- This is a stacked chunk over PR #355 only. Its exact required parent is
  `a1e2aaa3ba7e781d30ca7da09d3775af6659ec48`.
- PR #355 remains open, non-draft, green, mergeable, and human-review gated at
  contract refresh. Its protected-main base is
  `c716fa424c1a86bda9e0f85c77c307fa07172bca`.
- The parent provides the authorized request receipt, durable attempt and
  provider key, committed dispatch fence, accepted/invalid result custody,
  immutable compilation persistence, current-lineage validation, and bounded
  recovery classifications.
- The merged POL-02 adapter provides the only unified provider method,
  `ProjectGuideAgentRuntime.compile_project_guide`.
- The current provider port is one-shot. It accepts no application
  idempotency key and exposes no retrieval or reconciliation method. This
  chunk therefore proves **at most one local provider invocation**, not
  exactly-once provider execution after an uncertain outcome.
- If PR #355 changes head, closes without merging, or is superseded, stop,
  restack on the authoritative replacement, and repeat contract review. If it
  merges unchanged, rebase this chunk onto the resulting protected main and
  repeat exact-head verification before implementation continues.

## Scope and ownership

### PROJECTS owns

- one dependency-safe execution-only hidden command/result/port contract;
- reconstruction of one exact immutable context from current guide, source
  snapshot, setup generation, ART-verified extracted material, and the two
  canonical capability projections;
- reconstruction of exact execute facts from the already committed request,
  attempt, and provider key;
- the orchestration state machine over the existing POL-03B coordinator;
- the decision to invoke the unified runtime only after a newly committed
  `dispatch_permitted=true` receipt; and
- bounded operator outcomes that expose identifiers and recovery state, not
  guide content, provider output, credentials, or AUTH handles.

PROJECTS creates no second attempt, compilation, policy projection, setup
ledger, provider client, or authorization protocol.

### ART and CHECKER/POL retain ownership

- ART remains the sole source of verified extracted guide material through
  `GuideSufficiencyMaterialPort`.
- ART's pre-submit catalogue projection and CHECKER/POL's post-submit
  projection remain the only capability truth.
- The hidden command consumes these existing typed projections and does not
  register, infer, cache, or persist a competing catalogue.

### AUTH retains ownership

- AUTH's public compilation facts and Protocol remain frozen.
- The command requires an existing request operation created through the real
  authenticated Project Manager boundary. It never reconstructs, impersonates,
  or replays the requesting human and never calls `authorize_request`,
  `prepare_request`, or `consume_request`.
- The application composition layer binds only the existing fixed-service AUTH
  adapter. PROJECTS domain code must not import AUTH models, repositories,
  kernel, prepared handles, or private resource contexts.
- AUTH's production compilation adapter may add one bounded `from_prepared`
  factory so application composition can bind the matching authorization and
  prepared services without reading a private attribute. It adds no action,
  fact, handle, authority, fallback, or second adapter.
- Provider execution and persistence use only the active fixed
  `workstream.project.setup` service.

### Provider boundary

- `ProjectGuideAgentRuntime` remains the sole provider-neutral interface.
- The OpenAI adapter must distinguish a **known returned but invalid structured
  result** from transport failure, timeout, configuration failure, and caller
  cancellation. Add one bounded typed invalid-output exception; do not expose
  provider text or exception details.
- Known malformed, partial, or semantically invalid output maps to the existing
  terminal `schema_invalid` code; proven unsafe text maps to `unsafe_text`.
  Transport failure, timeout, process loss, and cancellation after the dispatch
  fence remain `provider_outcome_unresolved` and are never rewritten as invalid.
- Every `ProjectGuideCompilationResult` envelope member is required at the
  model/adapter boundary, including components whose valid value may be empty
  or null. Raw omission must not silently acquire a default and appear
  complete.
- The expected agent identity, agent version, instruction version, and schema
  version are server-owned constants (or one equally small frozen manifest),
  never model-selected values. The pre-fence context manifest must match the
  attempt exactly. Returned `agent_version` must match the context/attempt;
  returned `agent_name` and `schema_version` satisfy their existing closed
  literals rather than fields that do not exist on the attempt.
- `ProjectGuideCompilationContext` carries the expected agent version before
  dispatch, so the provider input and attempt identity cannot disagree. The
  fixed v1 manifest is `project-guide-compilation-agent-v1` / `v1` / `v1` /
  `project_guide_compilation_result.v1`; changing it requires a later reviewed
  manifest version, not a runtime fallback.
- No provider retry, same-key replay claim, retrieval API, generic provider
  operation framework, or new dependency is introduced.

## Hidden public command

The PROJECTS public API exposes one execution command with one selector:

```text
attempt_id
```

`attempt_id` identifies existing authorized custody and is not itself
authority. The command accepts no project, guide, setup, raw guide text,
material, catalogue, model result, actor, prepared handle, provider key,
expected predecessor, path, URL, session, or ORM object.

The result contains only:

```text
operation_id
attempt_id
provider_idempotency_key
classification
compilation_id?
```

The port also defines one closed `ProjectGuideCompilationExecutionError` with
only an allowlisted safe code:

```text
attempt_unavailable
context_unavailable
service_authority_denied
storage_unavailable
```

The error contains no guide/provider content, credential, exception string,
path, stack, or AUTH detail. Its code does not replace or advance the durable
attempt classification.

The port has one method. Manual invocation and future queue delivery call the
same method with the same attempt ID. The authenticated boundary that creates
the attempt and the later queue delivery belong to POL-04B. This chunk adds no
HTTP or broker entry point.

## Context reconstruction

Before any provider effect, the hidden command opens a short database
transaction and:

1. loads the attempt and its one immutable authorized request operation, then
   locks and validates the exact draft guide, current source snapshot, and
   latest setup run/generation;
2. loads ART-verified material through the existing public material port;
3. maps it with the existing verified guide-material builder and freezes it as
   `VerifiedGuideMaterialSnapshot`;
4. builds the current ART pre-submit and CHECKER/POL post-submit projections
   through their existing pure factories; the pre-submit projection uses the
   startup settings-backed disabled-entry set rather than an implicit default;
5. applies one fixed agent identity, agent version, and instruction version;
6. validates the canonical context byte limit before any dispatch fence;
7. rebuilds one `CompilationAttemptIdentity` and requires exact equality with
   the stored attempt; and
8. reconstructs the existing execute-preflight facts, operation identity,
   provider key, and expected predecessor from durable server-owned custody.

The transaction ends before provider I/O. The detached value is a frozen
Pydantic context, not an ORM graph, path, workspace, handle, or serialized
queue payload.

Keep the read seam narrow: one private
`load_compilation_execution_state(session, attempt_id)` beside the existing
coordinator returns only immutable attempt identity, server-derived preflight
facts, and recovery classification. The context builder separately consumes
the composition-supplied `GuideSufficiencyMaterialPort` and canonical pre/post
factories. Each fence, outcome, and persistence mutation receives a new
session and a freshly revalidated fixed `workstream.project.setup` AUTH
composition.

The exact frozen context sent to the provider is reused when recording a known
result; POL-03B independently rechecks current setup lineage. Recovery from
`provider_result_accepted_not_persisted` reconstructs the original context from
immutable ART usage and the exact catalogue/runtime manifests before
persistence. If an old manifest cannot be reproduced after code or deployment
drift, recovery fails closed and leaves the accepted attempt intact. It never
falls back to a different current context and never redispatches.

## State machine

### 1. Load authorized custody or recover

Using a fresh root session, call one private PROJECTS loader with the attempt
ID. It locks the attempt and request operation, requires current setup lineage,
and returns immutable identity, server-derived execute facts, and the bounded
recovery classification. It returns no raw accepted result.

- `compilation_persisted` returns the existing bounded result.
- `compilation_invalid_terminal` returns the existing terminal result.
- `provider_result_accepted_not_persisted` skips provider work and continues
  directly to fresh-context persistence.
- `provider_outcome_unresolved` returns unresolved and performs no provider
  call.
- `compilation_reserved` may proceed to the fixed-service dispatch fence.

Missing request custody denies. The hidden path never creates or recovers a
request by impersonating its original human actor.

### 2. Fence before provider I/O

Using a new root session and fixed-service AUTH composition, rebuild exact
preflight facts from the immutable request identity and call
`fence_dispatch`.

Only a committed receipt with `dispatch_permitted=true` permits one call to
`compile_project_guide(context)`. A false permit or any other classification
returns without provider I/O.

### 3. Record a known outcome

After the single call:

- a valid complete result with the exact fixed agent version is validated
  against the exact frozen dispatched context and recorded through
  `record_accepted_result` in a new root transaction;
- a typed known-invalid output or wrong result agent version is recorded with
  the exception's bounded allowlisted `schema_invalid` or `unsafe_text` code;
  and
- timeout, transport/configuration failure, process loss, or cancellation
  records nothing after the already committed fence.

No exception text, provider response, prompt, trace, or unbounded failure is
persisted.

### 4. Persist accepted compilation

On the first pass, use another fresh root session to call `persist_accepted`
with the exact frozen context sent to the provider. On
accepted-not-persisted recovery only, first reconstruct and verify the exact
original context as described above. Return only the bounded persisted receipt.
No policy or setup-run projection occurs.

## Closed invariants

### One attempt and one local call

- One already authorized exact setup generation owns one request identity,
  attempt, provider key, and at most one `dispatch_permitted=true` receipt.
- Concurrent or repeated hidden commands may call the runtime at most once in
  the observed process history.
- Once the fence is uncertain, no recovery path invokes the provider until a
  separately reviewed provider retrieval/reconciliation capability exists.
- Accepted-not-persisted and persisted recovery perform zero provider calls.
- A new provider attempt requires a new setup generation.

### Complete result before projection

- A valid accepted result contains the full strict sufficiency, artifact,
  requirement, pre-submit, and post-submit envelope and all component hashes,
  and passes the merged strict validator before persistence.
- Every envelope field is present. Explicit empty collections and a null
  artifact policy are valid only when the semantic validator permits them:
  `draft_ready*` requires an artifact proposal, while a complete
  `guide_blocked` result may carry null/empty proposal components.
- Partial, malformed, unsafe, wrong-agent, or semantically inconsistent output
  creates no compilation or component policy projection and terminally
  consumes the generation.
- The immutable compilation is proposal/provenance evidence only. It is not a
  `GuideSufficiencyReport`, `SubmissionArtifactPolicy`, pre-submit policy,
  post-submit policy, setup success, approval, or guide activation.

### Authority and isolation

- The supplied attempt must have one exact immutable authorized request
  operation and still match the guide, snapshot, project, setup run, and latest
  generation.
- The hidden command cannot create human request authority or replace the
  actor/link/grant recorded by the authenticated request boundary.
- Only the fixed project setup service can fence, record, or persist.
- No session, transaction, lock, prepared handle, ORM object, or mutable
  repository value crosses provider I/O.

### Hidden and simple

- No existing worker, queue, router, continuation, API schema, setup-run
  status, or live call graph changes.
- The candidate orchestrator calls `compile_project_guide` only. It cannot
  call `analyze_guide_sufficiency`, `derive_submission_artifact_policy`, or
  `derive_post_submit_checker_policy`.
- The implementation reuses the merged POL-03B state machine and current
  material/catalogue factories. It adds no migration, table, outbox, queue,
  generic operation engine, plugin framework, or fallback.

## Allowed files

```text
backend/app/interfaces/project_agents.py                 # fixed manifest, required envelope, typed invalid result
backend/app/adapters/project_agents/openai_agent_sdk.py  # exact invalid-output mapping only
backend/app/modules/authorization/guide_compilation.py    # matching prepared-service factory only
backend/app/modules/projects/api/__init__.py
backend/app/modules/projects/api/guide_compilation.py
backend/app/adapters/projects/__init__.py
backend/app/adapters/projects/guide_compilation.py
backend/app/modules/projects/guide_compilation/__init__.py
backend/app/modules/projects/guide_compilation/context.py
backend/app/modules/projects/guide_compilation/orchestrator.py
backend/app/modules/projects/guide_compilation/contracts.py   # pure identity/facts helpers only
backend/app/modules/projects/guide_compilation/service.py     # private execution-state loader only
backend/tests/projects/guide_compilation/helpers.py           # shared fixture only
backend/tests/projects/guide_compilation/test_context_builder.py
backend/tests/projects/guide_compilation/test_hidden_orchestrator.py
backend/tests/projects/guide_compilation/test_hidden_orchestrator_postgresql.py
backend/tests/projects/guide_compilation/test_hidden_call_graph.py
backend/tests/test_agent_runtime.py                         # typed invalid-output behavior only
backend/tests/test_project_guide_compilation_contracts.py   # required result envelope only
backend/tests/authorization/guide_compilation/test_adapter_contract.py  # exact factory parity only
backend/tests/test_ci_test_lanes.py                         # exact new-test inventory only
backend/scripts/run_test_lanes.py                           # exact new-test registration only
backend/scripts/behavior_ownership.py                       # exact new callable ownership only
backend/tests/test_behavior_ownership.py                    # exact ownership assertion only
backend/scripts/test_structure_boundary.py                  # exact new-file scope only if required
backend/tests/architecture/test_test_structure_boundary.py  # exact scope assertion only if required
.github/workflows/backend.yml                                # exact 04A per-file coverage gate only
.ci/behavior-ownership/partition.v1.json
.ci/behavior-ownership/lifecycle/project-guide-compilation-context.json
.ci/behavior-ownership/lifecycle/project-guide-compilation-orchestrator.json
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/**
.agent-loop/CURRENT_STATE.md                                # exact on-merge 04A state only
docs/operations_backend_testing.md                          # exact lane command only if changed
```

No directory wildcard is implicit except the initiative documents. If another
runtime, test, migration, schema, CI, generated, or documentation file is
needed, stop and amend/re-review this contract before editing it.

## Not allowed

- `ProjectSetupRun`, guide, policy, AUTH, ART, CHECKER, task, submission,
  review, contribution, compensation, or audit schema changes.
- Any migration, dependency, environment setting, provider client, outbox,
  broker message, Celery task, route, or UI.
- Live fixed-service routing, setup-ledger activation, setup status/output
  mutation, approval, canonical component projection, checker execution, or
  guide activation.
- Raw/serialized guide material, model result, caller-supplied provider key,
  provider credentials, AUTH handle, session, path, workspace, or ORM object
  in the public command. The bounded server-owned provider-key UUID remains
  permitted only in the result receipt.
- Human AUTH context reconstruction or any hidden call to `authorize_request`,
  `prepare_request`, or `consume_request`.
- Application-layer access to `PreparedAuthorizationService._authorization` or
  any other AUTH private attribute; only the AUTH-owned bounded factory may
  perform that internal binding.
- Provider redispatch, automatic retry, claimed same-key provider replay,
  compatibility alias, legacy inference fallback, or second runtime adapter.
- Catch-all exception handling that converts unknown/transport failure into a
  terminal invalid result.

## Acceptance tests

### Real-service lifecycle

- Against the migrated real PostgreSQL schema, an authenticated PM test fixture
  first creates one authorized request/attempt. The production hidden command
  then reconstructs ART-backed context, receives one fixed-service dispatch
  permit, calls a deterministic fake runtime once, stores one complete
  immutable compilation, commits one execute decision, and creates zero
  additional request events, component policies, setup output IDs, outbox rows,
  approvals, or guide activation.
- Two truly concurrent identical commands converge on one attempt, one key,
  one provider invocation, one compilation, the one pre-existing request
  decision, and one execute decision.
- A fault after accepted-result custody but before final persistence is
  recoverable by the same command with zero additional provider calls.
- A fault, timeout, or cancellation after the dispatch fence leaves one
  unresolved attempt; replay and manual recovery make zero provider calls.
- Known invalid/partial/unsafe output produces one terminal-invalid attempt,
  zero compilation, zero component projections, and zero execute-persist
  event. Replays make zero provider calls.
- Stale guide, source, setup generation, catalogue/runtime manifest, fixed
  service actor/link, or predecessor fails closed before any new provider
  invocation or product projection.

### Contract and reachability

- A syntax-aware call-graph test starts at the PROJECTS public hidden port and
  proves the candidate production path can reach only
  `compile_project_guide`, never any of the three legacy runtime methods.
- A spy runtime whose three legacy methods fail immediately proves they are
  never invoked while the complete result already contains post-submit data.
- Public command/result validation rejects extra fields, raw material, actor,
  provider, handle, path, and ORM-shaped input.
- Candidate reachability proves the hidden path cannot call the human request
  methods or construct a human authorization context.
- The production AUTH adapter factory accepts only one existing prepared
  service, returns the same adapter composition as the explicit constructor,
  and rejects no/foreign authorization composition through existing checks.
- The OpenAI adapter raises the typed known-invalid exception only after a
  provider returned malformed/invalid structured output; timeout,
  cancellation, configuration, and transport failures retain their existing
  non-terminal exception behavior.
- Raw mapping/JSON output missing any required result-envelope member is
  rejected as typed invalid output; no Pydantic default may hide omission.

### Test integrity

- Primary lifecycle proof uses real PostgreSQL and production AUTH/ART
  adapters. Mocks cannot be the sole evidence for request, fence, accepted or
  terminal custody, persistence, concurrency, or forbidden-effect absence.
- Fake runtime evidence counts exact calls and returns deterministic strict
  results. Every important assertion includes both required rows and forbidden
  rows/effects. Every hidden-path integration test begins from an already
  authorized durable request rather than calling request authority from the
  candidate orchestrator.
- Seeded faults must prove the suite detects a removed dispatch-permit guard, a
  second-call recovery branch, a legacy method call, an invalid-output
  misclassification, skipped identity/context comparison, and component
  projection leakage.
- New/changed backend subsystem coverage is at least 90 percent per materially
  changed file; repository coverage remains at least 78 percent. No skip,
  deselection, retry-to-green, or mock-only waiver satisfies a required case.

Celery redelivery is intentionally not an 04A acceptance test: this chunk adds
no Celery entry point, and eager/mock execution would not prove broker
redelivery. Real delivery and queue recovery belong to POL-04B after the
hidden port and AUTH-12B2 activation are complete.

## Verification commands

Exact test paths may be narrowed only by contract amendment; implementation
must register every new test in the canonical semantic lanes.

```bash
cd backend
uv run ruff check app/interfaces/project_agents.py \
  app/adapters/project_agents/openai_agent_sdk.py \
  app/modules/authorization/guide_compilation.py \
  app/adapters/projects app/modules/projects/api \
  app/modules/projects/guide_compilation \
  tests/authorization/guide_compilation/test_adapter_contract.py \
  tests/projects/guide_compilation tests/test_agent_runtime.py \
  tests/test_project_guide_compilation_contracts.py
uv run pytest -q tests/projects/guide_compilation \
  tests/test_agent_runtime.py tests/test_project_guide_compilation_contracts.py \
  tests/authorization/guide_compilation/test_adapter_contract.py \
  tests/architecture/test_authorization_boundary.py
uv run pytest -q tests/projects/guide_compilation \
  tests/test_agent_runtime.py tests/test_project_guide_compilation_contracts.py \
  tests/authorization/guide_compilation/test_adapter_contract.py \
  --cov=app --cov-branch --cov-report=
for source in \
  app/interfaces/project_agents.py \
  app/adapters/project_agents/openai_agent_sdk.py \
  app/modules/authorization/guide_compilation.py \
  app/modules/projects/api/__init__.py \
  app/modules/projects/api/guide_compilation.py \
  app/adapters/projects/__init__.py \
  app/adapters/projects/guide_compilation.py \
  app/modules/projects/guide_compilation/__init__.py \
  app/modules/projects/guide_compilation/context.py \
  app/modules/projects/guide_compilation/orchestrator.py \
  app/modules/projects/guide_compilation/contracts.py \
  app/modules/projects/guide_compilation/service.py
do
  uv run coverage report --include="${source}" --precision=2 --fail-under=90
done
uv run pytest -q tests/test_behavior_ownership.py \
  tests/architecture/test_test_structure_boundary.py tests/test_ci_test_lanes.py
uv run python -m scripts.authorization_boundary validate \
  --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
uv run python -m scripts.test_structure_boundary validate \
  --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md \
  --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
uv run python -m scripts.behavior_ownership validate
cd ..
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_chunk_state_sync.py \
  --base-ref a1e2aaa3ba7e781d30ca7da09d3775af6659ec48
git diff --check a1e2aaa3ba7e781d30ca7da09d3775af6659ec48
```

The final implementation also runs all seven canonical semantic lanes against
real pinned services and reconciles exact node custody before review.
Hosted CI runs the same per-file 90 percent gate for every materially changed
production file; aggregate package coverage cannot hide a weak file.

## Required reviews

Preimplementation and exact-final-head implementation review require these
nine tracks:

1. architecture and module ownership;
2. simplicity, reuse, and deduplication;
3. security and authorization;
4. QA and lifecycle correctness;
5. test-delta and false-green resistance;
6. senior engineering feasibility;
7. CI and evidence integrity;
8. product and operations truth; and
9. documentation and state consistency.

Human review focus: confirm that 04A creates one hidden, complete proposal with
at most one local provider invocation; unresolved outcomes never redispatch;
invalid returned output is terminal; no component or setup projection occurs;
and no live caller changes.

## Stop conditions

Stop and amend/re-review before implementation if:

1. the exact PR #355 parent changes or an overlapping owner PR appears;
2. context cannot be reconstructed from existing ART and catalogue owners
   without serializing material or adding a second registry;
3. execution cannot start from one exact previously authorized attempt without
   recreating or impersonating the human request;
4. a transaction, lock, session, AUTH handle, ORM object, or workspace must
   cross provider I/O;
5. provider uncertainty would require redispatch, retrieval, or a claimed
   exactly-once guarantee;
6. invalid output cannot be distinguished from transport uncertainty without
   exposing provider details;
7. setup-ledger mutation, a live worker/route, AUTH private-attribute access
   outside its owner, new AUTH action or public-contract change, schema,
   migration, dependency, or component policy projection is required;
8. the candidate path can reach a legacy inference method or a second provider
   call;
9. real PostgreSQL/production AUTH/ART lifecycle proof, concurrency proof,
   forbidden-effect proof, per-file coverage, or seeded-fault sensitivity
   cannot pass; or
10. the exact original catalogue/runtime manifest cannot be reproduced for
    accepted-not-persisted recovery; or
11. any required file falls outside the exact allowed list.
