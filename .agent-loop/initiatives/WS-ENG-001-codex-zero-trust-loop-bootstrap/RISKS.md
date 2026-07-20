# RISKS: WS-ENG-001

| Risk | Severity | Mitigation |
|---|---:|---|
| Generic kit wording conflicts with Workstream language | High | Rewrite policies and AGENTS additions in Workstream terms. |
| Codex does not automatically discover custom agents in a project until trusted | Medium | Keep reviewer requirements in `AGENTS.md` and `.agent-loop` as durable fallback. |
| CI gate creates friction for docs-only work | Medium | Gate reports as sensor; internal evidence gate remains targeted to relevant paths. |
| Future agents still forget subagent review | High | Encode in `AGENTS.md`, `.agent-loop/policies`, PR template, CI evidence gate, and reviewer configs. |
| Agents merge without explicit approval | Critical | Encode no-merge rule in `AGENTS.md`, merge policy, PR template, and trust bundle. |
| Changed-file discovery drifts across gate scripts | Low | Current tests cover the duplicated logic; extract a shared helper in a later cleanup chunk if drift appears. |
| Write-capable workflow is tricked into executing PR code | Critical | Trigger only from protected-main push or explicit replay, run the updater from trusted `main`, disable checkout credential persistence, and never use `pull_request_target`. |
| Automation writes to protected `main` or another actor rewrites/replays generated authority | Critical | Hard-code and test `automation/loop-memory` as the sole push ref; block deletion and force-push; authenticate every generated file with an Actions-only Ed25519 key; require the expected protected-main SHA; rebuild invalid branch state from the immutable bootstrap; do not create, approve, or merge a bot PR. |
| Concurrent merges race and overwrite state | High | Serialize workflow runs, enforce monotonic merge timestamps, reject conflicting duplicate SHAs, and keep an append-only ledger. |
| Missing PR metadata forces intent inference | High | Agent Gates requires one newly added strict merge-intent JSON file; updater reloads its reviewed head blob and fails closed on missing, modified, duplicate, malformed, or inconsistent metadata. |
| A required check is missing or failed despite merge | High | Record observed conclusions and mark generated integrity as attention required; never report missing evidence as passed. |
| Automation permissions or transient GitHub failure prevent update | Medium | Preserve idempotent trusted-default-branch `repository_dispatch` replay bound to the current protected-main SHA; do not hand-edit generated state. |
| Generated branch is edited manually | High | Declare workflow-only ownership, validate JSON/render/ledger agreement, and reject conflicting replay state. |
| One initiative declares another initiative's next lifecycle gate | High | Schema v2 requires a non-null next chunk to share the completed initiative prefix; global priority remains human-owned. |
| Invalid schema-v1 state contaminates the corrected ledger | Critical | Reject it completely, clear only fixed generated paths, and bootstrap schema v2 from WS-ENG-001-03. |
| Signed state is correct while generated queue/status projections are stale | High | 04A derives every canonical projection from the authenticated ledger, signs the complete manifest, and validates byte-for-byte agreement. |
| Cleanup deletes non-automation branch content | Critical | Generate in an empty directory and construct a fresh tree from an empty temporary Git index; commit it as a normal child without traversing legacy paths or force-pushing. |
| Last merged PR is presented as every initiative's state | High | Reduce the authenticated ledger to the latest record per initiative and render compact initiative projections deterministically. |
| Merge automation falsely claims conversational work is active | High | 04A renders stopped/next merge state only; 04B separately owns authenticated explicit-start events. |
| Start workflow bypasses human authority or selects arbitrary work | Critical | 04B requires protected dispatch, current-main binding, exact successor equality, contract validation, signed event provenance, and fail-closed replay/conflict handling. |
| A mistaken or abandoned explicit start wedges an initiative | High | 04B cannot pass preimplementation review until an attributable signed cancel/correct event with reason, replay protection, and projection semantics is explicit. |
