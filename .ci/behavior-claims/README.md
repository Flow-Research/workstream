# Behavior mutation claims

The hosted behavior-mutation workflow is temporarily retired. These files are
retained as historical design input and are not currently required for pull
requests. Do not infer a blocking check from the policy or examples below.

Schema-v1 claim files provide bounded owning pytest nodes for mutation targets.
They are additive: every eligible changed production or CI-runtime Python target
is selected independently, and a claim cannot remove or replace one.

The filename and `chunk_id` must match. Targets are repository-relative Python
files under `backend/app/` or `backend/scripts/`; each target also names its
qualified callables, exact owning pytest nodes, typed observable outcomes, and
any essential real boundaries. Unknown fields, unsafe paths, missing files,
duplicate entries, unowned changed targets, or stale chunk identifiers fail
closed.

The retired behavior-mutation check discovered the one claim changed by the
pull request; labels, workflow inputs, environment variables, and PR prose
cannot select it. Copy `example.behavior-claim.json`, rename it to the bounded
chunk identifier, and replace every example target, callable, test, outcome,
and boundary. Eligible production changes without exactly one changed claim
fail closed. A test-only behavior claim is additive and cannot remove an
eligible changed target.

The retired check had no mutation percentage. Killed mutants passed. A meaningful
survivor, timeout, suspicious result, engine error, malformed or stale evidence,
target escape, or excluded mutant inside the selected callable scope blocks.
The only surviving control allowed by policy is Workstream's exact deliberately
weak calibration callable; contributors cannot add survivor allowlists,
free-form exemptions, or source mutation pragmas.

Under the retired design, changes with no eligible target and no claim produced typed `not_applicable`
evidence before the mutation toolchain is installed. Ordinary PR verdicts are
calculated by the evaluator and Git-delta helper archived from protected base,
not by PR-head policy code.

Validate claim discovery locally from the repository root:

```bash
backend/.venv/bin/python backend/scripts/mutation_policy.py \
  --repository-root . \
  --base-sha "$(git merge-base origin/main HEAD)" \
  --head-sha "$(git rev-parse HEAD)" \
  --discover \
  --selection-output /tmp/workstream-mutation-selection.json
```

An unrelated delta reports `applicability: not_applicable`. An applicable
delta must report the exact changed targets, callable ownership, and owning
tests expected by the contributor. Discovery errors are policy failures; fix
the claim or delta rather than editing generated evidence.
