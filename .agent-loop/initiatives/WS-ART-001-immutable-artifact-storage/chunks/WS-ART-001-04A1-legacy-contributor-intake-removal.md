# Chunk Contract: WS-ART-001-04A1 — Legacy Contributor Intake Removal

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Implemented; external PR gates pending

## Goal

Remove legacy multi-step upload-session/item contributor reachability and its
unused schema before building the one-ZIP replacement.

## Allowed Files

- `backend/app/modules/artifacts/models.py`
- `backend/app/db/models.py`
- `backend/app/modules/artifacts/schemas.py`
- `backend/app/modules/artifacts/service.py`
- `backend/app/modules/artifacts/repository.py`
- one new linear `0051` Alembic revision after `0050_guide_source_v2`
- `backend/tests/test_alembic.py`
- `backend/tests/test_artifact_architecture.py`
- contributor-only removals plus guide/checker regression coverage in
  `backend/tests/test_artifact_admission.py`,
  `backend/tests/test_artifact_recovery.py`, and
  `backend/tests/test_artifact_verification.py`
- `backend/tests/conftest.py`
- contributor-only cleanup in `backend/tests/test_artifact_authorization.py`
- stale-contract/spec/glossary text and this chunk's loop evidence

No runtime route file is allowed because no upload-session/item HTTP route is
currently composed and 04A1 adds no replacement.

## Not Allowed Changes

Replacement upload route, ZIP parsing, provider I/O, Submission/checker/review,
AUTH catalogue/availability, compatibility aliases, or fabricated backfill.
Old Alembic revisions are immutable. No detached historical columns, legacy
tables, compatibility models, or write aliases remain after the safe-empty
cutover.

## Locked Migration Policy

The new migration obtains exclusive locks on the legacy ledgers, put attempts,
and operation receipts before checking or changing schema. Upgrade refuses in
the same transaction if any of these facts exist:

- any `artifact_upload_sessions` row;
- any `artifact_upload_items` row;
- any `artifact_put_attempts.producer_request_type = 'contributor'` row;
- any non-null `artifact_put_attempts.upload_item_id`;
- any `artifact_operation_receipts.contract_version = 1` row; or
- any non-null `artifact_operation_receipts.upload_item_id`.

Refusal preserves the prior revision, schema, rows, foreign keys, and readable
historical identifiers without deletion or fabricated translation. Such a
deployment requires a separately approved maintenance/audit migration; 04A1
does not migrate populated legacy intake.

On a safe-empty deployment, upgrade removes contributor branches from put and
receipt constraints, removes their upload-item foreign keys/indexes/columns,
then drops `artifact_upload_items` and `artifact_upload_sessions`. Runtime code
simultaneously loses every contributor request, dispatch, lookup, and state
projection path.

Downgrade recreates the exact empty legacy columns, constraints, indexes, and
tables because a successful upgrade proved that no legacy facts were deleted.
It refuses atomically if the post-cutover database contains a contributor
producer fact that cannot be represented truthfully. No downgrade invents
sessions, items, actors, roles, or state.

## Acceptance Criteria

- No route, request command, admission union member, service dispatch,
  repository lookup, ORM model/import, SQL constraint, or recovery/verification
  mutation can create or use the old intake.
- Architecture/OpenAPI proof shows 04A1 exposes neither the retired surface nor
  the later submission-bundle replacement.
- Safe-empty upgrade removes both ledgers and every writable contributor
  reference; safe-empty downgrade recreates the exact empty prior schema.
- Every populated legacy condition above refuses atomically and leaves revision,
  schema, data, and historical identifier readability unchanged.
- Direct SQL cannot create contributor put attempts or upload-item-backed
  receipts after cutover.
- Guide and checker-output admission, put confirmation, missing-object recovery,
  integrity mismatch, and verification terminalization continue without any
  upload-item mutation branch.
- AUTH's historical-only deletion proof continues to pass without catalogue,
  matrix, availability, grant, or alias edits.

## Verification Commands

Exact minimum:

```bash
(cd backend && .venv/bin/python -m pytest -q \
  tests/test_artifact_architecture.py tests/test_alembic.py)
(cd backend && .venv/bin/python -m pytest -q \
  tests/test_artifact_admission.py tests/test_artifact_recovery.py \
  tests/test_artifact_verification.py)
(cd backend && .venv/bin/python -m ruff check app tests scripts)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Alembic tests must prove empty upgrade/downgrade, every populated-upgrade
refusal condition, atomic unchanged state after refusal, exact schema removal
and recreation, and post-cutover direct-SQL denial. Architecture tests must
prove runtime/import/metadata and route/OpenAPI absence. Focused guide/checker
tests must cover the shared recovery/verification outcomes named above. Hosted
Backend and Agent Gates remain authoritative for repository 78% and ART 90%
coverage; no threshold or gate may be weakened.

## Required Reviewers

Architecture, security/auth, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

Prove deletion without opening a replacement or losing historical evidence.
Stop if populated legacy rows require migration, an AUTH/catalogue change seems
necessary, a replacement route/ZIP/scratch/provider/Submission/checker/review
behavior is needed, an old Alembic revision would need editing, or any required
test/coverage gate would need weakening.
