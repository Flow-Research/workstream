# RISKS: WS-ENG-003

- Risk: L1; SLA: P0; work type: workflow/audit-ledger recovery.
- Recovery activation from the wrong merge must fail closed.
- Exemptions must bind exact initiative, chunk, and PR identities.
- The recovery self-exemption must be derived from trusted GitHub merge evidence.
- No recovery exemption may remain after processing the recovery merge.
- Required reviewers: senior, QA, security, product/ops, architecture, CI, docs, reuse, test delta.
