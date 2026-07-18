# Workstream PR Trust Bundle

## Chunk

`WS-REV-001-PLAN` - Review And Revision Lifecycle Planning

Merge intent: `.agent-loop/merge-intents/WS-REV-001-PLAN.json`

## Goal

Reconcile the complete review/revision lifecycle plan with trusted main after
AUTH reconciliation PR #140 and AUTH-09A PR #132, retain the WS-XINT handoffs
and human-approved FinalAcceptance boundary, and leave all runtime chunks
inactive.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/INTENT.md`
- Chunk contract: `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-PLAN-review-revision-lifecycle-planning.md`
- Human clarifications retained: one Project Guide context; controlled next-
  attempt rebase; exact leased-Submission context for reviewers; immutable Review,
  finding, and resolution history for every decision; accept-only
  FinalAcceptance; no v0.1 adjudication runtime.

## What Changed

- Adopted PR #140's exact AUTH custody, PREP, registration, service identity,
  per-feature activation, and lifecycle gates without claiming runtime exists.
- Reconciled AUTH-09A's merged migration `0023`, seven ART identities, eleven
  exact memberships, and 65-action catalogue (`9` active, `56` planned). It
  provisions no actor, admits no service token, activates no action, and includes
  no REV identity.
- Kept all 24 REV dependencies unavailable and separated the ART evidence action.
- Made REV-01 publish availability-neutral four-action registration and six exact
  service identity manifests.
- Repaired the AUTH-13/14 dependency cycle: an AUTH-owned schema-only contributor
  foundation precedes REV-02; REV-09A supplies hidden preparation behavior;
  amended AUTH-13/14 own their command/schema/migration cutovers; AUTH activation
  precedes REV-13 exposure.
- Made REV-12A merge-order-neutral relative to AUTH-13 and limited it to
  classifying/fencing owner-installed behavior.
- Assigned PREP validation, current-authority checking, single consumption,
  evaluation, and evidence staging solely to AUTH after REV locks and recomposes
  final feature facts.
- Split rejected pre-consumption substitution, permanently invalid consumed/
  duplicate use, and evaluated denial with clean AUTH evidence restaging.
- Made the request route or service command the caller `AsyncSession` owner and
  sole committer; REV orchestrates and stages shared audit/outbox rows.
- Added internal accept-only FinalAcceptance and changed submitter contribution
  lineage to consume it. Reviewer contribution remains direct from Review and
  ReviewLease for all three decisions.
- Preserved reachable fulfillment drain with CON-owned cutoff/ordinal lineage,
  completion-only delivery work, universal writer fencing, and same-root claim
  recovery.
- Updated the shared REV/CON handoff, archival reference provenance/checksums,
  and a narrowly bounded AUTH documentation scanner regression.
- Clarified that archival Flow Node text remains byte-preserved evidence while
  REV-01 must create the future active AWS S3/MinIO contract; fixed PR `#139`
  Markdown rendering without changing its meaning.
- Made guide resolution exact: compare the prior Submission's stamped identity/
  activation sequence with an internally consistent active pair, freeze the
  selected preparation for Task Context, and block invalid or unsafe context.

## Why It Changed

Merged WS-XINT, AUTH planning, and AUTH-09A changed actor identity, activation
custody, prepared mutation, service-identity foundations, catalogue/migration
facts, and cross-domain transaction boundaries.
The previous REV plan also predated the approved FinalAcceptance source and
contained stale sequencing that could not be implemented without ownership
collisions or circular prerequisites.

## Design Chosen

```text
AUTH schema-only contributor foundation
-> REV persistence and hidden behavior through REV-09A
-> amended AUTH-13/14 owner cutovers
-> remaining REV hidden behavior and REV-12A fencing
-> exact AUTH activations, including submission.create
-> REV-13 verification and product exposure
```

Every valid decision appends immutable Review/finding/resolution history. The
reviewer contribution operation runs for all decisions. Only `accept` adds
FinalAcceptance and invokes the submitter contribution operation. CON flushes
only; REV stages shared audit/outbox inputs; the request route or service command
commits once. Decision-time code performs no ART or provider call.

## Alternatives Rejected

- Feature-owned ActionId registration or activation.
- Full AUTH-13/14 before their downstream REV-09A preparation dependency.
- REV-owned prepared-handle validation or transaction commit.
- Inferring submitter acceptance directly from `Review.decision`.
- A second review submission route, raw ArtifactStore access, or CON router
  ownership in REV.
- Adjudication actions, queues, states, policy, runtime, or readiness gates in
  v0.1.

## Scope Control

### Allowed Files Changed

- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**`
- Exact FinalAcceptance amendment to the shared `REV_CON_HANDOFF.md`
- `.agent-loop/merge-intents/WS-REV-001-PLAN.json`
- Canonical WS-REV reference Markdown/PDF, provenance README, and checksums
- `.gitattributes` for the byte-preserved canonical Markdown
- `scripts/check_stale_authorization_docs.py` and its exact gate regressions

### Files Outside Contract

- None

## Product Behavior

- [x] No Workstream product behavior changed.
- [ ] Product behavior changed and is explained here:

This is planning, reference repair, review evidence, and a documentation-scanner
classification fix. It changes no backend runtime, migration, API, authorization
catalogue, artifact provider, contribution behavior, workflow, dependency, or
test threshold.

## Evidence

### Commands Run

```bash
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/test_agent_gates.py
sha256sum -c docs/reference_specs/SHA256SUMS
python3 scripts/check_loop_memory_state.py
git diff --check
```

### Result Summary

```text
Internal review evidence passed.
Markdown links passed for 36 changed Markdown files.
Workstream, ART, and AUTH stale scans passed.
80 agent-gate tests passed.
All reference checksums passed.
Loop-memory state passed.
Diff integrity passed.
```

## Acceptance Criteria Proof

- [x] Canonical reference Markdown/PDF and hashes are restored with no duplicate
  `(2)` paths.
- [x] PR #140 and WS-XINT owner boundaries are reconciled without runtime claims.
- [x] AUTH-09A's current 65/9/56 catalogue, migration `0023`, and closed ART
  service matrix are recorded without claiming provisioning or REV readiness.
- [x] Every decision has immutable Review/finding/resolution history; only accept
  adds FinalAcceptance and submitter contribution.
- [x] AUTH, ART, task, REV, CON, audit, outbox, and caller transaction ownership
  are explicit and non-circular.
- [x] All proposed chunks have scope, exclusions, acceptance criteria, proof,
  reviewers, and human focus.
- [x] First runtime chunk remains inactive and requires a separate explicit start.

## Test Delta

### Tests Added

- Added exact positive and fail-closed AUTH documentation-scanner cases for
  technical execution-package paths and existing live-drill CLI flags.

### Tests Modified

- Extended `scripts/test_agent_gates.py` only for the matching scanner boundary
  cases, including malicious suffix/path near misses and retained human-role
  rejection.

### Tests Removed Or Skipped

- None

## Internal Reviewer Results

Reviewed code SHA: `12a781b2c4e8e8bb3378e3c4cb4f7c32ac9ba5be`

Trusted main SHA: `299363af5d9e8a68bcc9b17457188048483caeed`

Reviewed at: `2026-07-17T14:07:20Z`

Reviewer run IDs: senior/architecture/reuse=`/root/finalaccept_senior_arch_r2`; QA/product/test-delta=`/root/finalaccept_qa_product_r2`; security/docs/CI=`/root/finalaccept_security_docs_r2`

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS | None | Executable dependency graph and ownership are coherent. |
| QA/test | PASS | None | PREP, exact guide keep/rebase/block behavior, frozen Task Context, decisions, activation, and release proof are testable. |
| Security/auth | PASS | None | AUTH ownership, caller commit, denial atomicity, and lineage fail closed. |
| Product/ops | PASS | None | Approved review, revision, contribution, and release behavior is preserved. |
| Architecture | PASS | None | Cross-owner graph is acyclic; REV-12A only classifies/fences. |
| CI integrity | PASS | None | No workflow, threshold, dependency, or package gate weakened. |
| Docs | PASS | None | Normative plan, chunks, handoff, log, and evidence are consistent. |
| Reuse/dedup | PASS | None | Existing routes, participants, PREP, composition, and typed ports are reused. |
| Test delta | PASS | None | Scanner tests are additive; none were weakened or removed. |

## External Review

External review response file:

- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/reviews/WS-REV-001-PLAN-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | PASS on prior publication head; rerun required | Zero unresolved inline threads; PR-description template warning addressed by this bundle. |
| GitHub checks | Rerun required | Agent gates passed on the prior publication head; final backend and gate checks must pass after this evidence-only update. |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence remains unchanged; no workflow was edited.

## Remaining Risks

- AUTH must merge the schema-only contributor foundation, AUTH-09B/09E,
  PREP, custody, registration, exact REV service identity extensions, amended
  AUTH-13/14 cutovers, evaluators, and activations at the named gates.
- ART must schedule review-evidence ownership and merge packet-read plus
  server-derived `Submission.artifact_hash` amendments.
- CON must merge frozen policy lineage, mutually exclusive contribution sources,
  the two-operation flush-only participant, and later fulfillment fence/cutoff
  capabilities.
- PR #128 still needs final-head external checks and explicit human merge approval.

## Follow-Up Work

- Merge intent names `WS-REV-001-01` as the same-initiative successor with
  `next_requires_explicit_start: true`.
- Every runtime chunk requires a fresh main-SHA audit, its own contract/evidence,
  reviewer fanout, and explicit human start.

## Human Review Focus

Please inspect:

- AUTH activation and service identity custody.
- AUTH-13/14 versus REV-09A/12A/13 ownership and ordering.
- All-decision immutability and accept-only FinalAcceptance.
- Two ordered CON operations and mutually exclusive contribution lineage.
- Guide rebase, ART lease isolation, transaction ownership, and fulfillment drain.
- Absence of adjudication and runtime implementation.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.

Only the human may approve and merge PR #128. This PR does not start
`WS-REV-001-01`.
