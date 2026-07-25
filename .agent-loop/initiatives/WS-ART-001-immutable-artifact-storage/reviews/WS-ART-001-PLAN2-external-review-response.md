# External Review Response: WS-ART-001-PLAN2

## Comments addressed

- moved 04A to `upload_admission`, kept it internal and non-routable, and made
  04C the sole owner of the hidden contributor route/action declaration;
- defined relative `/`-separated NFC paths and fail-closed exact, NFC, and
  Unicode case-fold collision rejection before checks, materialization, or
  provider I/O;
- clarified that ART removes only ART-side legacy reachability while the AUTH
  registration contract owns ActionId retirement/unavailable proof;
- described 03A as the only immediate successor;
- reconciled `ArtifactPutAttempt` states with the implemented closed enum and
  separated them from legacy producer-item and replica states;
- removed the contributor-supplied hash-manifest field and documented the
  manifest as server-generated;
- scoped archive and semantic-manifest identities to Submission outer ZIPs;
- canonicalized every changed chunk heading and aligned the PLAN2 successor
  title so repository governance gates can parse the contracts;
- expanded the PR description to the canonical trust-bundle structure.
- defined abandoned verified admissions as capacity-charged `ready` records
  with only terminal `consumed` or `stale` outcomes and no expiry, release,
  deletion, cleanup, or retention process;
- made normalized regular-file executable intent part of semantic identity and
  fixed read-only materialization without preserving arbitrary ZIP permissions;
- required fresh AUTH-owned prepared capabilities at durable put intent and at
  atomic Submission/admission consumption;
- used canonical phase-specific fixed-service ActionIds and kept
  `artifact.binding.create` and `artifact.checker_input.materialize` as their
  shared PermissionIds;
- strengthened agent-gate assertions so lifecycle and ActionId/PermissionId
  regressions fail closed.
- repaired the hosted pytest-only failure by asserting the explicit typed
  capability/no-AUTH-repository boundary and normalizing Markdown whitespace
  before semantic ActionId/PermissionId checks.

## Comments deferred

None.

## Human decisions needed

None beyond the normal human review and explicit merge approval for PR #197.

## Commands rerun

- `git diff --check`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_markdown_links.py`
- `python3 scripts/test_agent_gates.py` — 100 tests
- hosted-equivalent loop-memory branch-coverage command — 300 tests, 90.46
  percent
- `python3 scripts/check_internal_review_evidence.py`
- `python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main`

## Remaining risks

Hosted GitHub checks and refreshed CodeRabbit review must validate the pushed
repair. No backend runtime behavior changed, so slow backend suites remain
hosted rather than local.
