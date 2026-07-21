# WS-ENG-003-01 PR Trust Bundle

## Chunk and goal

`WS-ENG-003-01` recovers canonical loop memory through merged PR #166 and this recovery merge exactly once, without leaving a reusable exemption.

## Human-approved intent

The user instructed the orchestrator to repair the failed post-merge automation immediately. Merge remains explicitly user-owned.

## Changes and design

- Adds a closed certificate for exact PR #166 merge `6445ce62` and activation chunk `WS-ENG-003-01`.
- Before reduction, requires the resolved target to be the final merge in the exact two-merge plan and derives the recovery PR identity through trusted GitHub evidence.
- Supplies each merge only its own exact authorization out of band; recovery entries never enter state or ledger history.
- Blocks signing unless canonical state reaches the exact target and the full validated ledger contains no recovery identity.
- Successful replay has an empty plan and cannot recreate recovery entries; later unstarted merges still fail.

## Scope and product behavior

No product runtime, API, database, dependency, signing key, normal start/cancel behavior, manual state edit, force push, or wildcard exemption.

## Proof, test delta, and CI integrity

- 185 combined tests pass; updater branch coverage is 90.72 percent.
- 94 focused tests and 88 standalone agent-gate tests pass.
- Exact CLI round trip, malformed policy, wrong identity/order/target, collision, partial consumption, ledger leakage, replay, and later enforcement are covered.
- No test, check, permission, or coverage threshold was weakened.

## Reviewer results

All nine required tracks pass reviewed code SHA `a5a0c228`: senior, QA, security, product/ops, architecture, CI integrity, docs, reuse/dedup, and test delta.

## Remaining risks and external review

The recovery plan intentionally fails if another merge lands before this recovery PR. Hosted CI and CodeRabbit remain.

## Human review focus

Review exact certificate identity, target/final-plan binding, out-of-band per-merge authorization, and full-ledger pre-sign leakage assertion.

## Follow-up and human merge ownership

No successor is declared. Only the user may approve and merge this PR.
