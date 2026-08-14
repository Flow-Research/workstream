# WS-ARCH-001-CP02 External Review Response

## CodeRabbit review at `3ccf4d35`

All seven comments were verified against current repository behavior rather
than applied blindly. Each was valid within the bounded interpretation below.

1. Stable operation identity: fixed. The trusted server-side command caller
   supplies one stable `operation_id`; external clients cannot choose it, CON
   computes the request digest, and retries preserve the same identity.
2. Exact allowed files: fixed. Globs and brace expansions were replaced with
   concrete production, test, generated-parity, initiative, and review paths.
3. Eligibility race: fixed. PROJECTS then ACTORS eligibility uses
   transaction-bound reads with locks held or fixed-order revalidation directly
   before AUTH consumption and insertion. Ineligibility/revocation race tests
   must prove no binding or event is created.
4. Migration references: fixed in the active CON handoff. `0052` is explicitly
   historical; the active graph ends at `0003_submission_lineage`. Historical
   chunk evidence was intentionally not rewritten.
5. Existing rows at `0004`: fixed without compatibility invention. The upgrade
   must fail before schema mutation when the binding table is non-empty; tests
   prove empty success and non-empty preservation/recreation requirement.
6. Reviewer vocabulary: fixed. Status values are lowercase `pass`; risk and
   remediation details are separate prose.
7. Test wording: fixed. The future proof names unit tests, PostgreSQL
   schema/lifecycle tests, concurrency tests, reset tests, boundary tests, and
   hosted full-coverage proof explicitly.

## Verification after correction

- architecture re-review: pass;
- security/authorization re-review: pass;
- senior-engineering re-review: recorded in the final trust bundle;
- stale authorization and Workstream wording checks: pass;
- changed Markdown links: pass;
- atomic chunk-state synchronization: pass;
- `git diff --check`: pass.

Hosted CI and CodeRabbit must rerun against the corrected exact head. This file
does not mark their earlier head as proof for the corrected commit.
