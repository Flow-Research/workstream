# PR Trust Bundle: WS-AUTH-001-03

## Chunk

`WS-AUTH-001-03` - Legacy Actor Classification Preflight

## Goal

Provide the supported, explicit, dry-run-first evidence workflow that classifies
every legacy actor identity before canonical actor migration without inference,
manual SQL, grants, or actor-state mutation.

## Human-Approved Intent

The user explicitly started AUTH-03 after PR #107 merged AUTH-02 as `060b780`.
This PR implements only the existing AUTH-03 contract. Coverage work remains
independent, and AUTH-04 remains inactive pending a separate post-merge start.

## What Changed

- Added strict version-one manifest, live-row, envelope, report, and stable
  failure contracts.
- Added a read-only repeatable-read PostgreSQL snapshot over the fixed legacy
  identity projection.
- Added deterministic canonical checksums and a future migration verifier.
- Added a dry-run-first CLI with private, atomic, immutable envelope export.
- Preserved the primary CLI failure and exit code when engine cleanup also
  fails.
- Added adversarial file, JSON, UUID, mismatch, TOCTOU, concurrency, privacy,
  and CLI behavior tests.
- Expanded the authorization operations runbook and reconciled AUTH loop memory.

## Why It Changed

Existing actor registry rows have issuer and opaque subject but no trustworthy
subject kind. The later canonical actor migration must fail closed rather than
guessing whether a legacy identity is human or an internal service.

## Design Chosen

An operator-owned strict JSON manifest binds each exact legacy UUIDv5, HTTPS
issuer, case-sensitive subject, and `human` or `service` kind. One read-only
repeatable-read snapshot verifies completeness and exact identity, then binds a
canonical confidential envelope to the live row set, manifest, database, UTC
generated-at value, and its complete contents. Publication uses an owner-only
directory, mode `0600`, temp-file `fsync`, atomic no-overwrite link, directory
`fsync`, and rollback on post-link durability failure.

Pure envelope loading and verification remain independent from the mutable
actor ORM so the future synchronous Alembic migration can reuse them. That
migration will accept the file only through
`WORKSTREAM_LEGACY_ACTOR_CLASSIFICATION_FILE` and must recompute live bindings
inside its transaction.

## Alternatives Rejected

- Inferring kind from email, issuer subject syntax, token roles, or profiles.
- Converting legacy profile rows into grants.
- Manual SQL classification or an ad hoc migration bypass.
- Persisting staged classifications in current actor state.
- Importing the live actor ORM into the migration evidence boundary.
- Writing confidential evidence inside any Git worktree.

## Scope Control

The diff is limited to the contract-approved classifier module, CLI, focused
tests, actor database test, authorization runbook, and durable AUTH loop memory.
There is no schema, Alembic, dependency, CI, grant, role, actor-state, API,
product lifecycle, frontend, review, payment, or later AUTH implementation.

## Product Behavior

This chunk adds no public API and grants no authority. Operators receive a
privacy-bounded dry-run report by default. Non-empty registries require a
complete exact manifest. Empty registries produce explicit empty proof. Export
is explicit, confidential, canonical, owner-only, and no-overwrite.

## Acceptance Criteria Proof

Tests cover strict/duplicate/oversized/non-finite JSON, supported kinds,
canonical UUIDv5 derivation, exact issuer/subject matching, missing/stale/extra
rows, deterministic hashes, complete envelope checksum, database drift,
TOCTOU, empty proof, canonical bytes, permissions/ownership, main and linked
worktrees, symlinks, idempotence, link and `fsync` failures, environment-only
handoff, cleanup redaction, migration import independence, and real PostgreSQL
snapshot isolation under a concurrent commit.

## Tests And Checks

- 60 repaired focused behavior tests passed against isolated PostgreSQL.
- New classifier plus CLI coverage is 92 percent combined.
- Repository-wide Ruff, stale wording, stale authorization docs, Markdown
  links, docstring coverage, and `git diff --check` pass.
- The isolated-runner lifecycle rerun passed 16/16 tests.
- The unchanged GitHub Backend CI `--cov-fail-under=78` gate will provide the
  repository-wide coverage and complete-suite evidence before merge.

## Test Delta

No tests were deleted, skipped, xfailed, or weakened. The changed actor test
uses real PostgreSQL and proves read-only repeatable-read state plus concurrent
snapshot stability. File and CLI tests exercise observable failure behavior,
not execution-only coverage lines.

## CI Integrity

No workflow, dependency, package script, threshold, exclusion, or bypass
changed. Focused coverage exceeds 90 percent. Repository-wide coverage remains
enforced at the unchanged 78 percent CI floor while the separate coverage
initiative raises that floor toward the authoritative 90 percent target.

## Reviewer Results

All required tracks pass reviewed code SHA
`8c5334c1635694689ef4a7fb11c572bd6a871e09`. Original implementation
`8e2ae48` supplies the classifier foundation; merge integration `0ae502b`
incorporates PR #108; prior lifecycle head `a70b89c` resolves its conflicts;
and external repair `4923b67` preserves primary CLI failures across cleanup
failure. Engineering, security, QA, test-delta, CI, product, docs, architecture,
and reuse re-review passed with no remaining findings.

## External Review

Ready PR #109 is open at
`https://github.com/Flow-Research/workstream/pull/109`. Local Agent Gates pass;
rerun GitHub Backend CI, CodeRabbit, and explicit human review are pending.

## Remaining Risks

- Database binding is a same-cluster guard, not a globally unique environment
  identity; clone/restore/recreation requires fresh evidence.
- Production classifications remain operator inputs from authoritative issuer
  evidence and are not available or required for deterministic implementation.
- The later migration must still consume and reverify this envelope; AUTH-03
  does not alter schema or actor state.

## Follow-Up Work

AUTH-04 remains inactive. The future actor migration consumes this preflight in
its owning reviewed chunk. Confidential manifest/envelope deletion follows the
durable migration-record and rollback-window procedure in the runbook.

## Human Review Focus

Inspect absence of inference, exact UUIDv5/issuer/subject matching, complete
row-set and envelope checksums, owner-only custody, every-worktree exclusion,
snapshot/TOCTOU behavior, future migration independence, and absence of grants
or database writes.

## Human Merge Ownership

Only the user may approve and merge this PR. PR publication is not merge
approval, and AUTH-04 must not start automatically.
