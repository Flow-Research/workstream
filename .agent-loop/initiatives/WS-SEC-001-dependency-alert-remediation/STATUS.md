# Status: WS-SEC-001 Dependency Alert Remediation

- Initiative state: complete on merge of `WS-SEC-001-01`
- Runtime dependency outcome: `cryptography` and `pypdf` use patched versions.
- Tooling dependency outcome: backend manifests use patched `pytest` and
  `pytest-asyncio`; mutation-tool manifests use patched `pytest` and `uv`
  versions.
- Product behavior changed: no

Future dependency alerts use fresh bounded changes against current `main`.
