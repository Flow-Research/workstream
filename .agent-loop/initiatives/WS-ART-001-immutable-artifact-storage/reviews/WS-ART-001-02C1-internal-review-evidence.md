# Internal Review Evidence: WS-ART-001-02C1

## Chunk

`WS-ART-001-02C1`: Admission And Put-Attempt Foundation

Open sub-agent sessions: none.

Valid findings addressed: yes.

## Reviewed Revision

Reviewed code SHA: `535069cfb1a7312d731bb14a6023ceb0894402e9`

Trusted base: `8d5eb15b384fd75787ce98a099400a1d335d2560`

Reviewed at: 2026-07-19T15:20:00Z

Reviewer run IDs: senior-engineering/security-auth/ci-integrity=/root/review_senior_6392825f; architecture/product-ops/test-delta=/root/review_arch_6392825f; qa-test/reuse-dedup/docs=/root/plan_review_actor_boundary

Each track explicitly rebound its review to the final SHA above. All sessions
completed.

Only review evidence, trust-bundle, external-response, and initiative-status
files may change after the reviewed implementation SHA. Any implementation,
test, workflow, policy, specification, or chunk-contract change invalidates
this evidence and requires a new exact-SHA review cycle.

## Reviewed Change

- Adds server-owned deployment, project, producer, and task admission scopes,
  unique content charges, and one atomic prepared put attempt before provider
  I/O.
- Accepts only closed guide, contributor, and checker-output requests and
  derives canonical relationships and scope limits inside Workstream.
- Uses an actors-owned same-transaction proof boundary that locks the exact
  profile then identity link and returns frozen primitive state; ART no longer
  imports or queries actor persistence.
- Leaves every prepared execution field inactive: `next_run_at`, executor,
  lease, terminal result, replica, and receipt are null and execution generation
  is zero.
- Makes release timestamps biconditional with released charge state.
- Adds deterministic database contention proof for same-content deduplication
  and distinct-content oversubscription.
- Adds migration `0028_artifact_admission`, following
  `0027_contributor_foundation`, with populated-state downgrade refusal.

## Reviewer Results

| Reviewer | Result | Blocking findings | Disposition |
|---|---:|---|---|
| senior engineering | PASS | None | Transaction and ownership repairs are bounded and maintainable. |
| architecture | PASS | None | Actors own persistence proof; ART remains provider-neutral and dormant. |
| QA/test | PASS after fixes | None | Distinct actors and a scope-reservation barrier now prove real ledger contention. |
| security/auth | PASS | None | Exact identity, relationship, configuration, and quota checks fail closed without duplicating AUTH. |
| product/ops | PASS | None | No task, submission, checker, review, contribution, compensation, or reputation lifecycle mutation. |
| reuse/dedup | PASS | None | Canonical actor and artifact interfaces are reused; optional test-only barrier duplication is documented. |
| CI integrity | PASS | None | All prior 90-percent gates and the repository 78-percent floor remain fail closed. |
| test delta | PASS | None | Removed tests match intentionally removed provider execution; retained behavior gains stronger proof. |
| docs | PASS after fixes | None | Migration, inactive scheduling, status, evidence, and trust bundle are synchronized. |

## Findings Addressed

- Removed ART's direct `ActorProfile` and `ActorIdentityLink` queries and added
  an actors-owned frozen admission proof in the caller's transaction.
- Made `next_run_at` nullable and null for `prepared`, enforced by the prepared
  execution-inactive database constraint.
- Enforced `(state = 'released') = (released_at is not null)`.
- Preclaimed the namespace in concurrency fixtures, used distinct actors, and
  synchronized immediately before the real scope reservation method. The
  same-content case proves two attempts, seven unique charges, eight links, and
  four counted deployment bytes; oversubscription proves one success, one typed
  capacity failure, one attempt, and four charges.
- Corrected active migration wording from `0027` to
  `0028_artifact_admission`.

## Deterministic Proof

The isolated real-PostgreSQL/MinIO focused matrix ran against the reviewed SHA:

```text
371 passed in 757.38s
scoped coverage: 94.02%
required scoped floor: 90%
Alembic head: 0028_artifact_admission
```

Additional results:

- Ruff: PASS.
- configured docstring coverage: PASS at 90.5 percent.
- stale artifact contract scan: PASS at `artifact_store_cutover`.
- agent gates: PASS, 88 tests.
- Markdown links: PASS.
- schema-v2 merge-intent validation: PASS.
- `git diff --check`: PASS.

GitHub Backend remains authoritative for the isolated full repository suite and
78-percent repository-wide floor on the published final head.

## Remaining Risks

- Provider execution, acknowledgement observation, verification, publication,
  recovery, routes, and product cutover remain intentionally unavailable.
- Native AWS remains runtime-ineligible pending separately owned live proof.
- External GitHub and CodeRabbit checks remain pending until the rebased final
  candidate is published.

## Stop Condition

Publish the evidence-bound candidate to existing PR #154, wait for fresh
external checks, and stop for explicit user merge approval. Do not start
`WS-ART-001-02C2` automatically.
