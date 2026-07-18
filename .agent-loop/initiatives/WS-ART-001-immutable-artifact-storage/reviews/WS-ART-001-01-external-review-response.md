# External Review Response: WS-ART-001-01

## Source

CodeRabbit review run `7a032b7f-7bd9-44cf-b88d-89615eb8376e` on PR #101.

## Valid Findings Addressed

- Replaced the local-adapter factory assertion with a typed configuration error.
- Made cancellation recovery persist before cancellation escapes, including
  repeated cancellation, without outliving the caller-owned database session.
- Corrected the migration test so it reaches `sealed_hash_required` instead of
  referencing a nonexistent column.
- Clarified optional store commitments, persisted-integrity classification,
  `service_principal`, and verification `failed` versus integrity `quarantined`.
- Centralized service-principal validation.
- Added one reusable media-type schema and runtime/schema rejection of control
  characters, including trailing-newline request and response facts.

## Additional Internal Findings

Internal review strengthened the external cancellation suggestion: plain
`asyncio.shield` could leave cleanup running after the caller session closed.
The final helper retains and awaits cleanup through repeated cancellation, and
the regression test fails when the shielded ownership behavior is removed.

## Validation

Ruff, contract fixtures, configuration tests, migration guards, coordinator
cancellation/recovery tests, stale scans, Markdown links, and diff hygiene pass.
All required internal delta reviewers passed and their sessions are closed.

## Result

All valid external findings are addressed. Await the final current-head GitHub
checks and human merge decision.
