# Chunk Contract: WS-XINT-002-04B Guide Read And Binding Authorization Activation

## Goal

Activate fixed-service guide binding and guide-read actions only after merged
ART-03B1, 03B2, 03B3A, 03B3B1, 03B3B2, 03B3B3A, 03B3B3B, 03B3B3C,
03B3B3D, 03B3B4, and 03B4 evidence, without weakening ART-03C.

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
backend/app/modules/artifacts/guide_materialization.py
backend/app/interfaces/artifact_operations.py
backend/tests/test_authorization.py
backend/tests/test_artifact_architecture.py
backend/tests/test_guide_artifacts.py
backend/tests/test_guide_bindings.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04B-internal-review.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04B-pr-trust-bundle.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-04B-external-review-response.md
```

## Not allowed

Human ingest behavior, ART byte/admission implementation outside the narrow
guide-read authorization seam, project lifecycle
changes, submission/review behavior, provider redesign, token roles, generic
guide download, new ActionId or PermissionId values, Celery task payload or
orchestration changes, production route composition, or ART-03C legacy removal.
This contract, the chunk map, and other planning files are not editable by the
04B implementation PR; any required scope change returns to planning review.
The canonical AUTH activation-custody ledger listed above is the sole exception:
04B must update its two existing action rows atomically with catalogue ownership
and availability so documentation/runtime parity cannot become stale.

## Acceptance criteria

- `artifact.guide_source.binding.create` is available only to the fixed
  artifact-binding identity for exact verified content, binding role, guide
  source item, and setup generation.
- `artifact.guide_source.read` is available only to the fixed guide-reader
  identity for the exact bound guide content and setup generation.
- Catalogue ownership for both actions is reconciled from the obsolete
  `WS-AUTH-001-ART-03` label to `WS-XINT-002-04B`; no alias, duplicate action,
  PermissionId, or second activation path is retained.
- AUTH adds two closed typed resource contexts and extends only the existing
  `PreparedAuthorizationService`, `_scope_from_resource`, and kernel service
  branch. The guide actions must not reuse or broaden the generic put,
  verification-job, or pending-work resource selectors.
- Binding authorization binds exactly `project_id`, `guide_id`,
  `guide_source_snapshot_id`, `guide_source_item_id`,
  `project_setup_run_id`, `setup_generation`, `content_id`,
  `verified_replica_id`, `sha256`, `byte_count`, and fixed
  `logical_role=guide_source_original`.
- Read authorization binds exactly `project_id`, `guide_id`,
  `guide_source_snapshot_id`, `guide_source_item_id`,
  `project_setup_run_id`, `setup_generation`, `binding_id`, `content_id`,
  `verified_replica_id`, `storage_namespace_id`, `namespace_fingerprint`,
  `verification_receipt_id`, `verification_generation`, `sha256`,
  `byte_count`, and `media_type`.
- The production AUTH adapters are implemented in
  `backend/app/modules/artifacts/authorization.py`. ART-03C owns the later live
  Celery task/route composition and legacy cutover; 04B neither serializes a handle
  nor changes Celery orchestration.
- The existing guide-read seam must not require a handle prepared outside
  `ArtifactMaterializationService`'s internally owned database session. The
  materialization request carries an idempotency key and exact identifiers, not
  a prepared handle. After locking and composing the exact read facts, the
  service obtains a fresh fixed-reader adapter for that same session, prepares
  and consumes its handle in that root transaction, and only then permits
  provider access. This is the only ART behavior correction owned by 04B.
- Both actions require exact prepared-authority validation and single-use
  consumption before any provider read or binding write. Stale, replayed,
  revoked, mismatched, cross-session, cross-action, or cross-resource authority
  denies before I/O.
- Successful binding state and bounded authorization evidence commit atomically
  in the caller-owned root transaction before later provider reads.
- Replaced binding, stale setup generation, wrong identity, cross-guide,
  cross-project, replay, and revoked service authority deny atomically.
- Copied handles and mismatched snapshot, item, setup run, generation, binding,
  content, replica, namespace, namespace fingerprint, receipt, verification
  generation, digest, size, media type, or logical role deny before provider
  access or protected mutation and create no allowed decision evidence.
- Prepared handles remain opaque, process-local, transaction-bound, and absent
  from Celery messages, logs, Pydantic models, and other serialization surfaces.
- Tests prove that no caller-supplied or earlier-session handle can enter the
  guide materialization request, and that preparation plus consumption use the
  exact session/transaction that authorizes the provider read.
- No generic artifact-download permission or human-to-service authority
  inheritance is introduced.
- ART-03C remains a separate clean-cut gate.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?Set WORKSTREAM_TEST_DATABASE_URL}" .venv/bin/pytest tests/test_authorization.py tests/test_guide_artifacts.py tests/test_guide_bindings.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.projects --cov-report=term-missing --cov-fail-under=90)
(cd backend && .venv/bin/pytest tests/test_artifact_architecture.py -q)
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
least privilege, complete mismatch/no-I/O proof, and preservation of the
ART-03C clean cut.
