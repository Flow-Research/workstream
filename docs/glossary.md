# Glossary

## Workstream

Flow's task evaluation and contribution infrastructure: the system for project guides, task queues, submission packets, automated checks, reviewer routing, evaluation sprints, revision loops, contribution records, payment status, and reputation signals.

## Project

A configured work program with its own human-facing guide, submission artifact policy, checker policies, review policy, revision policy, payment policy, and queue.

## Project Owner

The external or internal organization that provides open-ended project material
and business terms. That material can be markdown, URL-backed documentation,
repository docs, examples, rubrics, task instructions, base payout or payment
policy inputs, or other project-specific source material. The project owner
does not author or approve Workstream's machine-readable internal policy schema.

## Source

Where a task came from. In v0.1, sources are manual creation, controlled markdown import, or controlled CSV import.

## Origin

A future external task source that can submit tasks into Workstream through an adapter. External origin onboarding is not part of v0.1.

## Project Guide

The human-facing operating guide for a project. It contains the project instructions, quality bar, task examples, reviewer rubric, common rejection reasons, and links or summaries for the approved policies. A project guide may be markdown, an imported document, or a URL-backed guide, but runtime enforcement uses approved machine-readable policies attached to the guide version.

## Guide Sufficiency Report

The Workstream-owned record produced by `ProjectGuideSufficiencyAgent` for a
project guide version. It records whether the guide passed, is blocked by gaps,
or passed with warnings that an `admin` or `project_manager` must acknowledge
before activation.

## Submission Artifact Policy

The Workstream-derived, admin-or-project-manager-approved machine-readable
contract for what a worker must submit. It is derived from open-ended project
guide material after guide sufficiency passes or warnings are acknowledged,
reviewed by a Workstream actor with the `admin` or `project_manager` role, and
attached to a project guide version. It defines required artifacts, evidence
requirements, artifact hash requirements, allowed storage reference forms,
forbidden artifacts, attestation requirements, and project-specific packaging
rules. It can add or tighten requirements, but it cannot weaken Workstream's
default submission artifact rules.

## Project Submission Artifact Policy

The project-specific `SubmissionArtifactPolicy` attached to one project guide
version before Workstream merges it with default submission artifact policy.

## Effective Project Submission Artifact Policy

The deterministic merge of Workstream's default submission artifact policy and the project-approved submission artifact policy. Workstream computes this effective project policy before generating the project pre-submit checker policy.

## Pre-Submit Checker Policy

The server-generated project checker matrix produced from the effective project submission artifact policy, persisted with a compiled bundle hash, and locked by tasks before they enter the worker pipeline. It runs before Workstream creates a submission row or submission version. The preflight endpoint returns `PreSubmitCheckResponse`; a blocked submission-create attempt returns `pre_submission_checker_failed` with structured pass/fail/warning details. Neither path returns review decision values: `accept`, `needs_revision`, or `reject`.

## pre_submission_checker_failed

The worker-facing domain error code returned when a submission-create attempt is blocked by pre-submit checks. It includes structured pass/fail/warning details in the error details and is not a review decision. It must not be stored as `accept`, `needs_revision`, or `reject`. The preflight endpoint returns `PreSubmitCheckResponse` instead of this error code.

## Task

A unit of work inside a project.

## Task Contract

The normalized task fields required for Workstream to screen, assign, check, review, pay, and audit work.

## Submission Packet

The worker's submitted output plus summary, artifacts, evidence references, hashes, and metadata. Workstream assigns the submission version server-side after blocking pre-submit checks pass.

## Checker

An automated rule that validates a task or submission before human review.

## Checker Policy

The set of required and warning checks for a project phase. Pre-submit checker policy is generated from the effective project submission artifact policy. Post-submit checker policy governs durable internal checker runs after a submission is locked.

## Human Review

The judgment layer where a reviewer accepts, rejects, or requests revision.

## Finding

A structured reviewer issue with severity, area, required fix, and evidence.

## Revision Replay

A resubmission record showing how each prior review finding was addressed.

## Evidence

Proof supporting task completion or review decision. Examples: logs, hashes, tests, screenshots, diffs, notes.

## Payment Ledger

The record of accepted amount, pending payout, paid amount, and payment state.

## Reputation Ledger

The outcome-based record of worker and reviewer performance.

## Contribution Record

The evidence-backed record that accepted work was completed under a locked project guide. Payment and reputation records attach to contribution records, but do not replace them.

## Human Owner

The person accountable for a submitted packet, even when agents or external tools helped produce the work.
