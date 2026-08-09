# Chunk Contract: WS-AUTH-003-01 Boundary Foundation

## Goal

Install the minimal public AUTH namespace, a default-deny import gate, and a
no-new-AUTH-test-structure-debt gate without moving product behavior.

## Risk

L1 architecture/CI; runtime authorization behavior is intentionally unchanged.

## Allowed files

```text
backend/app/modules/authorization/api/__init__.py
backend/app/modules/authorization/api/action_ids.py
backend/app/modules/authorization/api/decisions.py
backend/app/modules/authorization/api/errors.py
backend/app/modules/authorization/api/facts.py
backend/app/modules/authorization/api/ports.py
backend/scripts/authorization_boundary.py
backend/scripts/test_structure_boundary.py
backend/scripts/behavior_ownership.py       # additive foundation transition only
backend/tests/architecture/test_authorization_boundary.py
backend/tests/architecture/test_test_structure_boundary.py
backend/tests/test_behavior_ownership.py    # additive transition proof only
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/assertion-maps/**
.github/workflows/**                     # invoke the new validator only
.ci/behavior-ownership/**                # exact ownership for new files only
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/**
docs/spec_authorization_service.md
```

## Not allowed

- Moving or changing AUTH runtime behavior.
- Migrating existing consumers in this foundation chunk.
- Models, repositories, database queries, migrations, routes, permissions,
  actions, roles, service identities, or lifecycle changes.
- Re-exporting AUTH-private runtime modules through the public API.
- Weakening behavior ownership, tests, coverage, Ruff, or CI.
- Increasing the recorded private-import count.
- Reorganizing or weakening existing AUTH tests; this chunk records structural
  debt and prevents new growth only.

## Acceptance criteria

1. `IMPORT_LEDGER.md` exactly records both current violation sets: non-AUTH
   imports of AUTH internals and AUTH imports of other modules' internals.
2. The validator parses Python imports without importing application code.
3. Any new consumer import of private AUTH, any new AUTH import of a product
   model/repository/service/router/schema/persistence implementation, any
   wildcard import, or dynamic import through `__import__`,
   `importlib.import_module`, or an aliased form fails closed. The foundation
   supports no dynamic-import allowlist: unknown/computed import forms,
   malformed ledger data, unresolved relative imports, or either exact
   edge-set/count increase also fail. Relative imports are canonicalized before
   edge comparison and cannot bypass either dependency direction.
4. Existing recorded inbound and outbound violations remain visible and
   unchanged; the foundation neither hides nor migrates them.
5. `authorization.api` imports in a clean process and exposes only bounded
   public contracts needed to begin incremental migration.
6. Public API reachability contains no ORM models, SQLAlchemy session,
   repository, concrete service, router, kernel, private capability registry,
   or product implementation.
7. CI runs both the import-boundary and test-structure validators for their
   applicable backend changes.
8. No runtime authorization or product test assertion changes.
9. Behavior ownership and architecture tests recognize the exact new files.
   Architecture fixtures prove wildcard, direct and aliased `__import__`,
   direct and aliased `importlib.import_module`, and computed module-name
   bypasses are rejected. They also prove inbound and outbound relative imports
    resolve to the same canonical edge and unresolved relative forms fail closed.
    The behavior-ownership partition may transition from trusted `origin/main`
    only by adding the exact eligible files approved by this foundation. Every
    trusted assignment, schema value, protected base, deterministic group, and
    full-authority digest remains unchanged or exactly recomputed as applicable.
    Removal, reassignment, reorder-based concealment, duplication, untracked or
    ineligible additions, unavailable/malformed trusted state, or any extra
    unresolved eligible target fails closed. No catalogue, eligibility,
    grouping, remap, or owned-test semantics change.
10. Required architecture, security, QA, CI-integrity, and test-delta reviews
    pass before the PR is ready.
11. `TEST_STRUCTURE_DEBT.json` records existing oversized AUTH test
    files/functions and production functions without changing them, including
    kind, path, qualified symbol where applicable, exact span, content hash,
    observed size, hard limit, capability owner, and removal chunk.
12. The test-structure validator rejects new hard-limit violations, growth of
    existing debt, all new pytest/unittest skip and xfail mechanisms, malformed
    exceptions, and incomplete assertion mappings. It also rejects an absent,
    malformed, stale, or incomplete debt ledger. Assertion mappings record old
    test and assertion IDs, exact ancestor revision and source span/hash,
    category, new node and layer, and reasoned applicability for concurrency
    and security dimensions. The validator derives all old assertion spans from
    the trusted old test and rejects fake nodes, mismatched bytes, duplicates,
    or omitted dispositions.
13. Static limits are never claimed as proof of cohesion. Architecture, QA,
    security, and test-delta review enforce the semantic rule that every new or
    materially changed test proves one primary behavior.

## Exact verification

Run from `backend/`:

```text
uv run ruff check app/modules/authorization/api scripts/authorization_boundary.py scripts/test_structure_boundary.py tests/architecture/test_authorization_boundary.py tests/architecture/test_test_structure_boundary.py
uv run python -m scripts.authorization_boundary validate --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
uv run python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
uv run pytest -q tests/architecture/test_authorization_boundary.py tests/architecture/test_test_structure_boundary.py
uv run pytest -q tests/test_behavior_ownership.py
uv run python -m scripts.behavior_ownership validate
```

GitHub binds the exact checked-out head and runs both validators, behavior
ownership validation, and the two exact architecture test files once in an
unconditional preflight job. Existing backend lanes depend on that preflight
and otherwise retain their full tests and coverage unchanged. There are no
workflow path filters, skip flags, `continue-on-error`, or fallback success
paths. Full coverage is not run locally.

## Required reviewers

- architecture
- security
- QA
- CI integrity
- test delta

## Human review focus

- Does the gate freeze both dependency directions and reject all new violations?
- Is the public API genuinely bounded rather than an internal re-export layer?
- Can POL-03A now expose one exact capability without weakening the rule?
- Does test enforcement preserve one-primary-behavior semantics rather than
  reward cosmetic line splitting?
