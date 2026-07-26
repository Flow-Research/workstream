# WS-ENG-ROOT-001-01 External Review Response

Comments addressed: one CodeRabbit fail-closed finding. Independent planning
state validation now rejects a non-string `intent_path` with a stable failure
instead of raising, with a regression test for `null` input.

Comments deferred: CodeRabbit's generic docstring-coverage warning is not a
changed-code defect and adding unrelated docstrings would violate this exact
recovery scope. The optional wider recovery runbook remains separate work.

Human decisions needed: explicit approval of PR #205 remains required because
trusted `main` contains the circular Agent Gate being repaired.

Commands rerun: focused loop-memory tests, chunk-contract tests, agent-gate
tests, independent state validation, internal evidence, Markdown links, stale
wording, and diff integrity.

Remaining risks: the trusted-main Agent Gate must fail on this recovery PR; it
cannot consume candidate code without self-authorizing the repair. The exact
schema-v7 recovery is base-pinned, identity-pinned, path-pinned, and one-use.
