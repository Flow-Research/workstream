# Automation Policy

Automation may discover, classify, summarize, draft, scaffold, and check.

Automation may not merge.

Automation may not begin the next L1 chunk without explicit user approval.

## Safe Automation

- stale wording scans
- Markdown link checks
- internal review evidence checks
- static gate reports
- PR trust bundle drafting
- reviewer comment grouping
- architecture drift reports

## Restricted Automation

- auth, permission, payment, policy, migration, lifecycle, or CI changes
- dependency replacement
- schema changes
- production deployment changes
- automated merge

Restricted automation requires an approved chunk contract and reviewer coverage.
