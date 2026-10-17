package api

import (
	"context"
	"encoding/json"
	"errors"
)

// ProjectPreparation is one contributor's preparation with finding counts only.
type ProjectPreparation struct {
	PreparationSummary
	ActorProfileID string `json:"actor_profile_id"`
}

type ProjectPreparationPage struct {
	Items  []ProjectPreparation `json:"items"`
	Cursor *string              `json:"next_cursor"`
}

var preparationOutcomes = []string{"pending", "passed", "failed", "infrastructure_failed"}

// ProjectPreparations lists every contributor's ZIP preparations in one project, newest first.
func (c *Client) ProjectPreparations(ctx context.Context, project string, q PageQuery) (Result[ProjectPreparationPage], error) {
	var result Result[ProjectPreparationPage]
	if q.ProjectID != nil || q.TaskID != nil || q.State != nil || q.Status != nil || q.UpdatedSince != nil {
		return result, errors.New("preparations accept only --outcome")
	}
	path, err := projectReadPath(project, "/submission-bundle-preparations")
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
	page := ProjectPreparationPage{Items: make([]ProjectPreparation, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		var value ProjectPreparation
		itemFields, err := contextObject(item, &value, []string{"preparation_id", "task_id", "assignment_id", "outcome", "state", "archive_sha256", "archive_byte_count", "created_at", "actor_profile_id"}, nil)
		id, _ := uuidIdentity(value.PreparationID)
		if err != nil || !validPreparation(itemFields, value.PreparationSummary) || !validUUID(value.ActorProfileID) || seen[id] ||
			(q.Outcome != nil && value.Outcome != *q.Outcome) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[ProjectPreparationPage]{Raw: raw, Value: page}, nil
}
