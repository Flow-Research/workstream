package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

// PageQuery selects one page of a signed list: the caller's own work or a
// project-wide management list. The server binds every continuation to the
// same filters and limit; each list accepts only its own filters.
type PageQuery struct {
	Limit        int
	Cursor       *string
	ProjectID    *string
	TaskID       *string
	State        *string
	Status       *string
	UpdatedSince *string
	Outcome      *string
}

type ActiveGuide struct {
	GuideID string `json:"guide_id"`
	Version string `json:"version"`
}

type ActorProject struct {
	ProjectID    string       `json:"project_id"`
	Name         string       `json:"name"`
	Status       string       `json:"status"`
	AdminRoles   []string     `json:"admin_roles"`
	ProjectRoles []string     `json:"project_roles"`
	ActiveGuide  *ActiveGuide `json:"active_guide"`
}

type ActorProjectPage struct {
	Items  []ActorProject `json:"items"`
	Cursor *string        `json:"next_cursor"`
}

type LatestSubmission struct {
	SubmissionID string   `json:"submission_id"`
	Version      *big.Int `json:"version"`
	Status       string   `json:"status"`
	StatusReason *string  `json:"status_reason"`
	SubmittedAt  string   `json:"submitted_at"`
	DecidedAt    *string  `json:"decided_at"`
}

type ContributorAssignment struct {
	AssignmentID       string            `json:"assignment_id"`
	ProjectID          string            `json:"project_id"`
	TaskID             string            `json:"task_id"`
	Title              string            `json:"title"`
	State              string            `json:"state"`
	AssignmentStatus   string            `json:"assignment_status"`
	TaskStatus         *string           `json:"task_status"`
	ClaimedAt          string            `json:"claimed_at"`
	StartedAt          *string           `json:"started_at"`
	ReleasedAt         *string           `json:"released_at"`
	LockedGuideVersion *string           `json:"locked_guide_version"`
	Compensation       CompensationTerms `json:"compensation"`
	LatestSubmission   *LatestSubmission `json:"latest_submission"`
	Revision           *RevisionContext  `json:"revision"`
	NextAction         string            `json:"next_action"`
	UpdatedAt          string            `json:"updated_at"`
}

type ContributorAssignmentPage struct {
	Items  []ContributorAssignment `json:"items"`
	Cursor *string                 `json:"next_cursor"`
}

type ContributorSubmission struct {
	SubmissionID  string                  `json:"submission_id"`
	ProjectID     string                  `json:"project_id"`
	TaskID        string                  `json:"task_id"`
	Title         string                  `json:"title"`
	Version       *big.Int                `json:"version"`
	Status        string                  `json:"status"`
	StatusReason  *string                 `json:"status_reason"`
	SubmittedAt   string                  `json:"submitted_at"`
	DecidedAt     *string                 `json:"decided_at"`
	FindingCounts SubmissionFindingCounts `json:"finding_counts"`
	UpdatedAt     string                  `json:"updated_at"`
}

type ContributorSubmissionPage struct {
	Items  []ContributorSubmission `json:"items"`
	Cursor *string                 `json:"next_cursor"`
}

type AssignmentCounts struct {
	Active *big.Int `json:"active"`
	Closed *big.Int `json:"closed"`
}

type AttemptCounts struct {
	EvaluationPending *big.Int `json:"evaluation_pending"`
	ReviewPending     *big.Int `json:"review_pending"`
	Accepted          *big.Int `json:"accepted"`
	NeedsRevision     *big.Int `json:"needs_revision"`
	Rejected          *big.Int `json:"rejected"`
}

type ContributorWorkSummary struct {
	ProjectID   *string             `json:"project_id"`
	Assignments AssignmentCounts    `json:"assignments"`
	Submissions AttemptCounts       `json:"submissions"`
	AwardTotals []CompensationAward `json:"award_totals"`
}

type PreparationSummary struct {
	PreparationID             string                   `json:"preparation_id"`
	TaskID                    string                   `json:"task_id"`
	AssignmentID              string                   `json:"assignment_id"`
	Outcome                   string                   `json:"outcome"`
	State                     string                   `json:"state"`
	StorageStatus             *string                  `json:"storage_status"`
	InfrastructureFailureCode *string                  `json:"infrastructure_failure_code"`
	ArchiveSHA256             string                   `json:"archive_sha256"`
	ArchiveByteCount          *big.Int                 `json:"archive_byte_count"`
	FindingCounts             *SubmissionFindingCounts `json:"finding_counts"`
	AdmissionID               *string                  `json:"admission_id"`
	SubmissionID              *string                  `json:"submission_id"`
	CreatedAt                 string                   `json:"created_at"`
	CompletedAt               *string                  `json:"completed_at"`
}

type PreparationDetail struct {
	PreparationSummary
	Findings []json.RawMessage `json:"findings"`
}

type PreparationPage struct {
	Items  []PreparationSummary `json:"items"`
	Cursor *string              `json:"next_cursor"`
}

func optionalUUID(value *string) bool { return value == nil || submissionSelector(*value) }

func oneOf(value string, allowed ...string) bool {
	for _, item := range allowed {
		if value == item {
			return true
		}
	}
	return false
}

var attemptStatuses = []string{"evaluation_pending", "review_pending", "accepted", "needs_revision", "rejected"}

func (q PageQuery) encode() (string, error) { return q.encodeWith(attemptStatuses) }

// encodeWith validates and encodes every set filter; status is checked
// against the list's own stored statuses. Only preparation lists accept an
// outcome, through encodePreparations.
func (q PageQuery) encodeWith(statuses []string) (string, error) {
	if q.Outcome != nil {
		return "", errors.New("only preparation lists accept --outcome")
	}
	if q.Limit < 1 || q.Limit > 100 || (q.Cursor != nil && !validTaskCursor(*q.Cursor)) ||
		!optionalUUID(q.ProjectID) || !optionalUUID(q.TaskID) ||
		(q.State != nil && !oneOf(*q.State, "active", "closed")) ||
		(q.Status != nil && !oneOf(*q.Status, statuses...)) ||
		(q.UpdatedSince != nil && !validTime(*q.UpdatedSince)) {
		return "", errors.New("limit must be 1–100; cursor 1–512 characters; IDs UUIDs; times RFC 3339; state active or closed")
	}
	query := url.Values{"limit": {strconv.Itoa(q.Limit)}}
	for name, value := range map[string]*string{
		"cursor": q.Cursor, "project_id": q.ProjectID, "task_id": q.TaskID,
		"state": q.State, "status": q.Status, "updated_since": q.UpdatedSince,
	} {
		if value != nil {
			query.Set(name, *value)
		}
	}
	return query.Encode(), nil
}

// encodePreparations encodes a preparation list page and its optional outcome.
func (q PageQuery) encodePreparations() (string, error) {
	outcome := q.Outcome
	if outcome != nil && !oneOf(*outcome, preparationOutcomes...) {
		return "", errors.New("--outcome must be " + strings.Join(preparationOutcomes, ", "))
	}
	q.Outcome = nil
	query, err := q.encode()
	if err != nil || outcome == nil {
		return query, err
	}
	values, _ := url.ParseQuery(query)
	values.Set("outcome", *outcome)
	return values.Encode(), nil
}

func (c *Client) contributorPage(ctx context.Context, path string, q PageQuery) (json.RawMessage, map[string]json.RawMessage, []json.RawMessage, error) {
	query, err := q.encode()
	if err != nil {
		return nil, nil, nil, err
	}
	return c.readPage(ctx, path, query, q.Limit)
}

// readPage fetches one closed {items, next_cursor} page of at most limit items.
func (c *Client) readPage(ctx context.Context, path, query string, limit int) (json.RawMessage, map[string]json.RawMessage, []json.RawMessage, error) {
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, query, nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return nil, nil, nil, err
	}
	var page struct {
		Items  []json.RawMessage `json:"items"`
		Cursor *string           `json:"next_cursor"`
	}
	fields, err := contextObject(raw, &page, []string{"items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || page.Items == nil || len(page.Items) > limit ||
		(page.Cursor != nil && (!validTaskCursor(*page.Cursor) || len(page.Items) == 0)) || !c.safeMutationResponse(raw) {
		return nil, nil, nil, &Failure{Code: "invalid_api_response"}
	}
	return raw, fields, page.Items, nil
}

func nonNegative(values ...*big.Int) bool {
	for _, value := range values {
		if value == nil || value.Sign() < 0 {
			return false
		}
	}
	return true
}

func decodeActorProject(raw json.RawMessage) (ActorProject, bool) {
	var value ActorProject
	fields, err := contextObject(raw, &value, []string{"project_id", "name", "status", "admin_roles", "project_roles"}, []string{"admin_roles", "project_roles"})
	if err != nil || !requiredNullable(fields, "active_guide") || !validUUID(value.ProjectID) || value.Name == "" ||
		!oneOf(value.Status, "draft", "active", "paused", "archived") {
		return value, false
	}
	for _, role := range value.ProjectRoles {
		if !oneOf(role, "submitter", "reviewer") {
			return value, false
		}
	}
	for _, role := range value.AdminRoles {
		if !oneOf(role, "access_administrator", "operator", "project_manager", "finance_authority", "audit_authority") {
			return value, false
		}
	}
	return value, value.ActiveGuide == nil || (validUUID(value.ActiveGuide.GuideID) && value.ActiveGuide.Version != "")
}

// MyProjects lists projects where the caller holds an exact grant.
func (c *Client) MyProjects(ctx context.Context, q PageQuery) (Result[ActorProjectPage], error) {
	var result Result[ActorProjectPage]
	raw, fields, items, err := c.contributorPage(ctx, "/api/v1/actors/me/projects", q)
	if err != nil {
		return result, err
	}
	page := ActorProjectPage{Items: make([]ActorProject, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		value, ok := decodeActorProject(item)
		id, _ := uuidIdentity(value.ProjectID)
		if !ok || seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[ActorProjectPage]{Raw: raw, Value: page}, nil
}

func validLatestSubmission(raw json.RawMessage, value *LatestSubmission) bool {
	fields, err := contextObject(raw, value, []string{"submission_id", "version", "status", "submitted_at"}, nil)
	return err == nil && requiredNullable(fields, "status_reason", "decided_at") && validUUID(value.SubmissionID) &&
		value.Version != nil && value.Version.Sign() > 0 && validTime(value.SubmittedAt) &&
		validSubmissionOutcome(SubmissionHistory{Status: value.Status, StatusReason: value.StatusReason, DecidedAt: value.DecidedAt})
}

func decodeContributorAssignment(raw json.RawMessage) (ContributorAssignment, bool) {
	var value ContributorAssignment
	fields, err := contextObject(raw, &value, []string{"assignment_id", "project_id", "task_id", "title", "state", "assignment_status", "claimed_at", "compensation", "next_action", "updated_at"}, nil)
	if err != nil || !requiredNullable(fields, "task_status", "started_at", "released_at", "locked_guide_version", "latest_submission", "revision") ||
		!validUUID(value.AssignmentID) || !validUUID(value.ProjectID) || !validUUID(value.TaskID) ||
		!oneOf(value.State, "active", "closed") ||
		!oneOf(value.AssignmentStatus, "active", "completed", "revision_expired", "revision_exhausted", "authority_revoked") ||
		(value.State == "active") != (value.AssignmentStatus == "active") || (value.State == "closed" && value.TaskStatus != nil) ||
		(value.TaskStatus != nil && !oneOf(*value.TaskStatus, taskStatuses...)) ||
		!oneOf(value.NextAction, "start", "prepare_submission", "awaiting_evaluation", "revise", "none") ||
		!validTime(value.ClaimedAt) || !validTime(value.UpdatedAt) || !ValidCompensation(value.Compensation) ||
		(value.StartedAt != nil && !validTime(*value.StartedAt)) || (value.ReleasedAt != nil && !validTime(*value.ReleasedAt)) {
		return value, false
	}
	if value.LatestSubmission != nil && !validLatestSubmission(fields["latest_submission"], value.LatestSubmission) {
		return value, false
	}
	return value, value.Revision == nil || validateRevisionContext(fields["revision"], value.Revision) == nil
}

// MyAssignments lists the caller's claims in projects where it holds a Submitter grant.
func (c *Client) MyAssignments(ctx context.Context, q PageQuery) (Result[ContributorAssignmentPage], error) {
	var result Result[ContributorAssignmentPage]
	raw, fields, items, err := c.contributorPage(ctx, "/api/v1/actors/me/assignments", q)
	if err != nil {
		return result, err
	}
	page := ContributorAssignmentPage{Items: make([]ContributorAssignment, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		value, ok := decodeContributorAssignment(item)
		id, _ := uuidIdentity(value.AssignmentID)
		if !ok || seen[id] || (q.ProjectID != nil && !sameUUID(value.ProjectID, *q.ProjectID)) ||
			(q.State != nil && value.State != *q.State) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[ContributorAssignmentPage]{Raw: raw, Value: page}, nil
}

func decodeContributorSubmission(raw json.RawMessage) (ContributorSubmission, bool) {
	var value ContributorSubmission
	fields, err := contextObject(raw, &value, []string{"submission_id", "project_id", "task_id", "title", "version", "status", "submitted_at", "finding_counts", "updated_at"}, nil)
	ok := err == nil && requiredNullable(fields, "status_reason", "decided_at") &&
		validUUID(value.SubmissionID) && validUUID(value.ProjectID) && validUUID(value.TaskID) &&
		value.Version != nil && value.Version.Sign() > 0 && validTime(value.SubmittedAt) && validTime(value.UpdatedAt) &&
		validSubmissionOutcome(SubmissionHistory{Status: value.Status, StatusReason: value.StatusReason, DecidedAt: value.DecidedAt}) &&
		validFindingCounts(fields["finding_counts"], &value.FindingCounts)
	return value, ok
}

// MySubmissions lists the caller's attempts in projects where it holds a Submitter grant.
func (c *Client) MySubmissions(ctx context.Context, q PageQuery) (Result[ContributorSubmissionPage], error) {
	var result Result[ContributorSubmissionPage]
	raw, fields, items, err := c.contributorPage(ctx, "/api/v1/actors/me/submissions", q)
	if err != nil {
		return result, err
	}
	page := ContributorSubmissionPage{Items: make([]ContributorSubmission, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		value, ok := decodeContributorSubmission(item)
		id, _ := uuidIdentity(value.SubmissionID)
		if !ok || seen[id] || (q.ProjectID != nil && !sameUUID(value.ProjectID, *q.ProjectID)) ||
			(q.TaskID != nil && !sameUUID(value.TaskID, *q.TaskID)) || (q.Status != nil && value.Status != *q.Status) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[ContributorSubmissionPage]{Raw: raw, Value: page}, nil
}

// MySummary counts the caller's claims and attempts and sums its awards.
func (c *Client) MySummary(ctx context.Context, project *string) (Result[ContributorWorkSummary], error) {
	var result Result[ContributorWorkSummary]
	if !optionalUUID(project) {
		return result, errors.New("--project must be a UUID")
	}
	query := ""
	if project != nil {
		query = url.Values{"project_id": {*project}}.Encode()
	}
	raw, err := c.request(ctx, http.MethodGet, "/api/v1/actors/me/summary", query, nil)
	if err != nil {
		return result, err
	}
	var value ContributorWorkSummary
	fields, err := contextObject(raw, &value, []string{"assignments", "submissions", "award_totals"}, nil)
	var assignments AssignmentCounts
	var attempts AttemptCounts
	if err != nil || !requiredNullable(fields, "project_id") || (project == nil) != (value.ProjectID == nil) ||
		(project != nil && !sameUUID(*value.ProjectID, *project)) || value.AwardTotals == nil ||
		contextObjectError(fields["assignments"], &assignments, "active", "closed") ||
		contextObjectError(fields["submissions"], &attempts, attemptStatuses...) ||
		!nonNegative(assignments.Active, assignments.Closed, attempts.EvaluationPending, attempts.ReviewPending,
			attempts.Accepted, attempts.NeedsRevision, attempts.Rejected) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[2]string]bool{}
	for _, award := range value.AwardTotals {
		key := [2]string{award.Instrument, award.Unit}
		if !validCompensationAward(award) || seen[key] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[key] = true
	}
	return Result[ContributorWorkSummary]{Raw: raw, Value: value}, nil
}

func contextObjectError(raw json.RawMessage, value any, required ...string) bool {
	_, err := contextObject(raw, value, required, nil)
	return err != nil
}

// validPreparation checks one preparation summary; callers bind its task or project.
func validPreparation(fields map[string]json.RawMessage, value PreparationSummary) bool {
	if !requiredNullable(fields, "storage_status", "infrastructure_failure_code", "finding_counts", "admission_id", "submission_id", "completed_at") ||
		!validUUID(value.PreparationID) || !validUUID(value.TaskID) || !validUUID(value.AssignmentID) ||
		!oneOf(value.Outcome, "pending", "passed", "failed", "infrastructure_failed") ||
		!oneOf(value.State, "checking", "checks_failed", "infrastructure_failed", "storing", "ready", "submitted", "stale") ||
		!policyHash.MatchString(value.ArchiveSHA256) || value.ArchiveByteCount == nil || value.ArchiveByteCount.Sign() <= 0 ||
		!validTime(value.CreatedAt) || (value.CompletedAt != nil && !validTime(*value.CompletedAt)) ||
		!optionalUUID(value.AdmissionID) || !optionalUUID(value.SubmissionID) ||
		(value.State == "submitted") != (value.SubmissionID != nil) || (value.State == "ready") != (value.AdmissionID != nil) {
		return false
	}
	if value.FindingCounts != nil {
		var counts SubmissionFindingCounts
		return validFindingCounts(fields["finding_counts"], &counts)
	}
	return true
}

func preparationsPath(task string) (string, error) {
	if !submissionSelector(task) {
		return "", errors.New("TASK_ID must be a UUID")
	}
	return "/api/v1/tasks/" + url.PathEscape(task) + "/submission-bundle-preparations", nil
}

// Preparations lists the caller's ZIP preparations for one task, newest first.
func (c *Client) Preparations(ctx context.Context, task string, q PageQuery) (Result[PreparationPage], error) {
	var result Result[PreparationPage]
	path, err := preparationsPath(task)
	if err != nil {
		return result, err
	}
	query, err := q.encodePreparations()
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, path, query, q.Limit)
	if err != nil {
		return result, err
	}
	page := PreparationPage{Items: make([]PreparationSummary, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		var value PreparationSummary
		itemFields, err := contextObject(item, &value, []string{"preparation_id", "task_id", "assignment_id", "outcome", "state", "archive_sha256", "archive_byte_count", "created_at"}, nil)
		id, _ := uuidIdentity(value.PreparationID)
		if err != nil || !validPreparation(itemFields, value) || !sameUUID(value.TaskID, task) || seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[PreparationPage]{Raw: raw, Value: page}, nil
}

// Preparation reads one of the caller's preparations with every intake finding.
func (c *Client) Preparation(ctx context.Context, task, preparation string) (Result[PreparationDetail], error) {
	var result Result[PreparationDetail]
	path, err := preparationsPath(task)
	if err != nil {
		return result, err
	}
	if !submissionSelector(preparation) {
		return result, errors.New("PREPARATION_ID must be a UUID")
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path+"/"+url.PathEscape(preparation), "", nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	var value PreparationDetail
	fields, err := contextObject(raw, &value, []string{"preparation_id", "task_id", "assignment_id", "outcome", "state", "archive_sha256", "archive_byte_count", "created_at", "findings"}, nil)
	if err != nil || !validPreparation(fields, value.PreparationSummary) || !sameUUID(value.TaskID, task) || !sameUUID(value.PreparationID, preparation) ||
		value.Findings == nil || !validPreSubmissionResults(value.Findings, value.Outcome == "passed") || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[PreparationDetail]{Raw: raw, Value: value}, nil
}
