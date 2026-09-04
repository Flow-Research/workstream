# Internal Review Evidence: WS-ART-001-02B1

## Chunk

`WS-ART-001-02B1`: S3-Compatible MinIO And AWS

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: `9cd5620ef5f72e7ba9abc75e9ac7b398996f0c8a`

Reviewed at: 2026-07-18T23:40:43Z

Reviewer run IDs: senior-engineering=019f778b-6b07-7561-a718-e1da40a532a0; architecture=019f778b-6372-7c83-85ca-a61f63885c17; QA/test=019f778b-74eb-7250-b07c-573c979b2849; security/auth=019f778b-81f0-7b31-85d5-8955f9047b3e; product/ops=019f7791-3326-71e3-b838-54143b94a129; reuse/dedup=019f7791-3943-7de3-bdbf-c3643f45c43c; CI-integrity=019f7791-43a6-78e0-8f17-67861bf27455; test-delta=019f7791-4c52-7091-9076-f534bccdfad6; docs=019f7797-215a-7e02-b6e4-c33b584ec2b5

The reviewed base is `origin/main` at
`983b9e534b84f1590fafecc0ce1355cf131257ce`, including AUTH PR #148 and the
latest merged REV planning. The merged REV planning changes introduce no ART
runtime or ownership drift in `origin/main...HEAD`.
Only review artifacts and initiative status may change after the reviewed SHA.
Any implementation, test, workflow, policy, or chunk-contract change invalidates
this evidence and requires a new exact-head review cycle.

## Reviewed Change

- Added one S3-protocol ArtifactStore implementation shared by MinIO and the
  inactive native AWS profile.
- Proved the active local/CI path against real digest-pinned MinIO with the same
  ArtifactStore v2 contract used by LocalStorage.
- Kept native AWS runtime-ineligible until Chunk 07 supplies an immutable live
  activation proof.
- Isolated each AWS workload-identity method from ambient credential, proxy,
  file, process, cache, and unselected metadata sources.
- Preserved server-derived content keys, sealed source validation, exact replay,
  bounded object size, no multipart/list/delete/copy surface, and sanitized
  provider failures.
- Added canonical global general-purpose bucket, region, prefix, and MinIO
  endpoint validation, including rejection of secret-bearing endpoint input.
- Retained the full repository 78 percent CI floor and every cumulative focused
  90 percent gate while adding exact S3 adapter and validation gates.
- Integrated AUTH PR #148 without editing or activating AUTH-owned runtime
  behavior.
- Integrated the latest merged REV planning without editing or activating
  REV-owned runtime behavior.
- Bound repository-managed MinIO to host loopback in Compose and CI and added
  deterministic gates for both definitions.
- Defined `local/CI MinIO` as non-production eligibility, including private
  operator-controlled container-network development/test endpoints only.
- Documented and enforced the exact `minio-v1` and `aws-s3-v1` namespace
  descriptor schemas.
- Bounded copied request-body bytes independently of source chunk size by
  retaining unconsumed source bytes through a memoryview cursor.
- Required the selected AWS workload credentials to materialize successfully before
  explicit resolution can report success.
- Canonicalized equivalent IPv6 MinIO literals before deriving endpoint and
  namespace identity.
- Extended secret-retention proof to byte buffers and public object state.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | The shared adapter and four external-review repairs are maintainable. Exact SDK pins bound the reviewed reliance on SDK credential internals. |
| qa/test | PASS WITH LOW RISKS | None | Real MinIO, credential isolation, bounded streaming, IPv6 identity, secret scanning, and CI evidence cover the chunk contract without weakened tests. |
| security/auth | PASS | None | Secret-bearing endpoint and metadata failures are sanitized, credential sources are closed, and ART/AUTH ownership remains intact. |
| product/ops | PASS | None | No operator recovery, contributor, reviewer, contribution, compensation, fulfillment, or reputation behavior is activated. |
| architecture | PASS WITH LOW RISKS | None | One typed adapter path remains, concrete S3 construction stays in ART composition, and exact SDK pins bound the inactive AWS helper dependency. |
| ci integrity | PASS | None | The 78 percent repository gate and all cumulative 90 percent gates remain fail closed with no bypass. |
| docs | PASS | None | README, artifact specification, settings, provider eligibility, and loop state match the implementation. |
| reuse/dedup | PASS WITH LOW RISKS | None | Provider references, S3 validation, runtime guards, and deep secret assertions reuse canonical helpers without parallel implementations. The reviewer relied on the recorded real-MinIO proof rather than rerunning it. |
| test delta | PASS WITH LOW RISKS | None | Active-MinIO and inactive-AWS proof is stronger, including all four repairs; no test was skipped or weakened. AWS remains intentionally inactive pending live proof. |

## Valid Findings Addressed

- Replaced permissive S3 region validation with a bounded canonical region
  grammar and complete positive/negative tests.
- Made invalid MinIO endpoint errors discard userinfo, malformed ports, and raw
  source values across constructor, Pydantic mapping/JSON/string validation,
  environment, dotenv, traceback, and structured error paths.
- Documented the intentional v0.1 global general-purpose bucket boundary and
  rejection of account-regional `-an` names because Workstream does not emit
  the account-regional namespace header.
- Rejected every AWS reserved general-purpose bucket prefix and suffix and
  validated every dotted bucket label.
- Sanitized ECS and IMDS credential failure paths so SDK exceptions cannot
  retain response bodies, authorization tokens, endpoints, or credentials.
- Bound replay to the sealed committed source before any provider operation and
  removed stale provider-reference divergence.
- Reconciled authored ART loop state and work queue with AUTH PR #148 while
  keeping AUTH-09D-B and every later ART chunk inactive.
- Corrected the successor chunk heading so merge-intent validation resolves
  `WS-ART-001-02C1` without changing explicit-start authority.
- Consolidated duplicate mapping validators while preserving distinct Pydantic
  entry points and clearing credentials from every ordinary exception path.
- Rejected non-object settings JSON before Pydantic can retain secret-bearing
  input in structured errors and cleared partial S3 secret extraction on later
  source failures.
- Bound repository-managed MinIO to loopback in Compose and CI and made both
  definitions regression-protected by the 88-test agent-gate runner.
- Clarified private non-production MinIO eligibility and added the exact closed
  S3 namespace profile table to the canonical artifact specification.
- Replaced whole-source-chunk pending copies with a bounded memoryview cursor and
  added direct proof that unconsumed bytes remain available without expanding
  the copied request buffer.
- Materialized deferred AWS workload credentials before returning explicit
  resolution success and sanitized refresh failures.
- Compressed equivalent IPv6 endpoint literals before namespace identity
  derivation.
- Extended deep secret assertions across bytes, bytearray, memoryview, and
  nested public object state.

## Commands Run

```bash
docker compose up -d --wait postgres redis minio
cd backend && .venv/bin/ruff check app tests
cd backend && .venv/bin/pip check
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_artifact_architecture.py tests/test_artifact_cleanup_wiring.py tests/test_artifact_preparation.py tests/test_artifact_store_conformance.py tests/test_local_artifact_store.py tests/test_s3_artifact_store.py tests/test_aws_credential_isolation.py tests/test_config.py tests/test_assertion_helpers.py tests/test_audit.py -q --cov=app.adapters.artifacts --cov=app.interfaces.artifact_operations --cov=app.interfaces.artifacts --cov=app.core.config --cov=app.core.s3_validation --cov-report=term-missing --cov-fail-under=90
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

Results: 443 real-service-focused tests passed after the external-review repairs.
`S3CompatibleArtifactStore` coverage is 91 percent, S3 validation coverage is
97 percent, and combined changed-subsystem coverage is 92.52 percent. Ruff,
dependency integrity, stale contract/authorization/review/wording scans,
Markdown links, 88 agent-gate tests, Compose validation, and diff checks passed.

The isolated full repository suite and 78 percent whole-app floor remain
authoritative in GitHub Backend CI, as explicitly chosen because local execution
is prohibitively slow. The CI reviewer confirmed that exact gate is retained.

## Remaining Risks

- Native AWS operations remain deliberately unavailable until Chunk 07 adds the
  release-bound live proof and production composition guard.
- MinIO is non-production protocol proof, including private local/dev/test
  container-network use; it is not production activation evidence.
- Provider acknowledgement remains non-bindable pending later admission,
  verification, publication, and recovery chunks.

## Stop Condition

Publish this evidence-bound candidate for GitHub CI, CodeRabbit, and explicit
human review. Do not merge without the user's approval and do not start
`WS-ART-001-02C1` automatically.
