# Implementation Backlog

## Review Lifecycle Status

Review/revision entries describe planned, unavailable v0.1 work. They become
executable only through the approved WS-REV chunk order, exact AUTH activation,
and REV-13 joint release; this backlog does not activate an endpoint or job.

## P0: Must Exist For v0.1

### Backend Foundation

- FastAPI backend scaffold
- modular monolith module layout
- thin routers
- service layer for workflow rules
- repository layer for database access
- interfaces for external boundaries
- adapters for external implementations
- SQLAlchemy 2.x async setup
- Alembic migrations
- Pydantic request and response schemas
- Postgres configuration
- async-first request and database boundaries
- test setup
- health endpoint

### Authentication Boundary

- verify external Flow authentication tokens
- map trusted token claims into Workstream actor context
- provide current actor dependency for protected routes
- attach actor id to audit events
- keep login, signup, password reset, and password storage out of Workstream
- keep local development auth separate from production Flow token verification

### Project And Guide

- create project
- upload/import project guide markdown
- version project guide
- mark one guide version active
- require guide approval before activation
- lock guide and policy versions on every task
- configure active ContributionPolicyVersion with explicit submitter/reviewer
  rules and award definitions
- configure submission artifact policy
- generate pre-submit checker policy
- configure post-submit checker policy
- configure review policy
- configure revision policy
- configure pre-review gate policy
- configure contribution policy and adapter bindings
- configure lessons-learned promotion rule

### Task Queue

- create task
- attach active guide version
- implement `SCREENING` lane before `READY`
- require readiness gate before task release
- assign skill tags
- freeze submitter ContributionPolicyVersion on TaskAssignment and reviewer
  version on ReviewLease
- change status only through allowed transitions
- record status audit event
- block direct `SUBMITTED -> ACCEPTED`
- block `REVIEW_PENDING` without checker run for exact submission version
- filter tasks by queue lane

### Submission

- create submission version
- attach output package/reference
- attach evidence items
- calculate package hash when file is uploaded
- calculate artifact hash manifest for every uploaded artifact
- require contributor attestation
- lock submission after auto-check starts
- create new submission version when any artifact changes

### Checker Framework

- checker runner
- checker result storage
- blocking status calculation
- project-specific required checkers
- API-readable checker results for the future reviewer surface
- contributor-visible failure summary
- bind checker run to exact submission version and artifact hash manifest
- bind checker run to package hash and locked task guide/policy context
- implement `check_evidence_integrity`
- implement `check_confidentiality_attestation`
- implement `check_low_quality_generated_artifacts`
- implement registered readiness checkers only after their contracts are locked
- implement project pre-submit intake execution from the locked project `PreSubmitCheckerPolicy`

### Review

- reviewer current work: active lease, one server-selected offer, or none
- accept decision
- needs-revision decision
- reject decision
- immutable blocking/advisory findings
- required fix per finding
- require evidence citation for accept decisions
- prevent self-review and conflict-of-interest review
- keep offline quality sampling separate from product decisions

### Revision Replay

- create replay for resubmission
- append one immutable response for each unresolved blocking finding
- append later `FindingResolution` values without editing the prior finding
- prepare the next attempt from the active Project Guide using the deterministic
  keep/forward-rebase/backward-rebase/block rule

### Compensation And Reputation

- reviewer contribution generated for every valid human Review; `accept`
  additionally creates FinalAcceptance, which alone sources the submitter
  contribution
- compensation awards reference the applicable contribution record; reputation
  remains a separate future consumer
- pending award fulfillment dashboard
- fulfilled status with immutable receipt and external reference
- future compensation issue/dispute workflow kept outside the v0.1
  `CompensationStatusProjection`
- new published `ContributionPolicyVersion` and `ContributionAwardDefinition`
  records for future amount changes; existing awards remain immutable
- reputation policy, events, and reviewer-pair anomaly behavior deferred to a
  separately approved initiative
- fast-accept-without-evidence flags

### Dashboards

- project status counts
- queue counts
- accepted count
- needs revision count
- pending compensation fulfillment
- fulfilled compensation total
- stale active tasks
- review pending age
- oldest unfulfilled compensation award age

## P1: Important After Core Loop Works

- separately approved future review-quality/adjudication workflow
- reviewer disagreement tracking
- registered Project Manager repair and Operator recovery controls
- project guide approval workflow
- checker false positive flag
- task batch import
- CSV export for compensation fulfillment reconciliation
- evidence hash verification
- notification events
- project lessons learned page
- guide change proposal flow

## P2: Later

- external source adapters
- agent execution integration
- public marketplace
- automated client billing
- on-chain settlement adapters
- advanced fraud detection
- organization/team accounts
- API for third-party task sources

## Deferred By Design

Do not build these in v0.1:

- internal coding workspace
- agent runtime
- chat-first workflow
- public bidding system
- complex dispute court
- blockchain settlement dependency

These are not rejected ideas. They are deferred because the task evaluation and contribution infrastructure must work first.
