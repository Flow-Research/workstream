# Chunk Contract: WS-XINT-003-09 — REV-AUTH Conformance And Release

## Status and risk

Non-implementable planning skeleton after 02 through 08B. Refresh exact files
and commands on current main before an explicit user request. L1 coherent
product release.

## Goal

Prove the complete review/revision authorization chain and permit REV's one
planned product-router release point without adding new behavior.

## Allowed files

Exact conformance/drill tests, route composition and manifests, release docs,
AUTH/REV status/evidence, and narrowly required defects found by the proof.

## Not allowed

New actions, permissions, roles, services, lifecycle states, compatibility
paths, feature expansion, adjudication, reputation, or unreviewed defect work.

## Acceptance criteria

- Static manifests prove every review/revision route and command has exactly one
  active ActionId and every action has exactly its intended principal/surface.
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

## Verification and reviewers

Complete hosted suite/API drills, stale scans, markdown links, migration-head
proof, all L1 internal reviewers, and external PR review.

## Stop

Human merge only. Do not begin a later initiative automatically.
