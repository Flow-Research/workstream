# Terminal Benchmark historical validation

[Local validation notes](LOCAL_VALIDATION_NOTES.md) record an earlier development
exercise. Its executable used superseded guide inference routes and was removed
when unified setup became the sole inference path. These notes are historical
evidence, not a runnable command or proof of current Workstream behavior.

Current HTTP lifecycle verification uses
[`backend/scripts/api_contract_e2e.py`](../../backend/scripts/api_contract_e2e.py)
in the isolated PostgreSQL/MinIO test environment. The live guide stops at draft
proposals; manager review and approval are delivered by their separate POL chunks.
