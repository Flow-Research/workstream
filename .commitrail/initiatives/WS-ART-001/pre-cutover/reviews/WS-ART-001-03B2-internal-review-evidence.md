# Internal Review Evidence: WS-ART-001-03B2

## Scope

Hidden fixed-reader materialization of exact verified guide-source bytes,
bounded syntactic classification, and ART-owned custody incidents. No AUTH
activation, extraction, agent invocation, Celery continuation, generic
download, or legacy cutover is included.

## Deterministic Evidence

- Ruff passed for `app`, `tests`, `scripts`, and migration `0040`.
- Focused format, architecture, and scratch inspection tests passed.
- The isolated PostgreSQL runner migrated through `0040` and passed all 13
  materialization-selected guide-binding tests, including denial before I/O,
  namespace drift, full rehash, replay, changed/truncated/stale incidents,
  cancellation, and timeout cleanup.
- Canonical lane collection accepted `test_guide_formats.py` in
  `shared_foundations`; the CI-integrity reviewer collected 2,316 nodes.
- Stale artifact-contract, changed Markdown-link, lightweight agent-gate, and
  `git diff --check` checks passed.
- Hosted Backend and Agent Gates remain required on the exact committed PR
  head; no local full-suite run was used.

## Findings And Repairs

- Architecture: shared the existing replica/namespace/store validator with the
  canonical `ArtifactMaterializationService`, and narrowed scratch inspection
  to a typed ART-owned inspector.
- Security: replaced substring relationship checks with bounded XML parsing;
  malformed XML, DOCTYPE, and whitespace-equivalent external relationships
  now fail closed.
- QA/test: added changed and stale-generation incidents, exact cross-resource
  denial, cancellation/timeout cleanup, fixed-limit arithmetic, ambiguous and
  malformed containers, video signatures, JPEG, WebP variants, and both
  classification-only and incident-only populated downgrade refusal.
- Senior engineering/reuse: added exact verification-job replica/terminal
  lineage, inspection deadline mapping, model/migration constraint-name parity,
  and shared namespace validation.
- Docs/product/ops: documented migration `0040`, evidence custody, populated
  downgrade refusal, and the no-new-Operator-route boundary. Artifact incidents
  remain separate from guide insufficiency.

## Final Reviewer Results

- Architecture: PASS WITH LOW RISKS.
- Security/auth: PASS.
- QA/test: PASS WITH LOW RISKS.
- Product/ops: PASS.
- CI integrity: PASS WITH LOW RISKS.
- Docs: PASS.
- Reuse/dedup: PASS WITH LOW RISKS.
- Test delta: PASS WITH LOW RISKS.
- Senior engineering: final confirmation recorded before PR publication.

Residual low risks are limited to the canonical materializer facade currently
implementing only the 03B2 guide-read slice, a structurally typed scratch
inspector, and repeated focused-test scratch setup. Later ART chunks must extend
the same facade and custody boundaries.
