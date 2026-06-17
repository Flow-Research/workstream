# Chunk Contract: WS-ENG-001-01 - Codex-Native Zero-Trust Loop Bootstrap

## Parent Initiative

`WS-ENG-001` - Codex Zero-Trust Loop Bootstrap

## Goal

Install the Workstream engineering loop in Codex-native repo surfaces while
preserving Workstream's existing product architecture and review rules.

## Risk Class

L1 - human-gated infrastructure.

## SLA

P1 - same day.

## Allowed Files

```text
AGENTS.md
.agents/skills/**
.codex/**
.agent-loop/**
.github/pull_request_template.md
.github/workflows/agent-gates.yml
scripts/check_internal_review_evidence.py
scripts/check_markdown_links.py
scripts/check_stale_workstream_wording.py
scripts/test_agent_gates.py
scripts/workstream_agent_gate.py
docs/operations_subagent_review_protocol.md
docs/internal_reviews/**
README.md
```

## Not Allowed

```text
backend/app/**
backend/alembic/**
backend/tests/**
demos/**
docker-compose.yml
Workstream product lifecycle behavior
database schema
API behavior
frontend implementation
Claude-specific files
```

## Acceptance Criteria

- [ ] Codex-discoverable skills exist under `.agents/skills/`.
- [ ] Codex custom reviewer agents exist under `.codex/agents/`.
- [ ] Product/Ops reviewer is first-class.
- [ ] Durable loop policies, templates, and initiative state exist under `.agent-loop/`.
- [ ] Existing Workstream `AGENTS.md` rules are preserved and strengthened.
- [ ] CI/static gates use pinned GitHub Actions and do not weaken existing checks.
- [ ] PR template requires trust bundle evidence and human merge ownership.
- [ ] Internal review evidence gate recognizes loop/process files as relevant.
- [ ] No Workstream product code changes are included.

## Verification Commands

```bash
python3 -m py_compile scripts/check_internal_review_evidence.py scripts/workstream_agent_gate.py scripts/check_stale_workstream_wording.py scripts/check_markdown_links.py scripts/test_agent_gates.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format markdown
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
```

`workstream_agent_gate.py` is a static sensor. It reports reviewability and gate-integrity risk, including local staged, unstaged, and untracked files. The blocking CI control for reviewer coverage is `check_internal_review_evidence.py`.

## Required Reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup

## Human Review Focus

Please inspect:

- `AGENTS.md`
- `.agent-loop/policies/`
- `.agents/skills/`
- `.codex/agents/`
- `.github/pull_request_template.md`
- `.github/workflows/agent-gates.yml`
- `scripts/check_internal_review_evidence.py`
- `scripts/workstream_agent_gate.py`

## Stop Conditions

Stop and ask the user if:

- the bootstrap needs to alter product code
- the bootstrap requires Claude-specific support
- reviewer agents cannot complete
- CI/test weakening appears necessary
- the user has not explicitly approved merge
