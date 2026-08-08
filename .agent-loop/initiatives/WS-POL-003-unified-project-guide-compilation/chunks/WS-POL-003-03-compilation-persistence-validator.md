# Planning Parent: WS-POL-003-03 - Compilation Persistence and Validator

Status: Split into `03A` and `03B`; this file is not executable. Risk: L1.

`03A` builds hidden schema, validator, repository, attempt crash fencing, and
deny-by-default authorization seams. AUTH-12I then activates the exact request
and execute actions. `03B` consumes that authority to make compilation-parent
persistence usable. Policy projections remain owned by 04B, 05B, and 06B in
their separate protected transactions.

No transaction or lock spans provider I/O. PM request/recovery records only
dispatch custody; the worker later authenticates independently as
`workstream.project.setup`. No handle crosses Celery.
