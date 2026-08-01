# Chunk Contract: WS-XINT-003-05 — Bounded Review Chain Read Activation

## Status and risk

Non-implementable planning skeleton after 04 and merged XINT-002-07A. Refresh
exact files and commands on current main before an explicit user request. L1
confidential history access.

## Goal

Activate only `review.chain.read` for the exact active lease. Evidence and ART
binding actions remain owned by XINT-002-07A/07B.

## Allowed files

Enumerate exact REV chain-read service/repository, AUTH context/activation
parity, route, tests, docs, and evidence at current-main start.

## Not allowed

Generic artifact or historical-byte authority, evidence mutation, decision,
Submission creation, recovery, or unbounded reviewer backlog/history.

## Acceptance criteria

- Chain reads require the exact active lease/reviewer and disclose only bounded
  relationship metadata for the leased task/Submission chain.
- Historical artifact bytes remain inaccessible unless independently present
  in the current exact packet manifest.
- Expired/released/reassigned leases, revocation, cross-project/task/submission,
  stale packet/version, wrong action, and replayed disclosure deny or conceal.

## Verification and reviewers

PostgreSQL read/race tests, concealment/redaction matrix, immutability, coverage
and hosted gates; full L1 reviewer set.

## Stop

Merge and stop before decision activation.
