# Finance

Finance is the dedicated owner for fulfillment of Workstream's earned awards.
The [implementation contract](../../../../workstream_finance_exec.md) defines
the required financial behavior and host integrations. Current code supplies
pure obligation, report and exception wire validation; it does not yet expose
Finance routes or execute transfers or point credits.

Workstream retains acceptance, contribution records, awards and fulfillment
receipts. Finance will own payees, arrangements, conversion, plans and execution.
Both financial handoff directions use authenticated HTTP after local commit.
Sharing host infrastructure grants no cross-owner write authority.

## Retained-reward preflight

From `backend/`, with the ordinary shared database configuration:

```sh
.venv/bin/python scripts/finance_reward_preflight.py --sample-limit 100
```

The command reads a single database-enforced read-only, repeatable-read
snapshot. It reports counts and at most 100 IDs per category for live v1 work,
retained economic facts, saved responses and source-lineage anomalies. It
prints no economic bodies, actor PII or credentials and changes no data.

Exit 0 means this diagnostic found no listed blockers; it does not establish
that cutover is safe. Exit 2 means retained work or anomalies block cutover.
Exit 1 means the diagnostic is unavailable, including an unsupported schema.
`cutover_fence_held` remains false: the migration must separately stop new v1
work, drain relevant workers, acquire owner fences and rerun blocker checks.

The current command supports the pinned pre-v2 revision
`0068_issuer_profile_email`. Forward reward migrations must extend its exact
supported-schema predicates and inventory before that schema is qualified.
Unknown or unexpectedly modified schemas fail closed. No startup sweep
enrolls or pays historical awards.

The supported baseline has Review storage but no authorized human
FinalAcceptance writer or canonical human decision receipt. Any retained human
acceptance therefore appears as an unqualified source anomaly and blocks
cutover pending owner reconciliation. A same-actor AUDIT row cannot substitute
for that missing authority. The same qualification limit applies to reviewer
ContributionRecords without a supported authorized creation path. The
diagnostic preserves those records.

## Contract proof

See [wire contracts](contracts/README.md) for portable schemas and fixtures.
Both public owner paths reject altered digests, crossed source identities,
partial quantities and malformed outcomes. Pure contract validity establishes
neither source authority nor provider finality. Real public-API, durable-worker,
PostgreSQL and external-HTTP qualification remain required by the specification.
