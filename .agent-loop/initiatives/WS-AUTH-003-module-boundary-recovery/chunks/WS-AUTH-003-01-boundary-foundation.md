# Chunk Contract: WS-AUTH-003-01 Boundary Foundation

## Goal

Install the minimal public AUTH namespace and a default-deny import gate so no
new private cross-module dependency can be introduced.

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
backend/tests/architecture/test_authorization_boundary.py
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

## Acceptance criteria

1. `IMPORT_LEDGER.md` exactly records both current violation sets: non-AUTH
   imports of AUTH internals and AUTH imports of other modules' internals.
2. The validator parses Python imports without importing application code.
3. Any new consumer import of private AUTH, any new AUTH import of a product
   model/repository/service/router/schema/persistence implementation, any
   wildcard import, or dynamic import through `__import__`,
   `importlib.import_module`, or an aliased form fails closed. The foundation
   supports no dynamic-import allowlist: unknown/computed import forms,
   malformed ledger data, or either exact edge-set/count increase also fail.
4. Existing recorded inbound and outbound violations remain visible and
   unchanged; the foundation neither hides nor migrates them.
5. `authorization.api` imports in a clean process and exposes only bounded
   public contracts needed to begin incremental migration.
6. Public API reachability contains no ORM models, SQLAlchemy session,
   repository, concrete service, router, kernel, private capability registry,
   or product implementation.
7. CI runs the validator on every backend change.
8. No runtime authorization or product test assertion changes.
9. Behavior ownership and architecture tests recognize the exact new files.
   Architecture fixtures prove wildcard, direct and aliased `__import__`,
   direct and aliased `importlib.import_module`, and computed module-name
   bypasses are rejected.
10. Required architecture, security, QA, CI-integrity, and test-delta reviews
    pass before the PR is ready.

## Exact verification

Run from `backend/`:

```text
uv run ruff check app/modules/authorization/api scripts/authorization_boundary.py tests/architecture/test_authorization_boundary.py
uv run python -m scripts.authorization_boundary validate --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
uv run pytest -q tests/architecture/test_authorization_boundary.py
uv run python -m scripts.behavior_ownership validate
```

GitHub runs the existing full backend tests and coverage. Full coverage is not
run locally.

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
