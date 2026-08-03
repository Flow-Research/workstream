# Chunk Contract: WS-QUAL-001-04R — Global 90 Percent CI Floor

Parent initiative: `WS-QUAL-001`

Goal: after exact hosted proof at or above 90.25 percent, change the canonical
global Backend floor from 78 to 90 and update its lightweight invariant.

Risk: L1 CI policy; P1.

Allowed files:

- `.github/workflows/backend.yml`
- `scripts/test_lightweight_agent_gates.py`
- `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**`

Not allowed: test/application/dependency changes, coverage inventory narrowing,
protected-floor removal, workflow bypass, or unrelated CI optimization.

Acceptance: current exact head proves >=90.25%; global `--fail-under=90` blocks;
all existing protected 90-percent checks remain; complete hosted Backend and
Agent Gates pass.

Verification: lightweight gates, workflow inspection, full hosted semantic
lanes/fan-in, complete coverage report, test-delta and CI-integrity review.

Required reviewers: senior, QA, CI integrity, test-delta, architecture, docs.
Human focus: exact proof, unchanged application inventory, and no CI weakening.

Stop if the exact candidate measures below 90.25 percent for any reason.
