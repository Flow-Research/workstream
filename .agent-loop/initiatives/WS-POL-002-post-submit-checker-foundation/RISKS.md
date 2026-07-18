# Risks: WS-POL-002 - Post-Submit Checker Foundation

| Risk | Impact | Mitigation |
|---|---|---|
| Reintroducing task-specific checker generation | High architecture drift and operational cost | Keep `PostSubmitCheckerPolicy` project-scoped; tasks lock references only. |
| Letting agent output become runtime authority | High security and correctness risk | Agent emits constrained setup spec only; Workstream compiler and registered checkers own runtime. |
| Weakening default durable checks | Bad submissions can bypass review gate | Compiler must always include defaults and reject attempts to remove or downgrade them. |
| Referencing unknown checker names | Activation can pass but runtime fails | Compiler and activation must require registered checkers. Unsupported required checks become setup blockers. |
| Confusing post-submit checker routing with product decisions | Workers/reviewers misunderstand lifecycle | Keep product decisions limited to `accept`, `needs_revision`, `reject`; keep internal routes hidden unless operator authorized. |
| Manual guide payload survives as a second policy path | Contract drift and inconsistent setup | Remove obsolete manual `post_submit_checker_policy` guide request fields once generated path exists. |
| Overloading post-submit checks with review/revision lifecycle | Scope creep | This initiative stops at automated pre-review gate readiness; human review and revision APIs remain separate. |
| Privacy leak in live drill evidence | External source/source-material exposure | Use sanitized refs, redacted identifiers, PDF/report privacy scan, and no local private paths. |
| CI or tests become too broad and slow | Reduced iteration quality | Use focused tests per chunk plus full API drill only in the final proof chunk. |
| Confusing v0.1 setup authorization with future project-scoped roles | Inaccurate access-control contract | WS-POL-002 uses current verified `admin`/`project_manager` setup authorization; project-scoped role assignment remains a separate future authorization chunk. |
