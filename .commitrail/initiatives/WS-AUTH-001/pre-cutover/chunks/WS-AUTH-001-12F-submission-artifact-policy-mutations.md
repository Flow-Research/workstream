# Chunk Contract: WS-AUTH-001-12F — Submission Policy Planning Parent

## Status

Split before runtime implementation after required L1 pre-start review failed
on 2026-08-05. This parent activates nothing and is not executable.

## Why the inherited contract was rejected

The inherited 12F contract combined four actions, a provenance migration,
human HTTP idempotency, external agent work, fixed-service custody, Celery
cutover, multi-row approval, effective/pre-submit compilation, and downstream
continuation without defining their transaction or replay boundaries. It also
omitted the dedicated prepared-mutation modules and Celery executor from scope.

Architecture, security, QA, and product/operations reviews all returned
`FAIL` before application code changed. Their blocking findings were:

- no dedicated flush-only mutation orchestrator/replay repository boundary;
- ambiguous human versus fixed-service derivation authority;
- no submission-policy-specific PREP binding/final matcher;
- no exact UUID idempotency/replay and rollback contract;
- no exact approval lock order or atomic provenance row set;
- ambiguous Project Manager manual authoring and 12G continuation semantics;
- placeholder rather than frozen verification commands; and
- missing Celery/internal-command files in the allowed scope.

## Approved product and authority decisions

- Workstream automatically derives the normal submission-artifact policy.
  `workstream.project.setup` is the only principal that calls the derivation
  agent and persists agent-derived policy output.
- The existing public inline derive endpoint is removed. A Project Manager may
  request or recover setup only through the existing governed setup dispatch;
  no human action invokes the agent inline.
- Project Managers may create and update a manual draft only as a governed
  exception with explicit manual provenance. They cannot edit an agent-derived
  draft in place or claim agent provenance.
- Approval remains Project Manager-only and atomically owns the exact draft,
  effective policy, and pre-submit compilation chain.
- 12F4 alone may atomically mark an existing post-submit policy superseded and
  record its exact upstream replacement identity when approval changes the
  effective/pre-submit lineage. That bounded invalidation is not derivation,
  compilation, correction, approval, or execution. 12F may otherwise only
  stage the setup continuation identity; 12G owns every new post-submit policy
  behavior.
- No backward-compatible role-based or public derive path survives.

## Executable children

1. `WS-AUTH-001-12F1` — typed PREP/replay/provenance foundation; zero action
   activation.
2. `WS-AUTH-001-12F2` — Project Manager manual draft create/update cutover.
3. `WS-AUTH-001-12F3` — fixed setup-service derivation and Celery cutover.
4. `WS-AUTH-001-12F4` — Project Manager approval and atomic effective/pre-submit
   chain cutover.

Children are sequential, L1, one PR each, and require explicit human start.
12G and 12B2 depend on merged 12F4, not this parent.

## Parent stop conditions

Stop if a child would reintroduce public inline derivation, allow a handle to
cross external work, mutate post-submit policy beyond 12F4's exact atomic
supersession/invalidation fields, reuse legacy role checks as authority, or
collapse manual and agent provenance.
