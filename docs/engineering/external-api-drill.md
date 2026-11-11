# External-client API drill

The audit is bounded to the original 29 public operations below. The endpoint
matrix is the client handoff boundary; OpenAPI route discovery is not a claim
that every registered or future lifecycle operation is ready.

## Fixed 29-operation acceptance matrix

The matrix is complete across compatible frozen executions: 798 HTTP checks
at `7c9f60d2`, 613 administrator checks (331 HTTP and 282 local evidence checks)
at `35e49840`, and 84 closing authority checks (53 HTTP and 31 local evidence
checks) at `1fb14077`. All met their expected outcomes, with no incomplete
scenario groups; every disposable database and role was cleaned up.

These are distinct recorded targets, not one execution at the final documentation
commit. After the external run, changes tightened 15 conflict-code
assertions; every expected code was checked against the retained real response,
and a helper regression rejects the wrong code even when HTTP 409 matches.
After the full administrator run, the added closing authority group was executed
separately against the unchanged product implementation. It covers service and
revoked-link grant targets, cross-project grant substitution, and scoped guide
and policy writes. Reports remain private, out of tree, at their original hashes.
Actor and identity-link reasons now share the same failure-continuation helper:
an unexpected rejection response stays recorded as failed while the next
unchanged-state read still runs. A changed-state read aborts continuation.
Focused regressions cover both resource types; successful requests, case names,
oracles and same-key recovery remain unchanged from the recorded execution.

This is the original client-audit scope, not all registered routes. Paths below
use `/api/v1`. `E` names cases in `external_api_drill.py`; `A` names cases in
`admin_api_drill.py`. Each row requires the named successful use, applicable
invalid inputs, authority checks and state/replay assertions. Bootstrap remains
local operator setup, not a thirtieth API. Draft-guide checks do not manufacture
activation, task execution or acceptance. The four proposal APIs added in #400
are outside this matrix.

| # | Operation | Contract and named evidence |
|---|---|---|
| 1 | `GET /health` | Exact public health value/shape and request/correlation headers: E `health`. |
| 2 | `GET /actors/me` | Canonical identity, every profile field, stable identity, token rejection and actor/link lifecycle admission: E `profile_*`, `*_self_read_*`. |
| 3 | `PATCH /actors/me` | Editable display-name null/normalization/length/type/NUL, rejected read-only email and mixed-update atomicity with unchanged-state readback: E `display_name_*`, `profile_readonly_*`, `*_self_write_*`. |
| 4 | `GET /actors/me/authorization-context` | Exact project, actor, roles and effective actions; selector validation, both contributor roles, revoked and foreign-project concealment: E `context_*`, `contributor_context_*`, `revoked_contributor_context_*`. |
| 5 | `GET /actors/{actor_profile_id}` | Exact human/service fields and timestamps, access-admin/system-audit reads, project-audit/ordinary/no-auth denial, absent/malformed selectors: E `admin_human_profile_fields`, `service_persisted_profile`; A `human_admin_read_fields`, `admin_read_profile_*`. |
| 6 | `GET /actors/{actor_profile_id}/identity-links` | Exact human/service link fields without subject disclosure, authority/selector checks, revoked/restored state: A `human_admin_link_fields`, `admin_read_link_*`; E `service_persisted_identity`, `service_link_*_readback`. |
| 7 | `POST /actors/{actor_profile_id}/suspend` | Full reason/key boundary matrix, authority/target denial, normalized replay/mismatch/conflict, exact receipt and current-state preservation: E `actor_suspend_*`; A self and last-admin guards. |
| 8 | `POST /actors/{actor_profile_id}/reactivate` | Same boundary matrix, restored access, already-active and terminal refusal: E `actor_reactivate_*`, `reactivated_*`, `deactivated_actor_cannot_reactivate`. |
| 9 | `POST /actors/{actor_profile_id}/deactivate` | Same boundary matrix, terminal status and subsequent self-access denial: E `actor_deactivate_*`, `deactivate_self_write_denied`. |
| 10 | `POST /actor-identity-links/{identity_link_id}/revoke` | Reason/key/authority/target boundaries, exact receipt, replay/mismatch/conflict, denied admission and unchanged current link: E `link_revoke_*`, `service_link_revoke_*`; A self guard. |
| 11 | `POST /actor-identity-links/{identity_link_id}/reactivate` | Same boundary matrix and restored identity admission without creating authority: E `link_reactivate_*`, `service_link_reactivate_*`. |
| 12 | `GET /authorization/permissions` | Exact frozen 74-permission catalogue, not runtime-derived expectations; authority and lifecycle rejection: E `catalogue_*`; A `inactive_catalogue_*`. Catalogue presence does not activate an action. |
| 13 | `GET /authorization/admin-role-definitions` | Exact five roles, allowed scopes and permission matrix; twenty-human allow/deny matrix: E `catalogue_*`; A `role_definitions_*`. |
| 14 | `POST /admin-role-grants` | Required/optional scope inputs, role/reason/key boundaries, self-grant prohibition, target eligibility, exact receipt/history and replay: A `grant_*`, `self_grant_*`, `system_only_*`, `inactive_grant_target_*`, `closing_service_grant_denied`, `closing_revoked_link_grant_denied`, `closing_restored_target_grant`. |
| 15 | `GET /admin-role-grants` | All 16 public history fields against independent stored custody, populated scope/status pagination, cursor/query limits and audit/ordinary/no-auth boundaries: A `admin_pages_*`, `admin_query_collection_*`, `admin_auditor_collection_*`. |
| 16 | `GET /actors/{actor_profile_id}/admin-role-grants` | Complete active/revoked lineage, multiple history rows, filters/cursors, system/project-audit scope and malformed/absent actors: A `history_*`, `admin_query_history_*`, `grant_*_full_history*`, `revoke_*_full_history*`. |
| 17 | `POST /admin-role-grants/{grant_id}/revoke` | Exact receipt and retained history, reason/key/selector boundaries, replay/mismatch, absent/revoked concealment and current authority: A `revoke_*`, `grant_target_revoke*`, `cross_admin_*`, `last_admin_*`. |
| 18 | `POST /service-actors` | Closed identity/opaque subject/reason inputs, 200/500-byte equality and overflow, denied callers, distinct binding conflicts, exact receipt, replay and stored profile/link: E `service_*`. |
| 19 | `POST /projects` | All three request fields, required/null/type/length/NUL, authority, duplicate slug, key/replay/conflict and exact draft readback: E `project_*`, `create_project`, `replay_project`, `overflow_*`; A `cannot_create_project_*`. |
| 20 | `GET /projects/{project_id}` | Complete administrative view versus exact three-field contributor view, real foreign projects and revoked access: E `read_project`, `project_maximum_readback`, `contributor_project_access_*`, `foreign_project_denial`; A `project_read_*`. |
| 21 | `GET /projects/{project_id}/contributor-candidates` | Exactly actor ID/display name; populated pagination, cursor tampering/binding, limit validation, service exclusion and human/link lifecycle membership: A `candidate_*`, `candidates_after_*`. |
| 22 | `POST /projects/{project_id}/role-grants` | Submitter/reviewer only, required input and nested qualification fields, combined bounds, exact manager/capture lineage, replay/recovery and self/foreign denial: E `qualification_*`, `project_issue_*`, `issue_project_*`; A `manager_self_project_grant_*`. |
| 23 | `GET /projects/{project_id}/role-grants` | Populated pages, role/status filters, scoped cursor and query boundaries, exact unchanged history after rejected writes: A `project_pages_*`, `project_filtered_*`, `project_cursor_*`; E `project_issue_*_unchanged`. |
| 24 | `GET /projects/{project_id}/role-grants/{grant_id}` | Every grant and qualification field, provenance, versions, revocation timestamps and replay preservation: E `read_project_*`, `project_issue_replay_unchanged_*`, `revoked_grant_readback_*`. |
| 25 | `POST /projects/{project_id}/role-grants/{grant_id}/revoke` | Both roles, reason boundaries, exact versioned receipt, preserved qualification, replay/mismatch/already-revoked conflict and lost contributor access: E `project_revoke_*`, `revoke_project_*`, `revoked_contributor_*`. |
| 26 | `POST /projects/{project_id}/guides` | Required version/examples/documents; optional summary; ordered exact example commitment; document label/media/order/unique IDs and waiting setup; bounds/invalid/recovery/authority/replay: E `guide_fields_*`, `guide_documents_*`, `guide_*_missing`, `guide_create_*`. |
| 27 | `PATCH /projects/{project_id}/guides/{guide_id}` | Summary only, omission/null/empty/max/type/NUL, immutable-field refusal, authority and exact metadata/replay: E `guide_patch_*`, `guide_foreign_actor_*`, `guide_rejected_body_unchanged`; A `closing_guide_patch_*` proves exact-project manager authority and retained metadata. |
| 28 | `PUT /projects/{project_id}/guides/{guide_id}/review-policy` | Every policy input including strict human-review mode; nondefaults/omission semantics; key/If-Match validation, unauthorized writes, exact generation/hash/predecessor and replay: E `*_review-policy`, `review-policy_fields_*`. |
| 29 | `PUT /projects/{project_id}/guides/{guide_id}/revision-policy` | Every revision-policy input, bounded rounds/deadline and state list, nullable reassignment, conditional mutation/replay and exact lineage: E `*_revision-policy`, `revision-policy_fields_*`. |

Read-only methods do not acquire mutation idempotency requirements. Field limits
are those in the current schema/owner, not invented client restrictions. Raw
reports retain their conservative `partial_positive` indexes; completing this
matrix is a bounded client-contract result, not a promise about every possible
input combination, production Flow deployment or unfinished product lifecycle.

For rows 22–25, A `closing_project_*` adds real foreign-manager and ordinary/
unauthenticated denials, wrong-project grant relations, malformed/missing keys,
and successful scoped controls with unchanged state after rejection. For rows
28–29, A `closing_review-policy_*` and `closing_revision-policy_*` add scoped
manager controls and foreign-manager/unauthenticated denials.

## Additional scenario detail


Project-role probes bind grantor and qualification-capture provenance to the
known HTTP-issued manager authority grant. Both contributor roles use exact
receipt, grant and qualification shapes, full current-state reads before and
after replay, malformed outer request/reason checks, and revoke replay/conflict
controls. Public-state comparisons preserve grant and snapshot timestamps; they
do not claim every hidden audit or authority table is unchanged.

Contributor-candidate probes require exactly `actor_profile_id` and
`display_name` in each row, with a known Unicode name and a privately populated
contact field in the fixture. They check populated pagination, cursor tampering
and project/limit binding, invalid query values, unauthenticated and unauthorized
callers, and exact membership after actor suspension/deactivation and identity-link
revocation/restoration. The existing twenty-human setup is reused, and a real
provisioned service actor must remain absent. Candidate listing is not a grant of
task access. Exact row checks are recorded as response predicates, not additional
nested field-index coverage entries.

Project/guide text probes retain the six surviving-field NUL regressions and
reject the removed inline-content field. The historical eight-field finding is
[API-DRILL-009](external-api-drill-findings.md#api-drill-009-project-and-guide-text-nul-becomes-503).
They require non-retryable 422 responses and valid same-key recovery. Fresh-key
guide PATCH controls compare public fields except `updated_at`; they are real
mutations, not proof of unchanged hidden history. The PostgreSQL regression
tests separately verify selected product and idempotency tables remain unchanged
after rejection, including the guide's internal mutation generation.

`backend/scripts/external_api_drill.py` is separate from the older API contract
drill. It uses a real local HTTP server, real token verification and PostgreSQL.
It does not seed product rows, disable guards, import the old drill or fake
agent/provider results. Initial Access Administrator bootstrap uses the existing
documented CLI and is recorded as setup, not an HTTP capability.

## Run

Use a disposable local PostgreSQL server, never a deployed database.

Run from a clean, frozen checkout. Do not commit, merge, pull or edit that checkout
while the drill runs: its later owner probes recheck the exact Git target against
the isolation metadata. Use a separate detached checkout if other work must
continue; a target-mismatch refusal is failed evidence, not a product defect.

From `backend/`, with an existing private output directory and the administrative
URL in `WORKSTREAM_TEST_ADMIN_DATABASE_URL`:

```sh
WORKSTREAM_ENVIRONMENT=local .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json /absolute/private/output/database.json \
  --timeout-seconds 1200 -- .venv/bin/python scripts/external_api_drill.py \
  --isolation-metadata /absolute/private/output/database.json \
  --report /absolute/private/output/report.json
```

The runner creates/migrates an isolated database and restricted role, then drops
both. The drill verifies matching runner metadata and connection identity and
requires an empty actor registry. The output file must not already exist and
must be outside the repository. The child server rejects an ambient backend
`.env` file, binds only loopback, and receives fresh test-only HMAC secrets.
No production Flow credentials, external model calls or storage providers are
used. The caller is responsible for stopping its disposable PostgreSQL server.
Local fixture tokens expire after one hour so rate-paced field drills can finish;
explicit expired-token probes retain their past expiry and must still return 401.
This changes neither deployed token verification nor authorization policy.
Local server readiness has a bounded 90-second monotonic deadline to accommodate
slow imports under machine load. Process exit or failure to become healthy still
fails the drill; a slow or unsuccessful startup is not API execution evidence.

Run helper tests from the repository root:

```sh
backend/.venv/bin/python -m unittest scripts.test_external_api_drill
```

## Interpret evidence

The separate `backend/scripts/admin_api_drill.py` entry point reuses this runner
for twenty HTTP-created human profiles, bootstrap and administrative authority.
Run the same isolated command above with `scripts/admin_api_drill.py` in place
of `scripts/external_api_drill.py` and retain the 1200-second timeout for rate pacing.
It performs actual local bootstrap CLI calls and read-only isolated-database
snapshots to check forbidden authority/state changes. All later mutations use
HTTP. The original no-product-SQL-write/no-disabled-guard rules still apply.
`local_evidence` cases are CLI/state/direct-concurrency assertions, not additional
HTTP endpoints. Cross-admin concurrent HTTP responses are checked there together
with their persisted outcome rather than counted as ordinary HTTP cases.
Concurrent calls demonstrate observed outcomes, not forced database lock overlap.
Self-removal HTTP denials exercise the self guards. Separately,
`admin_guard_probe.py` executes the actual grant/profile/link count guards under
the canonical control lock using stored rows established through HTTP/bootstrap.
Every probe rolls back and checks unchanged state. One/two effective admins,
suspended/revoked-link backup admins, restorations and post-revocation states
are compared. Separate ephemeral child-process mutations change `<= 1` to `< 1`
and must fail the exact affected checks; no product source file or API process
is changed. These are owner/transaction probes, not extra HTTP capabilities.
Missing groups remain incomplete, never certified.
Guard subprocess infrastructure failures retain an allowlisted `error_code` for
known isolation/target/count failures. Unexpected exceptions use
`guard_probe_failed`; arbitrary database or filesystem exception text is not
persisted because it can contain credentials or stored data.

Run its helper checks with
`backend/.venv/bin/python -m unittest scripts.test_admin_api_drill scripts.test_external_api_drill`.

The OpenAPI manifest inventories nested request/response fields. Each operation
records its executed cases and separates four evidence indexes:

- `field_cases`: passed strict-value comparisons and echoed request/correlation
  headers. Exact comparison of a populated object or array includes its nested
  values; an empty array never proves item fields.
- `predicate_cases`: passed explicit predicates, such as timestamp validity or
  page membership. A predicate is not automatically full value validation.
- `shape_cases`: passed exact top-level response-key checks, not field values.
- `request_cases`: scenario annotations describing exercised inputs. These are
  not independently verified value claims.

`uncovered_fields` lists schema fields without strict-value evidence; consult
the other indexes and named cases before treating these as missing tests.
Failed cases do not populate passed evidence indexes. These are
partial behavioral observations, not exhaustive schema certification:

- `partial_positive`: at least one successful HTTP case, not full readiness.
- `denial_only`: expected refusal observed; no successful use established.
- `failed`: a scenario assertion or request failed.
- `untested`: no case executed for that operation.

Even a field with a passing case can still need omission, boundary, invalid-type,
cross-field, persistence or permission proof. Use the fixed acceptance matrix
above and the actual run evidence, not automatic promotion from these counters.
Successful-only counts must never hide failures.

Initial cases cover token rejection, self-profile field values/bounds/nulls and
readback, administration/grant discovery, project creation/replay/conflict,
ungranted read denial, draft guides, initial review/revision policies and grant
revocation. Later field extensions are mapped in the fixed matrix above. Methods
outside that selection remain outside this audit; do not manufacture active-guide,
task or acceptance state to complete an OpenAPI inventory.

Extended cases check profile omission and normalization, response shape and
identity, policy replacement with a current selector, project length limits,
project-role access and revocation, service provisioning and identity-link
lifecycle. The client paces mutations against the default server rate budget;
it does not disable rate controls. Independent boundary failures are retained
while other independent probes continue, and any such failure keeps exit status
nonzero. A stored idempotent replay is not treated as current-state readback.

Field-extension cases traverse populated administrative grant, project-role and
contributor-candidate pages using identities independently established by HTTP
setup. They check missing, duplicate and foreign rows, filters, bounded limits
and cursor misuse. Project cursors are signed and bound to project/action/query;
administrative cursors are positional markers, not authority. Administrative
cursor reuse checks selector isolation rather than requiring signature rejection.
Nested qualification probes exercise required fields, container types, available
versus unavailable consistency, opaque references, UUID input and collection/
token bounds. Denials are followed by unchanged full grant-history readback, and the
same rejected idempotency key must admit a subsequent valid grant. Combined-bound
controls require successful readback of populated references at their exact limits.
They reproduced [API-DRILL-006](external-api-drill-findings.md#new-finding-api-drill-006--valid-qualification-exceeds-internal-admission-limit),
now repaired with a project-role-specific canonical request budget. Their
expected 201 is unchanged, and any failure still makes the drill exit nonzero.
Failed combined-bound controls also check unchanged
full history and denied project access. Independent smaller grant controls,
including a populated value for every reference collection, continue afterward.

## MCP handoff boundary

Service-subject NUL probes use valid idempotency headers and retain the same key
for subsequent valid provisioning. Invalid input must return non-retryable 422;
the focused PostgreSQL regression separately proves unchanged actor/link and
authority state plus exact 200-byte Unicode subject storage and replay. These
cases cover provisioning validation, not activation of every service action.

The active drill scope is **currently usable public APIs**, not every operation
discovered in OpenAPI. Hidden implementation routes and unfinished lifecycle
paths are excluded until their owners expose a supported client flow. A public
route with an unmet prerequisite is not automatically a usable adapter tool;
an operator-only route is not an ordinary contributor tool. Discovery entries
remain diagnostic navigation, not a denominator of APIs to certify.

The policy field extension covers the already usable draft-guide review-policy
and revision-policy PUT operations. It probes optional-field rejection, explicit
nondefault values, malformed/missing update headers, random mismatched selectors and
unauthorized mutations. Fresh authorized successors prove exact generation and
supersession after denials, not merely cached replay. Omitted ordinary optional
fields restore defaults; omitted `human_review_required` preserves the selected
predecessor's mode. Only an explicit setting changes that mode. These checks
establish policy configuration behavior, not runtime review or acceptance.
The random-selector probe is not evidence of stored cross-project isolation.

The endpoint-by-endpoint extension stays within the 29 canonical operations
already exercised by these two drills. Superseded identity, eligibility
and task surfaces are not MCP candidates or targets of this extension;
their removal belongs to the task owner. Do not expand this set merely because
an operation appears in OpenAPI.

The first checks cover exact unauthenticated health JSON, complete self-profile
business-field readback after valid and rejected updates, mixed valid/invalid
PATCH atomicity, and self authorization-context selectors, exact contributor
actions, revocation and an actual stored foreign project. Health is liveness,
not database/storage readiness. Profile reads intentionally advance admission
timestamps, so unchanged-business-state assertions compare every stable field
and require valid monotonic `updated_at`/`last_seen_at`, not timestamp equality.
These cases do not certify the remaining endpoint contracts automatically.
Actor administration additionally checks complete human profile identity and
lifecycle output fields, exact mutation receipts, same-key replay, and unchanged
target readbacks after invalid reasons. Lifecycle reasons use a 500-byte UTF-8
positive boundary and reject 502-byte and NUL inputs. Suspended actors may neither
read nor update their own profile. Denied self-reads do not advance admission
timestamps; an authorized administrator can inspect the suspended profile.
Deactivated actors may likewise do neither.
Embedded-NUL self-profile cases preserve
[API-DRILL-007](external-api-drill-findings.md#api-drill-007-embedded-nul-in-canonical-profile-fields-becomes-503)
as a permanent 422 regression expectation after the request-validator repair;
independent checks continue only after an unchanged profile readback. A run
containing that failure is not a passing API handoff.
The context selector similarly preserves
[API-DRILL-008](external-api-drill-findings.md#api-drill-008-nul-project-selector-becomes-503)
with a valid-selector and unchanged-project control before continuing. The
query now rejects NUL before lookup; neither fix changes authorization or storage.
Catalogue probes compare all 74 permission identifiers and every field of the
five administrative role definitions against frozen client expectations. Both
catalogues reject unauthenticated and ungranted callers. The twenty-actor role
matrix reuses the same complete role definition oracle. A catalogue entry is
not a claim that its action or downstream API is activated.
Administrative grant history probes compare the entire single-target public
row, including grantor/revoker references, reasons, nulls and timestamps. The
first read happens before replay, followed by exact full-state equality after
replay. Independent database snapshots continue to detect hidden duplicates.
Grant issue and revoke also reject NUL-containing reasons with 422 before the
same idempotency key is reused for the valid operation. Their permanent denial
probes use the existing unchanged-authority snapshot checks; PostgreSQL regression
additionally checks audit/control state and 500-byte Unicode recovery.
Identity-link lifecycle probes additionally reject malformed reason fields and
unknown fields, compare the entire stored public link view after each denial,
and preserve every unchanged field across revoke/reactivate. Reactivation must
clear `revoked_at` while recording its own timestamp; a partial status assertion
does not stand in for the full response contract.

Prepare the endpoint-and-field handoff from named passing client cases, not the
OpenAPI route list or aggregate test count. For each selected operation include
its method/path, caller grant requirements, request fields and headers, response
fields, observed errors, replay rules and remaining unchecked combinations.
Keep privileged administration separate from ordinary contributor tools. The
bootstrap CLI is deployment setup, never an HTTP or MCP capability. These
drills exercise draft project/guide surfaces; they do not establish the live
unified setup, submission, checker or acceptance path for an adapter.

The original metadata/authority entry points do not prove deployment connectivity,
real Flow integration, S3 custody, model quality, the unified setup pipeline, or
end-to-end acceptance. Their storage is disabled and no documents are uploaded.
A successful partial run cannot certify those surfaces for an MCP adapter.

## Public guide document pass

After the merged guide-intake cutover, `guide_payload` declares required documents.
Create-response checks cover document IDs, order, labels, media types and waiting
setup; PATCH still checks only its metadata response, not the create-only fields.
Prior execution results remain bound to their earlier target.

`backend/scripts/guide_document_api_drill.py` reuses the same HTTP/token/report
runner for the now-public upload and setup diagnostic routes. It uses two genuine,
shareable PDFs, an isolated runner-owned PostgreSQL database and MinIO bucket,
and a separately owned loopback Redis broker and actual Celery worker. The
canonical fixed guide-document parser must already be running as a separate,
networkless service with its own UID and socket custody. The drill passes its
canonical socket setting only to its preflight client and Celery worker environment;
the API subprocess does not receive that setting. The drill does not start a
parser inside the Celery worker or give the parser provider credentials, database
access, or an artifact-store mount.
The Celery worker transmits only the bounded document bytes required by the parser
protocol. The drill does not seed product rows or substitute a parser or
model/provider implementation.
The private provider configuration contributes only the explicitly selected
provider key and project-agent settings, never another worktree's database,
authority, storage, or parser configuration.
Install the repository-declared runtime extra first (`uv sync --frozen --extra
agents --extra dev` from `backend/`) and verify `import agents, openai` succeeds
in the interpreter used for both the drill and its Celery worker. A missing SDK can
leave setup reserved without ever invoking the model; it is not usable-flow proof.

Supply these environment variables to the isolated runner:

- `WORKSTREAM_DRILL_PROVIDER_ENV`: explicitly approved private provider env file.
- `WORKSTREAM_DRILL_GUIDE_PDFS`: JSON array of two local PDF paths, each at most 10 MiB.
- `WORKSTREAM_DRILL_BROKER_URL`: disposable loopback Redis broker, not another Celery worker's queue.
- `WORKSTREAM_DRILL_SCRATCH_ROOT`: unique private processing directory.
- `WORKSTREAM_DRILL_GUIDE_PARSER_SOCKET`: absolute path to the already-running
  isolated parser socket. The canonical deployed path is
  `/var/lib/workstream/guide-runtime/guide.sock`.
- `WORKSTREAM_TEST_MINIO_ENDPOINT`: local MinIO endpoint supported by the isolated runner.

Invoke the guide entry point using the same `--isolation-metadata` and `--report`
arguments and `--timeout-seconds 2400` on the isolated runner to cover its
1800-second setup observation window plus startup and cleanup. Use a Python
environment with the repository's agent dependencies.
Real model execution can incur provider usage; it requires explicit approval.
The operator owns parser startup and shutdown as well as broker teardown. The
runner verifies database/bucket cleanup; the entry point stops its API and
Celery worker even when a scenario fails.

This pass checks partial-upload waiting, exact commitments, replay, ungranted and
wrong-media denials, independently rereads stored original bytes, and observes
the real Celery worker through public setup diagnostics. Before it reads either
private PDF, creates a project or guide, starts the Celery worker, or permits model
inference, it sends a fixed synthetic Markdown parse through the canonical client.
An absent socket, wrong socket custody, malformed protocol response, or wrong
fixed-parser identity fails the drill without exposing the synthetic text in the
report. A model finding that a guide
is insufficient is a product outcome, not automatically an API defect. Finishing
setup does not certify manager approval, active project policy, submission or
acceptance. New upload/setup/findings operations are outside the original
29-operation census and must be reported separately with their actual evidence.

The diagnostic Celery worker consumes only the default `celery` queue with the
validated prefork, Redis visibility and no-prefetch topology required for inference.
It does not consume `workstream.outbox`; that queue has its own prefork validation
owned by the outbox topology. This pass therefore does not claim outbox delivery
evidence and must not add the outbox queue to that Celery worker.

The provider's unresolved outcome can describe an invocation still in flight:
observe the same setup run through completion or the bounded timeout, without
retrying inference. Exact upload replay retains the API-DRILL-010 regression;
failed assertions remain failed even when independent setup steps finish.

The resumed administrator pass at clean `d85258f8` completed 472 HTTP/local
evidence cases with twenty actors and ten owner-guard probes, without failures.
The separate metadata continuation completed 464 cases; the preceding run's
guide-version recovery assertion mismatch was corrected and replayed there.
Those two reports exercise 27 original HTTP operations. The earlier interrupted
metadata run also exercised both policy contracts; a fresh clean `e98ad76d`
continuation passed 84 cases: 47 review-policy, 30 revision-policy and seven
setup calls, with database cleanup complete. Across these passes the original
29 operations have executed scenarios, not every field combination. Do not add
the local evidence operations to the API count.

The live guide diagnostic at dirty `ac695417` completed 31 cases with two
retained replay failures. Both original PDFs were independently reread from
MinIO, actual broker delivery invoked the configured model, and setup persisted
a `sufficiency_blocked` report readable through the public API. Database and
bucket cleanup passed. That run did not inspect findings fields; the later
report-lineage predicate and private findings capture were not exercised there.

The subsequent clean `869a1d71` live run passed all 36 cases after the terminal
replay and denial-mapping repairs. Both exact replays returned `object_confirmed`;
both original PDFs were independently reread before and after resolver
deactivation. That deactivation made replay return concealed 404, with unchanged
public setup. The findings response matched the completed setup's report ID,
project, guide, source snapshot and generation before private retention.
Database and bucket cleanup completed. Fourteen focused real PostgreSQL/MinIO
regressions also passed, including unchanged terminal state and a single durable
denial audit. These are local execution results, not hosted-suite evidence.

That model outcome was `sufficiency_blocked`, with reported gaps concerning
archive bounds, content validation and post-submit evaluation. A stored finding
is evidence of the model's assessment, not proof that its capability mapping is
correct. This pass does not certify manager approval, activation, all public API
fields, or a complete MCP handoff.

At integrated `dd943749`, a fresh two-PDF run reached `schema_invalid` without a
sufficiency report. A separately isolated observation-only diagnostic rerun
completed 34 HTTP checks and produced a blocked report. The first failure remains
unexplained, not repaired by the second outcome. Both runs verified exact uploaded
bytes and completed local resource cleanup. The second also checked findings
lineage and denied inactive-resolver replay without changing setup or originals.
Its claimed encryption-check gap needs owner review: ART already rejects encrypted
ZIP entries. Its separate requests for project-specific expanded-size and member
limits must not be confused with ART's existing startup safety bounds. These are
historical observations, not finished API coverage. Subsequent source tracing
confirmed the existing package-size rule already enforces expanded bytes; its
proposal field now explains that meaning. The new `maximum_archive_entries`
rule limits normalized outer-ZIP tree entries, including implied parent directories, through
the same locked policy/compiler path. The separate `maximum_archive_size_bytes`
rule compares the entire compressed ZIP's verified byte count, including archive
metadata; it does not reuse expanded size. None of these changes exposes hidden intake APIs.
Fresh real-provider execution must retain its own exact target and results.

The post-POL-05B replay at `89a86753` completed 33 expected HTTP observations but
failed its draft-readiness assertion on an assistant-authored nested-archive
prohibition. The human subsequently rejected that restriction: submission ZIP
members may have any file type, including nested archives. Preserve the old PDF
and failed result, and version corrected inputs for the next run; this is a drill
fixture correction, not a product detector requirement. See the
[retained capability finding](external-api-drill-findings.md#post-pol-05b-replay-nested-archive-capability-gap).
This is not complete-guide success. POL-05B's proposal read, pre-submission
approval, correction and dispatch are now public; this replay did not exercise
those four operations and does not add them to the original 29-operation census.
