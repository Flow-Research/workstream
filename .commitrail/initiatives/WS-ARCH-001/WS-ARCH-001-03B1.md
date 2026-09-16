# ARCH-03B1 — Detach TASK project and guide display context

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: TaskService consumes immutable PROJECTS-owned display facts through the existing guide-context port, removing its private PROJECTS model and repository dependencies.

## Intent

Keep the project and exact guide shown to a contributor connected to the same
validated guide used by their task. Complete the remaining metadata boundary
before adding the broader task queues and actor-specific projections.

## Current behavior

Main at merged CP08 (`d2416a44`) stamps exact contribution lineage. TASK's
`TaskService._load_locked_task_context` first obtains validated PROJECTS facts,
then independently loads private `Project` and `ProjectGuide` ORM objects for
display. `LockedTaskContext` retains those objects. Draft creation also directly
loads `ProjectRepository`. These are the three remaining private PROJECTS
imports in TASK service, not additional policy-selection owners.

The adopted 03B skeleton also contains completed CP08 acceptance criteria and
an assignment-invalidation handler requiring an unimplemented committed outbox
claim contract. Existing OUTBOX supplies append only. The bounded sequence is
03B1 metadata cutover, remaining 03B queues/projections, then assignment
invalidation after AUTH-OUTBOX-01 and CON-02B. ARCH-03C retains exact authority,
originating invalidation-event append and public activation.

## Bounded change

### Allowed

- `backend/app/modules/projects/api/locked_policy.py` and `api/__init__.py`:
  immutable project/guide display facts and the existing port's project lookup.
- `backend/app/modules/projects/locked_policy_{repository,projection}.py`:
  build those facts from exact PROJECTS-owned rows under the existing transaction.
- `backend/app/modules/tasks/service.py`: replace the private project lookup and
  ORM-valued context; remove all superseded imports/fields/calls together.
- Existing affected composition or fixtures only where required by the changed
  port. Focused PROJECTS context and TASK HTTP/read tests, including
  `backend/tests/test_tasks.py`, new `backend/tests/tasks/test_project_display.py`,
  and existing `backend/tests/projects/test_locked_policy_*.py` and their fixtures.
  Register new tests in the existing exact lane catalogue if needed.
- Existing module-boundary machine/human ledgers: remove only retired edges;
  no new debt, raised thresholds or exemptions.
- This record, adopted 03B skeleton and dependency map, current initiative
  navigation, README, architecture/operating docs and roadmap where affected.

### Not allowed

No new route, permission, authorization decision, queue, assignment invalidation
handler, dispatcher, lineage writer, policy selection, checker execution,
migration, economic-schema deletion or compatibility implementation. Preserve
existing HTTP field contracts, separate contributor/manager authority, lock
order, no-flush/no-commit context reads and retained data. Migration head stays
`0024_task_policy_lineage`.

## Design and decisions

Extend the existing PROJECTS context port, not a second guide resolver.
The complete context includes required immutable display values for the exact
project and guide already validated by the owner. Their identities must match
the existing context and activation receipt. Descriptive project metadata is
current display data, not a new policy hash or immutable business-policy input.
Guide metadata is from the selected historical guide, never the current guide.
The implementation uses one frozen `ProjectDisplayFacts` (id, name, slug, description) for draft
lookup and complete context, plus frozen `GuideDisplayFacts` (id, project_id,
version, change_summary, effective_at) for complete context. Their UUID identity,
guide version and guide effective time must match the validated activation
context. Specifically project.id equals context.project_id;
guide.(project_id, id, version) equals the receipt-bound context tuple;
guide.effective_at equals activation_receipt.effective_at. Use only scalar strings, UUIDs and datetimes; no ORM/session objects.

Draft creation needs only project existence, not an activated guide. Use the
bounded project-metadata lookup to this same port that returns a detached
project value or absence. It must not acquire a new lock or require readiness,
and must not flush/commit the caller's work. Name the method
`read_project_display(project_id: UUID) -> ProjectDisplayFacts | None`. It may
be the first DB operation: do not reuse `_resolve`'s pre-existing-root-transaction
or active-project guard. Malformed project-ID strings map to the existing
`TaskProjectNotReady` error after current authorization checks. TASK retains its current validation
and authorization order. This avoids making draft creation depend on a guide
that the project manager has not yet configured.

## Acceptance criteria

- TASK service has no private PROJECTS model or repository import, constructor
  or ORM-valued display field; superseded paths are removed, not renamed.
- Public context facts reject wrong-project or wrong-guide display identity;
  matching values are detached and immutable.
- A draft task can still be created before guide activation; missing projects
  deny without task/audit writes.
- Contributor and manager work-context responses preserve their field shapes,
  authorization and exact historical guide metadata after a successor activates.
- Metadata reads neither flush pending writes nor commit and do not add a lock
  inversion. Existing policy receipt/hash substitution checks remain intact.
- Boundary debt shrinks, current documentation distinguishes 03B1 from remaining
  queues/invalidation and public AUTH activation, and all applicable checks pass.

## Risk and review routing

- Risk class: L1 (owner boundary and contributor-visible context).
- Required reviewers: architecture/reuse, security, QA/test delta,
  documentation/product operations, CI integrity. Senior engineering review of
  the bounded design can be combined with architecture.
- Human review focus: exact guide identity, no false claim that queues or
  assignment recovery are delivered, and no changed authorization or policy hash.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current owner/dependency trace | Inspect TASK context/service, PROJECTS context port, OUTBOX exports | Private display reads and append-only outbox confirmed | Plan findings reconciled before code |
| Nested display identity and immutability | `test_context_display_identity_and_immutability`: real activated context, positive replacement; independently replace nested project.id and guide.project_id/id/version/effective_at while original top-level receipt stays intact; frozen mutation rejects | Regression implemented | Exact execution evidence in PR |
| Existence-only draft lookup | `test_project_display_lookup_preserves_draft_and_transaction`: real PostgreSQL draft Project without Guide, missing UUID; pending invalid object remains unflushed; flushed uncommitted marker disappears on rollback | Regression implemented | Exact execution evidence in PR |
| No new Project lock | `test_project_display_lookup_does_not_wait_for_project_lock`: session A holds Project FOR UPDATE; bounded session B metadata read completes before A releases | Regression implemented | Exact execution evidence in PR |
| Draft create/absence/error order | `test_task_creation_before_guide_and_missing_project_atomicity`: HTTP valid draft create then missing/malformed project IDs, unauthorized malformed request; Task/Audit counts unchanged on denial | Regression implemented | Exact execution evidence in PR |
| Exact historical public display | `test_task_display_survives_guide_successor_for_contributor_and_manager`: activate first guide, create/screen/claim task, then activate distinct successor; both authorized routes return predecessor id/version/summary/effective_at and existing exact response keys; foreign scope denies | Narrower predecessor test replaced; requirements assertions retained | Exact execution evidence in PR |
| No gate or boundary weakening | Ruff; module/authorization/structure validators; exact lane equality; stale wording; markdown links; hosted full tests/coverage | Required checks preserved | Exact execution evidence in PR |

## Review findings

Architecture review narrowed the cleanup claim to TaskService. The unchanged
private `ProjectGuide` import in `tasks/pre_submit_context.py` remains an explicit
later AUTH/public-intake consumer; this change does not claim all TASK private
PROJECTS edges are retired. The draft lookup's first-read and inactive-project
semantics are preserved, distinct from activated-context readiness.

Plan discovery found that the old 03B skeleton requires a committed outbox claim
that does not exist and repeats CP08 writers. Keep completed lineage out of
03B implementation and order invalidation after its actual shared owner.
Actor-wide invalidation also needs explicit per-project TASK event fan-out under
the existing project-scoped outbox; no arbitrary project or shared TASK/REV
acknowledgement may be invented by the later handler contract.
Security/QA review required the independent nested substitutions and exact
transaction/HTTP proof names above; existing top-level receipt tests alone do
not prove the new nested display boundary.

## Reconciliation

- Current-source reconciliation: CP08 is merged; consume its complete frozen
  context and preserve its claim/revocation ordering.
- Next usable boundary: remaining 03B queues and actor-specific projections;
  assignment invalidation follows shared claim-contract delivery, before 03C
  integrated activation.
- Remaining risks: no live queue/invalidation/public activation is claimed by
  this bounded metadata cutover.
