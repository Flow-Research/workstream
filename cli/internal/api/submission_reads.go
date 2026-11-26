package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"unicode/utf8"
)

const maxSubmissionReadBytes = 2 * 1024 * 1024

// History has a different public cursor bound from ready/manager task lists.
// Preserve that distinction without changing existing task-list semantics.
func validSubmissionCursor(cursor string) bool {
	return cursor != "" && utf8.ValidString(cursor) && utf8.RuneCountInString(cursor) <= 1024
}

func submissionPageQuery(limit int, cursor *string) (string, error) {
	query, err := taskPageQuery(limit, nil)
	if err != nil || cursor == nil {
		return query, err
	}
	if !validSubmissionCursor(*cursor) {
		return "", errors.New("history cursor must contain 1–1024 valid UTF-8 characters")
	}
	return query + "&cursor=" + url.QueryEscape(*cursor), nil
}

type SubmissionEvidence struct {
	ID    string   `json:"id"`
	Type  string   `json:"type"`
	Label string   `json:"label"`
	Size  *big.Int `json:"size_bytes"`
}
type SubmissionFindingCounts struct {
	Blocking           *big.Int `json:"blocking"`
	Warning            *big.Int `json:"warning"`
	CoverageIncomplete *big.Int `json:"coverage_incomplete"`
}
type SubmissionHistory struct {
	ID            string                  `json:"id"`
	Task          string                  `json:"task_id"`
	Version       *big.Int                `json:"version"`
	Status        string                  `json:"status"`
	StatusReason  *string                 `json:"status_reason"`
	Summary       *string                 `json:"summary"`
	Feedback      *string                 `json:"feedback"`
	SubmittedAt   string                  `json:"submitted_at"`
	DecidedAt     *string                 `json:"decided_at"`
	FindingCounts SubmissionFindingCounts `json:"finding_counts"`
	LockedAt      *string                 `json:"locked_at"`
	Predecessor   *string                 `json:"supersedes_submission_id"`
	Evidence      []SubmissionEvidence    `json:"evidence_items"`
}
type SubmissionPage struct {
	Items  []SubmissionHistory `json:"items"`
	Cursor *string             `json:"next_cursor"`
}
type ContributorFinding struct {
	ID       string  `json:"id"`
	Checker  string  `json:"checker_name"`
	CheckID  *string `json:"check_id"`
	Path     *string `json:"path"`
	Line     *int64  `json:"line"`
	Status   string  `json:"status"`
	Severity string  `json:"severity"`
	Message  *string `json:"worker_message"`
	Fix      *string `json:"worker_suggested_fix"`
}
type SubmissionCheckerRun struct {
	ID          string               `json:"id"`
	Task        string               `json:"task_id"`
	Submission  string               `json:"submission_id"`
	Version     *big.Int             `json:"submission_version"`
	Status      string               `json:"status"`
	Attempt     *big.Int             `json:"attempt_number"`
	Predecessor *string              `json:"supersedes_checker_run_id"`
	Current     bool                 `json:"is_current_for_submission"`
	CreatedAt   string               `json:"created_at"`
	CompletedAt *string              `json:"completed_at"`
	Results     []ContributorFinding `json:"results"`
}
type SubmissionCheckerPage struct {
	Items  []SubmissionCheckerRun `json:"items"`
	Cursor *string                `json:"next_cursor"`
}

// SubmissionFindingsResult is one typed response shape. Exactly one member is
// populated according to whether the caller selected a page or an exact run.
type SubmissionFindingsResult struct {
	Page *SubmissionCheckerPage
	Run  *SubmissionCheckerRun
}

func decodeSubmission(raw json.RawMessage, task, submission string) (SubmissionHistory, error) {
	var value SubmissionHistory
	bad := &Failure{Code: "invalid_api_response"}
	fields, err := contextObject(raw, &value, []string{"id", "task_id", "version", "status", "submitted_at", "finding_counts", "evidence_items"}, nil)
	if err != nil || !requiredNullable(fields, "status_reason", "decided_at", "locked_at", "supersedes_submission_id", "summary", "feedback") ||
		!validUUID(value.ID) || !validUUID(value.Task) || (task != "" && !sameUUID(value.Task, task)) ||
		(submission != "" && !sameUUID(value.ID, submission)) || value.Version == nil || value.Version.Sign() <= 0 ||
		!validSubmissionOutcome(value) || !validFindingCounts(fields["finding_counts"], &value.FindingCounts) ||
		!validTime(value.SubmittedAt) || (value.LockedAt != nil && !validTime(*value.LockedAt)) ||
		(value.Predecessor != nil && (!validUUID(*value.Predecessor) || sameUUID(*value.Predecessor, value.ID))) || value.Evidence == nil {
		return value, bad
	}
	var evidence []json.RawMessage
	if json.Unmarshal(fields["evidence_items"], &evidence) != nil {
		return value, bad
	}
	seen := map[[16]byte]bool{}
	for index, item := range evidence {
		e := &value.Evidence[index]
		f, err := contextObject(item, e, []string{"id", "type", "label"}, nil)
		id, ok := uuidIdentity(e.ID)
		if err != nil || !requiredNullable(f, "size_bytes") || !ok || seen[id] || (e.Size != nil && e.Size.Sign() < 0) {
			return value, bad
		}
		seen[id] = true
	}
	return value, nil
}

// validSubmissionOutcome mirrors the server's attempt-status rules: only a
// decided attempt has decided_at, and only a deadline rejection or a checker
// coverage return carries a reason.
func validSubmissionOutcome(value SubmissionHistory) bool {
	decided := false
	switch value.Status {
	case "evaluation_pending", "review_pending":
	case "accepted", "needs_revision", "rejected":
		decided = true
	default:
		return false
	}
	if decided != (value.DecidedAt != nil) || (value.DecidedAt != nil && !validTime(*value.DecidedAt)) {
		return false
	}
	if value.StatusReason == nil {
		return true
	}
	return (value.Status == "rejected" &&
		(*value.StatusReason == "revision_deadline_expired" || *value.StatusReason == "revision_limit_reached")) ||
		(value.Status == "needs_revision" && *value.StatusReason == "checker_coverage_incomplete")
}

func validFindingCounts(raw json.RawMessage, counts *SubmissionFindingCounts) bool {
	if _, err := contextObject(raw, counts, []string{"blocking", "warning", "coverage_incomplete"}, nil); err != nil {
		return false
	}
	for _, count := range []*big.Int{counts.Blocking, counts.Warning, counts.CoverageIncomplete} {
		if count == nil || count.Sign() < 0 {
			return false
		}
	}
	return true
}

func (c *Client) Submission(ctx context.Context, id string) (Result[SubmissionHistory], error) {
	var result Result[SubmissionHistory]
	if !submissionSelector(id) {
		return result, errors.New("submission must be a UUID")
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, "/api/v1/submissions/"+url.PathEscape(id), "", nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	value, err := decodeSubmission(raw, "", id)
	if err != nil || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[SubmissionHistory]{Raw: raw, Value: value}, nil
}

func (c *Client) TaskSubmissions(ctx context.Context, task string, limit int, cursor *string) (Result[SubmissionPage], error) {
	var result Result[SubmissionPage]
	if !submissionSelector(task) {
		return result, errors.New("task must be a UUID")
	}
	query, err := submissionPageQuery(limit, cursor)
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, "/api/v1/tasks/"+url.PathEscape(task)+"/submissions", query, nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	var page SubmissionPage
	fields, err := contextObject(raw, &page, []string{"items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || page.Items == nil || len(page.Items) > limit ||
		(page.Cursor != nil && (!validSubmissionCursor(*page.Cursor) || len(page.Items) == 0)) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	var items []json.RawMessage
	if json.Unmarshal(fields["items"], &items) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for i, item := range items {
		value, err := decodeSubmission(item, task, "")
		id, _ := uuidIdentity(value.ID)
		if err != nil || seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items[i] = value
	}
	return Result[SubmissionPage]{Raw: raw, Value: page}, nil
}

func decodeSubmissionChecker(raw json.RawMessage, submission, run string) (SubmissionCheckerRun, error) {
	var value SubmissionCheckerRun
	bad := &Failure{Code: "invalid_api_response"}
	fields, err := contextObject(raw, &value, []string{"id", "task_id", "submission_id", "submission_version", "status", "attempt_number", "is_current_for_submission", "created_at", "results"}, nil)
	if err != nil || !requiredNullable(fields, "supersedes_checker_run_id", "completed_at") || !validUUID(value.ID) || !validUUID(value.Task) ||
		!sameUUID(value.Submission, submission) || (run != "" && !sameUUID(value.ID, run)) || value.Version == nil || value.Version.Sign() <= 0 ||
		value.Attempt == nil || value.Attempt.Sign() <= 0 || !validTime(value.CreatedAt) || (value.CompletedAt != nil && !validTime(*value.CompletedAt)) ||
		(value.Predecessor != nil && (!validUUID(*value.Predecessor) || sameUUID(*value.Predecessor, value.ID))) || value.Results == nil {
		return value, bad
	}
	switch value.Status {
	case "queued", "running", "completed", "infrastructure_failed":
	default:
		return value, bad
	}
	if !validateContributorFindings(fields["results"], value.Results) {
		return value, bad
	}
	return value, nil
}

func validateContributorFindings(raw json.RawMessage, findings []ContributorFinding) bool {
	var items []json.RawMessage
	if json.Unmarshal(raw, &items) != nil || items == nil || len(items) != len(findings) {
		return false
	}
	seen := map[[16]byte]bool{}
	for i, item := range items {
		f := &findings[i]
		fields, err := contextObject(item, f, []string{"id", "checker_name", "status", "severity"}, nil)
		id, ok := uuidIdentity(f.ID)
		if err != nil || !requiredNullable(fields, "check_id", "path", "line", "worker_message", "worker_suggested_fix") ||
			!ok || seen[id] || f.Checker == "" || (f.CheckID != nil && *f.CheckID == "") ||
			(f.Path != nil && *f.Path == "") || (f.Line != nil && (f.Path == nil || *f.Line < 1)) {
			return false
		}
		switch f.Status {
		case "passed", "warning", "failed", "coverage_incomplete":
		default:
			return false
		}
		switch f.Severity {
		case "info", "low", "medium", "high", "critical", "error":
		default:
			return false
		}
		seen[id] = true
	}
	return true
}

func (c *Client) SubmissionFindings(ctx context.Context, submission, run string, limit int, cursor *string) (Result[SubmissionFindingsResult], error) {
	var result Result[SubmissionFindingsResult]
	if !submissionSelector(submission) || (run != "" && !submissionSelector(run)) {
		return result, errors.New("submission and run must be UUIDs")
	}
	path := "/api/v1/submissions/" + url.PathEscape(submission) + "/checker-runs"
	query := ""
	if run != "" {
		path += "/" + url.PathEscape(run)
	} else {
		var err error
		query, err = submissionPageQuery(limit, cursor)
		if err != nil {
			return result, err
		}
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, query, nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	bad := &Failure{Code: "invalid_api_response"}
	if !c.safeMutationResponse(raw) {
		return result, bad
	}
	value, err := decodeSubmissionFindings(raw, submission, run, limit)
	if err != nil {
		return result, err
	}
	return Result[SubmissionFindingsResult]{Raw: raw, Value: value}, nil
}

func decodeSubmissionFindings(raw json.RawMessage, submission, run string, limit int) (SubmissionFindingsResult, error) {
	var result SubmissionFindingsResult
	bad := &Failure{Code: "invalid_api_response"}
	if run != "" {
		value, err := decodeSubmissionChecker(raw, submission, run)
		if err != nil {
			return result, err
		}
		result.Run = &value
		return result, nil
	}
	var page SubmissionCheckerPage
	fields, err := contextObject(raw, &page, []string{"items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || page.Items == nil || len(page.Items) > limit ||
		(page.Cursor != nil && (!validSubmissionCursor(*page.Cursor) || len(page.Items) == 0)) {
		return result, bad
	}
	var items []json.RawMessage
	if json.Unmarshal(fields["items"], &items) != nil {
		return result, bad
	}
	seen := map[[16]byte]bool{}
	var task string
	for index, item := range items {
		value, err := decodeSubmissionChecker(item, submission, "")
		id, _ := uuidIdentity(value.ID)
		if err != nil || seen[id] || (task != "" && !sameUUID(task, value.Task)) {
			return result, bad
		}
		seen[id] = true
		task = value.Task
		page.Items[index] = value
	}
	result.Page = &page
	return result, nil
}
