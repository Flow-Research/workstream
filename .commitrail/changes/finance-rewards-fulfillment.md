# Size-based rewards and dedicated Finance fulfillment

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Implement the size-based reward and dedicated Finance contract in `workstream_finance_exec.md` through one PR with cohesive, revertible commits.

## Intent

Carry accepted Workstream contributions through authenticated financial fulfillment. The user explicitly requests one PR; implementation stages are commit boundaries within that PR. The specification is the settled product contract, including one eligible Finance human authorizing bank transfers.

## Current behavior

Baseline main is `94334ccf4085c26c7bfaa054465fc05cfbdad1fc`. REV FinalAcceptance composes TASK and CON participants in the caller's transaction; compensation already persists immutable award sets. Policy definitions currently permit multiple instruments. Finance fulfillment is absent. Native human acceptance is explicitly unavailable. Existing policy, award, revision, AUTH and OUTBOX tests protect the boundaries this change extends.

## Bounded change

### Allowed

- The owner and integration paths enumerated in specification section 19.3: backend contribution/compensation/task/artifact/review/AUTH/ACTORS/OUTBOX public APIs and implementations, same-owner adapters, API delivery, workers, shared settings/model registration and forward migrations.
- Dedicated `backend/app/modules/finance/`, its adapters, routes, workers, contracts and focused tests.
- Existing Rust identity issuer, CLI, MCP, deployment wiring and affected tests/contracts/docs.
- This record, the implementation specification and affected current capability/architecture documentation; ignored local roadmap exports if roadmap changes require them.

### Not allowed

- Merge, production payout or deployment without applicable user authorization; no secrets in Git.
- Separate Finance application/database/migration chain, parallel identity/grant store, direct cross-owner financial writes or bypassed authenticated HTTP.
- Native human review expansion, wallets, withdrawal, external routing, automatic historical payouts, rewritten historical economic evidence or weakened tests/CI.

## Design and decisions

Extend existing policy, task selection, revision and acceptance operations. Finance shares host infrastructure but owns financial records. Durable handoffs use actual authenticated HTTP after transaction closure. New v2 writes select one exact size-based award; genuine v1 history remains read-only. Payment uncertainty reconciles the same provider reference.

Rejected alternatives: separate app/database, duplicate workflow engines, direct same-process fulfillment delivery, multiple-person approval, and a second money award for points conversion.

Commit sequence follows specification section 19.2: (1) executable contracts/digests and retained-data preflight; (2) policy/task/revision propagation; (3) atomic award/root/handoff and callback custody; (4) Finance/AUTH/machine identity and runtime partition; (5) configuration/plans/credit/authorized transfer; (6) HTTP/client/recovery integration; (7) operational qualification and documentation. Split stages into smaller cohesive commits as needed. Reverting code is not a data rollback: preserve durable financial evidence and use the specification's coordinated cutover/restore procedure.

### First commit boundary: obligation wire contract

Allowed: `backend/app/modules/compensation/api/fulfillment_contracts.py`, `backend/app/modules/finance/api/`, `backend/app/modules/finance/contracts/`, narrowly scoped core wire-format primitives, and focused COMP/FIN contract tests. Excluded: models, migrations, module registry, routes, workers, AUTH activation, provider calls and financial effects. The next preflight commit requires its own concrete query/report plan before implementation; it is excluded from this contract-only commit.

Both owners independently validate the portable closed JSON Schema and canonical digests through their own public entry paths. Neither owner's decoder calls the other's decoder. Reuse the existing core hash and route-token primitive; avoid duplicated manually maintained field rules. Decode raw bytes before ordinary request parsing: enforce 64 KiB, strict UTF-8, duplicate-member rejection, object-only envelopes and unknown-member rejection. Tests exercise both entry paths against the same fixtures, including changed quantity with old digests and recomputed digests over an invalid source shape. Pure wire validation proves no source authority or database identity.

First-commit verification: `cd backend && .venv/bin/python -m pytest -q tests/finance/test_obligation_contracts.py`; `.venv/bin/ruff check app/core/financial_wire.py app/modules/compensation/api/fulfillment_contracts.py app/modules/finance/api tests/finance/test_obligation_contracts.py`. These are planned new tests/files, not executed proof. Schema fixtures include the exact specification vector, money and historical controls, plus negative canonicalization/shape/digest cases. Source-authority and runtime HTTP assertions remain later integration proof.

## Acceptance criteria

- [ ] Positive/negative contract fixtures reproduce canonical digest vectors and reject altered evidence.
- [ ] Sized public task/submission/revision paths preserve exact locked economic selection.
- [ ] Acceptance commits the selected award, root and handoff atomically; callbacks cannot create eligibility.
- [ ] Finance authority and worker profiles enforce source/project/grant currentness and disjoint delivery custody.
- [ ] All three fulfillment modes, uncertain outcomes, failure/retry, revocation, reversal and race boundaries are proven.
- [ ] Real PostgreSQL and public HTTP/durable-worker drills meet specification section 20; client/export contracts agree.
- [ ] Forward migration rehearsal preserves v1 evidence and refuses unsafe cutover.
- [ ] Current documentation, roadmap and operational claims match delivered proof; required reviews and repository checks pass.

## Risk and review routing

- Risk class: L0 (financial effects, cross-system authority and retained-data migration).
- Required reviewers: architecture, security, qa, test_delta, product_ops, reuse_dedup, documentation; ci_integrity for worker/deployment/check changes.
- Plan review precedes runtime implementation. Final reviews bind to a clean committed candidate after shared checks.
- Human review focus: economic selection and retained history, execution authority and uncertainty, cutover inputs, realistic drill evidence. Specific PR merge remains a human action.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Baseline reconciled | fetch origin main; inspect open PRs | Main matches pinned baseline; no open non-draft PR | Draft #708 touches intake and #698 CLI ZIP preparation; neither is implementation authority |
| Existing acceptance owner inspected | REV acceptance participant and compensation award participant | Existing caller-owned atomic composition confirmed | Full runtime suite not yet executed |
| Target behavior | Specification sections 20–21 and focused existing owner tests | Required proof defined; implementation pending | No payment/deployment qualification yet |

## Review findings

Pending plan review and implementation evidence. No readiness claim.

## Reconciliation

- Current-source reconciliation: baseline matches the specification; no newer merged owners found.
- Next usable boundary: executable contracts and safe read-only retained-data preflight, with financial activation closed.
- Remaining risks: broad single-PR review surface explicitly selected by user; commit boundaries aid inspection but do not establish runtime rollback safety.
