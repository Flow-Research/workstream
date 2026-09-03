# Chunk Contract: WS-XINT-003-03D — Lease Timer Service Activation

## Status and risk

Non-implementable planning skeleton after 03C. Refresh from current `main`.
L1 fixed-service authority.

## Goal

Activate only `review.preference_expiry.run` and `review.lease_expiry.run`
against merged REV-06C commands and the exact 02C service identities.

## Boundaries and acceptance

AUTH may connect only the exact 02D contracts to merged REV-06C composers and
change the two named availability rows. It may add no catalogue value,
principal, context class, protocol, REV service-job/lifecycle behavior, or route.
Fresh in-process authority, identifier-only payloads, all-pairs service denial,
idempotency, claim/release/expiry races, and atomic evidence must pass. Expiry
versus decision is re-proved in 06 after canonical decision behavior exists.

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
test delta, reuse/dedup, and docs.

## Stop

Merge and stop before context/chain activation.
