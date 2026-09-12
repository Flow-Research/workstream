# WS-AUTH-001-12F4 — Project-manager authority over unified proposals

- Initiative: `WS-AUTH-001`
- Durable disposition: `Complete`
- Intended merge outcome: activate exact current Project Manager authorization for the existing hidden complete-proposal read, pre-submission approval and correction operations; public composition follows in POL-05B.

## Intent

A covered human Project Manager can inspect the complete finalized setup result,
approve the pre-submission proposal or request a corrected generation. Reuse the
POL-05A operation and transaction owners. Do not run another inference for approval.

## Current behavior

POL-05A provides `GuideProposalService`, immutable approval/correction custody,
strict public AUTH facts and a nominal prepared-operation port. Its default
composition is unavailable. The catalogue lists the three actions as planned.
The approval action still maps to the superseded manual policy mutation context.
Shared `PreparedAuthorizationService` owns issuer, session, root transaction,
request, one-use handles and authority locking. Its projection replay helper
currently only accepts setup-service projection/finalization resources.

## Bounded change

### Allowed

- `backend/app/modules/authorization/`: exact proposal domain/PREP resource,
  adapter, catalogue, shared kernel/PREP dispatch, digest and audit-target wiring;
  remove approval from the superseded manual policy resource mapping.
- `backend/app/api/deps/`: explicit dependency factory for the new AUTH adapter,
  only if useful to the next public consumer; no route exposure.
- Narrow public AUTH/POL contracts only when existing facts cannot bind required
  authority. Product lifecycle/compiler ownership stays unchanged.
- Focused `backend/tests/authorization/guide_proposals/` and affected catalogue,
  resource-union, proposal and composition tests; shared test fixtures and explicit
  semantic-lane registration/expectation updates.
- AUTH/POL specifications, README, roadmap, current initiative navigation and this
  adopted chunk record. `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` records
  exact reductions in touched oversized code; boundary inventories only for
  actual changed edges. Exact behavior-ownership partition registration, its
  approved-addition set in `backend/scripts/behavior_ownership.py`, and closed
  admission regression coverage in `backend/tests/test_behavior_ownership.py`
  are included; protected base and retained ownership stay unchanged.

### Not allowed

Public proposal routes, new product mutations, agent calls, post-submit approval,
guide activation, task/intake changes, broader role/service permissions, retained
data deletion, compatibility routes/aliases or a second authorization kernel.
No workflow, coverage-floor, test-selection or structural-limit weakening.
`backend/tests/test_authorization.py` and the structural debt inventory may
shrink as obsolete approval-only assertions and shared parsing are replaced.

## Design and decisions

1. Use the exact public proposal locator before product locks and complete
   `GuideProposalAuthorizationFacts` after them. Closed strict domain validation
   binds typed IDs, generation, component/output commitments and paired current
   approval identity/digest. Preserve the canonical public business digest;
   transport request identity is separately bound to live PREP custody.
2. Activate only the three adopted actions. Extend the existing exact-project
   Project Manager lock/evaluator path; deny Operator, Audit, unrelated humans,
   services, foreign scope, revoked grants and inactive identities.
3. Add one AUTH adapter implementing `GuideProposalAuthorizationPort` with the
   caller session and authenticated request context. Per locator it constructs
   the existing kernel/PREP/repository together, preserving actor/link/request
   and binding business correlation to the operation ID computed by POL. This
   avoids duplicating POL operation-ID formulas in public callers. A nominal view delegates one-use custody
   to shared PREP and closes handles on every exit. Read produces bounded allowed
   evidence; mutation receipts carry the actual matched grant and decision.
4. Extend shared PREP matching/replay through the proposal-specific domain rules.
   Replay requires fresh current authority and the exact original allowed event,
   operation correlation, actor, scope, permission, resource and business digest;
   a new transport request is permitted. No new allowed event or product writes
   on exact replay. Current authority must remain locked through owner completion.
5. Replace the old approval resource mapping entirely. Required tests for manual
   draft create/update/derive remain; old approval-only shape tests are replaced
   by unified proposal tests. The unused approval-only
   `SubmissionPolicyCompilationContext` and old approval-only output fields are
   removed after tracing their sole application consumer. Remove obsolete wording in the touched replay helper
   without adding another implementation path.

The shared manager-lock routine and guide resource matching are extracted within
AUTH to keep the oversized kernel smaller. The existing manual draft parser is
likewise extracted from PREP without changing its validation. Structural debt
entries only shrink; no limits or exceptions are raised. Proposal action IDs
have one catalogue-owned set shared by these paths.

## Acceptance criteria

- All three actions accept only current covered human PM authority; raw kernel
  calls or old manual approval contexts cannot bypass preparation.
- Final resource must match every prepared selector; changed action, actor/link,
  project, guide, compilation, operation, handle, session or transaction
  rejects without allowed evidence or product writes.
- The live locator request ID equals the current authenticated transport request;
  an exact replay may have a new transport request. The immutable business
  request digest must still equal retained operation evidence.
- Real finalized proposal read/approval/correction and valid replay run through
  the concrete adapter and real PostgreSQL audit/product constraints. Incomplete
  results and stale proposal/component hashes remain rejected by the same owner.
- Revocation and role/tenant substitution deny; valid controls traverse the same
  fixture guards. Concurrency serializes current authority with grant revocation.
- Persisted receipt digest matches the canonical proposal facts. No raw guide
  text, correction reason, storage handle or provider output enters AUTH audit.
- No public proposal route or post-submit/guide activation becomes available.

This cohesive authorization change exceeds the usual 500-line L1 guideline
because three actions require shared PREP/replay wiring, real database and
concurrency proof, and removal of the superseded approval resource. It adds no
second product owner, schema migration, public route or dependency. Reviewers
receive bounded specialty assignments rather than one undifferentiated diff.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: architecture, security, QA, test delta, documentation,
  product/operations; CI integrity for test selection/coverage evidence and reuse
  for shared PREP/adapter ownership (related tracks may share one assignment).
- Human review focus: narrow human activation, no obsolete approval bypass,
  current-authority replay and unchanged hidden/public boundary.

## Evidence

Planned commands use `/tmp/pol05a-review-venv/bin/python` (system Python with the
backend dependencies; do not execute the incompatible old backend venv binary).
Future tests: `backend/tests/authorization/guide_proposals/test_context.py`
(digest parity, strict facts and old resource rejection), `test_prepared.py`
(handle/request/session substitution and actor/role all-pairs), and
`test_postgresql.py` (read audit, real approval/correction, changed-transport
replay, revocation and system-scope PM denial). Run these with
`python -m pytest tests/authorization/guide_proposals -q` from backend through
`scripts/run_isolated_tests.py` for PostgreSQL custody. Run affected existing
`tests/test_authorization.py` to preserve create/update/derive; existing
`tests/projects/guide_compilation/proposals` proves hidden product guards. Run
actual full semantic-lane collection, lint/structure/links/stale wording, then
hosted Backend and Agent Gates on the frozen candidate. New test paths above are
planned implementation, not existing execution evidence. Test-of-test probes must
reach the intended guard with otherwise valid finalized proposals. Full hosted
coverage must preserve all existing floors and at least 90% for changed AUTH.

## Review findings

Plan review corrected a transport/business-request ambiguity: a new transport
request is permitted for exact replay, while the canonical business request
and stored operation remain identical. Initial PostgreSQL proof exposed an
overly strict UUID concrete-type check; parsed UUID subclasses from the actual
PostgreSQL driver are accepted, while raw strings still reject.

## Reconciliation

- Main: `2c95d4e2`, merged POL-05A (#398); no overlapping open AUTH PR.
- Next usable boundary: POL-05B exposes the same hidden operations using AUTH-12F4.
- Remaining risks: locked product facts remain PROJECTS-owned; AUTH must validate
  custody without importing private PROJECTS repositories or duplicating compiler
  decisions. Public endpoints and request denial composition remain POL-05B work.

Review reconciliation keeps proposal resources in their own canonical action map,
composed into the existing kernel and PREP. The established mutation-only map
remains closed; its existing regression test exposed the incorrect initial
registration. Exact behavior-ownership registration includes all five new AUTH
modules while retaining the partition's protected base and every existing owner.
The admission test rejects undeclared additions, retained-owner changes and
removal. Current action and operational PREP inventories explicitly distinguish
active hidden proposal authority from pending POL-05B public composition.

Database negative fixtures use the actual `project_manager` role with system
scope and an actual other-project manager grant. Neither case substitutes an
invalid role token or an unrelated Audit grant for the boundary being tested.

Shared proposal value builders live in a non-test support module. Importing
collected test modules from the new AUTH tests caused deterministic UUID
parameter IDs to differ between full collection and individual lane execution.
Moving the existing builders preserves their single owner and assertions while
making collection independent of those cross-test imports; the lane runner and
selection validation are unchanged. Foreign-project fixtures use the existing
authorized project-creation helper before issuing their Project Manager grant.

The independent action-owner, active-action and audit-action test inventories
include exactly the three AUTH-12F4 activations. The superseded proposal-planned
assertion is replaced by executable-action and exact activation-owner checks;
all other planned actions remain closed and the catalogue cardinality is retained.

The adopted acceptance contract describes all three completed activations.
Happy-path tests require the nominal authorization receipt for approval and
correction, while the read action explicitly returns no receipt. A dropped
mutation receipt must fail the regression even when audit and one-use behavior
still succeed.
