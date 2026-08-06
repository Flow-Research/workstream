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

## PR #289 retirement review on `54cd358a`

Comments addressed:

- Rewrote the PR description using the complete repository trust-bundle
  template so its title, intent, scope, evidence, reviewer results, deliberate
  workflow retirement, remaining risk, and follow-up boundary match the final
  diff.
- Added the same reactivation guard to `CONTRIBUTING.md`, the behavior-claim
  guide, and the Backend operations guide: enforcement cannot resume without an
  approved fresh changed-line-aware plan proving unchanged executable lines do
  not block declaration-only changes.
- Reworded the remaining claim-discovery and fail-closed guidance as historical
  behavior rather than an active contribution requirement.

Comments deferred:

- Two mutation-policy inline threads are outdated because the referenced
  implementation was fully reverted and is absent from the final PR diff.

Human decisions needed:

- A repository administrator must remove the retired check from external
  branch-protection settings if it was configured there.

Commands rerun:

```text
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

Remaining risks:

- Behavior mutation is no longer enforced in hosted CI. Reintroduction requires
  the separately approved changed-line-aware design recorded in current status.
