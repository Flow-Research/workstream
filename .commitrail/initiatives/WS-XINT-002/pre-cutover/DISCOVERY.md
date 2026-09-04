# Discovery: WS-XINT-002 ART-AUTH End-to-End Contract

## Observations on trusted main

- Baseline commit `2fb322bd2249a5fe9d3fa706dc63f033074e38ce` contains
  76 PermissionIds and 81 ActionIds: 22 active and 59 planned. All current
  artifact actions are planned and unavailable.
- The fixed service matrix has seven artifact identities and eleven memberships:
  verifier, put resolver, scheduler, binding, guide reader, materializer, and
  checker output.
- Six planned upload-session actions still exist even though the approved ART
  design uses one continuous outer-ZIP preparation surface.
- `artifact.submission_bundle.prepare`,
  `artifact.review_packet.materialize`, and
  `artifact.review_evidence.binding.create` are absent from the catalogue.
- Human review evidence actions already exist as planned:
  `review.finding_evidence.ingest` maps to `review.decision`, and
  `review.finding_response_evidence.ingest` maps to `submission.create`.
- `PreparedAuthorizationService` in
  `backend/app/modules/authorization/prepared.py` binds an opaque handle to the
  exact service, session, root transaction, action, actor, scope, idempotency
  key, and canonical request digest. It is single-use and rejects copying and
  serialization.
- `_scope_from_resource()` supports only actor-self and admin-mutation resource
  types. `AuthorizationService._prepare_prelocked()` rejects every service
  action as unavailable and has no assigned-contributor or ART resource plan.
- The existing ART 03A worktree has substantial uncommitted implementation plus
  a preserved `AUTH_END_TO_END_CONTRACT.md`. It must not be edited or mixed into
  this planning change.
- AUTH-11A is merged on `main`; the earlier migration dependency is resolved.

## Existing plans affected

- `WS-ART-001` chunks 03A-07 cover guide ingest/use, one-ZIP submission
  admission, submission binding, checker materialization/output, and recovery.
- `WS-AUTH-001/ACTIVATION_CUSTODY.md` assigns the existing 25 ART actions to
  eight AUTH custodians but does not contain the final submission/review action
  set.
- `WS-AUTH-001-14` mixes broader submission/checker cutover with artifact
  dependencies and must not be treated as an alternate ART activation path.
- REV plans own lease, decision, finding, response, and revision facts. They do
  not grant artifact bytes directly.

## Confirmed gaps

1. One closed catalogue migration must add the three missing actions and remove
   the six obsolete upload-session actions and permissions without aliases.
2. The service matrix must remove scheduler expiry and add review packet and
   review-evidence memberships to existing identities.
3. PREP needs a closed extension mechanism for exact feature-owned typed
   resource contexts and lock plans; a generic callback or dictionary context
   would violate the authorization boundary.
4. Guide ingest, submission preparation/finalization, binding, review packet,
   and evidence binding need explicit transaction choreographies and crossed
   concurrency proof.
5. Initial, checker-remediation, and human-review revision submissions use the
   same public action but different closed locked facts. Checker remediation is
   rooted in one final `needs_revision` CheckerRun without human-review facts.
   Human-review revision facts include exact predecessor, active preparation
   head/digest, required responses/evidence, replacement assignment, limits,
   deadline, and predecessor advancement fencing.
6. Checker authority must remain byte-bounded and cannot create or consume a
   Submission.

## Assumptions requiring implementation-time confirmation

- `Submission`, not a separate `SubmissionVersion` table, remains the immutable
  version node linked by `supersedes_submission_id`.
- Existing service identities are sufficient; review packet uses the artifact
  materializer and review evidence binding uses the artifact binding service.
- Operator artifact audit stays Operator-only unless a separately reviewed
  exact Audit Authority projection is approved.

## WS-XINT-002-03 preimplementation reconciliation

- Trusted `main` at `f4cebb08176be41214d2eee4cae076064974818f` contains the
  merged ART 02C2 verification/publication fencing, ART 02C3 recovery chain,
  and ART 02D bounded Operator surfaces required by the activation gate.
- The implemented ART-owned authority protocol and facts are in
  `backend/app/modules/artifacts/schemas.py`; no integration implementation yet
  exists. This chunk deliberately creates
  `backend/app/modules/artifacts/authorization.py` as the ART-owned adapter and
  resource-composition boundary. It must implement the existing protocol (as
  corrected for transaction-bound consumption), not duplicate its schemas or
  move feature loading into AUTH.
- Put resolution and verification currently call `preflight()` after a
  candidate-reading transaction has ended, then claim a fence in a later
  transaction. Pending-work scan similarly computes its cutoff, authorizes,
  and loads the page in three separate phases. This cannot be connected safely
  to `PreparedAuthorizationService`, which requires one exact active root
  transaction and invalidates capabilities across replacement transactions.
- A terminal revalidation already occurs after the exact fenced ART rows are
  locked and before every terminal mutation. Activation must retain that
  placement but replace it with a fresh prepare/consume in the same terminal
  transaction; a capability must never span provider I/O.
- The safe choreography is therefore two fresh decisions for put/verification:
  claim authorization evidence commits atomically with the lease/fence, then
  provider I/O occurs, then terminal authorization evidence commits atomically
  with the fenced terminal mutation. The scanner uses one transaction for
  cutoff, preparation, exact page composition/consumption, and decision
  evidence, then publishes only those IDs after commit.
- The fixed service matrix already binds verifier, resolver, and scheduler to
  exactly one action each, but the three actions remain planned and the kernel
  intentionally rejects every prepared service action. Activation must extend
  the closed PREP scope/resource unions and kernel service branch; changing
  catalogue availability alone would still deny every resource guard.
- Production Celery tasks for put resolution and verification are registered
  but intentionally deny without constructing an ART runtime. No pending-work
  Beat entry exists. This chunk must provide an explicit executor composition
  root and scheduler registration without importing feature repositories into
  AUTH.
- The shared authority-audit fact validator originally admitted only the
  allowed boolean for authorization decisions. Exact ART operation/page
  binding therefore requires a privacy-bounded resource-context digest in the
  existing JSON evidence envelope; no schema migration is required.
- `backend/tests/test_artifact_put_resolution.py` does not exist. Existing put
  fencing proof is spread across artifact admission, verification, and recovery
  suites, so the corrected contract names the actual tests and permits a new
  focused activation test module rather than assuming a pre-existing file.

## WS-XINT-002-04B preimplementation reconciliation

- Trusted `main` at `9618b938c213a98e33772c04185a6e5d6b8c35f8`
  contains the complete hidden ART-03B1 through ART-03B4 guide binding,
  verified materialization, classification, extraction, and sufficiency
  pipeline required by the 04B entry gate.
- `artifact.guide_source.binding.create` and `artifact.guide_source.read`
  already exist in the closed catalogue with their correct permissions and
  fixed service-matrix memberships, but both remain `planned` and retain the
  historical `WS-AUTH-001-ART-03` owner. This is the observed preimplementation
  state; the reviewed 04B acceptance criteria require replacing that owner with
  `WS-XINT-002-04B` when the two actions activate.
- `GuideSourceBindingAuthorityFacts` and `GuideSourceReadAuthorityFacts`
  already carry the exact reviewed ART resource manifests. The feature
  services lock and validate canonical ART/project lineage before calling
  their authorization seams.
- Production binding and read seams remain intentionally fail-closed through
  `DenyGuideSourceBindingPreparedAuthorization` and
  `DenyGuideSourceReadPreparedAuthorization`. Existing tests use test-only
  allow adapters; no production 04B adapter is composed yet.
- The shared `PreparedAuthorizationHandle` and fixed-service PREP kernel must
  be extended, not replaced. The implementation must activate only the two
  guide actions, preserve process-local single-use handles, and keep all
  Celery messages identifier-only.
- ART-03C remains blocked until 04B merges. XINT-003 policy mutation work is
  independent but is not the immediate cross-initiative dependency while ART
  is waiting for guide binding/read activation.
