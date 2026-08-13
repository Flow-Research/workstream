# Chunk Contract: WS-ARCH-001-03C AUTH Task Readiness Activation

Status: non-executable planning skeleton after reviewed 03A/03B manifests.
Risk: L1. Outcome: the exact
AUTH-13 task/claim/assignment actions become usable only through the owner
public APIs and one integrated readiness proof.

Allowed: AUTH public API/catalogue/evaluator/PREP composition, delivery-root
wiring, focused AUTH/TASK integration tests, boundary/debt ledgers and
initiative evidence/status. Not allowed: TASK lifecycle ownership, private
PROJECT/TASK imports, ART/checker/review activation, generic task permission,
role-only fallback or public Submission cutover.

Acceptance: actor, identity link, project grant, task, assignment, contributor,
approved generation, transaction and idempotency are exact; replay,
revocation, stale context and concurrency fail closed with atomic evidence.
Assignment activation also requires the CON-owned freeze result and the exact
`TaskAssignment.submitter_contribution_policy_version_id`; AUTH never selects
or evaluates ContributionPolicy and cannot authorize assignment creation when
the CON participant refuses or the frozen version facts differ.
Verify focused tests, PostgreSQL races, catalogue/database parity, boundary
validators, Ruff and hosted coverage. Required reviews: authorization
architecture, security, product/ops, QA, senior, CI and test delta.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
