# Chunk Contract: WS-ARCH-001-02 Submission Capability Repair

Status: Proposed after 01 and XINT-05A contract reconciliation. Risk: L1.

## Goal

Provide the exact AUTH, ART, and TASK public capabilities needed for hidden
submission preparation and atomic ready-admission consumption while preserving
module ownership and reducing the touched private-import ledger.

## Required split before implementation

This coordination contract must be split into reviewable PR contracts for:

1. AUTH public preparation capability and production activation;
2. ART ready-admission/binding public API and private-edge migration;
3. TASK immutable Submission command and composed atomic transaction;
4. live API cutover and legacy-path removal.

No split may activate behavior whose required public capability is absent.

## Ownership

- AUTH owns authority facts, opaque handles, decisions and evidence.
- ART owns admission locks, compatibility/staleness, consumption and bindings.
- TASKS owns task/assignment/predecessor facts and immutable Submission.
- The application composition root opens the SQLAlchemy transaction/unit of
  work and constructs transaction-bound AUTH, ART, and TASK public-port
  implementations. The TASK-owned application command coordinates those ports
  without receiving ART/AUTH repositories, ORM rows, concrete services, or a
  raw session through a public API. No domain orchestrator is introduced.

## Not allowed

- ART importing TASK models/context/repositories or creating Submission rows.
- TASKS importing ART models/repositories.
- Either module importing AUTH outside `authorization.api`.
- New ledger edges, compatibility facades, dual paths, or migration-number
  assumptions before rebase.

## Acceptance criteria

- Concurrent consumption creates one Submission and one binding.
- Preparation and final consumption use separate fresh authority decisions.
  Final authority is an opaque, non-persisted, non-serializable capability
  bound to the exact actor, identity link, assignment, task, project,
  predecessor, admission, locked context, request, operation, service action,
  session, and transaction facts.
- Final authority is revalidated and consumed inside the same transaction as
  Submission creation, ART binding, and `ready -> consumed` admission change.
  Token validity never substitutes for current actor/link/grant/assignment
  state.
- All authorization evidence and protected mutations commit atomically.
- Denial, stale context, wrong predecessor, replay, or service unavailability
  leaves no partial effect.
- Every touched private edge is removed and no edge is added.
- Existing ART/TASK/AUTH behavior and coverage gates remain green.

## Required reviewers

Architecture, security, QA, product/ops, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.
