# Behavior mutation claims

The hosted behavior-mutation workflow is temporarily retired. These files are
retained as historical design input and are not currently required for pull
requests. The claim-discovery and fail-closed rules below describe the retired
design only; do not infer a blocking check from them. Behavior-mutation
enforcement must not resume until a fresh changed-line-aware plan is approved
and proves that unchanged executable lines cannot block a declaration-only
change.

Historically, schema-v1 claim files provided bounded owning pytest nodes for
mutation targets. They were additive: every eligible changed production or
CI-runtime Python target was selected independently, and a claim could not
remove or replace one.

Under that retired design, the filename and `chunk_id` had to match. Targets
were repository-relative Python files under `backend/app/` or
`backend/scripts/`; each target also named its
qualified callables, exact owning pytest nodes, typed observable outcomes, and
any essential real boundaries. Unknown fields, unsafe paths, missing files,
duplicate entries, unowned changed targets, or stale chunk identifiers failed
closed.

The retired behavior-mutation check discovered the one claim changed by the
pull request; labels, workflow inputs, environment variables, and PR prose
could not select it. Contributors copied `example.behavior-claim.json`, renamed
it to the bounded chunk identifier, and replaced every example target,
callable, test, outcome, and boundary. Eligible production changes without exactly one changed claim
failed closed. A test-only behavior claim was additive and could not remove an
eligible changed target.

The retired check had no mutation percentage. Killed mutants passed. A meaningful
survivor, timeout, suspicious result, engine error, malformed or stale evidence,
target escape, or excluded mutant inside the selected callable scope blocked.
The only surviving control allowed by policy was Workstream's exact deliberately
weak calibration callable; contributors could not add survivor allowlists,
free-form exemptions, or source mutation pragmas.

Under the retired design, changes with no eligible target and no claim produced
typed `not_applicable`
evidence before the mutation toolchain was installed. Ordinary PR verdicts were
calculated by the evaluator and Git-delta helper archived from protected base,
not by PR-head policy code.

For historical diagnostics only, claim discovery can still be inspected locally
from the repository root:

```bash
backend/.venv/bin/python backend/scripts/mutation_policy.py \
  --repository-root . \
  --base-sha "$(git merge-base origin/main HEAD)" \
  --head-sha "$(git rev-parse HEAD)" \
  --discover \
  --selection-output /tmp/workstream-mutation-selection.json
```

Under the retired design, an unrelated delta reported
`applicability: not_applicable`. An applicable delta reported the exact changed
targets, callable ownership, and owning tests expected by the contributor.
This command does not produce active PR evidence or authorize reactivation.
