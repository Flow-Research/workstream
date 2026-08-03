# Chunk Contract: WS-XINT-003-02D — AUTH PREP Integration Readiness

## Status

Proposed planning contract after 02C. Refresh exact files and verification
commands from current `main` before implementation.

## Parent initiative

`WS-XINT-003` — REV-AUTH End-to-End Contract.

## Goal

Publish one complete fail-closed PREP integration surface for every approved
REV action so REV can implement its lifecycle using stable AUTH contracts
without AUTH implementing or interpreting REV product state.

## Why this chunk exists

Registration alone does not tell REV how to bind canonical locked facts to an
opaque prepared capability. Deferring each interface until activation causes
per-chunk AUTH discovery. This chunk closes those interfaces once while every
lifecycle action remains unavailable.

## Risk class and SLA

L1 authorization protocol and cross-subsystem boundary. No expedited review
SLA.

## Allowed files

Refresh to exact current-main paths within:

```text
backend/app/modules/authorization/runtime.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/<bounded REV integration contract modules>
backend/tests/<bounded authorization and PREP tests>
docs/spec_authorization_service.md
docs/spec_review_lifecycle.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/**
```

## Not allowed changes

- No imports of REV repositories/models into AUTH evaluation or PREP custody.
- No REV lifecycle loaders, lock orchestration, queue/lease mutation, decision,
  revision behavior, routes, service jobs, or product persistence.
- No action activation, fixed-service execution, XINT-002 ownership change, or
  serialized prepared handle.
- No omnibus nullable resource context, generic dictionary/service locator,
  local REV policy engine, fallback authority, or role-only shortcut.

## Acceptance criteria

- A closed action-to-resource-contract manifest covers every approved v0.1
  human, Project Manager, Operator, and fixed-service action in
  `ACTION_CUSTODY.md`; future evidence-upload actions remain explicitly
  unavailable and unsupported for execution.
- Contracts use typed stable identifiers, enums, digests, bounded timestamps,
  reasons, modes, and lineage facts. They contain no ORM rows, bytes, extracted
  content, provider credentials, scratch paths, or executable callbacks.
- REV remains responsible for locking its canonical rows and composing the
  exact final context. AUTH validates identity/link/grant or fixed-service
  authority, action, request digest, session/root transaction, resource digest,
  staleness inputs, and single-use consumption.
- The existing opaque `PreparedAuthorizationHandle` remains the only durable-
  boundary protocol. It is process-local, non-serializable, action-bound,
  principal-bound, session-bound, transaction-bound, resource-bound, and
  single-use.
- Unavailable actions fail closed at prepare and consume. Publishing a contract
  does not grant runtime authority.
- Contract tests prove copied, reconstructed, serialized, replayed,
  wrong-session, wrong-transaction, wrong-action, wrong-principal,
  cross-project/resource, stale-digest, revoked, and unavailable denial.
- Static scans prove Celery payloads cannot carry handles and AUTH does not
  import REV product repositories or implement lifecycle rules.
- The interface includes enough exact fields for REV to implement every later
  action without requesting a new AUTH protocol or context family. Any omission
  returns to planning before merge.

## Verification commands

Refresh exact paths at implementation start, then include Ruff, focused PREP,
kernel, serialization, parity and denial tests, changed-subsystem coverage at
or above 90 percent, and hosted Backend coverage preserving the repository-wide
78 percent floor.

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
test delta, reuse/dedup, and docs.

## Human review focus

Confirm the surface is complete enough for REV to build against while AUTH
does not own lifecycle facts or make any lifecycle action executable.

## Stop conditions

Stop on any need for AUTH to load REV state, any missing catalogue/principal
from 02C, any new protocol, or any action becoming available. Merge this chunk
and stop. REV may then begin its lifecycle implementation; later XINT chunks
perform bounded integrated activation.
