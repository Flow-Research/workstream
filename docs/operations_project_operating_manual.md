# Project Operating Manual

## Purpose

This manual defines how a project runs inside Workstream. It is the practical bridge between a project guide and daily work.

Every project has:

- active guide
- queue owner
- reviewer owner
- guide source snapshot
- guide sufficiency report
- submission artifact policy
- effective project submission artifact policy hash
- generated project pre-submit checker policy
- post-submit checker policy
- review policy
- revision policy
- payment policy
- review guard
- lessons learned log

## Project Setup Checklist

Before releasing tasks:

- project name and slug exist
- project guide imported
- guide source snapshot captured
- project owner setup material captured
- latest project setup run visible to `admin` or `project_manager`
- payment policy base amount configured
- payment policy currency configured
- allowed task types listed
- task source, description, acceptance, and rejection fields listed
- guide sufficiency report passed or warnings acknowledged by `admin` or `project_manager`
- submission artifact policy derived by Workstream and approved by `admin` or `project_manager`
- effective project submission artifact policy hash persisted
- generated project pre-submit checker policy is created from the effective project submission artifact policy
- project pre-submit checker bundle hash persisted
- post-submit checker policy attached
- review policy attached
- revision policy attached
- payment policy attached
- reviewer pool assigned
- review guard created from the project guide
- guide version marked active
- each task locks the guide snapshot, effective project submission artifact policy hash, and pre-submit checker bundle hash before entering `READY`

The guide source snapshot freezes guide/source material only. While the guide is
still draft, an `admin` or `project_manager` may attach or update checker,
review, revision, and payment policy records after snapshot capture because
those records are activated as separate policy context.

Project setup operators inspect setup state through API reads, not direct
database queries. These endpoints require `admin` or `project_manager` access:

- `GET /api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy`

`ProjectSetupRun` is only a setup ledger. Policy truth remains in the guide
source snapshot, sufficiency report, submission artifact policy, effective
project policy, and compiled project pre-submit checker policy rows.

## v0.1 Quality Gates

### Project Activation Gate

A project cannot become active unless guide, immutable guide-source snapshot,
passed or acknowledged guide sufficiency report, approved submission artifact
policy, persisted effective project submission artifact policy hash, project
pre-submit checker bundle hash, post-submit checker policy, review policy,
revision policy, and payment policy are present. A task cannot enter `READY`
until it also locks the guide source snapshot id/hash, effective project
submission artifact policy hash, and project pre-submit checker bundle hash.

### Task Screening Gate

A task cannot move to `READY` until the task contract is complete, the guide version is locked, submission artifact requirements are clear, checker/review/revision/payment policy versions are locked, and a release decision is recorded.

After screening and release, workers use
`GET /api/v1/tasks/{task_id}/work-context` for the locked guide and lifecycle
context and `GET /api/v1/tasks/{task_id}/submission-requirements` for the exact
artifact, evidence, storage, packaging, hash, and attestation requirements.
Actors with the `admin` or `project_manager` role use
`GET /api/v1/tasks/{task_id}/locked-context` when support or a live API drill
needs full locked provenance without database inspection.

### Submission Quality Gate

A submission cannot move to human review until required checkers run against the exact submission version and artifact hashes. High-severity failures return to the worker when submission-caused; platform infrastructure failures remain in checker retry handling or audited admin/project manager intervention.

External origin qualification and webhook drop notifications are future adapter concerns, not v0.1 gates.

## Task Release Checklist

Before moving a task to `READY`:

- task belongs to project
- active guide version attached
- acceptance criteria exist
- required output is explicit
- submission artifact requirements are clear
- payment policy amount is set
- deadline or review SLA is set
- skill tags are set
- screening/readiness gate passed
- task status snapshot created
- task creator has run the project ready gate

## Ready Gate

A task cannot move to `READY` just because it has text.

The ready gate confirms:

- guide version is active
- task fits project scope
- acceptance criteria are objective enough to review
- submission artifact requirements are clear
- payout is set
- known project failure modes have been checked
- task does not depend on private or prohibited source material

If the ready gate fails, the task remains `DRAFT`.

## Submission Intake Checklist

Before accepting a submission packet:

- task is assigned to submitter
- summary exists
- output package or reference exists
- evidence exists
- revision replay exists when task was previously `NEEDS_REVISION`
- effective project submission artifact policy is loaded
- generated project pre-submit checker policy runs
- preflight failures return `PreSubmitCheckResponse(status="failed", eligible_to_submit=false, results=[...])`
- blocked submission-create attempts return `pre_submission_checker_failed` with structured pass/fail/warning details
- no submission row is created until blocking pre-submit checks pass

## Reviewer Simulation Gate

Before high-value or first-of-kind tasks are released, run a reviewer simulation:

- inspect task as if rejecting it
- identify likely blocker findings
- check whether acceptance criteria are atomic
- check whether evidence requirements are sufficient
- check whether the task can be reviewed without private explanation

The output is one of:

- ready
- needs revision before release
- reject-risk

## Review Checklist

Before review decision:

- read active guide version
- read task acceptance criteria
- inspect checker results
- inspect evidence
- inspect prior findings if resubmission
- write structured findings if not accepting

## Payment Checklist

Before marking paid:

- task is accepted
- payment record exists
- accepted amount is correct
- worker identity is correct
- payment reference is recorded
- paid amount matches record

## Lessons Learned Loop

Every repeated failure becomes one of:

- guide update
- checker update
- template update
- reviewer training note
- payment policy update
- revision policy update
- task creator checklist update

Do not let repeated mistakes remain tribal knowledge.

If a lesson changes acceptance, review, revision, payment, evidence, or checker expectations, it must become a guide, policy, template, or checker update before it is enforced. Chat and Slack messages can announce the change, but they are not the source of truth.

When a task already in `NEEDS_REVISION` is affected by a new guide or policy version, revision policy decides whether the next attempt is rebased. The worker must see the prior version, next version, and change summary before resubmitting.

Each lesson must have an action owner and one target:

- guide update
- checker update
- template update
- reviewer policy update
- revision policy update
- payment policy update
- project manager training note

## Weekly Project Review

Review:

- task counts by status
- accepted work
- rejected work
- needs-revision reasons
- checker failures
- reviewer quality
- pending payout
- paid total
- lessons learned

Output:

- policy changes
- checker backlog
- guide amendments
- revision policy amendments
- payment policy amendments
- project manager training notes
