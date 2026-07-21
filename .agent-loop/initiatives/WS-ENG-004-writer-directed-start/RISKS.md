# Risks: Writer-Directed Workstream Start

- Risk class: L1
- SLA: P1
- Work type: CI/workflow, policy, audit-ledger recovery
- Required reviewers: senior engineering, QA/test, security/auth, product/ops,
  architecture, CI integrity, docs, reuse/dedup, and test delta
- Human gate: explicit approval of the specific PR before merge; no additional
  admin or environment approval for start
- Budget posture: correctness-first with focused deterministic tests before the
  full agent gate

The start path is policy and audit sensitive. All selection must resolve from
exact trusted main, all active work must be excluded globally, and recovery must
be exact, ephemeral, self-consuming, and unusable after reconciliation.
