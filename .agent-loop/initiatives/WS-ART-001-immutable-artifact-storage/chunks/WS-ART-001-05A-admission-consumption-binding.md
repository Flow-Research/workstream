# Chunk Contract: WS-ART-001-05A — Admission Consumption And Submission Binding

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Superseded as an executable
contract by WS-ARCH-001-02; requires split replacement contracts after
WS-ARCH-001-01 and XINT-05A reconciliation

## Goal

Preserve the intended atomic ready-admission-to-Submission outcome while
restoring module ownership: ART exposes ready-admission consumption and exact
binding capabilities; TASKS owns immutable Submission creation; AUTH owns
prepared authority; application composition owns transaction wiring.

## Allowed Files

No files are authorized by this superseded contract. WS-ARCH-001-02 must split
the work into exact AUTH, ART, TASK, composition, migration, test, and cutover
contracts before implementation.

## Not Allowed Changes

Legacy API transport cutover, checker execution, review decisions or notes,
contribution lifecycle, provider reads/writes, deletion, or AUTH activation.
ART must not import TASK private models/context/repositories or create a
Submission. TASKS must not import ART private models/repositories. Neither may
import AUTH outside `authorization.api`.

## Acceptance Criteria

- fresh human and fixed binding-service prepared authority is consumed in the
  same composition-owned transaction as the protected mutations;
- actor, identity, project, task, assignment, predecessor, locked context,
  content, manifest, and checker evidence match under locks;
- ART-owned `ready -> consumed`, TASK-owned Submission creation, and ART-owned
  binding commit once through transaction-bound public ports;
- mismatch proven during consumption makes the admission stale where specified;
- concurrent attempts create one business effect and exact replay is stable;
- denial or persistence failure rolls back every effect.

## Verification Commands

Focused transaction, concurrency, replay, stale-context, authorization, model,
migration, coverage, and hosted Backend/Agent Gates.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Review module ownership, the atomic boundary, and immutable lineage. This file
is planning evidence only and must not start implementation.
