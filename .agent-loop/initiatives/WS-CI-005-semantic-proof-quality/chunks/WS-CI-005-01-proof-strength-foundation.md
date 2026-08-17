# Chunk: WS-CI-005-01 Proof-Strength Foundation

## Intent

Add the shared proof vocabulary and deterministic receipt/validator foundation
without changing specialty reviewer prompts yet.

## Allowed files

```text
.agents/skills/reviewer-evidence-protocol/SKILL.md
.agents/skills/reviewer-evidence-protocol/references/proof-quality-patterns.md
.agent-loop/templates/INTERNAL_REVIEW_RECEIPT.schema.json
.agent-loop/templates/INTERNAL_REVIEW_EVIDENCE.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md
.agent-loop/initiatives/WS-CI-005-semantic-proof-quality/**
scripts/reviewer_contracts.py
scripts/test_reviewer_contracts.py
```

## Not allowed

Product/runtime code, migrations, workflows, contributor permission changes,
specialty reviewer agent/skill edits, or hosted receipt custody.

## Acceptance criteria

- Closed proof-strength values are defined once.
- Every receipt trace row declares proof strength and compatibility.
- PASS requires at least one test-of-the-test probe.
- Incompatible or unavailable proof fails closed.
- PR #349 failure patterns live in one concise shared reference.
- Mutation and malformed-output tests cover every new field/rule.

## Risk

L1/P1 reviewer infrastructure.

## Verification

### Acceptance-to-proof map

| Behavior atom | Future implementation | Required future proof | Custody |
|---|---|---|---|
| Only the eight closed proof strengths are accepted | receipt schema and validator | `ReviewerContractTests.test_receipt_rejects_unknown_proof_strength` | local unit |
| Every trace row declares claimed boundary and proof strength | receipt schema | `ReviewerContractTests.test_receipt_requires_boundary_and_strength_per_trace_row` | local unit |
| Compatibility comes from the validator-owned closed matrix | `proof_compatibility_failures` | `ReviewerContractTests.test_reviewer_cannot_self_attest_compatibility` | local unit |
| Service/mock proof cannot satisfy repository, transaction, concurrency, or direct-SQL claims | compatibility matrix | `ReviewerContractTests.test_weaker_proof_cannot_satisfy_infrastructure_claims` | local unit |
| Real isolation proof requires a stored foreign resource | compatibility matrix | `ReviewerContractTests.test_isolation_proof_rejects_missing_row_mock` | local unit |
| Unavailable proof prevents PASS | receipt validator | `ReviewerContractTests.test_unavailable_proof_blocks_pass` | local unit |
| Proof types are not a substitutable strength hierarchy | compatibility matrix | `ReviewerContractTests.test_proof_types_are_not_a_strength_hierarchy` | local unit |
| PASS requires a test-of-the-test probe and observed result | receipt schema and validator | `ReviewerContractTests.test_pass_requires_test_of_the_test_probe` | local unit |
| Shared failure-pattern IDs are complete and unique | shared reference and validator | `ReviewerContractTests.test_failure_pattern_registry_is_complete_and_unique` | local unit |

All selectors above live in `scripts.test_reviewer_contracts`. The full command
remains:

```bash
python3 -m unittest -v scripts.test_reviewer_contracts scripts.test_review_target
python3 scripts/reviewer_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_review_contracts.py
git diff --check
```

## Required reviewers

Architecture, CI integrity, security, QA, test delta, senior engineering,
reuse/dedup, documentation, and product/operations.

## Human review focus

Confirm the taxonomy is minimal, does not infer semantics from filenames, and
does not add contribution or merge authority.

## Outcome on merge

Shared proof-strength structure is available; reviewer adoption remains
unstarted until explicit human direction.
