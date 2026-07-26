# Chunk Contract: WS-ENG-ROOT-001-02 — Exact Root Reconciliation Recovery

## Goal

Preserve the reviewed schema-v7 recovery policy while shared reconciliation
collects PR #205, then consume PR #205 and this repair as one exact sequence.

## Risk class

L0

## Start phase

`implementation`

## Machine-checkable scope

```chunk-scope-json
{
  "schema_version": 1,
  "chunk_id": "WS-ENG-ROOT-001-02",
  "phase": "implementation",
  "risk_class": "L0",
  "allowed_paths": [
    ".agent-loop/policies/loop-memory-recovery.json",
    ".agent-loop/initiatives/WS-ENG-ROOT-001-planning-intake-gate-recovery/**",
    ".agent-loop/merge-intents/WS-ENG-ROOT-001-02.json",
    ".agent-loop/merge-intents/WS-ENG-ROOT-001-01.json",
    "scripts/check_loop_memory_state.py",
    "scripts/check_chunk_contract.py",
    "scripts/update_post_merge_memory.py",
    "scripts/test_agent_gates.py",
    "scripts/test_check_chunk_contract.py",
    "scripts/test_check_loop_memory_state.py",
    "scripts/test_update_post_merge_memory.py"
  ],
  "forbidden_paths": ["backend/**", "frontend/**", ".github/**"],
  "required_reviewers": ["senior engineering", "qa/test", "security/auth", "product/ops", "architecture", "ci integrity", "docs", "reuse/dedup", "test delta"],
  "verification_commands": ["agent-gate-tests", "loop-memory-state", "loop-memory-recovery-tests", "chunk-scope-tests", "internal-review-evidence", "markdown-links", "stale-wording", "git-diff-check"]
}
```

## Allowed files

```text
.agent-loop/policies/loop-memory-recovery.json
.agent-loop/initiatives/WS-ENG-ROOT-001-planning-intake-gate-recovery/**
.agent-loop/merge-intents/WS-ENG-ROOT-001-02.json
.agent-loop/merge-intents/WS-ENG-ROOT-001-01.json
scripts/check_loop_memory_state.py
scripts/check_chunk_contract.py
scripts/update_post_merge_memory.py
scripts/test_agent_gates.py
scripts/test_check_chunk_contract.py
scripts/test_check_loop_memory_state.py
scripts/test_update_post_merge_memory.py
```

## Not allowed

```text
backend/**
frontend/**
.github/**
product behavior, workflow changes, dependencies, reusable recovery authority
```

## Acceptance criteria

- [ ] `reconcile_to_main` recollects schema-v7/v8 recovery merges with the exact
      immutable policy used during preparation.
- [ ] Schema v8 binds signed basis `339248c4`, PR #205 merge `ce512bdb`, this
      activation identity, adjacency, exact paths, null successor, and fixed
      recovery-only evidence.
- [ ] Both exemptions are consumed and neither persists in signed history.
- [ ] Mutation, replay, wrong-order, wrong-parent, and foreign-identity cases fail.
- [ ] No product, workflow, dependency, coverage, start, or authorization behavior changes.

## Verification commands

```bash
python3 scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 scripts/check_loop_memory_state.py
python3 scripts/test_check_chunk_contract.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Required reviewers

- [ ] senior engineering
- [ ] qa/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] ci integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Confirm the authority is exact, adjacent, one-use, and cannot admit a third merge.

## Stop conditions

Stop if the policy becomes reusable, paths widen, checks weaken, or product code changes.
