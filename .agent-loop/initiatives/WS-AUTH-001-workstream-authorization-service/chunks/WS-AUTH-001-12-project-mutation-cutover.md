# Chunk Contract: WS-AUTH-001-12 — Project Mutation Cutover Planning Parent

## Status

Planning-only parent. Required L1 review rejected the inherited combined
runtime contract before application-code edits. Runtime work is split into
12A through 12H plus 12B2 and 12D2, and each child requires its own reviewed
start.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Freeze the exact project-mutation catalogue, resource and transaction
boundaries, provenance ownership, fixed-service boundary, and ordered runtime
children needed to remove issuer-claim authorization from project mutations.

## Why this chunk exists

The inherited contract combined route and setup-service actions, PREP extension,
service provisioning, provenance schema, external-agent transaction breaks,
and guide activation. Splitting prevents a partial cutover or generic policy
resource from becoming authority.

## Risk class

L1

## SLA

P1

## Exact mutation inventory

| Surface / handler | ActionId | PermissionId | ActionOwner | Principal | Child |
|---|---|---|---|---|---|
| `POST /api/v1/projects` / `create_project` | `project.create` | `project.create` | `WS-AUTH-001-12C` | system-scoped Project Manager | 12C |
| `POST /api/v1/projects/{project_id}/guides` / `create_guide` | `project.guide.create` | `project.guide.manage` | `WS-AUTH-001-12D` | covered Project Manager | 12D |
| `PATCH /api/v1/projects/{project_id}/guides/{guide_id}` / `update_guide` | `project.guide.update` | `project.guide.manage` | `WS-AUTH-001-12D` | covered Project Manager | 12D |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots` / `create_guide_source_snapshot` | `project.guide_source_snapshot.create` | `project.guide.manage` | `WS-AUTH-001-12D` | covered Project Manager | 12D |
| new `PUT /api/v1/projects/{project_id}/guides/{guide_id}/review-policy` | `project.review_policy.update` | `project.review_policy.manage` | `WS-AUTH-001-12D2` | covered Project Manager | 12D2 |
| new `PUT /api/v1/projects/{project_id}/guides/{guide_id}/revision-policy` | `project.revision_policy.update` | `project.review_policy.manage` | `WS-AUTH-001-12D2` | covered Project Manager | 12D2 |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports` / `create_guide_sufficiency_report` | `project.guide_sufficiency_report.create` | `project.guide.manage` | `WS-AUTH-001-12E` | covered Project Manager | 12E |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots/{source_snapshot_id}/run-sufficiency-agent` / `run_guide_sufficiency_agent` | `project.guide_sufficiency.run` | `project.guide.manage` | `WS-AUTH-001-12E` | covered Project Manager over HTTP; `workstream.project.setup` only through internal command resolution | 12E |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}/acknowledge-warnings` / `acknowledge_guide_sufficiency_warnings` | `project.guide_sufficiency.warnings.acknowledge` | `project.guide.manage` | `WS-AUTH-001-12E` | covered Project Manager | 12E |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies` / `create_submission_artifact_policy` | `project.submission_artifact_policy.create` | `project.effective_policy.manage` | `WS-AUTH-001-12F` | covered Project Manager | 12F |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots/{source_snapshot_id}/derive-submission-artifact-policy` / `run_submission_artifact_policy_derivation_agent` | `project.submission_artifact_policy.derive` | `project.effective_policy.manage` | `WS-AUTH-001-12F` | covered Project Manager over HTTP; `workstream.project.setup` only through internal command resolution | 12F |
| `PATCH /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}` / `update_submission_artifact_policy` | `project.submission_artifact_policy.update` | `project.effective_policy.manage` | `WS-AUTH-001-12F` | covered Project Manager | 12F |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}/approve` / `approve_submission_artifact_policy` | `project.submission_artifact_policy.approve` | `project.effective_policy.manage` | `WS-AUTH-001-12F` | covered Project Manager | 12F |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/approve` / `approve_current_post_submit_checker_policy` | `project.post_submit_checker_policy.approve` | `project.effective_policy.manage` | `WS-AUTH-001-12G` | covered Project Manager | 12G |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/request-correction` / `request_post_submit_checker_policy_correction` | `project.post_submit_checker_policy.correction.request` | `project.effective_policy.manage` | `WS-AUTH-001-12G` | covered Project Manager | 12G |
| internal `run_post_submit_checker_policy_derivation_agent` | `project.post_submit_checker_policy.derive` | `project.effective_policy.manage` | `WS-AUTH-001-12G` | `workstream.project.setup` | 12G |
| setup-run ledger mutations used by both Celery entry points | `project.setup_run.update` | `project.guide.manage` | `WS-AUTH-001-12B2` | `workstream.project.setup` | 12B2 |
| `POST /api/v1/projects/{project_id}/guides/{guide_id}/activate` / `activate_guide` | `project.guide.activate` | `project.guide.manage` | `WS-AUTH-001-12H` | covered Project Manager | 12H |

The hidden ART ingest route and `artifact.guide_source.ingest` are already
active under `WS-XINT-002-04A` and are frozen outside AUTH-12. ART binding/read,
provider access, extraction, and later ART activation remain outside AUTH-12.

## Child order

1. 12A registers all eighteen actions as planned, adds exact typed resource
   contracts, and adds PostgreSQL action-evidence parity after ART-owned
   migration `0040` merges. It activates nothing.
2. 12B establishes the fixed project-setup identity and four planned matrix
   memberships without activating the Celery path.
3. 12C cuts over project-shell creation.
4. 12D cuts over draft guide and source-snapshot metadata mutations.
5. 12D2 adds separate review and revision policy routes. Retired guide-bound
   economic policy remains removed and CON-owned; AUTH-12 creates no replacement.
6. 12E cuts over guide-sufficiency mutations.
7. 12F cuts over submission-artifact policy mutations and their provenance.
8. 12G cuts over post-submit checker-policy derivation/approval/correction without
   changing checker execution, visibility, or `WS-POL-002-03` behavior.
9. 12B2 activates setup-run ledger authority and cuts both Celery entry points
   only after 12E/12F/12G have activated the exact product actions they call.
10. 12H cuts over guide activation after every prerequisite family is local.

Agent-backed commands may perform an authorization preflight before external
work, but no prepared handle may cross a rollback, commit, agent call, Celery
message, serialization boundary, or session. Final persistence uses a fresh
root transaction: prepare authority, lock canonical rows, recompose final
facts, consume once, flush product/evidence/idempotency state, and commit once.

Every `workstream.project.setup` product action additionally binds the locked
active setup run, expected setup step, task/correlation identity, project,
guide, source snapshot, setup generation, and stale-output digest. Its evidence
records the service profile, identity link, and closed static-matrix membership
as `grant-or-service`; it must never fabricate a human project grant. Missing,
wrong, revoked, replaced, or stale setup custody denies before product effects.

Every HTTP mutation requires a UUID `Idempotency-Key`. Its canonical digest
binds the exact action, route parameters, validated request body, actor/link,
and server-owned operation generation. Exact replay returns the recorded
result; mismatched reuse fails with the canonical idempotency conflict and no
product effect. Project-resource denial, missing lineage, and cross-project
scope use the same concealed 404 envelope. Project creation has no existing
resource to conceal and uses the canonical 403 authorization denial. Denied
authorization commits bounded denial evidence but no product state; failed
participants roll back and restage that exact denial evidence.

## Allowed files

Planning/review artifacts under this initiative plus
`scripts/check_stale_authorization_docs.py` solely for the exact technical-path
exemption used by 12B2. No scanner rule or other exception may change.

## Not allowed changes

Application code, migrations, action availability, runtime service identity,
routes, schemas, project lifecycle state, ART behavior, or CI configuration.

## Acceptance criteria

- Every current project mutation route and setup-service command appears once
  in the inventory or is explicitly excluded.
- Each child is independently reviewable and names exact PREP, scope,
  provenance, denial, transaction, and proof requirements.
- Guide create/update cannot silently authorize review, revision, retired economic, or
  contribution policy changes; 12D removes those embedded fields and 12D2
  supplies only separate review/revision routes before guide activation.
- No child treats token roles, combined contributor roles, uploader authority,
  or a generic policy resource as authority.
- Migration custody acknowledges ART-03B2's active `0040` work and allocates
  only from the trusted merged head.
- Fixed setup-service execution is not generic project authority: exact active
  run/step/task lineage and service provenance are required and directly
  invocable or cross-lineage requests fail closed.

## Verification commands

```bash
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact action names and permissions, human/service separation, child ordering,
guide create/update policy separation and CON economic-policy ownership,
ART boundary, and transaction-local PREP.

## Stop conditions

Stop if an action cannot be tied to one canonical resource family, a prepared
handle would cross a transaction/external-work boundary, fixed service work
requires human authority, or a child must alter ART/REV/CON behavior.

Later mutation children must extend or extract the canonical project lineage
composition already used by `projects/authorization_reads.py`; they may not
duplicate guide/source/policy chain hashing and lock logic route by route.
