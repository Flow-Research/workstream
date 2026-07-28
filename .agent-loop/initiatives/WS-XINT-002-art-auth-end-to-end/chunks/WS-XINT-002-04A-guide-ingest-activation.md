# Chunk Contract: WS-XINT-002-04A Guide Ingest Authorization Activation

## Goal

Activate only `artifact.guide_source.ingest` after merged ART-03A evidence uses
the one opaque, transaction-bound PREP interface from WS-XINT-002-02.

## Risk class

L1.

## Entry gate

- ART-03A is rebased onto current `main`, merged, and reviewed.
- Its durable mutation request carries `PreparedAuthorizationHandle`; raw
  `AuthorizationContext` and an ART-local alternate authority protocol are not
  mutation authority.
- The hidden route remains deny-only until this chunk installs the exact AUTH
  adapter and changes only guide ingest availability.

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
backend/tests/test_artifact_admission.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04A-internal-review.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04A-pr-trust-bundle.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04A-external-review-response.md
```

## Not allowed

ART byte/admission implementation, project routes or lifecycle behavior,
guide binding/read, submission/review behavior, provider redesign, token roles,
generic guide download, new catalogue values, or a second authority protocol.
This contract, the chunk map, and other planning files are not editable by the
04A implementation PR; any required scope change returns to planning review.

## Acceptance criteria

- Initial authority requires the exact active Project Manager grant for the
  project and occurs before scratch or request-body byte intake.
- Final PREP consumption recomposes and locks actor/link, grant, project, draft
  guide, snapshot/item, operation identity, request digest, and server-computed
  digest, byte count, and media type in the caller-owned root transaction.
- Consumption occurs before capacity/put-intent commit and provider I/O;
  authorization evidence and the protected mutation commit atomically once.
- Revoked actor/link/grant, cross-project lineage, stale guide/snapshot/item,
  replay, copied or serialized handle, cross-session/root/action/resource use,
  and replaced transaction deny atomically without capacity, put, provider, or
  allowed-audit effects.
- Only `artifact.guide_source.ingest` becomes active. Guide read and binding
  remain planned until WS-XINT-002-04B consumes merged ART-03B evidence.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_guide_artifacts.py tests/test_artifact_admission.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.projects --cov-report=term-missing --cov-fail-under=90)
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

Manager-only ingest, one opaque PREP seam, final locked lineage and byte facts,
denial atomicity, and ingest-only availability.
