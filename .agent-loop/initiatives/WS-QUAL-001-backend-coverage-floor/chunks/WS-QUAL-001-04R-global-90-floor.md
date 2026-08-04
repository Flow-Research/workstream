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
Agent Gates pass. The hosted evidence step reads generated
`.ci/test-lanes/coverage.json`, validates integer totals, and fails unless
`covered_lines * 10000 >= num_statements * 9025`. It records both the measured
global percentage and required `90.25` pre-switch percentage in
`hosted-evidence.json` on the exact checked-out head.

Verification commands/evidence:

- `PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py`
- Inspect the workflow diff for the unchanged complete application inventory,
  integer 90.25-percent evidence check, recorded required percentage, global
  `--fail-under=90`, and every existing protected check.
- Full hosted semantic lanes/fan-in and generated coverage/hosted-evidence JSON.
- Test-delta and CI-integrity review.

Required reviewers: senior, QA, CI integrity, test-delta, architecture, docs.
Human focus: exact proof, unchanged application inventory, and no CI weakening.

Stop if the exact candidate measures below 90.25 percent for any reason.
