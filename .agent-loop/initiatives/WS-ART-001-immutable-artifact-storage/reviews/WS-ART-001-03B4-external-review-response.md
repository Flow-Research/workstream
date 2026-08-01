# WS-ART-001-03B4 External Review Response

## Comments addressed

- Fixed the Backend semantic-lane interruption by adding the exact
  `setup_generation` keyword to the remaining enqueue-failure test stub.
- Moved generation-invariant validation before the guide transaction commit.
- Moved the latest-generation read behind the locked guide/setup header and
  reject stale generations from that locked transaction.
- Require image structural extraction output to decode to a JSON object.
- Preserve distinct conflict, unavailable, stale, artifact, and sanitized
  unexpected-failure setup codes.
- Added report provenance shape, digest, size, and generation constraints plus
  the child canonical-output digest constraint in ORM and migration.
- Wrapped non-finite and unsupported-value prompt serialization as the
  port-owned runtime error.
- Added missing queue/task argument docs and corrected captured-payload typing.
- Strengthened tests for obsolete extraction exclusion, exact prompt byte count,
  atomic setup-run output linkage, migration restoration, constraints, and
  absolute/relative persistence-import boundary detection.
- Added the ART material adapter to the focused 90 percent coverage command.
- Reconciled the closed artifact-interface export assertion with the three
  canonical guide-sufficiency value types exposed by that interface.
- Recreated the async database engine after the migration downgrade/upgrade
  boundary. The round-trip test owns table and column restoration; the shared
  clean-schema fingerprint gate remains the single canonical assertion for the
  complete constraint catalogue, avoiding duplicate order-sensitive schema
  custody inside an ordinary semantic lane.
- Advanced the canonical Alembic test head from the merged `0045` revision to
  this chunk's `0046_guide_sufficiency` revision so every downgrade guard
  restores and asserts the actual repository head.

## Comments deferred

- Legacy four-argument Celery compatibility is intentionally not added. This
  hidden continuation has never been activated in production, so no legitimate
  deployed messages exist; deriving a missing generation would weaken the exact
  generation fence required by the approved contract.
- The per-item locked ART query remains because v0.1 source item counts are
  bounded and the explicit per-item completeness check is easier to audit. A
  set-based optimization has no correctness benefit in this chunk.
- The long verified continuation is not refactored during review repair. Named
  helper extraction would be behavior-neutral but adds unnecessary churn across
  a transaction-sensitive method after correctness review.

## Human decisions needed

None. Deferred suggestions do not change the approved product or security
boundary.

## Commands rerun

- Ruff over backend application, tests, and scripts.
- Focused architecture, queue failure, router, prompt, migration, exact material,
  provenance/replay, stale-contract, authorization-doc, and Markdown-link checks.
- Hosted Agent Gates on the repaired PR head; Backend is rerun after each exact
  semantic-lane repair.

## Remaining risks

The hidden verified continuation remains unavailable until AUTH-04B. ART-03C
still owns live legacy cutover; no compatibility fallback may bypass the exact
setup-generation identity.
