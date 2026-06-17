# PLAN: WS-ENG-001

## Approach

Bootstrap Workstream's engineering loop using Codex-native surfaces first:

1. Keep `AGENTS.md` as the hard repository instruction layer.
2. Add `.agents/skills/` for Codex-discoverable workflow skills.
3. Add `.codex/agents/` for read-only custom reviewer agents.
4. Add `.agent-loop/` for durable policies, initiative memory, templates, review
   logs, and chunk contracts.
5. Add CI/static gates that strengthen existing evidence requirements.
6. Add a PR template based on the trust bundle pattern.

## Design Choices

- `.agents/skills/` is canonical for Codex skills because Codex scans that path.
- `.agent-loop/` is canonical for engineering memory because it should be readable
  by humans and portable across repositories.
- `.agent-loop/skills` is intentionally not used to avoid duplicated skill sources.
- Claude files are excluded because this repo is being optimized for Codex CLI.
- Product/Ops review is first-class because Workstream is operational
  infrastructure, not only code.

## Alternatives Rejected

- Blindly copying the entire kit: rejected because it would import Claude files,
  generic TODOs, and duplicate skill locations.
- Keeping everything only in docs: rejected because Codex would not discover
  skills or custom reviewer agents directly.
- Relying only on CodeRabbit and CI: rejected because Workstream requires
  internal reviewer tracks before external review is considered sufficient.

## Verification Strategy

- Compile Python gate scripts.
- Run the Workstream agent gate against `origin/main...HEAD`.
- Run the internal review evidence gate.
- Run stale wording scan.
- Run Markdown link check for changed Markdown files.
- Run required internal reviewer tracks and record findings.
