# External Review Response: WS-AUTH-001-01

## Pull Request

PR #93 - Adopt Workstream authorization service baseline

## CodeRabbit Findings

Valid findings addressed locally:

- updated PR publication and work-queue lifecycle state;
- added enforceable identity-link uniqueness and active-link cardinality;
- aligned approval provenance fields and examples on grant/profile IDs;
- marked legacy audit claim/role columns prohibited for new authority events;
- added permission, candidate-grant, resource, and lifecycle guards to task
  lifecycle diagrams;
- changed the Flow relationship to externally issued Flow-token wording;
- included Audit in the permission-scoped locked-context projection;
- documented repair, retry, and contributor-revision checker-failure routes;
- defined `Both` as the guarded union of Submitter and Reviewer capabilities;
- separated Contributor and Operator personas in the product brief;
- defined system-scoped versus exact-project Project Manager coverage;
- added PlantUML files to active authorization-document discovery and tests.

One suggestion was rejected: renaming persisted contributor grant `both` to
`submitter_reviewer`. The user explicitly approved the exact values
`submitter`, `reviewer`, and `both`; D11 records that decision, and the capability
matrix now removes ambiguity by defining the guarded union semantics.

## Additional Internal Findings

The internal review also found and repaired two issues beyond the external
comments:

- technical-worker exemptions are match-local, so unrelated Celery wording
  cannot hide a later human `worker` occurrence;
- later chunk contracts now own deterministic migration from legacy human
  `worker_*` fields to canonical `contributor_*` fields without changing
  immutable attribution.

## Latest Main Integration

PR #90 merged to `main` as `a7aa474` and is merged into this branch locally.
Conflict resolution preserves its correction provenance and activation gates,
uses Contributor for human product actors, and keeps Celery/setup worker terms
only for internal execution processes.

No GitHub thread is replied to or resolved by this evidence file. Thread writes
remain a separate explicit action after the repaired commit is pushed.

## CI Follow-Up

The first repaired head passed Agent Gates and CodeRabbit. Backend CI reported
one stale prompt assertion in `backend/tests/test_agent_runtime.py` while 463
tests passed. The assertion is terminology-only and now expects Contributor,
matching the reviewed prompt and the existing project prompt-contract test.
