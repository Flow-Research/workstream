# Chunk Contract: WS-XINT-002-06A — Pre-Submit Materialization Activation

Parent initiative: `WS-XINT-002` | Risk: L1 | Status: Active after merged ART-04B3 and AUTH-12F2

## Goal

Activate only the fixed pre-submit checker materializer before contributor
preparation can become available.

## Allowed Files

- `backend/app/modules/authorization/catalogue.py`
- `backend/app/modules/authorization/runtime.py`
- `backend/app/modules/authorization/kernel.py`
- `backend/app/modules/authorization/prepared.py`
- `backend/app/modules/audit/schemas.py`
- `backend/app/modules/artifacts/authorization.py`
- `backend/app/modules/artifacts/submission_materialization.py`
- focused authorization/materialization tests under `backend/tests/`
- canonical AUTH/ART/XINT status, chunk, specification, and review evidence
- hosted CI metadata only when required to run the existing gates; the gates
  and coverage thresholds may not be weakened

## Not Allowed Changes

Contributor preparation activation, post-submit reads, checker output writes or
bindings, human checker authority, generic artifact reads, or new ActionIds.

## Acceptance Criteria

- only `artifact.pre_submit.checker_input.materialize` changes availability;
- only the fixed pre-submit materializer identity may prepare and consume it;
- authority binds the process-local prepared-bundle/scratch generation,
  exact active assignment identity, task, project,
  effective submission-artifact policy, pre-submit checker policy, plan and
  catalogue hashes, archive digest and byte count, semantic-manifest hash,
  server-selected ArtifactStore storage scheme, request, session, and
  transaction facts; no durable admission exists yet;
- assignment currentness is revalidated from the locked assignment row by the
  ART-04C1 caller before it prepares these facts; `TaskAssignment` has no
  generation field, so 06A must not invent a parallel assignment version;
- cheap scalar lineage and digest consistency checks run before authorization
  consumption without reading artifact bytes;
- service/action/lifecycle/scope denial occurs during PREP before
  `PreparedArtifact.inspect()` or ZIP open; after inspection, final consumption
  binds the server-computed semantic manifest and rejects replay or exact-fact
  drift before workspace reservation/creation, projected checker facts,
  checker dispatch, or provider access;
- prepared handles never enter Celery payloads.

## Verification Commands

Focused AUTH/ART/checker tests, stale auth/artifact scans, coverage, and hosted
Backend/Agent Gates.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Confirm this one activation follows merged ART-04B3 and AUTH-12F2 and unblocks
ART-04C1. Stop before contributor preparation/admission, `Submission`,
post-submit materialization, checker-output, review-packet, or generic-read
activation. After 06A merges, ART may execute 04C1 then 04C2 while AUTH resumes
at 12F3; neither successor is part of this chunk.
