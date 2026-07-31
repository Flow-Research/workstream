# Chunk Contract: WS-XINT-003-03B — Lease Timer Services

## Status and risk

Non-implementable planning skeleton after 03A. Refresh exact files and commands
on current main before an explicit user request. L1 fixed-service authority.

## Goal

Activate only `review.preference_expiry.run` and `review.lease_expiry.run`.
Both `review.reconcile.run` identities remain planned until 08B.

## Allowed files

Enumerate exact REV timer commands, worker registration, AUTH
service identity/matrix/context parity, migration, tests, docs, and evidence at
current-main start.

## Not allowed

Generic scheduler identity, serialized prepared handles, human authority in job
payloads, decision/revision behavior, or manual Operator execution of workers.

## Acceptance criteria

- Each command runs only as its separately admitted fixed service identity with
  exact action membership and canonical row scope.
- Payloads contain identifiers/provenance only; workers prepare fresh authority
  and re-read current state inside a new transaction.
- Expiry versus claim/release/decision races have deterministic
  lock order and exactly one valid terminal effect.
- Retry is idempotent and cross-service/action/lease/project requests deny.
- All-pairs identity denial and Celery registration/payload scans pass.

## Verification and reviewers

Focused worker/PostgreSQL race/matrix tests, Ruff, coverage and hosted gates;
architecture, security, product/ops, QA, senior, CI, reuse, docs, test-delta.

## Stop

Merge and stop before packet/context reads.
