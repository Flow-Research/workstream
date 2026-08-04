# Review Log: WS-ART-001 Immutable Artifact Storage

## WS-ART-001-03A

- Reconciled on 2026-07-28 with trusted `main` `033654ac`, after merged
  WS-XINT-002-01 through 04 planning, internal-service activation, and AUTH 11B
  project identity/read context.
- Preimplementation reconciliation review rejected the preserved raw
  `AuthorizationContext`, custom evidence, and callback revalidation seam. The
  repair uses only the merged opaque `PreparedAuthorizationHandle` operation
  contract and one request-local PREP adapter lifecycle.
- The route-facing command performs Project Manager preflight before body read,
  scratch construction, or provider runtime. Production remains deny-only
  while `artifact.guide_source.ingest` is planned.
- Transaction A locks canonical project/guide/snapshot/item lineage, consumes
  the issuer-local handle against server-computed digest, byte count, and media
  type, stages non-authoritative `GuideSourceArtifactIngest`, reserves capacity,
  and creates put intent atomically. Provider I/O remains after commit.
- Migration `0038_guide_source_ingest` follows the merged `0037`
  authorization evidence head. Binding, reads, setup activation,
  materialization, and action availability remain outside 03A.
- Final internal review: senior engineering PASS WITH LOW RISKS; architecture
  PASS WITH LOW RISKS; QA PASS WITH LOW RISKS; security/auth PASS WITH LOW
  RISKS; product/ops PASS; reuse/dedup PASS WITH LOW RISKS; CI integrity PASS
  WITH LOW RISKS; test delta PASS; docs PASS. All blocking findings were
  repaired before PR creation.
- Repairs include commit-before-provider execution, activated fixed-service
  put-resolver composition, confirmed-missing replay with capacity
  reacquisition, concealed request-metadata validation, populated downgrade
  refusal, and preservation of existing hosted coverage gates.
- Initial hosted Backend run `30360132709` failed before execution because the
  new guide test module lacked semantic-lane custody. The bounded repair assigns
  it to `shared_foundations` and makes that ownership an exact regression;
  local canonical lane collection and CI/test-delta re-review pass.
- Hosted rerun `30360448433` cleared lane collection/validation and executed all
  lanes, then schema custody rejected the pre-constraint expected fingerprint.
  The exact hosted canonical fingerprint after the SHA-256 check constraint is
  now recorded; no schema or runtime behavior changed in that repair.
- Hosted run `30360906515` then executed 1,618 tests: 1,615 passed and three
  stale test fixtures failed. The bounded repair supplies complete guide
  lineage to the real admission proof, uses the pre-staging lineage lock helper
  for its intended test, and adds the new optional lineage fields to the quota
  unit fixture. Production code is unchanged by this repair.
- Hosted run `30361748346` proved all 1,618 shared, 236 project, and 217 task
  tests pass. Its sole failure was asyncpg rejecting the populated-downgrade
  test's multi-command prepared seed. The seed now executes six parameterized
  statements in one transaction; the exact isolated migration test passes.
- Hosted run `30363061162` again proved all shared, project, and task tests pass.
  Its sole schema failure was the migration fixture omitting the identity link
  now required for every human actor. The fixture creates the canonical active,
  verified link, and the exact isolated migration test passes.
- Hosted run `30364425613` passed every semantic lane, API E2E, and repository
  coverage, then measured the unchanged artifact-foundation gate at 89.77%.
  Focused tests now cover absent/missing/resolved replay selection and the
  fail-closed missing PREP transaction boundary; no threshold or production
  behavior changed.
- The final rebase preserved AUTH 11B project-read dependencies alongside the
  hidden ART route. Senior, QA, security/auth, and CI-integrity reconciliation
  reviews passed with no blockers.
- Rebased hosted run `30366469273` passed all lanes, API E2E, and repository
  coverage, raising artifact-foundation coverage to 89.87%. Additional focused
  tests cover invalid-role rejection before preparation and cleanup when PREP
  commit fails; production and the 90% threshold remain unchanged.
- Hosted run `30367711119` again passed all lanes, API E2E, and repository
  coverage, raising artifact-foundation coverage to 89.98%. A focused boundary
  proof now covers fail-closed partial guide lineage claims; production and the
  90% threshold remain unchanged.
- Hosted run `30369062154` remained at 89.98% after one repository branch varied
  between runs. A deterministic deny-only seam test now proves the default 04A
  selector rejects final PREP consumption, providing margin without changing
  production or the threshold.
- Hosted run `30370291310` passed artifact-foundation coverage, then failed only
  the ART-added whole-projects gate against merged AUTH 11B's unrelated 71.54%
  project coverage. The new out-of-scope gate and its self-test were removed;
  repository and every pre-existing subsystem gate remain unchanged.
- Final CodeRabbit review findings were triaged separately. Valid bootstrap
  cleanup, route exception-boundary, exact exception, typed digest, and result
  contract findings were repaired with focused tests. Reuse/query optimizations
  were deferred; PREP transaction duration remains an AUTH 04A activation gate.

## WS-ART-001-02D

- Signed explicit start verified on 2026-07-22 against trusted main
  `92b8a7aa`.
- L1 preimplementation plan review: PASS WITH CONDITIONS. The accepted design
  uses an artifact-owned typed activation seam with deny-only production
  wiring, exact ActionId/PermissionId evidence validation, canonical resource
  composition, transaction-local retry reauthorization, configuration-only
  readiness, and the existing bounded in-process metrics convention.
- Focused real-HTTP PostgreSQL evidence passes for binding discovery, redacted
  replica and receipt reads, verification diagnosis, reason-bound `202` retry,
  recovery/audit follow-through, admission usage, inactive readiness,
  pagination, and concealed denial. Required implementation reviewer fanout is
  pending on the candidate commit.
- First implementation review on `6f281793`: circuit-breaker PASS with a
  justified single-contract size exception; all nine reviewer tracks FAIL.
  Blocking findings covered canonical product/pre-binding lineage, recovery
  port bypass and authorization ordering, open response dictionaries, receipt
  cursor/audit completeness, project-scoped admission redaction, proactive
  metrics, safe quota reconciliation, CI gate activation, and missing
  adversarial HTTP/race proofs.
- Repair replaces page-derived scope with locked product and put-attempt
  lineage, routes retry through `ArtifactOperatorRecoveryPort`, authorizes
  canonical recovery facts before differentiated errors, installs strict
  response models and composite receipt cursors, covers every receipt audit
  lineage, requires project-scoped usage, emits all four pressure scopes from
  admission, reconciles configured limits under locked CAS guards, activates
  the exact API-router CI gate, and expands HTTP replay/race/concealment and
  pagination proof.
- Final internal review cleared every blocker. The first hosted PR #177 run
  passed Agent Gates, preflight, API E2E, and shards 1, 2, and 4. Shard 3 found
  one stale exact OpenAPI inventory assertion after the nine intended protected
  Operator routes were composed. Commit `536213ff` updates the exact total and
  protected counts/hashes; its single regression passes and all reviewer tracks
  reapproved the repair. The rerun passed all four shards, then the unchanged
  90 percent artifact foundation gate reported 89.50 percent. Commit
  `f1b9480c` adds meaningful resolver/page helper tests without changing the
  threshold or production code; 26 focused tests and all reviewer tracks pass.
  The next hosted run improved the unchanged gate to 89.70 percent. Commit
  `45725a85` adds exact audit-resource composition and missing-lineage tests,
  covering 14 additional Operator statements for the remaining roughly
  13-statement gap; 28 focused tests and all reviewer tracks pass. A final
  binding projection/missing-resource proof closes the last statement without
  changing production code or the threshold. Final Backend run `29894507010`
  passes preflight, API E2E, all four shards, repository coverage, every scoped
  coverage gate, and artifact foundation coverage at exactly 90.00 percent.

## WS-ART-001-02C3

- Signed explicit start verified on 2026-07-21 against trusted main `f2aa57a4`.
- L1 preimplementation plan review: PASS WITH CONDITIONS.
- Required conditions cover verification-job lineage, database recovery
  invariants, concurrency-safe replay, AUTH separation, atomic audits, terminal
  fencing, and cumulative coverage gates.
- First internal review batch returned blocking findings: taskless guide
  recovery was not representable, the Operator mutation seam was not yet
  fail-closed, and required fencing/terminal/migration proofs were incomplete.
- Repair in progress: recovery task context is nullable, the exact Operator
  authority seam defaults to deny until AUTH-owned activation, authorization
  evidence is retained in the initiation audit, and focused guide/authority
  drift tests were added. No publication claim is recorded yet.
- Re-review cleared taskless-guide and architecture blockers, then identified
  an authorization-ordering bypass on exact replay. Every normal and
  concurrent-winner replay now revalidates the persisted human identity and
  exact recovery authority before returning identifiers; denied replay is
  covered with zero-write assertions.
- Final internal review results on `841f2a38`: senior engineering PASS WITH
  LOW RISKS; architecture PASS WITH LOW RISKS; QA PASS; security PASS WITH LOW
  RISKS; product/ops PASS WITH LOW RISKS; reuse/dedup PASS WITH LOW RISKS; CI
  integrity PASS; test delta PASS; docs PASS.
- Accepted low risks are limited to legacy terminal-audit top-level metadata,
  private audit-builder ownership coupling, and duplicated human-proof shape;
  none changes authorization, recovery custody, or product lifecycle state.
- GitHub Actions run `29851665477` found two valid integration issues: an
  over-broad lineage trigger and an incomplete integrity-mismatch upload-item
  transition. Both received bounded repairs and their three failing tests pass
  locally; final internal re-review and hosted rerun remain.

## WS-ART-001-03B-PLAN

- Planning correction reviewed after ART-03A and AUTH-04A merged.
- Initial architecture, senior, QA, CI, and product/ops reviews found blocking
  scope, provenance, parser-boundary, verification, image-semantics, and
  operational-outcome gaps.
- Repairs split implementation into 03B1, 03B2, 03B3A, 03B3B, and 03B4;
  separated content extraction from binding/generation usage; defined isolated
  parsing, prompt-injection handling, stable setup errors, exact commands, and
  the later parser dependency approval gate.
- Final results: architecture PASS WITH LOW RISKS; senior engineering PASS WITH
  LOW RISKS; QA PASS WITH LOW RISKS; security PASS; product/ops PASS; CI PASS
  WITH CONDITIONS; docs PASS WITH LOW RISKS; reuse PASS WITH LOW RISKS; test
  delta PASS WITH CONDITIONS. Planning-PR conditions are resolved by committing
  the new contracts; the dependency checker remains a future 03B3B criterion.
- First external run: CodeRabbit was rate-limited and produced no findings.
  Agent Gates found five valid retired-vocabulary occurrences, now repaired.
  Backend recorded one unrelated AUTH PostgreSQL concurrency failure after
  1,651 passes; the repaired documentation head requires a fresh hosted rerun.
- CodeRabbit later posted five valid findings. The repair makes repository and
  scoped coverage gates explicit, fixes concrete extraction bounds and their
  adversarial proof, exhaustively maps failure statuses, normalizes guide-read
  wording, and adds locked revalidation immediately before report commit.
- The repaired-head review found one remaining recovery-semantics gap. Timeout
  and memory termination are now non-retryable limit failures; executor loss
  receives one bounded fresh-authority/materialization retry, then a stable
  extraction-failed outcome with only redacted diagnostics.

## WS-ART-001-03B2

- Implemented the hidden fixed-reader materialization and syntactic
  classification slice after merged 03B1.
- Initial internal review found active namespace drift, a broad scratch
  callback, unsafe external-relationship matching, and missing incident,
  boundary, cancellation, image, and downgrade tests.
- Repairs share the canonical replica namespace/store validator, use the
  canonical materializer facade and typed scratch inspector, parse bounded
  relationship XML fail closed, and add the complete focused proof set.
- Final architecture, security, QA, product/ops, CI-integrity, docs,
  reuse/dedup, test-delta, and senior-engineering reviews pass. Exact hosted
  PR-head checks remain the publication gate.
- CodeRabbit's six low-severity comments were repaired with naming and wording
  alignment, protocol variance, bounded nested buffering, JPEG marker handling,
  and immutable-conflict proof. Its generic docstring warning is superseded by
  the passing repository-owned hosted docstring gate.
- Senior-engineering, security, and QA repair-delta re-reviews pass with no
  blockers before the repaired PR head is published.

## WS-ART-001-03B3A

- Implemented the hidden default-deny extraction framework and standard-library
  text, Markdown, JSON, and CSV canonicalization slice.
- Initial L1 review found blocking sandbox, provenance, concurrency, workspace,
  retry, terminal replay, schema-proof, and test-surface issues.
- Repairs added exact guide/content locks, classification predicates, durable
  two-slot retry custody, extracted-attempt usage fencing, cleanup recovery,
  fixture-only resource probes, and expanded boundary/migration evidence.
- Architecture, security, senior engineering, product/ops, QA, docs, reuse,
  CI-integrity, and test-delta repair reviews pass with no blockers.

## WS-ART-001-03B3B1

- Selected the minimal complex-format dependency set: `pypdf==6.14.2`,
  `defusedxml==0.7.1`, and `Pillow==12.3.0`; no package or lock change occurs.
- Initial security, QA, senior-engineering, and product/ops review found that
  version-only declarations did not bind installed wheel hashes, excluded
  OOXML packages and optional groups could bypass the gate, format scopes were
  global, and wheel identity/platform coherence was under-specified.
- Repairs require exact hash-bound PyPI wheel references, scan runtime,
  optional, and dependency-group declarations, reject the prohibited OOXML
  package set, validate wheel identity/tags/platform, and scope imports per
  parser module.
- Focused proof passes with 34 tests and 92.94 percent checker coverage.
  Architecture, security, QA, product/ops, senior engineering, CI integrity,
  reuse/dedup, and test-delta reviews pass after repair. Docs confirmation and
  exact hosted PR-head behavior remain publication evidence.
- The first approval-authorized hosted run reached the canonical lane inventory
  and correctly failed because the new focused test module had not been assigned
  to a lane. The repair adds it to `shared_foundations`; no lane, test, or
  coverage policy is weakened.
- CodeRabbit's later review found three valid issues: ambiguous final-head
  wording, unstable type failures, and `COMMENTED` reviews erasing approval.
  All are repaired with regression proof. Its review-event checkout concern is
  rejected because hosted review-event run `30600808957` passed exact-head
  approval and executed the PR's lane inventory before its later failure.

## WS-ART-001-03B3B2

- Installed only the approved hash-bound `pypdf==6.14.2` wheel and added the
  bounded passive-PDF adapter to the existing isolated extraction child.
- Initial architecture review found eager pre-limit parser loading and obsolete
  v1 `unsupported` replay. Repairs made loading PDF-only after resource limits,
  retained seccomp before untrusted-byte parsing, introduced PDF policy v2,
  and reset only an exact-lineage obsolete retry budget.
- Initial QA/test-delta review found that generic action dictionaries and
  several JavaScript/submit/import/launch variants lacked proof. Repairs reject
  `/A` generically and cover real annotation actions and named active features.
- The new policy regression now proves v1 `unsupported` evidence remains
  historical while fresh v2 extraction succeeds and subsequent claims replay
  only the v2 success. The isolated PostgreSQL test passes.
- Focused PDF/extraction/architecture tests pass, PDF coverage remains above 90
  percent, the dependency/lock gate and canonical lane inventory pass, and no
  CI or coverage policy is weakened.
- Final architecture, security, QA, product/ops, senior engineering, CI
  integrity, docs, reuse/dedup, and test-delta reviews pass. Low future reuse
  advice is recorded but is not a blocker for this bounded format adapter.
- CodeRabbit's valid external findings add bounded `KeyError`/`IndexError`
  malformed-PDF mapping and document the 100,000-object inspection limit.

## WS-ART-001-03B3B3A

- Installed only the approved hash-bound `defusedxml` wheel and added hidden,
  validation-only OOXML container security without activating a document
  adapter, AUTH action, or sufficiency flow.
- Initial internal review found broad package-part acceptance, active metadata,
  DTD, nested-archive, root-relationship, shared-policy, and weak assertion
  gaps. Repairs use exact-format positive policies, strict passive metadata,
  parser-enforced XML denial, bounded read failures, canonical classifier facts,
  and zero-body-read ordering proof.
- Focused validation passes 136 tests with 93.92 percent OOXML coverage; lane,
  dependency, lock, stale-contract, link, and diff gates pass.
- Architecture, security, QA, senior engineering, product/ops, reuse, CI,
  test-delta, and docs review tracks pass after repair. Hosted GitHub and
  CodeRabbit evidence remain the publication gate.
- CodeRabbit's one valid external finding closes non-canonical root
  relationship parts and fails closed on malformed relationship-part shapes;
  focused security and test-delta re-review cover the repair.

## WS-ART-001-04A3

- Tightened the L1 contract before implementation to make 04A3 process-local,
  exclude legacy caller-owned package/manifest authority, freeze the manifest
  schema, and defer durable persistence/binding to 04C2/05A.
- Extended the existing safe outer-ZIP read with exact file hashes and
  executable normalization, then added the canonical manifest and typed
  unchanged-work gate without a second parser or durable/public side effect.
- Security review found that an optional current-predecessor selector left a
  future stale-comparison seam. Non-first comparison now requires exact equality
  with the locked/reloaded current selector and has omission/advancement proof.
- Focused evidence passes 85 tests and 92.11 percent owned coverage. Ruff,
  semantic-lane inventory, stale scans, links, and diff checks pass.
- Architecture, security, QA, product/ops, senior engineering, CI integrity,
  docs, reuse/dedup, and test-delta final reviews pass.

## WS-ART-001-PLAN4

- Replaced combined 04B with a bounded sequence: 04A4 removes the legacy
  caller-owned standalone precheck, 04B1 installs the sole versioned catalogue,
  04B2 executes mandatory platform/default checks on one sealed tree, and 04B3
  executes locked project rules and persists one bounded evidence set.
- Initial review found conflicting standalone-precheck docs, duplicated registry
  risk, stale caller package/hash/manifest authority, missing route-removal
  ownership, weakened coverage commands, and lost executable/crossed-state test
  obligations. All were repaired in the plan and canonical docs.
- The v0.1 catalogue gives every entry a stable ID/version, classification,
  phase/order/dependencies, typed inputs, bounded result, policy trace, and
  explicit operational state. Mandatory disabled entries fail preparation
  closed; only advisory entries may be disabled while execution continues.
- Broad sensitive-name heuristics are no longer silently universal blockers.
  High-confidence exclusions remain blocking; ambiguous patterns must be
  advisory or locked project-specific.
- Canonical flows now distinguish contributor ZIP/summary/attestation input from
  server-derived archive identity, semantic manifest, pre-submit evidence,
  verified admission, ArtifactBinding, and post-submit materialization.
- Architecture, security, QA, product/ops, senior engineering, CI integrity,
  reuse/dedup, and test-delta reviews pass after repair. Docs review identified
  and repaired final route-prefix and AUTH owner-table drift; final confirmation
  is recorded before publication.
- CodeRabbit then found seven valid specification gaps: namespace mapping,
  typed result provenance, infrastructure/finding separation, audit redaction,
  immutable catalogue snapshot locking, stale historical response wording, and
  residual client-shaped evidence fields. All are repaired after rebasing onto
  current main; the external response and complete PR trust bundle record the
  disposition.
- Focused architecture, security, QA, and docs re-review pass the external
  repair. Architecture additionally required authority-neutral shared result
  identity and complete platform/default dispatch mapping; both were repaired
  before final publication.
