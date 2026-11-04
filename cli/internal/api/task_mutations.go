package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"regexp"
	"unicode/utf8"
)

// MutationTask is the contributor-safe TaskResponse returned by claim,
// not the management detail or contributor read projection.
type MutationTask struct {
	ID                                string   `json:"id"`
	ProjectID                         string   `json:"project_id"`
	LockedContributionPolicyVersionID string   `json:"locked_contribution_policy_version_id"`
	LockedGuideVersion                string   `json:"locked_guide_version"`
	LockedReviewPolicyID              string   `json:"locked_review_policy_id"`
	LockedReviewPolicyGeneration      int      `json:"locked_review_policy_generation"`
	LockedReviewPolicyHash            string   `json:"locked_review_policy_hash"`
	LockedRevisionPolicyID            string   `json:"locked_revision_policy_id"`
	LockedRevisionPolicyGeneration    int      `json:"locked_revision_policy_generation"`
	LockedRevisionPolicyHash          string   `json:"locked_revision_policy_hash"`
	SourceType                        string   `json:"source_type"`
	Title                             string   `json:"title"`
	Description                       string   `json:"description"`
	TaskType                          *string  `json:"task_type"`
	Difficulty                        *string  `json:"difficulty"`
	SkillTags                         []string `json:"skill_tags"`
	EstimatedTimeMinutes              *int     `json:"estimated_time_minutes"`
	Status                            string   `json:"status"`
	AcceptanceCriteria                *string  `json:"acceptance_criteria"`
	RejectionCriteria                 *string  `json:"rejection_criteria"`
	DeadlineAt                        *string  `json:"deadline_at"`
	CreatedAt                         string   `json:"created_at"`
	UpdatedAt                         string   `json:"updated_at"`
}

type TaskAssignment struct {
	ID                                   string  `json:"id"`
	TaskID                               string  `json:"task_id"`
	ProjectID                            string  `json:"project_id"`
	SubmitterContributionPolicyVersionID string  `json:"submitter_contribution_policy_version_id"`
	ContributorID                        string  `json:"contributor_id"`
	AssignedBy                           string  `json:"assigned_by"`
	AssignedAt                           string  `json:"assigned_at"`
	AcceptedAt                           string  `json:"accepted_at"`
	ReleasedAt                           *string `json:"released_at"`
	Status                               string  `json:"status"`
}

type ClaimedTask struct {
	Task       MutationTask
	Assignment TaskAssignment
}

var policyHash = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

func (c *Client) taskWrite(ctx context.Context, selector, action, key string, reason *string, responseLimit int) (json.RawMessage, error) {
	raw, err := c.taskWriteRoute(ctx, "/api/v1/tasks/", selector, action, key, reason, responseLimit)
	return raw, taskWriteFailure(err)
}

func (c *Client) taskWriteRoute(ctx context.Context, route, selector, action, key string, reason *string, responseLimit int) (json.RawMessage, error) {
	if _, ok := uuidIdentity(selector); !ok || len(selector) > 100 {
		return nil, errors.New("TASK_ID must be a UUID")
	}
	if _, ok := uuidIdentity(key); !ok || len(key) > 100 {
		return nil, errors.New("--idempotency-key must be a UUID")
	}
	fields := map[string]string{}
	if reason != nil {
		if !utf8.ValidString(*reason) || utf8.RuneCountInString(*reason) > 1000 {
			return nil, errors.New("reason must contain at most 1000 valid UTF-8 characters")
		}
		fields["reason"] = *reason
	}
	body, err := json.Marshal(fields)
	if err != nil || len(body) > maxUpdateBytes {
		return nil, errors.New("task request exceeds the request size limit")
	}
	return c.requestWithResponseLimit(ctx, http.MethodPost, route+url.PathEscape(selector)+"/"+action, "", body, key, http.StatusOK, responseLimit)
}

func taskWriteFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "task outcome unknown; inspect task show (observation, not rollback proof); replay only the unchanged action, task, reason and idempotency key"
	}
	return err
}

func (c *Client) ClaimTask(ctx context.Context, selector, key string, reason *string) (Result[ClaimedTask], error) {
	var result Result[ClaimedTask]
	raw, err := c.taskWrite(ctx, selector, "claim", key, reason, maxResponseBytes)
	if err != nil {
		return result, err
	}
	var envelope struct {
		Task       json.RawMessage `json:"task"`
		Assignment json.RawMessage `json:"assignment"`
	}
	var value ClaimedTask
	err = decode(raw, &envelope, []string{"task", "assignment"}, nil)
	if err == nil {
		value.Task, err = decodeMutationTask(envelope.Task, selector, "in_progress")
	}
	if err == nil {
		err = decodeTaskFields(envelope.Assignment, &value.Assignment,
			[]string{"id", "task_id", "project_id", "submitter_contribution_policy_version_id", "contributor_id", "assigned_by", "assigned_at", "accepted_at", "status"}, nil)
	}
	a := value.Assignment
	if err != nil || !sameUUID(a.TaskID, value.Task.ID) || !sameUUID(a.ProjectID, value.Task.ProjectID) ||
		!sameUUID(a.SubmitterContributionPolicyVersionID, value.Task.LockedContributionPolicyVersionID) ||
		!sameUUID(a.ContributorID, a.AssignedBy) || !validUUID(a.ID) || a.Status != "active" ||
		!validTime(a.AssignedAt) || !validTime(a.AcceptedAt) || a.ReleasedAt != nil {
		return result, taskWriteFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[ClaimedTask]{Raw: raw, Value: value}, nil
}

func decodeMutationTask(raw json.RawMessage, selector, status string) (MutationTask, error) {
	var task MutationTask
	err := decodeTaskFields(raw, &task, []string{
		"id", "project_id", "locked_contribution_policy_version_id", "locked_guide_version",
		"locked_review_policy_id", "locked_review_policy_hash", "locked_revision_policy_id",
		"locked_revision_policy_hash", "source_type", "title", "description", "status", "created_at", "updated_at",
	}, []string{"skill_tags", "locked_review_policy_generation", "locked_revision_policy_generation"})
	if err != nil || !sameUUID(task.ID, selector) || !validUUID(task.ProjectID) ||
		!validUUID(task.LockedContributionPolicyVersionID) || !validUUID(task.LockedReviewPolicyID) ||
		!validUUID(task.LockedRevisionPolicyID) || task.LockedGuideVersion == "" ||
		task.LockedReviewPolicyGeneration < 1 || task.LockedRevisionPolicyGeneration < 1 ||
		!policyHash.MatchString(task.LockedReviewPolicyHash) || !policyHash.MatchString(task.LockedRevisionPolicyHash) ||
		task.Status != status || !validTime(task.CreatedAt) || !validTime(task.UpdatedAt) ||
		(task.DeadlineAt != nil && !validTime(*task.DeadlineAt)) {
		return task, &Failure{Code: "invalid_api_response"}
	}
	return task, nil
}

func validUUID(value string) bool {
	_, valid := uuidIdentity(value)
	return valid
}

func sameUUID(left, right string) bool {
	a, validA := uuidIdentity(left)
	b, validB := uuidIdentity(right)
	return validA && validB && a == b
}
