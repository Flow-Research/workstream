# Chunk Contract: WS-ENG-008-02 — Scheduled Signed-State Drift Audit

## Parent initiative

`WS-ENG-008` — Repository-Native SDLC Assurance

## Goal

Independently and periodically verify signed loop-memory custody and semantic
consistency without granting the audit any repair or write capability.

## Why this chunk exists

Merge and start workflows validate state during events, but later corruption or
out-of-band drift currently has no scheduled detection path.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Start phase

`implementation`

## Machine-checkable scope

```chunk-scope-json
{
  "schema_version": 1,
  "chunk_id": "WS-ENG-008-02",
  "phase": "implementation",
  "risk_class": "L1",
  "allowed_paths": [
    ".github/workflows/loop-memory-drift-audit.yml",
    "scripts/audit_loop_memory_drift.py",
    "scripts/test_audit_loop_memory_drift.py",
    "scripts/test_agent_gates.py",
    "docs/operations_post_merge_memory.md",
    ".agent-loop/policies/repository-engineering-policy.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/STATUS.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-02-scheduled-signed-state-drift-audit.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-02-internal-review-evidence.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-02-pr-trust-bundle.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-02-external-review-response.md",
    ".agent-loop/merge-intents/WS-ENG-008-02.json"
  ],
  "forbidden_paths": ["backend/**", "frontend/**"],
  "required_reviewers": ["senior engineering", "qa/test", "security/auth", "product/ops", "architecture", "ci integrity", "docs", "reuse/dedup", "test delta"],
  "verification_commands": ["loop-memory-drift-tests", "agent-gate-tests", "markdown-links", "stale-wording", "git-diff-check"]
}
```

## Allowed files

```text
.github/workflows/loop-memory-drift-audit.yml
scripts/audit_loop_memory_drift.py
scripts/test_audit_loop_memory_drift.py
scripts/test_agent_gates.py
docs/operations_post_merge_memory.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/STATUS.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-02-scheduled-signed-state-drift-audit.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-02-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-02-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-02-external-review-response.md
.agent-loop/merge-intents/WS-ENG-008-02.json
```

## Not allowed

```text
write permissions, signing keys, state publication, repair, replay, dispatch, approval, or merge behavior
changes to loop-memory reducers, signer, generated schema, start/cancel authority, or branch protection
application or product subsystem reachability checks
external notification credentials
coverage, test, review, or human gate weakening
```

## Acceptance criteria

- [ ] Scheduled and manually dispatchable workflow runs only trusted default-
      branch code with read-only contents/actions permissions and pinned actions.
- [ ] The job receives no signing secret, persists no credentials, and contains
      no push, dispatch, replay, publish, apply-event, sign-state, or repair path.
- [ ] Audit verifies signature, manifest digests, exact closed tree, independent
      semantic state, ledger chain, projections, current-main ancestry, and
      active contract path/blob/heading/phase binding.
- [ ] Main or automation advancement during the audit is reported distinctly
      from cryptographic or semantic corruption; no partial result is success.
- [ ] Missing branch, invalid key, shallow history, symlink/gitlink, extra file,
      ledger collision, stale projection, duplicate active chunk, and broken
      contract reference fail closed in fixtures.
- [ ] Workflow and script have bounded timeouts/output and produce diagnostic
      artifacts containing no secret or mutable authority.
- [ ] Existing merge/start validation and recovery instructions remain canonical.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-008-03` and requires a
      separate explicit start.

## Verification commands

```bash
python3 scripts/test_audit_loop_memory_drift.py
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

- Is the audit structurally incapable of writing or repairing state?
- Are advancement races distinguished from corruption without accepting either blindly?
- Does it reuse, rather than fork, canonical signature and semantic validation?

## Stop conditions

Stop if the audit needs a write token, signing secret, generated-state edit, or
new recovery path.
