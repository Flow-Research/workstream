# Chunk Contract: WS-AUTH-001-12H - Unified Guide Activation Cutover

Status: Proposed after POL-07, corrected 12B2, CP05 active
ContributionPolicy behavior, CP06 validation, and CP07 ProjectGuide binding;
inactive. Risk: L1. CP08, WS-ARCH-001-03A/03B/03C, and CP09 are downstream and
are not prerequisites.

## Goal

Activate only `project.guide.activate` over one complete approved
current-generation unified compilation chain.

## Allowed files

AUTH catalogue/kernel/PREP/runtime/API composition, project activation
authorization adapter/resource context, one AUTH-owned parity/provenance
migration if required, focused tests, specifications, and AUTH/POL memory.

## Not allowed

Compilation, policy derivation/approval/compiler semantics, agent calls, ART
provider behavior, CON redesign, task/submission/review activation, legacy
chain compatibility, or issuer-role fallback.

## Acceptance

- Entry requires exact immutable `ProjectGuideCompilation`, accepted result and
  sufficiency/artifact/pre/post component hashes, source/setup generation, both
  catalogue snapshots, approved effective/pre/post projections, and completed
  unified setup custody.
- Required capability gaps or any blocked/partial/unapproved/mixed-generation
  component deny. Optional gaps require exact PM acknowledgement.
- Final PREP binds the complete chain plus actor/link/grant, action, operation,
  request/idempotency, session, and transaction. POL/project code owns product
  locks and the one activation commit.
- The exact CP07 `ProjectGuide.contribution_policy_version_id` binding is
  present, current for the activation lineage, and validated through CP06
  against CP05 active behavior. Retired guide-bound economic fields grant no
  authority and are ignored by this activation path; CP09 removes them only
  after WS-ARCH-001-03C activates the replacement task/assignment path.
- The merged POL-07 single checker port proves both compiled pre-submit and
  post-submit components are executable through the sole approved commands;
  activation cannot precede that proof.
- No old independent sufficiency/submission/post rows are sufficient without
  compilation/component linkage; no compatibility authorization remains.
- Concurrent activation yields one active guide. Stale/replaced/revoked/replay/
  copied/wrong-handle/session/transaction cases deny before mutation.

## Verification and review

Complete/partial/mixed-chain matrix, gap acknowledgement, concurrency/replay,
AUTH all-pairs, POL-07 sole-port and activation integration, migration round trip, hosted
coverage, and all L1 tracks. Human focus: complete unified lineage only.
