# Plan: WS-ARCH-001 Modular Monolith Boundaries

## Strategy

Use one incremental dependency strangler:

```text
canonical module map
-> exact repository-wide private-edge inventory
-> no-new-edge enforcement
-> expose one real capability through the owner's api package
-> migrate exact consumers and composition wiring
-> remove those ledger edges
-> repeat with product delivery until the ledger is empty
```

## Permanent rules

1. A module owns its facts, mutations, invariants, persistence, and errors.
2. Cross-module runtime imports target only `app.modules.<module>.api`.
3. Public APIs contain immutable facts, commands/results, stable errors,
   opaque capability Protocols, and ports—not implementation.
4. The caller supplies server-owned canonical facts; it never receives the
   target's ORM model or repository.
5. Concrete implementations meet only in the application composition root or
   the exact same-owner `backend/app/adapters/<owner>/__init__.py` composition
   root. That adapter root constructs typed public ports; the exception never
   extends to nested adapter files or cross-owner private imports.
6. The application composition root opens the SQLAlchemy transaction/unit of
   work and constructs transaction-bound public-port implementations. The
   owning application command coordinates those injected ports without
   receiving another module's repository, ORM model, concrete service, or raw
   database session through a public API. Coordination does not transfer
   domain ownership.
7. Existing private edges may remain only while frozen. A changed capability
   must remove its relevant edges and may add none.
8. Tests import another module through its public API except package-local
   white-box tests owned by that module.

## Delivery integration

Boundary repair is not a separate rewrite lane after the foundation. Every
feature contract touching `artifacts`, `authorization`, `projects`, `tasks`,
`checkers`, `reviews`, `contributions`, or `compensation` must state:

- owning module for every new fact and mutation;
- public API additions and exact consumers;
- concrete composition-root wiring;
- protected-base debt edges removed;
- proof that debt does not grow;
- behavior, transaction, authorization, replay, and denial preservation.

## Submission capability correction

Before contributor preparation activation or ART-05A replacement behavior:

- TASKS exposes immutable task, assignment, predecessor, and Submission facts;
- PROJECTS exposes locked guide and project-policy lineage facts;
- CHECKERS exposes effective-plan compilation and bounded execution-result
  facts; ART retains durable evidence identity, persistence, pass capability,
  and admission attachment;
- ART exposes hidden preparation, ready-admission validation/consumption, and
  binding ports;
- AUTH exposes exact preparation and consumption capabilities and activates
  them only after the corresponding hidden behavior is complete;
- the composition root owns the transaction/unit-of-work boundary and invokes
  the TASK-owned application command with transaction-bound AUTH and ART
  public ports while PROJECT/CHECKER facts are already immutable inputs;
- ART does not create or query TASK ORM rows;
- TASKS does not query ART ORM rows;
- TASKS does not become a facade over PROJECT or CHECKER private persistence;
- ART does not compile checker plans or read PROJECT persistence;
- POL-03A now owns merged migration `0062_guide_compilation`; every later
  migration identifier is chosen only after rebasing on then-current `main`.

## WS-ARCH-001-02 delivery order

The former single coordination placeholder is split into these PR boundaries:

1. `02A`: TASKS preparation/Submission immutable fact and port contract.
2. `02B`: PROJECTS locked-policy fact and port contract.
3. `02C`: CHECKERS effective pre-submit plan/bounded execution-result contract.
4. `02D`: ART hidden preparation public API migration using only owner APIs;
   production stays deny-only and proves zero effect plus the exact resource
   manifest, not successful AUTH consumption.
5. `02E`: ART ready-admission consumption and binding public capability.
6. `02F`: TASK-owned immutable Submission command plus composed atomic
   transaction, hidden from the public route; production remains deny-only and
   proves zero effect plus the exact transaction manifest.
7. `02G`: AUTH production activation and positive end-to-end proof of
   contributor preparation.
8. `02H`: AUTH fixed binding/human consumption activation and positive
   concurrency proof against the hidden transaction.
9. `02I`: deferred admission-only public API/dispatch cutover and complete
   legacy precheck/caller-package removal. It may run only after the separate
   checker-remediation and human-review revision context extensions, post-submit
   checker materialization/output visibility and repair, and REV admission
   handoff are merged.

All hidden owner behavior and transaction wiring through 02F must merge before
02G may make contributor preparation live. Each contract is one PR. A
foundation PR may add typed public contracts and
their owner-local implementation/tests but may not activate behavior or modify
the live Submission route unless its contract explicitly owns that boundary.
No later chunk begins merely because an earlier public type exists; its entry
gate requires the named merge and exact resource manifest.

The initial-submission foundations through 02H do not remove the live legacy
Submission path. Before 02I, WS-ARCH-001-03/04/05 must split and deliver the
PROJECT/TASK, CHECKER, and REV public capabilities needed to replace
XINT-002-05C/05D, ART-06A/06B, XINT-06B, and the exact reviewer-admission
handoff. All three contributor contexts then use one admission-backed path:
initial submission, checker remediation, and reviewer-requested revision. A
review note remains REV-owned and relates to the exact predecessor Submission;
the contributor response is a new complete ZIP and immutable Submission.

## PLAN2: canonical Submission-to-allow-review sequence

PLAN2 corrects the post-02H delivery path around one measurable product
milestone. It does not start REV or CON implementation and does not release a
public route.

### Gate 0: complete Project Guide readiness in the owner initiative

The existing WS-POL-003 order remains authoritative:

```text
POL-03B
-> POL-04A -> AUTH-12B2 -> POL-04B
-> POL-05A -> AUTH-12F4 -> POL-05B
-> POL-06A -> AUTH-12G -> POL-06B
-> POL-07 -> AUTH-12H
```

Each POL/AUTH chunk repairs only the public boundary and structural debt it
touches. Completion means one current approved unified generation supplies the
exact active guide plus complete pre-submit and post-submit policy identities
and hashes. POL-08 physical cleanup follows the canonical `allow_review`
milestone so it does not create a circular dependency on the Submission path;
no live call may use the transitional inference paths in the interim.

### Gate 1: current task and assignment authority

Parent 03 is split into 03A-03C. PROJECTS exposes current approved compilation
facts; TASKS exposes claim/assignment and immutable locked-context facts; AUTH
activates only the exact task/assignment actions after both hidden owner paths
exist. A task cannot enter preparation with a stale guide, policy generation,
assignment, contributor, or predecessor.

### Gate 2: canonical post-submit checker completion

Parent 04 is split into 04A-04E. CHECKERS first publishes immutable
post-submit plan/run/result contracts. ART materializes the exact verified
Submission binding. CHECKERS installs hidden owner-local persistence while its
production authority remains fail-closed. AUTH then activates only those exact
fixed-service boundaries. TASKS finally dispatches the now-authorized
execution and projects the current routing fact without owning checker logic.

The acceptance manifest must bind:

- project, task, assignment, contributor and predecessor;
- approved unified guide/setup generation and complete policy hashes;
- Submission id/version and admission id;
- ART binding, content, replica, digest and byte count;
- checker plan, run, result and supersession/currentness identities;
- `routing_recommendation = allow_review`.

Replay, revocation, stale generation, stale assignment, replaced binding,
non-current run, cross-project/resource, wrong service/session/transaction and
concurrent duplicate execution all fail closed. Denial produces no provider
read, checker mutation, TASK transition, REV admission or allowed audit fact.

### Gate 3: REV admission follows the merged manifest

Parent 05 is no longer a prerequisite for *producing* canonical
`allow_review`. It begins only afterward. Its first future split installs the
exact REV admission consumer; packet, lease, claim, decision and revision
remain REV-owned successors. CON remains downstream of REV final acceptance.

### Public cutover remains later

02I remains deferred. It may remove the legacy public Submission path only
after initial, checker-remediation and reviewer-requested revision contexts all
use the admission-backed contract and their checker/REV handoffs are proven.
Canonical hidden `allow_review` is therefore an upstream milestone, not an
implicit public release.

## Verification

- AST import-edge inventory and protected-base comparison.
- Public API dependency/leak/reachability tests.
- AUTH edges remain exclusively recorded by WS-AUTH-003. The general validator
  loads the canonical AUTH ledger through the existing AUTH boundary parser
  and combines its result by reference; it does not copy AUTH edges into a
  second ledger. Tests prove missing, additional, or divergent AUTH/general
  results fail closed.
- Behavior-ownership and test-structure validators remain green.
- Capability-focused unit and PostgreSQL concurrency tests.
- Ruff, stale wording, Markdown links, repository coverage, and hosted lanes.
- Architecture, security, QA, product/ops, senior, reuse, test-delta, CI, and
  docs review for L1 boundary chunks.

## Rejected alternatives

- One repository-wide package move: unreviewable and behaviorally unsafe.
- Let each module invent its own facade: creates inconsistent protocols.
- Put orchestration in ART or AUTH: transfers lifecycle ownership.
- Create a generic shared domain/service locator: hides coupling.
- Preserve the debt ledger permanently: normalizes the architecture failure.
