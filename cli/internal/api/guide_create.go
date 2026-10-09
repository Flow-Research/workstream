package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"net/http"
	"net/url"
	"reflect"
	"strings"
	"unicode"
)

// These are CLI wire envelopes, not backend policy limits. Guide declarations
// include examples and up to 100 document selectors, unlike small mutations.
const MaxGuideInputBytes = 1024 * 1024
const maxGuideResponseBytes = 2 * 1024 * 1024

type GuideExample struct {
	Content string   `json:"content"`
	Title   *string  `json:"title"`
	Labels  []string `json:"labels"`
}

type GuideDocumentInput struct {
	Label     string `json:"label"`
	MediaType string `json:"media_type"`
}

type GuideDocument struct {
	DocumentID string `json:"document_id"`
	Label      string `json:"label"`
	MediaType  string `json:"media_type"`
	Order      int    `json:"order"`
}

type GuideWaitingSetup struct {
	ID     string `json:"id"`
	Status string `json:"status"`
}

// GuideCreated is the immutable creation receipt, not current guide readiness.
type GuideCreated struct {
	ContributionPolicyID        *string           `json:"contribution_policy_id"`
	ContributionPolicyVersionID *string           `json:"contribution_policy_version_id"`
	ActivationOperationID       *string           `json:"activation_operation_id"`
	ID                          string            `json:"id"`
	ProjectID                   string            `json:"project_id"`
	Version                     string            `json:"version"`
	Status                      string            `json:"status"`
	ChangeSummary               *string           `json:"change_summary"`
	TaskExamples                []GuideExample    `json:"task_examples"`
	TaskExamplesHash            *string           `json:"task_examples_hash"`
	ApprovedBy                  *string           `json:"approved_by"`
	EffectiveAt                 *string           `json:"effective_at"`
	CreatedBy                   string            `json:"created_by"`
	CreatedAt                   string            `json:"created_at"`
	UpdatedAt                   string            `json:"updated_at"`
	SupersededAt                *string           `json:"superseded_at"`
	Documents                   []GuideDocument   `json:"documents"`
	Setup                       GuideWaitingSetup `json:"setup"`
}

type guideCreateInput struct {
	Version       string               `json:"version"`
	ChangeSummary *string              `json:"change_summary"`
	TaskExamples  []json.RawMessage    `json:"task_examples"`
	Documents     []GuideDocumentInput `json:"documents"`
}

func (c *Client) CreateGuide(ctx context.Context, project string, body json.RawMessage, key string) (Result[GuideCreated], error) {
	var result Result[GuideCreated]
	if !validUUID(project) || len(project) > 100 || !validUUID(key) || len(key) > 100 {
		return result, errors.New("PROJECT_ID and --idempotency-key must be UUIDs")
	}
	if len(body) > MaxGuideInputBytes {
		return result, errors.New("--input must contain a bounded public guide declaration")
	}
	input, examples, err := decodeGuideInput(body)
	if err != nil {
		return result, errors.New("--input must contain a bounded public guide declaration")
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPost,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides", "", body, key, http.StatusCreated, maxGuideResponseBytes)
	if err != nil {
		return result, guideCreateFailure(err)
	}
	value, err := decodeCreatedGuide(raw, project, input, examples)
	if err != nil {
		return result, guideCreateFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[GuideCreated]{Raw: raw, Value: value}, nil
}

func decodeGuideInput(raw json.RawMessage) (guideCreateInput, []GuideExample, error) {
	var input guideCreateInput
	fields, err := contextObject(raw, &input, []string{"version", "task_examples", "documents"}, nil)
	if err != nil {
		return input, nil, err
	}
	examples, err := decodeGuideExamples(fields["task_examples"])
	if err != nil {
		return input, nil, err
	}
	var documents []json.RawMessage
	if jsonv2.Unmarshal(fields["documents"], &documents) != nil || len(documents) == 0 || len(documents) > 100 {
		return input, nil, errors.New("invalid documents")
	}
	for _, document := range documents {
		var value GuideDocumentInput
		if _, err := contextObject(document, &value, []string{"label", "media_type"}, nil); err != nil || !guideMediaType(value.MediaType) {
			return input, nil, errors.New("invalid document declaration")
		}
	}
	return input, examples, nil
}

func decodeGuideExamples(raw json.RawMessage) ([]GuideExample, error) {
	var members []json.RawMessage
	if jsonv2.Unmarshal(raw, &members) != nil || len(members) == 0 || len(members) > 100 {
		return nil, errors.New("invalid examples")
	}
	examples := make([]GuideExample, 0, len(members))
	for _, member := range members {
		value := GuideExample{Labels: []string{}}
		if _, err := contextObject(member, &value, []string{"content"}, []string{"labels"}); err != nil {
			return nil, err
		}
		examples = append(examples, value)
	}
	return examples, nil
}

func decodeCreatedGuide(raw json.RawMessage, project string, input guideCreateInput, examples []GuideExample) (GuideCreated, error) {
	var value GuideCreated
	fields, err := contextObject(raw, &value, []string{
		"id", "project_id", "version", "status", "created_by", "created_at", "updated_at", "documents", "setup", "task_examples",
	}, nil)
	if err != nil {
		return value, err
	}
	// Nullable but required fields must still be present; the public schema's
	// three optional policy/activation UUIDs may be omitted with null defaults.
	for _, field := range []string{"change_summary", "task_examples_hash", "approved_by", "effective_at", "superseded_at"} {
		if _, ok := fields[field]; !ok {
			return value, errors.New("missing guide field")
		}
	}
	returnedExamples, err := decodeGuideExamples(fields["task_examples"])
	if err != nil || !reflect.DeepEqual(examples, returnedExamples) || !reflect.DeepEqual(input.ChangeSummary, value.ChangeSummary) ||
		!validUUID(value.ID) || !sameUUID(value.ProjectID, project) || value.Version != input.Version || value.Status != "draft" ||
		!validUUID(value.CreatedBy) || !validTime(value.CreatedAt) || !validTime(value.UpdatedAt) ||
		value.TaskExamplesHash == nil || !contextPolicyDigest.MatchString(*value.TaskExamplesHash) {
		return value, errors.New("invalid guide receipt")
	}
	value.TaskExamples = returnedExamples
	// Creation and its stored exact replay precede approval/activation. Valid
	// UUIDs and times are still invalid here when they imply those later facts.
	if value.ContributionPolicyID != nil || value.ContributionPolicyVersionID != nil ||
		value.ActivationOperationID != nil || value.ApprovedBy != nil || value.EffectiveAt != nil || value.SupersededAt != nil {
		return value, errors.New("contradictory draft guide receipt")
	}
	if _, err := contextObject(fields["setup"], &value.Setup, []string{"id", "status"}, nil); err != nil ||
		!validUUID(value.Setup.ID) || value.Setup.Status != "awaiting_documents" {
		return value, errors.New("invalid setup receipt")
	}
	var documents []json.RawMessage
	if jsonv2.Unmarshal(fields["documents"], &documents) != nil || len(documents) != len(input.Documents) {
		return value, errors.New("invalid document membership")
	}
	identities := make(map[[16]byte]bool, len(documents))
	for index, document := range documents {
		var item GuideDocument
		_, err := contextObject(document, &item, []string{"document_id", "label", "media_type", "order"}, nil)
		identity, valid := uuidIdentity(item.DocumentID)
		if err != nil || !valid || identities[identity] || item.Order != index ||
			item.MediaType != input.Documents[index].MediaType || item.Label != normalizedGuideLabel(input.Documents[index].Label) {
			return value, errors.New("invalid document selector")
		}
		identities[identity] = true
	}
	return value, nil
}

func normalizedGuideLabel(label string) string {
	// Python str.split(), used by the public owner, includes U+001C–U+001F
	// in addition to the Unicode whitespace accepted by Go's Fields.
	return strings.Join(strings.FieldsFunc(label, func(r rune) bool {
		return unicode.IsSpace(r) || (r >= '\x1c' && r <= '\x1f')
	}), " ")
}

func guideMediaType(value string) bool {
	return value == "application/pdf" || value == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
		value == "application/vnd.openxmlformats-officedocument.presentationml.presentation" || value == "text/markdown"
}

func guideCreateFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "guide declaration outcome unknown; replay only the unchanged project, input file contents and idempotency key"
	}
	return err
}
