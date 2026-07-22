# WS-AUTH-001-10B1 PR Trust Bundle

## Chunk

`WS-AUTH-001-10B1` — Authorization Read Rate Control

Merge intent: `.agent-loop/merge-intents/WS-AUTH-001-10B1.json`

## Goal and approved boundary

Provide durable, cross-replica abuse control before privacy-sensitive project
role reads are exposed. This chunk only prepares the shared control; 10B2 owns
route attachment, disclosure, concealment, cursors, and action activation.

## What changed

- Migration `0033_authorization_read_rate` safely adds one closed counter scope.
- Existing privacy-safe HMAC framing, PostgreSQL time, repository, and committed
  independent session remain the only rate-control implementation.
- Dedicated bounded limit/window settings and one unattached FastAPI dependency
  are added.
- Operations/spec documentation covers rollout, rollback, drift refusal,
  recovery, 429/Retry-After, private 503, and secret separation.
- GitHub receives one additive 90 percent API-controls coverage report while
  the repository-wide 78 percent and every existing subsystem gate remain.

## Evidence and review

Exact integrated implementation/docs tree
`2d6d347e1e3f16821218d257ccb29e5e458d4a45`, including integration merge
`3b90fbd7cf3c80c3dcfc199953317492e4ddcd2e`, passed all nine required internal
tracks against trusted main `92b8a7aa813c5914d8191547b62eb3823a37a140`.
Focused PostgreSQL, dependency, migration, concurrency, Ruff, Agent Gates,
stale-doc, Markdown-link, and diff-integrity checks pass. Full sharded tests and
coverage run in GitHub Actions because the local full suite takes hours.

Before the ART merge, the first GitHub run exposed three stale tests that still
named `0031` as current head, and the first repair updated those pre-rebase
expectations to AUTH-owned `0032`. Run `29875491247` then proved a multi-step
refusal rolls back the full migration transaction and retains its starting
head. After ART claimed `0032_artifact_recovery`, AUTH rebased linearly to
`0033_authorization_read_rate`; current-head and refusal-state assertions now
retain `0033`, while successful AUTH downgrade stops at direct predecessor
`0032_artifact_recovery`. The combined lineage/migration suite passes 3/3 on a
fresh isolated database. A new hosted run remains required for the merged tree.
Alembic reports exactly one head: `0033_authorization_read_rate`.

Post-integration CodeRabbit repair `746e577a` strengthens the migration
round-trip to seed and preserve both legacy scopes. Its focused isolated
PostgreSQL 16 test passes, and all nine internal tracks passed the exact
one-file delta. The hosted checks must pass again on the final evidence head.

## Risks and controls

Migration drift fails closed before DDL and leaves revision, constraint, and
rows unchanged. Downgrade locks before refusing any live or expired new-scope
row. The dependency is not attached to production routes, and stored keys never
contain raw issuer, subject, token, actor, grant, or network data.

## Human review focus and merge ownership

Review the exact constraint transition, locked downgrade refusal, old/new scope
isolation, absence of route/action changes, and additive CI coverage gate. The
user retains approval authority for this PR and merge. After merge, automation
records 10B2 as stopped/next; it does not begin automatically.
