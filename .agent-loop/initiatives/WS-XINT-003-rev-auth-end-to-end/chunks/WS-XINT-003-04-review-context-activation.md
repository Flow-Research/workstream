# Chunk Contract: WS-XINT-003-04 — Review Context Activation

## Status and risk

Non-implementable planning skeleton after 03D, merged REV-06C/07A, and merged
XINT-002-07A. Refresh exact files and commands on current main before an
explicit user request. L1 confidential artifact access.

## Goal

Activate human `review.context.read` and `review.chain.read` against the exact
REV-07A lease/packet/chain context and consume XINT-002-07A fixed
`artifact.review_packet.materialize`. Reviewer note/findings require no artifact
upload; evidence actions remain future-intent-required and unavailable.

## Allowed files

Enumerate exact AUTH evaluator/availability parity, merged REV-07A and
XINT-002-07A read-only manifests, integrated tests, canonical specs, docs, and
evidence files at current-main start. No lifecycle implementation file is
writable.

## Not allowed

New contexts/protocols/principals, REV lifecycle behavior, contributor response
authority, decision/revision implementation, XINT-003
ownership of ART actions, XINT-002 ownership of human REV actions, or generic
artifact authority.

## Acceptance criteria

- Human reviewer context/finding authority is limited to the exact leased
  Submission and canonical immutable packet manifest/bindings.
- Lease expiry/release/reassignment, actor/link/grant revocation, version drift,
  packet replacement, cross-resource, and wrong service/action deny bytes.
- The fixed ART materializer cannot claim, decide, submit, or inherit reviewer
  authority. Review-evidence binding remains planned/unavailable.
- Human-review revision uses XINT-002-05D and the normal contributor ZIP path;
  07B is reserved and CheckerRun remediation remains a distinct context.
- The chunk adds no ActionId, PermissionId, principal, context class, protocol,
  REV lifecycle behavior, or product route.

## Verification and reviewers

PostgreSQL read/evidence races, PREP denial, ART service separation, coverage,
hosted gates, and full L1 reviewers.

## Stop

Merge and stop before decision activation.
