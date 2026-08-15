# Status: WS-CI-004 Review Evidence Integrity

## Current status

Implementing `WS-CI-004-01`.

## Current focus

Land the shared protocol, canonical schema, and read-only target sensor without
changing reviewer-agent behavior or CI.

## Chunk status

| Chunk | Status | Notes |
|---|---|---|
| `WS-CI-004-PLAN` | Planned on merge | Research and contracts only |
| `WS-CI-004-01` | Complete on merge | Protocol, schema, target tool, and focused tests in one PR |
| Proposed step 2 | Not active | Reviewer/skill adoption; no implementation contract exists |
| Proposed step 3 | Not active | Local session convergence; no implementation contract exists |

## Durable current state

Reviewer agents, specialty skills, workflows, product behavior, and GitHub merge
authority remain unchanged. This chunk adds only the shared protocol/schema and
a local read-only target sensor.

## Next action

Human review and merge of `WS-CI-004-01`. Do not start reviewer adoption or
local convergence automatically.
