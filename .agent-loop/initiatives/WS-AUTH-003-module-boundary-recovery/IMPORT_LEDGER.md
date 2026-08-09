# AUTH Import-Cutover Ledger

This ledger freezes both prohibited directions:

1. non-AUTH runtime importing AUTH outside `authorization.api`;
2. AUTH runtime importing another module's private implementation.

A file may change only to replace its private import, adapt typed public facts,
or wire a public port. Product behavior, query, lock, mutation, concealment, and
transaction flow must remain unchanged. Adding an entry requires a reviewed
contract amendment and is forbidden if it increases either violation count.

## Platform and composition

```text
backend/app/api/deps/authorization.py
backend/app/api/router.py
backend/app/api/routes/auth.py
backend/app/db/models.py
```

## Shared public contract

```text
backend/app/interfaces/artifact_operations.py
```

This file may only replace AUTH-private type references with public AUTH facts;
it may not become a second AUTH API.

## Actors and audit

```text
backend/app/modules/actors/schemas.py
backend/app/modules/actors/service.py
backend/app/modules/audit/schemas.py
```

## ART

```text
backend/app/adapters/artifacts/internal_workers.py
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/guide_bindings.py
backend/app/modules/artifacts/guide_materialization.py
backend/app/modules/artifacts/operator.py
backend/app/modules/artifacts/router.py
backend/app/modules/artifacts/schemas.py
backend/app/modules/artifacts/service.py
backend/app/modules/artifacts/submission_admission.py
backend/app/modules/artifacts/submission_authorization.py
backend/app/modules/artifacts/submission_materialization.py
```

## Projects/POL

```text
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/create_router.py
backend/app/modules/projects/create_service.py
backend/app/modules/projects/guide_mutation_router.py
backend/app/modules/projects/guide_mutation_service.py
backend/app/modules/projects/policy_mutation_router.py
backend/app/modules/projects/policy_mutation_service.py
backend/app/modules/projects/router.py
backend/app/modules/projects/submission_policy_mutation_service.py
backend/app/modules/projects/sufficiency_mutation_service.py
backend/app/workers/project_setup.py
```

## Tasks

```text
backend/app/modules/tasks/router.py
```

## Completion condition

Every file above imports AUTH only through `app.modules.authorization.api` or
has no AUTH import. The static analyser reports no unlisted import and no
exception. This ledger becomes a completed audit record, not a permanent
allowlist for private imports.

## AUTH outbound private-import debt

Every exact current outbound import is recorded below. Actors and Audit are
separate modules too; their current use by AUTH is debt, not a platform
exception.

```text
backend/app/modules/authorization/admin_service.py
  app.modules.audit.schemas
  app.modules.audit.service
backend/app/modules/authorization/catalogue.py
  app.modules.actors.service_identities
backend/app/modules/authorization/kernel.py
  app.modules.audit.schemas
  app.modules.audit.service
backend/app/modules/authorization/lifecycle_service.py
  app.modules.actors.models
  app.modules.audit.schemas
  app.modules.audit.service
backend/app/modules/authorization/prepared.py
  app.modules.actors.repository
  app.modules.actors.service_identities
  app.modules.audit.schemas
backend/app/modules/authorization/project_role_service.py
  app.modules.audit.schemas
  app.modules.audit.service
backend/app/modules/authorization/read_service.py
  app.modules.actors.repository
  app.modules.actors.schemas
  app.modules.actors.service
  app.modules.projects.models
backend/app/modules/authorization/repository.py
  app.modules.actors.models
  app.modules.audit.schemas
  app.modules.projects.repository
backend/app/modules/authorization/review_contracts.py
  app.modules.actors.service_identities
backend/app/modules/authorization/router.py
  app.modules.actors.repository
  app.modules.actors.schemas
  app.modules.actors.service
  app.modules.projects.repository
backend/app/modules/authorization/runtime.py
  app.modules.actors.service_identities
backend/app/modules/authorization/schemas.py
  app.modules.actors.service_identities
  app.modules.audit.schemas
backend/app/modules/authorization/service.py
  app.modules.audit.schemas
  app.modules.audit.service
backend/app/modules/authorization/service_actor_schemas.py
  app.modules.actors.service_identities
backend/app/modules/authorization/service_actor_service.py
  app.modules.actors.models
  app.modules.actors.repository
  app.modules.actors.service_identities
  app.modules.audit.schemas
  app.modules.audit.service
```

The validator records inbound and outbound counts separately. A new AUTH import
of any product model, repository, service, router, schema, persistence module,
or unapproved implementation fails even when its file already appears above.
Later capability repair replaces these with the owning module's public port or
typed contract and removes the exact ledger lines.
