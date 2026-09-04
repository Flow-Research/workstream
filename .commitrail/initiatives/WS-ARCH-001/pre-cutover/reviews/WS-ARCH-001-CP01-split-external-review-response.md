# WS-ARCH-001 CP01 Split External Review Response

## Comments addressed

- Replaced two nonexistent future verification commands in CP01A and CP01B
  with repository-owned runnable checks.
- Expanded the binding-authority risk mitigation to name retirement,
  fulfillment, callback, and delivery exclusions across identifiers,
  permissions, identities, routes, evaluators, and service-matrix rows.

## Comments not applied

- CP01A and CP01B remain executable implementation contracts for future PRs.
  Their actions remain planned/unavailable on merge, but those PRs still make
  real AUTH catalogue and typed-public-API changes. Only CP01 is the
  non-executable planning parent.
- CodeRabbit's requests to implement the registered actions in PR #331 were not
  applied. PR #331 is the bounded plan/chunk split; runtime implementation
  belongs to the later one-chunk-per-PR CP01A and CP01B changes.

## Human decisions needed

None. These dispositions preserve the approved planning-only scope.

## Commands rerun

```text
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/workstream_agent_gate.py --help
git diff --check
```

## Remaining risks

CP01A and CP01B implementation still require separate human approval and their
full contract verification on then-current main.
