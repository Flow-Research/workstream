# Chunk Contract: WS-ART-001-05A — Admission Consumption And Submission Binding

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after XINT-05A

## Goal

Atomically consume one compatible `ready` admission, create the immutable
Submission, and bind it to the exact verified artifact and semantic manifest.

## Allowed Files

Submission/admission/binding models and migration, transactional service and
repository seams, canonical resource facts, focused tests/docs/CI evidence.

## Not Allowed Changes

Legacy API transport cutover, checker execution, review decisions or notes,
contribution lifecycle, provider reads/writes, deletion, or AUTH activation.

## Acceptance Criteria

- fresh human and fixed binding-service prepared authority is consumed in the
  same transaction as the protected mutation;
- actor, identity, project, task, assignment, predecessor, locked context,
  content, manifest, and checker evidence match under locks;
- `ready -> consumed`, Submission creation, and binding commit once;
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

Review the atomic boundary and immutable lineage. Stop before transport cutover.
