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

AWS S3 is activation-gated. Configuration supplies only non-secret exact
release, namespace, role/policy, reviewed trust-policy digest and bucket-policy
bindings; it cannot assert a pass. API, Celery task-process and Beat startup load
an exact fresh activation after the
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
their individual starts, so overlapping unexpired groups are expected.

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

The readiness and negative roles each accept exactly one closed trust shape:
one `Allow` statement with one IAM OIDC provider, the exact
`sts:AssumeRoleWithWebIdentity` action, and `StringEquals` claims containing
only that provider issuer's exact `sub` plus audience `sts.amazonaws.com`.
The runtime role may use the same shape, or the Linux VM shape consisting of
one condition-free `Allow` for service principal `ec2.amazonaws.com` and action
`sts:AssumeRole`. In the VM shape, the trusted environment provisioner owns the
instance-profile attachment; untrusted runtime workloads cannot select or
attach another role. Wildcard subjects, negative or pattern operators,
missing or foreign audience claims, AWS principals, role chaining, ECS or
other service principals, additional statements and additional condition keys
fail activation. A deployment using a different trust shape must change its
infrastructure to one of these reviewed shapes or land a separately reviewed
proof extension; the configured digest alone does not make unsupported IAM
semantics safe.

PostgreSQL stores the three pairwise-distinct role ARNs and reviewed trust
digests and rejects a probe or activation tuple that collapses them. The live
readiness executor proves the corresponding trust documents and disjoint exact
OIDC subjects. The database binds those observed digests; it does not
independently attest external IAM truth after the observation.

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
