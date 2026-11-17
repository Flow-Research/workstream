# Finance

Finance is the dedicated owner for fulfillment of Workstream's earned awards.
The [implementation contract](../../../../workstream_finance_exec.md) defines
the required financial behavior and host integrations. Current code supplies
pure obligation, report and exception wire validation; it does not yet expose
Finance routes or execute transfers or point credits.

Workstream retains acceptance, contribution records, awards and fulfillment
receipts. Finance will own payees, arrangements, conversion, plans and execution.
COMP exposes four authenticated original-bound evidence APIs: report,
exact-event lookup, bounded source evidence and linked exception report. Three
active request-bound AUTH actions protect them. Bounded signed PostgreSQL proof
covers replay, rollback, concurrency, revocation and native guards; Finance
admission, durable delivery, execution and cutoff/drain qualification remain
unfinished. Both financial handoff directions use
authenticated HTTP after local commit.
Sharing host infrastructure grants no cross-owner write authority.

## Contract proof

See [wire contracts](contracts/README.md) for portable schemas and fixtures.
Both public owner paths reject altered digests, crossed source identities,
partial quantities and malformed outcomes. Pure contract validity establishes
neither source authority nor provider finality. Real public-API, durable-worker,
PostgreSQL and external-HTTP qualification remain required by the specification.
