# Decisions

## D1: One public AUTH import surface

Only `app.modules.authorization.api` is public across product modules.

## D2: Incremental recovery

One small foundation PR freezes debt. Each later feature chunk repairs only the
AUTH capability it touches and must shrink the ledger.

## D3: No deferred enforcement

We do not wait until REV to establish the rule. The no-new-violations gate
merges before AUTH/POL feature work resumes.

## D4: Facts cross boundaries

Typed identifiers and immutable canonical facts cross module boundaries. ORM
objects, repositories, sessions, and concrete services do not.

## D5: Capability-level extraction

Large AUTH files and tests are split as their capabilities are exercised, not
through one mechanical repository-wide move.

## D6: REV starts clean

REV `allow_reviews` receives no temporary private-import exception. Its AUTH
and ART ports must exist before its implementation begins.

## D7: POL-03A is the first proof

POL-03A remains preserved at `1a7242f2` until the foundation merges, then its
exact boundary is repaired before its implementation continues.

## D8: Tests prove one primary behavior

Line limits are guardrails, not the definition of quality. New/changed tests
must prove one primary invariant. Existing mixed/oversized proof is frozen and
decomposed only as its capability is touched, with assertion parity.
