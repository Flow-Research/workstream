# External-client API drill

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
revocation/restoration. The existing twenty-human setup is reused; service-actor
exclusion is not established by this group. Candidate listing is not a grant of
task access. Exact row checks are recorded as response predicates, not additional
nested field-index coverage entries.

Project/guide text probes include all eight NUL-input regressions from
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

Use a disposable local PostgreSQL server, never a deployed database. From
`backend/`, with an existing private output directory and the administrative URL
in `WORKSTREAM_TEST_ADMIN_DATABASE_URL`:

```sh
WORKSTREAM_ENVIRONMENT=local .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json /absolute/private/output/database.json \
  --timeout-seconds 480 -- .venv/bin/python scripts/external_api_drill.py \
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
of `scripts/external_api_drill.py` and allow a 900-second timeout for rate pacing.
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
cross-field, persistence or permission proof. No operation is promoted to fully
verified by this initial slice. Successful-only counts must never hide failures.

Initial cases cover token rejection, self-profile field values/bounds/nulls and
readback, administration/grant discovery, project creation/replay/conflict,
ungranted read denial, draft guides, initial review/revision policies and grant
revocation. Other methods, nested policy fields and response fields remain
explicitly uncovered. Add independent scenarios as current APIs become reachable;
never manufacture active-guide, task or acceptance state to complete a report.

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
positive boundary and reject 502-byte and NUL inputs. Suspended actors may read
their own profile, including their suspended status, but may not update it;
that allowed read advances admission timestamps. Deactivated actors may do neither.
Embedded-NUL self-profile cases preserve
[API-DRILL-007](external-api-drill-findings.md#api-drill-007-embedded-nul-in-canonical-profile-fields-becomes-503)
as a permanent 422 regression expectation after the request-validator repair;
independent checks continue only after an unchanged profile readback. A run
containing that failure is not a passing API handoff.
The context selector similarly preserves
[API-DRILL-008](external-api-drill-findings.md#api-drill-008-nul-project-selector-becomes-503)
with a valid-selector and unchanged-project control before continuing. The
query now rejects NUL before lookup; neither fix changes authorization or storage.
Catalogue probes compare all 73 permission identifiers and every field of the
five administrative role definitions against frozen client expectations. Both
catalogues reject unauthenticated and ungranted callers. The twenty-actor role
matrix reuses the same complete role definition oracle. A catalogue entry is
not a claim that its action or downstream API is activated.
Administrative grant history probes compare the entire single-target public
row, including grantor/revoker references, reasons, nulls and timestamps. The
first read happens before replay, followed by exact full-state equality after
replay. Independent database snapshots continue to detect hidden duplicates.
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
and a separately owned loopback Redis broker and actual Celery worker. It does
not seed product rows or substitute a model/provider implementation. The private
provider configuration contributes only `OPENAI_API_KEY` and project-agent
settings, never another worktree's database, authority or storage configuration.

Supply these environment variables to the isolated runner:

- `WORKSTREAM_DRILL_PROVIDER_ENV`: explicitly approved private provider env file.
- `WORKSTREAM_DRILL_GUIDE_PDFS`: JSON array of two local PDF paths, each at most 10 MiB.
- `WORKSTREAM_DRILL_BROKER_URL`: disposable loopback Redis broker, not another Celery worker's queue.
- `WORKSTREAM_DRILL_SCRATCH_ROOT`: unique private processing directory.
- `WORKSTREAM_TEST_MINIO_ENDPOINT`: local MinIO endpoint supported by the isolated runner.

Invoke the guide entry point using the same `--isolation-metadata` and `--report`
arguments. Use a Python environment with the repository's agent dependencies.
Real model execution can incur provider usage; it requires explicit approval.
The operator owns broker teardown. The runner verifies database/bucket cleanup;
the entry point stops its API and Celery worker even when a scenario fails.

This pass checks partial-upload waiting, exact commitments, replay, ungranted and
wrong-media denials, independently rereads stored original bytes, and observes
the real Celery worker through public setup diagnostics. A model finding that a guide
is insufficient is a product outcome, not automatically an API defect. Finishing
setup does not certify manager approval, active project policy, submission or
acceptance. New upload/setup/findings operations are outside the original
29-operation census and must be reported separately with their actual evidence.

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

The real model outcome was `sufficiency_blocked`: the original project requests
archive bounds, content validation and post-submit audit evaluation not supported
by the selectable catalogue. Those are legitimate project capability gaps, not
API failures or human acceptance. This pass does not certify manager approval,
activation, all public API fields, or a complete MCP handoff.
