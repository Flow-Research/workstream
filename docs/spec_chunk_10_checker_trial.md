# Chunk 10 Checker Trial

## Purpose

Chunk 10 proves the Week 2 checker framework against real sample submission flows.

This chunk does not add a new lifecycle state or review decision. It exercises the existing API contracts from project guide activation through task submission, lock, automatic checker run, task routing, worker-visible feedback, and trusted checker retry from an internal blocked gate.

## Scope

- sample submissions that pass and fail through the backend API
- failure catalog for checker outcomes
- false-positive notes
- missing-checker notes
- trusted checker retry documentation for internal blocked gate repair
- tests that prove trusted internal and worker-visible checker output boundaries

## Non-Scope

- product frontend implementation
- human review decision records
- revision replay enforcement
- contribution records
- payment records
- reputation records
- external checker worker infrastructure
- new checker names unless the trial proves a missing checker is required

## Trial Matrix

The trial must include at least five sample submissions:

| Scenario | Expected Routing | Expected Task Status | Worker Visible |
| --- | --- | --- | --- |
| Clean packet | `allow_review` | `review_pending` | Passing checker context |
| Missing required file | `needs_revision` | `needs_revision` | Required-file fix message |
| Forbidden file path | `needs_revision` | `needs_revision` | Safe forbidden-file fix message |
| Weak confidentiality attestation | `needs_revision` | `needs_revision` | Attestation fix message |
| Locked task setup defect | `task_setup_blocked` | `auto_checking` | Internal route hidden |

The worker-facing output must keep the same public language as the rest of Workstream. Worker-fixable checker failures are `needs_revision`. Internal setup defects stay hidden from workers and are repaired by a project manager before a trusted checker retry.

The locked task setup defect must also prove trusted repair:

```text
task_setup_blocked
-> project manager repairs task setup
-> trusted checker retry
-> allow_review
-> review_pending
```

## Conditions Of Satisfaction

- at least one clean submission reaches `review_pending`
- at least one worker-fixable submission failure reaches `needs_revision`
- locked task setup failures and worker-fixable failures use distinct routing recommendations
- worker-visible responses do not expose internal `task_setup_blocked` routing
- trusted checker retry from an internal blocked gate is covered
- false-positive notes are written down
- missing-checker notes are written down
- failure catalog links every trial scenario to the checker that produced the route

## Evidence

Trial evidence is stored in:

- [Checker Trial Failure Catalog](checker_trial_failure_catalog.md)
- backend API integration tests for the sample matrix

The trial test must use real backend API calls for project creation, guide activation, task screening/release, worker claim/start, submission creation, submission locking, checker run reads, and trusted checker retry. Direct database setup is allowed only to create the controlled locked task setup defect that normal lifecycle guards are designed to prevent.

## Verifier Agents

- senior engineering
- QA/test
- security/auth
- product/ops
