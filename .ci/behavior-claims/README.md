# Behavior mutation claims

Schema-v1 claim files provide bounded owning pytest nodes for mutation targets.
They are additive: every eligible changed production or CI-runtime Python target
is selected independently, and a claim cannot remove or replace one.

The filename and `chunk_id` must match. Targets are repository-relative Python
files under `backend/app/` or `backend/scripts/`; tests are exact pytest nodes
under `backend/tests/`. Unknown fields, unsafe paths, missing files, duplicate
entries, or stale chunk identifiers fail closed.

During the `WS-QUAL-001-04M` pilot, results are observational. Infrastructure,
custody, selection, baseline-test, or evidence failures remain blocking, but no
mutation percentage is a contributor requirement until a later human-approved
policy chunk.
