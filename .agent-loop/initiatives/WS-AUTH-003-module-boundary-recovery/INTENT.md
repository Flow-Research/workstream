# WS-AUTH-003: AUTH Module Boundary Recovery

## Human goal

Restore AUTH as a real modular-monolith boundary. Code outside AUTH may consume
only AUTH's explicit public interface. AUTH may not import feature models,
repositories, services, routers, or other private product implementation.
The resulting in-process interface must be replaceable by an HTTP or gRPC
adapter without rewriting ART, REV, CON, project, task, or checker business
logic.

## Why this exists

The repository already states this rule, but implementation accumulated direct
cross-module imports. Large layer-oriented files and tests then hid the missing
capability boundaries. The correction must precede further AUTH/POL feature
growth.

## Success state

- `app.modules.authorization.api` is AUTH's sole cross-module import surface.
- AUTH imports no product-module internals.
- Cross-module values are typed identifiers and immutable facts, never ORM
  objects or repositories.
- The composition root alone wires concrete cross-module implementations.
- AUTH internals are organized by API, domain, services, persistence, and
  transport responsibilities.
- Static enforcement immediately rejects new violations; incremental feature
  work shrinks the frozen debt ledger to zero.
- Existing authorization, locking, replay, revocation, evidence, concealment,
  and transaction behavior remains unchanged.
- AUTH tests are organized by behavior and retain assertion/coverage parity.
- New and changed tests prove one primary behavior; existing oversized/mixed
  tests are frozen and decomposed capability by capability without weakening
  proof.

## Non-goals

- No new permission, action, role, service identity, endpoint, or lifecycle.
- No product migration or schema change.
- No HTTP/gRPC deployment in this initiative; only an extractable boundary.
- No ART, REV, CON, project, task, or checker product redesign.
- No compatibility aliases in the completed architecture.

## Human decisions already made

- Do not rewrite all AUTH in one PR.
- Merge one small boundary-foundation PR, then repair capabilities alongside
  the product chunks that exercise them.
- Resume preserved POL-03A after the foundation merges and use it as the first
  capability-level boundary repair.
- Never permit the frozen violation count to increase.
- REV `allow_reviews` begins only through clean AUTH and ART public interfaces.
