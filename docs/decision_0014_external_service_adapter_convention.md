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
|- ArtifactStore
`- ExternalCheckerExecutionAdapter (selected hidden Unix-socket runtime)
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

The checker capability publishes a normalized pre/post request/result contract,
an immutable digest-pinned metadata registry, and a hidden typed Unix-socket
adapter for its trusted Rust node service. The registry remains data, not an
adapter factory: it cannot select Python code, discover plugins, grant execution
authority or construct a transport. The adapter factory is instance-local and explicitly installed by the selected
hidden CHECKERS composition. Durable PRE/POST owners retain request, lease and
result custody, while ART owns verified material and callback-scoped grants.
Production request/completion registration does not expose public intake.
Local integration uses runc/docker-dev; hosted gVisor proof remains separate.

The Rust service alone owns container-engine access. Python sends an opaque,
request-bound callback grant issued from ART's existing pre-admission scratch
lifetime. The service resolves it beneath the configured private scratch root,
recomputes exact file and directory facts, and mounts only the sealed workspace
read-only. Its trusted cache binds one OCI platform-manifest digest to repository,
OS, architecture and observed config image ID; it never pulls or resolves tags.
Hosted health fails closed without `runsc`. The explicit `docker-dev` mode is a
local mechanism qualification and cannot report hosted gVisor isolation.

For an approved POST capability that needs to build or execute submitted work,
the same service may expose one invocation-local Unix socket to the selected
checker image. This is a typed sub-capability of the existing external-checker
execution, not another external-service adapter, daemon, runtime factory or
image-output continuation. A locked administrative profile authorizes the exact
POST registry/image/configuration scope, prepared offline builder/base/cache
identities, material-role visibility and aggregate resource ceilings. The image
may supply only closed operation types, safe package-relative selectors and
workload argument arrays. The service—not the image—selects the engine, runtime,
images, mounts, host paths, network, limits and cleanup behavior.

The service publishes completed trial observations into request-bound
invocation memory only after cleanup is confirmed. The model capability may
resolve those server-owned facts through the same invocation; checker-supplied
copies are not evidence. Normalized final output remains the registered
external-checker result. An image cannot trigger host work by returning a
private plan as that result, and `project_private_plan.v1` remains invalid.
Persisting or replaying exact trial evidence requires an owner-typed CHECKERS/ART
contract; a transient socket receipt or ordinary isolation metadata does not by
itself establish durable evidence custody.

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
