# Project Guides and Policy Approval

This specification describes the current project-guide boundary. Use the
[capability ledger](roadmap_status.md) for delivery and deployment evidence,
the [project operating manual](operations_project_operating_manual.md) for the
manager workflow, and the [checker framework](architecture_checker_framework.md)
for proposal and external-image contracts.

## Guide source custody

An authorized Project Manager creates versioned guide metadata with task
examples and a complete document list, then uploads each declared original.
Workstream computes the byte size and digest and stores originals through
ArtifactStore. Document membership and source-snapshot identity are internal;
the client does not create a separate public snapshot.

Upload establishes source custody. It does not automatically invoke setup
inference. A changed document set requires a new guide. Exact create/upload
replay rechecks current authority and retains the original result.

## Optional setup assistance

The Project Manager explicitly requests one of two existing compilation paths:

- `POST /api/v1/projects/{project_id}/guides/{guide_id}/setup` requests assistance.
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/requirements/compile`
  compiles uploaded rules without a model provider.

Both require current exact-project manager authority and a UUID
`Idempotency-Key`. They reserve durable work; neither upload nor a readiness scan
can manufacture this authority. The service rechecks authority at execution,
projection and finalization. Recovery does not repeat an uncertain provider call.

Initial inference receives only the assigned guide documents and task examples,
apart from trusted system instructions. An explicit correction may also include
the manager's written feedback. It receives no registry catalogue, previous
image selections or runtime-availability metadata.

The output proposes source-cited PRE and POST requirements and sufficiency
findings. It does not select implementations or control task lifecycle policy.
A source-sufficient proposal need not have an image implemented yet. The manager
and engineers assess the proposal, implement project-owned images where needed,
and register those images separately.

## Policy approval

An authorized human selects exact registered image digests and configuration
for PRE and POST independently. Explicit empty phase lists are valid; suggestion
IDs do not impose image-membership requirements. The Workstream PRE default is
separate and cannot be removed by a project image.

Approval binds the displayed proposal and policy facts, warning acknowledgements
and exact selected image/configuration commitments. PRE approval and POST
approval are separate. Approval neither calls an evaluator nor rewrites the
finalized proposal. Later image registration does not alter retained proposal
bytes or require inference to run again.

See the [checker policy template](template_checker_policy.md),
[artifact storage contract](spec_artifact_storage_service.md) and
[manager approval instructions](operations_project_operating_manual.md#review-approve-or-correct-a-guide-proposal)
for the detailed owner contracts.

## Corrections and manager handoff

A correction reserves one successor over the original documents and examples,
with the manager's reason. Source readiness cannot dispatch that correction.
Authorized setup reads expose its `correction_operation_id` and
`predecessor_compilation_id`, allowing another authorized manager to discover
and dispatch the saved request without the creator's response receipt.
Blocked proposals may be corrected but not approved. An uncertain provider
attempt is not an invitation to repeat the paid effect through a correction.

## Activation and locked task context

Activation requires complete approved PRE/POST policies, intact source and
compilation custody, supported review/revision policies and an explicitly
selected published ContributionPolicyVersion. It validates the exact guide
mutation generation and expected predecessor. It does not require an existing
Task, Submission or completed checker run.

One caller-owned transaction records AUTH evidence, activation receipt, guide
binding and predecessor supersession. Exact replay requires current authority
and returns retained facts rather than silently selecting newer policies.

The default ReviewPolicy requires human review. When the locked policy is
false, passing required POST checks follows the shared authorized acceptance
operation without fabricating a Review or reviewer contribution. The
[review lifecycle contract](spec_review_lifecycle.md) defines review/revision
rules; its planned boundaries do not become live merely through guide activation.

Tasks lock their applicable guide and policy identities; a later guide does not
rewrite existing submissions. See [task and assignment contracts](spec_task_assignment.md)
and [contribution/compensation ownership](spec_contribution_compensation.md).
Compensation uses the locked ContributionPolicyVersion; no task-local terms
or parallel guide-keyed compensation contract substitute for it.
