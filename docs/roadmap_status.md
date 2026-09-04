# Workstream v0.1 Roadmap And Capability Status

This is the public, human-readable source for what Workstream can do on
`main`, what is implemented but intentionally hidden, what we are building
next, and what remains before v0.1 is ready. It uses capability milestones,
not calendar promises.

Implementation claims require merged code, migrations, tests, and review
evidence. A plan or open pull request is not implemented behavior. Open pull
requests are the transient view of work currently under review.

## Product Goal

Workstream turns governed work into trusted `ContributionRecord` facts:

```text
Project Guide
-> governed Task
-> immutable Submission
-> deterministic Checks
-> authorized Review
-> controlled Revision when required
-> Contribution Records
-> conditional Compensation Awards and Fulfillment
-> evidence for a future Reputation projection
```

The v0.1 release bar is one secured, observable, recoverable end-to-end path.
Marketplace expansion, blockchain settlement, external source adapters,
automated routing, agent workspaces, and runtime reputation projection remain
outside v0.1.

## Status Vocabulary

| Status | Meaning |
| --- | --- |
| **Live foundation** | Merged behavior is available to its intended caller. It may still be only one part of a larger product flow. |
| **Hidden and proven** | Merged behavior exists and is tested, but no public production route exposes the complete flow yet. |
| **Next** | The next dependency-safe implementation boundary after current `main`. |
| **Planned** | The design direction is accepted, but its current skeleton must be refreshed into a bounded executable contract before coding. |
| **Deferred** | Deliberately outside the v0.1 runtime. |

## Executive Snapshot

Workstream already has strong backend foundations for identity, authorization,
projects, guide ingestion, immutable artifact storage, tasks, submissions, and
checker execution. The new unified Project Guide compiler and its two
deterministic projections are implemented behind hidden boundaries. The
contributor artifact path can prepare verified bytes, publish a ready
admission, create the immutable Submission, and bind it atomically, but its
public legacy cutover is intentionally deferred.

The current critical path is to finish one complete governed Project Guide
generation, lock its ContributionPolicyVersion into claimable work, and carry
one admitted Submission through a durable current post-submit checker result
with `routing_recommendation = allow_review`. That fact unlocks the live
review/revision path. Review decisions must then create contribution and
conditional compensation facts atomically before v0.1 can be released.

## End-To-End Lifecycle Scoreboard

| Lifecycle stage | Status on `main` | What is already proven | What remains before v0.1 |
| --- | --- | --- | --- |
| Identity and actor resolution | **Live foundation** | Flow-token verification; canonical ActorProfile and ActorIdentityLink; human/service separation; lifecycle controls | Final end-to-end operational and conformance proof |
| Authorization kernel | **Live foundation** | Closed action/permission catalogues; deny-by-default evaluation; grants; fixed services; rate controls; opaque transaction-bound PREP; atomic decision evidence | Activate only the remaining owner-proven TASK, checker, REV, and CON boundaries; remove obsolete authority after replacement paths are live |
| Project Guide source custody | **Live foundation** | Project Manager ingestion; immutable snapshots; verified binding and reads; PDF, DOCX, PPTX, XLSX and image handling; bounded extraction | Complete the unified-generation cutover and later remove remaining legacy inference paths |
| Unified Project Guide compilation | **Hidden and proven** | One immutable model attempt; persisted complete result; crash/recovery custody; deterministic sufficiency and submission-artifact-policy projections; exact AUTH request/execute/projection adapters | Finalize the setup ledger, activate finalization authority, cut live execution over, add approval and deterministic post-submit projection, expose one checker-service port |
| Contribution policy administration | **Hidden and proven** | Finance Authority adapter-binding lifecycle; ContributionPolicy read/create/update/publish/retire behavior; immutable operation and event history | Activate the five policy actions, expose validation, bind one published complete version to the active guide generation |
| Task readiness and claim | **Foundation plus planned replacement** | Task records, lifecycle guards, assignments, locked work context, public owner facts | A task must inherit the guide-bound ContributionPolicyVersion before `READY`; claim copies the prepared task context into TaskAssignment without a current-policy lookup; activate exact task authority |
| Contributor artifact preparation | **Hidden and proven** | One outer ZIP; bounded scratch inspection; canonical manifest; platform and project prechecks; unchanged-work rejection; durable put intent; verification; capacity-charged ready admission | Connect only the active unified guide/checker lineage and complete the later public admission-only cutover |
| Immutable Submission creation | **Hidden and proven** | Contributor preparation authority; atomic admission consumption; TASK-owned Submission creation; fixed-service artifact binding; replay/concurrency/rollback proof | Stamp the assignment's exact ContributionPolicyVersion and unified policy lineage; remove the legacy Submission path only after remediation and review prerequisites are ready |
| Post-submit checking and `allow_review` | **Planned; immediate integration milestone** | Checker contracts, registry/runner foundations, existing pre-review behavior, artifact materialization foundations | Publish one CHECKER post-submit API; materialize the exact Submission; persist one durable current superseding result; activate fixed services; automatically dispatch it and publish the canonical `allow_review` manifest |
| Review queue and lease | **Hidden persistence foundation** | Queue/admission idempotency and ReviewLease/preference persistence; complete unavailable REV action/principal catalogue and typed AUTH contracts | Packet-membership contract and manifest; Review schema; canonical admission from `allow_review`; claim/lease/packet authority; lease copies the Submission-stamped policy version with no CON lookup |
| Review decision and revision | **Planned** | Review/revision policy identities and mutation authority; approved same-task revision-rebase semantics | Immutable findings and decisions; `accept`, `needs_revision`, and `reject`; complete-context revision preparation; finding responses; replacement contributor rules; replay and recovery |
| Contribution and compensation truth | **Schema foundations plus hidden policy behavior** | ContributionPolicyVersion persistence; lifecycle-audit participant; adapter bindings; hidden policy administration | Persist ContributionRecord and CompensationAward; atomically create one reviewer record for every final review and, on accept only, FinalAcceptance plus the submitter record; evaluate frozen rules into zero, one, or two awards |
| Fulfillment, reconciliation, and audit | **Planned** | Shared audit foundations and provider-neutral adapter convention | Outbox/dispatcher authority, conditional award fulfillment, callbacks, idempotent recovery, reconciliation, bounded operational reads, and release controls |
| Frontend and pilot | **Planned after stable backend contracts** | React + Vite + TypeScript stack decision | Implement only stable backed surfaces, run the real internal pilot, repair findings, and complete release drills |

## What Has Been Completed

### Security and platform foundations

- FastAPI, SQLAlchemy 2.x async, PostgreSQL, Alembic, Celery, and Redis form the
  locked backend execution stack.
- The schema has one clean v0.1 Alembic baseline; later bounded migrations
  extend it without compatibility bridges for discarded pre-v0.1 history.
- AWS S3 is the hosted artifact target, MinIO proves the storage protocol in
  development and CI, and all storage access stays behind `ArtifactStore`.
- Private extraction scratch is bounded by `ArtifactScratchManager`; it is not
  durable artifact storage.
- Cross-module behavior is moving through explicit public ports under the
  modular-monolith boundary. New private edges are prohibited and touched debt
  is reduced incrementally.
- GitHub CI distributes the backend suite across semantic lanes, rejects
  skipped/deselected tests, preserves global coverage, and requires at least
  90 percent coverage for new or materially changed backend subsystems.

### Identity and authorization

- Workstream verifies external Flow identity tokens but owns no login,
  password, or primary authentication session.
- External subject identity resolves through ActorIdentityLink into a stable
  internal ActorProfile.
- Human roles and fixed-service authority remain separate and fail closed.
- Project and administrative grants, resource guards, lifecycle revalidation,
  idempotency, rate controls, audit evidence, and opaque prepared authority are
  implemented.
- Guide ingestion, guide binding/read, artifact verification/recovery,
  contributor preparation, Submission consumption/binding, unified compilation
  request/execute, and deterministic projection authority are implemented at
  their current hidden or live boundaries.

### Project Guide and artifact pipeline

- Project Managers can authorize guide-source ingestion for projects they are
  permitted to manage.
- Original bytes are immutable and verified before binding. Classification and
  extraction occur asynchronously from stored bytes; extracted content never
  replaces the original artifact.
- The unified compiler produces sufficiency, submission artifact, pre-submit,
  and post-submit proposals in one accepted result. The sufficiency and
  submission-artifact-policy components now project deterministically without
  another model call.
- Contributor ZIP preparation uses one verified byte lineage from scratch
  inspection through durable admission and eventual Submission binding.

### Contribution and review foundations

- Finance Authority can manage compensation adapter bindings through the
  hidden, authorized boundary.
- Complete hidden ContributionPolicy draft/publication/retirement behavior is
  persisted with immutable lifecycle history; its AUTH actions intentionally
  remain unavailable until the activation gate.
- REV queue/admission and lease/preference persistence foundations are merged.
- The governing rule is fixed: one ContributionPolicyVersion contains both the
  `accepted_submission` and `completed_review` rules. It is bound before task
  readiness and carried as immutable attempt lineage.

## Current Work And Immediate Order

Only open pull requests describe transient work. Use the repository's
[open pull-request view](https://github.com/Flow-Research/workstream/pulls) to
see whether any item below is already under review.

The next dependency-safe product sequence is:

1. **Finish the hidden unified-guide generation.** Implement POL finalization,
   then its exact AUTH finalization gate, followed by the live unified
   compilation cutover. This completes one stored setup result without
   reviving the three legacy inference calls.
2. **Complete guide policy approval.** Project Manager approval consumes the
   already-produced unified result; it does not run another agent. Persist the
   effective pre-submit policy and deterministic post-submit policy, activate
   their narrow AUTH gates, and expose one typed checker-service port.
3. **Activate and bind ContributionPolicy.** Activate only the five proven
   hidden policy actions, expose CON validation, and bind one exact published,
   complete, binding-valid ContributionPolicyVersion to the Project Guide.
4. **Activate the complete guide generation.** AUTH may permit terminal guide
   activation only when compilation, sufficiency, pre-submit policy,
   post-submit policy, review policy, revision policy, and ContributionPolicy
   all belong to the same approved current generation.
5. **Make tasks claimable from that generation.** TASK locks the complete guide
   and policy context before `READY`. Claim copies it to TaskAssignment; it
   performs no ContributionPolicy selection. Submission later copies the
   assignment's attempt version.
6. **Produce canonical `allow_review`.** Materialize the exact immutable
   Submission, execute the locked post-submit plan, persist one current result,
   activate only its fixed services, and automatically publish an exact
   `allow_review` manifest when no blocking failure exists.
7. **Start the live REV path.** Complete packet, Review, and FinalAcceptance
   persistence; admit only canonical `allow_review`; claim a bounded lease and
   exact packet using the Submission-stamped ContributionPolicyVersion.
8. **Make review decisions economically complete.** Before the first live
   Review commit, persist ContributionRecord/CompensationAward and install the
   atomic CON participant. Every final decision records reviewer work; accept
   additionally records accepted submitter work.
9. **Complete revision and operations.** Preserve old attempts immutably;
   rebase a continuing TaskAssignment only at the controlled human-revision
   boundary when the complete governed context changed. Finish recovery,
   fulfillment, reconciliation, audit, release controls, and legacy cleanup.
10. **Release proof.** Expose stable APIs and frontend surfaces, exercise the
    complete path through real database, durable-job, storage, security, failure,
    and recovery tests, then run the internal pilot.

## Critical Dependency Map

```text
Hidden unified compilation and projections (complete)
  -> setup finalization
  -> AUTH finalization gate
  -> live unified compilation cutover
  -> Project Manager approval + effective pre-submit policy
  -> deterministic post-submit policy + single checker port

Hidden ContributionPolicy behavior (complete)
  -> AUTH policy activation
  -> CON validation
  -> Project Guide policy-version binding

Both chains
  -> terminal Project Guide activation
  -> Task readiness and assignment lineage
  -> immutable admitted Submission
  -> durable current post-submit result
  -> canonical allow_review
  -> REV admission, lease, packet, decision and revision
  -> atomic ContributionRecord / CompensationAward effects
  -> fulfillment, reconciliation and release proof
```

No claim-time policy selection exists. A normal task claim copies the version
already locked on the ready task. Review claim copies the version stamped on
the admitted Submission. During `needs_revision`, the continuing assignment
may rebase only after comparing and atomically preparing the complete newer
governed context; earlier Submission, ReviewLease, Review, ContributionRecord,
and award history never changes.

## Remaining Release Gates

v0.1 is not ready until all of the following are true:

- One active Project Guide generation contains a complete approved compilation
  and every required policy identity/hash, including ContributionPolicyVersion.
- A task cannot enter `READY` without that complete locked context.
- A contributor can claim, submit one immutable ZIP, pass both checker phases,
  and receive a durable ready admission without a parallel legacy path.
- The immutable Submission automatically reaches exactly one current
  post-submit result and an exact `allow_review` manifest when eligible.
- A reviewer can claim only that admitted version, access only its bounded
  packet, and record one immutable final decision.
- `needs_revision` safely continues or rebases the same assignment while
  preserving every earlier attempt; `reject` and `accept` have their exact
  distinct effects.
- Every final review atomically creates the reviewer ContributionRecord;
  `accept` additionally creates FinalAcceptance and the submitter record.
- Frozen policy rules produce zero, one, or two CompensationAwards without
  controlling Workstream lifecycle truth.
- Fulfillment and recovery are idempotent, observable, reconcilable, and safe
  under durable-job, provider, transaction, and unknown-commit failures.
- Public APIs and frontend surfaces expose only the canonical paths, obsolete
  authority and legacy routes are removed, and the full security/operations
  drill plus internal pilot passes without weakening safeguards.

## Trace References

Internal chunk identifiers are useful for implementation traceability, but a
reader does not need `.agent-loop` to understand the roadmap above. The main
remaining trace sequence is:

- Unified guide: `POL-04A2 -> AUTH-12B2 -> POL-04B -> POL-05A -> AUTH-12F4
  -> POL-05B -> POL-06A -> AUTH-12G -> POL-06B -> POL-07 -> AUTH-12H`.
- Contribution lineage: `CP05 -> CP06 -> CP07 -> CP08 -> ARCH-03A -> ARCH-03B
  -> ARCH-03C -> CP09`.
- Post-submit admission: `ARCH-04A -> 04B -> 04C -> 04D -> 04E`; `04F` is the
  contributor-remediation prerequisite for the later public Submission cutover.
- Review/revision: REV packet/schema foundations may proceed independently,
  but live admission starts after `ARCH-04E`; the first live Review commit also
  requires CON contribution/award persistence and its atomic decision participant.

For implementation ownership and exact contracts, contributors can follow
[Current Engineering State](../.agent-loop/CURRENT_STATE.md). For historical
decisions, use the [Historical Planning Index](historical_planning.md).
