# Chunk Contract: WS-POL-003-05B - Live Pre-Submit Approval

Disposition: Complete. Risk: L1.

Implemented boundary and decisions: [POL-05B change record](../../WS-POL-003-05B.md).

## Goal

Expose PM approval and atomically publish the exact approved artifact,
effective, and compiled pre-submit chain under the narrow AUTH adapter.

## Allowed files

Project approval router/service/repository, AUTH adapter consumption, ART
compiler integration, focused tests, specifications, and WS-POL-003 docs.

## Not allowed

Model calls, post canonical projection/approval, checker execution, broad
authority, legacy 12F3-only approval, or partial effective state.

## Acceptance

- Fresh PM PREP and final locked revalidation bind the complete compilation and
  exact component/catalogue hashes.
- Approved artifact/effective/pre outputs, replay, and decision evidence commit
  atomically; concurrent approval yields one current chain.
- Approval performs zero model calls and never precedes post-proposal creation.
- Consume 05A's separate operation/provenance records; finalization history
  remains unchanged before and after approval, replay and rollback. Do not
  rebuild approval storage or add a second effective-policy compiler.

## Verification and review

Live read-before-approve and setup-wide correction use POL-05A's exact hidden
projection/commands and AUTH-12F4's separate actions. Bind an exact compilation
selector, never approve by an unverified latest diagnostic response. Expose
these before first approval; later POL-08 owns supplementary visibility and
physical cleanup, not the ability to inspect or correct the proposal.

PostgreSQL approval races, replay/revocation/stale facts, default isolation,
zero-call proof, hosted coverage, and impact-routed architecture, security, QA and product/operations reviews, plus tracks affected by the actual diff.
