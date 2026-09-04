# Chunk Contract: WS-AUTH-001-03 - Legacy Actor Classification Preflight

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Provide the supported, versioned, dry-run-first workflow that classifies every
legacy actor identity before canonical actor migration without inference or
manual SQL.

## Why this chunk exists

Current rows have issuer and subject but no trustworthy `subject_kind`.
Migration cannot safely guess human versus service.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/actors/legacy_classification.py
backend/scripts/legacy_actor_classification.py
backend/tests/test_actor_legacy_classification.py
backend/tests/test_actors.py
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
database schema migration
actor/profile persistence changes
authority grants
classification inferred from email, subject syntax, token roles, or profiles
writing production data without an explicit apply operation
```

## Acceptance criteria

- Manifest schema is versioned JSON with exact legacy actor ID, canonical
  issuer, opaque subject, and `subject_kind`.
- Unknown fields/kinds, invalid UUIDs, duplicate actor or issuer/subject,
  mismatches, missing database rows, and stale extra rows are rejected.
- Dry-run is the default and produces a checksum-bound, privacy-bounded report.
- The tool emits one canonical immutable envelope to an operator-selected path
  outside the repository. The envelope contains schema version, sorted actor
  classifications, source row-set SHA-256, manifest SHA-256, generated-at, and
  a non-secret database binding identifier.
- The row-set digest covers the complete sorted legacy identity projection
  needed by migration. Any row change after export changes the digest.
- Alembic later locates the envelope only through
  `WORKSTREAM_LEGACY_ACTOR_CLASSIFICATION_FILE`, verifies canonical checksum,
  recomputes the live row-set digest inside the migration transaction, and
  aborts on TOCTOU mismatch, missing/extra rows, or database-binding mismatch.
- Envelope generation is deterministic and idempotent and never writes grants
  or actor state.
- Empty registries need no manifest and produce an explicit empty proof.
- Runbook defines owner, secure manifest custody, dry-run/export sequence,
  evidence retention, environment-specific secure path, Alembic handoff,
  failure recovery, rollback boundary, and post-migration deletion of the
  classification file after its checksum/version are recorded durably.
- Tests prove deterministic output and fail-closed mismatch behavior.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review that classification is explicit, complete, checksum-bound,
privacy-bounded, and unusable as a grant or ad hoc migration bypass.

## Stop conditions

Stop if any existing subject kind must be inferred or if the only workable path
requires manual SQL or production identity-provider payloads.

## Activation

The user explicitly started this chunk after PR #107 merged as `060b780` on
2026-07-13. L1 preimplementation plan review returned PASS WITH CONDITIONS; the
conditions require strict Pydantic 2 schema-version-one models, canonical UUIDv5
derivation, complete envelope checksums, privacy-bounded failures, read-only
repeatable-read proof, crash-safe no-overwrite publication, and focused
subsystem coverage of at least 90 percent while preserving the global baseline.

## Implementation review status

Original implementation SHA `8e2ae489834a3934d6ef507834139a1009dac2e6`
and prior reviewed lifecycle revision `a70b89c91a8950eabaa750e340d4f853529d66f0`
passed the required internal reviews. External repair implementation
`4923b677f0a928d77792084c3edc4569b8c28e7b` preserves the primary CLI failure
when engine cleanup also fails and passed fresh internal review. Focused
isolated-PostgreSQL behavior proof is 60 passing tests with 92 percent
combined statement coverage for the classifier and CLI; the pure repair matrix
is 59 passing tests at 90.12 percent combined coverage. The isolated
database-runner lifecycle suite passes 16/16. Backend, Agent Gates, and
CodeRabbit passed on final branch head `43ffbfe`; explicit human approval then
merged PR #109 to `main` as `f06532e` on 2026-07-13. Post-merge memory is the
current gate; AUTH-04 remains inactive pending its separate explicit start.
