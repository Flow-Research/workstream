# WS-XINT-002-03 PR Trust Bundle

## Chunk

`WS-XINT-002-03` — Internal Service Activation (L1).

## Goal and intent

Activate the minimum fixed ART service authority needed for verification,
pending-work scanning, and put-attempt resolution while preserving PREP's
transaction binding, single-use consumption, and deny-by-default behavior.

## What changed

- Activated exactly `artifact.verification.execute`,
  `artifact.pending_work.scan`, and `artifact.put_attempt.resolve`.
- Added closed typed ART contexts and a prepared-authority adapter that binds
  action, service profile/link, exact resource, fence facts, request digest,
  transaction, and idempotency scope.
- Required claim authorization and commit before provider I/O, followed by a
  fresh terminal authorization consumed atomically with evidence and state.
- Bound scanner authority to the exact cutoff, kind, page size, and final ID
  page, publishing only after commit.
- Made direct fixed-service `require` calls deny; only valid prepared
  consumption can allow these actions.
- Persisted the canonical resource-context digest in decision evidence and
  extended existing audit-fact constraints to admit only its strict form.
- Routed Celery tasks through one composition adapter and added one scanner
  schedule.

## Security and failure properties

Copied, replayed, cross-action, cross-resource, stale-fence, replaced-
transaction, revoked, suspended, or post-I/O stale handles deny. Failed claim,
terminal, scanner, evidence, or state mutations roll back and can be retried
without reusing consumed authority. Human and Operator authority is not
expanded; all other ART service actions remain planned and issue no handle.

## Evidence

- Migrated PostgreSQL internal-authorization suite: 9 passed.
- Focused authorization, artifact architecture, recovery, and verification
  evidence passed, including relationship conflict and scanner rollback.
- Migration clean upgrade/downgrade passed; downgrade refuses forward evidence.
- Ruff, stale scans, markdown links, lightweight gates, lane inventory, and
  diff checks passed.
- Required internal reviewers passed; reuse/dedup recorded only low residual
  risk.
- GitHub Actions will run the full repository suite and coverage at the exact PR
  head; no local four-hour full run is required.

## Human review focus

Confirm the three-action activation boundary, claim/provider/terminal ordering,
exact scanner page binding, public clean-denial restaging, and strict audit
digest persistence. The user retains merge approval for this specific PR.

## Next gate

`WS-XINT-002-04` is only the declared same-initiative successor. It does not
start automatically and requires a fresh explicit trusted-main event.
