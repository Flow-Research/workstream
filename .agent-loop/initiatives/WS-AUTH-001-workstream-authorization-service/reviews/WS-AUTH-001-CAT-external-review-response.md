# External Review Response: WS-AUTH-001-CAT

## Pull request

PR #117 - Reconcile authorization action and resource catalogue

## Comments addressed

1. CodeRabbit correctly identified that `STATUS.md` described the persisted
   audit constraint as 49 permissions without restating the 52 approved
   identifiers. The text now distinguishes AUTH-05A's 49-identifier persisted
   audit base from the 52 approved catalogue and names the three planned recovery
   identifiers.
2. CodeRabbit correctly identified a stale second-start requirement in the
   lower `WORK_QUEUE.md` instructions. The queue now records that the AUTH-05B
   start signal was received and that only CAT merge plus its post-merge
   memory/stop checkpoint remain.

## Comments deferred

None.

## Human decisions needed

None. The repair preserves the already approved catalogue and lifecycle gates.

## Commands rerun

```text
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
git diff --check
```

## Remaining risks

None from these comments. AUTH-05B remains inactive until CAT merge and its
post-merge memory/stop checkpoint.
