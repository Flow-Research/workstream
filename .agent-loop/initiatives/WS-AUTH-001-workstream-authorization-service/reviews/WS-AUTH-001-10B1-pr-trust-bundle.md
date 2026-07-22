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

Exact reviewed tree `9b33edea094fa997f03c3a7f7e57ecc9fd20bda8`
with executable-code commit `8ceb4e16d8e152572c94ad3032d8a2edc2cea55e`
passed all nine required internal tracks against trusted main `1473f7a0`.
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
