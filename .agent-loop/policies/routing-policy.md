# Routing Policy

Classify work before implementation.

## Risk Classes

### L0 - Human-Led Direction

Architecture direction, product direction, data model strategy, payment
architecture, auth model, policy framework, irreversible migrations, or
legal/compliance-sensitive behavior.

No autonomous implementation.

### L1 - Human-Gated Infrastructure

Core infrastructure, orchestration, payment boundaries, permission systems,
policy engines, task lifecycle, audit logs, security-sensitive integrations,
or engineering-loop enforcement.

Task-scoped implementation is allowed only with explicit chunk contracts,
evidence, required reviewers, and human checkpoint.

### L2 - Bounded Engineering

Bug fixes, small refactors, tests, and small feature slices with limited blast
radius.

### L3 - Maintenance

Docs, issue triage, cleanup, small UI copy, formatting, or non-critical
dependency review.

### L4 - Read-Only Automation

Summaries, drift reports, backlog grouping, monitoring, or analysis with no
source edits.

## Reviewer Matrix

The baseline reviewer set is always senior engineering, QA/test, security/auth,
and product/ops unless a chunk contract explicitly marks a track unrelated. The
matrix below adds focused reviewers; it does not replace the baseline set.

| Work type | Risk | Required reviewers |
|---|---:|---|
| Architecture direction | L0 | Human-led plan review |
| Auth/payment/policy/task lifecycle | L1 | QA/test, security/auth, architecture, senior engineering, product/ops, docs |
| Engineering-loop enforcement | L1 | baseline, architecture, CI integrity, docs, reuse/dedup |
| CI/workflow change | L1/L2 | baseline, CI integrity, reuse/dedup when scripts or agent definitions change |
| Bug fix | L2 | QA/test, senior engineering, test delta when tests change |
| Docs-only | L3 | docs, product/ops when operator workflow changes |
| Read-only triage | L4 | no implementation reviewers |
