# WS-ART-001-04C1 Planning Correction PR Trust Bundle

## Chunk

`WS-ART-001-04C1` planning correction only.

## Goal And Human Intent

Make the next ART durable-put chunk implementable without losing the guarantee
that the checked ZIP, durable storage intent, later verified admission, and
eventual Submission all refer to the same exact lineage.

## What Changed And Why

Preimplementation review proved the generic `ArtifactPutAttempt` row alone
could not reconstruct actor, assignment, predecessor, manifest, evidence, and
locked-policy lineage for 04C2 after process loss. The corrected contract adds
one narrow `SubmissionBundleDurableIntent` joining the immutable passing
evidence set to the generic put attempt before provider I/O.

The correction also fixes the pre-intent crash rule: old evidence never remints
process-local authority; recovery requires complete reupload and checker
execution with a new prepared generation and evidence identity.

## Design Chosen

- Unique foreign keys from the intent to `PreSubmitEvidenceSet` and
  `ArtifactPutAttempt`; no duplicate lineage blob or request-digest parsing.
- Live `PreparedArtifact` plus single-use `PreSubmitPassCapability` remain
  required for the mutation.
- Typed TASK/PROJECT locks and opaque AUTH PREP consumption commit with the
  intent, provisional capacity, authorization evidence, and put attempt.
- Provider I/O occurs only after commit and reuses existing generic
  observation/recovery.
- Production contributor preparation stays unavailable until XINT-05A.

Rejected alternatives were generic metadata, parsing the request digest,
persisting scratch/handles, reminting authority from evidence, and adding a
submission-specific recovery path.

## Scope Control And Product Behavior

Changed only ART planning, status, chunk contracts, normative specification,
and review evidence. No runtime behavior changes. 04C1 still excludes ready
admission publication, Submission/binding, public routes, review/contribution,
retention/deletion, provider redesign, and AUTH availability.

## Acceptance Proof And Checks

- `git diff --check`: passed.
- stale artifact contract scan: passed.
- Markdown link scan across six changed files: passed.
- Test delta: none; planning-only.
- CI integrity: no workflow, command, coverage, or dependency change.

Internal architecture, security/auth, product/ops, QA, senior-engineering, and
docs plan reviews passed after all material findings were incorporated.
External CI and CodeRabbit remain pending after PR publication.

## Remaining Risks And Follow-Up

Implementation must keep the intent row narrow, update shared put-attempt
constraints safely, prove guide continuation ignores submission attempts, and
demonstrate provider I/O cannot occur before the durable transaction commits.
After this planning PR merges, implement 04C1; 04C2 remains separate.

## Human Review Focus And Merge Ownership

Confirm the durable intent is necessary and sufficiently narrow, and that the
crash/replay wording never permits durable evidence to become mutation
authority. Human approval owns merge; the agent will not merge this PR.
