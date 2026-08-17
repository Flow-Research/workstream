# Discovery: WS-CI-005 Semantic Proof Quality

## Current behavior

WS-CI-004 already supplies exact-target inspection, structured receipts,
specialty routing, atomic traceability, residual-escape analysis, and isolated
reviewer evaluations. `scripts/reviewer_contracts.py` checks that every reviewer
agent and skill contains the shared semantic requirements. Its evaluation model
uses positive, negative, stale-replay, output-contract, and handoff cases.

The remaining gap is semantic discrimination. The validator checks that a
traceability row has an owner, implementation source, named proof, custody, and
result. It does not determine whether the named proof can observe the behavior.

## Relevant files and symbols

| Path | Current responsibility | Gap |
|---|---|---|
| `.agents/skills/reviewer-evidence-protocol/SKILL.md` | Universal exact-head and semantic review process | No proof-strength or test-of-the-test rule |
| `.agents/skills/{architecture,security,qa,test-delta,ci-integrity,reuse-dedup,senior-engineer}-review/SKILL.md` | Specialty review depth | No shared database/isolation/strict-fake failure patterns |
| `.codex/agents/*-reviewer.toml` | Custom reviewer execution contracts | Can repeat named proof without demonstrating discrimination |
| `.agent-loop/templates/INTERNAL_REVIEW_RECEIPT.schema.json` | Structured advisory receipt | Trace rows do not declare proof strength or adversarial mutation outcome |
| `scripts/reviewer_contracts.py` | Reviewer contract/evaluation validator | Validates fields and tokens, not proof compatibility |
| `scripts/test_reviewer_contracts.py` | Mutation and output regression tests | Does not replay non-discriminating proof classes |
| `WS-CI-004/evaluations/{CASES,EXPECTATIONS}.json` | Blind reviewer evaluation inputs | Covers broad specialties, not the PR #349 escapes |
| `.agents/skills/evidence-gate/SKILL.md` | Deterministic pre-review evidence | Does not classify infrastructure custody |
| `.agents/skills/pr-trust-bundle/SKILL.md` | Human-facing evidence summary | Can summarize a named but semantically weak test |

## Failure replay

### PR #338 and PR #346

These exposed path continuity, atomic state vocabulary, public-owner boundaries,
completed-history immutability, ledger parity, and compound-criterion gaps.
WS-CI-004 now covers exact-head and traceability mechanics for those classes.

### PR #349

The following escaped after initial internal passes:

1. `PROJECT_POINTS` quantity `"1.0"` passed a duplicated runtime validator while
   canonical schema and database rules rejected it.
2. A COMPENSATION owner fact was trusted after checking only its project, not
   binding identity and instrument type.
3. Malformed immutable input leaked `AttributeError` before domain concealment.
4. A mocked repository exception was presented as transaction rollback proof.
5. Fake authorization methods raised labels for wrong-session/copy/replay cases
   without constructing those conditions.
6. PostgreSQL `<>` comparisons over nullable operands allowed trigger guards to
   evaluate to unknown and skip rejection.
7. Independent foreign keys allowed project, policy, and version facts that
   existed individually but did not share composite ownership.
8. A cross-project read test used a mock returning `None`, duplicating the
   missing-record case rather than proving repository isolation.
9. PostgreSQL regressions initially failed during shared fixture setup because
   they recreated a globally unique service identity, so the intended
   integrity assertion was never reached.
10. A required-version regression initially used an invalid non-UUID value the
    old code already rejected instead of `None`, the previously accepted bad
    selector.

These are proof-quality failures: the named proof existed but could not
distinguish the defect.

## Existing tests and gaps

Existing reviewer-contract tests prove protocol adoption and receipt shape.
They do not currently prove:

- proof custody is compatible with the claim;
- a reviewer mutates or contradicts a claimed invariant;
- strict fakes validate identity, state, and call order;
- real tenant-isolation proof persists a foreign resource;
- database review covers NULL semantics, composite ownership, direct SQL, and
  rollback durability;
- reuse review compares schema, runtime, and database representations of one
  canonical rule;
- escaped findings become permanent blind evaluation cases.
- fixture setup reaches the intended assertion rather than merely failing;
- a regression input distinguishes corrected behavior from the pre-fix code.

## Dependencies and conventions to preserve

- Extend `scripts/reviewer_contracts.py`; do not create a parallel validator.
- Extend the WS-CI-004 reviewer registry and evaluation harness; do not fork the
  nine-reviewer map.
- Keep shared rules in one protocol/reference and specialty deltas in their
  existing skill and agent files.
- Keep receipts advisory and out of tree; GitHub remains durable authority.
- Keep external review responses separate from internal receipts.

## Risks discovered

| Risk | Consequence | Planned control |
|---|---|---|
| Named proof without observability | False PASS | Closed proof-strength and compatibility rules |
| Permissive fake | Simulated security/isolation evidence | Strict-fake obligations and blind fixtures |
| ORM-only review | SQL integrity bypass | Database integrity reference and direct-SQL probes |
| Missing tenant record | Isolation test duplicates not-found | Real foreign-resource proof requirement |
| Duplicated business rule | Schema/runtime drift | Canonical-rule reuse comparison |
| More reviewer prose | Token/maintenance growth | One concise shared reference, validated adoption tokens |

## Unknowns to measure during implementation

- Whether proof-strength metadata belongs directly in the receipt schema or in
  a referenced traceability sub-schema.
- The smallest blind-fixture set that covers each escape without leaking the
  answer or making evaluation slow.
- Which proof-strength mismatches can be checked deterministically and which
  remain reviewer judgments.
