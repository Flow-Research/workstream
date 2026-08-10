# Chunk Contract: WS-ARCH-001-01 Boundary Foundation

Status: Proposed. Risk: L1.

## Goal

Install the general modular-monolith boundary foundation without moving or
changing product behavior: canonical module registry, exact private runtime
edge ledger, protected-base no-growth validator, public API leak checks, and CI
enforcement that composes with WS-AUTH-003.

## Allowed files

```text
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/**
.agent-loop/CURRENT_STATE.md
.agent-loop/policies/architecture-boundaries.md
.agent-loop/policies/repository-engineering-policy.md
.ci/module-boundaries/**
backend/scripts/module_boundaries.py
backend/tests/architecture/test_module_boundaries.py
.github/workflows/backend.yml
docs/architecture_lockdown.md
docs/diagrams/backend_v01_components.*
docs/operations_backend_testing.md
```

## Not allowed

- Application runtime, ORM, repository, service, router, schema, migration, or
  composition behavior changes.
- Moving modules or creating empty `api` packages.
- Replacing or weakening AUTH-003, behavior-ownership, coverage, test-structure,
  or hosted lane gates.
- Adding a permanent exception or generic shared/orchestrator module.

## Acceptance criteria

- Registry names exactly nine business and three supporting modules.
- Repository engineering policy uses the same canonical ownership map and
  contains no nonexistent `modules/submissions` boundary.
- Ledger records exact source file, target module, imported private path, and
  capability/repair owner. An unresolved non-security edge uses an explicit
  `owner-unresolved` state. An AUTH- or authorization-affecting edge without an
  owner uses `security-triage-required`, which blocks implementation of the
  touched capability until ownership is resolved.
- Validator rejects a new edge, expanded existing edge, public API private
  leak, unknown module, and cyclic public dependency.
- Existing exact debt passes only through protected ledger reconciliation.
- AUTH-003 is the sole canonical source for every inbound/outbound AUTH edge.
  The general validator loads that ledger through the existing AUTH boundary
  parser and combines it by reference; the general ledger contains no copied
  AUTH edge. Tests prove missing, additional, or divergent AUTH/general results
  fail closed.
- CI runs the general validator for applicable backend changes.

## Verification commands

```text
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/module_boundaries.py validate
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest -q -p pytest_asyncio.plugin backend/tests/architecture/test_module_boundaries.py backend/tests/architecture/test_authorization_boundary.py
PYTHONPATH=backend backend/.venv/bin/ruff check backend/scripts/module_boundaries.py backend/tests/architecture/test_module_boundaries.py
git diff --check
```

Full coverage and semantic lanes run in GitHub.

## Required reviewers

- architecture
- security
- QA
- senior engineering
- CI integrity
- reuse/dedup
- test delta
- docs

## Human review focus

- Is the ledger a temporary exact recovery instrument rather than an allowlist?
- Does the validator preserve AUTH-003 and existing CI strength?
- Are module ownership and public API rules precise enough to govern ART-05A?
