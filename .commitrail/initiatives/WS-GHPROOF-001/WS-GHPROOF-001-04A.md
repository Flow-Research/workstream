# WS-GHPROOF-001-04A — Checker-owned forge claim selection

- Initiative: `WS-GHPROOF-001`
- Durable disposition: `Planned`
- Intended merge outcome: project images own submission interpretation; shared POST retrieves only scoped forge facts and processes normalized findings.

## Intent

Garden work can originate as Workstream tasks. A project guide defines the
required submission and checker image. Contributors claim, work and submit;
the external checker interprets its proof and evaluates authorized forge facts.
Workstream owns verified bytes, restricted execution and policy-governed outcomes.
Adding another project's submission format must not require shared POST edits.

## Current behavior

`SelectedPostSubmitProcessor._claimed_change_number` opens `proof.json` and
reads `pr_url` before invoking the image. This improperly binds every forge-facts
consumer to Harnessy's format. The existing `ForgeFactsAdapter` already bounds
origin/repository/base branch and keeps credentials outside the offline image.
The image execution contract has no way to return a typed fact selector.

## Bounded change

### Allowed

- CHECKERS external contracts, selected POST processor/evidence/budget; existing
  external execution port, lazy composition and model wrapper delegation.
- Existing Unix-socket adapter, Rust checker SDK/service and their focused tests.
- ART post-submit materialization grant/receipt checks for the same verified callback.
- `external_checkers/harnessy_proof/` parsing, image declarations and tests.
- Affected current checker/forge documentation, roadmap and initiative navigation;
  test registration and generated inventories only as required by changed tests.

### Not allowed

- Project-specific filenames, proof fields or evaluation rules in shared execution.
- Checker internet access, credentials inside images, arbitrary URL fetching,
  new public routes, automatic GitHub issue import, or acceptance changes.
- Model/trial execution during claim selection; unbounded rounds or generic agent
  tool frameworks; a compatibility parser or fallback to the removed core path.
- Rewriting retained evidence, broad data cleanup, TUI or human-review expansion.

## Design and decisions

Use a bounded two-pass invocation only for a locked binding selecting forge facts.
First the same pinned image receives an explicit locator input and verified ART
material under its own request-bound grant. It returns a separate, closed locator
response (one bounded change URL or null), never a verdict/finding pretending to
be a capability request. The existing adapter validates the selector against the
locked forge origin/repository/base, then retrieves facts. The ordinary evaluation
invocation receives those facts and the same verified submission. The image owns
both extraction and evaluation. Invalid/missing claims yield no facts and a
checker-owned finding; transport/protocol failures remain infrastructure failures.

Extend the existing execution port with the locator operation, sharing its
transport and sandbox controls. The service rejects model grants for this operation
and does not create model/trial relays. Python and Rust validate matching request,
registry, phase, response digest, sizes and operation. Ordinary evaluation must
reject locator responses. One locator pass, one bounded provider read and one
ordinary evaluation are the entire sequence. Budget both sandbox runs and cleanup.
For completed member results, retain locator result/request/isolation and facts/input digests in optional member
evidence; new forge executions always supply it. Existing immutable results are
not rewritten. This is retained evidence, not a parallel execution implementation.

A live callback relay was considered: current model/trial relays require private
proxy service/mount/grant/cancellation machinery. A new authenticated forge relay
would add more authority and deployment machinery than this bounded read needs.
Parameterized core JSON-path parsing was rejected: it would still make the shared
owner interpret project submissions. Importing project Python into the worker
would bypass the image isolation boundary.

## Acceptance criteria

- [ ] Shared POST never opens a project proof file or knows `proof.json`/`pr_url`.
- [ ] Actual image locator and evaluation work for the Harnessy/GitHub example;
      an alternate proof format needs only a different project image.
- [ ] Foreign repository/origin, substituted request/registry, malformed/oversized
      locator and replayed material grants cannot obtain unauthorized facts.
- [ ] No model/trial callback or unrestricted network is available during location.
- [ ] Provider failure remains infrastructure; absent/malformed proof yields the
      image's actionable work findings; ordinary non-forge PRE/POST is unchanged.
- [ ] Locator/facts evidence and doubled invocation budget bind the final result;
      cancellation/cleanup use the existing bounded execution mechanism.
- [ ] Focused Python/Rust and actual offline-image composition prove the boundary;
      full hosted CI, affected reviews and current docs pass before readiness.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: architecture/security plan review, then architecture/security,
  QA/test-delta, documentation; CI integrity if test allocation changes.
- Human review focus: no project parsing in shared code, scoped read authority,
  no hidden network/model capabilities, exact evidence and cost of two image runs.

## Evidence

Focused verification covers the Python wire/policy contracts, image parser,
selected POST processor and the Rust workspace. Six real PostgreSQL cases prove
ART-issued request binding, exact retained receipts, unchanged replay and rejection
of substituted receipt facts. The native Docker composition script runs the pinned
image twice, rejects locator-grant reuse for evaluation and verifies offline,
read-only execution and cleanup. Its forge facts are controlled fixtures, not a
live GitHub read. Existing Terminal Systems proof does not demonstrate Garden.

Repeat the native proof with a compiled checker service, Docker and the backend
environment:

```sh
docker build -t ws-harnessy-forge:qualification external_checkers/harnessy_proof
backend/.venv/bin/python external_checkers/workstream-checker-service/tests/harnessy_forge_composition.py --service external_checkers/target/debug/workstream-checker-service --checker-image ws-harnessy-forge:qualification
```

The Garden deployment/drill still requires its guide, locked image binding and
configured read-only forge credential. No GitHub issue import or project lifecycle
changes are included. Retained policy records remain readable without altering
hashes; new forge bindings must declare locator support. An existing image without
that support cannot execute through the new protocol and has no fallback parser.

## Reconciliation

- Current-source reconciliation: main `419ac76ca`; no overlapping forge PR open.
- Next usable boundary: project-owned forge proof evaluation, followed by the
  authorized Garden project configuration/drill; no issue-source integration.
- Remaining risks: locator response is untrusted input; provider authority must
  remain the locked binding, not the returned URL. No new acceptance authority.

Plan review: PASS WITH LOW RISKS after fixing the exact wire contract, two separate ART grants, callback denial, successful-member receipt validation and second-run budget. Locator uses unchanged request schema with input.workstream_forge_facts_stage=locate and envelope operation locate_forge_change; ordinary execute rejects that marker. Only separate typed locator success or ordinary infrastructure failure is legal. Locator failure retains existing execution=None infrastructure evidence. Each selected forge adds its image deadline plus 60,000ms cleanup in addition to the existing 120,000ms read allowance.
