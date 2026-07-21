# DECISIONS: WS-ENG-002

## 2026-07-21 — One explicit human checkpoint

An authorized GitHub workflow dispatch is the explicit human start. GitHub's repository-writer dispatch boundary plus a fixed actor allowlist reviewed on trusted `main` supplies the operational authorization, and a second environment reviewer is not required for `start`. The initial allowlisted orchestrator identity is `Abiorh001`. Cancellation retains the existing protected-environment approval. Signed audit evidence and all state-integrity controls remain required.
