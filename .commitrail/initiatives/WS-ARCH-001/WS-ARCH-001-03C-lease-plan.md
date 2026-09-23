# ARCH-03C — Contributor assignment lease and skip plan

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: adopt the contributor lease/skip requirement and its
  bounded implementation sequence; runtime implementation remains Planned.

## Intent

A contributor may skip their claimed task. A project-configured lease starts
when PostgreSQL records the claim, not when work starts. Skip or expiry closes
that assignment and returns eligible pre-submission work to `ready`, available
to any currently authorized contributor, including the previous contributor.
Retain history and explain an expired own assignment distinctly from lack of
ownership. Two days is the user's duration example, not an adopted global default.

## Current behavior

`tasks/authorized_commands.py::claim` already creates a unique TaskAssignment
with `assigned_at=clock_timestamp()` after live AUTH consumption. Its replay
receipt prevents duplicate claims. `tasks/models.py` has assignment history and
one-active-assignment uniqueness, but no contributor lease expiry. Task
`deadline_at` is descriptive metadata, not a claim-relative lease.
`tasks/assignment_invalidation.py` owns exact authority-caused release with
immutable evidence; its cause and fixed-service permission are not generic skip
or expiry authority. `tasks/submission_composition.py` and ART preparation own
the existing exact-assignment admission path. PROJECTS owns frozen guide/policy
facts. ReviewPolicy's reviewer lease is unrelated. Existing Celery workers
provide the scheduling/execution infrastructure; no new scheduler is required.

## Bounded change

### Allowed

This planning PR changes only this record, ARCH overview/current PLAN/CHUNK_MAP,
the adopted 03C contract, `.commitrail/INDEX.md`, `docs/roadmap_status.md`, and
`docs/spec_chunk_4_task_queue_assignment.md`. Update ignored local roadmap exports
only if present. Subsequent implementation children must name their exact files
and tests in their own existing-initiative records before editing code.

### Not allowed

No application, schema, migration, worker, API, dependency or test changes here.
No new login/eligibility path, compatibility implementation, generic authority,
retained-data deletion, reviewer-lease redesign, automatic acceptance, or
post-submission lifecycle reset. No task-deadline reinterpretation or fabricated
AUTH invalidation event to make skip/expiry fit an unrelated permission.

## Design and decisions

1. **PROJECTS owns configuration; TASK owns the lease.** Add a positive bounded
   contributor lease duration to governed project configuration and include its
   version/hash in the existing frozen guide-context contract. Do not reuse
   ReviewPolicy or ContributionPolicy for an unrelated contributor timeout.
   The policy-carrier decision is an explicit 03C3 source-design task: there is
   no contributor-duration field today. Extend existing project configuration
   and custody where possible; justify any necessary new policy record before
   implementation. No separate policy engine or approval subsystem.
   Exact unit/name, default and maximum must be explicit in 03C3's reviewed
   contract. Missing/invalid configuration must not activate claimable work.
2. **Claim freezes duration and expiry.** The ready task carries its governed
   duration/identity; claim copies it to the new assignment, captures one
   PostgreSQL wall-clock instant after serialization locks, and computes the
   expiry from it. Project policy edits do not silently change a running lease
   or the policy already locked on a ready task. No client clock, request time,
   transaction-start `now()` or process clock determines eligibility. Start,
   retry and replay do not extend expiry. No heartbeat/renewal feature is added.
3. **Exact assignment identity remains mandatory.** A reclaim creates a new
   assignment ID and a fresh claim-relative lease, even for the same person.
   Every preparation, admission and Submission stays bound to its assignment;
   previously issued preparation/admission cannot transfer to a new assignment.
4. **One TASK release operation, explicit reasons.** Reuse the current TASK
   transaction/state/evidence mechanics for authority revocation, contributor
   skip and lease expiry, keeping each trigger's authorization and proof
   separate. Proposed assignment terminal reasons are `skipped` and `expired`,
   alongside existing `authority_revoked`; review schema vocabulary before code.
   Close the exact active assignment, record release evidence and clear the
   task's assignee in one transaction. Return the task to `ready` only from
   `claimed`/`in_progress` with no retained Submission for that assignment.
   Preserve locked task policy, attempts, admissions and artifact evidence.
   If skip arrives after expiry, record expiry rather than disguising it as skip.
5. **Foreground checks are decisive; worker timing is not permission.** Start,
   preparation reservation/execution/recovery, admission consumption and final
   Submission creation check the exact active assignment against PostgreSQL
   time under the owning locks. `observed_at >= expires_at` is expired.
   A stale active row cannot authorize submission while the worker is delayed.
   Recheck after external processing and after lock waits, immediately at the
   final atomic admission/Submission mutation. Define this check as the
   serialization point; no requirement to predict the future commit timestamp.
   A Submission validly created before that point wins; later cleanup cannot
   reopen it. An expired pre-submit attempt creates no Submission.
6. **Periodic bounded Celery sweep.** A configurable recurring schedule scans
   indexed due active assignments in bounded batches. Candidate discovery is
   advisory; release re-locks/revalidates the exact assignment, PostgreSQL time,
   task state and no-Submission condition. Follow existing TASK/AUTH lock order;
   do not lock assignment rows ahead of the task or hold scan locks across
   external calls. Overlapping workers, delayed jobs and redelivery are safe.
   A missed scan catches up on the next run; no per-assignment countdown job,
   pg_cron dependency or timer-trigger subsystem. Ordinary PostgreSQL triggers
   can enforce writes but cannot wake themselves when time passes.
7. **Separate, minimal authority.** Contributor skip requires live exact-project
   Submitter authority and ownership of the exact active assignment. The expiry
   worker needs an explicitly reviewed fixed-service action and database-bound
   due-assignment facts. Do not broaden the delivered authority-reconciler
   permission or use the dispatcher as product authorization. Reuse AUTH/PREP
   and existing worker conventions, not a second authorization system.
8. **Useful and private feedback.** Authorized contributors can read their own
   assignment's server-issued start, expiry and terminal reason. Expired own
   assignment returns a stable expiry-specific code/message (including after
   someone else reclaims); skipped own assignment is distinct. Wrong-owner or
   inaccessible project responses preserve existing concealment and never
   disclose the replacement contributor. Same-key old claim replay cannot
   resurrect/extend the lease or claim a new assignment; a new claim uses a new
   request key and normal current authority. Client countdown is informational.

## Implementation sequence

Keep ARCH-03C2's adopted authority-event producer/registration scope intact.
Before declaring the public task workflow complete, add these owner boundaries:

| Boundary | Outcome | Required predecessor |
|---|---|---|
| ARCH-03C3 | Governed contributor duration, frozen task/assignment lease facts, minimal claim writer and migration together; no compatibility path | Delivered PROJECTS context/CP08; current-source policy-carrier review |
| ARCH-03C4 | Exact TASK skip/expiry release, AUTH contracts and decisive foreground expiry guards across existing preparation/admission/Submission consumers | 03C3; reuse delivered 03B9/03C1 mechanics without broadening their authority |
| Remaining ARCH-03C public integration | Exact contributor skip/history/queue exposure, fixed-service expiry authority and periodic worker composition, plus existing public task/guide readiness wiring | 03C2, 03C3, 03C4; public surface remains bounded through reviewed child contracts |

These are owner boundaries, not a promise that the remaining public integration
fits one PR. No completed chunk restarts. Neither lease implementation nor the
worker may be presented as delivered by this planning PR. Downstream intake
and post-submit integration retain their existing owners and consume these
lease guards; they do not implement a second assignment lifecycle.

## Acceptance criteria and future proof

The following are **future implementation tests**, not executed runtime evidence
for this plan. Use real PostgreSQL and production AUTH/owner paths; no sleeping
for two days, mocked ownership or disabled unrelated guards.

| Required behavior | Future proof / fixture and valid control |
|---|---|
| Configured claim-relative duration | PROJECTS contract/migration tests: positive duration survives approval/hash/context/task/assignment; zero, missing, invalid bounds reject; valid control follows identical guards |
| PostgreSQL time and locked policy | TASK claim tests: skew app/client clocks, wait for serialization lock and compare stored claim/expiry with DB time; later policy change leaves locked task/assignment unchanged |
| Skip and reclaim | TASK release integration: own active skip returns READY, old row terminal, new contributor and same-person reclaim create distinct IDs; unauthorized/project-substituted skip leaves rows unchanged |
| Expiry without worker | Real preparation/admission creation tests with otherwise-valid exact policy, artifact custody and admission, due assignment and worker disabled: expiry-specific rejection, no Submission; identical unexpired control succeeds |
| Processing crosses expiry | Delay external preparation or hold transaction lock until due; final admission/creation recheck rejects while already-expired-at-start tests remain separate |
| Races and replay | Independent sessions: skip/expiry versus Submission, duplicate sweep, simultaneous reclaim and AUTH role changes; exactly one valid result, no deadlock or partial release; old claim/skip replay never mutates successor |
| Old upload after same-person reclaim | Valid admission for prior assignment cannot be consumed using the new assignment; no provider/check rerun can silently retarget it |
| History and concealment | Public own-assignment expiry/skipped feedback before/after reclaim; no replacement actor/private data; inaccessible project gets existing concealment response |
| Post-submit boundary | Valid existing Submission excludes all ordinary skip/expiry release; post-check/review/revision are not reset |
| Worker recovery | Real scheduled Celery worker and PostgreSQL due scan: bounded batches, missed scan catch-up, overlapping deliveries and exact-service revocation; cleanup is idempotent and does not authorize foreground access |
| Regression discrimination | Removing final expiry guard fails the otherwise-valid expired-admission test; removing exact assignment comparison fails old-admission/same-person-reclaim test; stale transaction-time defect fails lock-wait probe |

03C3 must account for retained assignments without provable duration/expiry:
no invented lease history, silent unbounded fallback, or deletion. Choose and
review an explicit migration prerequisite/refusal with actionable diagnostics
before implementation. Any retained-data conversion requires separate authority.

## Risk and review routing

- Risk class: L1 (planning for policy, authorization, lifecycle and concurrency).
- Required reviewers: architecture/security/reuse; QA/product_ops/documentation.
- Human review focus: skip and expiry behavior, frozen duration, same-person
  reclaim, clear history, and duration/default bounds before implementation.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| No existing contributor lease | Inspect TASK claim/models/release and PROJECTS policies | Claim/history exist; contributor duration/expiry absent | Policy carrier and numerical bounds require 03C3 design |
| Reuse existing owners | Inspect authorized_commands, assignment_invalidation, submission_composition and Celery workers | Existing authority, lineage and job owners identified | Future race/worker tests must execute |
| Planning consistency | Markdown links, Commitrail validation, stale wording scan and focused plan review | Record exact results in PR | No runtime implementation claimed |

## Review findings

Plan review must test expired active-row submission, same-person reclaim,
processing across expiry, transaction-time skew and post-submit preservation.

## Reconciliation

- Current-source reconciliation: merged #432's authority and immutable release
  receipts remain complete; this adds human-requested task lease/skip behavior.
- Next usable boundary: ARCH-03C2, then reviewed lease/skip owner children before
  public task completion. This plan does not authorize starting another chunk.
- Remaining risks: policy carrier/default/bounds and retained-data prerequisites
  must be resolved in 03C3; real implementation and concurrency evidence pending.
