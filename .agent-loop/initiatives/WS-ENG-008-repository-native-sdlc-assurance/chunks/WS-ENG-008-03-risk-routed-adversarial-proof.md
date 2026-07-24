# Chunk Contract: WS-ENG-008-03 — Risk-Routed Adversarial Proof

## Parent initiative

`WS-ENG-008` — Repository-Native SDLC Assurance

## Goal

Require explicit, reviewable bypass attempts and outcomes for high-risk chunks
without adding a duplicative universal reviewer.

## Why this chunk exists

Existing reviewers assess adversarial concerns, but the attempts, expected
denials, observed evidence, and untested surfaces are not represented uniformly.

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

## Allowed files

```text
.agents/skills/risk-router/SKILL.md
.agents/skills/security-review/SKILL.md
.agents/skills/qa-review/SKILL.md
.agents/skills/evidence-gate/SKILL.md
.agent-loop/templates/CHUNK_CONTRACT.md
.agent-loop/templates/PR_TRUST_BUNDLE.md
.agent-loop/templates/ADVERSARIAL_PROOF.md
.agent-loop/policies/routing-policy.md
.github/pull_request_template.md
scripts/check_internal_review_evidence.py
scripts/test_agent_gates.py
CONTRIBUTING.md
AGENTS.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/STATUS.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-03-risk-routed-adversarial-proof.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-03-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-03-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-03-adversarial-proof.md
.agent-loop/merge-intents/WS-ENG-008-03.json
```

## Not allowed

```text
new merge/start/cancel authority or automatic approval
replacement or weakening of any existing reviewer track
empty findings file as proof
runtime penetration, production credentials/data, destructive attack, or external target activity
application, API, database, product lifecycle, or coverage changes
```

## Acceptance criteria

- [ ] Risk router deterministically requires adversarial proof for L0/L1 auth,
      payment, audit/ledger, migration/schema, CI/workflow, signed-loop,
      artifact-custody, data-ownership, secret, and tool-input surfaces.
- [ ] Evidence schema requires attack objective, boundary, safe method, expected
      denial, observed result, proof reference, finding disposition, and untested
      surfaces; an empty or claim-only file fails.
- [ ] Existing reviewer tracks own the proof and cannot all mark the relevant
      security/QA/architecture concern unrelated.
- [ ] Internal evidence and trust templates link the exact adversarial proof for
      routed chunks and preserve reviewed-SHA/post-review rules.
- [ ] Safe local fixture attempts never target production or require credentials.
- [ ] Positive and negative fixtures cover missing attempts, fabricated output,
      unresolved findings, destructive methods, wrong chunk/SHA, and unrouted work.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-008-04` and requires a
      separate explicit start.

## Verification commands

```bash
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
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

- Does the proof show attempted denials rather than an empty compliance claim?
- Is routing bounded enough to avoid duplicating every reviewer on low-risk work?
- Are destructive and external attacks prohibited?

## Stop conditions

Stop if adversarial proof requires production access, destructive tests, a new
authority role, or removal of an existing reviewer.
