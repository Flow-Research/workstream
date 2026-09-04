# Chunk Contract: WS-XINT-003-03C — Release And Preference Decline Activation

## Status and risk

Non-implementable planning skeleton after 03B. Refresh from current `main`.
L1 reviewer mutation authority.

## Goal

Activate only `review.release` and `review.decline_preference` against merged
REV-06B behavior. Every timer, packet/context, and decision action remains
unavailable.

## Boundaries and acceptance

AUTH may connect only the exact 02D contracts to merged REV-06B composers and
change the two named availability rows. It may add no catalogue value,
principal, context class, protocol, REV lifecycle behavior, or route. Owning
reviewer/active-lease and offered-reviewer/preference scope, revocation,
staleness, replay, cross-resource denial, idempotency, and atomic evidence must
pass integrated proof.

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
test delta, reuse/dedup, and docs.

## Stop

Merge and stop before timer activation.
