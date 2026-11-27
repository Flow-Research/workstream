# Artifact Storage Operations

This runbook covers the hidden Operator surfaces for immutable artifact
storage. These surfaces diagnose Workstream records; they never expose provider
object references, endpoints, credentials, signed URLs, or raw provider
responses.

## Authorization and storage boundary

The routes under `/api/v1/operator/artifacts` require a current persisted
system-scoped human Operator grant. AUTH makes a fresh exact action/resource
decision and retains its audit evidence. JWT role metadata is not authority.
Reads, including configuration-only readiness, never authorize verification
retry. Retry has its own action and commits its decisions with the ART recovery
chain. Missing resources and denied authority share a concealed 404; an
unavailable decision/audit returns 503. These routes do not expose provider
objects or activate S3. WS-XINT-002-03 separately activates the fixed verifier,
pending-work scanner and put resolver through transaction-bound prepared
authority; it grants no Operator route by itself.

AWS S3 uses a dedicated restricted credential. See the
[S3 credential runbook](operations_aws_s3_credentials.md) for setup, permissions,
qualification and rotation. Storage access does not depend on an expiring
PostgreSQL proof or a periodic privileged inspection job. Workstream still
checks product authorization and exact namespace ownership, and verifies file
hashes and byte counts before accepting provider results.

## Backup and restore boundary

Database and S3 backup execution remains environment-owned. Preserve retained
object bytes, the exact private namespace and immutable product custody rows
together. Do not rebind a content record, replica, receipt or audit fact to
another bucket, prefix or artifact. After restore, verify the configured
credential and real storage reads before admitting new work. A database restore
does not itself prove that the corresponding S3 bytes remain available.

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
`configured_limit_bytes` is `null` when the serving deployment has not
configured that scope; the persisted `limit_bytes` remains an observed row,
not permission to admit more bytes or a claim of provider readiness.

Each bounded scope also reports submission-bundle pressure as
`unbound_ready_count`/`unbound_ready_bytes` and
`stale_count`/`stale_bytes`. Ready admissions are verified but not yet consumed
by a Submission; stale admissions proved incompatible at a later consumption
boundary. Both remain charged under v0.1 capacity limits. Use these projections
to distinguish abandoned or context-invalid bundles from ordinary artifact
growth; there is no operator deletion or release action.

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

The v0.1 baseline installs immutable ready-admission custody. Recovery planning
must preserve those facts and move forward with a corrective migration rather
than deleting or bypassing them; the baseline cannot be downgraded.

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

## Contributor-intake baseline invariant

The v0.1 baseline contains only the current contributor-intake schema. The
retired upload-session/item shape and version-1 receipt contract are not an
upgrade source. Recreate pre-v0.1 development databases; for production data,
use a separately reviewed evidence-preserving maintenance migration rather
than deleting, detaching, rewriting, or restamping rows.

## Submission source reclamation

Terminal submission sources use the dedicated
`workstream.artifacts.sweep_submission_sources` task. Configure
`WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE` as a JSON object with explicit
`maximum_candidates` (1–1000), `run_seconds` (1–300), and `lease_seconds`
(1–300, no greater than `run_seconds`). These are validation bounds, not
recommended deployment values. Size the page and execution envelope from
measured provider latency and terminal-source arrival rates. An absent profile
disables the Beat entry; it does not constitute a deployed cleanup service.

Supply the profile to Beat and the dedicated Celery process. Run that process with only
its cleanup queue and the prefork pool:

```bash
celery -A app.workers.celery_app:celery_app worker --pool=prefork -Q workstream.source_cleanup
```

Other Celery processes must select their own queues explicitly. Mixed queues,
eager execution, and other pools are rejected for cleanup. The task execution
boundary also rejects foreign registered task names delivered to this process.
Startup checks the
persisted namespace, current cleanup-service authority and provider configuration
before forking. Each sweep repeats current authority checks. The task has a
fixed 360-second process hard limit; broker messages cannot extend it.

Beat schedules a bounded sweep every 12 hours. Its recovery pass first fences
expired receiving/PRE operations, rechecking each under its task lock and current
service authority. This clears only the old operation's task pointer; it neither
resumes PRE nor releases storage charges. Live and accepted operations remain
protected. Recovery uses the sweep's explicit page/run limits and bounds each
attempt by the configured lease interval. Foreground recovery can use at most
half the run envelope, preserving time for unrelated source cleanup even when a
task lock is held. This is periodic foreground recovery,
not the prompt runtime-session reaper. Sources must have been terminal for at
least two hours; a newly observed completed version starts a fresh two-hour
protection period. Candidate discovery grants no deletion
permission: the existing owner locks task/source custody, rejects accepted or
retained sources, and commits an audited exact-generation claim before provider
I/O. Only confirmed object absence and settled upload obligations release the
charge. A failed or interrupted attempt retains its charge; a later sweep can
claim a new generation after the old lease expires. Repeated sweeps do not
release the same charge again.

For S3-compatible storage, supply separate cleanup credentials to this Celery process
through its storage settings and put the upload principal identity in the
profile's `upload_principal`. The provider factory rejects the upload principal
as the cleanup principal. Use the IAM user ARN for native AWS dedicated
credentials, or the access-key identity for MinIO. Native AWS workload identity
without an explicit comparable principal is not admitted for cleanup. Do not give these deletion credentials to API or
ordinary Celery processes. The source path uses the same dedicated static
credentials as other artifact operations; it does not restore the retired
expiring provider-proof system. Native AWS source permissions and exact-version
cleanup still require deployment qualification. MinIO tests alone do not
establish that evidence.

The sweep covers sealed sources, Local unfinished uploads and recorded MinIO
multipart handles. Local cleanup retains an abort tombstone to reject late
initiation. Remote cleanup requires parts absence after abort, fresh handle
discovery and no remaining versions or delete markers. A completion discovered
before or during abort becomes a retained exact-version target; it requires a
fresh aged cleanup claim before deletion. An abort acknowledgment alone does not
release storage charges. The S3 data-plane SDK makes one total attempt per call;
durable owners control observation and retries.

For remote initiation whose response was lost, discovered multipart IDs are
saved on the existing cleanup claim before abort. A fresh authorization binds
that retained set; newly discovered IDs invalidate the previous authorization.
Retries check every retained handle even when discovery no longer lists it.
Empty discovery cannot prove that an uncertain initiation never happened, so
that case remains charged. Inventory of objects whose operation record is
genuinely absent is an optional future enhancement under submission spec §17.4;
this sweep does not discover or delete those objects. Reconciliation of uncertain
writes belonging to known operations remains required.
Do not treat this schedule as proof that every abandoned byte is reclaimed.
