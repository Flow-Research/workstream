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

Only `backend/app/modules/authorization/api/` currently provides an explicit
module public API. PRs #304 and #305 established its minimal surface, exact
private-import ledger, and no-new-AUTH-violation gate. PR #307 subsequently
merged the first capability proof: hidden project-guide compilation uses the
public AUTH surface without adding private AUTH debt.

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
- There is no repository-wide module-public-API ledger or validator yet.

## Unknowns to resolve per capability

- Which module owns the application command when one transaction spans public
  ports?
- Which exact immutable facts are sufficient without exposing an ORM row?
- Which legacy edges can be removed in the same feature chunk without changing
  behavior?
- Which next migration identifier is free on then-current `main`?
