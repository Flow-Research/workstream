# WS-ARCH-001-CP06 — Validate an explicitly selected ContributionPolicy

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: expose CON-owned, caller-transaction validation of an
  exact ContributionPolicy version for new guide binding and later controlled
  revision adoption, without activating a guide or changing frozen work.

## Intent

After unified guide setup and separate pre/post approvals, PROJECTS needs to
validate the explicitly chosen contribution/compensation policy before binding
it. CP06 supplies that dependency; CP07 owns guide binding and AUTH-12H supplies
activation authority. This is internal validation, not a public policy route,
policy selection algorithm, authorization grant or compatibility path.

## Current behavior

Main `bbaec878` includes POL-07B. CON publication already locks the PROJECTS
project, project-scope advisory fence, policy aggregate, exact versions, rules,
definitions, units and adapter bindings. Publication retires the prior version;
its immutable graph remains retained. The authorized read's optional-version
selection also serves draft inspection and is not activation validation.
The adopted CP06 skeleton is design input, not an executable plan.

## Bounded change

### Allowed

- `contributions/api/` explicit selection, validation facts and typed port;
  CON-owned validation implementation and existing repository reads/locks,
  including refresh of preloaded graph/unit rows when acquiring their locks.
- Extract and reuse publication's graph/resource eligibility checks within CON;
  update publication to use the same checks rather than add a second validator.
- `adapters/contributions/__init__.py` explicit caller-session composition using
  existing PROJECTS and COMPENSATION ports.
- Remove the redundant CON alias for PROJECTS eligibility; update its affected
  CON callers to import the canonical PROJECTS contract directly.
- Focused CON contract/PostgreSQL/concurrency tests and exact test-lane, public
  contract and behavior-ownership inventories (including exact-addition proof);
  current specs, README, roadmap, initiative navigation and this adopted contract.

### Not allowed

No migration, guide/Task/Assignment/Submission/ReviewLease write, public route,
new AUTH action/evaluator, economic execution, compiler, provider, worker,
compatibility alias or fallback implementation. No change to publication or
retirement authorization, transition evidence, or existing attempt lineage.
No CI workflow or gate relaxation; retry-artifact changes arrive unchanged
from main through merged PR #408.

## Design and decisions

- Require explicit UUID project/policy/version identifiers and a closed typed
  validation purpose. Missing IDs never select current/latest/draft state.
- Require a caller-owned root transaction. Retain locks through the caller's
  commit/rollback; never begin, commit, roll back or write product rows here.
- Match existing lock ordering: PROJECTS project first, CON project-scope fence,
  policy aggregate, exact version, rules/definitions, sorted units and bindings.
  Do not acquire a policy lock before asking PROJECTS to lock its project.
- New guide activation requires an active aggregate and exact equality between
  the requested version and its current published selector, then complete
  same-project graph and active eligible units/bindings. Stale selectors fail.
- Controlled revision adoption validates only the exact version supplied from
  the caller's locked newly active complete guide context. A subsequently
  advanced selector does not replace that bound version; published or retired
  immutable versions remain readable. Changed-context adoption revalidates
  present unit/binding eligibility. Unchanged attempts make no validation call.
  CON does not own or attest guide completeness, task rebase or authorization;
  those runtime proofs belong to CP07 and later TASK/REV integration. Those
  compositions must reject use of revision-purpose facts for a new binding
  and obtain revision identifiers from locked guide custody, not caller choice.
- Refresh locked unit/rule/definition rows, matching existing policy/version
  and binding reads. A stale caller identity map must not preserve old active
  eligibility after a concurrent resource change.
- Return immutable canonical identity and graph/binding facts, not ORM rows or
  authority. Preserve public owner direction; CP07 must inject its dependency
  through PROJECTS' local contract and composition, not create a CON/PROJECTS
  import cycle or CON callback into guide activation.
- Keep authorized policy read's existing draft/version selection: it is a
  distinct current inspection use case. New binding never calls that selector.

## Acceptance criteria

- Exact eligible activation selection returns canonical facts. Missing, foreign,
  stale, draft, incomplete or invalid resource selections fail closed without
  substituting another version, disclosing rows or changing data.
- Both unpaid and compensated actor rules use one canonical complete-graph
  validator shared with publication. Both actor rules are required.
- Revision-purpose validation preserves the supplied historically published
  version after later publication/retirement while checking current binding
  eligibility; new activation rejects that same stale version. No test claims
  a complete guide/revision workflow before its owners exist.
- Root transaction only; denial/late caller rollback leaves caller effects and
  policy state atomic, and locks remain held until transaction end.
- Real PostgreSQL interleavings cover activation validation versus publication
  and retirement in both orderings, and resource suspension fencing. Tests
  must reach the target guard and include valid controls; deliberate removal
  of selector equality must be detected by a contract-level regression with
  an otherwise-published requested version (a retired version alone would hit
  a different guard). Real PostgreSQL preloaded rule/definition fixtures must
  refresh after supported draft edits and publication; current unit retirement
  is database-blocked, so no test may bypass that guard to manufacture a race.
- Preserve publication/retirement regression coverage, current authority and
  immutable evidence. Run relevant lint, boundaries, test inventory, links and
  stale wording checks; final hosted lanes and coverage floors remain required.

## Risk and review routing

- Risk class: L1 (policy eligibility and concurrent database custody).
- Required reviewers: architecture/reuse, security, QA/test-delta,
  documentation/product operations, CI integrity for exact test inventory.
- Human review focus: activation selects only the explicitly expected current
  version; revision adoption cannot silently drift; correct shared lock order;
  no claims of live guide activation, task rebase or economic behavior.

## Evidence

The typed contract tests require exact selection, both actor rules, valid
resources and caller transaction custody. Real PostgreSQL tests exercise
authorized publication/retirement races, resource fences, caller rollback and
stale graph identity-map refresh. Existing publication/authority tests protect the
shared-rule extraction. A selector negative control removes only equality:
the stale-selector test fails while both valid-purpose controls pass.
Database-owned UUID subclasses are normalized for the canonical graph-input
validator; public requests accept UUID instances without accepting strings.
Final exact-head
commands, hosted results and review freshness belong in the PR trust summary.

The initial unit-retirement fixture was infeasible: the database explicitly
keeps that lifecycle unavailable. The replacement proof edits mutable draft
rule/definition rows before authorized publication. Unit lock refresh remains
consistent with all owner reads; no enabled retirement lifecycle is claimed.
The existing publication binding-lock test used a nonexistent column and
accepted any database error. It now uses the actual binding lifecycle column
and requires PostgreSQL lock-timeout `55P03`, not an unrelated SQL error.

## Plan reconciliation

The old skeleton's policy-first wording conflicts with existing project-first
operations. It also conflates a formerly published retired version with a draft
and overstates what a CON-only test can prove about future complete guide/task
adoption. This record narrows those claims and preserves ownership. CP07 remains
next; CP06 does not begin it automatically.

## Cross-owner lock handoff

Before production composition, reconcile the existing AUTH/CON/COMPENSATION
lock order. Source tracing shows role issuance taking AuthorityControl before
Project, while hidden CON publication takes Project before AuthorityControl
and hidden binding suspension takes binding before AuthorityControl. Selected
validation takes Project before binding. These edges can form a cycle; no real
PostgreSQL interleaving of that cycle was executed in CP06. Neither the new
validation port nor the hidden publication/suspension operations has a current
production caller. This is an existing cross-owner availability concern to
resolve before exposing or composing those paths, not proof of a live deadlock
or an authorization bypass. CP06 does not claim to repair it.
