# WS-ARCH-001-02D ART Preparation Resource Manifest

## Public entry capability

`app.modules.artifacts.api.SubmissionBundlePreparationCommand.prepare` accepts
one `SubmissionBundlePreparationRequest` and returns one
`SubmissionBundlePreparationResult`.

The request carries only:

- dependency-safe `ActorIdentityFacts`;
- request and correlation identifiers;
- task, assignment, predecessor, and idempotency identifiers;
- bounded packet text and media type;
- the request-local asynchronous byte source.

It carries no authorization context, prepared handle, database session, ORM
row, provider coordinate, scratch path, inspection result, custody value, or
durable pass capability. The route remains hidden from OpenAPI and the
production contributor authority remains deny-only.

## Owner ports consumed by ART

| Owner | Public capability | Facts used by ART |
|---|---|---|
| TASK | `TaskSubmissionContextPort.lock_submission_context` | Exact task, assignment, contributor, lifecycle kind/status, predecessor version, and task-stamped project-policy references |
| PROJECT | `ProjectLockedPolicyContextPort.lock_locked_policy_context` | Exact guide/source lineage, effective artifact policy, compiled pre-submit policy, statuses, and canonical policy JSON |
| CHECKER | `EffectivePreSubmissionPlanningPort.compile_effective_plan` | Immutable effective plan and plan identity |
| CHECKER | `PreSubmissionExecutionFacts` | Bounded ordered result facts only; ART retains its own byte and scratch custody |
| AUTH | `ActorIdentityFacts` plus ART-private opaque authorization port | Active actor and identity-link references; process-local prepared handles remain opaque `object` values and are never serialized |

## Lock and authority order

1. Contributor preflight occurs before the runtime opens or request bytes are
   read.
2. TASK and then PROJECT facts are locked through their public ports, and the
   CHECKER plan is compiled from those exact facts.
3. ART prepares and inspects bytes in bounded scratch.
4. Fixed-service materialization authority is consumed before workspace byte
   access or checker execution.
5. After execution and scratch cleanup, contributor authority is revalidated,
   then TASK and PROJECT facts are locked again in the evidence transaction.
6. Evidence persists only if assignment, predecessor, guide, policy, plan,
   byte, manifest, and result facts remain exact.
7. Fresh final contributor authority is prepared and consumed in the durable
   put-intent transaction before capacity reservation, put-attempt creation,
   or provider I/O.

## Private custody retained by ART

These values are deliberately not public contracts:

- `PreparedBundleMaterializationRequest`;
- prepared artifact and generation binding;
- archive inspection and semantic manifest;
- scratch workspace and reader;
- `PreSubmitExecutionCustody`;
- `PreSubmitPassCapability`;
- durable put and ready-admission internals.

## Composition

Delivery code lives in `app.api.routes.artifact_submissions`. Owner adapter
packages bind TASK, PROJECT, CHECKER, and ART implementations to public ports.
The boundary gate permits an owner adapter to import only its own module's
private implementation; cross-owner private imports remain ledgered debt and
new debt remains prohibited against the protected base.

## Denial guarantees

Unavailable authority, changed TASK/PROJECT lineage, mismatched plans or
results, copied/replayed/wrong opaque handles, and invalid media types fail
without publishing a successful preparation. Authority handles do not enter
request schemas, Celery payloads, provider contracts, logs, or persistence.
