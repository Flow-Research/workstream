# WS-ART-001-03A External Review Response

Reviewed at: `2026-07-28`

## Comments Addressed

- Bootstrap cleanup now closes an already-created provider bootstrap when
  scratch-manager construction fails; a focused test proves the failure path.
- Route UUID parsing is isolated from ingest execution, so malformed request
  identifiers remain concealed while an unrelated implementation `ValueError`
  is no longer converted to `404`; both outcomes have focused tests.
- The invalid logical-role test now asserts the exact
  `ArtifactAdmissionRelationshipError` contract.
- The prepared-request digest now exposes the same five explicit keyword-only
  UUID parameters as its canonical request-value helper.
- Artifact operation structural checks now apply forbidden provider fields to
  canonical result classes as well as request classes.

## Comments Deferred

- Consolidating three small prepared-authorization test doubles is a reuse-only
  cleanup with no behavior or security effect; retain local test ownership in
  03A and revisit if the fake contract changes.
- Passing the already-locked lineage into staging would remove one same-
  transaction query but is an optimization, not a correctness repair.
- The PREP transaction remains bounded by the canonical scratch deadline while
  guide ingest is hidden and deny-only. AUTH `WS-XINT-002-04A` must review the
  transaction/read duration before activation; 03A does not activate the
  action or introduce a second authorization path.
- The comment about strengthening the removed project-coverage self-test is
  obsolete after the reviewed 03A coverage-ownership reconciliation.

## Human Decisions Needed

None for 03A. Activating guide ingestion remains the explicit AUTH 04A gate.

## Commands Rerun

```text
python3 -m ruff check app/adapters/artifacts/__init__.py app/modules/projects/router.py app/modules/artifacts/authorization.py tests/test_guide_artifacts.py tests/test_artifact_architecture.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q -p pytest_asyncio.plugin tests/test_guide_artifacts.py tests/test_artifact_architecture.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Remaining Risks

- Guide ingestion remains intentionally unavailable until AUTH 04A installs
  and proves the exact adapter.
- The transaction-duration observation is an activation concern, not a live
  production exposure in 03A.
