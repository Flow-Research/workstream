# WS-ARCH-001-CP02 Plan Review Evidence

## Scope reviewed

The executable-contract correction for hidden CON adapter-binding behavior was
reviewed against current `main`. This evidence covers planning only; no runtime,
schema, route, action availability, or product behavior changes in this PR.

## Reviewer results

- Architecture status: pass. Public CON ports, owner capability boundaries,
  deny-default composition, and CP03-only AUTH activation are explicit.
- Security/authorization status: pass. Exact tenant-safe loading, opaque
  prepare/consume/close semantics, service-identity eligibility, transaction
  binding, replay denial, and audit/evidence separation are specified.
- Product/operations status: pass. Low-risk note: replacement and resume semantics,
  bounded reads, and lifecycle ownership are correct. Its history-link concern
  was resolved by requiring resumed events to reference the exact preceding
  suspended event.
- Documentation status: pass. Findings were resolved by removing stale actor vocabulary and aligning the
  roadmap with the proposed executable-contract state.
- Senior engineering status: pass. Findings were resolved by adding schema-reset files to allowed scope,
  making duplicate operation handling deterministic, and excluding retirement
  fields from the CP02 read view.

## Deterministic checks

Passed:

```text
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py --changed-from origin/main
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
git diff --check
```

## Resolved findings

- Replaced the non-executable skeleton with exact allowed/not-allowed scope,
  public ports, state transitions, migration requirements, tests, reviewers,
  and stop conditions.
- Kept read request-scoped and mutations on one domain-facing opaque PREP port;
  no AUTH private import or second authorization protocol is permitted.
- Added exact compensation-adapter actor eligibility; generic service actors
  and existing ART/REV identities cannot substitute.
- Added immutable CON lifecycle events distinct from AUTH decision evidence.
- Required a same-binding link from resume to the preceding suspension event.
- Made `operation_id` globally unique and selected an exact PostgreSQL
  transaction advisory fence for create, suspend, and resume. An exact replay
  returns the immutable original result only after current read authorization;
  all mismatches and denied reads remain concealed conflicts, with no second
  mutation authorization, evidence, or effect.
- Required unconditional prepared-object closure and create/resume owner
  eligibility fences; suspend remains available to safely disable an
  ineligible binding.
- Added the Alembic environment head guard and unavailable-action registration
  proof to the future implementation scope.
- Added schema fingerprint/reset inventory files and checks to implementation
  scope.
- Defined `route_key` exactly as CON already validates it and retained
  `instrument_type` without translation or compatibility aliases.

## Final disposition

Fresh exact-diff re-review after the second external review:

- architecture: pass with low implementation risk;
- security/authorization: pass with low implementation risk;
- product/operations: pass with low implementation risk;
- senior engineering: pass.

Final status: pass for the planning correction. The future CP02 implementation
requires a fresh review of its actual code, migration, tests, and hosted CI
evidence.
