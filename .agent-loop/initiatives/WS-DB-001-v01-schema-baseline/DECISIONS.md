# Decisions

1. The reset is a clean cut. Existing development databases are destroyed and
   recreated; there is no stamp, bridge, or compatibility alias.
2. The canonical v0.1 baseline is a single Alembic revision with
   `down_revision = None`.
3. Final PostgreSQL state is the source for baseline parity. ORM metadata alone
   is not accepted as sufficient proof.
4. Canonical reference rows required for runtime startup are installed by the
   baseline and verified against application catalogues.
5. Historical reviews remain historical. Current executable references and
   operator instructions are rewritten.
6. Baseline downgrade is not a supported operational path. Its implementation
   raises before mutation; tests prove schema and data remain intact.
7. New migrations after this reset start at `0002`; old numeric identifiers are
   never reused as aliases.
8. The revision-0023 frozen Python contract, service-identity migration helper,
   and its CLI are obsolete after the clean cut and are deleted. The current
   runtime service-identity registry remains authoritative.
