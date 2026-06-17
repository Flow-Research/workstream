# Engineering Review Policy

AI review is a sensor, not a verdict. Human merge ownership remains required.

## Stages

```text
1. Evidence gate
2. Required Codex internal reviewer agents
3. External review such as CodeRabbit or GitHub review
4. Human checkpoint
```

## Required Internal Tracks

Every implementation or specification chunk requires:

- senior engineering
- QA/test
- security/auth
- product/ops

Add focused reviewers when relevant:

- architecture for boundary or abstraction changes
- CI integrity for workflow, test, lint, or coverage changes
- docs for public behavior, onboarding, ADR, or process changes
- reuse/dedup for helpers, shared contracts, or duplicated logic
- test delta for changed tests

## Severity

- Critical: security incident, data loss, payment/auth bypass, production outage,
  irreversible corruption, or major architecture damage.
- High: likely correctness bug, missed acceptance criterion, serious test gap,
  architecture boundary violation, or unsafe operational behavior.
- Medium: reliability, maintainability, edge-case, or documentation issue that
  requires a human decision.
- Low: minor cleanup or clarification.
- Informational: observation only.

Critical and High findings block the PR. Medium findings require a human
decision. Low and Informational findings may be deferred when documented.
