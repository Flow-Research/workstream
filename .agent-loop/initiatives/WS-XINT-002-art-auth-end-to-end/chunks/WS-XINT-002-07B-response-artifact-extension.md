# Chunk Contract: WS-XINT-002-07B — Response Artifact Evaluator Extension

## Goal

Extend the already-active `artifact.review_evidence.binding.create` evaluator to human-revision response slots after the exact REV obligation and preparation exist.

## Boundary

This chunk changes no ActionId availability, registers no action, and creates no identity. It reuses `workstream.artifact.binding` and the existing opaque transaction-bound prepared authorization. Human response authority remains with XINT-003-07; shared Submission actions remain with XINT-002-05D.

## Acceptance criteria

- Server-derived `contributor_response` mode binds `Review(needs_revision)`, unresolved finding/response slot, obligation, preparation head/digest, contributor assignment, predecessor Submission, deadline/round, guide/policies, verified content, session, transaction, request, and decision evidence.
- CheckerRun-rooted remediation, wrong service/action/mode, stale preparation, predecessor advancement, expired/exhausted obligation, copied/replayed handle, and cross-resource facts fail closed before durable mutation.
- ART binding and the human REV mutation commit or roll back together. The binding service cannot create a Submission or inherit contributor authority.

## Stop

Do not change catalogue availability or add generic artifact access.
