package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"unicode/utf8"

	"github.com/Flow-Research/workstream/cli/internal/taskimport"
)

const taskImportResponseLimit = 16 * 1024 * 1024
const taskBatchTransitionResponseLimit = 2 * 1024 * 1024

// ImportedTask identifies one original DRAFT creation, even after later advancement.
type ImportedTask struct {
	TaskSize          *string `json:"task_size,omitempty"`
	ID                string  `json:"id"`
	ExternalTaskID    string  `json:"external_task_id"`
	Status            string  `json:"status"`
	ProjectID         string  `json:"project_id"`
	SourceType        string  `json:"source_type"`
	SourceRef         string  `json:"source_ref"`
	SourcePayloadHash string  `json:"source_payload_hash"`
	ImportBatchID     string  `json:"import_batch_id"`
	CreatedBy         string  `json:"created_by"`
	CreatedAt         string  `json:"created_at"`
	UpdatedAt         string  `json:"updated_at"`
}

// TaskImportBatch preserves original complete ordered creation custody.
type TaskImportBatch struct {
	BatchID        string         `json:"batch_id"`
	ProjectID      string         `json:"project_id"`
	SourceID       string         `json:"source_id"`
	SHA256         string         `json:"sha256"`
	ByteCount      int            `json:"byte_count"`
	SchemaVersion  string         `json:"schema_version"`
	MappingVersion string         `json:"mapping_version"`
	Label          *string        `json:"label"`
	RowCount       int            `json:"row_count"`
	CreatedAt      string         `json:"created_at"`
	Tasks          []ImportedTask `json:"-"`
}

type taskImportEnvelope struct {
	BatchID        string            `json:"batch_id"`
	ProjectID      string            `json:"project_id"`
	SourceID       string            `json:"source_id"`
	SHA256         string            `json:"sha256"`
	ByteCount      int               `json:"byte_count"`
	SchemaVersion  string            `json:"schema_version"`
	MappingVersion string            `json:"mapping_version"`
	Label          *string           `json:"label"`
	RowCount       int               `json:"row_count"`
	CreatedAt      string            `json:"created_at"`
	Tasks          []json.RawMessage `json:"tasks"`
}

type CurrentBatchTask struct {
	TaskID   string `json:"task_id"`
	RowIndex int    `json:"row_index"`
	Status   string `json:"status"`
}

type TaskImportBatchStatus struct {
	Creation     TaskImportBatch
	CurrentTasks []CurrentBatchTask
}

type TaskBatchTransitionTask struct {
	TaskID                            string `json:"task_id"`
	RowIndex                          int    `json:"row_index"`
	Status                            string `json:"status"`
	LockedGuideVersion                string `json:"locked_guide_version"`
	LockedContributionPolicyVersionID string `json:"locked_contribution_policy_version_id"`
	LockedContextHash                 string `json:"locked_context_hash"`
}

type TaskBatchTransition struct {
	ProjectID string                    `json:"project_id"`
	BatchID   string                    `json:"batch_id"`
	Operation string                    `json:"operation"`
	RowCount  int                       `json:"row_count"`
	Tasks     []TaskBatchTransitionTask `json:"tasks"`
}

func taskImportBatchPath(project string) string {
	return "/api/v1/projects/" + url.PathEscape(project) + "/task-import-batches"
}

func validBatchSelectors(values ...string) bool {
	for _, value := range values {
		if len(value) > 100 || !validUUID(value) {
			return false
		}
	}
	return true
}

// ImportTaskBatch selects existing source custody. It does not upload, screen or release.
func (c *Client) ImportTaskBatch(ctx context.Context, project, source, key string) (Result[TaskImportBatch], error) {
	var result Result[TaskImportBatch]
	if !validBatchSelectors(project, source, key) {
		return result, errors.New("PROJECT_ID, SOURCE_ID and --idempotency-key must be UUIDs")
	}
	body, _ := json.Marshal(map[string]string{"source_id": source})
	raw, err := c.requestWithClientAndResponseLimit(ctx, c.taskBatchHTTP, http.MethodPost, taskImportBatchPath(project), "", body, key, http.StatusCreated, taskImportResponseLimit)
	if err != nil {
		return result, taskBatchWriteFailure(err)
	}
	value, err := c.decodeTaskImportBatch(raw, project, "")
	if err != nil {
		return result, taskBatchWriteFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	// Exact-file recovery retains the original source and rows. A different
	// selector must establish verified equivalent bytes through its own public
	// read; failure after the successful POST cannot become a known write denial.
	if !sameUUID(value.SourceID, source) {
		selected, err := c.TaskImportSourceStatus(ctx, project, source)
		if err != nil || selected.Value.Status != "verified" || selected.Value.SHA256 != value.SHA256 || selected.Value.ByteCount != value.ByteCount {
			return result, taskBatchWriteFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
		}
	}
	return Result[TaskImportBatch]{Raw: raw, Value: value}, nil
}

func (c *Client) TaskBatchStatus(ctx context.Context, project, batch string) (Result[TaskImportBatchStatus], error) {
	var result Result[TaskImportBatchStatus]
	if !validBatchSelectors(project, batch) {
		return result, errors.New("PROJECT_ID and BATCH_ID must be UUIDs")
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, taskImportBatchPath(project)+"/"+url.PathEscape(batch), "", nil, "", http.StatusOK, taskImportResponseLimit)
	if err != nil {
		return result, err
	}
	var envelope struct {
		Creation     json.RawMessage   `json:"creation"`
		CurrentTasks []json.RawMessage `json:"current_tasks"`
	}
	if _, err = contextObject(raw, &envelope, []string{"creation", "current_tasks"}, nil); err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	creation, err := c.decodeTaskImportBatch(envelope.Creation, project, batch)
	if err != nil || len(envelope.CurrentTasks) != creation.RowCount {
		return result, &Failure{Code: "invalid_api_response"}
	}
	value := TaskImportBatchStatus{Creation: creation, CurrentTasks: make([]CurrentBatchTask, 0, creation.RowCount)}
	for index, rawTask := range envelope.CurrentTasks {
		var task CurrentBatchTask
		_, err = contextObject(rawTask, &task, []string{"task_id", "row_index", "status"}, nil)
		if err != nil || task.RowIndex != index || !sameUUID(task.TaskID, creation.Tasks[index].ID) || !batchStatusPattern.MatchString(task.Status) || !c.safeMetadata(task.Status) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		value.CurrentTasks = append(value.CurrentTasks, task)
	}
	return Result[TaskImportBatchStatus]{Raw: raw, Value: value}, nil
}

func (c *Client) TransitionTaskBatch(ctx context.Context, project, batch, operation, key string, reason *string) (Result[TaskBatchTransition], error) {
	var result Result[TaskBatchTransition]
	if !validBatchSelectors(project, batch, key) || (operation != "screen" && operation != "release") {
		return result, errors.New("PROJECT_ID, BATCH_ID and --idempotency-key must be UUIDs; action must be screen or release")
	}
	if (reason != nil && (!utf8.ValidString(*reason) || utf8.RuneCountInString(*reason) > 1000)) ||
		(operation == "release" && (reason == nil || strings.TrimSpace(*reason) == "")) {
		return result, errors.New("reason must contain at most 1000 UTF-8 characters; release requires a nonblank reason")
	}
	body, err := json.Marshal(struct {
		Reason *string `json:"reason"`
	}{reason})
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithClientAndResponseLimit(ctx, c.taskBatchHTTP, http.MethodPost, taskImportBatchPath(project)+"/"+url.PathEscape(batch)+"/"+operation, "", body, key, http.StatusOK, taskBatchTransitionResponseLimit)
	if err != nil {
		return result, taskBatchWriteFailure(err)
	}
	value, err := c.decodeBatchTransition(raw, project, batch, operation)
	if err != nil {
		return result, taskBatchWriteFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[TaskBatchTransition]{Raw: raw, Value: value}, nil
}

var batchStatusPattern = regexp.MustCompile(`^[a-z][a-z0-9_]{0,29}$`)

func taskBatchWriteFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "batch outcome unknown; inspect status as observation, then manually replay only the unchanged project, source/batch, action, reason and idempotency key; later Task or authority changes may prevent replay"
	}
	return err
}

func (c *Client) decodeBatchTransition(raw json.RawMessage, project, batch, operation string) (TaskBatchTransition, error) {
	var value TaskBatchTransition
	fields, err := contextObject(raw, &value, []string{"project_id", "batch_id", "operation", "row_count", "tasks"}, nil)
	if err != nil || !sameUUID(value.ProjectID, project) || !sameUUID(value.BatchID, batch) || value.Operation != operation || value.RowCount < 1 || value.RowCount > taskimport.MaxRows || len(value.Tasks) != value.RowCount {
		return value, &Failure{Code: "invalid_api_response"}
	}
	var rows []json.RawMessage
	if jsonv2.Unmarshal(fields["tasks"], &rows) != nil {
		return value, &Failure{Code: "invalid_api_response"}
	}
	seen := make(map[[16]byte]bool)
	status := "screening"
	if operation == "release" {
		status = "ready"
	}
	for index, task := range value.Tasks {
		var exact TaskBatchTransitionTask
		_, err := contextObject(rows[index], &exact, []string{"task_id", "row_index", "status", "locked_guide_version", "locked_contribution_policy_version_id", "locked_context_hash"}, nil)
		id, valid := uuidIdentity(task.TaskID)
		if err != nil || !valid || seen[id] || task.RowIndex != index || task.Status != status ||
			!validUUID(task.LockedContributionPolicyVersionID) || !policyHash.MatchString(task.LockedContextHash) ||
			!utf8.ValidString(task.LockedGuideVersion) || utf8.RuneCountInString(task.LockedGuideVersion) < 1 || utf8.RuneCountInString(task.LockedGuideVersion) > 100 ||
			!c.safeMetadata(task.TaskID) || !c.safeMetadata(task.LockedGuideVersion) || !c.safeMetadata(task.LockedContributionPolicyVersionID) || !c.safeMetadata(task.LockedContextHash) {
			return value, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
	}
	return value, nil
}

func (c *Client) decodeTaskImportBatch(raw json.RawMessage, project, batch string) (TaskImportBatch, error) {
	var envelope taskImportEnvelope
	_, err := contextObject(raw, &envelope, []string{"batch_id", "project_id", "source_id", "sha256", "byte_count", "schema_version", "mapping_version", "row_count", "created_at", "tasks"}, nil)
	if err != nil || !validUUID(envelope.BatchID) || !sameUUID(envelope.ProjectID, project) || !validUUID(envelope.SourceID) ||
		(batch != "" && !sameUUID(envelope.BatchID, batch)) ||
		!policyHash.MatchString(envelope.SHA256) || envelope.ByteCount < 1 || envelope.ByteCount > taskimport.MaxBytes ||
		envelope.RowCount < 1 || envelope.RowCount > taskimport.MaxRows || len(envelope.Tasks) != envelope.RowCount ||
		envelope.SchemaVersion != "workstream.task_import.v1" || envelope.MappingVersion != "workstream.task_import.draft_mapping.v1" || !validTime(envelope.CreatedAt) {
		return TaskImportBatch{}, &Failure{Code: "invalid_api_response"}
	}
	if envelope.Label != nil && (!utf8.ValidString(*envelope.Label) || utf8.RuneCountInString(*envelope.Label) < 1 || utf8.RuneCountInString(*envelope.Label) > 255 || strings.ContainsRune(*envelope.Label, 0) || !c.safeMetadata(*envelope.Label)) {
		return TaskImportBatch{}, &Failure{Code: "invalid_api_response"}
	}
	value := TaskImportBatch{BatchID: envelope.BatchID, ProjectID: envelope.ProjectID, SourceID: envelope.SourceID, SHA256: envelope.SHA256, ByteCount: envelope.ByteCount, SchemaVersion: envelope.SchemaVersion, MappingVersion: envelope.MappingVersion, Label: envelope.Label, RowCount: envelope.RowCount, CreatedAt: envelope.CreatedAt, Tasks: make([]ImportedTask, 0, envelope.RowCount)}
	seen, external := make(map[[16]byte]bool), make(map[string]bool)
	for _, row := range envelope.Tasks {
		task, err := c.decodeImportedTask(row, value)
		id, valid := uuidIdentity(task.ID)
		if err != nil || !valid || seen[id] || external[task.ExternalTaskID] ||
			(len(value.Tasks) > 0 && (task.TaskSize == nil) != (value.Tasks[0].TaskSize == nil)) {
			return value, &Failure{Code: "invalid_api_response"}
		}
		seen[id], external[task.ExternalTaskID] = true, true
		value.Tasks = append(value.Tasks, task)
	}
	return value, nil
}

var originalTaskFields = []string{
	"id", "project_id", "locked_contribution_policy_version_id", "locked_guide_version", "locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash", "locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash", "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash", "locked_effective_project_submission_artifact_policy_id", "locked_effective_project_submission_artifact_policy_hash", "locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash", "source_type", "source_ref", "source_payload_hash", "import_batch_id", "external_task_id", "title", "description", "task_type", "difficulty", "skill_tags", "estimated_time_minutes", "status", "acceptance_criteria", "rejection_criteria", "deadline_at", "created_by", "assigned_to", "created_at", "updated_at",
}

func (c *Client) decodeImportedTask(raw json.RawMessage, batch TaskImportBatch) (ImportedTask, error) {
	var task ImportedTask
	var fields map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &fields); err != nil {
		return task, &Failure{Code: "invalid_api_response"}
	}
	expected := len(originalTaskFields)
	if _, present := fields["task_size"]; present {
		expected++
	}
	if len(fields) != expected {
		return task, &Failure{Code: "invalid_api_response"}
	}
	for _, field := range originalTaskFields {
		value, present := fields[field]
		if !present || ((strings.HasPrefix(field, "locked_") || field == "assigned_to" || field == "deadline_at") && string(value) != "null") {
			return task, &Failure{Code: "invalid_api_response"}
		}
	}
	// The complete public TaskResponse field set was checked above. Decode only
	// identities used by CLI output; validate instructions through the canonical
	// local import parser without retaining a second private Task DTO.
	if jsonv2.Unmarshal(raw, &task) != nil || !validTaskSizeField(fields, task.TaskSize) || !sameUUID(task.ProjectID, batch.ProjectID) || task.Status != "draft" ||
		task.SourceType != "json_import" || task.SourceRef != "task-import-source:"+batch.SourceID || task.SourcePayloadHash != batch.SHA256 ||
		!sameUUID(task.ImportBatchID, batch.BatchID) || !validUUID(task.CreatedBy) || !validTime(task.CreatedAt) || !validTime(task.UpdatedAt) {
		return task, &Failure{Code: "invalid_api_response"}
	}
	instructions := make(map[string]json.RawMessage)
	for _, field := range []string{"external_task_id", "title", "description", "task_type", "difficulty", "skill_tags", "estimated_time_minutes", "acceptance_criteria", "rejection_criteria"} {
		instructions[field] = fields[field]
		if field == "skill_tags" {
			var tags []string
			if jsonv2.Unmarshal(fields[field], &tags) != nil {
				return task, &Failure{Code: "invalid_api_response"}
			}
			for _, tag := range tags {
				if !c.safeMetadata(tag) {
					return task, &Failure{Code: "invalid_api_response"}
				}
			}
		} else if field != "estimated_time_minutes" && string(fields[field]) != "null" {
			var text string
			if jsonv2.Unmarshal(fields[field], &text) != nil || !c.safeMetadata(text) {
				return task, &Failure{Code: "invalid_api_response"}
			}
		}
	}
	if size, present := fields["task_size"]; present {
		instructions["task_size"] = size
	}
	validation, err := json.Marshal(map[string]any{"schema_version": "workstream.task_import.v1", "tasks": []any{instructions}})
	if err == nil {
		_, err = taskimport.ValidateJSON(validation)
	}
	if err != nil {
		return task, &Failure{Code: "invalid_api_response"}
	}
	for _, metadata := range []string{task.ID, task.ProjectID, task.SourceRef, task.SourcePayloadHash, task.ImportBatchID, task.CreatedBy, task.CreatedAt, task.UpdatedAt} {
		if !c.safeMetadata(metadata) {
			return task, &Failure{Code: "invalid_api_response"}
		}
	}
	return task, nil
}
