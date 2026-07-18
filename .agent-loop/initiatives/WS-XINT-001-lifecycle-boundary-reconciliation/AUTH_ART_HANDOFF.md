# AUTH <-> ART Handoff

## Boundary

AUTH is the sole activation custodian. ART is the sole artifact resource and
behavior owner. AUTH never performs artifact storage/lifecycle mutations; ART
never registers grants, evaluates authority locally, or changes action
availability.

## Complete current custody transfer

All mappings remain unchanged. `docs/spec_authorization_service.md` remains the
canonical ActionId-to-PermissionId and principal/resource blueprint. The table
below repeats those mappings only to bind each row to its proposed AUTH custody
group; this handoff is the canonical activation-custody transfer. The proposed
groups replace the current ART-valued `ActionOwner` rows atomically.

| AUTH custody group | ActionId | PermissionId |
|---|---|---|
| `AUTH_ART_02D_OPERATOR` | `artifact.binding.read` | `artifact.binding.read` |
| `AUTH_ART_02D_OPERATOR` | `artifact.replica.read` | `artifact.replica.read` |
| `AUTH_ART_02D_OPERATOR` | `artifact.receipt.read` | `artifact.receipt.read` |
| `AUTH_ART_02D_OPERATOR` | `artifact.verification_job.read` | `artifact.verification_job.read` |
| `AUTH_ART_02D_OPERATOR` | `artifact.verification_job.retry` | `artifact.verification_job.retry` |
| `AUTH_ART_02D_OPERATOR` | `artifact.recovery_attempt.read` | `artifact.recovery_attempt.read` |
| `AUTH_ART_02D_OPERATOR` | `artifact.audit.read` | `artifact.audit.read` |
| `AUTH_ART_02D_OPERATOR` | `operations.artifact_storage_admission.read` | `operations.status.read` |
| `AUTH_ART_02D_INTERNAL` | `artifact.verification.execute` | `artifact.verification.execute` |
| `AUTH_ART_02D_INTERNAL` | `artifact.pending_work.scan` | `artifact.pending_work.scan` |
| `AUTH_ART_02D_INTERNAL` | `artifact.put_attempt.resolve` | `artifact.put_attempt.resolve` |
| `AUTH_ART_03` | `artifact.guide_source.ingest` | `artifact.guide_source.ingest` |
| `AUTH_ART_03` | `artifact.guide_source.read` | `artifact.guide_source.read` |
| `AUTH_ART_03` | `artifact.guide_source.binding.create` | `artifact.binding.create` |
| `AUTH_ART_04A` | `artifact.upload_session.create` | `artifact.upload_session.create` |
| `AUTH_ART_04A` | `artifact.upload_session.read` | `artifact.upload_session.read` |
| `AUTH_ART_04A` | `artifact.upload_item.write` | `artifact.upload_item.write` |
| `AUTH_ART_04A` | `artifact.upload_session.seal` | `artifact.upload_session.seal` |
| `AUTH_ART_04A` | `artifact.upload_session.cancel` | `artifact.upload_session.cancel` |
| `AUTH_ART_04A` | `artifact.upload_session.expire` | `artifact.upload_session.expire` |
| `AUTH_ART_04B` | `artifact.pre_submit.checker_input.materialize` | `artifact.checker_input.materialize` |
| `AUTH_ART_05` | `artifact.submission.binding.create` | `artifact.binding.create` |
| `AUTH_ART_06A` | `artifact.post_submit.checker_input.materialize` | `artifact.checker_input.materialize` |
| `AUTH_ART_06B` | `artifact.checker_output.write` | `artifact.checker_output.write` |
| `AUTH_ART_06B` | `artifact.checker_output.binding.create` | `artifact.binding.create` |

After transfer, AUTH removes unused `ART_02D`, `ART_03`, `ART_04A`, `ART_04B`,
`ART_05`, `ART_06A`, and `ART_06B` owner enum values. Closed typed, SQL, audit,
and definition-owner parity must reject partial transfer, dual writers, missing
owners, extra owners, and changed mappings.

## Fixed service-action matrix

`docs/spec_authorization_service.md` remains the canonical fixed service-action
matrix source. This table is a non-authoritative repeat used only to bind the
existing matrix to the activation-custody sequence.

| Service identity | Exact static matrix actions |
|---|---|
| `workstream.artifact.verifier` | `artifact.verification.execute` |
| `workstream.artifact.put_resolver` | `artifact.put_attempt.resolve` |
| `workstream.artifact.scheduler` | `artifact.pending_work.scan`, `artifact.upload_session.expire` |
| `workstream.artifact.binding` | `artifact.guide_source.binding.create`, `artifact.submission.binding.create`, `artifact.checker_output.binding.create` |
| `workstream.artifact.guide_reader` | `artifact.guide_source.read` |
| `workstream.artifact.materializer` | `artifact.pre_submit.checker_input.materialize`, `artifact.post_submit.checker_input.materialize` |
| `workstream.artifact.checker_output` | `artifact.checker_output.write` |

AUTH provisions these identities and owns the typed static matrix; there are no
database assignment rows. Registration and matrix membership are inert while
actions are planned. After AUTH-09E, ART accepts only a canonical AUTH service
context at its composition root and never derives identity from a Celery task,
executor ID, queue, environment string, or provider credential.

## Delivery order

```text
AUTH-09A fixed service identity and static matrix foundation
-> AUTH-09B controlled service ActorProfile/ActorIdentityLink provisioning
-> AUTH-09C actor and identity-link administrative reads
-> AUTH-09D actor and identity-link lifecycle mutations
-> AUTH-09E fixed service runtime admission
-> ART-02C1 admission/put-attempt foundation, inactive
-> ART-02C2 hidden verification/resolution/scanner behavior
-> ART-02C3 hidden recovery envelope
-> ART-02D hidden Operator routes and exact resource composers
-> AUTH_ART_02D_INTERNAL activation
-> AUTH_ART_02D_OPERATOR activation
-> later ART-03 through ART-06B hidden behavior
-> matching AUTH activation group after each behavior merge
```

`artifact.verification_job.retry` is independently evaluated and activated. It
is never implied by verifier, scheduler, or put-resolver activation. AWS provider
release is also separate: an authorized action cannot instantiate AWS until ART
live-provider proof is current.

## Mutation protocol

For a human caller, AUTH locks the actor, identity-link, and matched grant rows.
For a fixed service, AUTH locks the service ActorProfile and ActorIdentityLink,
then validates immutable `service_identity`, exact static service-action matrix
membership, and action availability. ART then locks artifact rows, recomposes
the final typed artifact context, completes one AUTH evaluation, stages ART
lifecycle/audit state, and lets the request boundary or Celery execution commit
once. Terminal Celery writes additionally require the matching ART executor and
execution generation. Authorization identity and execution fencing remain
independent checks.

## AUTH owner response

AUTH must add reviewed registration/transfer and activation chunk contracts,
add the AUTH-09E service-admission contract, repair stale AUTH documents and
catalogue descriptions, preserve every mapping, and prove no action becomes
active without its merged ART behavior manifest.

## ART owner response

ART must repair its plan/chunk sequencing, implement only hidden behavior before
activation, publish exact resource/guard/surface manifests, and never edit AUTH
catalogues, static matrix rows, evaluators, grants, or availability.

This handoff changes no runtime and starts no downstream chunk.
