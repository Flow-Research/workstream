# System Architecture

## Summary

Workstream is organized around projects, tasks, submissions, checks, reviews, revisions, payments, and reputation.

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
  Payment dashboard
  Reputation dashboard

Backend API
  Project service
  Source/import service
  Task service
  Submission service
  Checker service
  Review service
  Revision service
  Contribution service
  Evidence service
  Payment service
  Reputation service

Storage
  Postgres for records
  Object storage abstraction for files and evidence
  Append-only audit log for state transitions
  Hash-locked artifacts after submission lock

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
- File storage: local development can use filesystem-backed storage, but it must sit behind an object-storage abstraction compatible with R2/S3-style storage
- Auth: external Flow authentication token verification through an auth interface/adapter; Workstream does not own login, signup, password reset, password storage, or primary auth sessions
- Jobs: async-first background execution through Celery-backed workers for product lifecycle jobs

Async policy:

- API handlers use async FastAPI patterns where I/O is involved.
- Database access, file storage, checker execution orchestration, notifications, and audit writes use non-blocking boundaries.
- Long-running setup and checker work must not block request/response paths.
- Project setup automation and checker runs create records immediately, return an accepted/running state where applicable, and complete through a Celery worker.
- FastAPI background tasks are not used for Workstream product lifecycle jobs.
- A different durable queue can replace Celery later only with an ADR-level reason.

Rust, TypeScript, or another language can be introduced later for a specific layer only with a clear reason, such as high-throughput checker execution, worker isolation, frontend integration, or a specialized SDK/runtime requirement. They do not replace the Python/FastAPI API by default.

Frontend policy:

- React + Vite owns the internal operations UI.
- The frontend talks to FastAPI through explicit API contracts.
- The UI stays dashboard/form/workflow focused, not a marketing site.
- Next.js is deferred unless server rendering, public pages, or full-stack React routing becomes a real requirement.

The architecture avoids framework coupling in the domain model. Project, task, submission, checker, review, revision, contribution, payment, reputation, and audit behavior remain portable.

Auth policy:

- Workstream verifies Flow-issued tokens through an `AuthVerifier` interface.
- Production auth uses a Flow token verifier adapter.
- Local development may use a mock verifier only outside production.
- Actor identity is based on stable Flow token issuer and subject, not email.
  Flow issuer plus subject remains the canonical portable identity anchor;
  Workstream actor id is a local durable product reference derived from that
  pair.
- Flow Identity token audience, scope, token id, client, space, and delegation
  claims remain token/claim context. Workstream may preserve them in audit or
  actor claim snapshots, but exact task, submission, review, payment, and
  evidence access is still authorized locally by Workstream.
- Workstream may keep local actor/profile records for workflow state,
  workflow eligibility, audit display, and reputation, but those records do not
  replace Flow as the auth source and do not grant route access.
- Route role and permission checks may use trusted role claims from the current
  `ActorContext` only as the v0.1 bootstrap path. The long-term authorization
  source is a Workstream-owned role-assignment layer. Local actor/profile
  records may add workflow eligibility conditions, such as an active worker
  profile before task claim, but they are not route permission authority.
- Routers use the pure current-actor dependency when they only need verified
  Flow identity. Routes that need local actor registry side effects use a
  separate registration dependency that first resolves the current actor, then
  records or refreshes local actor/profile metadata. Permission checks live in
  service or policy code so workflow rules do not scatter across HTTP handlers.
- Audit records preserve actor id, external subject, issuer, role/claim context, and whether dev/mock auth was used when relevant.

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
- payment policy
- skill taxonomy

Project setup visibility APIs expose the latest setup run, sufficiency reports,
submission artifact policies, the current effective project policy, and the
compiled project pre-submit checker policy summary to `admin` and
`project_manager` actors. These reads replace operator DB inspection for setup
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
- worker-safe task work context
- worker-safe submission requirements derived from locked effective project policy
- locked task provenance for `admin` and `project_manager` actors

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

- review queue
- findings
- review decisions
- second-review flags
- reviewer audit history

### Revision Service

Owns:

- prior feedback replay
- fix summaries
- issue closure
- resubmission linkage

### Contribution Service

Owns:

- contribution record creation after acceptance
- accepted submission linkage
- accepted review linkage
- acceptance evidence references
- artifact hash manifest references
- export status
- payment and reputation attachment point

### Evidence Service

Owns:

- file attachments
- logs
- hashes
- screenshots
- checker output
- reviewer notes
- artifact immutability after checker execution begins

### Payment Service

Owns:

- payment records derived from locked payment policy context
- accepted amount
- pending payout
- paid amount
- payment status
- payment references

### Reputation Service

Owns:

- worker performance
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
- payment transition events
- manual overrides
- guide and policy version references

## First Database Choice

Use Postgres for records.

Use a storage interface for large files and evidence. During local development, the implementation can store files on the local filesystem, but callers use stable object identifiers, content hashes, and an object-storage-style API so the backend will later target R2, S3, or another compatible object store without changing submission/evidence semantics.

Submission artifacts are hash-locked once a checker run starts. Any changed artifact creates a new submission version instead of mutating the old one.

Every important lifecycle action creates an append-only audit event. State is readable from current records, and audit history explains how the system got there.

## API Style

Use explicit domain APIs rather than generic CRUD-only endpoints.

Examples:

```text
POST /projects
POST /projects/:id/tasks
POST /tasks/:id/claim
POST /tasks/:id/submit
POST /submissions/:id/run-checks
POST /reviews/:id/decision
POST /submissions/:id/revision-replay
POST /contributions/:id/export
POST /payments/:id/mark-paid
```

## v0.1 Gates

Workstream has three v0.1 quality gates:

- project activation gate
- task screening gate
- submission quality gate

The proposal's origin qualification and task ingestion gates are future adapter concepts. In v0.1, manual, markdown, and CSV intake normalize into the same task contract and pass through project activation plus task screening before work reaches workers.

## Audit Log

Workstream needs an append-only audit log from v0.1.

Audit events cover:

- task status transitions
- assignment changes
- submission creation and locking
- checker runs
- review decisions
- revision replay closure
- payment status transitions
- reputation events
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
