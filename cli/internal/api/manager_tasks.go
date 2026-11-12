package api

import (
	"bytes"
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math/big"
	"net/http"
	"reflect"
	"time"
)

// ManagerTask retains the full management mutation projection. Embedding the
// common values here does not enlarge the contributor decoder's allowed fields.
type ManagerTask struct {
	MutationTask
	LockedGuideSourceSnapshotID                        string  `json:"locked_guide_source_snapshot_id"`
	LockedGuideSourceSnapshotHash                      string  `json:"locked_guide_source_snapshot_hash"`
	LockedEffectiveProjectSubmissionArtifactPolicyID   string  `json:"locked_effective_project_submission_artifact_policy_id"`
	LockedEffectiveProjectSubmissionArtifactPolicyHash string  `json:"locked_effective_project_submission_artifact_policy_hash"`
	LockedPreSubmitCheckerPolicyID                     string  `json:"locked_pre_submit_checker_policy_id"`
	LockedPreSubmitCheckerBundleHash                   string  `json:"locked_pre_submit_checker_bundle_hash"`
	SourceRef                                          *string `json:"source_ref"`
	SourcePayloadHash                                  *string `json:"source_payload_hash"`
	ImportBatchID                                      *string `json:"import_batch_id"`
	ExternalTaskID                                     *string `json:"external_task_id"`
	CreatedBy                                          string  `json:"created_by"`
	AssignedTo                                         *string `json:"assigned_to"`
}

type taskCreateInput struct {
	TaskSize             string   `json:"task_size"`
	Title                string   `json:"title"`
	Description          string   `json:"description"`
	TaskType             *string  `json:"task_type"`
	Difficulty           *string  `json:"difficulty"`
	SkillTags            []string `json:"skill_tags"`
	EstimatedTimeMinutes *big.Int `json:"estimated_time_minutes"`
	SourceType           string   `json:"source_type"`
	SourceRef            *string  `json:"source_ref"`
	SourcePayloadHash    *string  `json:"source_payload_hash"`
	ImportBatchID        *string  `json:"import_batch_id"`
	ExternalTaskID       *string  `json:"external_task_id"`
	AcceptanceCriteria   *string  `json:"acceptance_criteria"`
	RejectionCriteria    *string  `json:"rejection_criteria"`
	DeadlineAt           *string  `json:"deadline_at"`
}

func (c *Client) CreateTask(ctx context.Context, project string, body json.RawMessage, key string) (Result[ManagerTask], error) {
	var result Result[ManagerTask]
	if !validUUID(project) || project != canonicalUUID(project) || !validUUID(key) || len(key) > 100 {
		return result, errors.New("PROJECT_ID must be a canonical UUID and --idempotency-key a UUID")
	}
	input := taskCreateInput{SourceType: "manual", TaskSize: "small", SkillTags: []string{}}
	var fields map[string]json.RawMessage
	err := jsonv2.Unmarshal(body, &fields)
	if len(body) > MaxGuideInputBytes || err != nil || fields == nil ||
		decodeTaskFields(body, &input, []string{"title", "description"}, nil) != nil ||
		(fields["source_type"] != nil && bytes.Equal(bytes.TrimSpace(fields["source_type"]), []byte("null"))) ||
		!oneOf(input.TaskSize, "small", "medium", "large") ||
		(fields["task_size"] != nil && bytes.Equal(bytes.TrimSpace(fields["task_size"]), []byte("null"))) ||
		(input.SourceType != "manual" && input.SourceType != "markdown_import" && input.SourceType != "csv_import") ||
		(input.EstimatedTimeMinutes != nil && input.EstimatedTimeMinutes.Sign() <= 0) ||
		(input.DeadlineAt != nil && !validTime(*input.DeadlineAt)) {
		return result, errors.New("--input must contain a bounded closed TaskCreate JSON object")
	}
	path, err := taskProjectPath(project)
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPost, path, "", body, key, http.StatusCreated, maxGuideResponseBytes)
	if err != nil {
		return result, managerTaskFailure(err)
	}
	value, err := decodeManagerTask(raw, project, "", "draft")
	if err != nil || !sameTaskDeclaration(value, input, fields["task_size"] != nil) || !c.safeMutationResponse(raw) {
		return result, managerTaskFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[ManagerTask]{Raw: raw, Value: value}, nil
}

func (c *Client) PrepareTask(ctx context.Context, project, selector, action, key string, reason *string) (Result[ManagerTask], error) {
	var result Result[ManagerTask]
	if !validUUID(project) || len(project) > 100 || (action != "screen" && action != "release") {
		return result, errors.New("select a project UUID and screen or release action")
	}
	raw, err := c.taskWrite(ctx, selector, action, key, reason, maxGuideResponseBytes)
	if err != nil {
		return result, managerTaskFailure(err)
	}
	status := "screening"
	if action == "release" {
		status = "ready"
	}
	value, err := decodeManagerTask(raw, project, selector, status)
	if err != nil || !c.safeMutationResponse(raw) {
		return result, managerTaskFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[ManagerTask]{Raw: raw, Value: value}, nil
}

func decodeManagerTask(raw json.RawMessage, project, selector, status string) (ManagerTask, error) {
	var task ManagerTask
	strings := []string{"id", "project_id", "title", "description", "source_type", "status", "created_by", "created_at", "updated_at"}
	locks := []string{
		"locked_contribution_policy_version_id", "locked_guide_version", "locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash",
		"locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash", "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash",
		"locked_effective_project_submission_artifact_policy_id", "locked_effective_project_submission_artifact_policy_hash", "locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash",
	}
	if decodeTaskFields(raw, &task, strings, []string{"skill_tags"}) != nil ||
		!validUUID(task.ID) || !sameUUID(task.ProjectID, project) || (selector != "" && !sameUUID(task.ID, selector)) ||
		task.Status != status || !validUUID(task.CreatedBy) || task.AssignedTo != nil ||
		!validTime(task.CreatedAt) || !validTime(task.UpdatedAt) || (task.DeadlineAt != nil && !validTime(*task.DeadlineAt)) ||
		(task.EstimatedTimeMinutes != nil && *task.EstimatedTimeMinutes <= 0) {
		return task, errors.New("invalid manager task response")
	}
	var fields map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &fields); err != nil {
		return task, err
	}
	if !validTaskSizeField(fields, task.TaskSize) {
		return task, errors.New("invalid task size")
	}
	for _, key := range locks {
		field, present := fields[key]
		null := bytes.Equal(bytes.TrimSpace(field), []byte("null"))
		if (status == "draft" && present && !null) || (status != "draft" && (!present || null)) {
			return task, errors.New("invalid task lineage presence")
		}
	}
	if status != "draft" {
		if !validUUID(task.LockedContributionPolicyVersionID) || task.LockedGuideVersion == "" ||
			!validUUID(task.LockedReviewPolicyID) || task.LockedReviewPolicyGeneration <= 0 || !policyHash.MatchString(task.LockedReviewPolicyHash) ||
			!validUUID(task.LockedRevisionPolicyID) || task.LockedRevisionPolicyGeneration <= 0 || !policyHash.MatchString(task.LockedRevisionPolicyHash) ||
			!validUUID(task.LockedGuideSourceSnapshotID) || !policyHash.MatchString(task.LockedGuideSourceSnapshotHash) ||
			!validUUID(task.LockedEffectiveProjectSubmissionArtifactPolicyID) || !policyHash.MatchString(task.LockedEffectiveProjectSubmissionArtifactPolicyHash) ||
			!validUUID(task.LockedPreSubmitCheckerPolicyID) || !policyHash.MatchString(task.LockedPreSubmitCheckerBundleHash) {
			return task, errors.New("invalid task lineage")
		}
	}
	return task, nil
}

func validTaskSizeField(fields map[string]json.RawMessage, size *string) bool {
	_, present := fields["task_size"]
	return !present || (size != nil && oneOf(*size, "small", "medium", "large"))
}

func sameTaskDeclaration(t ManagerTask, input taskCreateInput, sizeExplicit bool) bool {
	if t.TaskSize == nil && sizeExplicit || t.TaskSize != nil && *t.TaskSize != input.TaskSize {
		return false
	}

	minutes := (*big.Int)(nil)
	if t.EstimatedTimeMinutes != nil {
		minutes = big.NewInt(int64(*t.EstimatedTimeMinutes))
	}
	return t.Title == input.Title && t.Description == input.Description && t.SourceType == input.SourceType &&
		reflect.DeepEqual(t.TaskType, input.TaskType) && reflect.DeepEqual(t.Difficulty, input.Difficulty) &&
		reflect.DeepEqual(t.SkillTags, input.SkillTags) && reflect.DeepEqual(minutes, input.EstimatedTimeMinutes) &&
		reflect.DeepEqual(t.SourceRef, input.SourceRef) && reflect.DeepEqual(t.SourcePayloadHash, input.SourcePayloadHash) &&
		reflect.DeepEqual(t.ImportBatchID, input.ImportBatchID) &&
		reflect.DeepEqual(t.ExternalTaskID, input.ExternalTaskID) && reflect.DeepEqual(t.AcceptanceCriteria, input.AcceptanceCriteria) &&
		reflect.DeepEqual(t.RejectionCriteria, input.RejectionCriteria) && sameTaskDeadline(t.DeadlineAt, input.DeadlineAt)
}

func sameTaskDeadline(returned, submitted *string) bool {
	if returned == nil || submitted == nil {
		return returned == nil && submitted == nil
	}
	want, inputErr := time.Parse(time.RFC3339Nano, *submitted)
	got, responseErr := time.Parse(time.RFC3339Nano, *returned)
	// Pydantic/PostgreSQL retain microsecond precision and normalize timezones.
	return inputErr == nil && responseErr == nil && got.Equal(want.Truncate(time.Microsecond))
}

func managerTaskFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "manager task outcome unknown; replay only the unchanged action, selectors, input/reason and idempotency key; project task reads are observations, not rollback proof"
	}
	return err
}
