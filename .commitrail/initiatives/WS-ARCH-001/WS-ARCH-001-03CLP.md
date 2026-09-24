# WS-ARCH-001-03CLP — Deferred contributor submission windows and skip

- Initiative: `WS-ARCH-001`
- Durable disposition: `Stopped`
- Intended merge outcome: record deferral from v0.1, remove lease/skip from the
  critical path, and retain corrected future revision-window intent.

## Intent

The user has paused timed contributor assignment leases and voluntary skip.
These improve abandoned-work handling but do not gate the core v0.1 lifecycle.
Continue ARCH-03C2 and the existing public task/guide integration sequence.
Keep authorized claim/start, exact assignment ownership, locked policy lineage,
atomic admission-backed submission, safe retries and authority-revocation handling.
No clock feature or project-policy duration field is implemented by this plan.

## Current behavior and limitation

TASK claim creates a unique assignment and records PostgreSQL
`clock_timestamp()` after live authority consumption, but has no contributor
expiry field or automatic timeout. `deadline_at` is descriptive task metadata.
TASK's existing authority-invalidation release is cause/permission-specific and
not a generic abandonment command. The retained manager `release_to_ready`
operation changes a screened task only; widening its generic transitions would
leave an active assignment behind. It is not safe abandoned-assignment recovery.

Claims do not expire automatically during this deferral. Before release, assess
and document safe abandoned-assignment recovery or explicitly constrain pilot
operations. Do not imply that an Operator recovery command exists or recommend
manual SQL, forged revocation events or weakened ownership as a workaround.
This assessment does not restart the deferred lease feature.

## Bounded change

### Allowed

Planning/documentation only: this record, ARCH overview/current PLAN/CHUNK_MAP,
the adopted 03C contract if needed to remove this PR's prerequisites,
`.commitrail/INDEX.md`, `docs/roadmap_status.md` and
`docs/spec_chunk_4_task_queue_assignment.md`. Local ignored roadmap exports
must change together if present. No exports are present in this checkout.

### Not allowed

No application/schema/migration/API/worker/test/workflow changes, compatibility
paths, retained-data deletion, automatic acceptance, public lease activation,
new policy table or scheduler. Do not redesign live REV or claim a future test
has executed. Do not start another implementation chunk as part of this record.

## Retained future design — not v0.1 requirements

The following replaces the original initial-claim-only proposal. It is retained
intent, not an implementation-ready contract or authorization to resume.

1. The manager configures `contributor_assignment_lease_duration_seconds` on
   the existing versioned ProjectGuide through authorized create/draft update.
   Bind its exact value/hash to activation and frozen task/assignment context;
   no unrelated ReviewPolicy/ContributionPolicy field or new policy subsystem.
   Two days is an example, not an approved default. Initial default, numerical
   bounds, migration prerequisites and revision rebase interactions require
   explicit design before implementation. Missing duration is **not** a current
   v0.1 readiness failure while this feature remains deferred.
2. Claim starts the initial contributor submission window at one PostgreSQL
   wall-clock instant after serialization locks. A valid immutable Submission
   atomically ends that window. Checking, queue waits and human review consume
   no contributor submission time and cannot expire the assignment's closed window.
3. Committing an authorized human `needs_revision` decision atomically starts
   a fresh submission window at PostgreSQL time, using the governed duration.
   Bind this window to the exact assignment, originating Review/revision episode
   and attempt identity. Revision submission ends that window. Retrying claim,
   review decisions, preparation, dispatch or submission never restarts a clock.
   Lock the new window's duration when the decision commits; later policy changes
   or context rebase must not silently reset its start/expiry. Reconcile the
   selected duration with the existing complete-context revision rules before code.
4. Expiry closes the exact open initial **or revision** window and assignment,
   clears its active assignee and returns eligible work to `ready`. Voluntary
   skip uses the same TASK-owned exact release mechanics with separate authority.
   Do not use “any prior Submission exists” as a blanket release prohibition:
   revision expiry necessarily has prior submissions. Preserve every prior
   Submission, Review, finding, artifact, admission and audit event unchanged.
   Closed windows under checking/review and final accepted/rejected work cannot
   be reopened by expiry. Revision-episode/queue/preparation closure must be
   coordinated atomically through the existing owners, not left detached.
5. Reclaim creates a new assignment and fresh submission window, even for the
   same person. Only never-submitted work opens an initial window. Reclaim after
   revision expiry must explicitly continue the retained revision lineage under
   the new assignee, linked to the predecessor Review, Submission and findings;
   it cannot silently reset to first-submission behavior. Existing TASK custody
   rejects retained-submission initial paths and contributor substitution, so
   reconcile TASK/REV continuation and authorized new-assignee custody before
   resuming implementation. Do not copy the previous contributor's identity or
   transfer their admission, artifacts or authority.
   Define required visibility of predecessor findings through authorized owner
   facts; no automatic private-data exposure or contributor credit inheritance.
   Existing exact-assignment checks must reject stale attempts after reclaim.
6. PostgreSQL time is authoritative. Foreground preparation and final admission/
   Submission mutation reject expired open windows even if cleanup is delayed.
   Recheck after external processing and lock waits. Use a bounded periodic
   Celery scan for cleanup; ordinary database triggers do not fire with elapsed
   time. Candidate discovery is not authorization and must revalidate exact
   assignment/window/state under existing lock order. No new scheduler.
7. Reuse the TASK release seam and exact AUTH/PREP with distinct skip, expiry
   and authority-change provenance. Never broaden generic manager transitions
   or the delivered authority-reconciler permission. First valid serialized
   release owns one immutable outcome; later delivery acknowledges that outcome
   without relabeling it or touching a successor. Own skip finding the current
   window already expired commits expiry and returns that reason, rather than
   raising inside the transaction and rolling the release back.
8. Authorized own-history responses distinguish expired/skipped assignments
   from wrong ownership without exposing the replacement contributor. A previous
   submission window ID cannot authorize a new window, even within the same
   assignment or with the same actor and idempotency key.

## Future ownership and sequencing

Proposed ARCH-03C3/03C4 lease children and expiry-worker composition are parked;
they are not predecessors of ARCH-03C public integration or downstream checking.
The current sequence stays ARCH-03C2 -> existing public task/guide integration
-> intake/Submission integration -> durable post-submit evaluation and routing.

If resumed, review PROJECTS duration/activation custody, TASK claim/window/release,
ART admission consumers, AUTH exact trigger authority and REV decision/episode
owners together before defining PR-sized children. Reconcile the current
[revision deadline/closure contract](../../../docs/spec_review_lifecycle.md#revision-limits-repair-and-legacy-recovery):
it presently blocks preparation on exhaustion and requires an explicit closure
command. This stopped proposal does not silently replace that rule with READY
requeue. Avoid making REV lifecycle depend on a timer subsystem now.

## Acceptance criteria

For this deferral:

- Current navigation, dependency sequence and release gates do not require
  timed contributor leases, their policy field or voluntary skip for v0.1.
- The no-automatic-expiry limitation and unproven abandoned-assignment recovery
  are explicit; core ownership/authorization/submission safeguards remain.
- Retained intent includes initial and revision windows, submission closing each
  window, no contributor time during review, and retries never renewing time.
- Revision expiry permits historical submissions while preserving immutable
  evidence; new claimant identity/admission cannot inherit from old attempts.

Before any future implementation, require real PostgreSQL tests for otherwise
valid expired initial/revision admission rejection; submitted/closed windows
surviving checking/review delays; exactly one new window per committed
`needs_revision` despite retries; revision submission versus expiry races;
revision expiry with retained Review/findings/Submission rows unchanged;
same-person and different-person reclaim with explicit predecessor lineage;
stale admission/window replay rejection; generic manager-release denial;
competing skip/expiry/revocation and queue cleanup; delayed/duplicate Celery
scans; lock-wait clock skew; and authorized expiry feedback/concealment.
Removing the final expiry guard or exact window/assignment binding must make
its otherwise-valid negative regression fail. These are future requirements,
not executed runtime evidence for a stopped feature.

## Risk and review routing

- Risk class: L1 (lifecycle, authorization and policy plan reconciliation only).
- Required reviewers: architecture/security/reuse and QA/product_ops/documentation.
- Human review focus: deliberate v0.1 deferral, no-auto-expiry limitation,
  operational recovery assessment, and retained revision semantics.

## Evidence

| Claim | Proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing claim has no timed expiry | TASK authorized_commands/models source | DB claim time and exact assignment exist; no lease runtime | No auto-release promised |
| Existing manager release is not recovery | TaskService.release_to_ready and lifecycle source | Screened-task transition only; no assignment close | Recovery assessment required |
| Revision intent conflicts with blanket prior-Submission guard | Prior plan versus human requirement and REV specification | Corrected as deferred intent with explicit owner reconciliation | Future atomic episode/window design |
| Deferral consistency | Links, Commitrail/stale checks, focused plan review | Exact results in PR | No runtime feature evidence claimed |

## Review findings

The initial plan failed to distinguish a closed submitted window from an open
revision window. Reclaim of expired revision work also cannot be described as an
initial submission path: current TASK custody rejects that retained-submission
and new-contributor combination. Preserve explicit TASK/REV continuation as a
future design requirement, not an implemented bypass. These corrections remain
recorded for any later restart.
Earlier safeguards remain: existing guide config carrier; no generic manager
release bypass; expiry-specific committed skip receipt; single terminal outcome.

## Reconciliation

- Current-source reconciliation: merged #432 remains complete. No lease/skip
  requirement has landed on main; remove this PR's proposed mandatory additions.
- Next usable boundary: ARCH-03C2, then existing public task/guide integration.
- Remaining risks: abandoned work does not automatically expire; future lease
  work must reconcile REV rules, duration defaults/bounds and retained data.
