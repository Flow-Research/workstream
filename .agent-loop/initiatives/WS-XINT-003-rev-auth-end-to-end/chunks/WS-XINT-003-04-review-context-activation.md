# Chunk Contract: WS-XINT-003-04 — Review Context And Finding Authority Activation

## Status and risk

Non-implementable planning skeleton after 03B. Refresh exact files and commands
on current main before an explicit user request. L1 confidential artifact access.

## Goal

Activate human `review.context.read` and `review.finding_evidence.ingest` against
the exact lease/packet/finding context. Consume the already-merged XINT-002-07A
fixed `artifact.review_packet.materialize` and reviewer-finding binding
capabilities. The ART contract split is completed by WS-XINT-003-01, not here.

## Allowed files

Enumerate exact REV context/finding service, AUTH composers/activation parity,
merged XINT-002-07A ART-only manifest, routes, tests, canonical specs, docs, and
evidence files at current-main start.

## Not allowed

Contributor response authority, decision/revision implementation, XINT-003
ownership of ART actions, XINT-002 ownership of human REV actions, or generic
artifact authority.

## Acceptance criteria

- Human reviewer context/finding authority is limited to the exact leased
  Submission and canonical immutable packet manifest/bindings.
- Lease expiry/release/reassignment, actor/link/grant revocation, version drift,
  packet replacement, cross-resource, and wrong service/action deny bytes.
- Materializer and binding services use separate fixed identities and cannot
  claim, decide, submit, or inherit reviewer authority.
- The ART materializer/binder receives only its fixed-service actions. Future
  07B response evidence requires exact `Review(needs_revision)`, obligation,
  preparation head/digest, contributor assignment, predecessor, response,
  deadline, and round; CheckerRun remediation is ineligible.

## Verification and reviewers

PostgreSQL read/evidence races, PREP denial, ART service separation, coverage,
hosted gates, and full L1 reviewers.

## Stop

Merge and stop before chain-read activation.
