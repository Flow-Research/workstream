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
persist. API-DRILL-007 below is a separate newly reproduced repair item.

Human-confirmed v0.1 project roles are **submitter** and **reviewer**.
Adjudication is deferred. Do not implement adjudicator functionality, widen an
audit allowlist to support it, or introduce a compatibility path to make the
old advertised role pass.

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

## Retest and handoff criteria

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
