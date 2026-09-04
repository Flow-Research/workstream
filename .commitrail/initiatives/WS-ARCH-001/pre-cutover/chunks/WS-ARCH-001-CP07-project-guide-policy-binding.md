# Chunk Contract: WS-ARCH-001-CP07 — Project Guide Policy Binding

Status: proposed non-executable skeleton after CP06. Risk: L1.

PROJECTS extends its public guide-activation composition to call the CON public
validation capability and persist the returned exact version as non-null
`ProjectGuide.contribution_policy_version_id`. PROJECTS owns the guide write and
single transaction; it imports no CON models/repositories and performs no
policy selection itself.

The covered Project Manager invokes `project.guide_sufficiency.run` through
the public HTTP route. The fixed `workstream.project.setup` service resolves
the same action only through the internal command boundary and must never call
or depend on that public route.

This chunk reconciles the current v0.1 baseline schema for ProjectGuide only.
TASK/Assignment/Submission fields and legacy economic-path removal remain later.

## Merge state

- Outcome on merge: `planned`
