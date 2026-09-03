# Internal Review Evidence: WS-ART-001-PLAN

## Chunk

`WS-ART-001-PLAN` - Immutable Artifact Storage And Flow Node Integration
Planning

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: f7fbc339d6e2c806a0a711325a7d3314cd299ef2

Reviewed at: 2026-07-11T23:03:40Z

Reviewer run IDs: senior-engineering=019f5324-6fce-7a73-b92b-8886fbb30fdd; QA/test=019f5324-850d-7140-9e5c-58d1bc2c791e; security/auth=019f5324-7e01-7532-9f7f-943cfc886d4f; product/ops=019f5324-8c78-76d0-ab08-7a8d3f40cd27; architecture=019f5324-7661-72e0-857d-8902ed9da442; docs=019f5324-95e0-7d12-b0d6-5ff0b2ae4418; CI-integrity=019f5347-b88e-7571-a901-5c057d10d232; reuse/dedup=019f5347-bc91-7a42-8ea6-9c8b5e88e82c; test-delta=019f5347-c2c5-7443-aa79-ee656495781d

## Reviewed Change

- Defined Workstream-owned artifact sessions/items, provider-neutral content,
  immutable bindings, replicas, and append-only provider receipts.
- Defined `ArtifactStorePort`, `LocalStorageAdapter`, and `FlowNodeAdapter`
  boundaries without exposing CID/DAG/pin types to Workstream domain logic.
- Defined exact-byte sealing, deterministic artifact-set manifests, pre-submit
  admission input binding, and atomic submission attachment.
- Defined crash recovery that never accepts provider receipts alone and requires
  persisted commitment proof or exact client replay.
- Defined private service authentication, retention/release authorization,
  stable failure meaning, and no contributor blame for provider failures.
- Split delivery into seven Workstream chunks and three Flow Node chunks with
  explicit WS-AUTH and WS-REV dependencies.
- Kept Flow Node and Workstream runtime implementation out of this planning PR.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed recovery, cutover ownership, verification, and operational scope. |
| QA/test | PASS | None | Confirmed migration ownership, race counts, fault phases, and executable commands. |
| security/auth | PASS | None | Confirmed service identity, release scope, privacy, integrity, and no receipt-only trust. |
| product/ops | PASS | None | Confirmed actor boundaries, failure meaning, reviewer deferral, and no payment/reputation effects. |
| architecture | PASS | None | Confirmed upload-item ownership, immutable binding semantics, and provider/domain separation. |
| docs | PASS | None | Confirmed route, manifest, policy, ADR precedence, and loop-memory consistency. |
| CI integrity | PASS | None | Confirmed no workflow weakening and non-empty focused test targets/CI-equivalent commands. |
| reuse/dedup | PASS | None | Confirmed shared audit, canonical hashing, checker retry, and Flow Node primitive reuse. |
| test delta | PASS | None | Confirmed migration, focused runtime, Compose, and safe API-contract proof ownership. |

## Valid Findings Addressed

- Added a per-item upload operation ledger and removed staged-binding ambiguity.
- Made resource bindings immutable and kept staging outside binding records.
- Added deterministic manifest entry identity, total ordering, and duplicate
  rejection.
- Bound pre-submit admission to the exact summary, contributor attestation,
  upload session, task, and artifact-set hash.
- Added exact replay requirements for crash recovery without a persisted byte
  commitment.
- Added distinct destructive `artifact:release` scope and retention-reference,
  legal-hold, audit, and negative authorization proof.
- Assigned the full policy/compiler/project-agent/ADR clean cutover and rejected
  all legacy caller URI/hash/storage-scheme contracts.
- Added Flow Node migration proof, non-empty Cargo test targets, live focused
  conformance, production route inventory, and test-control isolation.
- Added Alembic test ownership, full backend regression commands, clean Compose
  health waits, explicit fault phases, and safe Compose test-database guards.
- Required reuse of shared `AuditRepository` and `canonical_json_hash`.
- Addressed all seven initial CodeRabbit findings and reran all nine internal
  tracks against the external-fix and durable-memory head.

## Commands Run

```bash
git diff --check main...HEAD
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/test_agent_gates.py
```

Results:

- Diff hygiene: passed.
- Stale authorization docs: passed.
- Stale Workstream wording: passed.
- Markdown links: passed for 23 changed Markdown files.
- Loop memory: passed.
- Agent gate regression tests: 31 passed.

## Remaining Risks

- This is planning proof, not runtime or provider proof.
- Each L1 implementation chunk still requires its own migrations, tests,
  internal reviews, external review, and explicit human merge approval.
- Production issuer values, encryption/backups, retention/legal-hold policy, and
  quotas remain implementation/deployment inputs.
- Product cutovers remain blocked on their named WS-AUTH chunks; reviewer
  packet/evidence APIs remain deferred to WS-REV.

## Stop Condition

Do not start `WS-ART-001-01`, edit Flow Node, or resume checker expansion until
this planning PR is externally reviewed, explicitly merged by the user, and the
user gives a separate implementation start signal.
