# Chunk Contract: WS-ARCH-001-06 Contribution and Compensation Repairs

Status: Non-executable planning placeholder. Risk: L1.

Install exact REV/CON/COMP public handoffs before contribution or award
activation. REVIEWS supplies one immutable `completed_review` fact for every
valid Review, regardless of decision, and creates one REV-owned
`FinalAcceptance` fact only for `accept`. CONTRIBUTIONS creates the reviewer
`completed_review` record from the former and the submitter
`accepted_submission` record only from `FinalAcceptance`—never by inspecting a
raw Review decision. COMPENSATION owns conditional award and fulfillment. No
downstream module may recompute or mutate upstream lifecycle truth.

This file does not authorize implementation. Replace it with complete bounded
contracts before any code change.
