# WS-ART-001-03B3B3D PR Trust Bundle

## Chunk

`WS-ART-001-03B3B3D` — XLSX Extractor (L1).

## Goal and human-approved intent

Add deterministic, bounded XLSX guide extraction after exact XLSX
classification and the shared OOXML security boundary. Preserve the verified
workbook bytes as authoritative. This hidden chunk must not activate AUTH,
invoke guide sufficiency, change contributor submission ZIP processing, or
start later image and Celery work.

## What changed and why

- Added an isolated standard-library XLSX adapter with exact workbook,
  relationship, worksheet, cell, formula-cache, shared-string, merge, and
  omission semantics.
- Advanced XLSX evidence to `guide-extraction-v5` and extended the fixed worker
  result protocol without changing existing format behavior.
- Added bounded semantic accumulation and an exact final 4 MiB canonical-output
  check, in addition to the existing child process limits.
- Added a dedicated XLSX test module, hosted semantic-lane membership,
  architecture confinement proof, DB-backed persistence/replay cases, and the
  corresponding artifact-storage specification.

## Design chosen and alternatives rejected

The adapter receives the exact immutable payload only after the worker-owned
shared OOXML validator accepts it. It then resolves a single namespace-family
workbook graph and emits compact canonical JSON. Formula source and typed
caches are preserved but never evaluated. Rejected alternatives were direct
provider access, request-path parsing, generic ZIP extraction, raw workbook
input to an agent, caller MIME trust, partial output, a new dependency, or a
second authorization/OOXML protocol.

## Scope control and product behavior

Only hidden guide-source extraction changes. There is no route, AUTH action,
Celery continuation, sufficiency decision, provider read, binding mutation,
submission, checker, review, contribution, payment, or reputation change.
Artifact parser failures remain bounded extraction outcomes and are not guide
insufficiency decisions.

## Acceptance criteria proof

- Transitional and Strict workbook families, canonical worksheet order,
  `very_hidden` normalization, coordinate sorting, scalar types, formula
  caches, shared/inline strings, and merged ranges have deterministic tests.
- Duplicate IDs, targets, cells and ranges; orphan or cross-root parts; mixed
  namespaces; invalid grid coordinates; unsafe formulas; and unsupported cell
  shapes fail with stable codes.
- Every fixed omission category has an independent trigger test, and a real
  isolated-child test proves a true omission map survives the worker protocol.
- Exact policy constants and boundary transitions cover 100 worksheets,
  100,000 rows, 1,000,000 cells, 32,768 characters, 64 XML levels, and 4 MiB
  output without publishing partial evidence.
- Architecture tests prove the adapter is imported in production only by the
  isolated extraction worker; persistence tests bind v5 output and reject
  obsolete replay policy.

## Tests and checks run

- Ruff and the approved guide-extractor dependency gate — pass.
- Focused OOXML/XLSX/extraction command — 177 passed; XLSX branch coverage
  90.94 percent.
- Lane/dependency/OOXML/XLSX/extraction/architecture suite — 262 passed.
- Stale artifact contracts, Markdown links, and `git diff --check` — pass.
- DB-backed replay and repository-wide 78 percent coverage remain assigned to
  the hosted Backend/Agent Gates; no local full-suite run was used.

## Test delta and CI integrity

No test, assertion, lane, workflow, dependency rule, or coverage threshold was
removed, skipped, or weakened. The dedicated XLSX module joins the existing
`shared_foundations` lane. The focused 90 percent changed-subsystem check and
the separate hosted 78 percent repository baseline remain explicit.

## Reviewer results

Architecture, security, QA, senior engineering, product/ops, reuse/dedup, CI
integrity, test-delta, and docs reviews pass, with only documented low residual
risks. Findings for merged-cell
precedence, namespace ambiguity, omission completeness, duplicate identities,
failure taxonomy, output accumulation, documentation precision, and missing
focused proof were repaired and re-reviewed.

## External review

CodeRabbit and hosted GitHub checks have not yet reviewed the branch. Their
results supplement but do not replace the completed internal review, and all
valid findings must be repaired before human merge approval.

## Remaining risks and follow-up work

The expensive row/cell thresholds are proven using exact constants and shared
counter transition tests instead of materializing million-cell local fixtures;
the hosted suite retains integration proof. Image metadata, durable
sufficiency continuation, AUTH activation, and legacy cutover remain separate
later chunks.

## Human review focus and merge ownership

Review relationship ownership and family consistency, formula/cache semantics,
omission evidence, bounded accumulation, v5 replay identity, and the absence of
AUTH or sufficiency activation. A human owns merge approval; the agent will not
merge this PR.
