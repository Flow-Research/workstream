# Canonical public API field drill

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Extend endpoint-by-endpoint contract evidence for the 29 selected canonical public operations without treating obsolete or unfinished routes as drill targets.

## Intent

The human wants a verified external-client contract for usable APIs, not a count
of every registered route. The merged prior drill proves successful scenarios
for 29 operations; this does not prove every field combination. Review/revision
policy creation, replacement and replay already work. Extend missing optional
field and conditional-update probes without repeating unchanged work by default.

The human expanded this same PR to drill the 29 already exercised canonical
operations, one by one. Obsolete API removal belongs to the task agent; this
change neither exercises nor removes those routes. The human additionally authorized
repairing reproduced API-DRILL-007/008 in this same PR. Each endpoint is assessed against its actual schema, authority and
service owner before adding cases, with meaningful omissions, type/boundary
cases, response values, persistence, replay and denied side effects where
applicable. A passing example or aggregate count is not endpoint completion.

## Bounded change

Allowed: `backend/scripts/external_api_drill.py`,
`scripts/test_external_api_drill.py`, `docs/engineering/external-api-drill.md`,
`docs/engineering/external-api-drill-findings.md`, `docs/roadmap_status.md`,
`backend/scripts/admin_api_drill.py`, `scripts/test_admin_api_drill.py`,
this record, and existing ignored local roadmap exports if present.
The bounded NUL repairs also allow `backend/app/modules/actors/schemas.py`,
`backend/app/api/routes/auth.py`, `backend/app/modules/projects/schemas.py`,
and `backend/tests/test_api_drill_repairs.py`.

Prohibited: other product changes, migrations, hidden routes,
direct product SQL writes, enabled unavailable actions, disabled guards, provider
fakes, CI/coverage changes, and edits in the product-builder worktree. Newly reproduced product
defects stay failing and are communicated before deciding repair ownership.

Repair design: reject embedded NUL in the existing self-profile text validator
and authorization-context query constraint before PostgreSQL receives it. Do not
sanitize it into another value, change primary-key selection, narrow ordinary
Unicode text, alter authority or introduce a new validation subsystem. Prove
422 `invalid_request` with `retryable: false`, unchanged profile business fields,
and subsequent valid profile/project-selector controls through HTTP and the live
drill. Existing exact 503 reproductions are the pre-fix negative evidence.

## Design and alternatives

Reuse the existing client, isolated runner and field indexes. Extend only the
29 canonical operations selected in the external/admin drills. Keep existing tests and named
evidence. Do not create another drill framework or treat successful empty reads
as proof of unavailable populated lifecycles. OpenAPI discovery is navigation,
not a readiness list. Bootstrap is operator setup, not an external endpoint.

## Acceptance criteria

The policy criteria below remain required. Additionally, inspect and drill in
this order: health; self profile GET/PATCH; self authorization context; actor
and identity-link reads/lifecycle; permission and administrative-role discovery;
administrative grant reads/issue/revoke; service provisioning; project create/read;
contributor candidates; project grant reads/issue/revoke; guide create/update;
review/revision policy PUT. Record unchecked behavior explicitly. Do not claim
full completion until every selected endpoint's applicable checklist has passing
named evidence on a compatible target. Keep bootstrap as setup, not a 30th API.

Initial execution step: assert the health body's exact value/shape without
authentication, and strengthen full-state profile readback after rejected input.
Reuse existing valid controls and the normal token verifier and rate budget.

Discovery/grant extension: compare all 73 permission identifiers and the exact
five-role scope/permission matrix against a frozen public-contract oracle, not
runtime imports or values learned from the response. This proves catalogue
projection, not activation of every listed permission. Preserve the existing
twenty-actor authority matrix. Administrative grant history must compare every
public field, including grantor/revoker lineage and timestamps, before and after
same-key replay; retain independent stored-state denial checks. Helper mutations
must reject changed permissions, duplicate roles, extra fields and changed replay
timestamps. No additional product changes are authorized by this extension.

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

Risk L1: authorization/policy evidence integrity and bounded request validation repairs.
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

The next independent project/guide input diagnostic reproduced API-DRILL-009
across eight text inputs. Its durable reproduction and repair boundary live in
the findings document, and the roadmap explicitly retains this unresolved gap.
The private diagnostic uses distinct administrator/manager actors after an
initial self-grant fixture was correctly denied. No project-builder product
files are changed; repair ownership must be coordinated before that expansion.

The human subsequently authorized the complete API-DRILL-009 repair here.
Extend the eight existing request fields with NUL-excluding Pydantic constraints,
preserving all current lengths, Unicode, nullability and omission semantics.
Do not change services, database behavior or the future guide contract. The
product-builder's separate uncommitted removal of guide content fields must not
be reversed during integration; surviving fields retain the new validation.
Add parameterized HTTP/PostgreSQL rejection and recovery regressions, permanent
live drill cases with full public-state controls, and schema-level boundary
checks. All eight original failing cases must pass unchanged 422 expectations.
The existing L1 plan and security/QA/test-delta/docs review routing applies.

Contributor-discovery evidence extension: reuse the twenty-actor setup and
existing paging helpers. Require the exact two-field candidate row, including
a populated Unicode display name while withholding contact data. Exercise
candidate cursor query binding, malformed query values and caller authority.
At existing actor/link lifecycle transitions, verify exact candidate membership
before and after exclusion/restoration. Do not add product mutations beyond the
existing authorized lifecycle setup or infer candidate listing grants task access.
Helper mutants must reject leaked extra fields and altered/missing candidate
values. Preserve all earlier scenarios, full coverage floors and fail-closed
reports; run the expanded real administrator drill and focused review.
