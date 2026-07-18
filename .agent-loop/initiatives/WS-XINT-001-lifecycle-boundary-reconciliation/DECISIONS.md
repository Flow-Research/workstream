# Decisions: WS-XINT-001 Lifecycle Boundary Reconciliation

## D1 - AUTH Owns Activation Custody

`ActionOwner` denotes the exact AUTH chunk authorized to change one registered
action from `planned` to `active`. ART, REV, and CON remain feature/resource
owners but are not activation custodians. There is no dual writer.

## D2 - Registration, Hidden Behavior, Activation

Every cross-initiative action follows three reviewed checkpoints: AUTH registers
the planned action and typed context contract; the feature owner implements
hidden behavior, resource composition, guards, and calls while the action still
fails closed; AUTH integrates the evaluator and alone activates the action.

## D3 - Complete ART Custody Transfer

AUTH must transfer all 25 currently registered ART actions, preserving every
ActionId-to-PermissionId mapping, to closed AUTH activation custodians. Fixing
only the eleven ART-02D rows would leave the same ambiguity in ART-03 through
ART-06B. Unused ART owner enum values are removed atomically after transfer.

## D4 - Fixed Artifact Services Are Exact

AUTH owns the seven fixed artifact service identities and their exact action
matrix rows. A service receives no human role, project grant, broad permission
union, or implicit access from its identity name. A Celery executor ID is
execution fencing, not authorization identity.

## D5 - Authority Locks Before Feature State

For mutations, AUTH prepares and locks canonical authority first. Feature
owners then lock their records, recompose final typed facts, complete one AUTH
evaluation, stage feature/audit/outbox writes, and let the request boundary or Celery execution commit
once. Reads remain request scoped. Feature domain services flush and never
commit on behalf of a caller.

## D6 - ART And REV Split Semantics From Bytes

REV owns the meaning and membership of review packets and reviewer evidence.
ART owns immutable bytes, commitments, bindings, provider verification, and
artifact recovery. REV receives only typed capabilities and stable binding IDs;
it never receives ArtifactStore, scratch paths, or provider authority.

## D7 - Core Contributions Do Not Call ART

The review transaction invokes a CON-owned flush-only participant with canonical
Review, Submission, actor, assignment, policy-freeze, and reviewed-packet
commitment facts. CON creates reviewer contribution records for every committed
Review and submitter contribution records only for `accept`. It does not call
ART or require a new contribution-evidence artifact. Any later export artifact
is an optional projection with a separate action and failure lifecycle. The
already-stabilized submission artifact digest may be copied as immutable lineage;
CON does not load, verify, or rederive it through ART.

## D8 - Separate Parallel Owner Work

This coordination PR changes no runtime. After merge, AUTH, ART, REV, and CON
owners amend and implement only their own bounded chunks. A handoff is not an
implementation start signal and cross-initiative successors remain human-owned.

## D9 - Review Evidence Has One Exact Binding Action

Review finding and response bytes bind through
`artifact.review_evidence.binding.create`, mapped to existing
`artifact.binding.create`, assigned only to `workstream.artifact.binding`, and
activated only by `AUTH_ART_REV_EVIDENCE` after hidden ART capability behavior
merges. No generic artifact-read or binding PermissionId is executable as an
action alias.

## D10 - ContributionPolicy Owns Award Eligibility

`ContributionPolicyVersion` is the sole project policy that determines what an
immutable `ContributionRecord` earns. Each `ContributionRule` is explicit for
`accepted_submission` or `completed_review` and is either unpaid or references
immutable `ContributionAwardDefinition` rows. A resulting
`CompensationAward` carries instrument `money` or `project_points`; only then
does the shared outbox route money to a payment-request/settlement adapter or
points to the project-points adapter. Neither downstream rail decides whether
the contribution earned an award.

## D11 - Project Contributor Roles Are Independently Granted

The v0.1 `ProjectRoleGrant` values are exactly `submitter`, `reviewer`, and
`adjudicator`. There is no combined role. One human may hold all three
capabilities through independent immutable rows, each independently issued,
revoked, regranted, and revalidated. Adjudication actions remain unavailable
until WS-REV defines their complete product contract and AUTH activates them.

## D12 - Fixed Services Require A Separate Runtime Admission Path

Service ActorProfiles use the canonical identity-link boundary and one fixed
`service_identity`, but they never enter human provisioning or human grant
evaluation. AUTH owns one typed service-admission path from verified subject to
the exact static action row. Feature owners still own resource facts, guards,
hidden behavior, and execution. Service provisioning does not activate any
feature action, and missing service rows deny only the service request rather
than preventing administrative provisioning.

## D13 - Authority Loss Is Consumed By The Owning Lifecycle

AUTH records exact grant/profile/link invalidation and its cause. Submitter
grant loss is consumed by task-assignment reconciliation; reviewer grant loss
is consumed by review reconciliation; adjudicator grant loss is consumed by
adjudication-assignment reconciliation only after that lifecycle is enabled.
AUTH never mutates those product records, and one role's revocation never
removes another contributor or administrative grant.
