# Operations Review

Review scope: markdown docs only.

## Findings

### High: Revision rebuttal path needs a clearer state

The operator workflow says rebuttal is allowed when a finding is wrong, but the reviewer workflow does not define how a rebutted finding is closed or kept open.

Suggested change: define finding closure states and the rule for rebutted findings.

### High: Compensation fulfillment reconciliation needs an operating cadence

The compensation fulfillment ledger is modeled, but operations need a simple
daily/weekly reconciliation process so authorized but unfulfilled awards do not
drift.

Suggested change: add compensation fulfillment reconciliation cadence and
required report fields.

### Medium: Reviewer independence rule is missing

The plan should prevent submitters from reviewing their own submissions and should make second review optional by project policy.

Suggested change: add reviewer independence constraints.

### Medium: Checker failures should produce operator-facing fix instructions

Checker result schema has a message field, but operationally each failure should include a suggested fix. This reduces repeated confusion.

Suggested change: add `suggested_fix` to checker result contract.
