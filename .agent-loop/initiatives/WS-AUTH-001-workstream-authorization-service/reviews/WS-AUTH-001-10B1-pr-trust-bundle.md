# WS-AUTH-001-10B1 PR Trust Bundle

## Chunk

`WS-AUTH-001-10B1` — Authorization Read Rate Control

Merge intent: `.agent-loop/merge-intents/WS-AUTH-001-10B1.json`

## Goal and approved boundary

Provide durable, cross-replica abuse control before privacy-sensitive project
role reads are exposed. This chunk only prepares the shared control; 10B2 owns
route attachment, disclosure, concealment, cursors, and action activation.

## What changed

- Migration `0032_authorization_read_rate` safely adds one closed counter scope.
- Existing privacy-safe HMAC framing, PostgreSQL time, repository, and committed
  independent session remain the only rate-control implementation.
- Dedicated bounded limit/window settings and one unattached FastAPI dependency
  are added.
- Operations/spec documentation covers rollout, rollback, drift refusal,
  recovery, 429/Retry-After, private 503, and secret separation.
- GitHub receives one additive 90 percent API-controls coverage report while
  the repository-wide 78 percent and every existing subsystem gate remain.

## Evidence and review

Exact code commit `8ceb4e16d8e152572c94ad3032d8a2edc2cea55e`
passed all nine required internal tracks against trusted main `1473f7a0`.
Focused PostgreSQL, dependency, migration, concurrency, Ruff, Agent Gates,
stale-doc, Markdown-link, and diff-integrity checks pass. Full sharded tests and
coverage run in GitHub Actions because the local full suite takes hours.

The first GitHub run exposed three stale tests that still named `0031` as
current head. The first repair updated those expectations to `0032`. Run
`29875491247` then proved a multi-step refusal in `0031` rolls back the
preceding `0032` step too and retains `0032`; the second repair updates only
those two refusal-state expectations. The successful direct downgrade to
`0031` remains asserted. A fresh isolated three-test sequence passed and all
nine tracks re-reviewed exact code SHA `8ceb4e16`. A new hosted rerun remains
required.

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
