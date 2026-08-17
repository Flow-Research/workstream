# Chunk Contract: WS-CI-004-05 — Semantic Review Completeness

## Merge state

- Outcome on merge: `complete`

## Goal

Require reviewers to decompose material requirements into independently
checkable behavior atoms and trace each atom through its owner, implementation,
proof, and execution custody before issuing a passing verdict.

## Why this chunk exists

Exact-head review, impact-cone inspection, and adversarial probes prevent stale
or shallow receipts, but PR #346 demonstrated that a reviewer can still accept
a polished criterion-to-test table while one material behavior has no named
proof. Review must establish semantic completeness, not merely the presence of
a matrix.

## Risk class

L1 — reviewer protocol, skills, agents, evidence schema, and evaluation harness.

## Allowed files

```text
.agents/skills/reviewer-evidence-protocol/SKILL.md
.agents/skills/{architecture-review,security-review,qa-review,test-delta-review,docs-review,product-ops-review,ci-integrity-review,reuse-dedup-review,senior-engineer-review}/SKILL.md
.codex/agents/*-reviewer.toml
.agent-loop/templates/INTERNAL_REVIEW_RECEIPT.schema.json
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/{CHUNK_MAP.md,STATUS.md,REVIEWER_MATRIX.md}
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/chunks/WS-CI-004-05-semantic-review-completeness.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/evaluations/{CASES.json,EXPECTATIONS.json}
.agent-loop/CURRENT_STATE.md
scripts/{reviewer_contracts.py,test_reviewer_contracts.py,test_review_target.py}
```

## Not allowed

```text
backend product/runtime behavior or migrations
hosted or committed exact-head receipt custody
new merge authority, automatic merge, or universal reviewer fanout
coverage, CI, branch-protection, or existing test weakening
```

## Acceptance criteria

- [ ] Every material criterion is decomposed into atomic observable behaviors,
      including actors, resources/tenants, lifecycle states, failures, and
      forbidden side effects where relevant.
- [ ] Every behavior atom maps to its owner, implementation source, named proof,
      and execution custody; missing or narrative-only mappings block PASS.
- [ ] Every final review states a residual escape hypothesis and how the reviewer
      attempted to falsify it.
- [ ] Architecture, security, QA, test-delta, docs, product/ops, CI, reuse, and
      senior-review skills and agents contain specialty-specific completeness
      probes instead of generic boilerplate alone.
- [ ] The canonical receipt schema rejects missing trace rows or residual escape
      analysis, requires all trace rows to be verified for a passing verdict,
      and advances the breaking receipt contract to schema version 2.
- [ ] Realistic multi-file evaluation fixtures reproduce the semantic omission
      observed during PR #346 review without leaking the expected answer.
- [ ] Session evidence remains advisory and GitHub remains the sole merge authority.

## Verification commands

```bash
python3 -m unittest -v scripts.test_reviewer_contracts scripts.test_review_target
python3 scripts/reviewer_contracts.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_active_state_projections.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security, QA, test-delta, CI integrity, senior engineering,
reuse/dedup, and documentation.

## Human review focus

Confirm the change forces semantic proof without turning reviewer prose into a
second permission system or adding unnecessary process ceremony.
