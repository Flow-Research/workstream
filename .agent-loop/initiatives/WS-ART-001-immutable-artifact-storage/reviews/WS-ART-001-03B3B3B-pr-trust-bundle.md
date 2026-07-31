# WS-ART-001-03B3B3B PR Trust Bundle

## Chunk

`WS-ART-001-03B3B3B` — DOCX Extractor (L1).

## Goal and human-approved intent

Add deterministic, bounded DOCX text and table extraction after exact DOCX
classification and the merged OOXML security boundary. Preserve original
verified guide bytes as authoritative. This hidden chunk must not activate
AUTH, invoke guide sufficiency, add other formats, or touch contributor ZIPs.

## What changed and why

- Added an isolated DOCX adapter that emits compact sorted JSON blocks in
  document order with fixed paragraph, row, cell, and nested-table semantics.
- Added a fixed omission schema for headers, footers, comments, deletions,
  passive objects, hidden text, and field instructions.
- Advanced DOCX evidence to `guide-extraction-v3` and bound omission facts to
  immutable persistence and replay checks.
- Reused the existing worker-owned OOXML validator loader and kept both the
  validator and DOCX adapter imports confined to the isolated child.
- Added focused tests, the existing hosted semantic lane assignment, and the
  exact storage-service contract.

## Design chosen and alternatives rejected

The isolated worker composes the shared OOXML validator with the DOCX adapter
before descriptor-only seccomp. The adapter receives an explicit validator,
then parses only validated `word/document.xml` and bounded style facts. The
parent accepts only the exact result and omission schemas. Rejected alternatives
were upload-request parsing, direct provider access, a second OOXML validation
path, raw binary agent input, partial output, or generic document authority.

## Scope control and product behavior

Only hidden guide-source extraction changes. There is no route, authorization
activation, Celery continuation, sufficiency invocation, provider read, guide
binding, submission, checker, review, contribution, payment, or reputation
change. Unsupported and malformed content remains a bounded internal artifact
outcome, not a guide-insufficiency decision.

## Acceptance criteria proof

- Paragraphs, hyperlinks, tabs, breaks, tables, cells, nested tables, and empty
  structures have exact canonical output tests.
- Headers, footers, comments, tracked deletion/move-from content, passive
  objects, fields, direct/inherited style-hidden text, and document-default
  hidden text are omitted and recorded.
- Active content and malformed XML fail through stable bounded outcomes.
- Exact output-limit behavior returns no partial usable result.
- The real isolated runner proves v3 policy, omission transport, and scratch
  cleanup; architecture tests prove worker-only adapter/validator imports.
- Persistence tests bind canonical output and omission facts and reject obsolete
  policy evidence as a replay target.

## Tests and checks

- Ruff and approved extractor-dependency gate — pass.
- Focused DOCX/OOXML/extraction/architecture/lane suite — 151 passed.
- DOCX module coverage — 95.02 percent (9 tests).
- Stale artifact contracts, stale wording, Markdown links, lane integrity, and
  `git diff --check` — pass.
- Hosted Backend/Agent Gates retain DB-backed replay, repository-wide coverage,
  and semantic-lane proof; no local full-suite run was used.

## Test delta and CI integrity

No test, assertion, lane, workflow, dependency rule, or coverage threshold was
removed, skipped, or weakened. Invalid result-shape fixtures carry valid
omission facts so they still reach their intended validation branches. The new
DOCX module joins the existing `shared_foundations` lane.

## Reviewer results

Architecture, CI integrity, test delta, and docs pass. Security, QA, senior
engineering, product/ops, and reuse/dedup pass with only documented low risks.
All blocking deletion traversal, hidden-style cascade, isolated-runner, shared-
loader reuse, protocol-test, and documentation findings were repaired and
re-reviewed.

## External review

The first Agent Gates run found two stale human-worker vocabulary matches; both
now use the exact isolated-child result-protocol wording and the local gate
passes. The first Backend run exposed a nondeterministic raw-ZIP pytest ID;
explicit stable format IDs now produce identical repeated collections.
CodeRabbit's first attempt was rate-limited without code findings and must be
retriggered. Hosted checks remain required on the repaired PR head.

## Remaining risks and follow-up

DOCX has a large visibility model; this chunk intentionally supports a bounded
subset and treats `w:vanish` presence conservatively, including explicit false
values. Future formats should reuse the same isolated result protocol without
growing duplicated schemas. PPTX/XLSX, durable sufficiency continuation, and
AUTH activation remain separate later chunks.

## Human review focus and merge ownership

Review exact canonical ordering/separators, omission semantics, injected shared
OOXML validation, v3 replay identity, isolation, and absence of AUTH or
sufficiency activation. A human owns merge approval; the agent will not merge
this PR.
