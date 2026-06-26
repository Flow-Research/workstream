# Implementation Backlog

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
- configure base amount and currency
- configure submission artifact policy
- generate pre-submit checker policy
- configure post-submit checker policy
- configure review policy
- configure revision policy
- configure pre-review gate policy
- configure payment policy, including payment dispute policy
- configure lessons-learned promotion rule

### Task Queue

- create task
- attach active guide version
- implement `SCREENING` lane before `READY`
- require readiness gate before task release
- assign skill tags
- assign base amount
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
- require worker attestation
- lock submission after auto-check starts
- create new submission version when any artifact changes

### Checker Framework

- checker runner
- checker result storage
- blocking status calculation
- project-specific required checkers
- API-readable checker results for the future reviewer surface
- worker-visible failure summary
- bind checker run to exact submission version and artifact hash manifest
- bind checker run to package hash and locked task guide/policy context
- implement `check_evidence_integrity`
- implement `check_confidentiality_attestation`
- implement `check_low_quality_generated_artifacts`
- implement registered readiness checkers only after their contracts are locked
- implement project pre-submit intake execution from the locked project `PreSubmitCheckerPolicy`

### Review

- review queue
- accept decision
- needs-revision decision
- reject decision
- structured findings
- required fix per finding
- require evidence citation for accept decisions
- prevent self-review and conflict-of-interest review
- reviewer simulation gate for first-of-kind or high-value tasks

### Revision Replay

- create replay for resubmission
- map each prior finding to a fix
- require evidence per fix
- reviewer closure status

### Payment And Reputation

- contribution record generated on acceptance
- payment and reputation records reference contribution record
- payment record generated on acceptance
- pending payout dashboard
- paid status with reference
- disputed payment status
- payment adjustment record for amount changes
- worker reputation events
- reviewer reputation events
- reviewer-pair anomaly flags
- fast-accept-without-evidence flags

### Dashboards

- project status counts
- queue counts
- accepted count
- needs revision count
- pending payout
- paid total
- stale active tasks
- review pending age
- accepted unpaid age

## P1: Important After Core Loop Works

- second-review assignment
- reviewer disagreement tracking
- admin override controls
- project guide approval workflow
- checker false positive flag
- task batch import
- CSV export for payment reconciliation
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
