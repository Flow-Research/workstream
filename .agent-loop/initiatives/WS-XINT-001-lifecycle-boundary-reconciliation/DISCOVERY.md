# Discovery: WS-XINT-001 Lifecycle Boundary Reconciliation

## Sources inspected

- trusted `origin/main` at `9a04434`;
- ART-02A3 reviewed implementation at `935b1a2` in its isolated worktree;
- AUTH-09 planning/implementation worktree at `c4200a7`;
- REV planning worktree at `1b0b549`;
- CON planning worktree at `217115b`;
- the merged AUTH action catalogue and authorization specifications;
- the ART plan, decisions, and chunk contracts.

Unmerged worktree content is discovery evidence, not a runtime dependency.

## Current authorization facts

The merged catalogue has 25 planned ART ActionIds. Eleven are currently assigned
to `ActionOwner.ART_02D`; the other fourteen are assigned across `ART_03`,
`ART_04A`, `ART_04B`, `ART_05`, `ART_06A`, and `ART_06B`. Registration is
non-executable, but the owner field is also being used as activation custody.

The active WS-AUTH-001-09 worktree's reviewed `09A` subchunk defines seven fixed
artifact service identities and eleven exact static matrix memberships. Its
current plan correctly keeps every matrix row planned, but retained obsolete
feature-owned activation wording. That conflicts with the newer AUTH-owned
activation-custody decision.

ART D28 already prohibits ART from inventing service principals or activating
authorization. ART D25, the ART plan, ART-02C2, ART-02D, AUTH-09 documents, and
REV planning still contain older feature-activation wording.

## Current ART facts

PR #129 added inactive scratch preparation and committed-source values only.
ART-02A3 replaces ArtifactStore v1 with byte-only v2 and LocalStorage v2, but it
does not add admission, provider execution, verification, recovery, product
cutover, service identity, evaluator, or action activation.

ART owns artifact commitments, contents, replicas, receipts, bindings, provider
attempts, verification jobs, recovery attempts, storage audit, adapter
composition, and execution fencing. PostgreSQL stores record truth; ArtifactStore
stores immutable bytes.

## Current REV facts

REV owns ReviewPacketManifest and ReviewEvidenceArtifact semantics, Review,
ReviewFinding, ReviewLease, revision preparation, and product decisions. It
intends to consume ART through typed capabilities and AUTH through the public
authorization service. Raw ArtifactStore, provider references, AUTH repositories,
and grant queries are already prohibited.

REV correctly limits artifact bytes to an active lease and exact current packet,
but its action choreography still describes owning REV chunks as activation
owners. It also needs a closed transaction contract for evidence candidate/
finalization and for the final review decision that invokes CON.

## Current CON facts

CON owns `ContributionRecord`, contribution policies and freezes, awards,
fulfillment, shared outbox delivery, and related audit/projections. Its plan
already defines a flush-only transaction participant called by REV and forbids
CON commits or provider I/O inside the review transaction.

The current CON artifact handoff makes a newly serialized contribution-evidence
artifact mandatory before CON-09A. That is unnecessary for core ContributionRecord
creation. The immutable Review, Submission, reviewer, contributor, assignment,
policy-freeze, and reviewed-packet commitment are sufficient canonical inputs.
An export or independently stored contribution-evidence document can be a later
optional projection without gating the core transaction.

## Existing tests and proof surfaces

- AUTH catalogue parity and action availability tests.
- AUTH fixed service identity and static service-action matrix tests.
- ART adapter, migration, cancellation, and concurrency tests.
- Planned REV conformance matrices for authorization, artifact disclosure, and
  contribution atomicity.
- Planned CON matrices for idempotency, outbox, callback, and compensation
  lifecycle behavior.

## Gaps

- No one canonical document names both resource owner and activation custodian.
- No complete AUTH-custody transfer exists for all 25 planned ART actions.
- The four initiative plans do not share one lock/commit vocabulary.
- Core contribution creation is coupled to an ART projection that the user has
  rejected.
- Parallel branches need immutable handoffs instead of direct cross-worktree
  edits.

## Risks

- Partial owner transfer could leave unused enums or dual activation writers.
- An active action without merged feature behavior would turn a registration
  row into an unsafe allow path.
- Feature behavior requiring an already-active action would create a circular
  dependency.
- ART provider calls inside REV or CON transactions would make atomic rollback
  impossible.
- A generic artifact read action would broaden reviewer or contribution
  disclosure beyond canonical product relationships.
