package api

import (
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"strings"
	"unicode/utf8"
)

// RevisionContext is the contributor-visible, frozen preparation projection.
// It contains identities and bounded change summaries, never policy bodies.
type RevisionContext struct {
	PreparationID            string                   `json:"preparation_id"`
	PreparationSHA256        string                   `json:"preparation_sha256"`
	PredecessorPreparationID *string                  `json:"predecessor_preparation_id"`
	SourceSubmissionID       string                   `json:"source_submission_id"`
	SourceRoutingManifestID  string                   `json:"source_routing_manifest_id"`
	Sequence                 int64                    `json:"sequence"`
	NextRevisionRound        int64                    `json:"next_revision_round"`
	MaxRevisionRounds        int64                    `json:"max_revision_rounds"`
	RequestedAt              string                   `json:"requested_at"`
	DeadlineAt               *string                  `json:"deadline_at"`
	ClockState               string                   `json:"clock_state"`
	RemainingMicroseconds    *int64                   `json:"remaining_microseconds"`
	Outcome                  string                   `json:"outcome"`
	Disposition              string                   `json:"disposition"`
	Direction                *string                  `json:"direction"`
	Prior                    RevisionSnapshot         `json:"prior"`
	Target                   *RevisionSnapshot        `json:"target"`
	PriorRewardSelection     RevisionRewardSelection  `json:"prior_reward_selection"`
	TargetRewardSelection    *RevisionRewardSelection `json:"target_reward_selection"`
	Changes                  []RevisionChange         `json:"changes"`
}

type RevisionRewardSelection struct {
	CompensationMode string  `json:"compensation_mode"`
	TaskSize         string  `json:"task_size"`
	Instrument       *string `json:"instrument"`
	Unit             *string `json:"unit"`
	Quantity         *string `json:"quantity"`
}

type RevisionSnapshot struct {
	GuideID               string          `json:"guide_id"`
	ActivationOperationID string          `json:"activation_operation_id"`
	ActivationGeneration  int64           `json:"activation_generation"`
	ActivatedAt           string          `json:"activated_at"`
	Lineage               RevisionLineage `json:"lineage"`
}

type RevisionLineage struct {
	GuideVersion                string `json:"locked_guide_version"`
	SourceSnapshotID            string `json:"locked_guide_source_snapshot_id"`
	SourceSnapshotHash          string `json:"locked_guide_source_snapshot_hash"`
	ArtifactPolicyID            string `json:"locked_effective_project_submission_artifact_policy_id"`
	ArtifactPolicyHash          string `json:"locked_effective_project_submission_artifact_policy_hash"`
	PreSubmitPolicyID           string `json:"locked_pre_submit_checker_policy_id"`
	PreSubmitBundleHash         string `json:"locked_pre_submit_checker_bundle_hash"`
	PostSubmitPolicyID          string `json:"locked_post_submit_checker_policy_id"`
	PostSubmitPolicyVersion     string `json:"locked_post_submit_checker_policy_version"`
	PostSubmitPolicyHash        string `json:"locked_post_submit_checker_policy_hash"`
	ReviewPolicyID              string `json:"locked_review_policy_id"`
	ReviewPolicyGeneration      int64  `json:"locked_review_policy_generation"`
	ReviewPolicyHash            string `json:"locked_review_policy_hash"`
	RevisionPolicyID            string `json:"locked_revision_policy_id"`
	RevisionPolicyGeneration    int64  `json:"locked_revision_policy_generation"`
	RevisionPolicyHash          string `json:"locked_revision_policy_hash"`
	ContributionPolicyVersionID string `json:"locked_contribution_policy_version_id"`
}

type RevisionChange struct {
	Component string `json:"component"`
	Before    string `json:"before"`
	After     string `json:"after"`
}

func revisionInvalid() error { return errors.New("invalid revision context") }

func validateRevisionContext(raw json.RawMessage, value *RevisionContext) error {
	fields, err := contextObject(raw, value, []string{
		"preparation_id", "preparation_sha256", "source_submission_id", "source_routing_manifest_id",
		"sequence", "next_revision_round", "max_revision_rounds", "requested_at",
		"clock_state",
		"outcome", "disposition", "prior", "changes", "prior_reward_selection",
	}, nil)
	if err != nil || !validUUID(value.PreparationID) || !contextPolicyDigest.MatchString(value.PreparationSHA256) ||
		!validUUID(value.SourceSubmissionID) || !validUUID(value.SourceRoutingManifestID) ||
		value.Sequence <= 0 || value.NextRevisionRound < 0 || value.MaxRevisionRounds < 0 ||
		!validTime(value.RequestedAt) || value.Changes == nil || len(value.Changes) > 8 {
		return revisionInvalid()
	}
	if _, ok := fields["deadline_at"]; !ok {
		return revisionInvalid()
	}
	if _, ok := fields["remaining_microseconds"]; !ok {
		return revisionInvalid()
	}
	if value.ClockState == "running" {
		if value.DeadlineAt == nil || !validTime(*value.DeadlineAt) || value.RemainingMicroseconds != nil {
			return revisionInvalid()
		}
	} else if value.ClockState == "paused" {
		if value.DeadlineAt != nil || value.RemainingMicroseconds == nil || *value.RemainingMicroseconds <= 0 || value.Outcome != "blocked" || value.Disposition != "context_blocked" {
			return revisionInvalid()
		}
	} else {
		return revisionInvalid()
	}
	if value.PredecessorPreparationID != nil && !validUUID(*value.PredecessorPreparationID) {
		return revisionInvalid()
	}
	switch value.Outcome {
	case "kept", "rebased", "blocked":
	default:
		return revisionInvalid()
	}
	switch value.Disposition {
	case "ready", "context_blocked", "revision_limit_reached", "revision_deadline_expired":
	default:
		return revisionInvalid()
	}
	if value.Direction != nil {
		switch *value.Direction {
		case "kept", "forward", "backward":
		default:
			return revisionInvalid()
		}
	}
	if err := validateRevisionSnapshot(fields["prior"], &value.Prior); err != nil {
		return err
	}
	if rawTarget, present := fields["target"]; present && string(rawTarget) != "null" {
		if value.Target == nil || validateRevisionSnapshot(rawTarget, value.Target) != nil {
			return revisionInvalid()
		}
	}
	if validateRevisionRewardSelection(fields["prior_reward_selection"], &value.PriorRewardSelection) != nil {
		return revisionInvalid()
	}
	targetReward, present := fields["target_reward_selection"]
	if !present || !requiredNullable(fields, "target") || (value.Target == nil) != (value.TargetRewardSelection == nil) {
		return revisionInvalid()
	}
	if value.TargetRewardSelection != nil && (validateRevisionRewardSelection(targetReward, value.TargetRewardSelection) != nil ||
		value.TargetRewardSelection.TaskSize != value.PriorRewardSelection.TaskSize) {
		return revisionInvalid()
	}
	var changes []json.RawMessage
	if jsonv2.Unmarshal(fields["changes"], &changes) != nil || changes == nil || len(changes) != len(value.Changes) {
		return revisionInvalid()
	}
	for i, change := range changes {
		if _, err := contextObject(change, &value.Changes[i], []string{"component", "before", "after"}, nil); err != nil {
			return revisionInvalid()
		}
		switch value.Changes[i].Component {
		case "guide", "source", "artifact", "pre_submit", "post_submit", "review", "revision", "contribution":
		default:
			return revisionInvalid()
		}
		if utf8.RuneCountInString(value.Changes[i].Before) == 0 || utf8.RuneCountInString(value.Changes[i].Before) > 200 ||
			utf8.RuneCountInString(value.Changes[i].After) == 0 || utf8.RuneCountInString(value.Changes[i].After) > 200 {
			return revisionInvalid()
		}
	}
	return nil
}

func validateRevisionSnapshot(raw json.RawMessage, value *RevisionSnapshot) error {
	fields, err := contextObject(raw, value, []string{
		"guide_id", "activation_operation_id", "activation_generation", "activated_at", "lineage",
	}, nil)
	if err != nil || !validUUID(value.GuideID) || !validUUID(value.ActivationOperationID) ||
		value.ActivationGeneration <= 0 || !validTime(value.ActivatedAt) {
		return revisionInvalid()
	}
	lineage := &value.Lineage
	_, err = contextObject(fields["lineage"], lineage, []string{
		"locked_guide_version", "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash",
		"locked_effective_project_submission_artifact_policy_id", "locked_effective_project_submission_artifact_policy_hash",
		"locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash",
		"locked_post_submit_checker_policy_id", "locked_post_submit_checker_policy_version", "locked_post_submit_checker_policy_hash",
		"locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash",
		"locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash",
		"locked_contribution_policy_version_id",
	}, nil)
	if err != nil || strings.TrimSpace(lineage.GuideVersion) == "" ||
		strings.TrimSpace(lineage.PostSubmitPolicyVersion) == "" ||
		!validUUID(lineage.SourceSnapshotID) || !validUUID(lineage.ArtifactPolicyID) ||
		!validUUID(lineage.PreSubmitPolicyID) || !validUUID(lineage.PostSubmitPolicyID) ||
		!validUUID(lineage.ReviewPolicyID) || !validUUID(lineage.RevisionPolicyID) ||
		!validUUID(lineage.ContributionPolicyVersionID) ||
		lineage.ReviewPolicyGeneration <= 0 || lineage.RevisionPolicyGeneration <= 0 {
		return revisionInvalid()
	}
	for _, digest := range []string{
		lineage.SourceSnapshotHash, lineage.ArtifactPolicyHash, lineage.PreSubmitBundleHash,
		lineage.PostSubmitPolicyHash, lineage.ReviewPolicyHash, lineage.RevisionPolicyHash,
	} {
		if !contextPolicyDigest.MatchString(digest) {
			return revisionInvalid()
		}
	}
	return nil
}

func validateRevisionRewardSelection(raw json.RawMessage, value *RevisionRewardSelection) error {
	fields, err := contextObject(raw, value, []string{"compensation_mode", "task_size"}, nil)
	if err != nil || !requiredNullable(fields, "instrument", "unit", "quantity") || !oneOf(value.TaskSize, "small", "medium", "large") {
		return revisionInvalid()
	}
	if value.CompensationMode == "unpaid" {
		if value.Instrument != nil || value.Unit != nil || value.Quantity != nil {
			return revisionInvalid()
		}
		return nil
	}
	if value.CompensationMode != "compensated" || value.Instrument == nil || value.Unit == nil || value.Quantity == nil ||
		!validCompensationAward(CompensationAward{Instrument: *value.Instrument, Unit: *value.Unit, Quantity: *value.Quantity}) ||
		!validContributionQuantity(*value.Quantity, *value.Instrument) {
		return revisionInvalid()
	}
	return nil
}
