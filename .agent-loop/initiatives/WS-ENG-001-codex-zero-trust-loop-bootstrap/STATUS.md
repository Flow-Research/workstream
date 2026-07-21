# STATUS: WS-ENG-001

## Current

- `WS-ENG-001-01`: merged through PR #23 on 2026-06-20; complete
- `WS-ENG-001-02`: merged through PR #122 as `fc89fb6`; complete
- `WS-ENG-001-03`: corrective schema-v2 contract for initiative-local next gates
- `WS-ENG-001-04A`: merged through PR #161; signed replay and complete
  projections passed
- `WS-ENG-001-04B`: implementation approved; signed event reducer, protected
  workflow, cutover inventory, tests, CI coverage gates, operations policy, and
  all nine exact-SHA reviewer tracks pass at `26aca951`
- Current gate: push the repaired evidence head to open PR #165, then obtain
  fresh hosted checks, CodeRabbit re-review, and any renewed human approval
  required by branch policy before explicit user merge authority
- Product runtime: unchanged

## Last Update

The first live generated state proved signing, protected-main freshness, and
workflow isolation, but exposed that schema v1 allowed `WS-ENG-001-02` to name
`WS-AUTH-001-06` as a global next chunk. The corrective chunk makes successor
authority initiative-local, rejects schema v1 without compatibility, and
rebootstraps generated state at schema v2. No artifact, authorization, or other
Workstream product runtime is active in this engineering chunk.

## Next Required Event

Push the repaired evidence head to PR #165, obtain fresh hosted and CodeRabbit
results plus any policy-required renewed approval, and stop for explicit user
merge authority. Do not begin another chunk.
