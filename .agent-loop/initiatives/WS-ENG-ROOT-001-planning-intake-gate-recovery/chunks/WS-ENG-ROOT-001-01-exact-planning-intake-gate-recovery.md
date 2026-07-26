# Chunk Contract: WS-ENG-ROOT-001-01 — Exact Root Planning-Intake Gate Recovery

## Goal

Repair the circular trusted gates that reject the repository's documented
first-new-initiative planning intake, using one exact consumed recovery.

## Risk class

L0

## Start phase

`implementation`

## Machine-checkable scope

```chunk-scope-json
{
  "schema_version": 1,
  "chunk_id": "WS-ENG-ROOT-001-01",
  "phase": "implementation",
  "risk_class": "L0",
  "allowed_paths": [
    ".agent-loop/policies/loop-memory-recovery.json",
    ".agent-loop/initiatives/WS-ENG-ROOT-001-planning-intake-gate-recovery/**",
    ".agent-loop/merge-intents/WS-ENG-ROOT-001-01.json",
    "scripts/check_chunk_contract.py",
    "scripts/check_internal_review_evidence.py",
    "scripts/check_loop_memory_state.py",
    "scripts/update_post_merge_memory.py",
    "scripts/test_agent_gates.py",
    "scripts/test_check_chunk_contract.py",
    "scripts/test_check_loop_memory_state.py",
    "scripts/test_update_post_merge_memory.py"
  ],
  "forbidden_paths": ["backend/**", "frontend/**", ".github/**"],
  "required_reviewers": ["senior engineering", "qa/test", "security/auth", "product/ops", "architecture", "ci integrity", "docs", "reuse/dedup", "test delta"],
  "verification_commands": ["agent-gate-tests", "loop-memory-state", "chunk-scope-tests", "internal-review-evidence", "markdown-links", "stale-wording", "git-diff-check"]
}
```

## Allowed files

```text
.agent-loop/policies/loop-memory-recovery.json
.agent-loop/initiatives/WS-ENG-ROOT-001-planning-intake-gate-recovery/**
.agent-loop/merge-intents/WS-ENG-ROOT-001-01.json
scripts/check_chunk_contract.py
scripts/check_internal_review_evidence.py
scripts/check_loop_memory_state.py
scripts/update_post_merge_memory.py
scripts/test_agent_gates.py
scripts/test_check_chunk_contract.py
scripts/test_check_loop_memory_state.py
scripts/test_update_post_merge_memory.py
```

## Not allowed

```text
product code, backend, frontend, workflows, dependencies, coverage weakening
general unsigned implementation admission or reusable recovery authority
automatic start, merge, approval, cancellation, or AUTH implementation
```

## Acceptance criteria

- [ ] Only a brand-new initiative's additive canonical planning tree and one
      `<initiative>-PLAN` intent can use the restored planning-intake admission.
- [ ] Existing initiatives, implementation/configuration paths, scripts,
      workflows, policies, deletes, renames, links, and executable modes fail.
- [ ] Internal evidence accepts PLAN identity without inventing a PLAN contract,
      while retaining exact reviewed-SHA and all required tracks.
- [ ] Ordinary implementation/specification chunks remain signed-start-only.
- [ ] Schema-v7 recovery is exact to this identity, signed basis, first parent,
      empty recovered list, fixed reason/code, and is consumed on first use.
- [ ] Independent state validation rejects altered recovery evidence.
- [ ] Exactly one null-successor merge intent completes the root repair.

## Verification commands

```bash
python3 scripts/test_check_chunk_contract.py
python3 scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Stop conditions

Stop if the recovery is reusable, changes product code, or admits anything
beyond the closed planning-intake tree.
