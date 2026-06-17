---
name: discovery
description: Perform read-only repository discovery for an initiative. Use to map existing behavior, files, tests, risks, and unknowns before planning.
---

# Discovery

Perform read-only discovery. Do not edit application code.

## Inspect

- Repository structure
- Relevant modules/files
- Existing tests
- Existing docs
- Package scripts / build commands
- Architecture boundaries
- Security/payment/auth/data-sensitive areas

## Produce

Update `DISCOVERY.md` with:

- Current behavior
- Relevant files/modules
- Existing tests and gaps
- Dependencies/integrations
- Risks discovered
- Unknowns/questions for human
- Existing conventions to preserve

## Rules

- Cite concrete files and symbols.
- Do not infer architecture without evidence.
- Separate observations from assumptions.
- Stop if production secrets or external credentials are required.
