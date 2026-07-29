# Chunk Contract: WS-XINT-002-04B Guide Read And Binding Authorization Activation

## Goal

Activate fixed-service guide binding and guide read only after merged ART-03B1,
03B2, 03B3A, 03B3B, and 03B4 evidence, without weakening ART-03C.

## Risk class

L1.

## Entry gate

- WS-XINT-002-04A is merged.
- The complete split-03B hidden behavior and exact resource manifest are merged
  and reviewed.

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/repository.py
backend/app/modules/authorization/runtime.py
backend/app/modules/artifacts/authorization.py
backend/tests/test_authorization.py
backend/tests/test_guide_artifacts.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04B-internal-review.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04B-pr-trust-bundle.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04B-external-review-response.md
```

## Not allowed

Human ingest behavior, ART byte/admission implementation, project lifecycle
changes, submission/review behavior, provider redesign, token roles, generic
guide download, new catalogue values, or ART-03C legacy removal.
This contract, the chunk map, and other planning files are not editable by the
04B implementation PR; any required scope change returns to planning review.

## Acceptance criteria

- `artifact.guide_source.binding.create` is available only to the fixed
  artifact-binding identity for exact verified content, binding role, guide
  source item, and setup generation.
- `artifact.guide_source.read` is available only to the fixed guide-reader
  identity for the exact bound guide content and setup generation.
- Both actions require exact prepared-authority validation and single-use
  consumption before any provider read or binding write. Stale, replayed,
  revoked, mismatched, cross-session, cross-action, or cross-resource authority
  denies before I/O.
- Successful binding state and bounded authorization evidence commit atomically
  in the caller-owned root transaction before later provider reads.
- Replaced binding, stale setup generation, wrong identity, cross-guide,
  cross-project, replay, and revoked service authority deny atomically.
- No generic artifact-download permission or human-to-service authority
  inheritance is introduced.
- ART-03C remains a separate clean-cut gate.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_guide_artifacts.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.projects --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass `Backend / test` and `Agent Gates / agent-gates`.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Separate fixed identities, exact verified-content and generation binding,
least privilege, and preservation of the ART-03C clean cut.
