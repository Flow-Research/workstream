# Plan: WS-ENG-008 — Repository-Native SDLC Assurance

## Proposed approach

Strengthen the existing loop in dependency order: enforce the contract that
authorizes a diff, independently audit signed memory, formalize adversarial
proof, deepen invariant testing, measure mutation sensitivity, then compact
durable review navigation. Each mechanism lands independently and stops.

## Design chosen

### Forward-ratcheted contract scope

Every implementation/specification start after the `WS-ENG-008-01` merge must
select a contract carrying one strict fenced JSON block; there is no subjective
“material” exception. Chunk 01 also upgrades the already-added ENG-008 contracts
02–07 before it may name 02 as successor. Only chunks already signed-active at
the cutover may finish under an immutable grandfather record bound to the exact
pre-cutover start event and contract blob; stopped, proposed, or newly started
work cannot inherit that exemption. Grandfather records are never
inferred or mass-rewritten. A dedicated parser validates exact keys, canonical
repository-relative patterns, reviewer names, and verification commands. JSON
decoding uses an object-pairs hook (or equivalent) that rejects duplicate object
keys before exact-key and scope validation. Agent Gates compare the PR's
status-aware diff to this block and fail closed on
unmatched, forbidden, renamed, symlinked, submodule, or ambiguous paths.

### Read-only drift audit

A scheduled workflow checks out trusted `main`, fetches
`automation/loop-memory`, runs existing cryptographic and independent semantic
validators, checks main ancestry and active contract bindings, and publishes no
state. It has no signing secret and no write permission. Failure is diagnostic;
recovery remains the existing explicit process.

### Risk-routed adversarial proof

High-risk chunks record attack objective, boundary, method, expected denial,
observed evidence, findings, and untested surfaces. Existing reviewers own the
result through routing; no duplicative universal reviewer or empty findings
file is introduced.

### Bounded property and mutation evidence

Hypothesis is introduced first for pure loop reducers and validators, then for
authorization decision invariants after active AUTH work lands. Profiles are
deterministic and bounded. Mutation testing begins as a changed-module pilot
that reports complete classifications; it cannot weaken coverage or become a
blocking percentage until measured evidence supports a later human decision.

### Lossless review index

Root review history is copied byte-for-byte into versioned archives with a
linkable index. Initiative review directories remain detailed truth. No record
is deleted; future root entries become compact navigation only.

## Alternatives rejected

- Prose-only scope review: insufficiently deterministic.
- Automatic contract generation from the diff: retroactive authorization.
- Scheduled repair: creates a second write/authority path.
- One broad property suite required for every chunk: unbounded runtime and poor ownership.
- Immediate mutation threshold: no calibrated baseline.
- Empty adversarial findings file: proves no attempted attack.
- Destructive review-log rotation: breaks durable memory.

## Boundaries preserved

- No product, API, data, authorization grant, payment, artifact, or review
  lifecycle behavior changes.
- No start/cancel authority, signing key, branch protection, secret, or human
  merge policy changes.
- Existing CI and coverage floors may only be preserved or strengthened after
  measured human approval.
- Concurrent ART/AUTH/REV initiatives retain their scope and merge independently.

## Risk routing

| Chunk | Risk | SLA | Work type | Required reviewers | Human gate |
|---|---:|---:|---|---|---|
| `WS-ENG-008-01` | L1 | P1 | policy/CI | all nine tracks | Explicit PR merge approval |
| `WS-ENG-008-02` | L1 | P1 | workflow/security/operations | all nine tracks | Explicit PR merge approval |
| `WS-ENG-008-03` | L1 | P1 | policy/review evidence | all nine tracks | Explicit PR merge approval |
| `WS-ENG-008-04` | L1 | P2 | loop-security tests/dependency | all nine tracks | Explicit PR merge approval |
| `WS-ENG-008-05` | L1 | P2 | authorization tests/dependency | all nine tracks | Explicit PR merge approval after AUTH reconciliation |
| `WS-ENG-008-06` | L1 | P2 | CI/test dependency pilot | all nine tracks | Explicit PR merge approval and later separate threshold decision |
| `WS-ENG-008-07` | L1 | P2 | durable-memory migration/docs | all nine tracks | Explicit PR merge approval after concurrent log writers reconcile |

Budget posture is careful for every chunk: bounded implementation, deterministic
proof before reviewer fanout, and no automatic successor.

## Dependency and reconciliation order

1. Contract enforcement lands before other assurance work.
2. Drift audit reuses canonical contract parsing and current signed validators.
3. Adversarial proof routing reuses contract reviewer metadata.
4. Loop property tests precede the broader authorization suite.
5. Authorization property work reconciles the then-current canonical AUTH result
   before its separate signed start.
6. Mutation pilot inspects dormant QUALITY patches only as discovery and starts
   from the then-current canonical Backend workflow.
7. Review-log migration waits until active initiatives no longer carry root-log
   changes, then preserves every newly merged entry.

Before each chunk starts, the orchestrator fetches exact `main` and signed state,
checks the target initiative idle, audits concurrent PR path overlap, dispatches
the signed event, verifies its projection, and creates a fresh branch from that
main. Before publication and merge, it repeats base-delta reconciliation and
all contract proof.

## Verification strategy

- Parser and mutation matrices for schemas, paths, diff statuses, and reviewer sets.
- Byte-preserving NUL-delimited Git fixtures for controls, invalid UTF-8,
  non-NFC names, normalization/casefold collisions, and rename/type changes.
- Workflow semantic tests for read-only permissions and absence of repair/signing paths.
- Independent signed-state fixture audits and scheduled-run dry runs.
- Deterministic Hypothesis profiles with replayable failing examples.
- Property suites have hosted hard limits of 120 seconds each, with the exact
  head's elapsed time recorded; mutation execution has a 12-minute command
  limit inside a 15-minute job limit and may add no more than two minutes to the
  existing required Backend critical path because it runs as an independent lane.
- Mutation pilot artifact integrity and survivor-classification tests.
- Byte/digest/link equality for review-log archives.
- Existing Agent Gates, Backend full CI, coverage floors, Markdown links, stale
  wording, internal evidence gate, CodeRabbit, and human review remain required.

## Rollout and rollback

Each merge is forward-only and independently useful. If a new gate is too noisy,
repair it through a new reviewed chunk; do not disable or bypass it. Scheduled
audit failures never mutate state. Mutation evidence remains non-blocking during
the pilot. Archive migration preserves the original bytes, enabling audited
reconstruction without git history dependence.

## Review strategy

All seven chunks are L1 repository-assurance changes and receive senior, QA,
security, product/ops, architecture, CI integrity, docs, reuse, and test-delta
review. Each reviewer receives exact base, implementation SHA, signed start,
contract blob, concurrent-PR overlap report, and deterministic evidence.
