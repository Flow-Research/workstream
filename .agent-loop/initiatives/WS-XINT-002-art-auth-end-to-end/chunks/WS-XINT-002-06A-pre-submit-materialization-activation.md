# Chunk Contract: WS-XINT-002-06A — Pre-Submit Materialization Activation

Parent initiative: `WS-XINT-002` | Risk: L1 | Status: Proposed after ART-04B

## Goal

Activate only the fixed pre-submit checker materializer before contributor
preparation can become available.

## Allowed Files

AUTH catalogue/matrix/composition, ART authorization adapter/resource facts,
pre-submit checker materialization integration, focused tests/docs/CI evidence.

## Not Allowed Changes

Contributor preparation activation, post-submit reads, checker output writes or
bindings, human checker authority, generic artifact reads, or new ActionIds.

## Acceptance Criteria

- only `artifact.pre_submit.checker_input.materialize` changes availability;
- only the fixed pre-submit materializer identity may prepare and consume it;
- authority binds the process-local prepared-bundle/scratch generation,
  task/project/guide/locked policy, archive/manifest, checker definition,
  server-selected ArtifactStore storage scheme, request, session, and
  transaction facts; no durable admission exists yet;
- denial/replay/stale/cross-resource cases fail before scratch exposure;
- prepared handles never enter Celery payloads.

## Verification Commands

Focused AUTH/ART/checker tests, stale auth/artifact scans, coverage, and hosted
Backend/Agent Gates.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Confirm this one activation precedes XINT-05A. Stop before contributor or
post-submit action activation.
