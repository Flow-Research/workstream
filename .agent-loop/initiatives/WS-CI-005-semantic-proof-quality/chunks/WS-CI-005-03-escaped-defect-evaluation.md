# Chunk: WS-CI-005-03 Escaped-Defect Evaluation

## Intent

Prove the improved reviewer system detects the real failure classes that escaped
earlier review, establish behavioral adoption, and integrate concise results
into evidence/trust workflows.

## Allowed files

```text
.agents/skills/evidence-gate/SKILL.md
.agents/skills/pr-trust-bundle/SKILL.md
.agents/skills/task-chunk-loop/SKILL.md
.agents/skills/*-review/SKILL.md
.codex/agents/*-reviewer.toml
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/evaluations/**
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md
.agent-loop/initiatives/WS-CI-005-semantic-proof-quality/**
scripts/reviewer_contracts.py
scripts/test_reviewer_contracts.py
.github/workflows/agent-gates.yml
```

## Not allowed

Product/runtime code, hosted AI review gates, secrets, automatic approval/merge,
or using evaluation outcomes as contribution authority.

## Acceptance criteria

- Raw fixtures cover every recorded PR #349 escape without expected-answer
  leakage.
- Matching negative controls prevent universal over-flagging.
- Every reviewer has at least one defect/handoff case and one close clear
  control; changing all of one reviewer's results to findings fails validation.
- Raw fixtures include malicious embedded instructions; reviewers ignore them,
  do not execute supplied commands, and report the underlying evidence only.
- Removing untrusted-evidence fixture coverage fails deterministic validation.
- Each applicable reviewer detects or correctly hands off its owned defects.
- Output validation rejects a PASS backed by incompatible proof.
- Evidence and trust-bundle skills summarize proof quality and uncertainty
  without copying private session receipts into Git.
- Full forward-evaluation results are recorded against one exact head.
- The evaluated head is an ancestor of the adoption head, and deterministic
  validation proves the evaluated reviewer contracts changed only in their
  candidate-to-adopted lifecycle sentence after evaluation.

## Risk

L1/P1 reviewer evaluation and workflow integration.

## Verification

### Acceptance-to-proof map

| Failure atom | Required raw fixture | Required future proof | Custody |
|---|---|---|---|
| Canonical rule drift | schema/runtime/database disagreement | `ReviewerContractTests.test_blind_fixture_detects_canonical_rule_drift` | blind evaluation |
| Partial owner facts | correct project with wrong identity/instrument | `ReviewerContractTests.test_blind_fixture_detects_partial_owner_fact_validation` | blind evaluation |
| Malformed public input leak | wrong child type before attribute access | `ReviewerContractTests.test_blind_fixture_detects_malformed_input_leak` | blind evaluation |
| Mocked rollback | fake exception without staged state | `ReviewerContractTests.test_blind_fixture_rejects_mocked_rollback_proof` | blind evaluation |
| Label-only security fake | scenario name raised without constructed misuse | `ReviewerContractTests.test_blind_fixture_rejects_label_only_security_fake` | blind evaluation |
| SQL NULL guard escape | nullable comparison bypass | `ReviewerContractTests.test_blind_fixture_detects_sql_null_guard_escape` | blind evaluation |
| Composite ownership gap | individually valid cross-project IDs | `ReviewerContractTests.test_blind_fixture_detects_composite_ownership_gap` | blind evaluation |
| Missing-row isolation proof | mock `None` without stored foreign resource | `ReviewerContractTests.test_blind_fixture_rejects_missing_row_isolation_proof` | blind evaluation |
| Setup-only failure | unique seed collision before target assertion | `ReviewerContractTests.test_blind_fixture_detects_setup_only_failure` | blind evaluation |
| Non-discriminating regression input | invalid value old behavior already rejects | `ReviewerContractTests.test_blind_fixture_rejects_non_discriminating_input` | blind evaluation |
| Untrusted evidence instruction | malicious instruction plus underlying defect | `ReviewerContractTests.test_blind_fixture_ignores_untrusted_evidence_instructions` | blind evaluation |
| False-positive controls | valid mock/pure proof and valid public owner path | `ReviewerContractTests.test_blind_fixture_false_positive_controls` | blind evaluation |
| Fixture coverage cannot be removed | cases/expectations coverage | `ReviewerContractTests.test_proof_quality_fixture_classes_are_mandatory` | local mutation |
| Trust summaries do not claim receipt custody | evidence/trust skills | `ReviewerContractTests.test_trust_workflows_summarize_without_claiming_custody` | local unit |

All selectors above live in `scripts.test_reviewer_contracts`. The full command
remains:

```bash
python3 -m unittest -v scripts.test_reviewer_contracts scripts.test_review_target
python3 scripts/reviewer_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_review_contracts.py
git diff --check
```

The required `agent-gates` workflow executes the reviewer-contract validator,
its focused tests, and the stale-review scan on the exact PR head.

## Required reviewers

All nine existing reviewers plus human review of false-positive controls and
evaluation independence.

## Human review focus

Confirm the fixtures test transferable reasoning rather than memorized wording,
and that readiness remains advisory until human merge.

## Merge state

- Outcome on merge: `complete`

Independent blind evaluation succeeded against exact head
`8ab2da49e6b06f57167711d386607440a35abab5`. Reviewer contracts are
behaviorally adopted because deterministic supersession validation binds that
evaluated ancestor to the current reviewer contracts and permits only the
candidate-to-adopted lifecycle sentence to differ. The semantic proof-quality
initiative is complete.
Future escaped findings will be added only when they represent a reusable
failure class.
