# Genuine pre-v2 reward history

The two `finance_reward_v1_*.json.gz` files were captured from the actual
pre-v2 owners at writer commit `70a60846b6bb122a835f1a1d6928edf326cbfdef`,
against PostgreSQL revision `0068_issuer_profile_email`.

- `dual` contains real automatic FinalAcceptance, contribution and money/points
  awards, including the exact money quantity `2.125000000000000001`.
- `task_replay` contains a public omitted-size task creation and two-row verified
  JSON import, their original requests, responses, command/member receipts,
  manifest hashes and complete database ancestry.

[The loader](../finance/reward_history.py) binds fixed SHA-256 checksums and
provenance. [The explicit capture utility](../finance/capture_reward_history.py)
uses the current owners and refuses changed writer code or overwriting captures;
it supplies no old writer after v2 is introduced. Captured identities are test
identities; no bearer headers or credentials are retained in the seed.

NUMERIC columns are recorded as exact decimal strings with a database-validated
numeric-column descriptor. A normal JSON float round trip would erase economic
precision. The existing isolated restore helper validates that descriptor,
restores native PostgreSQL values, re-enables every trigger, validates physical
foreign keys, and compares the resulting rows before returning the fixture.
This is backup restoration for history/migration proof, not runtime admission.

Run the history controls from `backend/` through the isolated runner:

```sh
.venv/bin/python scripts/run_isolated_tests.py --metadata-json /tmp/reward-history-proof.json -- .venv/bin/python -m pytest -q tests/finance/test_reward_history.py
```

The task/import control checks original response equality, unchanged command
and manifest evidence, fresh authorization, changed-request conflict, and no
provider-byte/parser access during historical replay.
