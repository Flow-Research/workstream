# Chunk Contract: WS-REV-001-03P - Review And Revision Policy Persistence

## Status

Proposed only. It may start only through a signed `Loop Memory Explicit Event`
on exact current main after PLAN3 merges and this contract is refreshed/reviewed.

## Goal

Persist only REV-owned immutable ReviewPolicy and RevisionPolicy facts needed by
later routing, lease, decision, and human revision behavior.

## Risk

L1: policy immutability, duration/limit semantics, and later decision authority.

## Allowed files

To be fixed at signed start: REV-owned policy models, migration, schemas,
focused tests, and this initiative's evidence/merge-intent files only.

## Not allowed

- Task or TaskAssignment states/transitions.
- Project Guide, Submission, Checker, AUTH, ART, or CON owner implementation.
- Queue admission, leases, Reviews, decisions, revision execution,
  FinalAcceptance, routes, adjudication, reputation, or frontend work.

## Acceptance criteria

- ReviewPolicy and RevisionPolicy are immutable, versioned, and attributable to
  the exact upstream context they govern without mutating that context.
- Review preference/lease duration and human revision limits/deadlines have
  explicit typed semantics and are never inferred from unrelated SLA fields.
- Missing upstream Task/Assignment compatibility is reported to its owner and
  cannot be repaired in this chunk.
- No review lifecycle transition is activated.

## Verification

Fix exact commands at start: focused model/migration tests, PostgreSQL
immutability/refusal proof, downgrade/re-upgrade proof, agent gates, and full
coverage through GitHub Actions.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, test-delta, and CI integrity.

## Stop

Do not implement without a signed start on exact current main.
