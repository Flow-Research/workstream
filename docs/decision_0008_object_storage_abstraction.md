# ADR 0008: Files Use An Object-Storage Abstraction

## Status

Accepted

## Context

Workstream needs to store submission packages, evidence, checker logs, reports, and other artifacts.

Those artifacts must be hash-bound and auditable. Local development may use a
filesystem adapter. AWS S3 is the v0.1 production object store; other providers
require separate approved discovery and a verified maintenance cutover.

If services write directly to local paths, storage semantics will drift when object storage is introduced.

## Decision

All file and evidence storage goes through a storage interface that behaves like object storage.

Local filesystem storage is allowed only as an adapter behind that interface.

Callers use stable object keys, content hashes, metadata, and immutable artifact references. Services must not depend on local filesystem paths as the business contract.

## Consequences

Positive:

- local development remains simple
- production object storage can replace the local adapter without changing submission semantics
- artifacts can be hash-bound and audited consistently
- checker and review records can cite stable artifact identifiers

Tradeoff:

- direct file-path shortcuts are not allowed in domain services
- the storage interface must be designed before artifact-heavy workflows are implemented
