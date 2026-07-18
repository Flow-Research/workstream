# PR Trust Bundle

## Chunk

`WS-ART-001-PLAN` - Immutable Artifact Storage And Flow Node Integration
Planning

## Goal

Lock the cross-repository architecture and bounded chunk sequence required for
Workstream to own exact artifact bytes through a local adapter and focused Flow
Node provider before pre-submit/post-submit checker expansion resumes.

## Human-Approved Intent

- Intent: `../INTENT.md`
- Decisions: `../DECISIONS.md`
- Plan: `../PLAN.md`
- Chunk map: `../CHUNK_MAP.md`

## What Changed

- Added ADR 0013 and the canonical artifact storage target specification.
- Added discovery, intent, decisions, risks, plan, status, chunk map, and ten
  implementation chunk contracts across Workstream and Flow Node.
- Updated README/glossary and active loop memory for the planning initiative.
- Added exact failure, migration, concurrency, authorization, retention,
  recovery, provider-contract, and clean-cutover requirements.

## Why It Changed

Current Workstream submissions and guides can record declarations without
owning the referenced bytes. Checkers therefore cannot prove that pre-submit,
post-submit, and later review use the same immutable content. Flow Node has
useful low-level storage primitives, but its current REST path is not yet a
private byte-storage provider boundary.

## Design Chosen

Workstream owns authorization, lifecycle meaning, content identity, immutable
resource bindings, operation intent, and audit. Storage providers own bytes and
provider operation facts. A provider-neutral port supports both private local
development storage and a focused authenticated Flow Node runtime.

## Alternatives Rejected

- Caller URI/hash declarations as truth.
- Artifact bytes in PostgreSQL/Redis/outbox.
- Direct client access to Flow Node in v0.1.
- Flow Node ownership of Workstream product provenance or decisions.
- Receipt-only crash recovery.
- Per-task artifact policy/checker generation.
- Legacy compatibility aliases or fake verified backfills.

## Scope Control

Planning/docs/loop-memory files only. No backend runtime, migration, API,
Celery, Docker, checker, or Flow Node source was implemented in this PR.

## Product Behavior

- [x] No Workstream product runtime behavior changed.
- [x] No Flow Node runtime behavior changed.

## Acceptance Criteria Proof

- [x] Canonical ownership and storage boundary documented.
- [x] Local and Flow Node adapter contracts defined.
- [x] Exact-byte upload, sealing, admission, binding, and recovery defined.
- [x] Security, privacy, retention, release, and failure semantics defined.
- [x] Legacy removal and migration refusal ownership assigned.
- [x] Every implementation chunk has allowed files, exclusions, acceptance
  criteria, verification commands, reviewers, human focus, and stop condition.
- [x] All nine internal reviewer tracks passed the reviewed SHA.

## Tests And Checks Run

```bash
git diff --check main...HEAD
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/test_agent_gates.py
```

All passed; the agent-gate regression suite reported 31 passing tests.

## Test Delta

No product tests were added, changed, removed, skipped, or weakened. This PR is
planning-only. Future chunk contracts explicitly own focused and full-regression
proof.

## CI Integrity

No workflow, dependency, coverage, lint, typecheck, package-script, or checkout
credential setting changed. Future Workstream chunks require CI-equivalent
backend and Agent Gates commands; Flow Node chunks require non-empty dedicated
test targets and live focused-runtime conformance.

## Reviewer Results

Reviewed code SHA: f7fbc339d6e2c806a0a711325a7d3314cd299ef2

All required internal tracks passed: senior engineering, QA/test,
security/auth, product/ops, architecture, docs, CI integrity, reuse/dedup, and
test delta.

Internal evidence:

- `WS-ART-001-PLAN-internal-review-evidence.md`

## External Review

PR #97 received seven actionable CodeRabbit comments. All were fixed and
recorded separately in `WS-ART-001-PLAN-external-review-response.md`; external
review is not internal review evidence. Fresh checks must pass on the pushed
fix/evidence head.

## Remaining Risks

- Runtime behavior is not implemented or proven by this planning PR.
- Production retention/legal-hold, issuer, encryption/backup, and quota values
  still require implementation and deployment approval.
- Cross-repository delivery requires coordinated but independently reviewed
  Workstream and Flow Node PRs.

## Follow-Up Work

After explicit planning merge and a separate start signal, execute only
`WS-ART-001-01`. Do not begin Flow Node or product cutover chunks automatically.

## Human Review Focus

- Workstream versus Flow Node ownership.
- Crash recovery and exact-byte commitment.
- Artifact binding immutability and manifest identity.
- Service authentication, release authority, and private runtime scope.
- Policy/compiler clean cutover and WS-AUTH/WS-REV dependencies.
- Whether each L1 chunk remains independently reviewable.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break during implementation.
- [ ] I accept the remaining planning risks.
- [ ] The user explicitly approved this specific PR for merge.
