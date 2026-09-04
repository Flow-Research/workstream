# Chunk Contract: WS-ART-001-07A — Exact Reviewer Packet Materialization

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after XINT-06B

## Goal

Provide an authorized, bounded reviewer packet for one exact immutable
Submission without moving review decisions, notes, or routing into ART.

## Allowed Files

Existing `ArtifactMaterializationPort.materialize_bindings(...)` and
`BindingMaterializationRequest` convention, immutable reviewer-packet resource
manifest, ArtifactStore/ScratchManager integration, focused tests/docs/CI.

## Not Allowed Changes

Review queues, assignments, leases, decisions, findings/note storage, reviewer
artifact upload, contribution lifecycle, generic download, or AUTH activation.

## Acceptance Criteria

- packet resolution binds task, Submission, artifact binding, content, manifest,
  checker evidence, and locked policy facts;
- fresh fixed reviewer-reader service authority is consumed before provider I/O;
- every full read recomputes and verifies digest and byte count;
- stale/replaced/cross-resource/unverified input fails before byte exposure;
- reviewer decisions remain only `accept`, `needs_revision`, or `reject`, with
  their note/findings related to the reviewed immutable Submission aggregate.

## Verification Commands

Focused auth, integrity, cross-resource, scratch cleanup, packet provenance,
coverage, and hosted Backend/Agent Gates.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Confirm ART supplies exact bytes only. Stop if reviewer-uploaded evidence or
review lifecycle ownership appears.
