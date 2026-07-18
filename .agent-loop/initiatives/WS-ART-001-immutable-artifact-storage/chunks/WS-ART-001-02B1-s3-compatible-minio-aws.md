# Chunk Contract: WS-ART-001-02B1 - S3-Compatible MinIO And AWS

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 02A3

Artifact contract phase: `artifact_store_cutover`

## Goal

Implement `S3CompatibleArtifactStore`, prove it against real MinIO, and add
validated AWS S3 configuration plus deployment-proof support without making AWS
production-instantiable. R2 is deferred and has no active runtime profile or
credential-delivery contract.

## Allowed Files

- `backend/app/adapters/artifacts/s3_compatible.py` and adapter registration;
- AWS/MinIO settings in `backend/app/core/config.py`;
- backend dependency manifest/lock with exact `aiobotocore==3.7.0` and
  `botocore==1.43.0` pins, `docker-compose.yml`, and
  `.github/workflows/backend.yml` for MinIO and exact coverage proof;
- `scripts/test_agent_gates.py` only to assert the exact workflow command,
  source set, threshold, and cumulative retention;
- focused adapter, configuration, secret-redaction, negative-permission,
  workload-identity isolation, and LocalStorage/MinIO conformance tests,
  including `backend/tests/test_aws_credential_isolation.py`;
- AWS deployment-readiness documentation and chunk memory.

## Not Allowed

- any deferred-provider runtime or production activation;
- product/Operator routes, verification/recovery models, or product cutovers;
- presigned URLs, direct browser upload, delete/copy/list/search/public access;
- Flow Node or concrete-adapter imports in product services.

## Acceptance Criteria

- the adapter uses the sealed server-computed commitment to derive its
  identity-free key and cannot accept an arbitrary stream/digest pair;
- one conditional no-overwrite `PutObject` handles concurrent same-content
  writes, and a precondition failure remains an unverified replay candidate;
- AWS `HeadObject` maps 404 to missing and every 403 to provider unavailable;
  the adapter exposes and calls no object-list operation;
- objects above 512 MiB fail before provider I/O and multipart is absent;
- ETag/provider checksums are not Workstream integrity facts;
- native AWS endpoint omission with explicit region and MinIO endpoint/region
  validate; production rejects HTTP/local endpoints and static credentials;
- AWS production credential mode `aws_workload_identity` selects exactly one
  of `assume-role-with-web-identity`, `container-role`, or `iam-role`; the
  credential resolver contains only that provider and the resolved method must
  match;
- explicit credentials, environment access keys, shared credential/config
  files, credential processes, login/SSO, legacy EC2/Boto sources, and every
  unselected workload provider fail startup before credential loading;
- isolation tests poison nonselected file, process, cache, metadata, and network
  sources and prove none is accessed; MinIO static credentials are local/CI
  only and never survive error/log object graphs;
- dependency tests assert the exact async SDK pair; upgrades require a separate
  credential/provider-behavior review;
- real digest-pinned MinIO and LocalStorage pass the same v2 conformance suite;
- the application factory can instantiate only LocalStorage and MinIO in this
  chunk. Valid AWS configuration remains runtime-ineligible with the stable
  `artifact_provider_live_proof_required` startup failure; only Chunk 07 may
  add the immutable activation record and production composition guard;
- startup and operation tests reject configured adapter/profile/namespace
  mismatch against persisted deployment or replica identity; no request is
  routed to a second namespace;
- adversarial first-writer and cross-project tests prove that a client-selected
  digest cannot occupy another content key;
- focused changed-subsystem coverage is at least 90 percent and repository
  coverage remains at least 78 percent.
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift.

## Exact CI Coverage Gate

```bash
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
coverage report --include='app/workers/*' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis minio
(cd backend && .venv/bin/ruff check app tests)
(cd backend && .venv/bin/pytest tests/test_artifact_store_conformance.py tests/test_s3_artifact_store.py tests/test_aws_credential_isolation.py tests/test_config.py -q --cov=app.adapters.artifacts --cov=app.interfaces.artifact_operations --cov=app.interfaces.artifacts --cov=app.core.config --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is the adapter truly one S3-protocol implementation?
- Can untrusted input influence the final object key?
- Does AWS production load only the explicitly selected workload-identity
  provider without touching any other credential source?
