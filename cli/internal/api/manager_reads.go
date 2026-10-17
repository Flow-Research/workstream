package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math"
	"math/big"
	"net/http"
	"net/url"
)

// ProjectWorkQuery selects one page of a project's attempts or claims. The
// server binds every continuation to the same caller, project and filters.
type ProjectWorkQuery struct {
	PageQuery
	SubmitterID *string
}

// ProjectSubmission is the contributor attempt shape plus its submitter.
type ProjectSubmission struct {
	ContributorSubmission
	SubmitterActorID string `json:"submitter_actor_id"`
}

type ProjectSubmissionPage struct {
	Items  []ProjectSubmission `json:"items"`
	Cursor *string             `json:"next_cursor"`
}

// ProjectAssignment is the contributor claim shape plus its contributor.
type ProjectAssignment struct {
	ContributorAssignment
	ContributorActorID string `json:"contributor_actor_id"`
}

type ProjectAssignmentPage struct {
	Items  []ProjectAssignment `json:"items"`
	Cursor *string             `json:"next_cursor"`
}

// TaskStatusCounts holds one count per closed task status.
type TaskStatusCounts map[string]*big.Int

// ProjectWorkSummary carries award totals only for an exact-project Finance caller.
type ProjectWorkSummary struct {
	ProjectID                     string               `json:"project_id"`
	Tasks                         TaskStatusCounts     `json:"tasks"`
	Assignments                   AssignmentCounts     `json:"assignments"`
	Submissions                   AttemptCounts        `json:"submissions"`
	AcceptanceRate                *float64             `json:"acceptance_rate"`
	CheckerInfrastructureFailures *big.Int             `json:"checker_infrastructure_failures"`
	AwardTotals                   *[]CompensationAward `json:"award_totals"`
}

type TaskImportBatchSummary struct {
	BatchID     string           `json:"batch_id"`
	SourceID    string           `json:"source_id"`
	Label       *string          `json:"label"`
	SHA256      string           `json:"sha256"`
	ByteCount   *big.Int         `json:"byte_count"`
	RowCount    *big.Int         `json:"row_count"`
	State       string           `json:"state"`
	CreatedAt   string           `json:"created_at"`
	CommittedAt *string          `json:"committed_at"`
	TaskCounts  TaskStatusCounts `json:"task_counts"`
}

type TaskImportBatchPage struct {
	Items  []TaskImportBatchSummary `json:"items"`
	Cursor *string                  `json:"next_cursor"`
}

func (q ProjectWorkQuery) encode() (string, error) {
	if q.ProjectID != nil || !optionalUUID(q.SubmitterID) {
		return "", errors.New("--submitter must be a UUID")
	}
	query, err := q.PageQuery.encode()
	if err != nil || q.SubmitterID == nil {
		return query, err
	}
	values, _ := url.ParseQuery(query)
	values.Set("submitter_actor_id", *q.SubmitterID)
	return values.Encode(), nil
}

func projectReadPath(project, suffix string) (string, error) {
	if !submissionSelector(project) {
		return "", errors.New("PROJECT_ID must be a UUID")
	}
	return "/api/v1/projects/" + url.PathEscape(project) + suffix, nil
}

// withoutActor removes the one actor field the project read adds, so the
// remaining object must be exactly the contributor projection.
func withoutActor(raw json.RawMessage, key string) (json.RawMessage, string, bool) {
	var fields map[string]json.RawMessage
	var actor string
	if jsonv2.Unmarshal(raw, &fields) != nil || jsonv2.Unmarshal(fields[key], &actor) != nil || !validUUID(actor) {
		return nil, "", false
	}
	delete(fields, key)
	rest, err := jsonv2.Marshal(fields)
	return rest, actor, err == nil
}

// ProjectSubmissions lists every attempt in a project under Project Manager authority.
func (c *Client) ProjectSubmissions(ctx context.Context, project string, q ProjectWorkQuery) (Result[ProjectSubmissionPage], error) {
	var result Result[ProjectSubmissionPage]
	path, err := projectReadPath(project, "/submissions")
	if err != nil {
		return result, err
	}
	query, err := q.encode()
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, path, query, q.Limit)
	if err != nil {
		return result, err
	}
	page := ProjectSubmissionPage{Items: make([]ProjectSubmission, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		rest, submitter, ok := withoutActor(item, "submitter_actor_id")
		value, valid := decodeContributorSubmission(rest)
		id, _ := uuidIdentity(value.SubmissionID)
		if !ok || !valid || seen[id] || !sameUUID(value.ProjectID, project) ||
			(q.TaskID != nil && !sameUUID(value.TaskID, *q.TaskID)) || (q.Status != nil && value.Status != *q.Status) ||
			(q.SubmitterID != nil && !sameUUID(submitter, *q.SubmitterID)) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, ProjectSubmission{ContributorSubmission: value, SubmitterActorID: submitter})
	}
	return Result[ProjectSubmissionPage]{Raw: raw, Value: page}, nil
}

// ProjectAssignments lists every claim in a project under Project Manager authority.
func (c *Client) ProjectAssignments(ctx context.Context, project string, q ProjectWorkQuery) (Result[ProjectAssignmentPage], error) {
	var result Result[ProjectAssignmentPage]
	if q.TaskID != nil || q.Status != nil || q.UpdatedSince != nil || q.SubmitterID != nil {
		return result, errors.New("assignments accept only --state")
	}
	path, err := projectReadPath(project, "/assignments")
	if err != nil {
		return result, err
	}
	query, err := q.encode()
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, path, query, q.Limit)
	if err != nil {
		return result, err
	}
	page := ProjectAssignmentPage{Items: make([]ProjectAssignment, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		rest, contributor, ok := withoutActor(item, "contributor_actor_id")
		value, valid := decodeContributorAssignment(rest)
		id, _ := uuidIdentity(value.AssignmentID)
		if !ok || !valid || seen[id] || !sameUUID(value.ProjectID, project) || (q.State != nil && value.State != *q.State) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, ProjectAssignment{ContributorAssignment: value, ContributorActorID: contributor})
	}
	return Result[ProjectAssignmentPage]{Raw: raw, Value: page}, nil
}

// validTaskCounts requires exactly one non-negative count per task status and returns their sum.
func validTaskCounts(counts TaskStatusCounts) (*big.Int, bool) {
	total := new(big.Int)
	if len(counts) != len(taskStatuses) {
		return nil, false
	}
	for _, status := range taskStatuses {
		value, present := counts[status]
		if !present || !nonNegative(value) {
			return nil, false
		}
		total.Add(total, value)
	}
	return total, true
}

// ProjectSummary counts a project's work; award totals are null without exact-project Finance authority.
func (c *Client) ProjectSummary(ctx context.Context, project string) (Result[ProjectWorkSummary], error) {
	var result Result[ProjectWorkSummary]
	path, err := projectReadPath(project, "/summary")
	if err != nil {
		return result, err
	}
	raw, err := c.request(ctx, http.MethodGet, path, "", nil)
	if err != nil {
		return result, err
	}
	var value ProjectWorkSummary
	fields, err := contextObject(raw, &value, []string{"project_id", "tasks", "assignments", "submissions", "checker_infrastructure_failures"}, nil)
	var assignments AssignmentCounts
	var attempts AttemptCounts
	if err != nil || !requiredNullable(fields, "acceptance_rate", "award_totals") || !sameUUID(value.ProjectID, project) ||
		contextObjectError(fields["assignments"], &assignments, "active", "closed") ||
		contextObjectError(fields["submissions"], &attempts, attemptStatuses...) ||
		!nonNegative(assignments.Active, assignments.Closed, attempts.EvaluationPending, attempts.ReviewPending,
			attempts.Accepted, attempts.NeedsRevision, attempts.Rejected, value.CheckerInfrastructureFailures) ||
		!c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if _, ok := validTaskCounts(value.Tasks); !ok {
		return result, &Failure{Code: "invalid_api_response"}
	}
	decided := new(big.Int).Add(attempts.Accepted, new(big.Int).Add(attempts.NeedsRevision, attempts.Rejected))
	if rate := value.AcceptanceRate; (decided.Sign() == 0) != (rate == nil) ||
		(rate != nil && (math.IsNaN(*rate) || *rate < 0 || *rate > 1)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if value.AwardTotals != nil {
		seen := map[[2]string]bool{}
		for _, award := range *value.AwardTotals {
			key := [2]string{award.Instrument, award.Unit}
			if !validCompensationAward(award) || seen[key] {
				return result, &Failure{Code: "invalid_api_response"}
			}
			seen[key] = true
		}
	}
	value.Assignments, value.Submissions = assignments, attempts
	return Result[ProjectWorkSummary]{Raw: raw, Value: value}, nil
}

func validImportBatch(raw json.RawMessage, value *TaskImportBatchSummary) bool {
	fields, err := contextObject(raw, value, []string{"batch_id", "source_id", "sha256", "byte_count", "row_count", "state", "created_at", "task_counts"}, nil)
	if err != nil || !requiredNullable(fields, "label", "committed_at") || !validUUID(value.BatchID) || !validUUID(value.SourceID) ||
		!policyHash.MatchString(value.SHA256) || value.ByteCount == nil || value.ByteCount.Sign() <= 0 ||
		value.RowCount == nil || value.RowCount.Sign() <= 0 || value.RowCount.Cmp(big.NewInt(500)) > 0 ||
		!oneOf(value.State, "pending", "committed") || (value.State == "committed") != (value.CommittedAt != nil) ||
		!validTime(value.CreatedAt) || (value.CommittedAt != nil && !validTime(*value.CommittedAt)) ||
		(value.Label != nil && *value.Label == "") {
		return false
	}
	total, ok := validTaskCounts(value.TaskCounts)
	// A committed batch's members are exactly its rows; a pending batch has none yet.
	return ok && ((value.State == "committed" && total.Cmp(value.RowCount) == 0) || (value.State == "pending" && total.Sign() == 0))
}

// ProjectImportBatches lists a project's native task import batches in creation order.
func (c *Client) ProjectImportBatches(ctx context.Context, project string, q ProjectWorkQuery) (Result[TaskImportBatchPage], error) {
	var result Result[TaskImportBatchPage]
	if q.TaskID != nil || q.Status != nil || q.State != nil || q.UpdatedSince != nil || q.SubmitterID != nil {
		return result, errors.New("import batches accept no filters")
	}
	path, err := projectReadPath(project, "/task-import-batches")
	if err != nil {
		return result, err
	}
	query, err := q.encode()
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, path, query, q.Limit)
	if err != nil {
		return result, err
	}
	page := TaskImportBatchPage{Items: make([]TaskImportBatchSummary, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		var value TaskImportBatchSummary
		if !validImportBatch(item, &value) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		id, _ := uuidIdentity(value.BatchID)
		if seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[TaskImportBatchPage]{Raw: raw, Value: page}, nil
}
