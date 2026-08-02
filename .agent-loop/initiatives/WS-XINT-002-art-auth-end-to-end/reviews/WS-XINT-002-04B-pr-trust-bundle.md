# PR Trust Bundle: WS-XINT-002-04B

## Chunk

`WS-XINT-002-04B` — guide binding and guide read authorization activation.

## Goal and human-approved intent

Activate exactly `artifact.guide_source.binding.create` for
`workstream.artifact.binding` and `artifact.guide_source.read` for
`workstream.artifact.guide_reader`, preserving exact transaction, identity,
lineage, verified-content, and no-provider-I/O-on-denial guarantees.

## What changed and why

- Added closed typed binding/read resource contexts to the existing PREP kernel.
- Reconciled the two catalogue rows to active `WS-XINT-002-04B` custody.
- Added production fixed-service adapters using the existing opaque single-use
  `PreparedAuthorizationHandle` protocol.
- Removed the impossible caller-supplied read handle. The materializer obtains
  fresh authority in its owned session and holds exact lineage locks through the
  protected provider read and atomic classification write.
- Added exact digest evidence and fixed runtime/docs/custody parity.

## Design chosen

Reuse centralized PREP with two closed contexts and fixed service identities.
Binding retains the caller-owned transaction. Reading prepares and consumes
inside the materializer-owned transaction because handles cannot cross sessions.
The protected read holds canonical lineage locks through provider access.

## Alternatives rejected

- Serializable or reconstructable handles: violates opaque process-local PREP.
- Preparing the read in an earlier worker/session: violates transaction binding.
- Committing authorization before provider access and revalidating afterward:
  leaves a stale-lineage race.
- Generic download or role-derived service authority: violates least privilege.

## Scope control and product behavior

No new action/permission identifiers, migration, route, Celery payload,
submission/checker/review authority, generic download, parser behavior, or
ART-03C legacy cutover. Project Managers retain ingest only; neither human nor
Admin authority implies binding/read service authority.

## Acceptance proof and test delta

- Exact typed facts, action/service matrix, session/transaction, single-use,
  copied/wrong handle, replay, wrong service, human substitution, every adapter
  fact mismatch, cross-resource selectors, stale generation, wrong content, and
  wrong logical role are covered.
- Denial tests assert no provider read, binding, classification, or allowed
  evidence where applicable.
- Architecture tests prove materialization requests carry identifiers and an
  idempotency key, never a prepared handle.
- No tests were skipped, deleted, or weakened. The prior post-read stale-incident
  expectation was replaced by the stronger lock-through-provider invariant.

## Tests/checks run

- `ruff check app tests scripts`: passed.
- `pytest tests/test_artifact_architecture.py -q`: 20 passed.
- Focused `tests/test_authorization.py` guide/custody/service cases: passed.
- Stale AUTH docs, stale ART contracts, Markdown links, and diff check: passed.
- Hosted full Backend coverage and database-backed guide tests: required on the
  exact PR head.

## CI integrity

No workflow, dependency, package script, test config, skip/xfail, coverage
threshold, or fail-open changes.

## Reviewer results

Security, architecture, QA, senior engineering, product/ops, CI integrity,
docs, reuse/dedup, and test-delta tracks pass after all blocking findings were
resolved. Details are in `WS-XINT-002-04B-internal-review.md`.

## External review

PR #244 is merged and PR #245 now targets `main`. Every valid CodeRabbit finding
was fixed, the one stale fact-model finding was rejected with code evidence, and
all seven review threads are resolved. A fresh CodeRabbit invocation was
requested but rate-limited, so the existing review and recorded dispositions
remain the external review evidence. Hosted exact-head Backend coverage remains
required before readiness.

## Remaining risks and follow-up work

- Holding lineage locks through bounded provider I/O is intentionally strict and
  operationally heavier; ART-03C worker tuning must preserve deadlines.
- If more ART internal resource contexts are added, consolidate the small
  prepared/kernel mapping registries.
- ART-03C later owns live worker/route composition and legacy-path removal.

## Human review focus and merge ownership

Review exact fixed identities, full fact manifests, lock-through-read ordering,
atomic decision evidence, no human inheritance, and the absence of ART-03C scope.
Human approval owns every merge.
