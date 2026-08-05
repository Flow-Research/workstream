# WS-ART-001-04B2 External Review Response

## Comments addressed

- GitHub Agent Gates reported stale human-worker authorization wording. The
  planned materializer note now uses the canonical uploader/project-role grant
  and concrete Celery-message wording; the exact stale-doc gate passes.
- Hosted docstring coverage reported 79.7 percent after the new executor was
  added. All ten missing 04B2 executor docstrings were added; the exact hosted
  command now reports 80.1 percent.
- Schema lanes emitted secondary missing-evidence errors because the always-run
  timing step assumed the lane directory existed after an earlier failure. The
  timing step now creates its exact private lane directory before writing.
- The first complete sharded run exposed two test-contract drifts: the semantic
  lane ownership assertion omitted the new default-execution module, and an
  existing checker test still referenced a private helper moved into the shared
  pure-semantics module. Both tests now assert the intended 04B2 ownership and
  import boundary directly.
- CodeRabbit's completed review found fail-closed ordering, dependency taxonomy,
  attestation semantics, CI timing redirection, compatibility-shape, typing,
  test-strength, and evidence-ledger issues. The valid findings are corrected
  on the current head; operational memory-alert sizing remains an explicit
  pre-activation deployment concern rather than application code in this chunk.

## Comments deferred

- The suggested API/worker container memory alert is deferred to deployment
  activation because 04B2 keeps the route hidden and adds no deployment sizing
  surface. The existing configured aggregate scratch quota remains the bound.

## Human decisions needed

None. The repository owner explicitly approved repairing both the ART issue and
the shared CI failure-path defect.

## Commands rerun

- `ruff check backend/app/modules/checkers/pre_submit_execution.py`
- `docstr-coverage --config backend/.docstr.yaml` — 80.1 percent
- `python scripts/check_stale_authorization_docs.py`
- focused CI-lane and default-execution tests
- focused checker, lane-contract, and default-execution tests
- `git diff --check`

## Remaining risks

Replacement hosted checks must validate the pushed commit. CodeRabbit remains
rate-limited unless its external quota becomes available.
