# Chunk Contract: WS-POL-003-05B - Live Pre-Submit Approval

Status: Proposed after 05A and AUTH-12F4; inactive. Risk: L1.

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

## Verification and review

PostgreSQL approval races, replay/revocation/stale facts, default isolation,
zero-call proof, hosted coverage, and all L1 tracks.
