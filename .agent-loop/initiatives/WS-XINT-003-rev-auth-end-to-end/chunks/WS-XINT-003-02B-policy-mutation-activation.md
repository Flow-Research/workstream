# Chunk Contract: WS-XINT-003-02B — Policy Mutation Activation

## Status

Planning skeleton. Refresh only after 02A merges; do not start automatically.

## Goal

Expose the sole review/revision policy writer and activate exactly
`project.review_policy.update` and `project.revision_policy.update` through the
existing opaque, transaction-bound PREP protocol.

## Required boundary

- `ProjectPolicyMutationService` is the sole orchestration path.
- `ProjectRepository.add_review_policy_version()` and
  `add_revision_policy_version()` are the only policy-table writers.
- A replay-only repository may touch only the idempotency ledger.
- Exact committed replay returns the recorded response without new PREP,
  policy write, or allowed evidence, including after later grant/link
  revocation. Changed or pending replay conflicts without product state.
- Final PREP consumption follows locks on the exact project, draft guide,
  selected current policy, reserved replacement identity, actor/link/grant,
  operation, request digest, session, and transaction.
- New versions persist actor, identity link, matched grant, project scope,
  ActionId, decision-event reference, predecessor identity/digest, generation,
  and canonical policy digest atomically with selection advancement.
- Active/stale guide, stale selected policy, revoked authority, copied/wrong
  handle, wrong actor/action/project/guide/policy, replay, and crossed
  replacement races fail with no partial policy or audit state.
- No review lifecycle ActionId or behavior is activated.

## Risk, review, and stop

L1. Exact files and commands must be refreshed from post-02A main. Require all
L1 reviewers, hosted full coverage, CodeRabbit, and human merge. Merge and stop
before 03A.
