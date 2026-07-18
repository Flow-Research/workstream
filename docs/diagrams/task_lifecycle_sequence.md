# Task Lifecycle Sequence

This sequence shows the v0.1 operating loop from project guide to reviewer and
submitter contributions, conditional compensation awards, and fulfillment.

It is intentionally separate from the future identity and settlement diagram.
v0.1 records immutable awards and fulfillment receipts/projections; reputation
events and portable reputation are deferred.

```mermaid
sequenceDiagram
  autonumber
  actor PM as Project Manager
  actor Finance as Finance Authority
  actor Contributor as Human-Agent Contributor
  actor Reviewer as Reviewer
  participant UI as React UI
  participant API as FastAPI Backend
  participant Auth as Flow Auth Verifier
  participant Authorization as Workstream Authorization
  participant DB as Postgres
  participant Artifacts as ART v2 Capabilities
  participant Checks as Checker Runner

  PM->>UI: Create project, guide, tasks, and setup/checker/review/revision configuration
  UI->>API: POST project / guide / configuration
  API->>Auth: Verify Flow token
  Auth-->>API: Verified external identity
  API->>Authorization: Resolve actor profile and local grants
  Authorization->>Authorization: require(project.create/configure, candidates, resource/lifecycle guards)
  Authorization-->>API: Allowed AuthorizationContext with matched Project Manager grant
  API->>DB: Persist draft guide and checker/review/revision policy context

  Finance->>UI: Publish contribution policy
  UI->>API: POST contribution policy version
  API->>Auth: Verify Flow token
  Auth-->>API: Verified external identity
  API->>Authorization: require(contribution_policy.publish, candidates, project/resource/lifecycle guards)
  Authorization-->>API: Allowed with matched Finance Authority grant
  API->>DB: Publish project contribution policy version independently

  PM->>UI: Activate guide
  UI->>API: POST activate guide
  API->>Authorization: require(guide.activate, candidates, project/lifecycle guards)
  Authorization-->>API: Allowed with matched grant and permission
  API->>DB: Validate required policy context and mark guide active
  API->>DB: Audit project activation

  PM->>UI: Create and screen task
  UI->>API: POST task, then screen/release
  API->>Authorization: require(task.manage, candidates, project/lifecycle guards)
  Authorization-->>API: Allowed with matched grant and permission
  API->>DB: Lock active guide and policy versions onto task
  API->>DB: Move DRAFT -> SCREENING -> READY
  API->>DB: Audit transitions

  Contributor->>UI: Claim task
  UI->>API: POST claim
  API->>Auth: Verify Flow token
  Auth-->>API: Verified external identity
  API->>Authorization: Resolve actor profile and project grants
  Authorization->>Authorization: require(task.claim, candidates, assignment/resource/lifecycle guards)
  Authorization-->>API: Allowed AuthorizationContext with matched submitter grant
  API->>DB: Validate visibility, qualification, skill tags, and READY status
  API->>DB: Create assignment and move READY -> CLAIMED -> IN_PROGRESS

  Contributor->>UI: Submit packet
  UI->>API: POST submission packet with evidence and artifact manifest
  API->>Auth: Verify Flow token
  Auth-->>API: Verified external identity
  API->>Authorization: require(submission.create, candidates, ownership/resource/lifecycle guards)
  Authorization-->>API: Allowed with matched submitter grant
  API->>Artifacts: Finalize verified artifact bindings
  API->>DB: Create immutable submission version
  API->>DB: Lock submission version and audit submitter-owned finalization

  API->>Checks: Enqueue automated checks through Celery
  Checks->>Artifacts: Read exact authorized artifacts
  Checks->>DB: Persist checker run and results
  Checks->>DB: Keep task EVALUATION_PENDING while pre-review gate runs
  Checks->>DB: Move to REVIEW_PENDING, NEEDS_REVISION, or internal task_setup_blocked

  Reviewer->>UI: Request current work
  UI->>API: GET current work
  API->>Auth: Verify Flow token
  Auth-->>API: Verified external identity
  API->>Authorization: Resolve actor profile and project grants
  Authorization->>Authorization: require(review.queue.read, resource/lifecycle guards)
  Authorization-->>API: Allowed AuthorizationContext with matched reviewer grant
  API-->>UI: Active lease, one server-selected offer, or none

  Reviewer->>UI: Claim server-selected offer
  UI->>API: POST claim
  API->>Auth: Verify Flow token
  Auth-->>API: Verified external identity
  API->>Authorization: PREP review.claim with exact request bindings
  Authorization-->>API: Opaque single-use prepared handle
  API->>DB: Lock idempotency, lifecycle fence, queue, Task, Assignment, Submission, and CheckerRun; recompose canonical final facts
  API->>Authorization: Consume prepared handle and evaluate final facts
  Authorization-->>API: Allowed; authorization evidence staged
  API->>DB: Freeze reviewer policy; create ReviewLease and ReviewPacketManifest; commit once
  API-->>UI: Exact leased Review Context

  Reviewer->>UI: Submit accept, needs_revision, or reject
  UI->>API: POST decision with immutable findings/resolutions
  API->>Auth: Freshly verify Flow token
  Auth-->>API: Verified external identity
  API->>Authorization: PREP review.decision with exact request bindings
  Authorization-->>API: Opaque single-use prepared handle
  API->>DB: Lock idempotency, lifecycle fence, queue, lease, Task, Assignment, Submission, predecessor, and evidence; recompose canonical final facts
  API->>Authorization: Consume prepared handle and evaluate final facts
  Authorization-->>API: Allowed; authorization evidence staged
  API->>DB: Append Review/findings/resolutions; consume lease; close queue
  API->>DB: CON reviewer completed_review and applicable award

  alt needs_revision
    API->>DB: Set needs_revision and keep assignment active
  else accept
    API->>DB: Append FinalAcceptance; accept task; complete assignment
    API->>DB: CON submitter accepted_submission from FinalAcceptance
    API->>DB: Create applicable submitter CompensationAward
  else reject
    API->>DB: Block assignment and reject task
    API->>DB: No FinalAcceptance or submitter contribution
  end
  API->>DB: Stage shared audit/outbox and commit once; no ART call

  opt needs_revision after decision commit
    API->>DB: In a later authorized transaction, append frozen RevisionContextPreparation
    Contributor->>UI: Submit one response per unresolved blocking finding
    UI->>API: Create replacement Submission bound to preparation head
    API->>Checks: Run checks again
  end
```

## Lifecycle Invariants

- New TaskAssignments and ReviewLeases require an active published
  `ContributionPolicyVersion` to freeze.
- A contributor submission creates a new immutable submission version; locked artifacts are not edited in place.
- Review decisions are exactly `accept`, `needs_revision`, or `reject`.
- `needs_revision` commits the immutable Review and task effect first. Before
  contributor access, Workstream appends frozen preparation and later requires
  immutable responses and resolutions for prior blocking findings.
- Every valid human Review creates a reviewer contribution. Accept additionally
  creates FinalAcceptance, which alone sources the submitter contribution.
- Compensation fulfillment status is separate from task acceptance.
