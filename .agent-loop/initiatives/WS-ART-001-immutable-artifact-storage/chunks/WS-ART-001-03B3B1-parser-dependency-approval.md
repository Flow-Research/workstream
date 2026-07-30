# Chunk Contract: WS-ART-001-03B3B1 — Parser Dependency Approval

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Produce the exact pinned PDF, OOXML, and image parser allowlist and deterministic
CI enforcement without installing packages or changing runtime behavior.

## Why this chunk exists

Untrusted document parsers are separate security and supply-chain boundaries.
Human approval must precede every package or lock change.
## Approved plan reference

- PLAN: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md`

## Risk class

L1

## SLA

P2

## Allowed files

```text
backend/config/guide_extractor_dependencies.json
backend/scripts/check_guide_extractor_dependencies.py
backend/tests/test_guide_extractor_dependencies.py
.github/workflows/backend.yml
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
docs/spec_artifact_storage_service.md
```

## Not allowed

Package/lock changes, application/runtime imports, parser adapters, fixtures
containing real customer data, AUTH/Celery/submission changes.

## Acceptance criteria

- Each candidate records exact package/version, license, maintenance,
  advisories, transitive graph, native-code use, malformed-input history,
  network behavior, and cancellation/timeout implications.
- The allowlist schema records package name, exact version, artifact hashes,
  source/index, direct/transitive status, import names, native-wheel status,
  license, advisory snapshot date, and exact format scope.
- The allowlist maps each dependency to only PDF, OOXML, or image metadata.
- CI fails closed on undeclared, unpinned, hash-drifted, or wrong-format parser
  dependencies.
- Human approval of the exact list is recorded before any of 03B3B2,
  03B3B3A-03B3B3D, or 03B3B4 starts.

## Verification commands

```bash
(cd backend && python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run pytest -q tests/test_guide_extractor_dependencies.py)
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
git diff --check
```

## Required reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Stop conditions

Stop if scope expands, a dependency lacks approval/evidence, isolation must be
weakened, CI or coverage must be weakened, or a second runtime parser path is
required.

## Human review focus

Whether every proposed package is necessary, minimal, maintained, license-safe,
pure Python or explicitly native, and adequately isolated.
