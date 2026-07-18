# Test Design: WS-REV-001-02 Split

## Status

Planning-only test design. No backend test or fixture is implemented until the
AUTH-owned contributor-field foundation merges and the relevant child receives
a separate human start.

## Shared dependency gate

Every child begins with a deterministic dependency test that records:

- trusted-main SHA and single Alembic head;
- merged AUTH-09D-A PR/SHA;
- merged AUTH contributor-foundation PR/SHA and migration ID;
- absence of both retired task-subsystem contributor-identity storage names;
- presence of canonical `contributor_id` on TaskAssignment and Submission;
- database-backed canonical-human ActorProfile lineage;
- preserved task, submission, checker, and legacy-revision regression tests.

Any missing proof stops before a REV migration is generated.

## 02A - Guide Activation And Task Context

### Migration fixtures

| Case | Expected proof |
|---|---|
| Multiple projects with draft, active, and superseded guides | Active/superseded rows number independently per project; drafts remain null. |
| Historical rows with different effective times | Sequence follows `effective_at`, `created_at`, then `id`. |
| Activated guide missing required provenance | Upgrade fails and names the project/guide plus remediation. |
| Non-draft Task with exact same-project guide version | Task guide ID and activation sequence backfill exactly. |
| Task with missing, cross-project, or ambiguous guide context | Upgrade fails; current active guide is never substituted. |
| Protected Task stamps present | Downgrade refuses with destructive-remediation guidance. |

### Direct SQL constraints

- Reject zero/negative activation sequence.
- Reject draft with sequence.
- Reject active/superseded without sequence.
- Reject duplicate project/sequence.
- Reject mutation or clearing of an allocated sequence.
- Preserve sequence across active -> superseded -> active.
- Reject partial Task guide triplets and mixed guide ID/version/sequence.

### Concurrency

- Two first-time activations for one project serialize on the Project row and
  allocate distinct monotonically increasing sequences.
- Activations in different projects proceed independently.
- Reactivation racing with a new activation retains the old sequence and does
  not allocate twice.
- Publication locks all generation rows in deterministic type/ID order and a
  concurrent mutation of ProjectGuide, GuideSourceSnapshot,
  GuideSufficiencyReport, ProjectSetupRun, SubmissionArtifactPolicy,
  EffectiveProjectSubmissionArtifactPolicy, PreSubmitCheckerPolicy,
  PostSubmitCheckerPolicy, ReviewPolicy, RevisionPolicy, or transitional
  compensation-context row cannot create a mixed generation.

### Service behavior

- Draft creation allocates no sequence.
- First activation allocates once.
- Repeated activation of the sole active guide is a no-write idempotent return.
- Superseded-guide reactivation preserves original approval/effective
  provenance and sequence, clears superseded time, supersedes the current guide,
  and writes the reactivation audit with server-owned reason
  `older_guide_reactivated`; the route accepts no new caller reason/body.
- Draft, active-repeat, superseded-reactivation, invalid-state, and both
  competing-reactivation request/commit permutations have separate tests under
  the one canonical lock order.
- Task screening copies one complete guide identity.
- No semantic or lexical version comparison is used.
- No external call occurs while publication locks are held.

## 02B - Review Policy And Dormant Lifecycle

### Migration fixtures

| Case | Expected proof |
|---|---|
| Safe ReviewPolicy row | Approved duration defaults plus capacity 1, self-review false, close-task reject, optional evidence backfill. |
| `requires_second_review=true` | Upgrade refuses with guide/policy remediation. |
| Missing canonical decisions or finding fields | Upgrade refuses rather than broadening policy. |
| Existing RevisionPolicy with either legacy auto-reject value | Column is removed; no product row or lifecycle effect is created. |
| Existing normal Task/Assignment statuses | Values and timestamps are preserved. |
| Unknown or inconsistent historical status shape | Upgrade refuses with row IDs and remediation. |

### Direct SQL constraints

- Reject nonpositive preference/lease duration.
- Reject capacity other than one.
- Reject self-review true.
- Reject reject policy other than `close_task`.
- Reject unknown finding-evidence requirement.
- Reject malformed/duplicate/missing canonical decisions and finding fields.
- Reject `requires_second_review=true`.
- Reject activated ReviewPolicy and RevisionPolicy update or delete.
- Allow both draft-policy replacements before first activation.
- Reject unknown Task and TaskAssignment status values.
- Reject terminal Task without mapped reason/time and nonterminal Task with
  terminal fields.
- Reject Assignment status/timestamp mismatch.

### Service and lifecycle behavior

- New guide policy validates the exact v0.1 values.
- Activated ReviewPolicy/RevisionPolicy upserts fail without modifying the row.
- Either changed policy is created only under a new draft guide version.
- Lifecycle constants include accepted/rejected/cancelled and
  completed/blocked, but transition guards still reject attempts to enter them.
- Removal of `auto_reject_after_limit` creates no Review, finding, Task terminal
  status, Assignment terminal status, contribution, award, audit, or outbox
  effect. Executable limit/deadline block tests remain required in 09A.
- Checker paths cannot select `rejected` or `cancelled`.
- All three dormant cancellation reasons, including
  `legacy_revision_context_unrecoverable`, satisfy storage constraints but no
  02B service transition can create them.

## 02C - Submission Attribution And Lineage

### Migration fixtures

| Case | Expected proof |
|---|---|
| One assignment satisfying the exact inclusive temporal predicate | Submission receives that assignment ID. |
| No responsible assignment | Upgrade fails with submission/task IDs. |
| Multiple plausible assignments | Upgrade fails; current or latest assignment is not selected. |
| Assignment belongs to another task | Upgrade fails. |
| Submission contributor differs from assignment contributor | Upgrade fails. |
| Submission time equals assigned/accepted/released boundary | Inclusive predicate is applied exactly. |
| Missing acceptance, invalid interval, or overlapping reassignment intervals | Upgrade fails with responsible row IDs. |
| Same contributor assigned twice with non-overlapping intervals | The one interval containing submitted time is selected. |
| Timestamp tie yields two qualifying assignments | Upgrade fails as ambiguous. |
| Exact historical guide context | Guide ID/sequence backfill from locked version and task context. |
| Missing or inconsistent historical guide context | Upgrade fails; active guide is not substituted. |
| Valid N-1 chain | Upgrade succeeds and preserves every ID/version. |
| Cross-task, skipped, branched, or self-linked chain | Upgrade fails with chain remediation. |
| Protected lineage in use | Downgrade refuses. |

### Direct SQL constraints and immutability

- Reject assignment from another task.
- Reject contributor unequal to exact assignment contributor.
- Reject nonhuman contributor through the merged AUTH foundation.
- Reject version 1 with a predecessor.
- Reject version greater than one without predecessor.
- Reject predecessor whose task or version is not exact N-1.
- Reject a second successor for the same predecessor.
- Reject mutation/deletion of a finalized Submission's identity, attribution,
  version, predecessor, context, packet, evidence, or attestation.
- Reject EvidenceItem insert, update, or delete when its parent
  `Submission.locked_at` is non-null; `finalized_at` remains only the API alias.
- Permit only the separately owned set-once `artifact_hash` extension after
  finalization when that ART amendment later exists; reject overwrite.

### Concurrency and service behavior

- Two concurrent creates for one task serialize on Task/current head; one
  receives N and the other either receives N+1 under valid lifecycle state or
  fails with the stable conflict. They never create duplicate N or branches.
- Concurrent reassignment cannot change the assignment selected for a
  submission already being finalized.
- Release, authority revocation, and later reassignment preserve prior
  attribution.
- Suspended/deactivated human and service ActorProfiles are denied by the
  transaction-local AUTH revalidation. External subject, email, legacy typed
  profile ID, and token role are rejected as contributor substitutes.
- Submission request input never supplies assignment ID, contributor ID,
  version, predecessor, or guide context.
- TaskAssignment gains no guide/context field.
- No duplicate SubmissionVersion model/table/API appears.

## Regression and negative-scope proof

For every child:

- existing project-guide, task claim/start, submission finalization, checker,
  and legacy revision tests remain enabled;
- no assertion is weakened, skipped, or rewritten to accept unsafe lineage;
- no AUTH, ART, CON, compensation, contribution, reputation, adjudication, queue,
  lease, Review, finding, or public review-route file changes;
- migration upgrade is tested against real PostgreSQL, not only metadata;
- unsafe upgrades leave no partial DDL/data effects; safe fixtures prove
  upgrade/downgrade/upgrade, and protected-row fixtures prove downgrade refusal;
- full isolated suite remains at or above 78 percent repository coverage;
- each materially changed backend module remains at or above 90 percent;
- stale wording and Markdown-link checks pass.

## Human decisions still required

1. Exact positive v0.1 default for
   `review_preference_window_seconds`.
2. Exact positive v0.1 default for `review_lease_duration_seconds`.

These values are product policy. They are not inferred from the unrelated
`ReviewPolicy.sla_hours`, and no migration may start while either is unset.
