# Plan: WS-ARCH-001 Modular Monolith Boundaries

## Strategy

Use one incremental dependency strangler:

```text
canonical module map
-> exact repository-wide private-edge inventory
-> no-new-edge enforcement
-> expose one real capability through the owner's api package
-> migrate exact consumers and composition wiring
-> remove those ledger edges
-> repeat with product delivery until the ledger is empty
```

## Permanent rules

1. A module owns its facts, mutations, invariants, persistence, and errors.
2. Cross-module runtime imports target only `app.modules.<module>.api`.
3. Public APIs contain immutable facts, commands/results, stable errors,
   opaque capability Protocols, and ports—not implementation.
4. The caller supplies server-owned canonical facts; it never receives the
   target's ORM model or repository.
5. Concrete implementations meet only in the application composition root.
6. The application composition root opens the SQLAlchemy transaction/unit of
   work and constructs transaction-bound public-port implementations. The
   owning application command coordinates those injected ports without
   receiving another module's repository, ORM model, concrete service, or raw
   database session through a public API. Coordination does not transfer
   domain ownership.
7. Existing private edges may remain only while frozen. A changed capability
   must remove its relevant edges and may add none.
8. Tests import another module through its public API except package-local
   white-box tests owned by that module.

## Delivery integration

Boundary repair is not a separate rewrite lane after the foundation. Every
feature contract touching `artifacts`, `authorization`, `projects`, `tasks`,
`checkers`, `reviews`, `contributions`, or `compensation` must state:

- owning module for every new fact and mutation;
- public API additions and exact consumers;
- concrete composition-root wiring;
- protected-base debt edges removed;
- proof that debt does not grow;
- behavior, transaction, authorization, replay, and denial preservation.

## ART/TASK correction

Before ART-05A implementation:

- XINT-05A exposes the exact public AUTH preparation capability;
- ART exposes ready-admission validation/consumption and binding ports;
- TASKS exposes the immutable Submission command and predecessor/context facts;
- the composition root owns the transaction/unit-of-work boundary and invokes
  the TASK-owned application command with transaction-bound AUTH and ART
  public ports;
- ART does not create or query TASK ORM rows;
- TASKS does not query ART ORM rows;
- POL-03A now owns merged migration `0062_guide_compilation`; every later
  migration identifier is chosen only after rebasing on then-current `main`.

## Verification

- AST import-edge inventory and protected-base comparison.
- Public API dependency/leak/reachability tests.
- AUTH edges remain exclusively recorded by WS-AUTH-003. The general validator
  loads the canonical AUTH ledger through the existing AUTH boundary parser
  and combines its result by reference; it does not copy AUTH edges into a
  second ledger. Tests prove missing, additional, or divergent AUTH/general
  results fail closed.
- Behavior-ownership and test-structure validators remain green.
- Capability-focused unit and PostgreSQL concurrency tests.
- Ruff, stale wording, Markdown links, repository coverage, and hosted lanes.
- Architecture, security, QA, product/ops, senior, reuse, test-delta, CI, and
  docs review for L1 boundary chunks.

## Rejected alternatives

- One repository-wide package move: unreviewable and behaviorally unsafe.
- Let each module invent its own facade: creates inconsistent protocols.
- Put orchestration in ART or AUTH: transfers lifecycle ownership.
- Create a generic shared domain/service locator: hides coupling.
- Preserve the debt ledger permanently: normalizes the architecture failure.
