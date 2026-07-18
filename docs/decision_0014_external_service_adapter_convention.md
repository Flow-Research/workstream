# ADR 0014: External Services Use One Adapter Convention

## Status

Accepted through separate explicit human direction to standardize external
service adapters while planning WS-ART-001. This ADR records the convention;
it does not authorize identity or project-agent migrations. Adoption remains
capability-owned and occurs only in each approved migration chunk.

## Context

Workstream integrates replaceable external capabilities, including identity-
token verification, project setup agents, and immutable object storage. Each
capability needs precise domain operations, but construction and dependency
injection must not become a different ad hoc pattern for every integration.

Without one convention, provider selection can leak into product services,
concrete clients can spread across modules, and later provider changes can
require product-domain rewrites.

## Decision

Workstream defines a small central `ExternalServiceAdapter` protocol and a
generic `ExternalServiceAdapterFactory[TAdapter]` construction convention.

`ExternalServiceAdapter` defines only behavior meaningful to every external
integration:

- immutable adapter identity containing capability and provider keys;
- shared root errors for configuration, availability, and external protocol
  failures.

It does not define authentication, storage, model execution, source retrieval,
or payment operations. Typed capability ports extend it and own their methods:

```text
ExternalServiceAdapter
|- IdentityIssuerVerifier
|- ProjectGuideAgentRuntime
`- ArtifactStore
```

Concrete implementations satisfy explicit capability ports:

```text
FlowIdentityIssuerVerifier        -> IdentityIssuerVerifier
OpenAIAgentSdkProjectGuideRuntime -> ProjectGuideAgentRuntime
LocalStorageAdapter               -> ArtifactStore
S3CompatibleArtifactStore         -> ArtifactStore
Future FlowNodeArtifactStore      -> ArtifactStore
```

Each capability exposes a typed factory based on
`ExternalServiceAdapterFactory[TAdapter]`. The factory owns explicit provider
registration, duplicate-provider rejection, unknown-provider failure, typed
construction, and stable configuration-error mapping.

Registration is explicit in the FastAPI or Celery composition root.
Runtime plugin discovery, import scanning, mutable global registration, and
generic service locators are forbidden.

Settings parse and validate provider-specific configuration. Runtime provider
selection and concrete construction occur only in the typed capability
factory. The one owning integration/orchestration service receives the raw
capability port through dependency injection. Product APIs, product services,
Celery tasks, checkers, and repositories receive typed domain operations from
that owner and do not receive a writable transport port when doing so could
bypass product policy, admission, persistence, or audit. No caller imports
concrete adapters, inspects provider-selection settings, or calls provider APIs
directly.

Adapters own provider transport, provider authentication injection, bounded
request/response translation, and protocol validation. Product policy,
persistence, product authorization, audit, idempotency, lifecycle transitions,
and durable recovery remain in their owning Workstream services unless the
typed capability explicitly assigns a bounded transport retry.

Adoption is owned by each capability initiative. WS-ART installs the shared
foundation and migrates only `ArtifactStore`. WS-AUTH owns
`IdentityIssuerVerifier`. The project setup/checker initiative owns
`ProjectGuideAgentRuntime`. Each migration removes its previous factory entry
point and callers in one clean cut.

No compatibility alias, fallback constructor, dual registration path, or
service-locator shim is retained.

For artifact storage, only the artifact-storage orchestration service receives
the writable `ArtifactStore`. Guide, task, submission, and checker modules use
typed artifact ingest/read/materialization services so every `put` and read-only
`observe_put_result` crosses durable admission, receipts, and lifecycle
enforcement.

## Consequences

Positive:

- every external service follows one discoverable integration convention;
- capability methods remain typed and domain-specific;
- provider selection cannot leak into product services;
- local/test and production implementations use the same capability contract;
- AWS S3 and a future Flow Node adapter do not require product rewrites;
  Cloudflare R2 is deferred and would require its own later approved initiative.

Tradeoffs:

- existing capability factories require owner-approved clean-cut migrations;
- the shared base must remain deliberately small;
- capability-specific errors still require explicit typed mappings.

## Rejected Alternatives

- One universal adapter with `execute` or free-form request dictionaries:
  rejected because it destroys type safety and capability meaning.
- Independent factory conventions for every integration: rejected because it
  duplicates construction, failure, and dependency-injection decisions.
- Runtime plugin discovery or import scanning: rejected because startup
  behavior becomes implicit and difficult to audit.
- Concrete adapter construction in product services: rejected because it
  creates tight coupling and bypasses the composition root.
- Keeping old factory functions as aliases: rejected because Workstream is
  pre-production and does not retain obsolete integration paths.
