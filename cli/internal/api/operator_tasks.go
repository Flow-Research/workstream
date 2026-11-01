package api

import (
	"context"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"strings"
)

// OperationalTaskSummary is the status-only system-Operator queue projection.
type OperationalTaskSummary struct {
	TaskID    string `json:"task_id"`
	ProjectID string `json:"project_id"`
	Status    string `json:"status"`
	CreatedAt string `json:"created_at"`
	UpdatedAt string `json:"updated_at"`
}

type OperationalTaskPage struct {
	ProjectID  string
	Items      []OperationalTaskSummary
	NextCursor *string
}

// OperationalTaskLockedContext exposes only exact immutable policy references.
type OperationalTaskLockedContext struct {
	TaskID                                             string   `json:"task_id"`
	ProjectID                                          string   `json:"project_id"`
	LockedGuideVersion                                 string   `json:"locked_guide_version"`
	LockedGuideSourceSnapshotID                        string   `json:"locked_guide_source_snapshot_id"`
	LockedGuideSourceSnapshotHash                      string   `json:"locked_guide_source_snapshot_hash"`
	LockedEffectiveProjectSubmissionArtifactPolicyID   string   `json:"locked_effective_project_submission_artifact_policy_id"`
	LockedEffectiveProjectSubmissionArtifactPolicyHash string   `json:"locked_effective_project_submission_artifact_policy_hash"`
	LockedPreSubmitCheckerPolicyID                     string   `json:"locked_pre_submit_checker_policy_id"`
	LockedPreSubmitCheckerBundleHash                   string   `json:"locked_pre_submit_checker_bundle_hash"`
	LockedPostSubmitCheckerPolicyID                    string   `json:"locked_post_submit_checker_policy_id"`
	LockedPostSubmitCheckerPolicyVersion               string   `json:"locked_post_submit_checker_policy_version"`
	LockedPostSubmitCheckerPolicyHash                  string   `json:"locked_post_submit_checker_policy_hash"`
	LockedReviewPolicyID                               string   `json:"locked_review_policy_id"`
	LockedReviewPolicyGeneration                       *big.Int `json:"locked_review_policy_generation"`
	LockedReviewPolicyHash                             string   `json:"locked_review_policy_hash"`
	LockedRevisionPolicyID                             string   `json:"locked_revision_policy_id"`
	LockedRevisionPolicyGeneration                     *big.Int `json:"locked_revision_policy_generation"`
	LockedRevisionPolicyHash                           string   `json:"locked_revision_policy_hash"`
	LockedContributionPolicyVersionID                  string   `json:"locked_contribution_policy_version_id"`
}

var operationalLockedFields = []string{
	"task_id", "project_id", "locked_guide_version", "locked_guide_source_snapshot_id",
	"locked_guide_source_snapshot_hash", "locked_effective_project_submission_artifact_policy_id",
	"locked_effective_project_submission_artifact_policy_hash", "locked_pre_submit_checker_policy_id",
	"locked_pre_submit_checker_bundle_hash", "locked_post_submit_checker_policy_id",
	"locked_post_submit_checker_policy_version", "locked_post_submit_checker_policy_hash",
	"locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash",
	"locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash",
	"locked_contribution_policy_version_id",
}

func operatorTaskProjectPath(project string) (string, error) {
	if !validUUID(project) || len(project) > 100 {
		return "", errors.New("PROJECT_ID must be a UUID")
	}
	return "/api/v1/operations/projects/" + url.PathEscape(project) + "/tasks", nil
}

func (c *Client) OperationalTasks(ctx context.Context, project string, limit int, cursor *string) (Result[OperationalTaskPage], error) {
	var result Result[OperationalTaskPage]
	path, err := operatorTaskProjectPath(project)
	if err != nil {
		return result, err
	}
	query, err := taskPageQuery(limit, cursor)
	if err != nil {
		return result, err
	}
	raw, err := c.request(ctx, http.MethodGet, path, query, nil)
	if err != nil {
		return result, err
	}
	page, err := decodeTaskPage(raw, project, limit)
	if err != nil || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	value := OperationalTaskPage{ProjectID: page.ProjectID, Items: make([]OperationalTaskSummary, 0, len(page.Items)), NextCursor: page.NextCursor}
	seen := make(map[[16]byte]bool)
	for _, item := range page.Items {
		var task OperationalTaskSummary
		_, err := contextObject(item, &task, []string{"task_id", "project_id", "status", "created_at", "updated_at"}, nil)
		identity, valid := uuidIdentity(task.TaskID)
		if err != nil || !valid || !sameUUID(task.ProjectID, project) || !oneOf(task.Status, taskStatuses...) ||
			!validTime(task.CreatedAt) || !validTime(task.UpdatedAt) || seen[identity] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[identity] = true
		value.Items = append(value.Items, task)
	}
	return Result[OperationalTaskPage]{Raw: raw, Value: value}, nil
}

func (c *Client) OperationalTaskLockedContext(ctx context.Context, project, selector string) (Result[OperationalTaskLockedContext], error) {
	var result Result[OperationalTaskLockedContext]
	path, err := operatorTaskProjectPath(project)
	if err != nil {
		return result, err
	}
	if !validUUID(selector) || len(selector) > 100 {
		return result, errors.New("TASK_ID must be a UUID")
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/"+url.PathEscape(selector)+"/locked-context", "", nil)
	if err != nil {
		return result, err
	}
	var value OperationalTaskLockedContext
	_, err = contextObject(raw, &value, operationalLockedFields, nil)
	if err != nil || !sameUUID(value.TaskID, selector) || !sameUUID(value.ProjectID, project) ||
		strings.TrimSpace(value.LockedGuideVersion) == "" || strings.TrimSpace(value.LockedPostSubmitCheckerPolicyVersion) == "" ||
		value.LockedReviewPolicyGeneration == nil || value.LockedReviewPolicyGeneration.Sign() <= 0 ||
		value.LockedRevisionPolicyGeneration == nil || value.LockedRevisionPolicyGeneration.Sign() <= 0 ||
		!c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, id := range []string{
		value.LockedGuideSourceSnapshotID, value.LockedEffectiveProjectSubmissionArtifactPolicyID,
		value.LockedPreSubmitCheckerPolicyID, value.LockedPostSubmitCheckerPolicyID,
		value.LockedReviewPolicyID, value.LockedRevisionPolicyID, value.LockedContributionPolicyVersionID,
	} {
		if !validUUID(id) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	for _, digest := range []string{
		value.LockedGuideSourceSnapshotHash, value.LockedEffectiveProjectSubmissionArtifactPolicyHash,
		value.LockedPreSubmitCheckerBundleHash, value.LockedPostSubmitCheckerPolicyHash,
		value.LockedReviewPolicyHash, value.LockedRevisionPolicyHash,
	} {
		if !contextPolicyDigest.MatchString(digest) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	return Result[OperationalTaskLockedContext]{Raw: raw, Value: value}, nil
}
