# WS-ART-001-04A3 Internal Review Evidence

## Evidence gate

Result: PASS.

- The capability remains hidden and process-local: no route, ORM, migration,
  TASK mutation, provider I/O, checker, admission, Submission, review, or AUTH
  activation was added.
- File digest, byte count, and executable intent are derived during the same
  complete validated member read introduced by 04A2. There is no second ZIP
  parser or caller-owned manifest input.
- The closed canonical JSON body includes only normalized paths, entry type,
  exact file SHA-256/byte count, and normalized executable intent. Packaging
  metadata and arbitrary permission bits are excluded.
- The change gate is side-effect-free and distinguishes first submission,
  exact unchanged, semantic unchanged, changed, missing canonical predecessor,
  and stale predecessor selectors.
- Every non-first comparison requires the locked/reloaded current predecessor
  selector. Legacy `Submission.package_uri`, `package_hash`, and
  `artifact_hash_manifest` never become authority.
- Focused tests, 90-percent owned coverage, Ruff, semantic-lane inventory,
  stale scans, Markdown links, and diff checks pass.

## Reviewer results

- Architecture: PASS.
- Security: PASS after non-first comparisons were changed to require the exact
  current locked predecessor selector and omission received regression proof.
- QA: PASS.
- Product/operations: PASS.
- Senior engineering: PASS; immutable manifest construction now validates its
  digest, entry facts, and aggregates.
- CI integrity: PASS; both new test modules are inventoried exactly once and no
  workflow, threshold, timeout, or policy was weakened.
- Documentation: PASS; the canonical specification records all hidden stable
  failure tokens and defers public mapping.
- Reuse/dedup: PASS; the manifest is computed in the existing 04A2 traversal,
  uses shared canonical hashing, and now has one private body projection helper.
- Test delta: PASS; 04A2 tests remain unchanged, no tests were removed or
  skipped, and the new manifest/gate cases are lane-owned.

## Deterministic proof

- Focused archive, manifest, change-gate, and lane tests: `85 passed`.
- Focused owned coverage: `92.11%`, above the required 90-percent floor.
- Repository backend Ruff: passed.
- Stale artifact, authorization-doc, and Workstream-wording scans: passed.
- Markdown links and `git diff --check`: passed.

The first ordinary coverage process hit the workstation's known exit-139
failure without test output. Re-running the same focused scope with explicit
pytest plugins completed successfully; no assertion, coverage, or CI policy was
changed to accommodate the machine failure.

## Residual risk

04A3 provides the identity and comparison capability only. `04C2` must persist
this exact manifest with verified admission, while `05A` must revalidate and
bind its predecessor selector atomically. Hosted PR shards, CodeRabbit, and
human review of the exact commit remain required before merge.
