# Chunk Contract: WS-XINT-003-09 — REV-AUTH Conformance And Release Readiness

## Status and risk

Non-implementable planning skeleton after 02 through 08B. Refresh exact files
and commands on current main before an explicit user request. L1 coherent
release readiness. REV-13C alone releases product routes.

## Goal

Prove the complete review/revision authorization chain and publish the exact
readiness manifest consumed by REV-13C without adding behavior or registering a
product route.

## Allowed files

Exact conformance/drill tests, route-declaration scans and readiness manifests, release docs,
AUTH/REV status/evidence, and narrowly required defects found by the proof.

## Not allowed

New actions, permissions, roles, services, lifecycle states, compatibility
paths, feature expansion, adjudication, reputation, or unreviewed defect work.

## Acceptance criteria

- Static readiness manifests prove every candidate review/revision route and
  command declaration maps to exactly one intended active ActionId and
  principal/surface without registering a product router.
- End-to-end drills cover policy configuration; checker admission; queue/claim;
  packet/context; evidence; all three decisions; human revision N+1 and return;
  distinct CheckerRun-rooted remediation that creates no Review, finding,
  preparation, or reviewer contribution and returns through checker admission;
  revocation/expiry/reassignment; Project Manager/Operator recovery; fixed-service
  retry; projection; artifact outage/integrity failure; contribution/award
  source integrity with no reputation side effect; controlled shutdown, drain,
  crash resume, coherent reactivation; and lifecycle release.
- The universal mutation matrix proves forged, copied, replayed, and already-
  consumed handles; wrong session, transaction, action, actor, or fixed service;
  cross-project, task, Submission, lease, or Review; self-review and wrong role;
  stale lease, packet, predecessor, preparation, or policy; expired or revoked
  authority; and concurrent consumption all fail closed with no partial
  product, CON, audit, or outbox state.
- No token-role, direct grant-query, generic artifact-read, serialized PREP, or
  alternate authorization path remains.
- Hosted full coverage, per-subsystem floors, internal reviewers, CodeRabbit,
  and GitHub checks pass on the exact head before human merge.
- Product routers remain unregistered. REV-13C consumes this readiness evidence
  and is the sole product-router registration/final HTTP proof.

## Verification and reviewers

Complete hosted suite/API drills, stale scans, markdown links, migration-head
proof, all L1 internal reviewers, and external PR review.

## Stop

Human merge only. Do not begin a later initiative automatically.
