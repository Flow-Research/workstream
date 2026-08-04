# Plan: WS-QUAL-001 Behavior And Mutation Assurance

## Approach

Retire the proposed global-90 floor switch and deliver behavior assurance in
two independently reviewed implementation chunks.

### Stage 1: changed-scope mutation pilot

Add one exactly pinned mutation engine and a Workstream-owned policy wrapper.
The wrapper derives a closed set of eligible production targets from the git
delta and always mutates those targets. It then adds any explicit test-only
behavior claims, each with owning test nodes; a claim cannot replace eligible
changed-production mutation. The wrapper selects the smallest owner test set,
runs under a hard timeout, and emits machine-readable exact-head evidence.

The pilot does not block on mutation score. It does block on infrastructure
failure, malformed evidence, target escape, missing claimed tests, ordinary
test failure, or any weakening of existing Backend checks. Pilot results must
distinguish killed, survived, timeout, suspicious, excluded, and error mutants.

`mutmut` is the leading pilot candidate because its current documentation
supports pytest-aware test selection, function/module wildcards, incremental
results, parallel execution, source/selection configuration, covered-line
filtering, and Python 3.11/3.12. The implementation chunk must still prove a
pinned release against Workstream's async pytest and isolated-service setup;
planning does not pre-approve an unusable dependency.

### Stage 2: blocking behavior-mutation gate

Only after pilot review, add a separate required check for eligible changed
production logic and test-only PRs that claim behavioral improvement. The gate
uses the pilot's deterministic target and evidence grammar.

There is no repository-wide mutation percentage. The policy must enumerate
every engine status, including killed, survived, suspicious, timeout, tool
error, and excluded. Each status either blocks or maps to an independently
verified, typed classification accepted by policy (for example, demonstrably
equivalent or non-behavioral). Missing, stale, broad, free-form, or unrecognized
classifications fail closed. No status may pass implicitly.

## Behavior ownership

A qualifying behavior claim identifies:

- production module and callable or bounded target;
- owning test nodes;
- observable contract (return, persisted state, emitted fact, denial, mapped
  error, idempotent replay, or recovery outcome);
- relevant real boundary, if PostgreSQL, MinIO, HTTP, lock, trigger, or
  concurrency is essential.

The canonical input is a schema-v1 JSON file at
`.ci/behavior-claims/<chunk-id>.json`, validated by a repository-owned schema
and policy parser. Chat, PR prose, labels, workflow inputs, and environment
variables cannot widen targets. Behavior claims contain repository-relative
production targets, qualified callables, owning pytest node IDs, and typed
observable outcomes. Test-only non-behavioral maintenance uses a narrow typed
classification defined by policy rather than free-form exemption text.

Test-only changes that claim coverage or stronger behavior must provide this
mapping. Fixture-only changes are non-behavioral only when policy evidence
proves they cannot affect test selection, test inputs, or assertion behavior;
otherwise they require a bounded behavior claim. Documentation-only,
generated-code, and independently verified non-behavioral maintenance changes
remain outside mutation selection but subject to ordinary tests and review.

## Runtime and isolation strategy

- Never mutate the full backend in ordinary PR CI.
- Start with pure or direct-service logic whose owning tests avoid PostgreSQL
  and HTTP unless those boundaries are the behavior being proved.
- Run mutation work independently from the existing Backend critical path.
- Pilot command limit: 12 minutes inside a 15-minute job limit.
- A blocking rollout must demonstrate a practical hosted p95 and cannot extend
  required PR latency by more than two minutes when run in parallel.
- Mutation caches are acceleration only; evidence binds the exact source,
  configuration, selected tests, tool version, and result set.

## Dependency and evidence integrity

- Pin the selected engine and its transitive dependency closure with hashes.
- Do not add the mutation engine to production dependencies.
- Obtain the approved mutation package, version, and hash authority from the
  protected base revision, an equivalently protected allowlist, or a protected
  prebuilt runtime—never from a manifest editable by the pull request. If
  `scripts/mutation-requirements.txt` is used, install only from its trusted
  base-revision copy with `pip install --require-hashes`;
  `backend/pyproject.toml` may contain tool configuration but cannot add the
  engine to ordinary dev extras.
- Never apply mutants to the contributor worktree in CI.
- Upload bounded result evidence without source secrets, environment values,
  database contents, or artifact payloads.
- The policy wrapper, not mutable PR prose, determines eligibility and validates
  results.
- Mutation CI runs only on an unprivileged `pull_request`/`push` boundary with
  explicit read-only permissions, pinned Actions, checkout credentials
  disabled, no secrets or writable token in the mutation subprocess, and
  bounded non-restorable artifacts/caches.

## Alternatives rejected

- `WS-QUAL-001-04R` global floor switch: superseded before implementation.
- Full-suite-per-mutant execution: too slow and poorly owned.
- Score-only gating: hides which behavior remains unproved.
- Non-blocking forever: measures quality without protecting it.
- Immediate blocking rollout: lacks runtime and equivalent-mutant calibration.
- Mutating only covered lines as the sole eligibility rule: can hide untested
  changed behavior; covered-line filtering may optimize the pilot but cannot
  define the full policy.

## Verification strategy

Each implementation chunk runs focused policy tests, mutation-engine smoke
tests, Ruff, Agent Gates, Markdown/stale scans, internal reviewer tracks, and
hosted Backend. The pilot additionally proves at least one known strong test
kills its representative mutants and at least one deliberately weak test leaves
a representative mutant alive. The blocking chunk proves survivors, timeouts,
errors, missing evidence, stale evidence, and target escape all stop the gate.

## Dependency order

`PLAN3 -> PLAN3R1 -> 04M pilot -> human calibration checkpoint -> 05M blocking
gate`.
`05M` cannot begin from planning alone; it requires accepted exact hosted pilot
evidence and a new explicit human instruction.

## Stop

Planning does not install a mutation engine, change a workflow, or change a
coverage threshold. Stop after the PLAN3R1 correction PR and human checkpoint.
