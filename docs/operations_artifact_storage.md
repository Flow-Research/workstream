# Artifact Storage Operations

This runbook covers the hidden Operator surfaces for immutable artifact
storage. These surfaces diagnose Workstream records; they never expose provider
object references, endpoints, credentials, signed URLs, or raw provider
responses.

## Activation boundary

The routes are composed under `/api/v1/operator/artifacts`, but production
authority remains deny-only while the corresponding Authorization Service
Operator actions are planned. WS-XINT-002-03 activates only the fixed verifier,
pending-work scanner, and put resolver through transaction-bound prepared
authority. It grants no Operator route. Do not add role checks, fallback
constructors, or artifact-owned grant evaluation.

AWS S3 readiness is configuration-only and remains
`inactive_live_proof_required`. This check does not instantiate an adapter or
call AWS. Chunk 07 owns live bucket-policy, principal-boundary, credential,
anonymous-read-negative, lifecycle, and activation proof.

## Diagnosis sequence

1. Start from the exact project, project guide, snapshot, snapshot item, task,
   submission, or checker run and list its artifact bindings. Review lookup is
   deferred until the review lifecycle owns a canonical review record.
2. Follow the stable `content_id` to replicas. Replica responses contain only
   Workstream identity and verification, availability, and integrity states.
3. Follow a `replica_id` to redacted put receipts and its verification job.
4. Read exact audit events for the selected artifact resource.
5. If a verification job exhausted all attempts with terminal
   `provider_unavailable`, submit a reason-bound retry with a client
   idempotency key and expected source-job CAS version.
6. Follow the returned recovery-attempt ID to the immutable source/retry chain,
   current statuses, terminal mapping, and audit IDs.

Unauthorized, cross-project, and missing resources return the same concealed
not-found response. A retry revalidates actor state, identity link, exact
authority, source lineage, terminal eligibility, and CAS inside its creation
transaction. Never infer success from a database row alone; use the Operator
HTTP response and audit identifiers.

## Admission pressure

`GET /api/v1/operator/artifacts/admission-usage` requires an exact canonical
`project_id` and reports bounded deployment, project, and optional task usage.
It never enumerates producer-scope identifiers. It is read-only: it cannot
release charges, change configuration, or create recovery work.

Every successful admission transaction emits
`workstream_artifact_admission_pressure_total`
for each derived deployment, project, producer, and task scope. The bounded
structured-log metric contains only
`scope_type` (`deployment`, `project`, `producer`, or `task`) and
`pressure_band` (`normal`, `warning`, `critical`, or `exhausted`). Configure
the deployment log collector to aggregate this counter and alert for:

- warning at 75 percent;
- critical at 90 percent;
- exhausted at 100 percent.

Treat a critical or exhausted scope as an incident. Identify whether growth is
expected, confirm that its parent scopes have capacity, and compare the
configured limit with the persisted scope limit. Do not delete admission
charges or edit counters in PostgreSQL.

## Quota expansion and rollback

Quota changes are configuration-driven. Increase the smallest affected scope
and deploy the validated configuration. The next admission transaction locks
the affected counters and reconciles their persisted limits with configuration
using CAS fencing before reserving bytes. Confirm the read-only admission view
reports matching configured and persisted limits. Keep task, producer, project,
and deployment limits mutually consistent.

If the change is wrong, restore the previous configuration and redeploy. The
same locked reconciliation permits a decrease only when it is not below
already-counted bytes. Otherwise admission fails closed: stop new artifact
writes, retain the higher safe limit, and resolve the incident without deleting
charges or directly editing database state.

## Prohibited operations

These routes do not delete, retain, release, or mutate provider objects; change
admission configuration; activate AWS; or cut over any guide, task, submission,
checker, review, contribution, payment, or reputation lifecycle.

## Legacy contributor-intake migration

Migration `0051_legacy_intake_removal` is a safe-empty cut. Before deploying,
confirm that the legacy upload-session/item tables contain no rows and that no
put attempt or operation receipt carries contributor/upload-item lineage or a
version-1 receipt contract. The migration takes exclusive locks and refuses
before changing schema when any such evidence exists.

Do not delete, detach, or rewrite those rows to force deployment. Preserve the
database at revision `0050_guide_source_v2` and escalate for a separately
approved maintenance and audit migration. A refusal is an expected evidence-
preservation outcome, not permission to bypass the preflight.
