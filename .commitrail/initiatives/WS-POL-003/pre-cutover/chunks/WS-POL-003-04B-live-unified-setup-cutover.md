# Chunk Contract: WS-POL-003-04B - Live Unified Setup Cutover

Status: Proposed after 04A and AUTH-12B2; inactive. Risk: L1.

## Goal

Make the unified setup service the sole live inference path and persist the
complete compilation plus canonical sufficiency/artifact-policy projections.

## Allowed files

Project setup-service/queue/composition, projection repositories, exact
12E/12F action adapters, focused tests, specifications, and WS-POL-003 docs.

## Not allowed

Approval/pre effective mutation, post canonical projection, checker execution,
compatibility routing, or a second provider attempt/key.

## Acceptance

- Live orchestration invokes only `compile_project_guide`.
- Sufficiency and artifact-policy projections each consume fresh action-bound
  PREP in their own atomic transaction. Each PREP binds the immutable
  compilation and accepted-result hashes plus its exact sufficiency or
  artifact-policy component hash.
- All three old model methods/prompts are unreachable for unified generations;
  no deferred legacy post call or fallback exists.
- Complete replay returns canonical outputs with zero provider calls.

## Verification and review

Real PostgreSQL/Celery/API cutover, static reachability, one-attempt replay,
projection atomicity, hosted coverage, and all L1 tracks. Human focus: clean
one-call cutover with reusable, not borrowed, projection authority.
