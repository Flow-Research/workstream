# PR Trust Bundle: WS-ART-001-PLAN4

## Chunk

`WS-ART-001-PLAN4` — planning-only correction for default pre-submission checks.

## Goal

Define one discoverable, versioned, disable-aware catalogue and one effective
pre-submission execution while preserving the exact contributor ZIP custody
chain and locked Project Guide rules.

## Human-Approved Intent

Every submission is one outer ZIP. Workstream default checks and project-specific
checks run as one effective pre-submission operation against that exact ZIP in
bounded private scratch. All platform defaults are named centrally and expose
enabled/disabled state without allowing a mandatory check to be bypassed.

## What Changed

- added 04A4, 04B1, 04B2, and 04B3 chunk contracts;
- superseded the oversized combined 04B contract;
- defined the stable platform catalogue and constrained policy mapping;
- defined fail-closed mandatory disablement and explicit advisory disablement;
- aligned canonical architecture, policy, AUTH, workflow, glossary, and template
  documents with one-ZIP preparation, verified admission, and immutable binding;
- assigned clean removal of the legacy standalone precheck route to 04A4;
- incorporated all seven actionable CodeRabbit findings.

## Why It Changed

The former plan left default checks scattered across constants, compiler
primitives, a legacy registry, and documents; did not safely define `disabled`;
and could leave a caller-owned standalone precheck beside the authoritative ZIP
flow. The combined 04B also crossed too many L1 boundaries for one PR.

## Design Chosen

```text
04A4 legacy precheck clean cut
-> 04B1 sole catalogue + effective-plan compiler
-> 04B2 sealed materialization + platform/default execution
-> 04B3 locked project execution + one bounded evidence set
-> XINT-06A fixed materializer activation
-> 04C durable intent and verified admission
```

The task-locked compiled-bundle hash commits to an immutable catalogue snapshot
and locked project policy. Results use typed provenance; mandatory unavailable
checks yield retryable infrastructure failure rather than findings or success.

## Alternatives Rejected

- retaining the standalone caller-owned precheck route;
- separate platform and project execution APIs or registries;
- scattered conditionals or runtime plugin discovery;
- per-project or per-request default-check toggles;
- treating disabled mandatory checks as skipped/passing;
- a new task-lock column duplicating the compiled bundle's catalogue commitment.

## Scope Control

Planning and canonical documentation only. No route, runtime code, database
migration, provider I/O, AUTH activation/grant, Submission lifecycle, checker
execution, Review, contribution, compensation, or reputation behavior changes.

## Product Behavior

No product behavior changes in this PR. The approved target is one outer ZIP
plus summary/attestation, server-derived manifest/evidence facts, one effective
pre-submission result, verified admission, then atomic immutable Submission
binding under fresh authority.

## Acceptance Criteria Proof

- every default has stable identity/version/classification/order/limits/state;
- exact stable-ID/public-name/typed-capability-or-primitive mappings are
  specified for every platform default and constrained project rule;
- mandatory disabled entries fail closed; advisory disabled entries are explicit;
- project policy cannot disable or weaken platform defaults;
- no independent precheck route or second dispatch registry survives 04A4/04B1;
- audit and contributor results are bounded and path-redacted;
- exact coverage and crossed-state test obligations are assigned to each chunk.

## Tests And Checks Run

- stale artifact contract scan — pass;
- stale authorization docs scan — pass;
- stale Workstream wording scan — pass;
- Markdown links — pass;
- lightweight agent gates — pass;
- `git diff --check` — pass.

## Test Delta

No runtime tests change in this planning PR. The contracts require route/OpenAPI
removal proof, catalogue compiler tests, sealed materialization/executable parity,
crossed-state invalidation, full repository 78 percent coverage, and owned
subsystem 90 percent coverage in their implementation PRs.

## CI Integrity

No workflow, lane, package, lint, or coverage configuration is changed. Existing
hosted gates remain intact; each implementation contract names the exact full
and scoped coverage commands it must preserve.

## Reviewer Results

Architecture, security, QA, product/ops, senior engineering, CI integrity,
documentation, reuse/dedup, and test-delta reviewers pass after all valid
findings were repaired.

## External Review

CodeRabbit posted seven actionable findings and one description warning. All
seven are addressed; the PR description is replaced with this trust-bundle
structure. Detailed disposition is in
`WS-ART-001-PLAN4-external-review-response.md`.

## Remaining Risks

- implementation must consolidate rather than wrap the old registry/compiler;
- broad sensitive-name heuristics need false-positive tests;
- hosted checks must validate the rebased planning head;
- each implementation chunk still requires separate approval and L1 review.

## Follow-Up Work

After human merge: implement only 04A4. Do not start 04B1 automatically.

## Human Review Focus

- mandatory disablement can never become skip-and-pass;
- catalogue mapping and typed provenance form one namespace;
- catalogue snapshot identity is truly task-locked through the bundle hash;
- audit evidence cannot leak paths, credentials, provider details, or raw output;
- contributor evidence remains inside the one ZIP, not a second upload contract.

## Human Merge Ownership

Only the human owner may approve and merge PR #271. This planning merge does
not authorize any implementation chunk.
