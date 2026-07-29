# Internal Review Evidence: WS-ART-001-03B3A

Reviewed against trusted main: `93ec3fbb`

Reviewed at: `2026-07-29`

## Candidate

Hidden, bounded extraction framework for verified guide text, Markdown, JSON,
and CSV with exact provenance, deterministic successful content, and no agent,
provider-write, Celery, submission, or AUTH activation behavior.

## Deterministic Evidence

- changed-file Ruff, mapper configuration, Python compilation, and
  `git diff --check`: PASS;
- focused extraction plus architecture tests: 41 passed;
- real default-deny seccomp probes deny network, file opens, filesystem writes,
  and process creation after trusted imports;
- real child probes cover CPU, wall, memory, and abnormal executor outcomes;
- schema-contract coverage includes successful extraction/usage, extracted-
  attempt fencing, retry outcomes, and populated downgrade refusal;
- stale artifact-contract and Markdown-link scans: PASS;
- exact hosted Backend and Agent Gates remain required on the PR head.

## Reviewer Results

| Reviewer | Result | Blocking findings |
|---|---|---|
| senior engineering | PASS WITH LOW RISKS | none |
| architecture | PASS WITH LOW RISKS | none |
| QA/test | PASS WITH LOW RISKS | none |
| security/auth | PASS WITH LOW RISKS | none |
| product/ops | PASS WITH LOW RISKS | none |
| reuse/dedup | PASS WITH LOW RISKS | none |
| CI integrity | PASS WITH LOW RISKS | none |
| test delta | PASS WITH LOW RISKS | none |
| docs | PASS | none |

The CodeRabbit/hosted-CI repair delta was re-reviewed by senior engineering,
architecture/reuse, QA/test-delta, security, product/ops, and CI/docs. All
tracks pass after one valid legacy-ledger compatibility blocker was repaired
with exact prior-v2 normalization and restart coverage.

## Material Repairs

- replaced default-allow syscall denial with a default-deny allowlist;
- serialized guide generation and shared-content publication through canonical
  row locks;
- revalidated digest, size, media type, detector, binding, run, and generation;
- fenced successful usage to an exact `extracted` attempt in PostgreSQL;
- added cleanup-tracked scratch workspaces and post-launch child reaping;
- added a durable two-slot exact-lineage materialization budget so only
  executor failure or current-lineage cancellation may retry;
- moved destructive resource probes out of the production worker.

## Accepted Low Risks

- A later complex-format chunk should make the registry explicitly table-driven.
- The existing and extraction lineage queries remain similar but not yet
  identical enough to justify a shared selector.
- Hosted PostgreSQL concurrency and repository coverage gates remain the final
  publication proof.

Valid findings addressed: yes

Open sub-agent sessions: none
