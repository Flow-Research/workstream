# Plan: WS-QUAL-001 Current-Main Coverage Closure

## Approach

Retire the old milestone ladder and close the remaining gap with at most two
bounded test chunks followed by one floor switch:

1. Add fast project/setup behavior tests for observable service, repository,
   routing, queue, and replay gaps.
2. If still needed, add fast checker behavior tests for observable service,
   repository, runner, compiler, and routing gaps.
3. On current `main`, prove at least 90.25 percent globally and change only the
   canonical GitHub global floor from 78 to 90.

Each test chunk starts by reading the current hosted coverage JSON and selecting
behavioral gaps. It prefers pure functions, typed fakes, direct use-case calls,
and adapter contracts. PostgreSQL, MinIO, or HTTP is used only when that
boundary is itself the assertion.

## Coverage target

The last necessary test chunk must reach at least 90.25 percent before the CI
switch. This is operational headroom, not a permanent higher policy floor. If
concurrent main growth moves the measured result below 90.25 percent, the floor chunk stops
and returns to a small test chunk; it never lowers or rounds around the target.

## Test-quality rule

Every new test must name and assert one observable contract such as returned
data, persisted state, emitted audit/outbox fact, queue decision, mapped error,
authorization denial, idempotent replay, or recovery outcome. A test whose only
effect is executing previously missed lines is invalid.

No chunk may introduce skips, xfails, coverage pragmas, omit/include narrowing,
deleted assertions, broad mocking of the behavior under test, or duplicated
database/HTTP coverage already owned by another layer.

## Boundaries

- QUAL changes tests and, only in the final chunk, the global CI threshold and
  its lightweight invariant test.
- A production defect discovered by a stronger test is reported and fixed in a
  separate owning initiative/chunk.
- Production service decomposition, repository ports, UnitOfWork design, type
  checking, mutation testing, and property-test architecture require separate
  initiatives. They are not hidden inside coverage closure.
- CI runtime optimization remains WS-CI-owned. QUAL records test-time impact and
  must avoid obvious regressions but does not redesign lane infrastructure.

## Alternatives rejected

- Reviving `01B2` and the complex base-evidence ratchet: unnecessary now that
  exact lane custody and hosted coverage evidence exist.
- One large cross-owner coverage PR: crosses project, checker, task, artifact, and
  authorization ownership and is difficult to review.
- Raising the floor immediately: current measured coverage is below 90.
- Excluding low-coverage services or files: makes the global percentage false.
- More arbitrary shards: changes runtime distribution, not test architecture or
  coverage quality.

## Verification strategy

Every implementation chunk runs focused tests, Ruff for changed tests, complete
test-delta review, relevant stale-contract checks, and hosted Backend. The final
floor chunk additionally proves the combined coverage JSON covers the complete
application inventory at or above 90.25 percent and that every protected
90-percent check remains blocking.

## Dependency order

PLAN2 -> 02R -> optional 03R -> 04R. If those exact owner-scoped chunks do not
provide enough headroom, stop and plan one additional owner-specific test chunk
from the refreshed report. Do not create a percentage-driven residual bucket.
The CI floor change always remains a separate final PR.
