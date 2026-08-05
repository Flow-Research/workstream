# WS-QUAL-001-05M External Review Response

## CodeRabbit review on `12bb1d96`

Four substantive findings were accepted and fixed:

1. Plain, undecorated class headers are always executable spans, so a class
   rename cannot escape callable ownership.
2. Protected blocking capability detection uses the explicit
   `workstream-mutation-capability:discover-v1` marker rather than argparse
   source formatting.
3. Deleted eligible targets fail closed with `deleted_eligible_target`; absent
   executable logic cannot be mutated and cannot be classified as unrelated.
4. Generated TOML reparse failures become
   `invalid_generated_mutation_config` rather than escaping with a traceback.

The valid test suggestions were also applied: preserved non-mutmut TOML,
nested-function ownership, independent module-level/deleted-callable guards,
and missing owner-target rejection now have regressions.

The suggested owner-record refactor was not applied because it was explicitly
low value and would increase review surface without changing the corrected
behavior. The textual TOML rewrite remains fail closed; typed failure is the
required safety property for unsupported legacy shapes.

Exact-head hosted CI and CodeRabbit rereview remain required after publication.
