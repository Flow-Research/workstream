# External Review Response: WS-ART-001-PLAN4

## Comments addressed

- defined one closed mapping from stable catalogue ID to persisted public
  checker name to implementation dispatch primitive, including the legacy
  public-name/primitive differences;
- added a typed checker-result provenance envelope and explicit persistence
  fields for dispatch authority, authority-neutral definition ID/version
  (catalogue identity for pre-submit), public name, source, effective-plan hash,
  rule-instance ID, and locked-policy hash rather than relying on open-ended
  metadata;
- separated completed checker findings from retryable infrastructure outcomes;
  disabled mandatory entries, exhaustion, cancellation, authorization denial,
  and infrastructure failure create no contributor finding or product state;
- replaced full checker-result audit persistence with a closed, bounded,
  path-redacted projection and enumerated both allowed and forbidden fields;
- made each task's existing locked compiled-bundle hash transitively commit to
  the immutable catalogue version, manifest digest, ordered entry/configuration
  hashes, and enabled/disabled state;
- removed every obsolete `PreSubmitCheckResponse` reference from the historical
  Chunk 8 pre-submit section and conditions, replacing it with the canonical
  same-request `pre_submission_checker_failed` contract;
- corrected the submission packet and operating checklist so project-required
  evidence is inside the one outer ZIP and all paths, hashes, evidence facts,
  IDs, manifests, and bindings are server-derived;
- clarified that `PreSubmissionCheckerCatalogue` owns pre-submit dispatch while
  the durable registry owns post-submit dispatch;
- expanded the PR description to the complete trust-bundle structure.

## Comments deferred

None.

## Human decisions needed

None beyond normal review and explicit human merge approval for PR #271.

## Commands rerun

- `git diff --check`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_markdown_links.py`
- `PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py`

## Remaining risks

- hosted GitHub Backend gates and refreshed CodeRabbit review must validate the
  rebased repair;
- this is planning-only, so typed result persistence, route removal, and
  catalogue execution still require their separately approved implementation
  chunks and tests.
