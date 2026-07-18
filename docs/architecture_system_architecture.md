# System Architecture

## Summary

Workstream is organized around projects, tasks, submissions, checks, reviews,
revisions, contributions, compensation, and reputation.

The review/revision component described below is a planned target contract. Its
routes remain unavailable until hidden REV behavior, exact AUTH activation, and
the REV-13 joint release complete. `docs/spec_review_lifecycle.md` is normative.

The architecture stays modular enough to support different project types without becoming abstract to the point that no project can use it.

The visual architecture pack lives in [Architecture Diagrams](diagrams/README.md). It separates the 30-day v0.1 implementation from later adapter boundaries such as ERC-8004 agent identity and reputation, ERC-8183 task contract and escrow, x402 payment requests, OmniClaw settlement orchestration, and USDC settlement.

## High-Level Components

```text
Frontend
  Project dashboard
  Task queue
  Task detail
  Submission page
  Checker results
  Review queue
  Review page
  Compensation dashboard
  Reputation dashboard (deferred)

Backend API
  Actor service
  Authorization service
  Project service
  Source/import service
  Task service
  Submission service
  Checker service
  Review service
  Revision service
  Contribution and compensation service
  Evidence service
  Reputation service (deferred)

Storage
  Postgres for records
  Object storage abstraction for files and evidence
  Append-only audit log for state transitions
  Hash-locked artifacts during successful submission creation

Execution
  External at first
  Async checker/background workers
  Optional future agent runtime
```

## v0.1 Stack

The v0.1 stack is locked for implementation.

Approved stack:

- Frontend: React + Vite + TypeScript
- Backend API: Python with FastAPI
- ORM, migrations, and API schemas: SQLAlchemy 2.x async + Alembic + Pydantic schemas
- Database: Postgres
- Artifact storage: product services use ART v2 typed, provider-neutral
  capabilities; local development may use the filesystem provider, AWS S3 is
  the v0.1 hosted provider, and MinIO is the local/CI protocol proof
- Auth: external Flow authentication token verification through an auth interface/adapter; Workstream does not own login, signup, password reset, password storage, or primary auth sessions
- Jobs: async-first background execution through Celery-backed workers for product lifecycle jobs

Async policy:

- API handlers use async FastAPI patterns where I/O is involved.
- Database access, file storage, checker execution orchestration, notifications, and audit writes use non-blocking boundaries.
- Long-running setup and checker work must not block request/response paths.
- Project setup automation and checker runs create records immediately, return an accepted/running state where applicable, and complete through a Celery worker.
- FastAPI background tasks are not used for Workstream product lifecycle jobs.
- A different durable queue can replace Celery later only with an ADR-level reason.

Rust, TypeScript, or another language can be introduced later for a specific layer only with a clear reason, such as high-throughput checker execution, execution-process isolation, frontend integration, or a specialized SDK/runtime requirement. They do not replace the Python/FastAPI API by default.

Frontend policy:

- React + Vite owns the internal operations UI.
- The frontend talks to FastAPI through explicit API contracts.
- The UI stays dashboard/form/workflow focused, not a marketing site.
- Next.js is deferred unless server rendering, public pages, or full-stack React routing becomes a real requirement.

The architecture avoids framework coupling in the domain model. Project, task,
submission, checker, review, revision, contribution, compensation, reputation,
and audit behavior remain portable; reputation behavior remains deferred.

Auth policy:

- Workstream verifies Flow-issued tokens through an `AuthVerifier` interface.
- Production auth uses a Flow token verifier adapter.
- Local development may use a mock verifier only outside production.
- Verified tokens establish issuer/subject identity, subject kind, audience,
  time validity, and coarse scope; token roles are not product authority.
- `ActorProfile` and `ActorIdentityLink` provide the local actor root and
  revocable issuer/subject binding.
- `AdminRoleGrant` and exact-project `ProjectRoleGrant` records supply candidate
  permissions. Actor/resource/lifecycle guards decide the final result.
- Application services load canonical resources and call the single
  authorization service; routers do not evaluate grants or infer scope.
- Sensitive mutations revalidate actor/link/grant state in the same
  `AsyncSession` transaction that writes state and append-only authority
  evidence.
- Internal system workers use fixed system principals and explicit system permissions,
  never fabricated human roles.
- Audit records preserve bounded actor, issuer, matched grant/permission,
  resource, request/correlation, and decision context without raw tokens or
  full claims.

## Component Responsibilities

### Project Service

Owns:

- project metadata
- guide
- project setup run ledger
- submission artifact policy
- generated project pre-submit checker policy
- post-submit checker policy
- review policy
- revision policy
- skill taxonomy

Project setup visibility APIs expose the latest setup run, sufficiency reports,
submission artifact policies, the current effective project policy, and the
compiled project pre-submit checker policy summary through covered Project
Manager or authorized Operator/Audit projections. These reads replace operator database reads for setup
drills, but they do not make `ProjectSetupRun` a policy source of truth.

### Source/Import Service

Owns:

- manual intake metadata
- markdown import metadata
- CSV import metadata
- source payload hashes
- import batch ids
- internal screening rejection records

External origin onboarding, source adapters, and webhook drop notifications are later extensions. v0.1 keeps intake controlled and manual-first.

### Task Service

Owns:

- task creation
- task assignment
- task status
- task requirements
- task acceptance criteria
- queue views
- contributor-safe task work context
- contributor-safe submission requirements derived from locked effective project policy
- permission-scoped locked task provenance for covered Project Managers and
  authorized Operator/Audit projections

### Submission Service

Owns:

- submitted output
- submission packet
- attached evidence
- package metadata
- submission versioning

### Checker Service

Owns:

- checker registry
- checker execution
- checker results
- severity handling
- review gate enforcement

### Review Service

Owns:

- server-selected ReviewQueueEntry routing and ReviewLeases
- immutable ReviewPacketManifest and lease-bounded Review Context
- immutable Reviews, ReviewFindings, FindingResolutions, and FinalAcceptance
- decision orchestration, task effects, audit, and shared-outbox staging
- reviewer history and bounded authorized chain metadata

### Revision Service

Owns:

- immutable RevisionContextPreparation chains
- SubmissionFindingResponse and FindingResolution lineage
- exact Project Guide keep/forward/backward/block classification
- resubmission and preferred-return linkage

### Artifact Service Boundary

Owns:

- ART v2 immutable content, binding, verification, candidate/finalize, and recovery
- narrow active-lease packet read
- REV-owned packet membership and finding/response evidence semantics
- no provider or raw byte-only ArtifactStore import in review services

### Contribution And Compensation Service

Owns:

- immutable reviewer `completed_review` sourced from Review/ReviewLease
- immutable submitter `accepted_submission` sourced only from FinalAcceptance
- project ContributionPolicy and immutable published versions
- independently frozen TaskAssignment and ReviewLease policy-version references
- immutable CompensationAwards for payable contribution rules only
- immutable fulfillment receipts and rebuildable status projections
- contribution and compensation outbox events

### Reputation Service (Deferred)

Owns:

- contributor performance
- reviewer performance
- skill-level score
- revision and rejection rates
- task-difficulty weighting

### Audit Event Service

Owns:

- state transition events
- checker run events
- review decision events
- revision submission events
- compensation-award and fulfillment events
- manual overrides
- guide and policy version references

## First Database Choice

Use Postgres for records.

Use ART v2 provider-neutral capabilities for large files and evidence. During
local development, the implementation can store files on the local filesystem;
hosted v0.1 uses AWS S3 and local/CI integration uses MinIO without changing
submission or evidence semantics.

Submission artifacts are hash-locked during successful submission creation
before automatic checker execution is queued. Any changed artifact creates a new
submission version instead of mutating the old one.

Every important lifecycle action creates an append-only audit event. State is readable from current records, and audit history explains how the system got there.

## API Style

Use explicit domain APIs rather than generic CRUD-only endpoints.

Existing APIs follow the `/api/v1` prefix. The examples below are conceptual;
planned review/revision routes are not registered before REV-13.

```text
POST /projects
POST /projects/:id/tasks
POST /tasks/:id/claim
POST /tasks/:id/submit
POST /submissions/:id/finalize          # operational repair for the automatic checker gate
GET /submissions/:id/checker-runs
planned reviewer current-work read under /api/v1
planned active-lease decision mutation under /api/v1
planned revision submission through canonical task submission.create
POST /contributions/:id/export
POST /compensation-awards/:id/fulfillment-receipts
```

## v0.1 Gates

Workstream has three v0.1 quality gates:

- project activation gate
- task screening gate
- submission quality gate

The proposal's origin qualification and task ingestion gates are future adapter concepts. In v0.1, manual, markdown, and CSV intake normalize into the same task contract and pass through project activation plus task screening before work reaches contributors.

## Audit Log

Workstream needs an append-only audit log from v0.1.

Audit events cover:

- task status transitions
- assignment changes
- submission creation and finalization
- checker runs
- review decisions
- immutable revision responses and later finding resolutions
- compensation award, delivery, and fulfillment transitions
- reputation events only after separate implementation
- admin overrides

## Future Extension Points

Source adapters:

- import tasks from external systems
- map external schema to WorkstreamTask
- submit accepted outputs back to external systems

Agent runtime:

- assign work to human-agent pairs
- track agent execution logs
- preserve owner review gate

Settlement adapters:

- manual payout
- Stripe or bank ledger
- stablecoin payout
- ERC-8183 job settlement
- x402 micropayment support

Reputation adapters:

- internal reputation
- portable on-chain identity
- external reviewer score integration

## Anti-Overbuild Boundary

Do not build source adapters, agent runtime, marketplace discovery, or blockchain settlement until the internal lifecycle works with real pilot tasks.
