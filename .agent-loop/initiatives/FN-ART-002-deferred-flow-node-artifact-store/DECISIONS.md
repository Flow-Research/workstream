# Decisions: FN-ART-002

- Flow Node is optional and deferred beyond Workstream v0.1.
- It must implement ArtifactStore v2 without extending the generic port.
- Workstream keeps SHA-256/size as canonical identity.
- Flow Node provider IDs and DAG/CID details remain opaque observations.
- The provider accepts only a fixed Workstream service identity over TLS.
- Adoption uses complete migration plus maintenance cutover, never fallback.
- Semantic search and public publication require separate initiatives.
