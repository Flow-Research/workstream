# Risks: WS-ENG-006 - Contributor Engineering Onboarding

| Risk | Impact | Control |
|---|---|---|
| Documentation accidentally weakens an enforced gate | Contributors treat prose as permission to bypass signed state | Use explicit non-goals, security/architecture/CI review, and semantic tests. |
| Entry documents duplicate unstable workflow details | Future workflow changes create conflicting instructions | Link the canonical runbook and test only stable policy semantics. |
| Existing patches are described as authorized work | Scope and review evidence become retroactive | Define patches as discovery input until adopted after a signed start. |
| Human and product Contributor roles are conflated | Repository access is mistaken for runtime product authority | Define both terms explicitly and preserve product glossary language. |
| Planning artifacts are mistaken for an active start | Implementation begins before canonical signed state | Keep status proposed and require explicit-event evidence before implementation. |
| A brand-new initiative cannot land its first trusted-main contract | Contract resolution requires the contract on `main`, but merging it requires an earlier signed start | Add a closed planning-only first merge that records stopped signed state and never activates implementation. |
| Root repair authorizes itself too broadly | A reusable exception could bypass later starts | Bind the recovery certificate to exact PR #176 PLAN3 plus the ENG-006 activation target, require that ordered two-merge reconciliation, then consume both identities and reject reuse. |
| Planning intake carries implementation | Code could reach main without signed implementation start | Restrict intake to one additive planning tree plus one intent and fail closed on every foreign change. |
| Unauthorized contributor intake has no public canonical route | Newcomers may depend on private chat or publish unsigned work | Chunk 01 must name a public request route and exact maintainer adoption procedure. |
