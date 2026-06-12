# Task Lifecycle Sequence

This sequence shows the v0.1 operating loop from project guide to accepted contribution and payment/reputation records.

It is intentionally separate from the future identity and settlement diagram. v0.1 records payment status and reputation events internally; it does not execute on-chain settlement or write portable agent reputation.

```mermaid
sequenceDiagram
  autonumber
  actor PM as Project Manager
  actor Worker as Human-Agent Contributor
  actor Reviewer as Reviewer
  participant UI as React UI
  participant API as FastAPI Backend
  participant Auth as Flow Auth Verifier
  participant DB as Postgres
  participant Storage as Storage Abstraction
  participant Checks as Checker Runner

  PM->>UI: Create project, guide, and policies
  UI->>API: POST project / guide / policies
  API->>Auth: Verify Flow token
  Auth-->>API: ActorContext(project_manager)
  API->>DB: Persist draft guide and checker/review/revision/payment policy context

  PM->>UI: Activate guide
  UI->>API: POST activate guide
  API->>DB: Validate required policy context and mark guide active
  API->>DB: Audit project activation

  PM->>UI: Create and screen task
  UI->>API: POST task, then screen/release
  API->>DB: Lock active guide and policy versions onto task
  API->>DB: Move DRAFT -> SCREENING -> READY
  API->>DB: Audit transitions

  Worker->>UI: Claim task
  UI->>API: POST claim
  API->>Auth: Verify Flow token
  Auth-->>API: ActorContext(worker)
  API->>DB: Validate visibility, profile, skill tags, and READY status
  API->>DB: Create assignment and move READY -> CLAIMED -> IN_PROGRESS

  Worker->>UI: Submit packet
  UI->>API: POST submission packet with evidence and artifact manifest
  API->>Storage: Store or reference artifacts through storage abstraction
  API->>DB: Create immutable submission version
  API->>DB: Lock submission context and audit submission

  API->>Checks: Start automated checks asynchronously
  Checks->>Storage: Read referenced artifacts
  Checks->>DB: Persist checker run and results
  Checks->>DB: Keep task AUTO_CHECKING while pre-review gate runs
  Checks->>DB: Move to REVIEW_PENDING, NEEDS_REVISION, or internal task_setup_blocked

  Reviewer->>UI: Review packet
  UI->>API: Submit review decision
  API->>Auth: Verify Flow token
  Auth-->>API: ActorContext(reviewer)
  API->>DB: Store decision: accept, needs_revision, or reject

  alt needs_revision
    API->>DB: Create revision requirements from findings
    Worker->>UI: Submit revision replay
    UI->>API: POST revision replay and new submission version
    API->>DB: Link replay to prior findings
    API->>Checks: Run checks again
  else accept
    API->>DB: Create contribution record
    API->>DB: Create payment record with PENDING status
    API->>DB: Create reputation event
    API->>DB: Audit acceptance
  else reject
    API->>DB: Store rejection decision and findings
    API->>DB: Apply payment and reputation policy effects
    API->>DB: Audit rejection
  end
```

## Lifecycle Invariants

- A task cannot enter `READY` without locked guide, checker, review, revision, and payment policy context.
- A worker submission creates a new immutable submission version; locked artifacts are not edited in place.
- Review decisions are exactly `accept`, `needs_revision`, or `reject`.
- `needs_revision` starts a revision loop and must replay prior findings.
- Accepted work creates a contribution record before payment or reputation records.
- Payment status is separate from task acceptance.
