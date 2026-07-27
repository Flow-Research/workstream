# Discovery: WS-XINT-002 ART-AUTH End-to-End Contract

## Observations on trusted main

- `backend/app/modules/authorization/catalogue.py` contains 81 ActionIds and 76
  PermissionIds. All current artifact actions are planned and unavailable.
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
