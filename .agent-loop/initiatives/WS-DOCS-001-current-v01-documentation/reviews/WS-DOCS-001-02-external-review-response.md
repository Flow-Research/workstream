# WS-DOCS-001-02 External Review Response

## Comments addressed

1. CodeRabbit correctly identified that the data-flow page conflated the
   checker outcome `allow_review` with the later task lifecycle state
   `review_pending`. The page now names both layers and keeps
   `task_setup_blocked` as a routing recommendation rather than a checker
   outcome.
2. CodeRabbit correctly requested durable evidence for the merged REV/AUTH
   readiness claims. The capability ledger now binds policy identity, policy
   mutation activation, catalogue/fixed-service readiness, and the PREP/read
   handoff to merged PRs #242, #248, #255, and #257 respectively.

## Comments deferred

None.

## Human decisions needed

None beyond normal review and explicit merge approval for PR #259.

## Commands rerun

- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_stale_review_contracts.py`
- `python3 scripts/check_markdown_links.py`
- `PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py`
- `git diff --check`

## Remaining risks

The named readiness PRs do not make the REV lifecycle available. Both the
capability ledger and data-flow page retain that availability boundary.
