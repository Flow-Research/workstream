# Internal Review: WS-XINT-003-02A

## Scope

Final working-tree review of immutable review/revision policy identity and its
exact ProjectGuide, Task, Submission, and CheckerRun lineage.

## Results

- Architecture: PASS after guide selections became all-or-none, activated
  selections became immutable, and repository joins bound the complete exact
  identity tuple.
- Security/auth: PASS after the database began binding every CheckerRun to the
  same Task as its Submission through `(submission_id, task_id, version)`.
- Product/operations: PASS after active API drills and examples moved to the
  complete policy semantics and exact identity triples.
- QA/test: PASS after migration and runtime proof covered guide selection,
  downstream lineage, immutability, historical backfill, and fail-closed
  readiness.
- Senior engineering: PASS WITH LOW RISKS; formatting-only service churn and
  migration size remain review observations, not correctness blockers.
- Reuse/dedup: PASS WITH LOW RISKS; the shared policy-lineage helper is used
  rather than duplicating digest/readiness logic.
- Docs: PASS after the guide template, data model, glossary, and submission and
  checker specs were updated.
- Test delta: PASS after vacuous legacy assertions were replaced with exact
  selected-policy, copied-lineage, redaction, mismatch, and symmetric
  immutability assertions.
- CI integrity: PASS after regenerating the exact final schema fingerprint.

No blocking finding remains. All reviewer sessions completed.

## Deterministic evidence

- Ruff passed for application, tests, scripts, and the terminal benchmark.
- The focused migration/lineage selection passed: 10 tests, 74 deselected.
- Policy-lineage branch coverage passed: 9 tests, 100 percent coverage.
- The direct isolated cross-Task CheckerRun mismatch test passed.
- Migration and active E2E Python modules compile.
- Authorization, artifact, wording, review-contract, Markdown-link, and
  whitespace checks passed.

The repository-wide 78-percent coverage suite remains assigned to hosted
GitHub Actions on the exact PR head.

The first hosted run failed closed during inventory collection because the new
test module had no semantic-lane custody. The module was assigned to
`shared_foundations`; all 31 CI lane-contract tests pass without changing the
four-lane design or any coverage/failure gate. A local repository collection
then reached unrelated missing Pillow dependencies, so exact collection is
left to the hosted environment that supplies the locked CI dependencies.

The next hosted lane run exposed three stale test assumptions: partial guide
selection, mutation of now-immutable policy rows, and a cross-Task CheckerRun
rewrite that the new FK correctly rejects. The tests now prove all-or-none
selection, retain stamped work-context proof through the still-mutable payment
policy, and expect the cross-Task rewrite to fail at the database boundary.
All four corrected focused cases pass in isolated databases.
