# WS-SUBMIT-001-02 — Durable foreground intake custody

- Initiative: WS-SUBMIT-001
- Durable disposition: Planned
- Intended merge outcome: persist fenced pre-handoff intake with one matching task owner, immutable command/source identity and PostgreSQL failure/concurrency proof.

## Intent

Make an original upload accountable before provider writes begin. A process-local
prepared ZIP cannot provide ownership after API failure. This change supplies
durable foreground custody for subsequent bounded streaming and T1–T4 composition.

## Current behavior

The prior change defines immutable value contracts but creates no durable intake.
ART stores prepared admissions only after PRE; TASK has no early active-operation
pointer. Schema head is 0068 on main 94334ccf4. This change is stacked on PR #708;
it does not merge or modify that PR's branch.

## Bounded change

### Allowed

- ART intake model/repository and typed value additions under existing owners.
- TASK active-operation pointer and narrow owner methods; existing lifecycle
  guards must reject inconsistent assignment or task transitions while guarded.
- Migration after 0068: constraints, composite foreign keys, immutable identity,
  fenced forward transitions and matching task/operation custody.
- Database metadata registration, canonical migration/reset fixtures, semantic
  test selection and targeted real PostgreSQL tests required by this schema.
- Initiative/index/roadmap statements of exactly delivered and remaining behavior.

### Not allowed

- Public endpoint/client cutover, provider writes, background PRE or new authority.
- Claims of physical quota enforcement, storage cleanup or runtime qualification.
- Accepted handoff before the exact AUTH/CHECKERS/outbox composition exists.
- Historical artifact rewrites, deletion, changed revision rules or deployment defaults.

## Design and decisions

The initial hidden persistence boundary permits receiving, pre_checking and
pre-handoff terminal outcomes only. Finalization_pending/finalized remain denied
until the later accepted-authority and outbox transaction adds their full guards.
This is staged implementation of one lifecycle, not an alternative submission API.

Actor/key uniqueness and a partial unique task index fence concurrent operations.
The task pointer is composite-bound to its own operation and checked at commit.
Command, actual TASK locked-context snapshot, namespace and object key are
immutable. EOF raw identity precedes sealed generation; completed source facts
cannot change. Foreground owners use a generation and database-time lease.
Expired or terminal ownership cannot publish new source facts. Recovery may fence
and abandon expired pre-handoff work, never accept it. Persistence primitives are
internal; they grant no upload/read capability and do not replace AUTH.

## Acceptance criteria

- [ ] Current schema upgrades without rewriting retained data.
- [ ] Exact actor/key and one-active-task constraints hold across independent transactions.
- [ ] Task, assignment, actor/link, project and namespace substitutions fail in SQL.
- [ ] Task pointer and operation state commit together; rollback leaves neither.
- [ ] Command/context/source identities cannot mutate after binding.
- [ ] EOF precedes exact source sealing; stale/expired owners and terminal revival fail.
- [ ] Existing affected task/submission behavior remains valid with null intake pointers.
- [ ] Focused PostgreSQL, migration/model parity, lint and impact-routed reviews pass.

## Risk and review routing

- Risk class: L0
- Required reviewers: architecture, security, QA/test_delta, CI integrity, documentation
- Human review focus: custody locks/fences, deferred closure and retained-data preservation.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Baseline | Fetch main; inspect PR #708 | Main 94334ccf4, parent PR open and CI running | No merge authority implied |
| Custody | Real PostgreSQL owner/direct-SQL/concurrency tests | Not executed | No integrated T1–T5 proof yet |

## Review findings

None recorded yet.

## Reconciliation

- Current-source reconciliation: parent identity contracts include ART primary/fingerprint binding.
- Next usable boundary: streaming storage reservation/receipt and complete acceptance authority.
- Remaining risks: T4/T5, physical storage, runtime and public cutover remain unimplemented.
