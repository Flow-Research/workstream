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

### Project archive-limit follow-through

The human explicitly authorizes completing the genuine-guide archive limits in
this same PR. Source inspection corrects the earlier interpretation:
`limit_package_size` already compares the verified manifest's total expanded
bytes with `maximum_package_size_bytes`. Clarify that existing field in the
model-facing proposal schema and current documentation; do not add a second
expanded-size implementation. Add only `maximum_archive_entries`, an optional
strict positive integer counting the canonical outer ZIP tree (files and explicit
or implied parent directories), not raw central-directory record count.
Null means no additional project limit, not removal of platform safety limits.
Nested archives remain file entries; this is not a recursive archive-entry count.

Extend existing PROJECTS canonical/default/effective policy merging (minimum
non-null), model proposal projection, TASK locked-policy summary, CHECKERS
catalogue/compiler and the single effective-plan processor. Enforce member
count against ART's verified manifest, never caller declarations. Keep the
existing ART inspector and platform resource ceilings unchanged. Both size and
count failures block intake through existing evidence routing, not acceptance.
The approved policy hash and compiled bundle bind both limits; missing or altered
required rules fail closed. Do not expose hidden APIs or create a parallel checker.

Additional allowed files: `backend/app/interfaces/project_agents.py`, existing
PROJECTS `schemas.py`, `service.py` and
`guide_compilation/projection_payloads.py`; TASK `schemas.py` and `service.py`;
CHECKERS `catalogue.py`, `compiler.py`, `pre_submit_execution.py`, `service.py`,
and `api/pre_submit.py` (the closed result-code list for the new failure);
their existing focused policy/compiler/catalogue/execution/task-summary tests,
`docs/architecture_data_model.md`,
`docs/decision_0011_submission_artifact_policy_drives_pre_submit.md`,
`docs/architecture_checker_framework.md`,
`docs/template_submission_artifact_policy.md`,
and the existing drill docs, roadmap and this record. Existing structural debt
must not grow; extract a cohesive helper within its owning module if necessary.
No migrations, authority changes, retained-data rewrites, new public routes,
compatibility variants, provider fakes or CI/coverage weakening.

Risk L1. Plan review covers architecture and proof feasibility; focused final
architecture/security and QA/test-delta/docs reviews cover the changed owners.
Acceptance: schema rejects booleans, nonintegers and nonpositive counts;
projection preserves explicit count; effective defaults cannot be weakened;
compiler rejects missing/weakened rules; real ZIP processor probes prove exact
size/count boundaries, including directory members and compressed-vs-expanded
bytes. Regressions must detect disabled limit enforcement. Run focused tests,
the same two-PDF genuine-provider drill with isolated resources and exact stored
hash/replay checks, then hosted full CI. Retain failed runs and distinguish
public setup proof from hidden intake execution proof. Update incorrect prior
gap interpretations explicitly rather than rewriting historical evidence.
Human focus: one canonical expanded-byte limit, one member-count rule, unchanged
platform safety and authorization, and real drill results rather than inferred
readiness.

The genuine-provider diagnostic replay removed the reported size/count gaps but
reported root placement unsupported. Existing `require_file` already checks exact
paths; clarify the existing proposal's `required_artifacts` field description and
prove wrapping a required root file cannot satisfy it. No new path checker or
relaxed validation. Preserve both the earlier terminal `schema_invalid` run and
the subsequent valid blocked report; neither explains the other's outcome.

Focused review found two repairs: omitted optional count must merge as null
without rewriting policy JSON (`ARCH-SEC-001`), and the actual TASK requirements
response needs a non-null/invalid-value regression (`QA-ARCHIVE-001`). Both are
addressed alongside the primitive-list formatting correction (`DOC-ARCHIVE-001`).
Real ZIP evidence explicitly includes implied parent directories in ART's
canonical tree and proves omitting directory records cannot evade the count.

### Historical same-PR genuine-guide metadata repair

The following scope and evidence describe the earlier metadata-only repair.
Its prohibition on adding project archive limits is superseded by the explicit
project archive-limit follow-through above; all other safety boundaries remain.

The human additionally requested resolving the genuine-guide drill findings
before merging this PR, rather than handing them to a separate change. Trace
the existing catalogue, ART inspector and compilation validator first. Reuse
canonical catalogue metadata to expose already-enforced encrypted-entry
rejection to guide compilation; do not add another checker or invent configurable
project archive limits. Preserve the original failed model outcome: a later
successful call cannot explain its `schema_invalid` rejection.

This extension allows `backend/app/modules/checkers/catalogue.py`,
`backend/tests/test_checker_catalogue.py`,
`backend/tests/test_project_guide_compilation_contracts.py`, and the existing
drill documentation and record. Broader runtime repairs require a reproduced
cause and an explicit update here before implementation. No weaker model-output
validation, raw provider-output logging, hidden-route exposure, acceptance change,
database migration or product-builder worktree edits are allowed.

Acceptance: the model-facing projection describes the existing mandatory archive
encryption rejection without making it selectable; exact catalogue identity and
disabled-state checks remain enforced. Run the catalogue and compilation-contract
tests plus `test_submission_archive.py::test_encrypted_flag_is_rejected_before_member_open`.
Prove the new semantic regression fails against the previous catalogue metadata.
Then rerun the two genuine PDFs from a frozen checkout with isolated resources,
retaining every failed result. Investigate rejected model output with bounded,
sanitized diagnostics; never label an unexplained rejection repaired. Risk L1;
focused plan/architecture and QA/test-delta/documentation review cover this
extension, with security review if runtime diagnostics or validation change.
Human focus is honest capability coverage, unchanged fail-closed validation,
and the distinction between a valid blocked guide and a completed ready guide.

The metadata repair uses the existing `public_name`, not a new schema field.
Both enabled/disabled regression parameters failed against the old opaque label;
the repaired compilation-contract suite, exact catalogue snapshot and ART
encrypted-entry owner regression pass together (69 tests). The initial broader
plain invocation passed 86 tests but could not set up the database-backed startup
test; it is not a complete catalogue-suite pass. Real-provider replay and the
unexplained invalid result remain separate evidence obligations.

Follow-through evidence at clean `8b79daf7`: compilation contracts, the complete
archive inspector suite and catalogue snapshot passed 109 tests; the complete
catalogue suite separately passed 21 tests with isolated PostgreSQL and confirmed
cleanup. Focused architecture and QA/test-delta/docs reviews found no findings.
The same two-PDF real-provider replay completed 33 HTTP checks, reported only
the two genuine project-limit gaps, preserved original hashes and denied replay
after resolver deactivation. All owned resources were cleaned up. The SDK
redaction-aware private observer was calibrated with invalid structured output;
the real replay produced no validation exception. This verifies the metadata
repair, not the cause of the earlier isolated `schema_invalid` result.

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

The full rate-paced client run exposed fixture expiry after ten minutes: a later
revocation conflict received 401 `invalid_token` instead of reaching its intended
409 assertion. Extend only the ephemeral local issuer's default lifetime to one
hour. Explicit expired-token inputs and production verification remain unchanged.
Prove signed fixture admission after 901 seconds and actual expired-token rejection;
replay the real client run. Focused QA/test-delta review covers this fixture repair.
The separate genuine-document run also exposed an environmental missing-SDK
precondition; document installation of the existing runtime extra, not a fallback.

API-DRILL-013 repair: the human authorized fixing service provisioning subjects
containing NUL in this same PR. Extend the existing `OpaqueSubject` constraint in
`backend/app/modules/authorization/service_actor_schemas.py`; preserve exact
subject identity, ordinary Unicode, whitespace rejection and the 1–200 UTF-8
byte bound. No authority, service, migration or retained-data change is allowed.
Additionally allowed: a focused regression in the existing administrator
HTTP/PostgreSQL request-validation tests at
`backend/tests/authorization/admin_access/test_grant_validation_postgresql.py`.
Reuse their signed client/bootstrap fixture and snapshot helpers. Prove NUL
rejection before state changes, valid 200-byte Unicode same-key recovery,
stored subject identity and exact replay. Retain the original failing real-HTTP
probe and rerun it; add permanent subject probes to the existing external drill.
Assess the roadmap and findings in this PR. Risk remains L1 with focused plan,
security and QA/test-delta/docs review. Full backend tests remain hosted.

Administrative-reason drill continuation (API-DRILL-012): the same-PR small
repair scope additionally covers `backend/app/modules/authorization/admin_schemas.py`
and `backend/tests/authorization/admin_access/test_grant_validation_postgresql.py`.
Both administrative grant issue and revoke currently allow embedded NUL in the
public reason, then return 503 when PostgreSQL rejects it. Reject NUL through
their existing shared `Reason` constraint; retain its 1–500 UTF-8-byte bound,
ordinary Unicode, whitespace semantics and every authorization/replay guard.
Do not change services, canonical authority facts, migrations or stored data.
Prove 422 for each operation, unchanged grant/idempotency/audit snapshots, and
valid same-key recovery plus exact replay at the Unicode size boundary.
Add permanent live probes using the existing denial snapshot helper and its
counterexamples, which cannot swallow a failed rejection or changed history.
Existing security and QA/test-delta/docs
review routing applies; full backend verification stays in hosted CI.

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
checks. After the guide cutover, require unchanged 422 expectations for the six
surviving fields: project name, slug and description; guide-create version and
change_summary; guide-update change_summary. Removed top-level content_markdown
must instead be rejected as unknown input on both guide operations. Original
eight-field results remain historical evidence, not authority to restore fields.
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

Project-role grant evidence extension: pass the HTTP-issued manager authority
grant ID into the existing role drill. For both submitter and reviewer, check
the exact mutation receipt, full grant and qualification-snapshot fields and
known grantor/capture provenance. Read current state before replay and compare
the complete response again afterward. Revoke with an explicit key, preserve
all unchanged grant/snapshot fields, and prove revoke replay/conflict leaves
that public state unchanged. These HTTP readbacks do not certify every hidden
table. Test outer request omissions, malformed IDs/reasons and unknown fields
without weakening existing qualification boundary probes. No product changes.
Use a focused real-HTTP role scenario plus existing helper falsification tests
and hosted CI; retain prior execution targets for unchanged drill groups.

Merged guide-contract integration: replace inline-body fixtures with required
ordered task examples on guide creation; PATCH changes only change_summary.
Retain NUL rejection for surviving fields, preserve the new 1000-character
summary bound, and remove positive tests of deleted content fields. Test removed
fields as unknown-input rejection only. Expand guide evidence across example
content/title/labels, omission, null/type/length/aggregate limits, immutable input,
full response shape, authorized replay and foreign/unauthorized mutation.
Use public guide metadata and policy routes only; do not activate hidden upload,
compilation, manager-approval or task surfaces. Inventory exposure on merged main
before changing the selected operation list. Preserve old execution evidence at
its original target and mark superseded fixtures explicitly. This integration
does not claim the earlier eight-field NUL fixture still applies unchanged.
The existing L1 plan/review routing and same-PR allowed paths remain applicable.

Resumption after #396/#397: reconcile the existing drill with main before new
execution. Required document declarations and create-only document/setup response
fields replace the previous metadata-only fixtures. PATCH still returns guide
metadata and must not be tested against the create-only envelope. Preserve named
negative cases and independently check declaration order, types, identity, replay
and response privacy. Prior results retain their actual target; this is not a
claim that old fixtures certify the new API. The user also requests the now-public
guide upload drill with genuine project material; enable it only with isolated
real storage and approved model configuration, never fabricated provider output.
The supporting `backend/scripts/guide_document_api_drill.py` entry point and its
helper tests are in scope, reusing the existing HTTP/issuer/report runner. It
adds public document upload and setup/findings reads to this guide-specific pass;
those additions are explicitly separate from the original 29-operation census.
Use original, shareable PDF inputs outside Git; do not copy private benchmark
content or credentials into the repository. A real worker and uniquely owned
loopback broker use isolated storage/database credentials. Stop owned processes
and verify runner cleanup on failure as well as success. Output evidence may
contain public diagnostic fields but never the provider key or environment file.

Resumed diagnostic outcome: the original 29 HTTP operations have executed
scenarios across the metadata and twenty-actor administrator passes; this is not
all-field certification. The live document pass independently verified two
stored originals and reached public sufficiency evidence through actual Celery
delivery. It also reproduced API-DRILL-010, an ART terminal-upload replay defect.
Keep that assertion failed while observing independent steps, and retain a
nonzero final result until repaired. The human subsequently authorized fixing
API-DRILL-010 here and rerunning the live drill in this same PR.
The findings document records its reproduction and existing owner path.

API-DRILL-010 repair scope additionally allows
`backend/app/modules/artifacts/service.py`, existing guide/artifact regression
tests and their existing fixtures, and the existing guide-upload composition in
`backend/app/adapters/artifacts/__init__.py`. The regression also exposed an
unmapped internal authorization denial after resolver deactivation: map it to
the existing ART denial at this adapter, after rollback and canonical denial
restaging, as the existing internal operation adapter already does. Do not add
a protocol, duplicate authorization decision, or generic exception translation.
Keep exception translation in the existing ART-owned AUTH adapter in
`backend/app/modules/artifacts/authorization.py`. Reuse its denial boundary in
`backend/app/adapters/artifacts/internal_workers.py` and guide composition so
both callers preserve rollback and audit restaging without another private AUTH
import or duplicated translation recipe.
Remove the retired import edges from the existing AUTH import ledger and module
private-edge debt inventory; do not permit any new private dependency.
Register the new guide drill in the existing behavior ownership partition's
shared group; preserve the ownership validator and all structural limits.
Its exact path must also join the existing `API_DRILL_PARTITION_TARGETS` list in
`backend/scripts/behavior_ownership.py`, with positive and unapproved-path
regressions in `backend/tests/test_behavior_ownership.py`. No wildcard admission
or exemption from behavior ownership is allowed.
Factor extended regression setup/state checks into focused helpers rather than
introducing an oversized test or another structural debt entry.
Extend the existing authorized put resolver:
after current authority consumption and namespace/fence revalidation, recognize
an already `object_confirmed` put as completed without trying to claim it as
unfinished observation work. Preserve all incomplete-put recovery paths. Public
ingest admission remains responsible for exact actor/project/document/bytes/key
binding. No new endpoint, compatibility path, authority bypass, migration or
retained-data rewrite is allowed.

Acceptance: exact successful document replay returns a completed status with
unchanged hash/size and no second provider write; absent/revoked/foreign authority
and changed input still deny; unfinished recovery stays covered. Use focused
HTTP/PostgreSQL/MinIO regression and the existing two-PDF real drill, followed by
the strengthened findings-lineage read. Risk remains L1. Run focused plan and
implementation security/architecture plus QA reviews; human focus is legitimate
replay without a new upload, authorization shortcut or duplicate inference.

QA review additionally required the public findings list to match the completed
setup's report, project, guide, source snapshot and generation, rather than
accepting any HTTP 200 body. Extend the existing response predicate to support
the JSON root and test empty, duplicated, missing and foreign lineage. Keep
original shareable-document findings in the private report for later inspection;
do not print model text or claim earlier runs executed this new predicate.
