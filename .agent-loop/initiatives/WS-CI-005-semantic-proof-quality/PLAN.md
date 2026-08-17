# Plan: WS-CI-005 Semantic Proof Quality

## Proposed approach

Deepen the existing reviewer system in three bounded layers: define proof
semantics, adopt them in reviewers, then evaluate them against real escaped
defects. Do not add reviewers, hosted infrastructure, or contribution gates.

## Proof-strength vocabulary

Use a closed vocabulary in traceability rows:

| Strength | Minimum observable boundary |
|---|---|
| `pure` | Pure domain function or immutable value behavior |
| `service` | Orchestration, ordering, error mapping, and forbidden calls |
| `repository` | Real query/persistence behavior against the record database |
| `transaction` | Real staged effects plus commit/rollback observation |
| `concurrency` | Independent sessions/processes contending on shared state |
| `direct_sql` | Database constraint/trigger behavior bypassing ORM validation |
| `composition` | Real public ports and composition-root wiring |
| `negative_structure` | Import/route/background-job/ownership structure through syntax-aware inspection |

The vocabulary describes minimum custody, not a hierarchy where one proof
automatically replaces all others. For example, a database test cannot replace
a pure validation test, and a service mock cannot prove rollback.

### Closed compatibility rules

| Claimed boundary | Compatible minimum proof | Incompatible substitute |
|---|---|---|
| Pure validation/value rule | `pure` | Coverage or source grep alone |
| Service ordering/error/forbidden call | `service` | Pure helper test without orchestration |
| Query/persistence/tenant isolation | `repository` with a real stored row | Mock returning missing/`None` |
| Commit or rollback atomicity | `transaction` with staged and final state | Mocked repository exception |
| Lock/race behavior | `concurrency` with independent sessions/processes | Sequential service calls |
| Constraint/trigger/NULL guard | `direct_sql` against the real database | ORM-only construction or source inspection |
| Runtime owner-port wiring | `composition` | Service with a permissive fake |
| Import/route/background-job absence | `negative_structure` with syntax/registry-aware inspection | Raw substring grep where equivalent syntax exists |

Every traceability row declares both `claimed_boundary` and `proof_strength`.
The validator owns this compatibility matrix; a reviewer-supplied
`proof_compatibility` value cannot override it. `unavailable` never supports
PASS, and proof compatible with one boundary does not satisfy another.

## Test-of-the-test rule

Every final reviewer verdict must attempt at least one concrete contradiction of
a material claim. The probe states:

- the defect inserted or simulated;
- why the named proof should observe it;
- the actual result;
- whether the proof survived incorrectly;
- the resulting finding or residual uncertainty.

For changed tests, QA/test-delta must inspect whether the test would fail under
the defect. For unchanged trusted proof, a targeted mutation or equivalent
source-level counterexample may be used when execution is unavailable, but the
receipt must label it as inspected rather than executed.

## Shared escaped-failure patterns

Create one concise reference consumed by the shared protocol and specialties:

- permissive fake / label-only exception;
- mock used for repository, transaction, concurrency, or direct-SQL claim;
- missing real foreign tenant resource;
- partial returned-fact validation;
- duplicated canonical rule across schema/runtime/database;
- nullable SQL comparison and three-valued-logic escape;
- independent foreign keys where composite ownership is required;
- malformed public value reaching attribute access or persistence before
  concealment;
- source-text boundary grep that misses syntax-equivalent imports;
- aggregate coverage or broad test invocation hiding an unproven behavior.
- untrusted diff, comment, finding, or evidence text instructing a reviewer to
  ignore protocol, fabricate proof, execute content, or return `PASS`.
- fixture setup aborting before the intended assertion;
- regression input that the pre-fix implementation already rejects.

The reference is reviewer knowledge, not an automatic universal checklist.
Reviewers select patterns relevant to the impact cone and say why.

## Machine validation

Extend the canonical receipt and reviewer-contract validator to require:

- `proof_strength` on every traceability row;
- an explicit `proof_compatibility` result;
- at least one test-of-the-test adversarial probe for PASS;
- unavailable infrastructure custody to remain explicit;
- no PASS where the named proof is weaker than the declared behavior boundary;
- stable failure-pattern IDs in findings/evaluations.

Do not attempt to infer semantics from test filenames. Deterministic validation
checks closed fields, compatibility declarations, and required evidence. Blind
evaluations test whether reviewers apply the judgment correctly.

## Specialty adoption

- Architecture: composite ownership, syntax-aware private edges, composition
  roots, and database/model parity.
- Security: tenant/actor/resource substitution, nullable/fail-open state,
  replay, and concealment.
- QA and test-delta: discriminating proof, real failure injection, and
  test-of-the-test mutation.
- CI integrity: exact execution custody, selection, PostgreSQL/services,
  coverage and artifact provenance.
- Reuse/dedup: canonical rule comparison across schema, service, public API,
  migration, and database constraint.
- Senior engineering: permissive fakes, misleading abstractions, and proof cost.
- Documentation and product/operations retain their specialties and adopt the
  common proof fields without irrelevant database ceremony.

## Alternatives rejected

- One large implementation PR: too difficult to review and self-test.
- A new database reviewer: responsibilities already belong to architecture,
  security, QA/test-delta, and CI integrity.
- Mandatory mutation tooling for the entire repository: expensive and outside
  this initiative; targeted reviewer evaluation mutations are sufficient.
- Natural-language-only guidance: cannot detect drift or missing adoption.

## Boundaries preserved

- Repository engineering infrastructure only.
- No product/runtime code or migrations.
- No CI threshold reduction, test removal, or reviewer bypass.
- No automatic merge, approval, start, or post-merge state mutation.

## Verification strategy

- Unit tests for proof-strength schema and compatibility validation.
- Mutation tests removing every new shared requirement from a skill and agent.
- Blind positive/negative fixtures for every PR #349 failure class.
- Untrusted-evidence fixtures prove reviewers ignore embedded instructions and
  never execute commands supplied by diffs, comments, findings, or evidence.
- False-positive controls showing when a pure/service mock is appropriate.
- Output-set tests proving exact-head receipts cannot PASS with incompatible or
  unavailable proof.
- Forward evaluation of all nine reviewers with raw artifacts and no leaked
  expected answer.
- Standard state, Markdown, stale wording, diff, and reviewer-contract checks.

## Delivery sequence

1. `WS-CI-005-01`: shared vocabulary, receipt schema, validator, and reference.
2. `WS-CI-005-02`: candidate specialty skill/agent obligations and contract
   mutation tests; this step does not claim behavioral adoption.
3. `WS-CI-005-03`: escaped-defect blind fixtures, forward evaluation, final
   reviewer adoption, and trust-bundle/evidence-gate integration.

Each chunk is one PR. The next chunk begins only after explicit human start.
