# Chunk Contract: WS-ART-001-07B — Contribution Artifact Identity Handoff

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 07A

## Goal

Expose the immutable accepted Submission artifact identity that CON can record
without provider I/O or ART ownership of contribution lifecycle.

## Allowed Files

Typed read-only identity/provenance contract, acceptance-binding guards,
integration tests, docs, and scoped CI evidence.

## Not Allowed Changes

Contribution creation/state, compensation, reputation, review acceptance logic,
provider reads, delivery/export, generic download, or AUTH activation.

## Acceptance Criteria

- the handoff identifies accepted Review, Submission, binding, content digest,
  byte count, manifest digest, and locked policy/checker provenance;
- non-accepted, stale, mismatched, or unverified lineage fails closed;
- the contract performs no provider I/O and grants no byte-reading authority;
- CON remains the owner of ContributionRecord lifecycle.

## Verification Commands

Focused identity, accepted-state, cross-resource, no-provider-I/O, coverage, and
hosted Backend/Agent Gates.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Review ownership and provenance. Stop before CON implementation or delivery.
