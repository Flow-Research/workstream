# Chunk Contract: WS-ART-001-04C1 — Submission Durable Put Intent

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Planning correction after XINT-06A

## Goal

Consume the passing scratch result, reauthorize final facts, reserve capacity,
persist one put attempt, and hand the checked ZIP to ArtifactStore once.

## Allowed Files

Submission producer integration with generic admission/put attempt, one typed
durable submission-bundle intent model/migration, typed TASK/PROJECT/AUTH
seams, hidden orchestration, tests/docs/scoped CI.

## Not Allowed Changes

Ready admission publication, Submission creation/binding, public route,
provider redesign, second recovery aggregate, retention/deletion, or availability.

## Acceptance Criteria

- A passing execution must present both the exact live `PreparedArtifact` and
  its single-use process-local `PreSubmitPassCapability`; durable evidence by
  itself is never mutation authority.
- 04C1 adds the closed `SubmissionBundleArtifactAdmissionRequest` producer
  shape and one narrow durable intent. The intent has unique foreign keys to
  the exact immutable `PreSubmitEvidenceSet` and generic `ArtifactPutAttempt`;
  it does not duplicate the evidence row's complete lineage. Service-level
  locked validation requires that evidence to remain `passed` and `eligible`.
  Those typed joins recover without digest parsing every fact needed by 04C2:
  actor profile, identity link, project, task, assignment, predecessor
  identity/version, locked guide, snapshot and policy lineage,
  semantic-manifest identity/digest, archive digest/size/media type,
  effective-plan digest, storage scheme, operation identity, and put-attempt
  identity.
- TASK/PROJECT typed capabilities lock and revalidate their owned task,
  assignment, predecessor, guide, snapshot, and locked-policy facts. AUTH owns
  actor/link/project-authority/action revalidation and supplies only the opaque
  transaction-bound `PreparedAuthorizationHandle`; ART imports no AUTH
  repositories and implements no local evaluator.
- Fresh final authority consumption, the durable submission-bundle intent,
  capacity reservation, authorization evidence, and generic put attempt commit
  atomically before provider I/O. Denial or lineage drift creates none of those
  effects and closes scratch.
- The transaction commits before the exact prepared ZIP is handed once to the
  existing `ArtifactStorageOrchestrator`. Provider acknowledgement ambiguity,
  caller loss, and post-intent replay reuse the existing observation/recovery
  machinery; no second recovery aggregate or provider write path is added.
- The shared `ArtifactPutAttempt` producer constraints explicitly admit the
  submission-bundle producer. Generic scanner, verification, and recovery paths
  remain producer-neutral; guide setup continuation must ignore submission
  attempts and no producer-specific worker path is added.
- Exact concurrent continuation of one live prepared generation is fenced by
  durable uniqueness and creates one intent, capacity effect, and logical put
  effect. If a process dies after immutable passing evidence commits but before
  durable intent, recovery requires a complete fresh upload and checker
  execution with a new prepared generation, evidence identity, and immediate
  pass capability. An old durable evidence row never mints or remints a pass
  capability and old scratch/capability state is never reused.
- 04C2 must be able to reconstruct the complete publication lineage from
  PostgreSQL after scratch/process loss; scratch paths, handles, prepared
  authorization, and opaque request-digest decoding are forbidden.
- `artifact.submission_bundle.prepare` remains planned and unavailable. 04C1
  supplies a deny-by-default production adapter plus bounded test authority;
  XINT-05A alone may activate the production contributor action.

## Verification Commands

Focused tests must prove: evidence without a live capability denies; capability
or generation mismatch denies; revocation and lineage drift deny before any
durable/provider effect; concurrent continuation creates one intent/charge/
logical put; pre-intent process loss requires complete reupload/rechecks and a
new evidence identity; post-intent ambiguity resumes through existing
observation/recovery; 04C2 lineage reload uses PostgreSQL only; and a provider
spy observes no read/write before the durable transaction commits. Also run
the guide-continuation regression proving submission attempts are ignored. Run
Ruff, hosted gates, 90% owned-subsystem coverage, and the 78% repository gate.

## Required Reviewers

Security/auth, architecture, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

Provider I/O must be impossible before the durable authorization transaction.
