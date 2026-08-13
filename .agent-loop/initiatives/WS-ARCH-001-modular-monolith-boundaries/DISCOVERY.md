# Discovery: WS-ARCH-001 Modular Monolith Boundaries

## Current module set

Business modules:

| Module | Durable ownership |
|---|---|
| `actors` | actor profiles, external identity links, fixed service identities |
| `authorization` | actions, permissions, grants, prepared capabilities, decisions and evidence |
| `projects` | projects, guides, guide compilation, locked project policies and setup generations |
| `tasks` | tasks, assignments, claims, immutable Submissions and predecessor chains |
| `artifacts` | byte identity, archive safety, manifests, storage, verification, admissions, bindings and materialization |
| `checkers` | checker plans at execution time, runs, results and blocking outcomes |
| `reviews` | queue, reviewer lease, exact packet reference, decision and note/findings |
| `contributions` | trusted ContributionRecord facts and accepted-work provenance |
| `compensation` | conditional awards and fulfillment status |

Supporting modules are `audit` for append-only evidence, `outbox` for reliable
event delivery, and `api_controls` for API operational controls.

Submission is part of `tasks`. A revision is another immutable Submission
created after a `reviews` `needs_revision` decision. POL is an initiative and
capability family; guide compilation and locked policy custody remain in
`projects`, while checker execution remains in `checkers`.

## Existing public surfaces

`backend/app/modules/authorization/api/` provides the first explicit module
public API. PRs #304 and #305 established its minimal surface, exact
private-import ledger, and no-new-AUTH-violation gate. PR #307 subsequently
merged the first capability proof: hidden project-guide compilation uses the
public AUTH surface without adding private AUTH debt. PR #310 added the
repository-wide registry, exact general debt ledger, and protected-base gate.

## Observed cross-module topology

An AST inventory on `main` at `3c260e20` found private runtime edges in both
directions. Material examples include:

- `artifacts` imports private `authorization`, `tasks`, `projects`, `actors`,
  `checkers`, and `audit` modules;
- `tasks` imports private `artifacts`, `authorization`, `projects`, `checkers`,
  `actors`, and `audit` modules;
- `projects` imports private `authorization`, `artifacts`, `checkers`,
  `actors`, and `api_controls` modules;
- `authorization` imports private `actors`, `audit`, and `projects` modules;
- `checkers` imports private `artifacts`, `projects`, and `tasks` modules.

The exact AUTH subset is frozen in
`WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md`. Its validator passes
because current debt is recorded; it does not mean the imports are clean.

## Concrete ART risk

`artifacts/submission_admission.py` imports AUTH's private prepared handle and
TASK's private pre-submit context. Other ART files import private PROJECT,
TASK, CHECKER, ACTOR, and AUTH models or services. Discovery also found that
the earlier ART-05A wording assigned immutable Submission creation to ART even
though `tasks` owns the Submission lifecycle. This planning change resolves
that conflict by superseding ART-05A as executable authority until
WS-ARCH-001-02 produces split, ownership-correct contracts.

## Submission-path reconciliation after PR #310

The hidden preparation route is TASK-delivered but imports private ART request,
error, and command types. Application adapter wiring imports ART concrete
implementations. ART's `submission_admission.py` imports TASK's private
`pre_submit_context` and CHECKER private catalogue/execution types. TASK's
`pre_submit_context.py` in turn reads ACTOR and PROJECT ORM rows and compiles a
CHECKER-owned effective plan.

Therefore the earlier four-part AUTH/ART/TASK/composition description is
incomplete. Activating that shape would preserve circular authority and move
PROJECT/CHECKER behavior behind a TASK facade. The ownership-correct graph is:

```text
AUTH -> actor/identity/grant decision and opaque prepared authority
TASKS -> task, assignment, predecessor and Submission lifecycle facts
PROJECTS -> locked guide and project-policy lineage facts
CHECKERS -> effective pre-submit plan and bounded execution-result facts
ART -> ZIP custody, manifest, verified admission, consumption and binding
application composition -> transaction-bound concrete wiring only
```

No public capability may return an ORM row, repository, session, mutable policy
body, scratch path, provider credential, or another module's private type.
Preparation activation must wait until the TASKS, PROJECTS, CHECKERS, ART, and
AUTH public contracts it exercises are present and the corresponding private
edges are removed.

## Conventions to preserve

- The target module exposes immutable facts, commands/results, stable errors,
  opaque capabilities, and Protocol ports under `app.modules.<name>.api`.
- Public APIs expose no ORM models, repository, session, concrete service,
  provider client, or another module's private type.
- The application composition root wires concrete implementations.
- Alembic metadata discovery may import model packages solely for metadata; it
  is not a product-runtime API.
- `WS-AUTH-003` remains authoritative for AUTH-specific internal recovery;
  this initiative generalizes the cross-module rule without duplicating AUTH.

## Test and tooling evidence

- `backend/scripts/authorization_boundary.py` validates AUTH inbound/outbound
  debt.
- `backend/tests/architecture/test_authorization_boundary.py` protects the
  AUTH public surface.
- `backend/scripts/behavior_ownership.py` and `.ci/behavior-ownership/` protect
  behavior ownership, not general runtime import direction.
- PR #310 installed the repository-wide module registry, exact private-edge
  ledger, public API leak/cycle checks, and protected-base validator that govern
  every split contract below.

## Resolved sequencing constraints for submission capability

- Preparation and admission consumption are distinct authorization boundaries.
- Public fact/port foundations may merge while behavior remains hidden and
  deny-only.
- The contributor preparation action activates only after the hidden path uses
  public capabilities end to end.
- ART admission/binding and TASK Submission mutations may be implemented behind
  public ports before the route cutover, but their composed transaction must be
  proven before fixed-service activation or public reachability.
- The public cutover removes legacy package URI/hash/manifest input and the
  standalone precheck path in the same PR; no dual path or compatibility alias
  is permitted.

## Unknowns to resolve per capability

- Which exact owner-local lock/fact methods each implementation chunk can reuse
  without widening its public contract?
- Which exact immutable facts are sufficient without exposing an ORM row?
- Which legacy edges can be removed in the same feature chunk without changing
  behavior?
- Which next migration identifier is free on then-current `main`?

## Post-02B repository housekeeping

PRs #314 and #315 merged the TASKS and PROJECTS public capability foundations.
The PROJECTS change also extracted locked-policy persistence from the legacy
repository into `projects/locked_policy_repository.py`; this is the intended
capability-sized recovery pattern rather than a repository-wide rewrite.

The post-merge inventory confirms that large legacy production and test
containers remain, including `projects/service.py`, `artifacts/service.py`,
`tests/test_projects.py`, and `tests/test_authorization.py`. Their size is
evidence of frozen structural debt, not permission for a bulk split. Each
executable capability chunk must extract the behavior and tests it touches,
preserve old-to-new assertion coverage where required, and leave unrelated
containers unchanged.

Local worktree state is operational rather than repository authority. At the
post-02B audit, dirty worktrees existed for CON lifecycle evidence,
pre-start-assurance planning, and QUAL test-structure planning. They must not
be removed or overwritten. Dead temporary registrations and clean merged
worktrees may be pruned only after confirming no process owns them, their HEAD
is contained in `origin/main`, and they contain no uncommitted or unique work.

## Current-main reconciliation after 02H

PR #328 merged the hidden AUTH/TASK/ART consumption transaction. Human
Submission creation and fixed-service binding are now authorized, replay-safe,
and atomic, but the public route remains legacy. The existing checker subsystem
can persist `allow_review`; that result is attached to the legacy pre-review
workflow and does not prove the new admission-backed path is review-ready.

The current plans incorrectly compress three different outcomes into parents
03/04/05: project/task readiness, canonical post-submit checker completion, and
later reviewer/revision behavior. The corrected dependency is:

```text
complete unified guide compilation and approval
-> current task/assignment authority
-> merged 02H hidden Submission transaction
-> exact post-submit materialization and checker output
-> durable current allow_review manifest
-> REV admission
-> later review/revision and public 02I clean cut
```

PR #329 is the open planning reconciliation for this boundary. No open
implementation pull request owns the executable sequence; the owner skeletons
remain non-executable until refreshed against current `main`.
