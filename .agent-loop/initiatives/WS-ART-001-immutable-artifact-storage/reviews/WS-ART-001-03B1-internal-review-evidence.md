# Internal Review Evidence: WS-ART-001-03B1

Reviewed against trusted main: `e6573aa2`

Reviewed at: `2026-07-29`

## Candidate

Hidden, fail-closed binding of one verified guide-source artifact to one exact
draft-guide setup run and monotonic setup generation. Live binding authority
remains unavailable pending AUTH `WS-XINT-002-04B`.

## Deterministic Evidence

- changed-file Ruff, Python compilation, and `git diff --check`: PASS;
- stale artifact-contract scan and Markdown link check: PASS;
- canonical semantic-lane inventory and Agent Gates: PASS;
- focused tests cover exact replay, denial rollback, missing/unverified and
  cross-lineage rejection, stale generation, concurrency, explicit
  supersession, and populated downgrade refusal;
- migration proof covers deterministic per-guide generation backfill across
  two guides and empty downgrade/re-upgrade;
- hosted Backend run `30438579261` exposed the stale schema fingerprint; the
  exact hosted fingerprint is now committed without weakening the guard;
- hosted Backend run `30439786150` exposed a closed-contract expectation and
  test-fixture FK ordering issue; both were repaired without production or
  threshold changes;
- hosted Backend run `30440684668` enforced the canonical sharded SHA-256
  provider-key shape in the new fixture; the seed now uses that exact shape;
- hosted Backend run `30441301337` enforced the canonical one-active-identity
  invariant for human fixture actors; the seed now creates that verified link;
- the exact final PR head must pass the hosted Backend workflow's four semantic
  lanes, API E2E, repository 78% floor, and existing subsystem 90% gates.

## Reviewer Results

| Reviewer | Result | Blocking findings |
|---|---|---|
| senior engineering | PASS | none |
| architecture | PASS | none |
| QA/test | PASS | none |
| security/auth | PASS | none |
| product/ops | PASS | none |
| reuse/dedup | PASS WITH LOW RISKS | none |
| CI integrity | PASS | none |
| test delta | PASS | none |
| docs | PASS | none |

## Material Repairs

- required immutable verification receipts rather than trusting mutable status
  fields;
- reused canonical repository guide-lineage and staged-admission facts;
- updated the hosted schema fingerprint and API contract setup generation;
- added migration, supersession, downgrade, closed-port, and deterministic seed
  evidence;
- documented setup-generation and guide-binding data contracts.

## Accepted Low Risks

- Binding-specific guide and snapshot reloads overlap slightly with canonical
  lineage lookup, but preserve exact setup-version and snapshot-hash checks.
- The large focused seed helper is intentionally local because it additionally
  constructs verified replica, job, and immutable receipt evidence.

Valid findings addressed: yes

Open sub-agent sessions: none
