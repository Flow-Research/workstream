# Chunk Contract: WS-CI-004-03 — Final-Head And Merged-State Closure

## Merge state

- Outcome on merge: `complete`

## Goal

Close the two gaps demonstrated by PR #340: require an independent approval of
the most recent reviewable push, require review conversations to be resolved,
and prevent completed chunk projections from landing temporal `on merge`
wording that becomes stale immediately after merge.

## Why this chunk exists

PR #340 received complete exact-head internal review at `354bdb57`, but a later
test-only push became the merged PR head. GitHub dismissed stale approvals but
did not require approval of the most recent push. The same merge left CP03A and
WS-CI-004-02 described as `complete on merge` on `main`. Both conditions make
otherwise correct evidence misleading.

## Risk class

L1 — repository protection, CI, review integrity, and durable engineering state.

## Allowed files

```text
AGENTS.md
CONTRIBUTING.md
scripts/check_chunk_state_sync.py
scripts/test_chunk_state_sync.py
scripts/check_active_state_projections.py
scripts/test_active_state_projections.py
.github/workflows/agent-gates.yml
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/CHUNK_MAP.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/STATUS.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/chunks/WS-CI-004-03-final-head-state-closure.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/CHUNK_MAP.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/STATUS.md
.agent-loop/initiatives/WS-SEC-001-dependency-alert-remediation/STATUS.md
```

Repository branch-protection settings for `main` are also in scope: preserve
strict `test` and `agent-gates` checks, one approving review, stale-review
dismissal, admin enforcement, and force-push/deletion denial; additionally
require approval of the most recent reviewable push and resolved conversations.

## Not allowed

```text
product/runtime behavior
authentication or authorization behavior
test or coverage weakening
hosted reviewer receipt custody
agent-generated merge authority
automatic merging
additional approval count
workflow duplication
post-merge state-repair automation
```

## Acceptance criteria

- [ ] `main` requires one approving review, dismisses stale approvals, requires
      approval of the most recent reviewable push, and requires conversation
      resolution.
- [ ] Existing strict required checks and destructive-branch protections remain
      unchanged.
- [ ] A completed chunk's chunk-map, initiative-status, and current-state
      projection lines describe the final durable state without `on merge`.
- [ ] The chunk-state gate rejects temporal `on merge` wording in projection
      lines while continuing to require the contract declaration
      `Outcome on merge`.
- [ ] Tests cover chunk-map, initiative-status, and current-state rejection plus
      the valid final-state form.
- [ ] CP03A and WS-CI-004-02 are reconciled to merged state, and WS-CI-004-03
      lands as complete without a follow-up memory PR.
- [ ] No active `CURRENT_STATE.md`, initiative `STATUS.md`, or `CHUNK_MAP.md`
      retains temporal outcome wording from an already merged change.
- [ ] Documentation states that a push invalidates approval/review evidence and
      that another eligible human must approve the latest reviewable push.

## Verification commands

```bash
python3 -m unittest -v scripts.test_chunk_state_sync scripts.test_lightweight_agent_gates
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 -m unittest -v scripts.test_active_state_projections
python3 scripts/check_active_state_projections.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
git diff --check
gh api repos/Flow-Research/workstream/branches/main/protection
```

## Required reviewers

Architecture, CI integrity, security, QA, senior engineering, reuse/dedup, and
documentation. Product/operations confirms engineering review language does
not become Workstream product review state.

## Human review focus

Confirm the GitHub protection change closes the last-push race without adding a
second permission system, and confirm the local gate prevents stale merged-state
language without rewriting historical evidence.
