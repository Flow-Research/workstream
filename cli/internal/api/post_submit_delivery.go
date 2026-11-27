package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"unicode/utf8"
)

// PostSubmitDeliverySource is an observed UNKNOWN delivery, not permission to reconcile it.
type PostSubmitDeliverySource struct {
	ProjectID             string   `json:"project_id"`
	EventID               string   `json:"event_id"`
	EventType             string   `json:"event_type"`
	EventVersion          *big.Int `json:"event_version"`
	AggregateID           string   `json:"aggregate_id"`
	EvaluationRequestID   string   `json:"evaluation_request_id"`
	CheckerRunID          string   `json:"checker_run_id"`
	EvaluationGeneration  *big.Int `json:"evaluation_generation"`
	ClaimGeneration       *big.Int `json:"claim_generation"`
	PayloadDigest         string   `json:"payload_digest"`
	FinalizedAt           string   `json:"finalized_at"`
	DeliveryState         string   `json:"delivery_state"`
	ErrorCode             string   `json:"error_code"`
	Classification        string   `json:"classification"`
	ReconciliationEventID *string  `json:"reconciliation_event_id"`
	ReconciliationState   *string  `json:"reconciliation_state"`
}

type PostSubmitDeliveryPage struct {
	ProjectID  string                     `json:"project_id"`
	Items      []PostSubmitDeliverySource `json:"items"`
	NextCursor *string                    `json:"next_cursor"`
}

type PostSubmitDeliverySuccessor struct {
	EventID        string `json:"event_id"`
	PayloadDigest  string `json:"payload_digest"`
	OccurredAt     string `json:"occurred_at"`
	Classification string `json:"classification"`
}

type PostSubmitDeliveryReceipt struct {
	Source                  PostSubmitDeliverySource    `json:"source"`
	Successor               PostSubmitDeliverySuccessor `json:"successor"`
	AuthorizationDecisionID string                      `json:"authorization_decision_id"`
}

func validDeliverySource(raw json.RawMessage, source *PostSubmitDeliverySource, project, event string) bool {
	fields, err := contextObject(raw, source, []string{
		"project_id", "event_id", "event_type", "event_version", "aggregate_id", "evaluation_request_id", "checker_run_id",
		"evaluation_generation", "claim_generation", "payload_digest", "finalized_at", "delivery_state", "error_code", "classification",
	}, nil)
	if err != nil || !requiredNullable(fields, "reconciliation_event_id", "reconciliation_state") ||
		!sameUUID(source.ProjectID, project) || !validUUID(source.EventID) || (event != "" && !sameUUID(source.EventID, event)) ||
		(source.EventType != "PostSubmissionEvaluationRequested" && source.EventType != "PostSubmissionEvaluationCompleted") ||
		source.EventVersion == nil || source.EventVersion.Cmp(big.NewInt(1)) != 0 ||
		!validUUID(source.AggregateID) || !validUUID(source.EvaluationRequestID) || !validUUID(source.CheckerRunID) ||
		!positive(source.EvaluationGeneration, source.ClaimGeneration) || !contextPolicyDigest.MatchString(source.PayloadDigest) ||
		!validAuditTime(source.FinalizedAt) || source.DeliveryState != "dead_letter" || source.ErrorCode != "INVOKE_OUTCOME_UNKNOWN" ||
		!validDeliveryClassification(source.Classification) {
		return false
	}
	if (source.ReconciliationEventID == nil) != (source.ReconciliationState == nil) {
		return false
	}
	if source.ReconciliationEventID != nil {
		if !validUUID(*source.ReconciliationEventID) || sameUUID(*source.ReconciliationEventID, source.EventID) ||
			(*source.ReconciliationState != "pending" && *source.ReconciliationState != "active" &&
				*source.ReconciliationState != "acknowledged" && *source.ReconciliationState != "held") ||
			(*source.ReconciliationState == "held" && source.Classification != "unresolved") {
			return false
		}
	}
	return true
}

func validDeliveryClassification(value string) bool {
	return value == "committed" || value == "retry_safe" || value == "unresolved"
}

func (c *Client) PostSubmitDeliveries(ctx context.Context, project string, limit int, cursor string) (Result[PostSubmitDeliveryPage], error) {
	var result Result[PostSubmitDeliveryPage]
	if !validUUID(project) || len(project) > 100 || limit < 1 || limit > 100 || (cursor != "" && !validTaskCursor(cursor)) {
		return result, errors.New("PROJECT_ID must be a UUID, --limit 1..100, and --cursor at most 512 characters")
	}
	query := url.Values{"limit": {strconv.Itoa(limit)}}
	if cursor != "" {
		query.Set("cursor", cursor)
	}
	path := "/api/v1/operations/projects/" + url.PathEscape(project) + "/post-submit-deliveries"
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, query.Encode(), nil, "", http.StatusOK, MaxGuideInputBytes)
	if err != nil {
		return result, err
	}
	var page PostSubmitDeliveryPage
	fields, err := contextObject(raw, &page, []string{"project_id", "items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || !sameUUID(page.ProjectID, project) ||
		page.Items == nil || len(page.Items) > limit || !c.safeMutationResponse(raw) ||
		(page.NextCursor != nil && !validTaskCursor(*page.NextCursor)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	var items []json.RawMessage
	if jsonv2.Unmarshal(fields["items"], &items) != nil || len(items) != len(page.Items) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for i := range page.Items {
		if !validDeliverySource(items[i], &page.Items[i], project, "") {
			return result, &Failure{Code: "invalid_api_response"}
		}
		id, _ := uuidIdentity(page.Items[i].EventID)
		if seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
	}
	return Result[PostSubmitDeliveryPage]{Raw: raw, Value: page}, nil
}

func ValidPostSubmitDeliveryReason(reason string) bool {
	if !utf8.ValidString(reason) || utf8.RuneCountInString(reason) < 1 || utf8.RuneCountInString(reason) > 500 || strings.TrimSpace(reason) != reason {
		return false
	}
	for _, r := range reason {
		if r < 32 || r == 127 {
			return false
		}
	}
	return true
}

func (c *Client) ReconcilePostSubmitDelivery(ctx context.Context, project, event, reason, key string, abandonUnknown bool) (Result[PostSubmitDeliveryReceipt], error) {
	var result Result[PostSubmitDeliveryReceipt]
	if !validUUID(project) || !validUUID(event) || !validUUID(key) || len(project) > 100 || len(event) > 100 || len(key) > 100 {
		return result, errors.New("PROJECT_ID, EVENT_ID and --idempotency-key must be UUIDs")
	}
	if !ValidPostSubmitDeliveryReason(reason) {
		return result, errors.New("--reason must be 1..500 characters without surrounding whitespace or ASCII controls")
	}
	bodyFields := map[string]string{"reason": reason}
	if abandonUnknown {
		bodyFields["action"] = "abandon_unknown"
	}
	body, _ := json.Marshal(bodyFields)
	path := "/api/v1/operations/projects/" + url.PathEscape(project) + "/post-submit-deliveries/" + url.PathEscape(event) + "/reconcile"
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPost, path, "", body, key, http.StatusCreated, MaxGuideInputBytes)
	hint := "delivery reconciliation outcome unknown; manually replay only the unchanged project, event, action, reason and key"
	if err != nil {
		return result, checkerMutationFailure(err, hint)
	}
	var receipt PostSubmitDeliveryReceipt
	fields, err := contextObject(raw, &receipt, []string{"source", "successor", "authorization_decision_id"}, nil)
	if err != nil || !validUUID(receipt.AuthorizationDecisionID) ||
		!validDeliverySource(fields["source"], &receipt.Source, project, event) ||
		!validDeliverySuccessor(fields["successor"], &receipt.Successor, abandonUnknown) ||
		receipt.Source.ReconciliationEventID == nil || !sameUUID(*receipt.Source.ReconciliationEventID, receipt.Successor.EventID) ||
		(receipt.Source.ReconciliationState != nil && *receipt.Source.ReconciliationState == "pending" && receipt.Source.Classification != receipt.Successor.Classification) ||
		!c.safeMutationResponse(raw) {
		return result, checkerMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, hint)
	}
	return Result[PostSubmitDeliveryReceipt]{Raw: raw, Value: receipt}, nil
}

func validDeliverySuccessor(raw json.RawMessage, value *PostSubmitDeliverySuccessor, abandonUnknown bool) bool {
	_, err := contextObject(raw, value, []string{"event_id", "payload_digest", "occurred_at", "classification"}, nil)
	return err == nil && validUUID(value.EventID) && contextPolicyDigest.MatchString(value.PayloadDigest) &&
		validAuditTime(value.OccurredAt) && ((abandonUnknown && value.Classification == "unresolved") || (!abandonUnknown && (value.Classification == "committed" || value.Classification == "retry_safe")))
}
