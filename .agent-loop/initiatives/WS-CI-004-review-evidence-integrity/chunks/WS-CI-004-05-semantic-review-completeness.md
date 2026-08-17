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
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/reviews/WS-CI-004-05-external-review-response.md
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

- [x] Every material criterion is decomposed into atomic observable behaviors,
      including actors, resources/tenants, lifecycle states, failures, and
      forbidden side effects where relevant.
- [x] Every behavior atom maps to its owner, implementation source, named proof,
      and execution custody; missing or narrative-only mappings block PASS.
- [x] Every final review states a residual escape hypothesis and how the reviewer
      attempted to falsify it.
- [x] Architecture, security, QA, test-delta, docs, product/ops, CI, reuse, and
      senior-review skills and agents contain specialty-specific completeness
      probes instead of generic boilerplate alone.
- [x] The canonical receipt schema rejects missing trace rows or residual escape
      analysis, requires all trace rows to be verified for a passing verdict,
      and advances the breaking receipt contract to schema version 2.
- [x] Realistic multi-file evaluation fixtures reproduce the semantic omission
      observed during PR #346 review without leaking the expected answer.
- [x] Session evidence remains advisory and GitHub remains the sole merge authority.

## Completion evidence

| Behavior | Owner | Implementation source | Named proof | Execution custody | Result |
|---|---|---|---|---|---|
| Atomize material criteria | Shared reviewer protocol | `reviewer-evidence-protocol/SKILL.md` and nine specialty agents/skills | `test_all_agent_skill_contracts_compose_with_protocol` plus blind `qa-compound-trace` replay | local deterministic tests and exact-head QA review | verified |
| Trace every atom through owner, implementation, proof and custody | Shared protocol and receipt schema | protocol steps 6-7 and receipt `traceability` | receipt schema tests and reviewer-contract mutation tests | local deterministic tests | verified |
| Require residual escape falsification | Shared protocol and receipt schema | protocol step 8 and receipt `residual_escape` | `test_final_verdict_requires_verified_trace_and_closed_escape` | local deterministic tests | verified |
| Preserve specialty-specific depth | Nine specialty reviewer owners | matching skills and `.codex/agents/*-reviewer.toml` | `scripts/reviewer_contracts.py` and exact-head reviewer fanout | local validation and advisory review sessions | verified |
| Reproduce the PR #346 omission | Evaluation harness | `CASES.json` / `EXPECTATIONS.json` | blind `qa-compound-trace` classification plus fixture validation | isolated QA review and local tests | verified |
| Keep evidence advisory | GitHub authority boundary | receipt `custody`, schema closed fields, contract non-goals | authority-field adversarial schema probe and security review | local deterministic tests and advisory review session | verified |

## Verification commands

```bash
python3 -m unittest -v scripts.test_reviewer_contracts scripts.test_review_target
python3 scripts/reviewer_contracts.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_active_state_projections.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_review_contracts.py
git diff --check
```

## Required reviewers

Architecture, security, QA, test-delta, CI integrity, senior engineering,
reuse/dedup, and documentation.

## Human review focus

Confirm the change forces semantic proof without turning reviewer prose into a
second permission system or adding unnecessary process ceremony.
