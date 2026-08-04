# Chunk Contract: WS-CON-001-PLAN4 - Current-Main Reconciliation

## Goal and risk

Reconcile WS-CON-001 planning with current merged ART, AUTH, REV, XINT, and CON
state; remove stale sequencing; and publish the next bounded runtime contracts.
Planning/documentation risk only. No implementation is authorized by this
chunk.

## Allowed files

```text
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-PLAN4.json
.agent-loop/REVIEW_LOG.md only WS-CON-001-PLAN4 review result
docs/spec_contribution_compensation.md only Required Implementation Order
```

## Not allowed

```text
backend or frontend runtime
migrations, workflows, CI, dependencies, unrelated specification sections
AUTH, ART, REV, or XINT initiative files
roadmap/export files or archival reference inputs
```

## Acceptance criteria

- [ ] Baseline is current `main` and distinguishes merged runtime from open PRs
  and historical planning.
- [ ] ART, AUTH, REV, and CON ownership and runtime gaps are explicit.
- [ ] The chunk map no longer makes the dispatcher a prerequisite for
  persistence or the flush-only lifecycle audit participant.
- [ ] `03B` explicitly supplies the policy-version FK target needed by REV
  lease persistence, while `02C` precedes the REV FinalAcceptance transaction.
- [ ] Dispatcher and protected executors remain blocked on independent AUTH
  fixed-service action/admission contracts.
- [ ] Immediate runtime work is bounded to `03A`; no later chunk starts
  automatically.
- [ ] The pre-existing reference-PDF deletion is not modified or staged.

## Verification

```bash
git diff --check
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 -m unittest -v scripts.test_lightweight_agent_gates
```

Inspect the diff for scope, current SHAs, mutable PR language, dependency
direction, and the absence of runtime edits.

## Review and stop

Required review covers senior engineering, QA, security/auth, product/ops,
architecture, docs, reuse, CI integrity, and test delta. Resolve or record every
valid finding. Stop after the reviewed planning package; do not implement
`03A` in this chunk.
