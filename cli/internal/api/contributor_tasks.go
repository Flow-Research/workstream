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
)

type CompensationAward struct {
	Instrument string `json:"instrument"`
	Unit       string `json:"unit"`
	Quantity   string `json:"quantity"`
}

type CompensationTerms struct {
	ContributionPolicyVersionID string          `json:"contribution_policy_version_id"`
	AcceptedSubmission          json.RawMessage `json:"accepted_submission"`
	CompletedReview             json.RawMessage `json:"completed_review"`
}

// ReadyTaskSummary is the public contributor projection, not management facts.
type ReadyTaskSummary struct {
	TaskID               string            `json:"task_id"`
	ProjectID            string            `json:"project_id"`
	Title                string            `json:"title"`
	TaskType             *string           `json:"task_type"`
	Difficulty           *string           `json:"difficulty"`
	SkillTags            []string          `json:"skill_tags"`
	EstimatedTimeMinutes *int              `json:"estimated_time_minutes"`
	CreatedAt            string            `json:"created_at"`
	Compensation         CompensationTerms `json:"compensation"`
}

type ReadyTaskPage struct {
	ProjectID  string
	Items      []ReadyTaskSummary
	NextCursor *string
}

// ContributorTaskDetail excludes management-only source and actor metadata.
type ContributorTaskDetail struct {
	TaskSummary
	Description        string            `json:"description"`
	AcceptanceCriteria *string           `json:"acceptance_criteria"`
	RejectionCriteria  *string           `json:"rejection_criteria"`
	Compensation       CompensationTerms `json:"compensation"`
}

var exactQuantity = regexp.MustCompile(`^(0|[1-9][0-9]*)(\.[0-9]+)?$`)

func compensationAwards(raw json.RawMessage) ([]CompensationAward, bool) {
	var unpaid string
	if err := jsonv2.Unmarshal(raw, &unpaid); err == nil {
		return nil, unpaid == "unpaid"
	}
	var awards []CompensationAward
	if err := jsonv2.Unmarshal(raw, &awards, jsonv2.RejectUnknownMembers(true)); err != nil || len(awards) < 1 || len(awards) > 2 {
		return nil, false
	}
	seen := make(map[string]bool)
	for _, award := range awards {
		validInstrument := award.Instrument == "money" || award.Instrument == "project_points"
		if !validInstrument || award.Unit == "" || !exactQuantity.MatchString(award.Quantity) ||
			!strings.ContainsAny(award.Quantity, "123456789") || seen[award.Instrument] {
			return nil, false
		}
		seen[award.Instrument] = true
	}
	return awards, true
}

func ValidCompensation(value CompensationTerms) bool {
	_, validID := uuidIdentity(value.ContributionPolicyVersionID)
	_, validAccepted := compensationAwards(value.AcceptedSubmission)
	_, validReviewed := compensationAwards(value.CompletedReview)
	return validID && validAccepted && validReviewed
}

func CompensationAwards(raw json.RawMessage) ([]CompensationAward, bool) {
	return compensationAwards(raw)
}

func (c *Client) ReadyTasks(ctx context.Context, project string, limit int, cursor *string) (Result[ReadyTaskPage], error) {
	var result Result[ReadyTaskPage]
	path, err := taskProjectPath(project)
	if err != nil {
		return result, err
	}
	query, err := taskPageQuery(limit, cursor)
	if err != nil {
		return result, err
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/ready", query, nil)
	if err != nil {
		return result, err
	}
	page, err := decodeTaskPage(raw, project, limit)
	if err != nil {
		return result, err
	}
	value := ReadyTaskPage{ProjectID: page.ProjectID, Items: make([]ReadyTaskSummary, 0, len(page.Items)), NextCursor: page.NextCursor}
	seen := make(map[[16]byte]bool)
	selected, _ := uuidIdentity(project)
	for _, item := range page.Items {
		var task ReadyTaskSummary
		err := decodeTaskFields(item, &task,
			[]string{"task_id", "project_id", "title", "created_at"},
			[]string{"task_type", "difficulty", "estimated_time_minutes", "skill_tags", "compensation"})
		id, validID := uuidIdentity(task.TaskID)
		returned, validProject := uuidIdentity(task.ProjectID)
		if err != nil || !validID || !validProject || returned != selected || !ValidCompensation(task.Compensation) ||
			!validTime(task.CreatedAt) || seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		value.Items = append(value.Items, task)
	}
	return Result[ReadyTaskPage]{Raw: raw, Value: value}, nil
}

func (c *Client) ContributorTask(ctx context.Context, selector string) (Result[ContributorTaskDetail], error) {
	var result Result[ContributorTaskDetail]
	selected, valid := uuidIdentity(selector)
	if !valid || len(selector) > 100 {
		return result, errors.New("TASK_ID must be a UUID")
	}
	raw, err := c.request(ctx, http.MethodGet, "/api/v1/tasks/"+url.PathEscape(selector), "", nil)
	if err != nil {
		return result, err
	}
	var value ContributorTaskDetail
	err = decodeTaskFields(raw, &value,
		[]string{"task_id", "project_id", "title", "description", "status", "created_at", "updated_at"},
		[]string{"skill_tags", "compensation"})
	returned, valid := uuidIdentity(value.TaskID)
	if err != nil || !valid || returned != selected || !validTask(value.TaskSummary, value.ProjectID) || !ValidCompensation(value.Compensation) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ContributorTaskDetail]{Raw: raw, Value: value}, nil
}
