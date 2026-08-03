# Risks

| Risk | Mitigation |
| --- | --- |
| Product definition overclaims deferred behavior | Separate the complete product lifecycle from the current v0.1 capability ledger. |
| Flow auth disappears from operational guidance | Retain it explicitly as the current external authentication adapter. |
| `ContributionRecord` is described as only an accepted-submitter record | Explain both reviewer `completed_review` and accepted-submitter `accepted_submission` records. |
| “Source-agnostic” implies implemented source adapters | State that the core contract is source-agnostic while v0.1 intake remains manual-first. |
| Economic systems appear to control lifecycle truth | State that consequences consume immutable contribution facts and do not create or revise them. |
| Generated architecture artifacts drift | Regenerate context assets and PDF from the updated sources and run stale-document checks. |
| Historical evidence is altered | Exclude reference specs, internal reviews, and superseded calendar plans. |
