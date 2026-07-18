# PR Trust Bundle: WS-ENG-001-03

## Chunk

`WS-ENG-001-03` - Initiative-Local Loop Gates

Merge intent: `.agent-loop/merge-intents/WS-ENG-001-03.json`

## Goal

Prevent one merged initiative from selecting another initiative's next chunk,
make schema-v2 generated memory fail closed, and bind replay to current
protected `main` without changing Workstream product behavior.

## Human-Approved Intent

The user approved an end-to-end correction after the first live generated state
exposed a cross-initiative next pointer. Global initiative priority remains a
human decision; this merge intent records a null successor.

## What Changed

- Added strict schema-v2 intent, record, ledger, rendering, and signature-domain
  validation with no schema-v1 compatibility path.
- Bound non-null successors to one canonical same-initiative Markdown contract
  and reject every foreign matching contract locally and at reviewed head.
- Bound replay to current protected `main`, with stale dispatch rejection and
  first-parent-only queued-push reconciliation.
- Scoped workflow credentials and signing material, preserved a fixed generated
  branch target, and reconciled stale authored state for merged PRs.
- Added 71 deterministic gate tests and exact PR-template contract parity.

## Scope Control

Only approved engineering-loop, workflow, policy, template, script, test, and
documentation files changed. No product runtime, database, dependency, or gate
threshold changed.

## Product Behavior

- [x] No Workstream product behavior changed.

## Evidence

- Internal evidence: `WS-ENG-001-03-internal-review-evidence.md`
- 71 agent-gate tests passed.
- Both changed loop-memory modules have 94 percent branch coverage.
- Merge-intent, stale-state, stale-wording, auth-doc, artifact-contract,
  Markdown-link, compilation, and diff checks passed.

## Internal Reviewer Results

All required senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test-delta tracks passed on
reviewed SHA `27302401f5bcb1134241808b5f9afa57fa4ab1ad`. Every reviewer session
is closed and every valid prior finding is repaired.

## External Review

GitHub Actions and CodeRabbit are pending PR publication. Their results belong
in a separate external-review response; they do not replace internal evidence.

## Remaining Risks

The first schema-v2 post-merge workflow execution occurs only after this PR is
merged. The workflow fails closed on stale targets, malformed state, signature
failure, missing checks, ambiguous successor contracts, or unexpected history.

## Human Review Focus

- Confirm a merge intent cannot select a chunk from another initiative.
- Confirm schema v1 has no executable acceptance or migration path.
- Confirm only trusted `main` workflow code receives write/signing capability.
- Confirm the workflow writes only signed state to `automation/loop-memory`.
- Confirm AUTH-06 and ART-02A1 remain inactive until separate explicit starts.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] I explicitly approve this specific PR for merge.
