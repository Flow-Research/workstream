# Retained 0047 cap source

`retained_cap_source.json.gz` contains a checksum-bound fixture for the current
revision-cap recovery test. It is historical setup data, not a supported writer.
The archive contains 71 nonempty tables, two submissions, and the second
submission's blocked revision preparation (round 2, maximum 1).

The capture used detached commit `e2b926288899bcd9b05e1a560ec19b6bca8cfcfc`
and its `_retained_cap_source` fixture. That fixture explicitly adapts source
selection and preparation insertion to the 0047 contract. Its temporary ORM
projection columns were removed before capture. The capture then checked
`0047_revision_recovery`, origin replication mode, and enabled user triggers,
and read the rows in one read-only repeatable-read transaction. These are
guarded historical outcomes, not claims about an untouched current writer.

[Capture source](retained_cap_capture.py.txt) records the one-time operation.
After the real routing effect, the actual authorized dispatcher recorded a
positive retry while its lease was live. The capture used test-only 600-second
leases and one-second retry backoff. The restored test obtains fresh dispatcher
authority and a new invocation of the same completion event; it never extends
archived timestamps or enables unknown replay. Both stored artifact byte strings
are included; the current evaluation request's length and SHA-256 match its ZIP.

The isolated capture passed on schema 0065 with complete database and MinIO
cleanup. The archive itself is at 0047, before that capture run's upgrade.
Current tests restore through the shared exact-row, column-inventory and
foreign-key validator, then compare retained rows through the real upgrade.
Restore is setup and is not credited as executing the historical writer anew.

The checksum is enforced in `migration_revision_fixtures.py`. No retained policy
is relocked: reclaim succeeds, but an incompatible inherited policy refuses new
raw-ZIP intake under specification section 20.2. Compatible-policy reclaim and
new submission remain covered by the current revision-exhaustion tests.
