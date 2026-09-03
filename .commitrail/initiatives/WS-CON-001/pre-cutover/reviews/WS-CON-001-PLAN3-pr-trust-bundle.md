# Workstream PR Trust Bundle: WS-CON-001-PLAN3

## Chunk

`WS-CON-001-PLAN3` - AUTH And REV Current-Main Reconciliation.

Merge intent: `.agent-loop/merge-intents/WS-CON-001-PLAN3.json`

## Goal

Reconcile the contribution and compensation plan with trusted `main` at merged
REV PR #128 (`0302bcf`), which contains AUTH-09A after AUTH PR #140, before any
CON runtime implementation begins.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/INTENT.md`
- Chunk contract: `.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-PLAN3-auth-pr140-reconciliation.md`

- The current compensation-policy model completely supersedes the retired
  policy model; no compatibility path returns.
- The v0.1 accept path is `Review(accept) -> FinalAcceptance ->
  accepted_submission` with no adjudication lifecycle.
- REV owns Review and FinalAcceptance orchestration and the single transaction;
  CON is a mandatory flush-only contribution/award participant.
- AUTH owns identifiers, grants, evaluator integration, ActionOwner custody,
  evidence, and activation. CON must validate upstream planning rather than
  copy speculative identifiers.
- Pull and reconcile merged AUTH work before publishing this plan; do not start
  CON runtime work automatically.
- Consume merged REV's exact FinalAcceptance shape, two-operation CON
  participant, initiative interleaving, and sole joint release-control contract.

## What Changed

- Rebased CON authorization assumptions on AUTH PR #140 and AUTH-09A's current
  runtime catalogue while preserving PR #139 as the underlying boundary.
- Replaced the older prepared-authorization description with the exact opaque,
  single-use handle binding and authority-first lock protocol.
- Corrected `task.claim`: only its stable PermissionId exists; no task-claim
  ActionId is registered.
- Ordered task work as AUTH-10/PREP and the task seam, then CON-05A hidden
  policy freeze plus task composition, then AUTH-13 enumeration, registration,
  evaluator integration, and activation.
- Preserved planned `review.claim` and `review.decision` actions and their
  dependency on hidden CON participants, REV composition, and later AUTH
  activation.
- Replaced the obsolete nullable omnibus review participant with reviewer and
  accept-only submitter operations at REV's exact lifecycle points.
- Adopted REV's canonical FinalAcceptance field names and exact REV/CON chunk
  interleaving.
- Made REV-12A the sole joint release controller/fence and specified CON's
  root-ordinal, maximum-ordinal, drain, dispatch, callback, and writer hooks.
- Removed speculative `AUTH_CON_*` ActionOwner candidates. The 22 CON surface
  mappings remain unregistered, non-final proposals.
- Added the reviewed PLAN3 contract and one schema-v2 merge intent naming
  `WS-CON-001-01` as the same-initiative successor with an explicit start gate.

## Why It Changed

Treating a PermissionId as an existing ActionId would invert the safe rollout:
AUTH could activate task claim before the assignment captured its immutable
contribution-policy version. The corrected order keeps the feature unavailable
until hidden behavior and rollback proof are merged.

## Design Chosen

AUTH locks current actor/link/exact-grant authority first and prepares one
opaque handle bound to session, ActionId, actor-reference kind/reference,
idempotency key, and canonical request digest. The feature then locks product
rows and recomposes final facts. AUTH consumes the handle, evaluates once, and
stages evidence. Participants flush only and the owning request/command commits
once. A failed substitution attempt does not consume an otherwise valid handle.

ServiceIdentity, static-matrix membership, and action availability are
code-owned validations, not database lock targets. No AUTH persistence, grant
query, evaluator, identifier registration, or availability writer moves into
CON.

FinalAcceptance remains an internal REV-derived fact with canonical
`submission_id`, `recorded_by`, and `policy_context_ref`, no public API, and no
separate authorization action. The mandatory CON participant receives a
reviewer operation before the branch and, only for accept, a submitter operation
after FinalAcceptance and accepted Task/Assignment effects. No adjudication
policy, state, action, queue, lease, contribution, or release dependency is
added.

REV owns the sole `JointLifecycleReleaseControl` and
`JointLifecycleMutationFence`. CON fences every fulfillment-obligation root
creation/requeue/successor/repair writer before immutable monotonic ordinal
allocation. Delivery-draining completion is limited to same-generation roots
at or below the persisted cutoff; provider I/O occurs outside the transaction
and fence.

## Alternatives Rejected

- Activating task claim before CON-05A: rejected because assignment policy
  lineage would not be guaranteed.
- Treating `task.claim` as an existing ActionId: rejected by runtime catalogue
  evidence.
- Retaining `AUTH_CON_*` planning labels: rejected because PR #140 approves no
  such ActionOwner values.
- Giving CON an authorization evaluator or commit: rejected because those
  responsibilities remain AUTH- and request-owned.
- Adding a FinalAcceptance action or adjudication branch: rejected by the
  approved v0.1 lifecycle.

## Scope Control

### Allowed Files Changed

- Sixteen active WS-CON future chunk contracts.
- CON-09B moved from `chunks/` to `deferred/` as one non-executable proposal.
- PLAN3 contract, STATUS, RUNTIME_VERIFICATION, trust bundle, and external
  response under the WS-CON initiative.
- Root `.agent-loop/REVIEW_LOG.md` for the required durable external-review
  record.
- No merge-intent content changed; the cumulative PR still contains exactly one
  existing PLAN3 schema-v2 merge intent.

### Files Outside Contract

- None. The user-owned archival PDF deletion is unstaged and excluded.

The current-main reconciliation changes 22 planning/merge-intent files with 429
insertions and 178 deletions. It changes no backend, migration, test, workflow,
script, dependency, runtime catalogue, or active product document. Before the
final evidence rebind, the full planning branch is 69 files with 8,874
insertions and 90 deletions against `origin/main`; most of that delta is the original reference
transcription and durable planning/review record.

The circuit-breaker passed with a documentation-only size exception: the branch
is one coherent specification initiative, its runtime boundary is empty, and
the earlier planning snapshots retain their own review evidence. The user-owned
deletion of the archival CON PDF is unstaged and excluded.

The PR #142 external-review repair has 24 changed-path entries relative to the
pre-review head: 16 active chunk contracts; the old/new paths for one CON-09B
move; PLAN3, STATUS, RUNTIME_VERIFICATION, trust bundle, external-response log,
and root REVIEW_LOG. It adds no runtime, AUTH/REV/ART-owned, workflow,
dependency, migration, test, or merge-intent content change. The repair makes
verification executable and preserves upstream AUTH ownership rather than
changing product behavior.

## Product Behavior

- [x] No Workstream product behavior changed.
- [ ] Product behavior changed and is explained here.

This PR changes planning, lifecycle wording, future chunk contracts, and review
evidence only. It adds no runtime route, model, migration, action, permission,
grant, worker, provider call, or activation.

## Evidence

### Commands Run

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_loop_memory_state.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --check
```

### Result Summary

```text
Markdown link check: PASS (60 changed Markdown files before final evidence refresh)
Stale Workstream wording: PASS
Stale authorization documentation: PASS
Stale artifact contracts: PASS at foundation phase
Loop-memory state: PASS
Agent gates: PASS (80 tests)
External-review repair diff check: PASS
Working-tree diff check: PASS
External-review repair backend/.github/scripts delta: none
Merge-intent schema-v2 validation: PASS
Local roadmap workbook: not present, so no sheet-export check applies
```

## Acceptance Criteria Proof

- Runtime catalogue verified at 74 PermissionIds and 65 ActionIds: nine active,
  56 planned, no CON-specific ActionId, and no task-claim ActionId.
- Prepared-handle wording matches merged AUTH PR #140.
- The task and review activation sequences explicitly require hidden feature
  behavior before AUTH-only activation.
- Reviewer and submitter contribution lineage remains Review and
  FinalAcceptance respectively, inside the REV-owned transaction.
- FinalAcceptance names and CON operation ordering match merged REV PR #128.
- One shared release controller/fence, monotonic root ordinal, cutoff capture,
  and same-generation at-or-below-cutoff completion match REV-12A.
- The 22 CON mappings are explicitly unregistered/non-final; only the two
  proposed service PermissionIds remain identified as proposals.
- Merge-intent validation passes for successor `WS-CON-001-01`.
- Every CodeRabbit contract finding is dispositioned without moving AUTH-owned
  registration, evaluation, or activation into CON.
- Sixteen active future chunks name runnable focused commands, non-empty test
  selection, repository coverage 78, focused coverage 90, and explicit pass
  criteria.
- Optional CON-09B is a zero-file deferred proposal until a separately approved
  replacement contract closes then-current ART/AUTH disclosure scope.

## Test Delta

### Tests Added

- None; this planning repair defines mandatory commands for future chunks.

### Tests Modified

- None.

### Tests Removed Or Skipped

- None.

## Internal Reviewer Results

Reviewed code SHA: a69fad3a32ad47e3bd60a79cd75f5867eefc52b3

Reviewed at: 2026-07-17T18:14:54Z

Reviewer run IDs: auth08_arch_review/final-a69fad3, auth08_qa_product_review/final-a69fad3, auth08_security_review/final-a69fad3

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS AFTER FIXES | None | Scope, executable gates, deferred proposal, and durable review record pass. |
| QA/test | PASS AFTER FIXES | None | Selectors, migrations, rollback/races, 08B scope, and coverage criteria pass. |
| Security/auth | PASS AFTER FIXES | None | AUTH ownership/order, fail-closed checks, 09B whitelist, and trust controls pass. |
| Product/ops | PASS AFTER FIXES | None | No contribution, compensation, review, or release behavior changed. |
| Architecture | PASS AFTER FIXES | None | Boundaries and future chunk ordering remain coherent. |
| CI integrity | PASS AFTER FIXES | None | No CI/test/runtime delta or threshold/bypass weakening. |
| Docs | PASS AFTER FIXES | None | PR template, external response, scope, review log, and provenance pass. |
| Reuse/dedup | PASS | None | Existing runtime-verification and AUTH/REV contracts are reused. |
| Test delta | PASS | None | No tests changed; 80 agent-gate tests pass. |

The final repair results are rebound in
`WS-CON-001-PLAN3-internal-review-evidence.md` without changing reviewed
planning content after exact-SHA review.

## External Review

External review response file:

- `.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/reviews/WS-CON-001-PLAN3-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Addressed locally; push pending | Five consolidated threads and the description warning are repaired. |
| GitHub checks | Pending rerun | Agent Gates and Backend passed before this repair. |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence remains unchanged; no workflow changed.

### Integrity Detail

PLAN3 changes no test or CI file, removes no assertion, skips no test, changes
no threshold, and adds no bypass. Existing agent-gate coverage remains intact.

## Remaining Risks

- Future test selectors must select at least one test and future migration
  placeholders must be replaced by exact reviewed filenames.
- Optional CON-09B could drift unless its fresh contract repeats the separate
  ART/AUTH/human approval gate.

## Follow-Up Work

- AUTH-13 must be refreshed to consume the merged CON-05A/task-composition
  manifest before task-claim registration or activation.
- Future CON actions need complete feature manifests and exact AUTH-owned
  registration/activation contracts; the proposed table is not a registry.
- `review.claim` and `review.decision` remain unavailable until their complete
  REV/CON composition and AUTH gates merge.
- CON-01 remains a separate explicit human start after this planning PR.

## Human Review Focus

Confirm the corrected task-claim ordering, exact prepared-handle contract,
two-operation Review/FinalAcceptance/contribution transaction, canonical
FinalAcceptance names, sole REV-12A release controller/fence, executable future
chunk gates, and upstream-only AUTH registration/activation ownership. Also
confirm that optional CON-09B remains non-executable until fresh approval and
that the cumulative planning PR is acceptable as one coherent specification
record.

## Human Merge Ownership

This bundle authorizes refreshing PR #142, not merging it. The user must
explicitly approve PR #142 for merge. No successor chunk starts automatically.

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
