# External API drill: repair handoff

## Purpose and sequence

This preserves the human-requested repair handoff and original reproductions,
not a finished API catalogue or an MCP readiness report. PR #392 repaired the
five defects below. Both original drills passed on merged main `c681b51f`, with
226 external-client cases and 352 administrator checks, without unexpected
failures. The administrator run included twenty distinct actors and detected
all three intentional last-admin guard mutants. These counts include negative
and local evidence cases; they are not endpoint or exhaustive field counts.
The orchestrator is extending the remaining client field checks before handing
the verified endpoint-and-field list to the MCP adapter agent. The descriptions
for repaired items remain historical observations, not claims that those defects
persist. API-DRILL-007 and API-DRILL-008 below preserve the NUL defect
reproductions and their bounded request-validation repairs.

Human-confirmed v0.1 project roles are **submitter** and **reviewer**.
Adjudication is deferred. Do not implement adjudicator functionality, widen an
audit allowlist to support it, or introduce a compatibility path to make the
old advertised role pass.

## API-DRILL-010: successful guide-document replay returns stale

- Original reproduction after integration of merged PRs #396/#397, product main
  `53fec2b25590887f333321616ffca5ba59eaaf5f`. The new live guide drill ran
  against local head `ac695417` with uncommitted drill-only assertion changes;
  this is not clean-candidate or hosted verification.
- Create a project and a guide declaring two original PDF documents through
  public APIs as an authorized Project Manager. Upload the first PDF using a
  fresh UUID idempotency key, then resend the exact bytes, media type, document
  path and key. The original upload returns 202 with the expected canonical
  SHA-256 commitment and byte count. Replay returns 202 and `replayed: true`,
  but its public status is `stale`, not a completed document result.
- Reproduction uses an isolated migrated PostgreSQL database, real MinIO,
  public service provisioning and normal Flow-token verification. No product
  SQL writes, disabled triggers or fabricated provider receipts are involved.
- The terminal put has already become `object_confirmed`. The replay path in
  `GuideArtifactIngestService.publish` calls `resume_committed_put`, which
  enters `resolve_put_attempt`. Its observation claim only accepts unfinished
  puts, so the terminal attempt cannot be claimed and returns `stale`.
- Repair boundary: the existing ART replay operation must return an authorized,
  validated terminal result without creating a second upload, inference or
  storage owner. Preserve unfinished-put recovery, exact ownership/commitment,
  namespace binding, fencing and atomicity. The same bounded repair now returns
  `object_confirmed` after current authority consumption, before any unfinished
  observation claim or provider operation. Initial upload remains `document_stored`.
- Private evidence: `live5-report.json` and `live5-database.json` under
  `/tmp/workstream-api-resume.ipB7lK/`; case `upload_replay_0`, recorded status
  `stale`. These historical failures are not relabeled as passing.
- At clean `869a1d71`, fourteen focused PostgreSQL/MinIO regression cases passed;
  a separate real two-PDF/Celery/model run passed all 36 cases, including both
  exact replays and independent stored-byte verification. Removing only the
  terminal-return branch in memory made the regression fail on `stale` versus
  `object_confirmed`, demonstrating that it detects the original defect.

## API-DRILL-011: inactive guide resolver denial escapes as 500

- Reproduced during the replay repair: upload successfully, deactivate the
  fixed put-resolver actor through the administrator API, and resend the same
  upload. AUTH denies correctly, but its internal exception escaped the public
  guide composition as HTTP 500. The initial mapping caught a distinct public
  exception class, so rollback and denial restaging were not reached.
- The existing ART-owned authority adapter now owns a shared denial boundary:
  roll back denied work, restage canonical AUTH denial evidence, then translate
  to the existing concealed ART denial. Guide upload and internal Celery operations reuse
  that operation; no new private AUTH import, permission or generic catch is added.
- Real HTTP/PostgreSQL/MinIO regression proves 404, unchanged terminal upload
  fields, no provider operation, no extra dispatch, and exactly one
  `actor_deactivated` denial audit. The clean `869a1d71` live run additionally
  proves unchanged public setup and both stored originals after denied replay.
- Local raw artifacts live under `/tmp/workstream-api-replay.9kz5fH/`:
  `verified-regression.xml`, `verified-live-report.json` and their runner metadata;
  database and bucket cleanup completed. These private artifacts are not durable
  links or hosted CI evidence, and neither repair certifies every public API field.

## API-DRILL-012: administrative grant reasons containing NUL return 503

- Reproduced at clean `6b059004` through a fresh real HTTP server, normal
  token verification, local administrator bootstrap and isolated PostgreSQL.
  Both `POST /api/v1/admin-role-grants` and its `/{grant_id}/revoke` operation
  returned 503 `service_unavailable` for `reason: "bad\u0000reason"`.
- The shared public `Reason` type enforced 1–500 UTF-8 bytes but did not reject
  NUL. PostgreSQL cannot store NUL in the existing reason text columns.
  Complete public grant-history readbacks stayed unchanged after both failures;
  valid requests using the rejected keys succeeded. No authorization bypass
  or partial grant mutation was observed.
- Repair: reject NUL in that existing shared request constraint before
  reservation/storage. Preserve the byte bound, Unicode, whitespace, authority,
  idempotency and retained history. No migration or service change is needed.
- The real PostgreSQL regression checks issue and revoke independently for
  NUL and oversized UTF-8 input, unchanged grants/control/idempotency/audit,
  valid 500-byte Unicode same-key recovery, stored reason/version and exact
  replay. The administrator drill retains both NUL probes and reuses its
  existing wrong-status/changed-state falsification helper tests.
- Private original evidence: `/tmp/workstream-api-replay.9kz5fH/admin-reason-report.json`
  and `admin-reason-database.json`; both failed cases remain recorded and the
  disposable database was removed. This is not complete API certification.

## API-DRILL-013: service provisioning subject containing NUL returns 503

- Reproduced at clean `4a5c475f`: `POST /api/v1/service-actors` returned 503
  `service_unavailable` for both `service\u0000subject` and `\u0000` subjects,
  instead of rejecting invalid input with 422. The real HTTP run used normal
  token verification, local administrator bootstrap and an isolated database.
- The existing `OpaqueSubject` bounded UTF-8 length and whitespace but admitted
  NUL into PostgreSQL subject lookup/persistence. Both attempts preserved the
  observed authority/product/audit state. A 200-byte Unicode subject then
  succeeded using the same key, with exact replay and service-token resolution.
- The bounded repair adds NUL rejection to the existing public subject
  constraint. It preserves opaque identity, Unicode, the 1–200 byte bound,
  authority and idempotency. No service implementation or migration changes.
- PostgreSQL regressions compare complete actor/link and authority snapshots
  after rejection, then verify stored Unicode subject, same-key recovery and
  exact service/idempotency state on replay. Administrator observation timestamps
  may legitimately advance on successful replay. Permanent live probes retain
  failed expectations rather than swallowing failures or replacing the key.
- Original private evidence is `service-report.json` and `service-database.json`
  under `/home/abiorh/flow/api-drill-resume.6Rns3Y/`; the failed report remains
  unchanged and isolated database/role cleanup completed. These are local
  diagnostic artifacts, not hosted evidence or exhaustive API certification.

## Evidence boundary

- Product source: `b4b3d1d95d302011839f6f9dff3e2cb7c06c2124` (merged PR 390).
- Clean drill target `430c14d7547990c81eb6fe975b1757135d6aaf7f` reproduced the
  three oversized-field failures and the adjudicator grant failure.
- The subsequent `319f4ece509d645f7536b98da653921ac50a93cd` drill adds null-content,
  same-key recovery and forbidden-side-effect checks. Its raw evidence belongs
  to that exact target, not to later edits of this handoff or the drill.
  That run completed 226 cases: 109 successful calls, 112 expected denials and
  the five failures below. The final exit was nonzero. Its field audit remains
  incomplete; those counts are cases, not fully verified endpoints.
- Real loopback Uvicorn/FastAPI, normal Flow token verification with a fresh
  test-only issuer, and a fresh migrated PostgreSQL 17 database were used.
  The supported initial Access Administrator bootstrap CLI was setup only;
  subsequent product mutations used HTTP.
- No direct product-state inserts, disabled triggers, authentication overrides,
  old API-drill imports, fake model execution or production credentials.
- Artifact storage and automatic setup execution were disabled. Storage/model
  dependent flows and unavailable public activation are not positive evidence.

Local raw run evidence is under `/tmp/workstream-api-fields.TXbSNQ/`:
`run2.json`, `run3.json`, `run4.json`, matching `db*.json`, and the private
PostgreSQL log. These are temporary local artifacts, not durable shared links;
the reproductions and repair criteria below must remain sufficient without them.
Do not commit credentials, raw HTTP bodies, database connection strings or logs.

## Confirmed repair items

### API-DRILL-001: oversized project name becomes a service failure

- Route: `POST /api/v1/projects`, authorized system Project Manager, valid
  `Idempotency-Key`.
- Reproduce: `name` is 201 ASCII characters; `slug` is a fresh ordinary value.
- Observed: HTTP **503**, `error.code=service_unavailable`.
- Positive control: 200-character name succeeds and reads back unchanged.
- Cause: `ProjectCreate.name` is an unrestricted string, while `Project.name`
  is `varchar(200)`. PostgreSQL reported the exact length violation.
- Required repair: align public validation/OpenAPI with the existing 200-character
  persistence limit. Reject oversize input with 422 before attempting the write;
  retain legitimate Unicode and exact-limit behavior.
- Retest: `project_maximum_lengths`, `project_maximum_readback`, `overflow_name`,
  `overflow_name_retry_after_rollback`; add focused product regression coverage.

### API-DRILL-002: oversized project slug becomes a service failure

- Route and authority: same as API-DRILL-001.
- Reproduce: fresh `slug` is 121 ASCII characters; `name` is an ordinary value.
- Observed: HTTP **503**, `error.code=service_unavailable`.
- Positive control: 120-character slug succeeds and reads back unchanged.
- Cause: unrestricted `ProjectCreate.slug` versus `Project.slug varchar(120)`.
- Required repair: enforce the existing 120-character bound at the public
  boundary. Preserve duplicate-slug 409 behavior and idempotent replay/conflict.
- Retest: `overflow_slug`, `overflow_slug_retry_after_rollback`,
  `project_maximum_lengths`, `project_duplicate_slug`, `replay_project`,
  `conflicting_project_replay`.

### API-DRILL-003: oversized guide version becomes a service failure

- Route: `POST /api/v1/projects/{project_id}/guides`, authorized Project Manager,
  existing draft project, fresh UUID idempotency key.
- Reproduce: `version` is 51 ASCII characters and `content_markdown` is ordinary
  non-null guide text.
- Observed: HTTP **503**, `error.code=service_unavailable`.
- Positive control: a 50-character version succeeds.
- Cause: unrestricted `ProjectGuideCreate.version` versus
  `ProjectGuide.version varchar(50)`.
- Required repair: public/OpenAPI maximum of 50 characters; oversize input
  rejects with 422. Preserve version uniqueness, authorization and replay.
- Retest: `guide_maximum_version`, `overflow_version`,
  `overflow_version_retry_after_rollback`, `guide_current_state_after_overflow`.

### API-DRILL-004: nullable guide edit contradicts stored content

- Route: `PATCH /api/v1/projects/{project_id}/guides/{guide_id}`, authorized
  manager, existing draft guide with no source snapshot, fresh idempotency key.
- Reproduce: `{"content_markdown": null}`.
- The update schema admits null and the service assigns it to the stored guide;
  PostgreSQL then reports a `content_markdown` NOT NULL violation.
- Observed: HTTP **503**, `error.code=service_unavailable`. A fresh authorized
  current-state check confirmed that the original content remained intact.
- Required repair: distinguish omission from explicit null. Omitted content
  preserves existing content; explicit null rejects with 422. Do not make the
  stored guide nullable or silently reinterpret null as a successful edit.
  Preserve independently nullable `change_summary`.
- Retest: `guide_null_content`, `guide_null_content_unchanged`, valid content
  replacement, omission, nullable summary, unauthorized edit and unchanged
  current-state checks. Verify a rejected edit does not advance guide/replay state.

### API-DRILL-005: deferred adjudicator role is exposed as an input option

- Route: `POST /api/v1/projects/{project_id}/role-grants`.
- Reproduce: authorized manager, active human target, `role="adjudicator"`,
  valid qualification evidence and reason, fresh UUID idempotency key. The same
  request shape succeeds for submitter and reviewer.
- Observed: HTTP **503**, `error.code=service_unavailable`; PostgreSQL rejects
  the grant's audit event under `ck_audit_events_fact_bounds`.
- Current mismatch: the public `ProjectRole` enum, grant/qualification database
  checks and some current documentation admit adjudicator. The baseline's
  `authority_facts_are_safe` role allowlist omits it, although the event-specific
  project-grant rule includes it.
- Human resolution: this is **an unsupported-role exposure to remove**, not a
  request to make adjudicator issuance succeed. The public contract should offer
  only submitter/reviewer; adjudicator input should reject with 422, create no
  grant and confer no access.
- Reconcile affected request/response/filter schemas, authoritative role
  vocabulary, persistence and audit contracts, tests and current documentation
  consistently. Inspect actual dependencies before removing symbols; do not
  mechanically delete unrelated future-adjudication discussion or weaken audit
  checks. Follow the repository's current fresh-baseline/migration procedure.
- Retest: `unsupported_adjudicator_rejected`,
  `unsupported_adjudicator_no_active_grant`, `unsupported_adjudicator_no_access`,
  and all submitter/reviewer issuance, read, authority-context and revocation cases.
  Earlier raw runs tested the then-advertised enum with expected 201; the drill
  now expects 422 following the human scope clarification. Do not relabel the
  earlier execution as a run of that changed assertion.

The clean run also confirmed corrected same-key project/guide requests succeed
after the length failures; denied foreign edits preserve the original guide;
and the failed adjudicator request leaves no active grant or project access.
These checks bound the observed damage but do not make the incorrect 503s
acceptable. Database and restricted-role cleanup completed successfully; the
owned PostgreSQL server was stopped after the run.

## Repair owners and source locations

- [Project API schemas](../../backend/app/modules/projects/schemas.py):
  `ProjectCreate`, `ProjectGuideCreate`, `ProjectGuideUpdate`.
- [Project persistence](../../backend/app/modules/projects/models.py):
  `Project`, `ProjectGuide`.
- [Project creation](../../backend/app/modules/projects/create_service.py) and
  [guide mutations](../../backend/app/modules/projects/guide_mutation_service.py).
- [AUTH role vocabulary](../../backend/app/modules/authorization/schemas.py),
  [project-role request schemas](../../backend/app/modules/authorization/project_role_schemas.py),
  [AUTH persistence](../../backend/app/modules/authorization/models.py) and
  [grant service](../../backend/app/modules/authorization/project_role_service.py).
- [Canonical database baseline](../../backend/alembic/baseline/v01_schema.sql):
  `authority_facts_are_safe`, `authority_event_facts_are_safe`, role constraints.
- Current role wording in [AUTH specification](../spec_authorization_service.md),
  [glossary](../glossary.md), [architecture](../architecture_lockdown.md) and
  [review lifecycle](../spec_review_lifecycle.md) needs reconciliation with the
  human's two-role scope; assess the [roadmap](../roadmap_status.md) in the repair PR.

## Bounded repair implementation

The [repair change record](../../.commitrail/changes/api-drill-defect-repair.md)
covers the five fixes and their additional regression proof. Request validation
uses the existing 200/120/50 character limits; guide PATCH distinguishes omitted
content from explicit null; current project roles are submitter and reviewer.
The incremental role migration refuses incompatible retained authority history
without deleting or relabeling it. These repair statements do not reattribute
the historical executions above or complete the remaining API audit.

## Drill integrity fixes already made

These are harness repairs, not additional product defects for the other agent:

- A later successful call cannot erase an earlier failure.
- Collected independent failures keep the final CLI exit nonzero.
- Response equality checks nested types strictly: `true` cannot pass as `1`.
- A denied foreign guide edit is followed by a fresh authorized read of that
  same guide through a no-op PATCH, rather than a cached idempotent response.
- Policy-state preservation uses a fresh selector-bound update; cached replay
  alone is not claimed as proof of current state.
- Request pacing retains the server's existing mutation limits.

## New finding: API-DRILL-006 — valid qualification exceeds internal admission limit

**Repaired by the operation-specific admission change; original evidence below.**
The extended drill at `cf5e4633` against unchanged product main `c681b51f`
observed HTTP **500**, `error.code=internal_error`, for both submitter and
reviewer grants with valid populated qualification fields.

- Route: `POST /api/v1/projects/{project_id}/role-grants`.
- Setup: active system Project Manager; separate active, linked human target;
  HTTP-created draft project; no existing active exact-role grant; valid fresh
  UUID `Idempotency-Key` and reason `Exact project contribution role`.
- Qualification: each skills/reputation snapshot is `available`, with null
  `unavailable_reason` and twenty references: one 120-character `x` token plus
  nineteen short `skill:<n>` or `rep:<n>` tokens. Supply twenty distinct canonical
  UUID strings in `prior_project_work_refs`. External expertise contains one
  120-character `x` token plus nineteen `expertise:<n>` tokens (`n` from 0 to 18).
- Every field passes `ProjectRoleGrantIssueBody`; lists are at the advertised
  twenty-item limit and tokens at or below 120 characters. Canonical request
  serialization is 2,250 bytes for submitter (2,249 for reviewer) in this recipe.
- `parse_authority_request` in `authorization/schemas.py` rejects canonical
  requests above 2,048 bytes with `TypeError("invalid authority mutation request")`.
  `ProjectRoleGrantMutationService.reserve` reaches this check before completing
  the grant. A direct schema/admission probe reproduces the rejection without a
  database; the real HTTP cases reproduce the external 500.
- Repair: strictly validated project-role issuance uses a 9 KiB canonical
  envelope, sufficient for its actual largest permitted request (8,626 bytes).
  Every other authority mutation retains 2,048 bytes. Public field constraints,
  authorization, idempotency, snapshots and bounded audit projections remain
  unchanged. Selection occurs after validation of the closed request union.
- Retest: `qualification_combined_limits_submitter` and
  `qualification_combined_limits_reviewer` must return 201, read back every
  supplied reference and revoke normally. Keep independent smaller positive,
  replay and lifecycle controls; malformed cases must still reject without any
  new grant history. Add focused product-level regression and safe-bound tests.

The same PR now includes public-maximum parser and PostgreSQL regressions for
both roles: exact persisted references/readback, replay, mismatch and conflict
without another snapshot, and unauthorized refusal without grant, snapshot,
idempotency or audit residue. Envelope-edge tests retain bounded admission and
generic errors without rejected input in parser-owned traceback locals. Caller
frames and unrelated process memory are outside that diagnostic guarantee.
Both complete drills must pass on the repaired
candidate; the original failed runs are historical and remain unchanged outside
Git. This repair does not certify every other API field or deployed provider.

## API-DRILL-007: embedded NUL in canonical profile fields becomes 503

- Repair: the existing profile validator now rejects NUL before normalization
  or persistence. `test_profile_nul_rejected_without_partial_update` covers both
  fields, mixed valid/invalid atomicity and a subsequent valid Unicode update.
- Route: `PATCH /api/v1/actors/me`, authenticated human self-profile update.
- Inputs: `{"display_name":"before\u0000after"}` and, independently,
  `{"contact_email":"before\u0000after"}`.
- Expected: 422 `invalid_request` before persistence. PostgreSQL text cannot
  represent this character; rejecting it is storage-contract validation, not a
  new profile-format restriction.
- Observed: both returned 503 `service_unavailable` on clean
  `54f7343851235290697b801963687e583eb703e1`. Subsequent HTTP reads proved all
  stable/business profile fields unchanged. Admission timestamps may advance
  on those successful reads.
- Cause: `ActorProfileUpdateRequest.normalize_optional_text` accepts embedded
  NUL; `ActorService.update_self` reaches PostgreSQL, and the route maps the
  storage failure to service unavailability.
- Repair owner: actor self-profile schema/service tests. Reject the unsupported
  character at public validation; preserve valid Unicode, trimming, explicit
  null, omission, field limits and authorization. Do not sanitize silently,
  change storage, or weaken the expected status to accommodate the failure.
- Permanent reproduction: `display_name_nul` and `contact_email_nul` in
  `backend/scripts/external_api_drill.py`, each followed by full business-state
  readback. The failed cases remain red while independent probes continue;
  the overall drill exit must remain nonzero until repaired.
- Original private evidence: `/tmp/workstream-field-drill.l3LIo4/profile-nul.json`
  and `profile-nul-db.json`, with the separate reproduction source
  `probe_profile_nul.py`. Six HTTP cases: four successful controls/readbacks,
  two failures. Fresh local Flow verifier/Uvicorn/PostgreSQL; no product SQL
  writes or bypassed guards; isolated database/role cleanup completed. These
  temporary files are not shared evidence URLs; the inputs above suffice to
  reproduce the defect.

## API-DRILL-008: NUL project selector becomes 503

- Repair: the existing query constraint now excludes NUL without replacing
  primary-key lookup. `test_context_nul_rejected_preserving_id_lookup_and_concealment`
  covers rejection, valid selectors and concealed access for an ungranted actor.
- Route: `GET /api/v1/actors/me/authorization-context` with the URL-encoded query
  `project_id=before%00after`, authenticated through the normal canonical human
  identity path.
- Expected: bounded 422 `invalid_request` for a selector PostgreSQL cannot
  represent, not retryable service unavailability.
- Observed on clean `321cb0b64b86853442cc33f6a643a73873888a88`: 503
  `service_unavailable`. A normal absent-project UUID returned the expected
  concealed 404; subsequent profile readback preserved every business field.
- Cause: the public query validates length only. `ProjectService.find_project`
  passes the selector to a string primary-key lookup, where embedded NUL reaches the
  PostgreSQL text parameter before authorization can return its bounded result.
- Repair: validate storage-safe selector input at the canonical public boundary,
  preserve project-ID lookup and concealment, and add real HTTP/
  PostgreSQL regressions. Do not mask a database failure as a successful read or
  broaden project access.
- Permanent drill case: `context_selector_nul`, followed by a valid selector and
  full unchanged-project readback. Keep the 422 expectation and failed exit
  until the product is repaired.
- Private original evidence: `/tmp/workstream-field-drill.l3LIo4/context-nul.json`,
  `context-nul-db.json`, and `probe_context_nul.py`. Five HTTP cases: four passing
  controls and one failure. Fresh migrated database and normal verifier; no
  product-state seeding or disabled guards; database/role cleanup completed.

## API-DRILL-009: project and guide text NUL becomes 503

- Original reproduction on clean `60ab744792bc64327040f20fb14a72c26e9dd7c8`.
  This finding is separate from the repaired self-profile and context inputs.
- With a normally authenticated, system-scoped Project Manager and a fresh
  UUID `Idempotency-Key`, replace exactly one text field with JSON
  `"before\u0000after"` in an otherwise valid request:
  - `POST /api/v1/projects`: `name`, `slug`, or `description`.
  - `POST /api/v1/projects/{project_id}/guides`: `version`,
    `content_markdown`, or `change_summary`.
  - `PATCH /api/v1/projects/{project_id}/guides/{guide_id}` on a draft guide:
    `content_markdown` or `change_summary`.
- All eight cases returned 503 `service_unavailable`, rather than the expected
  non-retryable 422 `invalid_request`. PostgreSQL reported an invalid UTF-8
  byte sequence containing `0x00`. The request schemas accept the character and
  the mutation owners pass it to persistence.
- Controls: corrected requests using each failed request's original key all
  succeeded (201 for creation, 200 for update). Created projects were read back
  with their complete response fields. After each failed guide update, a
  fresh-key no-op PATCH returned the same public fields except `updated_at`,
  which that successful mutation may advance. These are public-state and key
  recovery checks, not proof that every internal table was unchanged.
- Repair boundary: `ProjectCreate`, `ProjectGuideCreate`, and
  `ProjectGuideUpdate` in `backend/app/modules/projects/schemas.py`, with
  HTTP/PostgreSQL regressions for all eight inputs. Preserve ordinary Unicode,
  existing length limits, optional nulls, omission semantics, authority and
  idempotency. Reject unsupported input; do not strip it or relabel a storage
  error as successful input validation after the write.
- Repair: all eight request fields exclude NUL using Pydantic field constraints,
  before the mutation handlers run. Existing limits, Unicode, nullable values
  and PATCH omission behavior remain intact. The parameterized
  `test_project_text_nul_rejected_without_state_and_same_key_recovers` checks
  422/non-retryability, unchanged selected project/guide and idempotency tables
  (including hidden guide generation), corrected same-key recovery and replay.
  No claim is made about every authority/audit table remaining unchanged.
- The product-builder's separate guide-contract changes must not be overwritten.
  On integration, preserve these constraints on surviving fields without
  restoring any removed guide fields.
- Private reproducer: `probe_project_guide_nul_v2.py` under
  `/tmp/workstream-field-drill.l3LIo4/`; corresponding
  `project-guide-nul-v2.json` and `project-guide-nul-v2-db.json` record 25 HTTP
  cases: 17 successful setup/control/readback calls and eight failures, with
  overall exit 1 and isolated database/role cleanup completed. Source hash and
  clean Git target are recorded. The initial probe stopped at the legitimate
  `self_grant_forbidden` guard; the corrected fixture uses distinct bootstrap
  administrator and Project Manager actors. No guard was bypassed.
- `project_guide_nul_cases` in the committed external drill preserves all eight
  422 expectations and their corrected same-key controls. It retains independent
  failures instead of changing expectations to match observed server errors.
  Temporary reproduction files are not shared evidence links.

## Retest and handoff criteria

### Genuine-guide capability evidence

A two-PDF real-provider drill reported archive encryption as an unsupported
automated check, although ART already rejects encrypted ZIP entries before
opening members. The existing mandatory catalogue entry
`artifact.archive.entries_safe` now names encrypted entries, symbolic links and
special files explicitly in its canonical `public_name`. This same hash-bound
metadata reaches guide compilation; no new checker or selectable policy is
introduced. Disabled mandatory capabilities still make the catalogue unavailable.
The owner regression proves encryption rejection separately from model behavior.
This is not proof that public submission intake is exposed.

The guide also requested project-specific expanded-archive size and member-count
limits. Subsequent runtime tracing corrected the initial interpretation: the
existing `maximum_package_size_bytes` rule already checks verified expanded bytes.
Its model-facing schema now states this explicitly. The missing member-count
rule is added as `maximum_archive_entries` through proposal projection, effective
minimum merging, locked summary, compiler and verified-manifest execution. ART
startup safety limits remain independent and unchanged. A fresh real-provider
replay is required before claiming model-level revalidation of these corrections.
A separate earlier real run
ended with `schema_invalid`; its original rejected output was not retained, so
the violated invariant is not established. Preserve that failed run and do not
claim a later valid blocked report explains or repairs it. Real-model semantic
reverification remains distinct from deterministic catalogue-contract tests.

Fresh real-provider replay at `8b79daf7` completed 33 HTTP checks with the same
two original PDFs. The valid blocked report identified only the requested
expanded-size and member-count limits as blocking gaps; encryption was no longer
reported unsupported. Both original-object hashes, exact upload replay and
deactivated-resolver denial passed, with isolated database and MinIO cleanup
confirmed. No validation rejection occurred, so this run verifies the metadata
repair but does not diagnose the earlier `schema_invalid` failure. The private
observer was calibrated to record validation types before SDK redaction without
retaining provider output or changing the rejection path.

Use the [new external-client drill](external-api-drill.md), not the older seeded
API drill. Keep unresolved failures red until product repairs actually satisfy
them; preserve the passing regressions for repaired defects. Run the applicable
full hosted tests and coverage for the repair; this
drill supplements those tests rather than replacing them.

After the repair merges, run against that exact main head with a fresh isolated
database, actual HTTP and verifier, and unchanged guards. Verify both successful
field behavior and failure-side-effect checks. Continue the remaining endpoint,
field, permission, pagination, policy and reachable lifecycle checks: fixing
these five items alone does not finish the all-field audit. Separate untested or
prerequisite-blocked operations from verified ones before the MCP handoff.
