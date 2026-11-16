# Retained multi-image POST fixture

These synthetic rows originate at commit
`94334ccf4085c26c7bfaa054465fc05cfbdad1fc`, schema
`0068_issuer_profile_email`. They preserve an already accepted revision under a
historical policy with two POST bindings. Current approvals must select exactly
one image per phase; the fixture does not provide an old approval implementation.

The [capture observer](multi_post_capture.py.txt) was appended to the original
`tests/checkers/external/test_revision_materialization.py` in a detached checkout.
The original source bytes were unchanged. For each role combination, the observer
records all nonempty public tables and both exact MinIO objects immediately before
successor POST execution. It writes the snapshot only after the original test
passes its execution, visibility, SQL custody, cleanup, replay and denial assertions.
Run `-k capture_retained_multi_post` through the isolated test runner at that commit
with an owned local MinIO endpoint. Recapture changes timestamps and identifiers
and requires review; it is not byte-for-byte reproducible.

The gzip archive uses canonical sorted JSON and `mtime=0`. Its checksum is pinned
in `tests/historical_revision_material_fixtures.py`. The loader validates source,
role configuration, captured object hashes/sizes and retained replica references.
The existing owned-database restore helper reinstates and checks triggers and
foreign keys before upgrading. The current coordinator then re-reads the accepted
request and must return exactly the captured request.

Current execution uses production authorization, materialization and checker
owners with a bounded read-only captured-byte store and controlled intake/image
adapters. Exact references have no fallback, and production digest, size and
manifest checks remain enabled. The captured namespace is unchanged: its MinIO
endpoint identity is immutable and cannot be repointed to a different CI endpoint.
This proves retained execution and per-binding isolation, not current MinIO,
SmolVM or AWS qualification. A current real-MinIO single-image revision journey
remains a separate required proof.

All three role combinations have successful original captures: findings only,
archive only, and both. Each contains 71 nonempty tables, 388 rows and two objects.
The first findings-only attempt cancelled during scratch reservation; the
unchanged single-case replay passed. No deadline or storage limit was relaxed.
Both capture runs completed database, role and MinIO cleanup. All three
current-schema upgrade and execution replays passed, with complete isolated
database/role cleanup. The final archive includes the same exact two snapshots
from the first replay and the separately verified findings-only snapshot.

Archive SHA256: `acde3375a3e96603868480fff9ffbb4492fe62ef3a89f9348e2ac9caddaae552`.

Capture observer SHA256: `1db5be2b35b4ef1380f46697a58ae4401760a5501f4efe9a57ac2ada8e70e623`.
