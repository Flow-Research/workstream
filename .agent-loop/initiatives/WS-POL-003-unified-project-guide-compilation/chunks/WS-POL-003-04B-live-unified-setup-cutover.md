# Chunk Contract: WS-POL-003-04B - Live Unified Setup Cutover

Status: Proposed after merged 04A3, 04A2, AUTH-12J, and AUTH-12B2; inactive.
Risk: L1.

## Goal

Make the unified setup service the sole live inference path by invoking the
already-hidden compilation, component-projection, and setup-finalization
operations in order. 04B does not persist a second projection or authorize a
second projection path.

## Allowed files

Project setup-service/queue/composition, authenticated PM request surface,
legacy reachability guards/removal, focused tests, specifications, and
WS-POL-003 docs. Exact files remain to be frozen on then-current main.

## Not allowed

Approval/pre effective mutation, post canonical projection, checker execution,
compatibility routing, or a second provider attempt/key.

## Acceptance

- Live orchestration invokes only `compile_project_guide`.
- Live orchestration calls the merged hidden sufficiency projection, artifact
  policy projection, and finalization operations; 04A3/12J and 04A2/12B2 remain
  the sole owners of their authorization and atomic persistence.
- All three old model methods/prompts are unreachable for unified generations;
  no deferred legacy post call or fallback exists.
- Complete replay returns canonical outputs with zero provider calls.

## Verification and review

Real PostgreSQL/Celery/API cutover, static reachability, one-attempt replay,
projection atomicity, hosted coverage, and all L1 tracks. Human focus: clean
one-call cutover with reusable, not borrowed, projection authority.
