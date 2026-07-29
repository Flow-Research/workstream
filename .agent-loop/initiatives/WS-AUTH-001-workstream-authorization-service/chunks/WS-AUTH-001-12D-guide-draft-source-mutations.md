# Chunk Contract: WS-AUTH-001-12D — Draft Guide And Source Metadata Cutover

## Status and prerequisite

Proposed and inactive after 12C.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate guide create/update and source-snapshot metadata creation for the
covered Project Manager using exact project/guide lineage and PREP.

## Why this chunk exists

These are human-owned draft metadata mutations adjacent to, but distinct from,
ART byte ingestion and policy lifecycle mutations.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/setup_queue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/api/deps/authorization.py
backend/alembic/versions/<then-current-next>_guide_source_metadata_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_guide_artifacts.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

ART ingest/binding/read/provider behavior, sufficiency/policy/activation state,
review/revision/retired-economic/contribution policy mutation, or issuer-claim fallback.

## Acceptance criteria

- Exact-project Project Manager authority is required; system scope covers its
  projects, project scope covers only the named project.
- Guide create and update hard-remove embedded review, revision, retired economic, and
  contribution policy mutation fields; 12D2 becomes the only configuration
  path and no compatibility route or payload alias remains.
- Final consume follows locks of project, draft guide, current source lineage,
  and generation facts, before mutation/setup enqueue intent.
- Cross-project/guide/snapshot, active/superseded guide, stale generation,
  revoked grant/link/profile, replay, copied handle, and transaction mismatch
  fail before state or queue intent.
- Existing active ART ingest is unchanged and no provider access is granted.
- Project/guide/source rows record local actor/link/grant/scope/action and
  decision-event provenance; historical rows remain nullable/readable.
- Changed authorization/project modules remain at least 90 percent covered and
  the final pushed head SHA passes `Backend / test` and `Agent Gates`.

## Verification commands

Before start, freeze exact isolated-runner, migration round-trip, coverage,
Ruff, API drill, stale contract/docs, link, and diff commands.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact lineage, policy-field clean cut, enqueue atomicity, and ART separation.

## Stop conditions

Stop if the route must mutate review/revision/retired-economic/contribution policy or
authorize byte/provider behavior.
