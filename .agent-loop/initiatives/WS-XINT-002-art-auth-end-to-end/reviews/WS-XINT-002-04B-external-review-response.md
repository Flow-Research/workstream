# External Review Response: WS-XINT-002-04B Planning Amendment

## Comments addressed

- CodeRabbit correctly identified that the verification command's `<test-db>`
  placeholder is parsed by the shell as redirection. The command now requires
  and reuses an existing `WORKSTREAM_TEST_DATABASE_URL` value through an
  executable shell expansion.
- Agent Gates correctly rejected two unqualified background-executor references. They now use
  the exact technical terms `Celery task payload` and `Celery task/route
  composition`, preserving the separation from Workstream's human contributor
  vocabulary.

## Comments deferred

None.

## Human decisions needed

Human review and merge of the corrected 04B security boundary remain required.

## Commands rerun

- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_markdown_links.py`
- `git diff --check`

## Remaining risks

No runtime action is activated by this planning amendment. Exact-head Agent
Gates, Backend, and CodeRabbit must pass before merge.
