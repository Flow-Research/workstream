package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"strings"
)

// ManagementWorkContext is the manager projection. It has no contributor
// lifecycle hints, guide documents, or compensation terms.
type ManagementWorkContext struct {
	Task                        TaskDetail              `json:"task"`
	Project                     ContextProject          `json:"project"`
	Guide                       ContextGuide            `json:"guide"`
	ReviewPolicy                ManagementContextPolicy `json:"review_policy"`
	RevisionPolicy              ManagementContextPolicy `json:"revision_policy"`
	ContributionPolicyVersionID string                  `json:"contribution_policy_version_id"`
}

type ManagementContextPolicy struct {
	PolicyID   string   `json:"policy_id"`
	Generation *big.Int `json:"generation"`
	PolicyHash string   `json:"policy_hash"`
}

type ManagementLineage struct {
	GuideVersion             string   `json:"locked_guide_version"`
	GuideSourceID            string   `json:"locked_guide_source_snapshot_id"`
	GuideSourceHash          string   `json:"locked_guide_source_snapshot_hash"`
	ArtifactPolicyID         string   `json:"locked_effective_project_submission_artifact_policy_id"`
	ArtifactPolicyHash       string   `json:"locked_effective_project_submission_artifact_policy_hash"`
	PreSubmitPolicyID        string   `json:"locked_pre_submit_checker_policy_id"`
	PreSubmitBundleHash      string   `json:"locked_pre_submit_checker_bundle_hash"`
	PostSubmitPolicyID       string   `json:"locked_post_submit_checker_policy_id"`
	PostSubmitPolicyVersion  string   `json:"locked_post_submit_checker_policy_version"`
	PostSubmitPolicyHash     string   `json:"locked_post_submit_checker_policy_hash"`
	ReviewPolicyID           string   `json:"locked_review_policy_id"`
	ReviewPolicyGeneration   *big.Int `json:"locked_review_policy_generation"`
	ReviewPolicyHash         string   `json:"locked_review_policy_hash"`
	RevisionPolicyID         string   `json:"locked_revision_policy_id"`
	RevisionPolicyGeneration *big.Int `json:"locked_revision_policy_generation"`
	RevisionPolicyHash       string   `json:"locked_revision_policy_hash"`
	ContributionPolicyID     string   `json:"locked_contribution_policy_version_id"`
}

var managementLineageFields = []string{
	"locked_guide_version", "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash",
	"locked_effective_project_submission_artifact_policy_id", "locked_effective_project_submission_artifact_policy_hash",
	"locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash",
	"locked_post_submit_checker_policy_id", "locked_post_submit_checker_policy_version", "locked_post_submit_checker_policy_hash",
	"locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash",
	"locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash",
	"locked_contribution_policy_version_id",
}

func validManagementLineage(v ManagementLineage) bool {
	for _, id := range []string{v.GuideSourceID, v.ArtifactPolicyID, v.PreSubmitPolicyID,
		v.PostSubmitPolicyID, v.ReviewPolicyID, v.RevisionPolicyID, v.ContributionPolicyID} {
		if !validUUID(id) {
			return false
		}
	}
	for _, digest := range []string{v.GuideSourceHash, v.ArtifactPolicyHash, v.PreSubmitBundleHash,
		v.PostSubmitPolicyHash, v.ReviewPolicyHash, v.RevisionPolicyHash} {
		if !contextPolicyDigest.MatchString(digest) {
			return false
		}
	}
	return strings.TrimSpace(v.GuideVersion) != "" && strings.TrimSpace(v.PostSubmitPolicyVersion) != "" &&
		v.ReviewPolicyGeneration != nil && v.ReviewPolicyGeneration.Sign() > 0 &&
		v.RevisionPolicyGeneration != nil && v.RevisionPolicyGeneration.Sign() > 0
}

type PostSubmitPolicySummary struct {
	SchemaVersion     *string  `json:"schema_version"`
	DefaultCheckers   []string `json:"default_checkers"`
	RequiredCheckers  []string `json:"required_checkers"`
	WarningCheckers   []string `json:"warning_checkers"`
	ExecutionCheckers []string `json:"execution_checkers"`
	BlockingSeverity  []string `json:"blocking_severities"`
}

type ManagementLockedContext struct {
	ManagementLineage
	TaskID        string                  `json:"task_id"`
	ProjectID     string                  `json:"project_id"`
	PolicySummary PostSubmitPolicySummary `json:"locked_post_submit_checker_policy_body_summary"`
}

func managerTaskContextPath(project, task, suffix string) (string, error) {
	path, err := taskProjectPath(project)
	if err != nil {
		return "", err
	}
	if !submissionSelector(task) {
		return "", errors.New("TASK_ID must be a UUID")
	}
	return path + "/" + url.PathEscape(task) + suffix, nil
}

func (c *Client) ManagementRequirements(ctx context.Context, project, task string) (Result[SubmissionRequirements], error) {
	var result Result[SubmissionRequirements]
	path, err := managerTaskContextPath(project, task, "/submission-requirements")
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, "", nil, "", http.StatusOK, maxResponseBytes)
	if err != nil {
		return result, err
	}
	value, err := decodeSubmissionRequirements(raw, task, project)
	if err != nil || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[SubmissionRequirements]{Raw: raw, Value: value}, nil
}

func (c *Client) ManagementWorkContext(ctx context.Context, project, task string) (Result[ManagementWorkContext], error) {
	var result Result[ManagementWorkContext]
	path, err := managerTaskContextPath(project, task, "/work-context")
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, "", nil, "", http.StatusOK, maxGuideContextResponseBytes)
	if err != nil {
		return result, err
	}
	var value ManagementWorkContext
	fields, err := contextObject(raw, &value, []string{"task", "project", "guide", "review_policy", "revision_policy", "contribution_policy_version_id"}, nil)
	if err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if err := decodeTask(fields["task"], &value.Task, true); err != nil || !sameUUID(value.Task.TaskID, task) || !validTask(value.Task.TaskSummary, project) || !oneOf(value.Task.TaskSize, "small", "medium", "large") || !oneOf(value.Task.Status, taskStatuses...) || !validUUID(value.Task.CreatedBy) ||
		(value.Task.AssignedTo != nil && !validUUID(*value.Task.AssignedTo)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if _, err := contextObject(fields["project"], &value.Project, []string{"id", "name", "slug"}, nil); err != nil || !sameUUID(value.Project.ID, project) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if _, err := contextObject(fields["guide"], &value.Guide, []string{"id", "project_id", "version", "effective_at"}, nil); err != nil || !validUUID(value.Guide.ID) || !sameUUID(value.Guide.ProjectID, project) || strings.TrimSpace(value.Guide.Version) == "" || !validTime(value.Guide.EffectiveAt) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, policy := range []struct {
		raw   json.RawMessage
		value *ManagementContextPolicy
	}{{fields["review_policy"], &value.ReviewPolicy}, {fields["revision_policy"], &value.RevisionPolicy}} {
		if _, err := contextObject(policy.raw, policy.value, []string{"policy_id", "generation", "policy_hash"}, nil); err != nil || !validUUID(policy.value.PolicyID) || policy.value.Generation == nil || policy.value.Generation.Sign() <= 0 || !contextPolicyDigest.MatchString(policy.value.PolicyHash) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	if !validUUID(value.ContributionPolicyVersionID) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ManagementWorkContext]{Raw: raw, Value: value}, nil
}

func (c *Client) ManagementLockedContext(ctx context.Context, project, task string) (Result[ManagementLockedContext], error) {
	var result Result[ManagementLockedContext]
	path, err := managerTaskContextPath(project, task, "/locked-context")
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, "", nil, "", http.StatusOK, maxResponseBytes)
	if err != nil {
		return result, err
	}
	var value ManagementLockedContext
	required := append(append([]string{}, managementLineageFields...), "task_id", "project_id", "locked_post_submit_checker_policy_body_summary")
	fields, err := contextObject(raw, &value, required, nil)
	if err != nil || !sameUUID(value.TaskID, task) || !sameUUID(value.ProjectID, project) || !validManagementLineage(value.ManagementLineage) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if _, err := contextObject(fields["locked_post_submit_checker_policy_body_summary"], &value.PolicySummary,
		[]string{"default_checkers", "required_checkers", "warning_checkers", "execution_checkers", "blocking_severities"},
		[]string{"default_checkers", "required_checkers", "warning_checkers", "execution_checkers", "blocking_severities"}); err != nil || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ManagementLockedContext]{Raw: raw, Value: value}, nil
}
