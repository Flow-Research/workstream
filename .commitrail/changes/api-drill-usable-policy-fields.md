# Usable public API policy-field drill

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Extend evidence for currently usable draft-guide policy APIs without treating unfinished routes as drill targets.

## Intent

The human wants a verified external-client contract for usable APIs, not a count
of every registered route. The merged prior drill proves successful scenarios
for 29 operations; this does not prove every field combination. Review/revision
policy creation, replacement and replay already work. Extend missing optional
field and conditional-update probes without repeating unchanged work by default.

## Bounded change

Allowed: `backend/scripts/external_api_drill.py`,
`scripts/test_external_api_drill.py`, `docs/engineering/external-api-drill.md`,
`docs/engineering/external-api-drill-findings.md`, `docs/roadmap_status.md`,
this record, and existing ignored local roadmap exports if present.

Prohibited: product code, public schema changes, migrations, hidden routes,
direct product SQL writes, enabled unavailable actions, disabled guards, provider
fakes, CI/coverage changes, and product-builder files. Newly reproduced product
defects stay failing and are communicated before deciding repair ownership.

## Design and alternatives

Reuse the existing client, isolated runner and field indexes. Extend only the
two usable draft-guide policy PUT operations. Keep existing tests and named
evidence. Do not create another drill framework or treat successful empty reads
as proof of unavailable populated lifecycles. OpenAPI discovery is navigation,
not a readiness list. Bootstrap is operator setup, not an external endpoint.

## Acceptance criteria

1. Probe remaining optional field null/type/closed-value behavior, valid nondefault
   values, strict human-review boolean values and omission/default restoration.
   Review-mode omission specifically preserves the current human-review setting;
   it is not ordinary default restoration during replacement.
2. Probe missing/malformed If-Match and Idempotency-Key, random mismatched selectors,
   and unauthorized mutation using real authorized controls.
3. Denied/invalid attempts must not advance selected policy state: a fresh successful
   mutation using the previously current selector must succeed and advance exactly
   one generation. Compare returned full policy fields, identity and lineage;
   distinguish this evidence from cached replay.
   This does not assert absence of legitimate denial audit events or prove
   every historical table remained unchanged.
   A nonexistent selector is not a stored foreign-resource or tenant-isolation proof.
4. Add a falsification helper test that fails if a rejection advances generation
   or a replacement returns wrong values. Retain all previous scenarios.
5. Run helper tests and the extended real-HTTP drill from a clean candidate,
   applicable hosted checks, and focused review. Never mark unexecuted scenarios
   or hidden/prerequisite-blocked routes as verified.

## Risk and review routing

Risk L1: authorization/policy evidence integrity, no product change.
Plan review checks fixture/selector feasibility. Implementation review covers
security plus QA/test-delta and documentation, combined proportionately.

## Evidence

Commands: `backend/.venv/bin/python -m unittest scripts.test_external_api_drill
scripts.test_admin_api_drill`; isolated external drill per its procedure;
Ruff on changed Python; `python3 scripts/check_commitrail_records.py --base-ref
origin/main`; Markdown links, stale wording and diff checks. Hosted tests and
coverage remain authoritative. Unchanged administrator evidence retains its
actual prior head; rerun only if its shared execution boundary changes.

Human focus: usable public API proof, not unfinished product activation or a
claim that every discovered endpoint belongs in the MCP adapter.

## Review corrections

The first live extension run exposed a harness expectation mismatch: missing
required headers use `invalid_request`, whereas a malformed policy UUID key
uses its explicit `validation_error` handler. Expected codes follow those owners.
Review also required hash-relation proof: changed semantics must change the
policy hash; the intentionally equivalent revision replacement must preserve it.
Helper mutants cover both directions. These are drill fixes, not product defects.
