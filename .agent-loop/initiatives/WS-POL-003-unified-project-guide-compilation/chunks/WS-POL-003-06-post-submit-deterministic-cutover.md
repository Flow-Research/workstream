# Chunk Contract: WS-POL-003-06 - Deterministic Post-Submit Cutover

Status: Proposed after 05. Risk: L1.

## Goal

Compile the stored unified post-submit proposal after effective/pre-submit
approval without rereading the guide or invoking a second model.

## Allowed files

Project post-submit policy/compiler/Celery/repository surfaces, exact AUTH-12G
composition, the one CHECKER/POL project capability catalogue, focused tests,
and WS-POL-003 docs.

## Not allowed

Checker execution, review/revision behavior, new checker registration, default
checker repetition, manual reuse of agent provenance, or ART changes.

## Acceptance

- Continuation performs zero model invocations.
- Exact compilation, effective policy, pre-submit plan, catalogue, and setup
  generation are locked and revalidated.
- Any correction/replacement/catalogue change invalidates the proposal.
- Platform-default repetition and unknown/wrong-stage checkers fail closed.
- Only registered project entries from the canonical durable CHECKER/POL
  post-submit source are selectable; ART pre-submit entries cannot be selected.
- Tests explicitly reject current legacy behavior that repeats any durable
  default in either required or warning project bindings.
- Compiled post-submit policy retains separate PM approval.

## Verification and review

Zero-call, invalidation, replay, approval-race, default-isolation, and atomic
evidence tests. Runtime dispatch is owned by later consumers of the chunk-07
port. Required reviewers: all L1 tracks.
