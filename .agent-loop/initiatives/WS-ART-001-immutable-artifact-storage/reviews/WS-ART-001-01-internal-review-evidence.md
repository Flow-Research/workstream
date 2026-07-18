# Internal Review Evidence: WS-ART-001-01

## Chunk

`WS-ART-001-01`: artifact domain and local adapter

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 5574bf59cf1cb86da76749e0cbc529036346fa8a

Reviewed at: 2026-07-12T09:52:26Z

Reviewer run IDs: senior-engineering=019f5412-7b62-7fa3-94a5-e16bc47d538b,delta=019f559c-8426-7c62-b38e-b35b1c45d437; QA/test=019f5412-64d7-7033-ac07-8c75c1e52684,delta=019f559c-89b3-7c21-bf39-17cc84bb5dcc; security/auth=019f5412-87f9-72d3-bc37-c3abc1151a63; product/ops=019f554d-60b0-7321-9412-4fb71eb074f9; architecture=019f5412-5588-7c60-8bd9-da0a2fe46924; CI-integrity=019f554d-6633-7143-9c93-f10b0f565fe3,delta=019f559c-8fc9-7063-aaca-7e45a84b0675; docs=019f554d-6ade-73d0-98ad-76e7d5a0474d; reuse/dedup=019f554d-73a7-7932-bf74-553d421590d6; test-delta=019f5565-2802-7462-b066-d178464cc479,delta=019f559c-9a09-77d1-83d5-882a8faca75e

External-review delta run IDs: senior-engineering=019f55ae-6e9f-7e22-a53e-56e77eebc0dc; QA/test=019f55ae-7143-7933-8189-66f00cbf3a2e; security/auth=019f55ae-7732-7982-9aaf-9424c7ce4605; product/ops=019f55ae-7e81-7640-af5a-d5fb5fee4b3c; architecture=019f55b9-23f9-7da1-9082-4d9cf462e47c; CI-integrity=019f55b9-26cf-7dd2-933e-c39e14cce010; docs=019f55b9-2b16-7361-a6e3-e0c246e1d1db; reuse/dedup=019f55b9-3132-72d0-984d-b2bc934d1421; test-delta=019f55ba-66d8-75b3-bc05-2f4e97e4bfd1

## Reviewed Change

- Added the provider-neutral artifact contract, immutable artifact records,
  upload coordination, recovery, retention, quarantine, and shared audit path.
- Added a private local object-storage adapter with bounded streaming,
  no-follow filesystem handling, atomic publication, durable receipts, and
  deterministic crash recovery.
- Added additive migration `0016`, configuration guards, versioned JSON
  contract fixtures, a phased stale-contract gate, and focused CI coverage.
- Kept public APIs, Flow Node, product cutovers, and later artifact chunks out
  of scope.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Recovery and transaction ownership are explicit and maintainable. |
| QA/test | PASS | None | Fault, replay, migration, and coordinator matrices cover the chunk contract. |
| security/auth | PASS AFTER FIXES | None | Filesystem, identifier, principal, receipt, and quarantine risks were repaired. |
| product/ops | PASS | None | Record separation and audit attribution preserve the intended product boundary. |
| architecture | PASS | None | Provider-neutral port and storage/domain separation match ADR 0013. |
| CI integrity | PASS | None | Global 78 percent floor remains while artifact scope fails below 90 percent. |
| docs | PASS | None | ADR, specification, plan, decisions, and chunk contracts are aligned. |
| reuse/dedup | PASS | None | Shared hashing and audit paths are reused without parallel frameworks. |
| test delta | PASS AFTER FIXES | None | Every seeded 0015 row and unaffected binding/replica column is preserved. |

## Commands Run

```bash
cd backend && .venv/bin/ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
cd backend && pytest -q tests/test_artifacts.py \
  --cov=app.adapters.artifacts --cov=app.interfaces.artifacts \
  --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90
cd backend && pytest -q tests/test_alembic.py tests/test_config.py
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
git diff --check
```

Results: Ruff passed; docstring coverage was 100 percent; 38 artifact tests
passed with 90.26 percent artifact-subsystem coverage; 17 migration/config
tests passed; 36 agent-gate tests passed; all stale, link, loop-memory, and diff
checks passed. Focused reviewer reruns also passed the repaired migration,
coordinator, ambiguous-replay, create-fault, and bounded-I/O cases.

GitHub Backend CI initially exposed a full-suite ordering failure: the artifact
database fixture set the database environment but could reuse a cached Settings
object created by earlier configuration tests. Commit `66729e4` replaced that
duplicate setup with the shared cache-aware `isolated_database_env` fixture.
The exact config-first sequence plus all six coordinator tests then passed (15
tests), and focused senior, QA, CI-integrity, and test-delta reviewers passed the
repair with no findings.

CodeRabbit's valid runtime, migration, contract, schema, and wording findings
were addressed through `5574bf5`. Internal review additionally ensured repeated
cancellation cannot detach database cleanup from the caller-owned session.

The repository-wide suite is intentionally not duplicated in this worktree
while the separately authorized WS-QUAL agent runs that proof. GitHub Backend
CI remains the fail-closed current-head global-coverage authority for this PR.

## Findings Addressed

- Ambiguous provider outcomes now require replay unless both expected digest
  and size were persisted after confirmed provider success.
- Cancellation, receipt corruption, missing intent/object, and ready-content
  integrity paths now fail closed with bounded recovery and audit evidence.
- Migration proof now compares every column of representative populated 0015
  project, guide, policy, task, submission, and checker rows and promotes none.
- Coordinator tests prove exact row/object/audit counts and byte-for-byte
  preservation of unaffected bindings and replicas.
- Adapter tests now prove bounded read/write slices and deterministic create,
  open, write, fsync, publish, metadata, receipt, verify, and quarantine faults.

## Remaining Risks

- Local storage is development-only and deliberately rejected in production.
- Flow Node adapter behavior and reconciliation against a remote provider remain
  owned by inactive chunk `WS-ART-001-02`.
- Public artifact APIs and product cutovers remain blocked on their named later
  chunks and authorization dependencies.

## Stop Condition

Publish this chunk for external and human review, then stop. Do not start
`WS-ART-001-02` and do not merge without explicit user approval.
