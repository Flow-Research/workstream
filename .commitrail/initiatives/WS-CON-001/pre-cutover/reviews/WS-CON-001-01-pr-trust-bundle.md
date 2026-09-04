# PR Trust Bundle: WS-CON-001-01

## Chunk

`WS-CON-001-01` - Canonical Contract Adoption And Architecture Decision

Risk: L0 direction executed as L1 specification work; SLA P1.

## Goal

Publish one repository-owned contribution/compensation specification and ADR
0016, reconciled with merged AUTH, REV, ART, and WS-XINT boundaries, without
changing runtime or archival inputs.

## Human-Approved Intent

The human approved the reconciled WS-CON plan, accept-only
`Review -> FinalAcceptance -> accepted_submission`, ContributionPolicy
superseding the retired economic model, no v0.1 adjudication, and explicit start
of this chunk.

## What Changed

- Added the canonical contribution/compensation specification and ADR 0016.
- Linked both from README with explicit precedence.
- Corrected active data-model naming and mirrored numeric/receipt rules.
- Recorded active-doc inventory, conformance proof, decisions, status, review
  evidence, and one merge intent.
- Reconciled the contract with merged AUTH-09B PR #143 and its
  74-permission/65-action/10-active/55-planned runtime baseline.

## Why It Changed

The archival input and old runtime-oriented chunk documents did not reflect
merged FinalAcceptance, AUTH custody/prepared mutation, optional ART evidence,
dispatcher/handler separation, or the joint release fence. One active contract
is required before schema/runtime chunks proceed.

## Design Chosen

- ContributionPolicy is the only target eligibility policy.
- TaskAssignment and ReviewLease independently freeze immutable versions.
- Every valid Review creates reviewer recognition; accept alone creates
  FinalAcceptance and submitter recognition.
- One mandatory CON participant has separate reviewer and accept-only submitter
  operations; REV stages audit/outbox and the caller commits once.
- Awards are immutable policy results; adapters only fulfill them after commit.
- AUTH owns identifier, evaluator, evidence, service admission, and activation;
  22 mappings remain non-final proposals.
- AUTH-09B provisioning creates only an approved service actor/link. It does not
  admit service credentials or grant feature authority, and the current ART
  identities/static rows cannot be reused by CON.
- One shared outbox and one REV-owned controller/fence govern delivery.
- Quantities use `NUMERIC(38, 18)` and receipts store only bounded, minimized
  canonical facts.

## Alternatives Rejected

- Direct submitter inference from Review.decision.
- Manual or independently authorized FinalAcceptance.
- One nullable cross-actor participant input.
- CON-owned commit or post-commit contribution repair.
- A compatibility alias or fallback economic policy.
- Mandatory ART evidence in the core transaction.
- Provider-decided award eligibility.
- Dispatcher authority inherited by handlers.
- A second CON release controller.
- Adjudication in v0.1.

## Scope Control

Changed files are limited to canonical docs, README precedence, the active
data-model correction, WS-CON initiative artifacts, and exactly one merge
intent. No backend, migration, AUTH/ART/REV-owned runtime contract, workflow,
dependency, test, coverage, or roadmap/export file changed.

The user-owned deleted reference PDF was not staged or committed.

## Product Behavior

Runtime behavior is unchanged. The documents define target behavior and keep
all routes hidden until implementation, AUTH activation, and joint release.

## Acceptance Criteria Proof

- ADR 0016 follows independent ADR 0015.
- Required policy, binding, contribution, award, receipt, status, outbox, audit,
  authorization, adapter, and release contracts are defined.
- Legacy cleanup is split across 05A/05B with no fallback or implicit unpaid.
- FinalAcceptance lineage, two operations, single commit, zero core ART calls,
  and no adjudication match merged REV.
- All 22 action mappings are unregistered and non-final.
- D11, legacy rows, service authority, and optional evidence remain human gates.
- `/api/v1`, secret exclusion, conformance mapping, and archive preservation are
  explicit.

## Tests And Checks Run

```text
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
git diff --check
```

All passed; agent gates reported 80 tests passed. Both present archival hashes
matched, the committed reference-spec diff was empty, and the mapping count was
exactly 22.

## Test Delta

No tests, scanners, test configuration, or coverage thresholds changed. The
existing tests were run unchanged.

## CI Integrity

No workflow, package script, dependency, lint/typecheck command, test runner, or
coverage threshold changed. CI-integrity review passed.

## Reviewer Results

Exact reviewed SHA: `a6a88fb42da8ffb37e8293f1495f6be3513e8ad1`.

| Track | Result |
|---|---|
| Senior engineering | PASS |
| QA/test | PASS |
| Security/auth | PASS after receipt/numeric repairs |
| Product/ops | PASS |
| Architecture | PASS |
| Docs | PASS after conformance/inventory repairs |
| Reuse/dedup | PASS |
| CI integrity | PASS |

All valid internal and external findings were repaired and all tracks passed at
the exact SHA with no remaining findings. No sub-agent session remains open.

## External Review

CodeRabbit raised two valid contract-clarity findings. The repaired contract now
states that policy definitions and awards reference the matching adapter binding
without reverse policy/award identifiers on the binding, and distinguishes
allowed bounded non-secret receipt identifiers from prohibited raw secrets,
authentication tokens, and unbounded provider payloads. Every internal track
then passed again at the exact repaired SHA. Both CodeRabbit threads are resolved
and outdated. After AUTH-09B merged, all tracks passed again at the exact
current-main reconciliation SHA. GitHub CI and CodeRabbit must rerun on the
pushed evidence commit; human review remains the merge gate.

## Remaining Risks

- D11 administrative role candidates are still human/AUTH gates.
- Legacy row classification is still a human migration gate.
- Protected CON service identities/actions/static rows are not yet approved;
  merged AUTH-09B provisioning does not satisfy them.
- AUTH-09C through 09E, AUTH-PREP, REV, task, ART-lineage, outbox, and release
  runtime prerequisites remain unimplemented and must refresh from trusted main
  per chunk.

## Follow-Up Work

The same-initiative successor is `WS-CON-001-02A`, shared transactional outbox
persistence. It requires a separate explicit start after this PR merges. This
chunk does not start it.

## Human Review Focus

1. Confirm FinalAcceptance and the two-operation transaction boundary.
2. Confirm ContributionPolicy fully supersedes the retired economic model.
3. Confirm AUTH owns activation and proposed identifiers stay non-final.
4. Confirm numeric/unit and provider-receipt minimization decisions.
5. Confirm open D11, legacy-row, and protected-service gates are acceptable.

## Human Merge Ownership

Only the human owner may approve and merge the specific PR. Passing reviewers,
CI, or CodeRabbit do not authorize merge or the next chunk.
