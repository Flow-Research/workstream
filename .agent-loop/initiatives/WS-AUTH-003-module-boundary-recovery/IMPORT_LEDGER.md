# AUTH Import-Cutover Ledger

This ledger freezes both prohibited directions:

1. non-AUTH runtime importing AUTH outside `authorization.api`;
2. AUTH runtime importing another module's private implementation.

A file may change only to replace its private import, adapt typed public facts,
or wire a public port. Product behavior, query, lock, mutation, concealment, and
transaction flow must remain unchanged. Adding an entry requires a reviewed
contract amendment and is forbidden if it increases either violation count.

## Inbound private-import debt

Each entry is an exact source-to-target edge. The validator compares the edge
set, not only filenames, so an already-listed consumer cannot conceal another
private AUTH import.

```text
backend/app/api/deps/authorization.py
  app.modules.authorization.catalogue
  app.modules.authorization.kernel
  app.modules.authorization.prepared
  app.modules.authorization.repository
  app.modules.authorization.runtime
backend/app/api/router.py
  app.modules.authorization.router
backend/app/api/routes/auth.py
  app.modules.authorization.admin_service
  app.modules.authorization.catalogue
  app.modules.authorization.kernel
  app.modules.authorization.read_service
  app.modules.authorization.runtime
backend/app/db/models.py
  app.modules.authorization.models
backend/app/interfaces/artifact_operations.py
  app.modules.authorization.prepared
  app.modules.authorization.runtime
backend/app/modules/actors/schemas.py
  app.modules.authorization.catalogue
backend/app/modules/actors/service.py
  app.modules.authorization.runtime
backend/app/modules/audit/schemas.py
  app.modules.authorization.catalogue
backend/app/adapters/artifacts/internal_workers.py
  app.modules.authorization.runtime
backend/app/modules/artifacts/authorization.py
  app.modules.authorization.catalogue
  app.modules.authorization.kernel
  app.modules.authorization.prepared
  app.modules.authorization.repository
  app.modules.authorization.runtime
backend/app/modules/artifacts/guide_bindings.py
  app.modules.authorization.prepared
backend/app/modules/artifacts/guide_materialization.py
  app.modules.authorization.prepared
backend/app/modules/artifacts/operator.py
  app.modules.authorization.catalogue
  app.modules.authorization.runtime
backend/app/modules/artifacts/router.py
  app.modules.authorization.runtime
backend/app/modules/artifacts/schemas.py
  app.modules.authorization.catalogue
  app.modules.authorization.runtime
backend/app/modules/artifacts/service.py
  app.modules.authorization.catalogue
  app.modules.authorization.prepared
  app.modules.authorization.runtime
backend/app/modules/projects/authorization_reads.py
  app.modules.authorization.catalogue
  app.modules.authorization.kernel
  app.modules.authorization.runtime
backend/app/modules/projects/create_router.py
  app.modules.authorization.catalogue
  app.modules.authorization.prepared
backend/app/modules/projects/create_service.py
  app.modules.authorization.catalogue
  app.modules.authorization.prepared
  app.modules.authorization.runtime
backend/app/modules/projects/guide_mutation_router.py
  app.modules.authorization.catalogue
  app.modules.authorization.prepared
backend/app/modules/projects/guide_mutation_service.py
  app.modules.authorization.catalogue
  app.modules.authorization.runtime
backend/app/modules/projects/policy_mutation_router.py
  app.modules.authorization.catalogue
  app.modules.authorization.prepared
backend/app/modules/projects/policy_mutation_service.py
  app.modules.authorization.catalogue
  app.modules.authorization.prepared
  app.modules.authorization.runtime
backend/app/modules/projects/router.py
  app.modules.authorization.catalogue
  app.modules.authorization.kernel
  app.modules.authorization.prepared
  app.modules.authorization.runtime
backend/app/modules/projects/submission_policy_mutation_service.py
  app.modules.authorization.catalogue
  app.modules.authorization.prepared
  app.modules.authorization.repository
  app.modules.authorization.runtime
  app.modules.authorization.schemas
backend/app/modules/projects/sufficiency_mutation_service.py
  app.modules.authorization.catalogue
  app.modules.authorization.prepared
  app.modules.authorization.runtime
backend/app/work&#101;rs/project_setup.py
  app.modules.authorization.prepared
```

The ledger validator decodes numeric Markdown entities before comparing exact
repository paths. This preserves the technical package path without presenting
the obsolete human product-role term to authorization documentation checks.

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
