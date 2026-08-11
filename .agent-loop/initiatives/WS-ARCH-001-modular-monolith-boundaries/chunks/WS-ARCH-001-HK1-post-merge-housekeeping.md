# Chunk Contract: WS-ARCH-001-HK1 Post-Merge Housekeeping

## Goal

Reconcile durable engineering state after PRs #312, #314, and #315 and record
the safe operational cleanup boundary before WS-ARCH-001-02C starts.

## Scope

Documentation and local-worktree housekeeping only. This chunk changes no
runtime behavior, schema, migration, authorization catalogue, test, or CI gate.

## Allowed files

```text
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/**
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/STATUS.md
```

Local operational cleanup may remove only worktree registrations or directories
that are clean, inactive, and fully contained in `origin/main`. Dirty or
unmerged worktrees are inventory only and remain untouched.

## Not allowed

Production or test code; workflows; coverage thresholds; migrations; product
behavior; mass file splitting; deleting a dirty, active, or unmerged worktree;
creating another architecture or test-structure initiative.

## Acceptance criteria

- [x] AUTH-12I is recorded as merged through PR #312.
- [x] WS-ARCH-001-02A and 02B are recorded as merged through PRs #314 and #315.
- [x] WS-ARCH-001-02C is the sole immediate implementation boundary.
- [x] POL-03B is recorded as eligible after merged AUTH-12I.
- [x] Dirty and unmerged worktrees are preserved.
- [x] Safe cleanup requires clean state, merged ancestry, and no active process.
- [x] Incremental capability-sized code and test recovery remains explicit.

## Risk and reviewers

Risk: L2 documentation/operations reconciliation. Required review: architecture,
docs, and senior engineering. CI integrity review is required if any workflow,
test command, or threshold unexpectedly changes.

## Verification

```bash
python3 scripts/check_markdown_links.py
rg -n "12I implemented pending review|12I.*not merged|02A only|02B.*Proposed" \
  --glob '!**/WS-ARCH-001-HK1-post-merge-housekeeping.md' \
  .agent-loop/CURRENT_STATE.md \
  .agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries \
  .agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service \
  .agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation
git diff --check
```

## Human review focus

Confirm the records describe merged behavior, do not turn planning into
authorization, and preserve all worktrees containing unique or uncommitted work.
