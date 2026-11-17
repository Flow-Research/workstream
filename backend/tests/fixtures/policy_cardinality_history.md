# Historical policy cardinality fixtures

These synthetic snapshots were captured from commit
`fac8ea5110dfe3ac1d8fa90a5f0ff132c3811034`, at schema
`0081_operation_read_authority`, before new approval inputs required exactly one
image per phase. They contain no provider or user-environment data.

`no_pre` contains a real approved 0-PRE/1-POST policy; `no_post` contains a real
approved 1-PRE/0-POST policy. Each includes its matching activation receipt,
TASK assignment, authorization rows and immutable policy custody. Both approvals
have non-null `request_json`. Each snapshot contains 52 nonempty tables and 308
rows. No policy row was rewritten to manufacture these cases.

The exact capture test is [policy_cardinality_capture.py.txt](policy_cardinality_capture.py.txt).
It was appended to `tests/artifacts/test_submission_intake_admission.py` in a
detached checkout; all original source bytes remained unchanged. Run that module
with `-k capture_historical_cardinality` through `scripts.run_isolated_tests` at
the source commit. The capture calls the original T1 rejection test before
recording rows. The run passed both cases and completed isolated database/role
cleanup. Snapshot timestamps and UUIDs intentionally remain literal evidence;
recapture will produce different bytes and requires review.

Capture source SHA256:
`04564ad49e1d6152093895379eed5062df1ac435d632925b268695f19e856941`.

The archive is canonical sorted JSON compressed with gzip `mtime=0`. Its SHA256
is `0b7cb10abc1c23864fac6c3be2b898caf297760192cc423e2f6f2c1e1862911c`.
The loader checks that checksum and provenance before using the existing owned
test-database snapshot restoration helper. Restoration is a backup setup step,
not proof of a current writer. Triggers and foreign-key settings are restored
and checked before migration or admission assertions run.

These fixtures establish historical policy custody and T1 refusal inputs. They
do not establish native execution, provider qualification or historical
multi-image POST execution.
