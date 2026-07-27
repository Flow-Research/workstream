# Decisions: WS-XINT-002 ART-AUTH End-to-End Contract

1. The dependency is owned end to end by a cross-initiative plan, not by ART-03A.
2. One outer ZIP replaces the six historical multi-step upload actions with
   `artifact.submission_bundle.prepare`; no compatibility aliases or retained
   unavailable rows remain. The immutable chunk contract and migration record
   the exact deleted ActionId and PermissionId values.
3. Initial, checker-remediation, and human-review revision submissions share the
   public preparation/create actions; each has an exact closed typed context.
4. Reviewer packet materialization is a fixed-service action plus a separate
   human lease decision. Neither substitutes for the other.
5. Finding and response evidence require separate human operation authority and
   fixed artifact binding authority.
6. Existing artifact materializer and binding identities gain review-packet and
   review-evidence memberships; scheduler loses upload-session-expiry
   membership. No new service identity is introduced.
7. Operators request and inspect; fixed internal services execute recovery. Artifact
   audit is not broadened implicitly to general Audit Authority.
8. Catalogue and reusable PREP dependencies are front-loaded. Activation stays
   evidence-gated and cannot be eliminated safely.
9. The simple contribution loop applies: planning does not require a signed
   start/cancel event or merge-intent file.
