# Plan: WS-POL-003 - Unified Project Guide Compilation

## Objective

Replace the current three complete project-guide inference passes with one
bounded logical `ProjectGuideCompilationAgent` attempt for each exact immutable
guide source, capability-catalogue snapshot, and setup generation. A durable
attempt identity and provider idempotency key enforce that cardinality across
dispatch, timeout, reconciliation, and retry.

The invocation proposes:

1. guide sufficiency and findings;
2. a submission-artifact policy draft;
3. an atomic, traceable requirement inventory;
4. supported project-specific pre-submit bindings;
5. supported project-specific post-submit bindings;
6. platform-covered requirements;
7. human-review and lifecycle-policy requirements; and
8. non-executable capability suggestions for unsupported requirements.

The model is untrusted. Trusted server code validates, canonicalizes, hashes,
persists, compiles, and submits separate canonical policies for approval.

## Prerequisite sequence

AUTH-12F, 12G, 12B2, and 12H complete the existing policy mutation,
fixed-service worker, and activation authorization boundaries. WS-POL-003 must
reuse those action-specific boundaries rather than create a broad
`project.guide.compile_everything` permission.

ART-04B1 supplies the complete typed pre-submit catalogue and effective-plan
compiler: mandatory/non-selectable platform coverage plus its closed selectable
project-rule namespace. ART-04B2/04B3 retain ART scratch/default execution.
WS-POL-003 consumes those typed projections and does not change ART ownership.

The merged pre-submit projection is consumed exactly as implemented:

- catalogue ID `workstream.pre_submission_checkers`, version `v0.1`, schema
  `pre_submission_checker_catalogue.v1`;
- immutable canonical manifest and `manifest_sha256`;
- stable definition ID/version, owner, phase/order/dependencies,
  classification, typed inputs, result schema, failure code, resource budget,
  state/disabled behavior, policy trace, and dispatch identity;
- pure `effective_pre_submission_plan.v1` bound to exact project, guide/source,
  effective policy, pre-submit policy, catalogue manifest, ordered entries,
  rule-instance identities/configuration hashes, and `plan_sha256`.

WS-POL-003 does not infer missing catalogue fields, mutate availability, or
reconstruct plan identity independently.

Durable CHECKER/POL ownership supplies post-submit defaults and registered
selectable project rules. WS-POL-003 creates no pre-submit or post-submit
dispatch registry; the unified agent sees read-only projections from both
canonical phase owners.

Before persistence/runtime cutover, an XINT/AUTH amendment must activate:

- `project.guide_compilation.request`: Project Manager dispatch/recovery bound
  to exact actor/link/grant, project, draft guide, snapshot, setup
  run/generation, operation, request digest, and idempotency identity;
- `project.guide_compilation.execute`: fixed `workstream.project.setup`
  authority bound to exact canonical input hash, source and phase-owned
  capability snapshot hashes, setup run/generation, instruction/agent version,
  prior compilation when superseding, session/root transaction, and result.

Execute authorizes only the model call plus immutable compilation parent
creation/supersession. It does not authorize canonical projections: 12E owns
sufficiency, 12F owns submission/effective/pre-submit policy mutations, and
12G owns post-submit policy mutations. Each projection consumes fresh
action-specific PREP at its protected transaction.

## Single checker execution surfaces

There are two lifecycle phases exposed through one internal typed checker
service port, with exactly one complete command per phase:

```text
ART sealed scratch material
-> checker_service.evaluate_pre_submission(...) exactly once
   -> mandatory ART platform plan + exact locked project pre-submit plan
ART verified stored/bound Submission material
-> checker_service.evaluate_post_submission(...) exactly once
   -> durable platform defaults + exact locked project post-submit plan
```

Artifact-flow orchestration supplies exact ART material facts and invokes the
phase command at the corresponding material boundary. The checker service
facade invokes the canonical phase executor once and returns one typed bounded
result; no caller invokes an individual checker. For pre-submit, ART-04B1-04B3
remain the sole plan compiler/executor/evidence writer behind the facade. For
post-submit, the durable CHECKER executor/repository is the sole writer. The
facade never reruns members or persists a competing evidence set.

These commands are internal typed service APIs, not contributor-facing HTTP
checker routes. Callers cannot provide checker names or invoke platform and
project rules separately. Automatic orchestration and any bounded repair use
the same command and deterministic attempt identity.

Setup proposal, approval, correction-request, and visibility APIs remain
separate because they configure or observe policy rather than execute a
submission. Read-only checker-run visibility also remains bounded and separate.

This initiative owns the checker service contract and composition. Later
artifact-flow integration consumes it at ART's scratch and verified-storage
boundaries without WS-POL-003 modifying ART code or forcing ART lifecycle changes.

## Input contract

`ProjectGuideCompilationContext` is strict (`extra="forbid"`) and contains:

- exact existing ART-verified `GuideSourceMaterial`;
- optional bounded representative task context;
- non-selectable `platform_coverage` generated from ART-04B1 platform entries
  plus CHECKER-owned durable post-submit defaults;
- selectable `project_capabilities` generated from ART-04B1's project-rule
  namespace for pre-submit and CHECKER/POL's registered rules for post-submit;
- server-owned classification policy and schema versions;
- optional bounded correction feedback tied to an exact superseded
  compilation.

Representative task context is tenant-local, server-redacted, and limited to
policy shape. It excludes actor/user IDs, emails, submission artifacts, review
decisions, payment/compensation data, credentials, secrets, URLs, and raw task
bodies not already part of approved guide/setup source material.

The canonical input binds source snapshot ID/hash, catalogue hashes, setup
run/generation, instruction version, configured agent identity, SHA-256, and
byte count. Provider responses, reasoning traces, credentials, scratch paths,
and raw duplicate source text are not persisted.

## Project capability and stage contract

Both canonical phase catalogues are closed, typed, versioned, and registered
explicitly at their composition roots. The pre-submit projection uses only the
fields in merged ART-04B1; it does not invent per-entry timeout or safety
metadata absent from `v0.1`. Catalogue mutation requires code, tests,
deployment, and startup parity validation; projects and model output cannot
register it.

A project capability is eligible for pre-submit only when ART-04B1 registers
it as an enabled `policy_primitive` in `project_policy`, its exact trusted
implementation satisfies the closed primitive contract, and its compiled
configuration matches the definition's policy fields. The later executor owns
the server-side 60-second aggregate project-rule ceiling; the model cannot
change stage, order, resource budget, disabled behavior, or timeout. Sixty
seconds is a ceiling, not permission. Mandatory ART work retains its separate
platform budgets.

Deterministic work outside that contract is post-submit. Expert judgment is
human review. Claiming, assignment, deadlines, routing, revision, acceptance,
payment, and other transitions are lifecycle policy. Timeout, cancellation,
or infrastructure failure is retryable platform state, never contributor
failure.

Post-submit is not an escape hatch: a selectable post-submit capability must
also be registered for that stage, closed-schema, deterministic,
side-effect-free, bounded, credential-safe, and implemented by trusted code.
It cannot execute arbitrary project code, shell, network calls, or model
judgment. Its timeout and resource budget are catalogue-owned and enforced.

Initial project pre-submit capability identities, enabled only when backed by
registered implementations, are:

- `policy.submission_packet.validate`
- `policy.storage_scheme.enforce`
- `policy.manifest_field.require` (Workstream manifest fields only)
- `policy.hash.verify`
- `policy.file.require`
- `policy.evidence.minimum`
- `policy.artifact.forbid`
- `policy.attestation.require`
- `policy.file_size.limit`
- `policy.package_size.limit`
- `policy.packaging.require`
- `policy.generated_quality.warn`

`policy.manifest_field.require` does not validate arbitrary domain files. Such
a requirement remains a capability gap until a dedicated typed structured-
document capability exists.

The initial project-selectable post-submit truth is only
`check_acceptance_criteria_present` unless the running build registers more.
Durable platform defaults are non-selectable and cannot be repeated in project
bindings. Unknown support becomes a capability suggestion; it is never
manufactured to make a guide appear complete.

## Output contract

`ProjectGuideCompilationResult` is strict, size/count bounded, and contains:

- `guide_blocked`, `draft_ready`, or `draft_ready_with_warnings`;
- sufficiency findings;
- nullable submission-artifact policy projection;
- atomic requirements with exactly one disposition;
- pre-submit and post-submit binding proposals;
- bounded capability suggestions;
- bounded safe setup notes;
- server-verified agent/schema identity.

Allowed dispositions are `platform_covered`, `supported_pre_submit`,
`pre_submit_capability_gap`, `supported_post_submit`,
`post_submit_capability_gap`, `human_review`,
`project_lifecycle_policy`, `guide_blocker`, and `informational`.

Bindings may select only the exact ID/version/stage exposed through
`project_capabilities`. Suggestions are engineering work items and can contain
no capability ID, source code, command, URL, import, dependency, or executable
expression.

## Evidence and text safety

Evidence uses a closed `GuideEvidenceRef` structure minted/validated by trusted
server code from the immutable source-item and extraction lineage. It never
contains raw excerpts, URLs, paths, credentials, signed references, or caller
text.

Every persisted operator-readable model field passes centralized bounded safe
text validation/redaction. Rejection is atomic: unsafe or structurally invalid
output produces retryable/blocked setup evidence and no policy projection.

## Trusted validation

Validation must, in order:

1. enforce strict shape and count/size limits;
2. lock and revalidate service identity, source lineage, setup run/generation,
   and canonical input identity;
3. validate sufficiency/finding consistency;
4. validate artifact policy with existing strict/default-merge rules;
5. validate requirement/binding/suggestion referential integrity;
6. reject platform/default selection or repetition;
7. reject unknown, disabled, stale-version, or wrong-stage capabilities;
8. validate typed configuration, deterministic/side-effect-free constraints,
   and phase-owned resource controls exactly as exposed: ART `resource_budget`
   plus executor gates and the aggregate pre-submit ceiling, or post-submit
   timeout/budget fields only when their canonical source defines them;
9. sanitize every persisted text field;
10. canonicalize and hash the result and each projection; and
11. prepare every required action-specific fixed-service PREP, consume all of
    them inside the one root database transaction owning compilation and
    projection persistence, then commit mutations and authorization evidence
    together; any validation, consumption, or write failure rolls back the
    entire unit without borrowing authority between actions.

The agent cannot order platform execution. Catalogue phases, dependencies, and
the trusted compiler determine order.

## Persistence and provenance

Add immutable `ProjectGuideCompilation` provenance with exact project, guide,
source snapshot, catalogue snapshots, setup run/generation, agent/instruction
identity, canonical input/result hashes, component hashes, created service
identity, and append-only supersession.

Existing `GuideSufficiencyReport`, `SubmissionArtifactPolicy`,
`PreSubmitCheckerPolicy`, and `PostSubmitCheckerPolicy` link to the exact
compilation ID/result/component hashes. They remain canonical business objects.

Agent-derived projections cannot be edited. Correction creates a new setup
generation and compilation. If separately manual policies remain supported,
they carry manual provenance, invalidate unified downstream proposals, and
cannot claim or reuse agent compilation approval.

## Lifecycle

```text
ART verified extraction
-> automatic fixed-service setup continuation
-> canonical platform/capability projections
-> one unified model invocation
-> trusted validation and immutable compilation
-> separate sufficiency/policy proposals
-> Project Manager review/approval
-> trusted effective + pre-submit compilation
-> deterministic post-submit proposal compilation (zero model calls)
-> separate PostSubmitCheckerPolicy approval
-> existing authorized guide activation
```

Blocked compilation creates no policy projections. A required capability gap
blocks activation with an exact operator-visible setup status/error. The setup
generation has one durable model-attempt row and provider idempotency key. A
timeout, cancellation, or infrastructure failure before known acceptance may
retry or reconcile only that key; an unknown outcome must be retrieved or
replayed idempotently, never redispatched with a new key. Once an accepted
result is persisted, retry reuses it. Invalid or unsafe output terminally
consumes the attempt and requires a new setup generation for correction. None
of these states is contributor failure or negative contribution evidence.

## Alternatives rejected

- Keep three guide-reading inference calls: repeated cost and inconsistent
  conclusions.
- Store one combined canonical policy: collapses separate ownership and
  approval lifecycles.
- Allow model-created checker code or identifiers: unsafe and non-auditable.
- Build POL-local pre/post primitive maps or duplicate ART platform/project
  entries: creates competing dispatch authority instead of consuming the two
  canonical phase owners.
- Permit in-place edits to agent projections: destroys result-hash provenance.
- Grant one broad compilation permission: bypasses action-specific AUTH
  custody and atomic evidence.
- Keep standalone precheck or caller-selected checker triggers: creates a
  parallel execution path that can drift from the locked effective plan.

## Verification strategy

- Strict contract and prompt-injection tests.
- Registry/version/stage/configuration/default-isolation tests.
- Fixed-service identity, PREP replay/session/transaction/resource tests.
- Postgres migration, append-only supersession, concurrent idempotency, and
  rollback tests.
- Single-logical-attempt lifecycle tests covering concurrent dispatch,
  timeout-after-provider-acceptance recovery under the same idempotency key,
  accepted-result reuse, terminal invalid/unsafe output, and zero-call
  post-submit continuation.
- Stale source/catalogue/setup/policy invalidation tests.
- Task-lock and activation-chain regression tests.
- OpenAPI/import/reachability tests proving standalone precheck is absent,
  no caller can select checkers, artifact-facing composition has one command per
  phase, and repair converges on the same attempt identity.
- Hosted CI full suite/coverage; changed backend subsystems remain at least 90
  percent and repository floor remains at least 78 percent.

## Completion boundary

Completion requires the old three runtime methods/prompts and second
post-submit model invocation to be deleted after all callers cut over. No
compatibility alias, dual inference path, second registry, or independently
invocable legacy precheck survives. The two canonical phase catalogues and one
typed checker service port remain; the port has exactly one complete command
per pre/post phase and no individual-checker product entry.
