# Chunk Contract: WS-ART-001-03B3B3D — XLSX Extractor

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Add deterministic bounded XLSX cell extraction using only the approved OOXML capability.

`WS-ART-001-03B3B1` and `WS-ART-001-03B3B3A` are hard predecessors. Package
installation and imports fail closed unless the merged protected GitHub approval baseline matches
the exact pinned allowlist.

## Approved plan reference

- PLAN: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md`

## Risk class

L1

## SLA

P2

## Allowed files

```text
backend/app/modules/artifacts/guide_xlsx.py
backend/app/modules/artifacts/guide_extraction.py
backend/app/modules/artifacts/guide_extraction_worker.py
backend/scripts/run_test_lanes.py
backend/tests/test_artifact_architecture.py
backend/tests/test_guide_bindings.py
backend/tests/test_guide_extraction.py
backend/tests/test_guide_xlsx.py
backend/tests/fixtures/guide_xlsx/**
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

DOCX/PPTX behavior, formulas/macros/external data execution, unapproved packages, framework/AUTH/Celery/submission changes.

## Acceptance criteria

- Require exact XLSX classification and the shared OOXML security boundary.
- Use exact policy identity `guide-extraction-v5`; obsolete `unsupported` or
  older XLSX evidence cannot replay as current-policy success. Successful XLSX
  evidence has only the exact boolean omission keys `truncated`, `omitted`,
  `formatting`, `comments`, `drawings`, `hidden_metadata`, and
  `unsupported_objects`. `truncated=false`; `omitted` is true exactly when any
  category is true. Persistence and replay comparison bind the complete
  omission mapping to the same canonical output.
- Emit compact sorted UTF-8 JSON with the exact top-level shape
  `{"worksheets":[...]}`. Each worksheet has exactly `cells`, `merged_ranges`,
  `name`, `position`, and `visibility`. `position` is the one-based workbook
  order. `visibility` is exactly `visible`, `hidden`, or `very_hidden` after
  normalizing OOXML `veryHidden`; missing state is `visible`. Duplicate sheet
  names, IDs, relationship IDs, or targets fail closed.
- Each emitted cell has exactly `coordinate`, `formula`, and `value`.
  Coordinates are canonical uppercase A1 references without `$`. Cells are
  sorted by ascending row number and then column number regardless of XML
  order. `formula` is either the exact formula source string or null and is
  never evaluated. `value` is null or exactly `{"type":TYPE,"value":TEXT}`;
  `TYPE` is one of `text`, `number`, `boolean`, `error`, or `date`. Resolve
  shared strings and inline rich-text runs to visible text in XML order while
  excluding phonetic annotations. Preserve stored numeric, error, date, and
  formula-cache lexical text; normalize boolean cache/input to `true` or
  `false`. Formula string results use `text`. A cacheless ordinary formula must
  use an absent or `n` type with no `v` and emits `value:null`; formula cells
  typed `str`, `b`, `e`, or `d` require the table's cached `v`. A non-formula
  cell with no value is empty and omitted.
  Styles and number formats never reinterpret stored scalar values.
- Support the exact cell combinations below. `v`, `is`, and `f` refer to direct
  SpreadsheetML children. Any other combination fails
  `malformed/xlsx_invalid_cell`; no coordinate, type, or value is inferred.

  | Cell `t` | Required/forbidden children | Canonical value |
  |---|---|---|
  | absent or `n` | optional `v`; `is` forbidden | `number` only when `v` matches `-?[0-9]+(?:\.[0-9]+)?(?:[Ee][+-]?[0-9]+)?`; whitespace, underscores, a leading plus, bare or trailing decimal points, NaN, and Infinity are rejected; empty without `f` is omitted |
  | `s` | one non-negative decimal shared-string index in `v`; `is` forbidden | resolved `text`; shared-string table and index must exist |
  | `inlineStr` | exactly one `is`; `v` and `f` forbidden | resolved inline rich `text` |
  | `str` | exactly one `v`; `is` forbidden | `text`, including an ordinary formula's string cache |
  | `b` | exactly one `v` containing `0`, `1`, `false`, or `true`; `is` forbidden | normalized `boolean` `false` or `true` |
  | `e` | exactly one non-empty `v`; `is` forbidden | exact lexical `error` |
  | `d` | exactly one `v`; `is` forbidden | exact lexical `date`, accepted only as `YYYY-MM-DD` or an RFC 3339 date-time with required timezone |

  An ordinary formula has `f@t` absent or `normal`, no other formula
  attributes or child elements, and non-empty source text. It may use only the compatible cached
  `v` rules above; `inlineStr` and `s` formula cells are invalid. Shared,
  array, and data-table formulas (`f@t=shared|array|dataTable`), empty formula
  source, or any formula metadata requiring reconstruction fail the complete
  extraction as `unsupported/xlsx_formula_unsupported`. Formula text and cached
  scalar text together own the 32,768-character cell budget.
- Each merged range has exactly `anchor` and `range`, using canonical uppercase
  A1 coordinates, and is sorted by anchor then terminal coordinate. Content is
  emitted only for the anchor cell; covered non-anchor cells are omitted. The
  range remains recorded even when the anchor is empty. Invalid, reversed,
  overlapping, duplicate, absolute, whole-row/column, or out-of-grid ranges
  fail closed rather than being repaired.
- A covered non-anchor merged cell must be semantically empty. Any covered cell
  containing `f`, `v`, or `is` fails `malformed/xlsx_merged_cell_conflict`;
  Workstream never silently discards populated covered content.
- Transitional SpreadsheetML uses
  `http://schemas.openxmlformats.org/spreadsheetml/2006/main` with workbook
  `r:id` namespace
  `http://schemas.openxmlformats.org/officeDocument/2006/relationships`.
  Strict SpreadsheetML uses
  `http://purl.oclc.org/ooxml/spreadsheetml/main` with workbook `r:id` namespace
  `http://purl.oclc.org/ooxml/officeDocument/relationships`. Workbook,
  worksheets, shared strings, `r:id`, and consumed relationship types must all
  use one family. Mixed families fail `malformed/xlsx_namespace_conflict`.
- `xl/workbook.xml` sheet order is authoritative. Resolve every sheet `r:id`
  through `xl/_rels/workbook.xml.rels` using the exact passive Transitional
  `http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet`
  or Strict `http://purl.oclc.org/ooxml/officeDocument/relationships/worksheet`
  relationship type. Resolve at most one shared-string table using the matching
  exact `sharedStrings` URI; a package may not mix relationship namespaces.
  Resolve case-variant stored part names only through the validator-approved
  case-folded map. Dangling, duplicate, cross-root/type, orphan worksheet or
  shared-string parts, and conflicting ownership fail
  `malformed/xlsx_relationship_conflict`.
- The adapter consumes only workbook `worksheet` and optional `sharedStrings`
  relationships. A `sheet` referencing chartsheet, dialogsheet, macro sheet, or
  any non-worksheet relationship fails
  `malformed/xlsx_relationship_conflict`. Passive
  style, theme, comment, drawing, chart, table, pivot, slicer, calculation-chain,
  and metadata relationships may remain unconsumed only when the shared OOXML
  boundary accepts them and the exact omission trigger below records them.
  Every stored `xl/worksheets/*.xml` part must be owned by exactly one sheet;
  every stored `xl/sharedstrings.xml` part must be the sole optional consumed
  shared-string target. Duplicate targets are compared case-folded.
- Every direct `sheetData/row` requires decimal `r` in `1..1048576`; duplicate
  row numbers fail even when XML order differs. Every direct row cell requires
  an A1 `r` using letters plus a decimal row, with no `$`, whitespace, range, or
  suffix; it is normalized uppercase, must be within columns `A..XFD` and rows
  `1..1048576`, and its row must equal the containing `row@r`. Duplicate
  normalized coordinates fail. Row/cell XML order is ignored after validation;
  no missing coordinate is inferred. Any SpreadsheetML `row` outside direct
  `worksheet/sheetData` ownership or `c` outside a direct validated row fails
  `malformed/xlsx_invalid_cell`; semantic cells are never silently ignored.
  Row and cell counters count validated direct elements before empty or covered
  cells are omitted from canonical output.
- Accept exactly 100 worksheets and reject 101 before worksheet extraction with
  `limit_exceeded/xlsx_sheet_limit`. Count explicit worksheet row elements
  across the item: exactly 100,000 pass and 100,001 fail
  `limit_exceeded/xlsx_row_limit`. Count explicit cell elements across the item:
  exactly 1,000,000 pass and 1,000,001 fail
  `limit_exceeded/xlsx_cell_limit`. Reject more than 32,768 Unicode code points
  across one cell's emitted formula plus scalar text as
  `limit_exceeded/xlsx_cell_character_limit`. Traversal beyond 64 XML semantic
  levels fails `malformed/xlsx_nesting_limit`. Exceeding D42's exact 4 MiB
  canonical output limit fails `limit_exceeded/output_limit`. Every limit
  rejects the complete result; no partial result is usable.
- Missing/unreadable workbook parts use
  `malformed/xlsx_workbook_unavailable`; well-formed invalid workbook roots use
  `malformed/xlsx_invalid_workbook_xml`; invalid worksheet roots/XML use
  `malformed/xlsx_invalid_worksheet_xml`; invalid shared-string roots/XML use
  `malformed/xlsx_invalid_shared_strings_xml`; invalid coordinates, row/cell
  ownership, scalar types, shared-string indexes, merge ranges, or duplicate
  cells use `malformed/xlsx_invalid_cell`. Non-well-formed or unsafe XML is
  rejected first by the shared boundary as `malformed/ooxml_unsafe_xml`.
- Omission facts record style/number-format parts, comments, drawings/charts,
  hidden workbook/custom/phonetic metadata, and passive unsupported spreadsheet
  objects. Exact triggers are:

  | Omission flag | Exact trigger |
  |---|---|
  | `formatting` | stored `xl/styles.xml` or any part under `xl/theme/` |
  | `comments` | any part under `xl/comments`, `xl/threadedcomments/`, or `xl/persons/` |
  | `drawings` | any part under `xl/drawings/` or `xl/charts/` |
  | `hidden_metadata` | any part under `docprops/` or `customxml/`; workbook `definedNames`; or `phoneticPr`/`rPh` in a shared or inline string |
  | `unsupported_objects` | stored `xl/calcchain.xml` or any part under `xl/tables/`, `xl/pivottables/`, `xl/pivotcache/`, `xl/slicers/`, `xl/chartsheets/`, or `xl/dialogsheets/` |

  Explicit worksheet `visibility` is canonical output and alone does not set
  `hidden_metadata`. Formulas are not omissions because their source and
  optional cache are explicit. Active
  content, macros, external relationships/data, embedded executables, and
  nested archives remain shared OOXML malformed rejections before extraction.
- Never evaluate formulas, apply number formats, execute links, or fetch
  external data. The isolated child receives the approved shared OOXML
  validator by injection; production imports of the XLSX adapter remain
  confined to `guide_extraction_worker.py`. No package or lock change is
  permitted.
- Prove deterministic workbook/sheet/cell ordering, every scalar/formula/cache
  type, rich/shared strings, merged ranges, visibility and omission facts;
  exact relationship/orphan behavior; exact 100/101 sheet, 100,000/100,001 row,
  1,000,000/1,000,001 cell, 32,768/32,769 character, depth, and output
  boundaries; complete Strict success and mixed XML/relationship family
  rejection; required row/cell ownership and Excel grid edges; populated
  non-anchor merged-cell rejection; every omission flag independently;
  unsafe/malformed input; crash, timeout, cancellation, cleanup;
  approval/dependency gate; child-only imports; complete cross-process omission
  facts; v5 persistence/replay identity; and coverage behavior. Assign the
  focused XLSX module to the existing canonical hosted semantic lane without
  changing lane or coverage policy.

## Verification commands

```bash
(cd backend && uv run ruff check app tests)
(cd backend && python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run pytest -q tests/test_guide_ooxml.py tests/test_guide_xlsx.py tests/test_guide_extraction.py --cov=app.modules.artifacts.guide_xlsx --cov-branch --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

Hosted Backend/Agent Gates must preserve 90% changed-subsystem and 78% repository coverage.

## Required reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human review focus

Format-specific deterministic semantics, reuse of the shared secure container
boundary, exact limits, and absence of parser imports outside the isolated child.

## Stop conditions

Stop on unapproved dependencies, scope expansion, isolation/CI weakening,
architecture drift, or repeated repair failure.
