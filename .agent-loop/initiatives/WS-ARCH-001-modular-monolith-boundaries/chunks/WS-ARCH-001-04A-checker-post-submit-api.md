# Chunk Contract: WS-ARCH-001-04A CHECKER Post-Submit API

Status: non-executable planning skeleton after POL-07 and 03C. Risk: L1.
Outcome: CHECKERS owns the single post-submit API and phase-command contract
for consuming and publishing immutable execution facts. Chunk 04C owns durable
final-result/currentness persistence; 04E owns the durable `allow_review`
routing manifest.

Allowed: `backend/app/modules/checkers/api/**`, focused CHECKER-owned
implementation/tests, boundary ledgers and initiative evidence/status. Not
allowed: ART provider access, TASK transitions, AUTH activation, REV admission,
ORM leakage, generic checker payloads or a second checker catalogue.

This extends the single POL-003 checker-service port and its complete
`evaluate_post_submission(...)` phase command. It must not add another
dispatcher, phase API, catalogue, caller-selectable checker path, or execution
surface.

Acceptance: facts bind the approved unified generation and closed checker
catalogue; only one final current result can authorize routing; stale,
superseded or partial results deny. Verify contract/unit tests, property tests
for canonical hashes, boundary validators, Ruff and hosted coverage. Required
reviews: architecture, security, product/ops, QA, senior and reuse.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
