# Decisions: WS-CI-004 Review Evidence Integrity

## D1: Review evidence is not authority

GitHub permissions and branch protection govern contribution. Human approval
governs merge. Internal review records cannot start, block, recover, or complete
initiative work by themselves.

## D2: Bind every pass to a subject

The minimum review subject is base SHA, merge-base SHA, and reviewed head SHA.
A verdict without that identity is not final-head evidence.

## D3: Separate subject, evidence, and verdict

Commit identity proves what was reviewed, evidence provenance explains what was
observed, and the reviewer verdict expresses a bounded conclusion. None may be
inferred from another.

## D4: Reuse the old evidence core, not the old control system

Exact SHA, timestamp, run references, closed results, and stale-delta detection
are reusable. Signed starts, leases, merge intents, loop memory, recovery
certificates, successor dispatch, and machine authorization are excluded.

## D5: One shared protocol, specialty extensions

Universal reviewer rules live in one mandatory skill. Specialty agents and
skills add focused questions and must not fork the provenance/freshness model.

## D6: Proportionate invalidation and convergence

A head change invalidates deterministic evidence and every reviewer whose paths,
boundaries, findings, or evidence claims are affected. Unaffected specialties do
not repeat ceremony. Base changes always require effective-delta reconciliation.
Readiness requires all required results to converge on one
`{base_sha, merge_base_sha, head_sha}` triple.

## D7: No hosted receipt gate

This initiative ends at local session convergence. It does not create durable
receipt custody, a trusted issuer, a hosted validator, or a blocking evidence
gate.

## D8: Human review remains essential

Exact-head provenance prevents stale or ambiguous passes; it does not prove the
reviewer was correct. Independent sensors and human judgment remain mandatory.

## D9: Session receipt custody

The orchestrator alone writes create-once JSON receipts beneath the Git common
directory, keyed by review target, run, and specialty. Target changes create new
receipts; prior receipts are never rewritten. GitHub remains durable custody.

## D10: One receipt shape and one target model

The existing internal-review-evidence and review-finding templates are extended
in place as the session receipt/ledger shape. The shared protocol skill is the
instruction source. The proposed convergence step must consume the target model
from the first implementation step; it must not reimplement `scripts/git_delta.py`
resolution or closed-result semantics.
