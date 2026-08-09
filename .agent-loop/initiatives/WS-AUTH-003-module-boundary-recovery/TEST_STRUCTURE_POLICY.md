# Incremental Test-Structure Recovery

## Primary rule

Every test proves one primary observable behavior. Its name, setup, operation,
and assertions must make the broken behavior identifiable from the first useful
failure. Passing a line-count gate does not make a mixed-behavior test valid.

Tests are organized around public/domain behavior and security invariants, not
one test for every private implementation function. Private helpers receive
direct tests only when they own an independently meaningful contract.

## Required shape

Each new or materially changed test has:

1. one named primary invariant;
2. setup that constructs state but does not perform the behavior under test;
3. one primary act boundary or one explicitly named concurrency race;
4. assertions about that invariant and its required absence of side effects;
5. no unrelated lifecycle, authorization, storage, or audit assertions.

Security tests may assert a coupled atomic outcome as one behavior. For
example, “denial produces neither protected mutation nor allowed evidence” is
one fail-closed invariant, not three unrelated tests.

## Test layers

```text
domain       pure rules, facts, decisions, state transitions
service      one application use case and its port interactions
persistence  PostgreSQL constraints, locking, idempotency, immutability
integration  public module ports and transaction ownership
end_to_end   a small number of complete wiring journeys
```

End-to-end tests prove wiring and one primary journey. They do not become the
only proof for every rule crossed by that journey.

## Structural guardrails

For new or materially changed AUTH recovery code, and for files explicitly
owned by a later AUTH-boundary capability chunk:

- test function target: 75 lines; hard maximum: 120 lines;
- test fixture/helper target: 60 lines; hard maximum: 100 lines;
- production function target: 60 lines; hard maximum: 100 lines;
- test file target: 800 lines; hard maximum: 1,200 lines;
- production file target: 800 lines; hard maximum: 1,200 lines.

These are review triggers and hard growth limits, not a substitute for
cohesion. A 30-line test that proves several unrelated behaviors is rejected.

A hard-limit exception requires an exact symbol/path, capability, technical
reason, primary invariant, reviewer approval, and removal chunk. “End to end,”
“security critical,” or “existing pattern” is not sufficient justification.

## Existing debt

Existing oversized AUTH files and functions enter the machine-readable frozen
debt ledger `TEST_STRUCTURE_DEBT.json`. Each entry records its kind, repository
path, qualified symbol when applicable, exact line span, content hash, observed
line count, hard limit, owning capability, and removal chunk. The foundation
records that baseline without rewriting it. The validator fails when the ledger
is absent, malformed, stale, or omits an observed baseline violation.

- New debt is rejected.
- A touched debt item may not grow.
- A feature chunk touching its behavior extracts at least the relevant primary
  invariant into the correct test layer and shrinks or removes the item.
- Tests are never deleted, skipped, xfailed, or weakened merely to reduce size.
- Old-to-new assertion mapping is required whenever a test is decomposed.

Each capability repair stores its machine-readable mapping at
`assertion-maps/<chunk-id>.json`. Every mapping entry records the old test node
ID, old assertion or invariant ID, source span and content hash, invariant
category, new/final test node ID, target test layer, and applicability for
concurrency, lock order, denial side effects, replay, revocation, evidence,
transaction ownership, and concealment. A `not_applicable` value requires a
specific reason. The validator checks that every frozen old assertion/invariant
has exactly one preserved disposition and that every referenced old and new
node exists; semantic reviewers confirm behavioral equivalence.

## Capability repair proof

Before changing one AUTH capability, its chunk records:

| Primary invariant | Layer | Existing test | New/final test |
|---|---|---|---|
| exact behavior | domain/service/persistence/integration/end_to_end | node id | node id |

The table covers decisions, denial side effects, lock order, replay, revocation,
evidence, transaction ownership, and concealment when relevant. It is
capability-specific rather than a repository-wide ceremonial checklist.

## Enforcement split

Static validation enforces measurable facts: function/file size, growth,
debt-ledger parity, exception schema, and assertion-map completeness. It rejects
new uses of `pytest.mark.skip`, `skipif`, `xfail`, module-level `pytestmark`,
parameter marks, `pytest.skip`, `pytest.importorskip`, and `unittest.skip*`;
these proof-weakening mechanisms do not receive a size-debt exception.
Architecture, QA, security, and test-delta review enforce behavioral parity and
the semantic rule that one test proves one primary behavior.

This is an AUTH boundary-recovery policy, not a repository-wide convention.
The final state is an empty import-debt ledger and an empty AUTH structural-debt
ledger, reached incrementally while product work continues.
