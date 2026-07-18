# WS-XINT-001-PLAN PR Trust Bundle

## Chunk

`WS-XINT-001-PLAN` - Lifecycle Boundary Reconciliation

Merge intent: `.agent-loop/merge-intents/WS-XINT-001-PLAN.json`

## Goal

Publish one reviewed planning source of truth that lets AUTH, ART, REV, and CON
continue independently without conflicting ownership, activation, transaction,
or lifecycle contracts.

## Human-Approved Intent

The user explicitly requested this cross-initiative reconciliation before the
parallel runtime agents continue. The approved contract is
`.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/chunks/WS-XINT-001-PLAN-boundary-reconciliation.md`.

## What Changed

- Defined AUTH-only action activation custody while feature initiatives retain
  their resource and runtime behavior ownership.
- Published exact AUTH/ART, AUTH/REV, ART/REV, and REV/CON handoffs, including
  all 25 ART actions and seven fixed artifact service identities.
- Locked project authority to independent `submitter`, `reviewer`, and
  `adjudicator` grants; removed the combined role from active planning.
- Separated core contribution creation from artifact-provider work and made
  `ContributionPolicyVersion` the frozen source for conditional compensation.
- Reconciled active architecture, operations, data-model, policy, roadmap, and
  initiative documents to the same lifecycle contract.
- Added deterministic scanners and regression tests that reject stale
  activation, authority, role, payment, and compensation wording.

## Why It Changed

Parallel implementation had reached shared boundaries where ambiguous custody
could cause duplicate activation, cross-subsystem writes, or incompatible role
and contribution models. This planning PR resolves those contracts before any
agent implements the next runtime chunk.

## Design Chosen

Each subsystem owns its feature behavior and persistence. AUTH alone decides
whether a protected action is active and admits exact human or fixed-service
authority. ART owns artifact bytes and bindings, REV owns review semantics and
leases, and CON owns contribution records, policy evaluation, awards, and
fulfillment state. Cross-subsystem interaction occurs through typed handoffs,
not direct repository ownership.

## Alternatives Rejected

- Feature-owned action activation was rejected because it creates multiple
  authorization custodians.
- A combined contributor role was rejected because submitter, reviewer, and
  adjudicator authority must be independently granted and revoked.
- Core contribution creation calling ART or a provider was rejected because it
  couples immutable contribution truth to external I/O.
- Operator-owned contribution policy or compensation mutation was rejected
  because those duties belong to Finance Authority and CON-owned commands.

## Scope Control

### Allowed Files Changed

- WS-XINT planning, handoff, decision, risk, status, review, and merge-intent
  records.
- Active AUTH, ART, REV, and CON planning contracts requiring boundary
  reconciliation.
- Related active architecture, operations, policy, roadmap, template, and
  diagram documents.
- Stale-contract scanners and their deterministic regression tests.

### Files Outside Scope

None. No backend, frontend, migration, workflow, provider, Celery, route, grant,
review, contribution, artifact, or payment runtime code changed.

## Product Behavior

- [x] No Workstream product behavior changed.
- [ ] Product behavior changed and is explained here.

## Acceptance Criteria Proof

- [x] AUTH-only activation custody and exact feature ownership are documented
  and scanner-enforced.
- [x] All 25 ART actions and seven fixed service identities have exact handoff
  records.
- [x] Independent submitter, reviewer, and adjudicator grants are canonical.
- [x] REV semantic artifacts remain backed by ART bindings through typed ports.
- [x] Core contribution creation performs no ART/provider operation and copies
  canonical artifact-hash lineage.
- [x] Contribution policy, award, fulfillment, and reputation ownership is
  explicit and stale payment terminology is rejected.
- [x] Every parallel initiative receives a bounded handoff and no runtime start
  signal.

## Tests/Checks Run

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/test_agent_gates.py
python3 -m ruff check scripts/check_stale_workstream_wording.py scripts/test_agent_gates.py
python3 -m ruff format --check scripts/check_stale_workstream_wording.py scripts/test_agent_gates.py
python3 -m ruff format --check scripts/check_internal_review_evidence.py scripts/test_agent_gates.py
git diff --check
```

Result summary:

```text
Markdown links: PASS (114 changed Markdown files)
Stale authorization documentation: PASS
Stale artifact contracts: PASS
Stale Workstream wording: PASS
Agent gate tests: PASS (80/80)
Ruff check and format: PASS
Chunk-contract ID inventory: PASS (97 unique IDs from 97 contracts)
Diff hygiene: PASS
```

## Test Delta

### Tests Added/Modified

- Added complete scanner fixtures for active shared contracts, historical-path
  parity, runtime compensation claims, activation custody, and authority rules.
- Bound all 84 active scanner patterns to ordered fixtures and explicit
  multiline/alternation variants.
- Proved every full-initiative authorization rule scans the complete contract
  even when no changed line intersects the finding.

### Tests Removed/Skipped

None.

## CI Integrity

- [x] Coverage threshold unchanged
- [x] Lint unchanged
- [x] Typecheck unchanged
- [x] No workflow weakening
- [x] No package script weakening
- [x] No unpinned new GitHub Action
- [x] Checkout credential persistence unchanged

## External Review

External review response file:
`.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/reviews/WS-XINT-001-PLAN-external-review-response.md`.

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Skipped | Status passed, but review was skipped because 127 files exceeded its 100-file limit. |
| GitHub checks | Pending after repair | Initial Agent Gates and Backend runs exposed the same PLAN-ID evidence parser defect; exact-ID repair is pending rerun. |

## Reviewer Results

Reviewed code SHA: `423f99d13472850da7f1b2686aa62fc7c4145683`

Reviewed at: `2026-07-17T02:10:13Z`

Reviewer run IDs: nine closed runs recorded in the internal review evidence.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | none | Complete planning diff and deterministic proof passed. |
| QA/test | PASS | none | Acceptance criteria and edge-case coverage passed. |
| security/auth | PASS | none | Authority, activation, and least-privilege boundaries passed. |
| product/ops | PASS | none | Human roles and lifecycle ownership passed. |
| architecture | PASS | none | Subsystem boundaries and planning-only scope passed. |
| CI integrity | PASS | none | No workflow, dependency, or threshold weakening. |
| docs | PASS | none | Canonical docs, diagrams, PDF, and links passed. |
| reuse/dedup | PASS | none | No duplicate rule source or competing abstraction. |
| test delta | PASS | none | Exact scanner inventory and runner parity passed. |

## Remaining Risks

- This PR defines contracts; runtime conformance remains the responsibility of
  each initiative's separately approved implementation chunks.
- Remote GitHub checks and CodeRabbit have not run on the published PR yet.

## Follow-Up Work

After explicit human merge approval and merge, each parallel AUTH, ART, REV,
and CON agent may pull trusted `main`, reconcile its own bounded plan/runtime
surface, and continue only under its own active chunk contract.

## Human Review Focus

Please inspect AUTH-only activation custody, independent project roles, fixed
service admission, transaction ownership, the contribution/compensation
boundary, and whether every handoff lets parallel initiatives continue without
cross-editing runtime ownership.

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
