# Behavior Ownership Catalogue

This directory holds reviewed engineering evidence about which exact tests own
which executable behavior. It does not grant Workstream product authority and
does not currently activate mutation testing.

`partition.v1.json` is the sole target-to-population-group partition. It lists
every eligible non-`__init__` Python target exactly once, binds the protected
base commit used to create it, and carries a digest over that authority data.
Population work must load this artifact from protected `main` or the approved
foundation commit. A branch-local replacement, relocation, duplicate, wildcard,
or digest mismatch fails validation.

Catalogue records belong under one group directory: `auth/`, `artifacts/`,
`lifecycle/`, or `shared/`. The JSON Schema is
[`scripts/behavior-ownership.schema.json`](../../scripts/behavior-ownership.schema.json).
Examples are illustrative only and never count as reviewed ownership.

Statuses are deliberately separate:

- `candidate` is deterministic discovery output awaiting human review.
- `reviewed` binds exact AST callables, collected pytest nodes, observable
  outcomes, real boundaries, and reviewers.
- `structural_only` requires a reviewed reason and is valid only when the target
  has no executable callable or module-level runtime behavior. Calls, branches,
  loops, raises, awaits, mutation, I/O, SQL, validators, and other runtime side
  effects fail validation. Structural records cannot contain callable or test
  fields.

Run the tooling from `backend/`:

```bash
.venv/bin/python -m scripts.behavior_ownership inventory
.venv/bin/python -m scripts.behavior_ownership generate --group auth
.venv/bin/python -m scripts.behavior_ownership validate
```

Validation reports unresolved targets while the catalogue is being populated.
An empty catalogue is therefore explicit and non-authoritative, not silently
complete.
