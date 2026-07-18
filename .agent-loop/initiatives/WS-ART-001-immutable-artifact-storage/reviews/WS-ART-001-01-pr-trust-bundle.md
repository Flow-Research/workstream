# PR Trust Bundle: WS-ART-001-01

## Goal

Establish Workstream's provider-neutral immutable artifact domain and a secure
local development adapter before any Flow Node or product-record cutover.

## What Changed

- Added immutable upload-session, item, content, binding, replica, and receipt
  records with additive PostgreSQL migration guards.
- Added a versioned provider contract and deterministic local adapter supporting
  store, recover, open/range, stat, verify, retain, release, and receipt lookup.
- Added coordinator transactions, replay recovery, quarantine, reconciliation,
  and shared Workstream audit events.
- Added environment guards, contract/stale scanners, focused tests, and a
  separate 90 percent artifact coverage gate.

## Scope Control

No public upload endpoint, product cutover, Flow Node adapter, authorization
implementation, legacy-field removal, reviewer API, or next-chunk behavior is
included. Local storage remains behind the object-storage abstraction and is
rejected outside local/dev/test environments.

## Design

Postgres stores identity, immutable digest/size facts, bindings, replica state,
provider receipt projections, and audit evidence. The storage provider stores
bytes. Provider calls occur outside lifecycle transactions; Workstream reserves
state before I/O and promotes facts only after verified provider success.

## Verification

- `38` artifact tests passed at `90.26%` subsystem coverage.
- `17` migration/config tests passed against isolated PostgreSQL.
- Ruff passed; docstring coverage is `100%`.
- `36` engineering-loop regression tests passed.
- Artifact, Workstream wording, authorization, Markdown-link, loop-memory, and
  diff-hygiene gates passed.
- All nine required internal reviewer tracks passed after fixes; no reviewer
  session remains open.

Reviewed code SHA: `5574bf59cf1cb86da76749e0cbc529036346fa8a`

The first Backend run found a Settings-cache ordering bug in the artifact test
fixture. The fixture now reuses the shared isolated database environment; the
exact failing order passed 15 tests and four focused internal delta reviewers.

## External Review

CodeRabbit's valid findings are addressed and recorded separately in
`WS-ART-001-01-external-review-response.md`. Final current-head GitHub checks
and human review remain pending.

## Human Review Focus

- Provider neutrality and separation of content, binding, replica, and receipt.
- Additive migration behavior with no inferred promotion of old declarations.
- Transaction boundaries around provider I/O and crash recovery.
- Filesystem privacy, no-follow handling, bounded streaming, and path redaction.
- Production rejection of the local adapter and preservation of later chunks.

## Human Merge Ownership

- [ ] I can explain the artifact record and transaction boundaries.
- [ ] I verified CI and external review results.
- [ ] I confirm the next chunk has not started.
- [ ] The user explicitly approved this specific PR for merge.
