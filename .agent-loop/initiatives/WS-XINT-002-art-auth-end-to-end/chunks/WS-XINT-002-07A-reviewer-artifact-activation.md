# Chunk Contract: WS-XINT-002-07A — Reviewer Artifact Activation

## Goal

Activate exact lease-scoped packet materialization and the single evidence-binding ActionId for reviewer-finding slots only.

## Boundary

This is the only availability transition for `artifact.review_evidence.binding.create`. It also activates `artifact.review_packet.materialize`. The fixed identities are `workstream.artifact.binding` and `workstream.artifact.materializer`. Human review actions remain with XINT-003.

## Acceptance criteria

- Packet materialization binds reviewer reference, active lease, packet manifest, Submission, checker, guide/policy, verified content, session, transaction, request, and decision evidence.
- Evidence binding accepts only server-derived `reviewer_finding` mode with the exact lease/finding slot and verified content commitment.
- `contributor_response` and every CheckerRun-rooted remediation shape hard deny even when the ActionId is active.
- Wrong, stale, revoked, replayed, copied, or cross-resource facts deny before byte disclosure or durable mutation.
- Human and fixed-service evidence commits atomically with the protected REV/ART operation. Prepared handles never enter a job payload.

## Stop

Do not add response-slot evaluation or activate human REV actions.
