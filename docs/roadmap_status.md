# Current Workstream v0.1 Status

This is the capability ledger for current v0.1 development. It records what is
implemented on `main`, what is being integrated, and what remains before the
v0.1 lifecycle is proven. It intentionally contains no delivery calendar.

The complete product is source-agnostic governed contribution infrastructure.
This ledger deliberately tracks the narrower v0.1 proof: one secured path from
project rules and a task through exact artifact custody, checks, authorized
review, revision when needed, and immutable contribution facts. Flow-token
verification is the current identity adapter, not the product definition.

Implementation claims must be supported by code, migrations, tests, and merged
history. A plan, contract, draft pull request, or historical specification is
not evidence that behavior is live.

## v0.1 Release Boundary

The target remains:

```text
Project Guide
-> Task
-> Submission Packet
-> Automated Checks
-> Human Review
-> Revision when required
-> Contribution Records
-> Conditional Compensation Award / Fulfillment
-> Contribution Evidence For Future Reputation Projection
```

The release bar is one secured, observable, end-to-end lifecycle using the
locked backend and storage architecture. Marketplace expansion, blockchain
settlement, external source adapters, automated routing, and agent workspaces
remain outside v0.1.

## Implemented On `main`

### Platform foundation

- FastAPI backend, SQLAlchemy async persistence, Alembic migrations, and
  PostgreSQL record storage.
- Async checker and project-setup execution with Celery and Redis where durable
  retries and isolation are required.
- Provider-neutral immutable artifact storage with MinIO protocol proof for
  local development and CI, plus bounded private processing scratch.
- External integrations composed through the typed ADR 0014 adapter boundary.

### Identity and authorization

- External Flow-token verification with issuer boundaries and request context.
- Canonical actors, identity links, actor lifecycle controls, and human lineage.
- Closed permission/action catalogues, deny-by-default authorization, bootstrap
  administrator grants, fixed-service identities, and runtime admission.
- Project-role grants, administrative APIs, authority evidence, idempotency,
  and PostgreSQL-backed rate controls.
- Project setup plus project create, guide mutation, binding, and read
  authorization foundations.
- Immutable review/revision policy identities, AUTH-owned policy mutation,
  complete planned REV action and fixed-service catalogues, and the typed
  fail-closed PREP/read handoff required for hidden REV implementation. These
  foundations merged through PRs #242, #248, #255, and #257 respectively.
  Contributor bundle preparation now uses the exact assigned-contributor AUTH
  PREP boundary from WS-ARCH-001-02G. Hidden TASK-owned Submission creation,
  admission consumption, and fixed-service binding are active through
  WS-ARCH-001-02H; only the later public clean cut remains gated.
  These readiness contracts do not make the review lifecycle available.
- Project Manager-authorized guide-sufficiency creation, asynchronous agent-run
  requests, and warning acknowledgement with UUID replay custody; automatic
  readiness and manual recovery converge on one deterministic setup task, and
  only the fixed project-setup service executes sufficiency and creates its
  authoritative report.

### Project, task, submission, and checker foundations

- Project guides, task queue records, task lifecycle guards, work context, and
  contributor submission requirements.
- Versioned submission packets with evidence references, locked context,
  finalization, and contributor privacy boundaries.
- Typed checker contracts, registry and runner behavior, durable checker
  records, pre-submit checks, and the automatic pre-review gate.
- Trusted retry, supersession, audit evidence, and real API contract drills for
  the implemented lifecycle.

### Guide-source and artifact processing

- Immutable source snapshots, source-media classification, typed extraction
  boundaries, and persisted extraction results.
- PDF, DOCX, and XLSX extraction with bounded input handling and OOXML security
  controls.
- Image metadata handling and persisted guide-sufficiency evidence.
- Guide materialization from persisted artifact-processing evidence.
- Fixed-service guide-source reads and binding creation with authorization,
  custody, lineage, rate-control, and stale-generation enforcement.
- Hidden unified Project Guide compilation custody with immutable attempt and
  result lineage, crash-safe reservation/recovery states, append-only
  supersession, and a deny-only public AUTH capability. Request/execute
  authority and live compilation remain unavailable.
## Integration In Progress

The following areas have merged planning, contracts, or partial foundations,
but are not all complete as one production path:

- Hidden contributor-ZIP pre-submit execution: fixed-service authority precedes
  byte access; one manifest-verified callback-scoped scratch tree runs the
  platform/default and project-policy phases; cleanup precedes one immutable
  combined evidence set. Evidence-linked durable put intent, verification, and
  capacity-charged ready-admission publication are merged. Contributor
  preparation authority is active through WS-ARCH-001-02G; hidden admission
  consumption, TASK-owned Submission creation, and final binding are active
  through 02H; the later public clean cut remains gated.

- integration of the merged review/revision policy and authorization readiness
  contracts into hidden REV lifecycle behavior;
- hidden review queue, reviewer assignment/claim, immutable decisions, and revision
  replay on the canonical authorization boundary;
- atomic review-to-contribution and conditional compensation integration.

The immediate upstream integration milestone is narrower and precedes live REV
work: one admission-backed immutable Submission must produce one durable final
current post-submit checker result with `routing_recommendation = allow_review`
through PROJECTS, TASKS, ART, CHECKERS, and AUTH public APIs. The existing
legacy pre-review result does not satisfy that milestone.

Open pull requests are the authoritative view of the exact code currently under
review. Their presence does not change the implemented-on-`main` list above.

## Remaining v0.1 Capability Milestones

1. Complete the remaining artifact custody chain: contributor intake cleanup,
   archive safety, semantic change gating, post-submit checker materialization,
   recovery, provider proof, and the later public cutover.
   Hidden durable admission, Submission creation, and final binding are already
   merged through WS-ARCH-001-02H.
2. Register exact ContributionPolicy authority while unavailable; implement
   and separately activate adapter-binding and ContributionPolicy behavior;
   expose CON validation; then bind one exact published,
   complete, binding-valid ContributionPolicyVersion at guide activation, and
   lock it on each task before that task becomes claimable. TaskAssignment
   inherits the task lock without a claim-time lookup, and each immutable
   Submission stamps the exact version governing that attempt.
   Complete `WS-ARCH-001-03A` through `WS-ARCH-001-03C` to activate the sole
   replacement task/assignment path, then run `WS-ARCH-001-CP09` to remove the
   retired guide-bound economic path only after that replacement is live.
3. Continue independent REV schema and packet-contract foundations. After
   canonical `allow_review`, activate admission and claim only when ReviewLease
   copies the exact ContributionPolicyVersion stamped on the admitted
   Submission, without a claim-time lookup.
4. Persist ContributionRecord and CompensationAward before live Review
   decisions. Every final decision atomically creates the reviewer record and
   evaluates its frozen rule; accept additionally creates FinalAcceptance and
   the submitter record and evaluates the assignment-frozen rule.
   `needs_revision` and `reject` create neither FinalAcceptance nor a submitter
   record.
5. Complete review/revision findings, replay, recovery, contribution-award
   fulfillment, idempotency, reconciliation, product reads, and audit behavior
   without making settlement a prerequisite.
6. Preserve authoritative contribution evidence for future reputation
   projections; reputation projection remains deferred from the v0.1 runtime.
7. Prove the complete v0.1 lifecycle through real API, database, durable-job,
   storage, security, and operational recovery tests.
8. Add the React/Vite/TypeScript product surfaces only against stable and tested
   backend contracts.
9. Run a real internal pilot and close findings without weakening lifecycle,
   authorization, storage, or evidence guarantees.

These are dependency-ordered capability milestones, not a schedule. Distinct
initiatives may proceed concurrently when their contracts and integration
boundaries do not conflict.

## How To Read Repository Status

- **Implemented:** code and required evidence are merged on `main`.
- **In progress:** a bounded branch or pull request exists; behavior is not yet
  part of `main`.
- **Planned:** an accepted specification or initiative describes future work;
  behavior is unavailable until implemented and merged.
- **Historical:** the document records prior intent or evidence and does not
  control current work.

Use [CONTRIBUTING.md](../CONTRIBUTING.md) to start work and the
[Historical Planning Index](historical_planning.md) when investigating earlier
decisions.
