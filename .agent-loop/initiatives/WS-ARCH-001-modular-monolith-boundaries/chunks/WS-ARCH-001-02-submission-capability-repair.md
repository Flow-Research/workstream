# Chunk Contract: WS-ARCH-001-02 — Submission Capability Repair Coordination

Status: Split coordination record; non-executable. Risk: L1.

## Goal

Coordinate the exact owner capabilities needed for hidden submission
preparation and atomic ready-admission consumption while preserving module
ownership and reducing the touched private-import ledger.

## Required split before implementation

This coordination contract is split into executable 02A-02I contracts for
TASKS facts, PROJECTS locked-policy facts, CHECKERS plan/bounded-result facts, ART
preparation, AUTH preparation activation, ART consumption/binding, TASK
Submission composition, AUTH consumption activation, and the final live clean
cut.

No split may activate behavior whose required public capability is absent.

## Ownership

- AUTH owns authority facts, opaque handles, decisions and evidence.
- ART owns admission locks, compatibility/staleness, consumption and bindings.
- TASKS owns task/assignment/predecessor facts and immutable Submission.
- PROJECTS owns locked guide and project-policy lineage.
- CHECKERS owns effective pre-submit plan and bounded execution-result facts;
  ART owns durable evidence identity and persistence.
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
- Implementation under this parent record. Only 02A-02I authorize bounded work
  after their entry gates and human approval.

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
