# Chunk Contract: WS-AUTH-001-12B2 - Unified Setup Ledger Activation

Status: Proposed after complete WS-POL-003-04A2 and WS-AUTH-001-12J; inactive.
Risk: L1.

## Goal

Activate only `project.setup_run.update` and its fixed-service adapter for the
reviewed unified setup-service manifest. POL-04B, not AUTH, owns the live one-call
Celery call-graph cutover.

## Allowed files

AUTH catalogue/kernel/PREP/runtime, narrow setup-ledger authorization adapter,
focused authorization/POL integration tests, specifications, and AUTH memory.

## Not allowed

Fixed-service routing, agent orchestration, model calls, policy/compiler behavior,
human routes, generic setup authority, serialized handles, ART/checker/review/
contribution behavior, or compatibility paths.

## Acceptance

- Activate `project.setup_run.update` only for fixed
  `workstream.project.setup`; no human or unrelated service receives it.
- Bind exact project/guide/source, setup run/generation, compilation attempt,
  canonical input/result identity, deterministic task/correlation identity,
  expected step/transition, operation, request, session, and transaction.
- Product projections retain their separate 12E/12F/12G actions. Setup-ledger
  authority never authorizes a projection row or provider call.
- The complete POL-04A2 manifest proves the exact finalization transition, and
  complete AUTH-12J proves both preceding component projections have their
  purpose-specific fixed-service authority. POL-04B alone proves live
  setup-service reachability and removal of the legacy inference calls.
- No handle crosses Celery, commit, rollback, provider I/O, session, or
  transaction; stale/replay/cross-resource/cross-step uses deny.
- Concrete integration proves revoked current service authority denies replay
  and the production authority receipt's actor, link, action, resource, facts
  digest, session, and root transaction exactly match the POL-04A2
  finalization receipt. These are AUTH-12B2 obligations, not prerequisites for
  completing hidden POL-04A2 behavior.

## Verification and review

All-pairs service denial, PREP/transition binding, command manifest, POL-04A
hidden integration, hosted coverage, and all L1 tracks. Human
focus: ledger authority only; POL owns the cutover.

## Merge state

- Outcome on merge: `planned`
