# Artifact Storage Operations

This runbook covers the hidden Operator surfaces for immutable artifact
storage. These surfaces diagnose Workstream records; they never expose provider
object references, endpoints, credentials, signed URLs, or raw provider
responses.

## Activation boundary

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

AWS S3 is activation-gated. Configuration supplies only non-secret exact
release, namespace, role/policy, reviewed trust-policy digest and bucket-policy
bindings; Roles Anywhere also binds the exact anchor/profile ARNs and canonical
state digests. Configuration cannot assert a pass. API, Celery task-process and
Beat startup load an exact fresh activation after the
namespace claim and before credential inspection. Every AWS SDK call reloads
the same activation selected for its logical operation, and ART reloads that ID
inside any provider-derived terminal transaction.

The deployment runs one fixed command separately under each configured proof
identity, using one newly generated non-secret UUID nonce. Run runtime proof
first so its retained challenge object exists, followed by readiness and
negative-access proof, then run credential-free coordination:

```bash
python -m scripts.aws_artifact_provider_proof runtime_immutability --group-nonce <uuid>
python -m scripts.aws_artifact_provider_proof readiness --group-nonce <uuid>
python -m scripts.aws_artifact_provider_proof negative_access --group-nonce <uuid>
python -m scripts.aws_artifact_provider_proof coordinate --group-nonce <uuid>
```

The coordinator and activation-table trigger both require the runtime result's
completion time to be no later than the readiness and negative result start
times. An out-of-order group cannot activate even when all three rows otherwise
match and report pass. This ensures the later denial calls target the object
that runtime proof actually retained, rather than relying on a missing-key 403.

Each proof process first binds its STS-observed caller to its configured role,
performs only that mode's fixed calls, and writes one append-only bounded result
using PostgreSQL time. Coordination has database access and no AWS transport;
it accepts exactly one passing result of every type in the common group. Run
the sequence every five minutes. Results and activations expire 15 minutes from
their individual starts, so overlapping unexpired groups are expected. The
deployment must complete runtime proof, readiness proof, negative-access proof
and coordination within the fixed 120-second proof-sequence allowance. Native
AWS settings reserve that allowance when validating operation deadlines and
assume successive runtime probes start within 300 seconds. The coordinator and
activation-table trigger reject insertion when PostgreSQL time minus
`runtime.started_at` exceeds the allowance. At the maximum permitted budgets,
equality leaves no scheduling or commit-latency slack: start earlier or configure
smaller operation deadlines to provide margin. Measure start-to-start cadence,
full-sequence duration and commit latency during the live drill. These bounds do
not guarantee continuous eligibility; a late or missed group fails closed.

The command accepts no pass value or caller-authored observation, and product,
API and configuration inputs cannot create these records. The deployed proof
process, its database writer credential and database administrators are the
v0.1 trust root for proof and activation rows. Protect that credential as
deployment authority. v0.1 does not claim resistance to a malicious holder of
it; a separate database role or external attestation would be a new security
design, not evidence supplied by this command.

Every new nonce intentionally leaves one immutable 49-byte challenge in the
production content-addressed namespace. At a five-minute cadence this is
105,120 objects and 5,150,880 payload bytes per 365-day year, before provider
metadata and request charges. They create no product binding or receipt, but
exercise the exact production resource policy and no-expiry lifecycle; capacity
monitoring must include them, and orphan cleanup must not delete them.

Each independently deployed executor supplies its own selected workload-identity
method and identity environment; the common settings contract does not imply
that the runtime, readiness and negative jobs share one credential method.
The exact three trust-policy digests are shared non-secret configuration. The
readiness run compares them with `GetRole`, rejects shared workload subjects,
and rejects any trust grant that lets one configured workload role assume
another.

For certificate-based external hosting, follow the
[Roles Anywhere setup guide](operations_aws_roles_anywhere.md). It supplies the
provisioning and generated configuration flow, private leaf-certificate mounts,
renewal/revocation steps and separate proof-job instructions. The CA signing key
stays under administrator-only custody outside all application mounts, including
when signing and application execution share a server. Application processes
receive only the runtime leaf identity.

Readiness and negative roles accept either a closed exact OIDC trust or the
closed Roles Anywhere certificate trust. Runtime also supports the EC2
instance-profile shape for independently selected AWS hosting. OIDC trust fixes
issuer, subject and audience. Roles Anywhere trust fixes source account,
trust-anchor ARN, issuer CN and the role-specific subject CN. Its shared profile
contains exactly the three roles. Each certificate proves own-role success,
explicit denial for both other roles, then own-role success again; a network,
certificate, timeout or malformed helper failure is not an access-denial proof.
No broad trust, role chaining or ambient credential fallback is supported.

PostgreSQL retains the three distinct role ARNs and trust-policy digests. For
Roles Anywhere it additionally binds anchor/profile ARNs and canonical state
digests on every probe and activation, including runtime and terminal checks.
The readiness executor compares those values to the actual enabled AWS resources
and CA material. Changed bindings require a fresh matching group. Retained
historical evidence is preserved; it does not activate the current proof
contract. Database custody does not replace ongoing external proof.

Do not supply bootstrap credentials or run all modes under one identity. The
readiness identity may inspect only the exact three role attachments/inline
policies and the exact two required managed-policy documents. A failed,
expired, mixed or drifted group cannot activate AWS. An expired activation
during a possibly successful write leaves recoverable acknowledgement-unknown
state; rerun proof and let the existing resolver observe the object.

## Safe activation evidence inspection

Inspect only bounded custody metadata. Filter by the known release, group nonce,
or activation ID and select record IDs, proof type/result, error code, configured
digests, and PostgreSQL timestamps. Do not dump raw provider responses, process
environments, SDK configuration, credential sources, or an unbounded table.
For example, an operator with the existing read-only database path can inspect
one group without changing its evidence:

```sql
SELECT id, probe_type, result, error_code, evidence_sha256,
       started_at, completed_at, expires_at
FROM artifact_provider_probe_results
WHERE group_nonce = '<known-uuid>'
ORDER BY probe_type
LIMIT 3;

SELECT id, group_nonce, supersedes_activation_id, activated_at, expires_at
FROM artifact_provider_activations
WHERE release_id = 'sha256:<known-release-digest>'
ORDER BY activated_at DESC, id DESC
LIMIT 20;
```

The rows are append-only evidence. Never update, delete, truncate, restamp, or
copy them to manufacture freshness. An expired or failed row is diagnostic and
cannot authorize provider I/O.

## Backup and restore boundary

Database and S3 backup execution remains environment-owned. A restore must
preserve retained object bytes, the exact private namespace, and all immutable
Workstream custody rows together. It must not rebind an object, activation,
probe result, content record, replica, receipt, or audit fact to a different
release, bucket, prefix, role, policy, or trust-policy digest. Restored
activations remain governed by their original PostgreSQL timestamps and will
normally be expired; run a fresh three-identity proof group before allowing AWS
provider I/O. There is no Workstream restore-by-rebinding or retained-data
deletion path in v0.1. Environment backup/restore drill evidence is still a
hosted release prerequisite and is not supplied by this offline activation
change.

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

Sealed, terminal submission sources use the dedicated
`workstream.artifacts.sweep_submission_sources` task. Configure
`WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE` as a JSON object with explicit
`maximum_candidates` (1–1000), `run_seconds` (1–300), and `lease_seconds`
(1–300, no greater than `run_seconds`). These are validation bounds, not
recommended deployment values. Size the page and execution envelope from
measured provider latency and terminal-source arrival rates. An absent profile
disables the Beat entry; it does not constitute a deployed cleanup service.

Supply the profile to Beat and the dedicated worker. Run the worker with only
its cleanup queue and the prefork pool:

```bash
celery -A app.workers.celery_app:celery_app worker --pool=prefork -Q workstream.source_cleanup
```

Other worker processes must select their own queues explicitly. Mixed queues,
eager execution, and other pools are rejected for cleanup. The task execution
boundary also rejects foreign registered task names delivered to this worker.
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
half the run envelope, preserving time for unrelated sealed cleanup even when a
task lock is held. This is periodic foreground recovery,
not the prompt runtime-session reaper. Sources must have been both sealed
and terminal for at least two hours. Candidate discovery grants no deletion
permission: the existing owner locks task/source custody, rejects accepted or
retained sources, and commits an audited exact-generation claim before provider
I/O. Only confirmed object absence and settled upload obligations release the
charge. A failed or interrupted attempt retains its charge; a later sweep can
claim a new generation after the old lease expires. Repeated sweeps do not
release the same charge again.

For S3-compatible storage, supply separate cleanup credentials to this worker
through its storage settings and put the upload access-key identity in the
profile's `upload_principal`. The provider factory rejects the upload principal
as the cleanup principal. Do not give these deletion credentials to API or
ordinary workers. Native AWS source cleanup remains unavailable until its
separate source-capability qualification is implemented and passed; existing
SHA-object activation and MinIO tests do not qualify it.

This worker currently covers sealed terminal sources. Unsealed uploads,
uncertain begin/completion results and genuine orphan reconciliation remain
unfinished requirements of the submission execution specification. Do not treat
this schedule as proof that every abandoned byte is reclaimed.
