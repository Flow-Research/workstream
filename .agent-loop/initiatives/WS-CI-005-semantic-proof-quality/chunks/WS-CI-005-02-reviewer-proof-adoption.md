# Chunk: WS-CI-005-02 Reviewer Proof Candidate Contracts

## Intent

Install candidate test-of-the-test, strict-fake, database/isolation, and
canonical-rule obligations across the existing specialty reviewers. This
chunk proves prompt and contract presence, not behavioral adoption.

## Allowed files

```text
.agents/skills/*-review/SKILL.md
.codex/agents/*-reviewer.toml
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md
.agent-loop/initiatives/WS-CI-005-semantic-proof-quality/**
.agent-loop/CURRENT_STATE.md
scripts/reviewer_contracts.py
scripts/test_reviewer_contracts.py
```

## Not allowed

New reviewer specialties, product/runtime code, workflows, migrations,
repository permissions, or universal fanout requirements.

## Acceptance criteria

- Every reviewer consumes the shared proof model without duplicating it.
- Specialty responsibilities are explicit and non-overlapping.
- QA/test-delta challenge whether tests discriminate behavior.
- Architecture/security cover database and composite ownership where relevant.
- Reuse compares canonical rule representations.
- CI integrity verifies actual infrastructure custody.
- Contract mutation tests fail when any adoption obligation is removed.

## Risk

L1/P1 reviewer behavior.

## Verification

### Acceptance-to-proof map

| Behavior atom | Future implementation | Required future proof | Custody |
|---|---|---|---|
| All nine agent/skill pairs consume the shared proof model | reviewer contracts and matrix | `ReviewerContractTests.test_all_reviewer_contracts_require_shared_proof_quality` | local unit |
| Removing a shared skill obligation fails closed | semantic skill requirements | `ReviewerContractTests.test_each_proof_quality_skill_requirement_is_independently_enforced` | local mutation |
| Removing a shared agent obligation fails closed | semantic agent requirements | `ReviewerContractTests.test_each_proof_quality_agent_requirement_is_independently_enforced` | local mutation |
| QA/test-delta require a discrimination probe | QA/test-delta contracts | `ReviewerContractTests.test_qa_and_test_delta_require_discrimination_probe` | local unit |
| Architecture/security require relevant database-integrity probes | architecture/security contracts | `ReviewerContractTests.test_architecture_and_security_require_database_integrity_probe` | local unit |
| Reuse requires canonical-rule comparison | reuse contracts | `ReviewerContractTests.test_reuse_requires_canonical_rule_comparison` | local unit |
| CI integrity traces actual infrastructure execution custody | CI contracts | `ReviewerContractTests.test_ci_requires_execution_custody_trace` | local unit |
| Docs/product remain proportionate without database ceremony | docs/product contracts | `ReviewerContractTests.test_docs_and_product_contracts_remain_proportionate` | local unit |

All selectors above live in `scripts.test_reviewer_contracts`. The full command
remains:

```bash
python3 -m unittest -v scripts.test_reviewer_contracts
python3 scripts/reviewer_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_review_contracts.py
git diff --check
```

## Required reviewers

All nine existing reviewers, with each reviewing its own contract and adjacent
handoff boundary. No reviewer validates itself as the sole evidence.

## Human review focus

Confirm the prompts remain concise, proportionate, and useful for small changes.

## Merge state

- Outcome on merge: `complete`

Candidate reviewer proof-quality contracts are installed. They are not called
adopted until `WS-CI-005-03` passes independent blind forward evaluation.
