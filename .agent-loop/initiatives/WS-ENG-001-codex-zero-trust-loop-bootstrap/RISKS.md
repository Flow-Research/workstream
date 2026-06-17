# RISKS: WS-ENG-001

| Risk | Severity | Mitigation |
|---|---:|---|
| Generic kit wording conflicts with Workstream language | High | Rewrite policies and AGENTS additions in Workstream terms. |
| Codex does not automatically discover custom agents in a project until trusted | Medium | Keep reviewer requirements in `AGENTS.md` and `.agent-loop` as durable fallback. |
| CI gate creates friction for docs-only work | Medium | Gate reports as sensor; internal evidence gate remains targeted to relevant paths. |
| Future agents still forget subagent review | High | Encode in `AGENTS.md`, `.agent-loop/policies`, PR template, CI evidence gate, and reviewer configs. |
| Agents merge without explicit approval | Critical | Encode no-merge rule in `AGENTS.md`, merge policy, PR template, and trust bundle. |
| Changed-file discovery drifts across gate scripts | Low | Current tests cover the duplicated logic; extract a shared helper in a later cleanup chunk if drift appears. |
