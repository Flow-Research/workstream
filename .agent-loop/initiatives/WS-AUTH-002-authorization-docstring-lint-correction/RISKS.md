# Risks: WS-AUTH-002 — Authorization Docstring Lint Correction

| Risk | Control |
|---|---|
| Ruff or docstring enforcement is weakened | Configuration and workflow files are forbidden |
| Runtime validation changes under a lint label | Only docstrings may change in the source file |
| AUTH-11 is incorrectly consumed | A separate corrective initiative preserves AUTH-11 state |
| Broad cleanup delays PR #198 | Exactly four named symbols are in scope |
| PR #198 consumes an unmerged patch | Integration waits for trusted-main merge |
