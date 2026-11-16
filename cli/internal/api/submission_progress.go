package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
)

// SubmissionProgress preserves the operation's outcome separately from current task context.
type SubmissionProgress struct {
	OperationID            string            `json:"operation_id"`
	TaskID                 string            `json:"task_id"`
	AssignmentID           string            `json:"assignment_id"`
	IdempotencyKey         string            `json:"idempotency_key"`
	State                  string            `json:"operation_state"`
	Stage                  string            `json:"processing_stage"`
	AcceptedAt             *string           `json:"accepted_at"`
	TaskStatusAtAcceptance *string           `json:"task_status_at_acceptance"`
	CurrentTaskStatus      *string           `json:"current_task_status"`
	SubmissionID           *string           `json:"submission_id"`
	SubmissionVersion      *big.Int          `json:"submission_version"`
	EvaluationRequestID    *string           `json:"evaluation_request_id"`
	Feedback               []json.RawMessage `json:"pre_submission_results"`
	FailureCode            *string           `json:"failure_code"`
	Stalled                bool              `json:"operationally_stalled"`
	NextAction             string            `json:"next_action"`
}

func decodeSubmissionProgress(raw json.RawMessage, task, operation, key string) (SubmissionProgress, error) {
	var value SubmissionProgress
	bad := &Failure{Code: "invalid_api_response"}
	fields, err := contextObject(raw, &value, []string{"operation_id", "task_id", "assignment_id", "idempotency_key", "operation_state", "processing_stage", "pre_submission_results", "operationally_stalled", "next_action"}, nil)
	if err != nil || !requiredNullable(fields, "accepted_at", "task_status_at_acceptance", "current_task_status", "submission_id", "submission_version", "evaluation_request_id", "failure_code") ||
		!validUUID(value.OperationID) || !sameUUID(value.TaskID, task) || !validUUID(value.AssignmentID) || !validUUID(value.IdempotencyKey) ||
		(operation != "" && !sameUUID(value.OperationID, operation)) || (key != "" && !sameUUID(value.IdempotencyKey, key)) ||
		!oneOf(value.State, "receiving", "pre_checking", "finalization_pending", "finalized", "rejected", "failed", "abandoned", "cancelled") ||
		!oneOf(value.Stage, "receiving", "pre_checking", "finalization_pending", "evaluation_pending", "evaluation_running", "review_pending", "needs_revision", "accepted", "rejected", "failed", "abandoned", "cancelled", "operationally_stalled") ||
		!oneOf(value.NextAction, "wait", "correct_and_submit_new_key", "retry_new_key_after_terminal", "inspect_governed_outcome") ||
		(value.AcceptedAt != nil && !validTime(*value.AcceptedAt)) ||
		(value.TaskStatusAtAcceptance != nil && *value.TaskStatusAtAcceptance != "evaluation_pending") ||
		(value.CurrentTaskStatus != nil && !oneOf(*value.CurrentTaskStatus, "draft", "screening", "ready", "in_progress", "submitted", "evaluation_pending", "review_pending", "needs_revision", "accepted")) ||
		(value.SubmissionID != nil && !validUUID(*value.SubmissionID)) ||
		(value.EvaluationRequestID != nil && !validUUID(*value.EvaluationRequestID)) ||
		(value.SubmissionVersion != nil && value.SubmissionVersion.Sign() <= 0) ||
		value.Feedback == nil || !validPreSubmissionResults(value.Feedback, value.AcceptedAt != nil) {
		return value, bad
	}
	return value, nil
}

// SubmissionOperation makes one bounded read; it never retries the submission mutation.
func (c *Client) SubmissionOperation(ctx context.Context, task, operation, key string) (Result[SubmissionProgress], error) {
	var result Result[SubmissionProgress]
	if !submissionSelector(task) || (operation == "") == (key == "") ||
		(operation != "" && !submissionSelector(operation)) || (key != "" && !submissionSelector(key)) {
		return result, errors.New("task and exactly one operation ID or idempotency key must be UUIDs")
	}
	query := url.Values{}
	if operation != "" {
		query.Set("operation_id", operation)
	} else {
		query.Set("idempotency_key", key)
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, "/api/v1/tasks/"+url.PathEscape(task)+"/submission-operations", query.Encode(), nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	value, err := decodeSubmissionProgress(raw, task, operation, key)
	if err != nil || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[SubmissionProgress]{Raw: raw, Value: value}, nil
}
