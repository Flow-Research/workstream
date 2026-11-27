package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math/big"
	"net/http"
	"net/url"
)

// Management history is deliberately separate from the contributor projection.
type ManagementSubmission struct {
	SubmissionHistory
	ContributorID        string   `json:"contributor_id"`
	AssignmentID         string   `json:"task_assignment_id"`
	ContributionPolicyID string   `json:"contribution_policy_version_id"`
	GuideVersion         string   `json:"locked_guide_version"`
	PostSubmitPolicyID   string   `json:"locked_post_submit_checker_policy_id"`
	PostSubmitVersion    string   `json:"locked_post_submit_checker_policy_version"`
	PostSubmitHash       string   `json:"locked_post_submit_checker_policy_hash"`
	ReviewPolicyID       string   `json:"locked_review_policy_id"`
	ReviewGeneration     *big.Int `json:"locked_review_policy_generation"`
	ReviewHash           string   `json:"locked_review_policy_hash"`
	RevisionPolicyID     string   `json:"locked_revision_policy_id"`
	RevisionGeneration   *big.Int `json:"locked_revision_policy_generation"`
	RevisionHash         string   `json:"locked_revision_policy_hash"`
	GuideSourceID        *string  `json:"locked_guide_source_snapshot_id"`
	GuideSourceHash      *string  `json:"locked_guide_source_snapshot_hash"`
	ArtifactPolicyID     *string  `json:"locked_effective_project_submission_artifact_policy_id"`
	ArtifactPolicyHash   *string  `json:"locked_effective_project_submission_artifact_policy_hash"`
	PreSubmitPolicyID    *string  `json:"locked_pre_submit_checker_policy_id"`
	PreSubmitBundleHash  *string  `json:"locked_pre_submit_checker_bundle_hash"`
}

var managementSubmissionFields = []string{
	"contributor_id", "task_assignment_id", "contribution_policy_version_id", "locked_guide_version",
	"locked_post_submit_checker_policy_id", "locked_post_submit_checker_policy_version", "locked_post_submit_checker_policy_hash",
	"locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash",
	"locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash",
	"locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash",
	"locked_effective_project_submission_artifact_policy_id", "locked_effective_project_submission_artifact_policy_hash",
	"locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash",
}

func stripJSONFields(raw json.RawMessage, keys ...string) (json.RawMessage, error) {
	var fields map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &fields); err != nil || fields == nil {
		return nil, errors.New("invalid object")
	}
	for _, key := range keys {
		delete(fields, key)
	}
	return jsonv2.Marshal(fields)
}

func validOptionalID(value *string) bool { return value == nil || validUUID(*value) }
func validOptionalHash(value *string) bool {
	return value == nil || contextPolicyDigest.MatchString(*value)
}

func decodeManagementSubmission(raw json.RawMessage, task, submission string) (ManagementSubmission, error) {
	var value ManagementSubmission
	bad := &Failure{Code: "invalid_api_response"}
	baseRequired := []string{"id", "task_id", "version", "status", "submitted_at", "finding_counts", "evidence_items"}
	required := append(append([]string{}, baseRequired...), managementSubmissionFields[:13]...)
	fields, err := contextObject(raw, &value, required, nil)
	if err != nil || !requiredNullable(fields, "status_reason", "decided_at", "locked_at", "supersedes_submission_id", "summary", "feedback") ||
		!requiredNullable(fields, "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash",
			"locked_effective_project_submission_artifact_policy_id", "locked_effective_project_submission_artifact_policy_hash",
			"locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash") {
		return value, bad
	}
	base, err := stripJSONFields(raw, managementSubmissionFields...)
	if err != nil {
		return value, bad
	}
	if value.SubmissionHistory, err = decodeSubmission(base, task, submission); err != nil {
		return value, bad
	}
	if !validUUID(value.ContributorID) || !validUUID(value.AssignmentID) || !validUUID(value.ContributionPolicyID) ||
		value.GuideVersion == "" || !validUUID(value.PostSubmitPolicyID) || value.PostSubmitVersion == "" || !contextPolicyDigest.MatchString(value.PostSubmitHash) ||
		!validUUID(value.ReviewPolicyID) || value.ReviewGeneration == nil || value.ReviewGeneration.Sign() <= 0 || !contextPolicyDigest.MatchString(value.ReviewHash) ||
		!validUUID(value.RevisionPolicyID) || value.RevisionGeneration == nil || value.RevisionGeneration.Sign() <= 0 || !contextPolicyDigest.MatchString(value.RevisionHash) ||
		!validOptionalID(value.GuideSourceID) || !validOptionalHash(value.GuideSourceHash) ||
		!validOptionalID(value.ArtifactPolicyID) || !validOptionalHash(value.ArtifactPolicyHash) ||
		!validOptionalID(value.PreSubmitPolicyID) || !validOptionalHash(value.PreSubmitBundleHash) {
		return value, bad
	}
	if (value.GuideSourceID == nil) != (value.GuideSourceHash == nil) ||
		(value.ArtifactPolicyID == nil) != (value.ArtifactPolicyHash == nil) ||
		(value.PreSubmitPolicyID == nil) != (value.PreSubmitBundleHash == nil) {
		return value, bad
	}
	return value, nil
}

type ManagementSubmissionPage struct {
	Items  []ManagementSubmission `json:"items"`
	Cursor *string                `json:"next_cursor"`
}

func managerHistoryPath(project, resource, suffix string) (string, error) {
	path, err := projectReadPath(project, suffix)
	if err != nil {
		return "", err
	}
	if !submissionSelector(resource) {
		return "", errors.New("resource must be a UUID")
	}
	return path + url.PathEscape(resource), nil
}

func (c *Client) ManagementTaskSubmissions(ctx context.Context, project, task string, limit int, cursor *string) (Result[ManagementSubmissionPage], error) {
	var result Result[ManagementSubmissionPage]
	path, err := managerHistoryPath(project, task, "/tasks/")
	if err != nil {
		return result, err
	}
	query, err := submissionPageQuery(limit, cursor)
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path+"/submissions", query, nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	var envelope struct {
		Items  []json.RawMessage `json:"items"`
		Cursor *string           `json:"next_cursor"`
	}
	fields, err := contextObject(raw, &envelope, []string{"items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || envelope.Items == nil || len(envelope.Items) > limit ||
		(envelope.Cursor != nil && (!validSubmissionCursor(*envelope.Cursor) || len(envelope.Items) == 0)) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	page := ManagementSubmissionPage{Items: make([]ManagementSubmission, 0, len(envelope.Items)), Cursor: envelope.Cursor}
	seen := map[[16]byte]bool{}
	for _, item := range envelope.Items {
		value, err := decodeManagementSubmission(item, task, "")
		id, _ := uuidIdentity(value.ID)
		if err != nil || seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[ManagementSubmissionPage]{Raw: raw, Value: page}, nil
}

func (c *Client) ManagementSubmission(ctx context.Context, project, submission string) (Result[ManagementSubmission], error) {
	var result Result[ManagementSubmission]
	path, err := managerHistoryPath(project, submission, "/submissions/")
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, "", nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	value, err := decodeManagementSubmission(raw, "", submission)
	if err != nil || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ManagementSubmission]{Raw: raw, Value: value}, nil
}

type ManagementFinding struct {
	ContributorFinding
	Message      string `json:"message"`
	BlocksReview bool   `json:"blocks_review"`
}
type ManagementCheckerRun struct {
	SubmissionCheckerRun
	RoutingRecommendation string              `json:"routing_recommendation"`
	OutcomeSource         string              `json:"outcome_source"`
	TriggerSource         string              `json:"trigger_source"`
	GuideVersion          string              `json:"locked_guide_version"`
	PostSubmitPolicyID    string              `json:"locked_post_submit_checker_policy_id"`
	PostSubmitVersion     string              `json:"locked_post_submit_checker_policy_version"`
	PostSubmitHash        string              `json:"locked_post_submit_checker_policy_hash"`
	ReviewPolicyID        string              `json:"locked_review_policy_id"`
	ReviewGeneration      *big.Int            `json:"locked_review_policy_generation"`
	ReviewHash            string              `json:"locked_review_policy_hash"`
	RevisionPolicyID      string              `json:"locked_revision_policy_id"`
	RevisionGeneration    *big.Int            `json:"locked_revision_policy_generation"`
	RevisionHash          string              `json:"locked_revision_policy_hash"`
	Results               []ManagementFinding `json:"results"`
}

var managementRunFields = []string{"routing_recommendation", "outcome_source", "trigger_source", "locked_guide_version", "locked_post_submit_checker_policy_id", "locked_post_submit_checker_policy_version", "locked_post_submit_checker_policy_hash", "locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash", "locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash"}

func decodeManagementRun(raw json.RawMessage, submission, run string) (ManagementCheckerRun, error) {
	var value ManagementCheckerRun
	bad := &Failure{Code: "invalid_api_response"}
	fields, err := contextObject(raw, &value, append([]string{"id", "task_id", "submission_id", "submission_version", "status", "attempt_number", "is_current_for_submission", "created_at", "results"}, managementRunFields...), nil)
	if err != nil || !oneOf(value.RoutingRecommendation, "not_evaluated", "allow_review", "needs_revision", "task_setup_blocked") || !oneOf(value.OutcomeSource, "none", "auto_checker") ||
		value.TriggerSource == "" || value.GuideVersion == "" || !validUUID(value.PostSubmitPolicyID) || value.PostSubmitVersion == "" || !contextPolicyDigest.MatchString(value.PostSubmitHash) ||
		!validUUID(value.ReviewPolicyID) || value.ReviewGeneration == nil || value.ReviewGeneration.Sign() <= 0 || !contextPolicyDigest.MatchString(value.ReviewHash) ||
		!validUUID(value.RevisionPolicyID) || value.RevisionGeneration == nil || value.RevisionGeneration.Sign() <= 0 || !contextPolicyDigest.MatchString(value.RevisionHash) {
		return value, bad
	}
	var results []json.RawMessage
	if json.Unmarshal(fields["results"], &results) != nil || results == nil || len(results) != len(value.Results) {
		return value, bad
	}
	base, err := stripJSONFields(raw, managementRunFields...)
	if err != nil {
		return value, bad
	}
	var baseObject map[string]json.RawMessage
	if jsonv2.Unmarshal(base, &baseObject) != nil {
		return value, bad
	}
	baseResults := make([]json.RawMessage, 0, len(results))
	for i, item := range results {
		f, err := contextObject(item, &value.Results[i], []string{"id", "checker_name", "status", "severity", "message", "blocks_review"}, nil)
		if err != nil {
			return value, bad
		}
		delete(f, "message")
		delete(f, "blocks_review")
		baseItem, err := jsonv2.Marshal(f)
		if err != nil {
			return value, bad
		}
		baseResults = append(baseResults, baseItem)
	}
	baseObject["results"], err = jsonv2.Marshal(baseResults)
	if err != nil {
		return value, bad
	}
	base, err = jsonv2.Marshal(baseObject)
	if err != nil {
		return value, bad
	}
	if value.SubmissionCheckerRun, err = decodeSubmissionChecker(base, submission, run); err != nil {
		return value, bad
	}
	return value, nil
}

func (c *Client) ManagementCheckerRuns(ctx context.Context, project, submission, run string, limit int, cursor *string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	path, err := managerHistoryPath(project, submission, "/submissions/")
	if err != nil {
		return result, err
	}
	path += "/checker-runs"
	query := ""
	if run != "" {
		if !submissionSelector(run) || cursor != nil {
			return result, errors.New("run must be a UUID without pagination")
		}
		path += "/" + url.PathEscape(run)
	} else if query, err = submissionPageQuery(limit, cursor); err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, query, nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	if !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if run != "" {
		if _, err := decodeManagementRun(raw, submission, run); err != nil {
			return result, err
		}
		return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
	}
	var envelope struct {
		Items  []json.RawMessage `json:"items"`
		Cursor *string           `json:"next_cursor"`
	}
	fields, err := contextObject(raw, &envelope, []string{"items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || envelope.Items == nil || len(envelope.Items) > limit ||
		(envelope.Cursor != nil && (!validSubmissionCursor(*envelope.Cursor) || len(envelope.Items) == 0)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	var task string
	for _, item := range envelope.Items {
		value, err := decodeManagementRun(item, submission, "")
		id, _ := uuidIdentity(value.ID)
		if err != nil || seen[id] || (task != "" && !sameUUID(task, value.Task)) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		task = value.Task
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}
