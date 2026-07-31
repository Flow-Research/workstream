# WS-ART-001-03B3B3C PR Trust Bundle

## Chunk

`WS-ART-001-03B3B3C` — PPTX Extractor (L1).

## Goal and human-approved intent

Add deterministic, bounded PPTX slide and notes extraction after exact PPTX
classification and the merged OOXML security boundary. Preserve original
verified guide bytes as authoritative. This hidden chunk must not activate
AUTH, invoke guide sufficiency, add XLSX/image behavior, or touch contributor
submission ZIPs.

## What changed and why

- Added an isolated PPTX adapter with exact presentation-order slide and notes
  extraction, deterministic compact JSON, and fixed omission evidence.
- Advanced PPTX evidence to `guide-extraction-v4` and bound its complete result
  schema to immutable persistence and replay checks.
- Reused the worker-owned shared OOXML validator and kept the PPTX adapter
  import confined to the isolated child.
- Added the canonical semantic lane, architecture and worker-order proofs,
  DB-backed replay cases, and the exact storage-service contract.

## Design chosen and alternatives rejected

The adapter accepts only bytes that pass the shared OOXML boundary. It resolves
the exact presentation relationship graph, traverses only approved shape-tree
text bodies and tables, and returns canonical content plus a fixed omission
map. Rejected alternatives were request-path parsing, direct provider access,
generic ZIP handling, raw binary agent input, broad XML scanning, partial
output, or a second authorization/OOXML protocol.

## Scope control and product behavior

Only hidden guide-source extraction changes. There is no route, authorization
activation, Celery continuation, sufficiency invocation, provider read, guide
binding, submission, checker, review, contribution, payment, or reputation
change. Artifact/parser failures remain bounded internal outcomes rather than
guide-insufficiency decisions.

## Acceptance criteria proof

- Presentation order, grouped shapes, tables, notes ownership, exact paragraph
  semantics, Strict/Transitional relationships, and empty structures have
  deterministic canonical-output tests.
- Masters, comments, hidden metadata, passive non-text objects, and embedded
  objects use an exact boolean omission schema bound to v4 evidence.
- Malformed relationship roots, duplicates, dangling/cross-root targets,
  orphans, shared ownership, namespace mixing, and invalid parts fail closed.
- Exactly 300 slides pass; 301 slides, depth beyond 64, and output beyond 4 MiB
  fail without partial agent input.
- The isolated runner proves v4 protocol transport and scratch cleanup;
  architecture tests prove worker-only adapter imports.
- Persistence tests bind canonical output and complete omission facts and reject
  obsolete PPTX policy evidence as a replay target.

## Tests and checks

- Ruff and approved extractor-dependency gate — pass.
- Focused OOXML/PPTX/extraction/architecture/lane suite — pass.
- PPTX module branch coverage — 94.43 percent (21 tests).
- Stale artifact contracts, Markdown links, lane integrity, and
  `git diff --check` — pass.
- Hosted Backend/Agent Gates retain DB-backed replay, repository-wide coverage,
  and semantic-lane proof; no local full-suite run was used.

## Test delta and CI integrity

No test, assertion, lane, workflow, dependency rule, or coverage threshold was
removed, skipped, or weakened. The new PPTX module joins the existing
`shared_foundations` lane. No dependency or workflow file changed.

## Reviewer results

Architecture, security, senior engineering, CI integrity, test delta, and docs
pass. QA, product/ops, and reuse/dedup pass with only documented low risks. All
blocking traversal, non-text leakage, relationship, visibility, depth, and
contract/test findings were repaired and re-reviewed.

## External review

CodeRabbit and hosted GitHub checks have not yet run on the committed PR head.
They remain required before human merge approval.

## Remaining risks and follow-up

DB-backed replay and repository-wide coverage evidence is hosted-only. If the
next XLSX adapter repeats the small OOXML loader or serializer patterns, assess
a bounded shared helper then rather than widening this chunk. XLSX, image,
durable sufficiency continuation, AUTH activation, and legacy cutover remain
separate later chunks.

## Human review focus and merge ownership

Review exact relationship ownership/order, structure-aware text eligibility,
omission semantics, v4 replay identity, depth/output limits, and absence of AUTH
or sufficiency activation. A human owns merge approval; the agent will not
merge this PR.
