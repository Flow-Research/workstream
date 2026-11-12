# Workstream Finance wire contracts

`obligation-v1.schema.json`, `fulfillment-report-v1.schema.json`, and
`fulfillment-exception-v1.schema.json` are the portable closed shapes specified in
the [implementation contract](../../../../../workstream_finance_exec.md).
Both COMPENSATION and FINANCE public `fulfillment_contracts.decode_obligation`
entry points validate raw bytes, canonical values, source shape and digests.
Their report and exception entry points additionally compare exact supplied
obligation facts, full-award quantity, success linkage and receiver-time bounds.
Late factual reports have no maximum delivery age.
The points fixture preserves the exact published section 21.3 digest vector;
money and historical fixture digests are computed with the canonical core hash.

Run from `backend/`:

```sh
.venv/bin/python -m pytest -q tests/finance/test_obligation_contracts.py tests/finance/test_fulfillment_contracts.py
```

Wire validation establishes neither source authority nor a stored obligation.
These contracts currently activate no routes, workers or payment effects.
Policy and quote contracts remain to be implemented. A valid wire report does
not establish provider finality or authorize a financial effect.
