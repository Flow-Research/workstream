# Workstream Finance wire contracts

`obligation-v1.schema.json` is the portable closed obligation shape specified in
the [implementation contract](../../../../../workstream_finance_exec.md).
Both COMPENSATION and FINANCE public `fulfillment_contracts.decode_obligation`
entry points validate raw bytes, canonical values, source shape and digests.
The points fixture preserves the exact published section 21.3 digest vector;
money and historical fixture digests are computed with the canonical core hash.

Run from `backend/`:

```sh
.venv/bin/python -m pytest -q tests/finance/test_obligation_contracts.py
```

Wire validation establishes neither source authority nor a stored obligation.
These contracts currently activate no routes, workers or payment effects.
Policy, report, exception and quote contracts remain to be implemented.
