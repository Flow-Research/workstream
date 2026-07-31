# Chunk Contract: WS-AUTH-001-12D — Draft Guide And Source Metadata Cutover

## Status and prerequisite

Implementation in progress after merged 12C and completed L1
pre-implementation review.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate guide create/update and source-snapshot metadata creation for the
covered Project Manager using exact project/guide lineage and PREP.

## Why this chunk exists

These are human-owned draft metadata mutations adjacent to, but distinct from,
ART byte ingestion and policy lifecycle mutations.

## Risk class and SLA

L1 / P1.

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/guide_mutation_repository.py
backend/app/modules/projects/guide_mutation_router.py
backend/app/modules/projects/guide_mutation_service.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/setup_queue.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/audit/schemas.py
backend/app/api/deps/authorization.py
backend/app/api/router.py
backend/alembic/versions/0045_guide_source_metadata_authority.py
.github/workflows/backend.yml
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_guide_artifacts.py
backend/tests/test_alembic.py
backend/tests/test_api_controls.py
backend/tests/project_create_fixtures.py
backend/tests/conftest.py
backend/scripts/api_contract_e2e.py
README.md
docs/spec_chunk_3_project_guide_foundation.md
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

ART ingest/binding/read/provider behavior; sufficiency, submission/checker,
activation, review, revision, retired economic/configuration, contribution-record,
or payout-configuration mutation; project update/archive invention; issuer-claim or token-role
fallback; a second authorization protocol; or a prepared handle crossing commit,
Celery, serialization, or durable job boundaries.

## Action and product clean cut

- Activate exactly `project.guide.create`, `project.guide.update`, and
  `project.guide_source_snapshot.create`. Every 12D2/12E/12F/12G/12B2/12H
  action remains planned. OpenAPI exposes exactly one marker for each 12D route.
- `ProjectGuideCreate.source_snapshot` is removed. Guide creation never creates a
  snapshot or setup run. Source metadata uses only its separate route/action/PREP.
- Guide create/update hard-remove `review_policy`, `revision_policy`, and every
  retired payout/economic configuration field or alias. Review/revision returns
  only in 12D2. Economic and contribution-record policy remains outside AUTH with
  no compatibility field, alias, route, or fallback.
- `content_markdown` remains guide source material. It may change only before the
  first source snapshot exists. Once any snapshot captures the guide, content
  changes fail before product state or replay commit; bounded non-source metadata
  such as `change_summary` may still change on an exact draft guide.
- Existing active ART ingest remains hidden and unchanged. 12D performs no
  `ArtifactStore`, binding, verification, provider, byte-read, or byte-write call.

## Authority and PREP contract

- Only an active human with an active exact identity link and effective Project
  Manager admin grant carrying `project.guide.manage` may proceed. System scope
  covers any project; project scope covers only its exact `scope_project_id`.
  Other admin roles, contributor grants, services, token roles, and issuer claims deny.
- PREP uses the existing opaque handle. Its positive project-mutation branch
  locks the exact actor/link and one effective Project Manager grant with system
  or exact-project coverage. Final consume revalidates lifecycle, active grant,
  action, scope, request digest, root transaction, and complete final resource facts.
- Unsupported preparation produces bounded denial evidence for the same exact
  resource context. Full resource-context digests are persisted for all 12D decisions.
- Copied/replayed/wrong-action/wrong-resource handles, changed input, replaced or
  nested transactions, cross-project/guide/snapshot selectors, stale lineage or
  generation, and post-lock revocation fail before product state or queue intent.

## Idempotency and transaction contract

- Every route requires a UUID `Idempotency-Key`, validated before actor
  first-access provisioning. The namespace is
  `(actor_profile_id, action_id, idempotency_key)` and the canonical digest binds
  route, validated body, actor, exact link, project, server operation id, target
  resource id, and operation generation.
- A fresh reservation starts `pending`. Protected state, allowed decision
  evidence, row provenance, exact serialized response, and the `committed`
  transition commit atomically. The route owns commit/rollback; product services
  never commit.
- Exact committed replay returns the recorded response without fresh PREP,
  product writes, setup-run creation, or broker dispatch. Changed input returns
  structured `idempotency_mismatch`; an in-flight request returns retryable
  `idempotency_pending`; denial and ordinary failure roll back pending state.
  Concurrent same-key consumption produces exactly one mutation.
- Dedicated 12D router/service/repository boundaries replace legacy
  request-role gating, self-commit, and embedded-policy behavior. No compatibility
  path remains in the legacy projects router/service.

## Per-mutation lock and consume order

- Guide create selects a nonpersistent, in-memory server-generated guide id at
  generation 1, prepares authority, then locks the exact project and proves the
  version absent; it
  consumes exact project/new-guide/version/generation facts before insert.
- Guide update prepares authority, then locks exact project, exact guide, and
  latest source lineage; proves the guide is a draft in the named project;
  reserves `current_mutation_generation + 1`; and consumes current
  version/status/generation plus predecessor snapshot id/hash before mutation.
- Source-snapshot create prepares authority, then locks exact project, draft
  guide, latest predecessor snapshot, and source lineage; sanitizes and hashes
  server-owned manifest facts; reserves a server-generated snapshot id and next
  generation; and consumes exact guide/version/status, predecessor id/hash, new
  snapshot id/hash/generation, and request digest before snapshot items or setup intent.

## Provenance, migration, and queue custody

- `project_guides`, `guide_source_snapshots`, and source-created
  `project_setup_runs` record nullable historical actor-profile, exact identity
  link, matched Project Manager grant, scope type/project, action, operation
  generation, and allowed decision-event provenance. The idempotency ledger
  retains every committed operation so later updates do not erase prior custody.
- Exact migration file `0045_guide_source_metadata_authority.py` (revision id
  `0045_guide_metadata_authority`) follows `0044_project_create_authority`. It
  adds nullable historical columns, foreign
  keys, action/scope/shape checks, the 12D replay ledger, immutable transition
  guards, and deferrable triggers tying new guide/snapshot/setup participants to
  exact allowed evidence and resource-context digest. Historical rows remain
  readable and unbackfilled; new mutations cannot omit custody. Downgrade refuses
  after any 12D evidence or attributed mutation.
- The setup-run row plus exact setup generation is the durable queue intent and
  commits with snapshot, evidence, and replay state. Celery dispatch occurs only
  after commit and never carries PREP. Broker failure records `enqueue_failed` on
  that exact run for bounded recovery. HTTP replay never creates or dispatches a
  second intent.

## Required proof matrix

- Success: system and exact-project Project Manager for all three actions, exact
  action/grant/scope/provenance, route-owned transaction, and recorded response.
- Denial: wrong role, contributor/service, wrong scope, revoked/suspended/
  deactivated actor/link/grant, and every unavailable future action.
- Capability abuse: copied/replayed/wrong-action/wrong-resource handle, changed
  input, replaced/nested transaction, cross-lineage, stale predecessor/generation,
  and post-lock revocation.
- Replay/concurrency: missing/invalid key, exact replay, mismatch, pending,
  concurrent same-key use, exact response, and no duplicate guide/snapshot/run/task.
- Policy clean cut: removed fields/aliases return 422 and write no policy row.
- Source immutability: content update succeeds before the first snapshot, fails
  after snapshot capture without state/replay effects, and a bounded
  `change_summary` update remains allowed on the exact draft.
- Queue: intent commits atomically; success records one task id; broker failure
  records `enqueue_failed`; replay creates and dispatches nothing.
- ART: hidden ingest remains unchanged and no provider/byte operation is called.
- Migration: `0044 -> 0045 -> 0044 -> 0045`, fingerprint, historical survival,
  unattributed/custody-mismatched refusal, and populated downgrade refusal.
- API: three action markers, success, concealed denial, replay/mismatch,
  policy-field rejection, and unchanged hidden ART route.

## Coverage and hosted gates

- Every new or materially changed AUTH-12D boundary remains at least 90 percent
  covered. Removal-only legacy aggregation modules remain under the unchanged
  authorization-subsystem and repository-wide gates.
- The repository-wide 78 percent floor and every existing 90 percent gate remain
  unchanged. Add a hosted per-file 90 percent gate for the three dedicated 12D
  modules; never add `continue-on-error`, `|| true`, skips, or exclusions.
- Final pushed SHA must pass `Backend / test`, `Agent Gates`, required internal
  reviewers, and external review triage.

## Verification commands

```bash
cd backend
uv run ruff check app/api/deps/authorization.py app/api/router.py \
  app/modules/audit/schemas.py app/modules/authorization/catalogue.py \
  app/modules/authorization/kernel.py app/modules/authorization/prepared.py \
  app/modules/authorization/runtime.py app/modules/projects/models.py \
  app/modules/projects/authorization_reads.py \
  app/modules/projects/guide_mutation_repository.py \
  app/modules/projects/guide_mutation_router.py \
  app/modules/projects/guide_mutation_service.py app/modules/projects/repository.py \
  app/modules/projects/router.py app/modules/projects/schemas.py \
  app/modules/projects/service.py app/modules/projects/setup_queue.py \
  tests/project_create_fixtures.py tests/test_authorization.py \
  tests/test_projects.py tests/test_guide_artifacts.py tests/test_alembic.py \
  tests/test_api_controls.py scripts/api_contract_e2e.py

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python scripts/run_isolated_tests.py \
  --metadata-json .ci/auth12d.json --lane auth12d --timeout-seconds 1200 -- \
  uv run pytest -p pytest_asyncio.plugin -q tests/test_authorization.py \
  tests/test_projects.py tests/test_guide_artifacts.py tests/test_alembic.py \
  tests/test_api_controls.py -k 'guide_authority or guide_source_metadata or create_guide or update_guide or create_guide_source_snapshot or guide_source_metadata_authority'

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python scripts/run_isolated_tests.py \
  --metadata-json .ci/auth12d-api.json --lane auth12d_api \
  --timeout-seconds 1500 -- uv run python scripts/api_contract_e2e.py

uv run coverage erase
uv run coverage run --source=app -m pytest -q tests/test_authorization.py \
  tests/test_projects.py tests/test_guide_artifacts.py \
  -k 'guide_authority or guide_source_metadata or create_guide or update_guide or create_guide_source_snapshot'
for source in app/modules/projects/guide_mutation_repository.py \
  app/modules/projects/guide_mutation_router.py \
  app/modules/projects/guide_mutation_service.py
do
  uv run coverage report --include="${source}" --precision=2 --fail-under=90
done

cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

The isolated PostgreSQL commands require `WORKSTREAM_TEST_ADMIN_DATABASE_URL`.
The full repository suite and coverage run only in hosted GitHub `Backend / test`;
do not run that full suite locally.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact lineage/generation, replay response custody, policy-field clean cut,
database-enforced provenance, durable setup intent/post-commit dispatch, and ART separation.

## Stop conditions

Stop if implementation must mutate excluded policy/ART behavior, introduce a
second auth protocol, weaken CI, cross PREP over commit/Celery, or exceed this boundary.
