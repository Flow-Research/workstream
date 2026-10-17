package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"mime"
	"net/http"
	"net/url"
	"regexp"
	"strings"
)

type ProjectGuideSummary struct {
	GuideID     string  `json:"guide_id"`
	Version     string  `json:"version"`
	Status      string  `json:"status"`
	CreatedAt   string  `json:"created_at"`
	EffectiveAt *string `json:"effective_at"`
}

type ProjectGuidePage struct {
	Items  []ProjectGuideSummary `json:"items"`
	Cursor *string               `json:"next_cursor"`
}

type ProjectGuideRecord struct {
	GuideID                     string  `json:"guide_id"`
	ProjectID                   string  `json:"project_id"`
	Version                     string  `json:"version"`
	Status                      string  `json:"status"`
	ChangeSummary               *string `json:"change_summary"`
	TaskExamplesHash            *string `json:"task_examples_hash"`
	ContributionPolicyID        *string `json:"contribution_policy_id"`
	ContributionPolicyVersionID *string `json:"contribution_policy_version_id"`
	ActivationOperationID       *string `json:"activation_operation_id"`
	ApprovedBy                  *string `json:"approved_by"`
	CreatedBy                   string  `json:"created_by"`
	CreatedAt                   string  `json:"created_at"`
	UpdatedAt                   string  `json:"updated_at"`
	EffectiveAt                 *string `json:"effective_at"`
	SupersededAt                *string `json:"superseded_at"`
}

type ProjectGuideDocument struct {
	DocumentID  string   `json:"document_id"`
	Label       string   `json:"label"`
	MediaType   string   `json:"media_type"`
	Order       *big.Int `json:"order"`
	IngestState string   `json:"ingest_state"`
	SHA256      *string  `json:"sha256"`
	ByteCount   *big.Int `json:"byte_count"`
}

type GuideReviewPolicyValues struct {
	PolicyID                         string   `json:"policy_id"`
	Generation                       *big.Int `json:"generation"`
	PolicyHash                       string   `json:"policy_hash"`
	HumanReviewRequired              bool     `json:"human_review_required"`
	SemanticsFormat                  string   `json:"semantics_format"`
	SemanticsStatus                  string   `json:"semantics_status"`
	SupersedesPolicyID               *string  `json:"supersedes_policy_id"`
	ReviewPreferenceWindowSeconds    *big.Int `json:"review_preference_window_seconds"`
	ReviewLeaseDurationSeconds       *big.Int `json:"review_lease_duration_seconds"`
	MaxActiveReviewLeasesPerReviewer *big.Int `json:"max_active_review_leases_per_reviewer"`
	SelfReviewAllowed                *bool    `json:"self_review_allowed"`
	RejectPolicy                     *string  `json:"reject_policy"`
	FindingEvidenceRequirement       *string  `json:"finding_evidence_requirement"`
	AllowedDecisions                 []string `json:"allowed_decisions"`
	MinimumFindingFields             []string `json:"minimum_finding_fields"`
	CreatedAt                        string   `json:"created_at"`
}

type GuideRevisionPolicyValues struct {
	PolicyID                  string   `json:"policy_id"`
	Generation                *big.Int `json:"generation"`
	PolicyHash                string   `json:"policy_hash"`
	SemanticsStatus           string   `json:"semantics_status"`
	SupersedesPolicyID        *string  `json:"supersedes_policy_id"`
	MaxRevisionRounds         *big.Int `json:"max_revision_rounds"`
	RevisionDeadlineHours     *big.Int `json:"revision_deadline_hours"`
	AllowedResubmissionStates []string `json:"allowed_resubmission_states"`
	ReviewerReassignmentRule  *string  `json:"reviewer_reassignment_rule"`
	CreatedAt                 string   `json:"created_at"`
}

type ProjectGuideDetail struct {
	Guide               ProjectGuideRecord         `json:"guide"`
	Documents           []ProjectGuideDocument     `json:"documents"`
	ReviewPolicy        *GuideReviewPolicyValues   `json:"review_policy"`
	RevisionPolicy      *GuideRevisionPolicyValues `json:"revision_policy"`
	LatestSetupRunID    *string                    `json:"latest_setup_run_id"`
	LatestCompilationID *string                    `json:"latest_compilation_id"`
}

type MissingCheckerCapability struct {
	RequirementID string `json:"requirement_id"`
	Stage         string `json:"stage"`
	Title         string `json:"title"`
}

type GuideActivationCondition struct {
	Code                string                     `json:"code"`
	Reason              string                     `json:"reason"`
	Message             string                     `json:"message"`
	MissingCapabilities []MissingCheckerCapability `json:"missing_capabilities"`
}

type GuideActivationReadiness struct {
	ProjectID string                     `json:"project_id"`
	GuideID   string                     `json:"guide_id"`
	Ready     bool                       `json:"ready"`
	Unmet     []GuideActivationCondition `json:"unmet"`
}

var guideStatuses = []string{"draft", "active", "superseded"}

// activationReasonCodes is the refusal code activation raises for each unmet
// reason; integrity faults carry the code of the refusal that stopped them.
var activationReasonCodes = map[string]string{
	"project_not_activatable":         "approval_blocked",
	"post_policy_unavailable":         "",
	"upstream_approval_not_current":   "",
	"post_policy_not_approved":        "proposal_stale",
	"guide_not_draft":                 "",
	"review_policy_unselected":        "proposal_stale",
	"revision_policy_unselected":      "proposal_stale",
	"source_snapshot_invalid":         "approval_blocked",
	"checker_policy_unsupported":      "approval_blocked",
	"checker_policy_mismatch":         "approval_blocked",
	"checker_registry_changed":        "approval_blocked",
	"checker_capability_missing":      "approval_blocked",
	"human_review_required_by_guide":  "approval_blocked",
	"activation_requirements_unmet":   "approval_blocked",
	"contribution_policy_unpublished": "proposal_stale",
	"contribution_policy_invalid":     "proposal_stale",
	"activation_integrity_failed":     "",
}

var capabilityRequirement = regexp.MustCompile(`^[a-z][a-z0-9_.-]{0,99}$`)

func guidePath(project, guide string) (string, error) {
	path, err := projectReadPath(project, "/guides")
	if err != nil || !validUUID(guide) {
		return "", errors.New("PROJECT_ID and GUIDE_ID must be UUIDs")
	}
	return path + "/" + url.PathEscape(guide), nil
}

func optionalTime(value *string) bool { return value == nil || validTime(*value) }

// ValidUUID reports whether a command argument is a UUID selector.
func ValidUUID(value string) bool { return validUUID(value) }

// SameUUID compares two UUID selectors by value, not spelling.
func SameUUID(left, right string) bool { return sameUUID(left, right) }

// ProjectGuides lists a project's guide versions by creation order.
func (c *Client) ProjectGuides(ctx context.Context, project string, q PageQuery) (Result[ProjectGuidePage], error) {
	var result Result[ProjectGuidePage]
	if q.ProjectID != nil || q.TaskID != nil || q.State != nil || q.UpdatedSince != nil || q.Outcome != nil {
		return result, errors.New("guides accept only --status")
	}
	if q.Status != nil && !oneOf(*q.Status, guideStatuses...) {
		return result, errors.New("--status must be " + strings.Join(guideStatuses, ", "))
	}
	path, err := projectReadPath(project, "/guides")
	if err != nil {
		return result, err
	}
	query, err := q.encodeWith(guideStatuses)
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, path, query, q.Limit)
	if err != nil {
		return result, err
	}
	value := ProjectGuidePage{Items: make([]ProjectGuideSummary, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &value.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		var guide ProjectGuideSummary
		itemFields, err := contextObject(item, &guide, []string{"guide_id", "version", "status", "created_at"}, nil)
		id, valid := uuidIdentity(guide.GuideID)
		if err != nil || !requiredNullable(itemFields, "effective_at") || !valid || seen[id] || guide.Version == "" ||
			!oneOf(guide.Status, guideStatuses...) || (q.Status != nil && guide.Status != *q.Status) ||
			!validTime(guide.CreatedAt) || !optionalTime(guide.EffectiveAt) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		value.Items = append(value.Items, guide)
	}
	return Result[ProjectGuidePage]{Raw: raw, Value: value}, nil
}

func validGuideRecord(raw json.RawMessage, value *ProjectGuideRecord, project, guide string) bool {
	fields, err := contextObject(raw, value, []string{"guide_id", "project_id", "version", "status", "created_by", "created_at", "updated_at"}, nil)
	activated := value.ActivationOperationID != nil
	return err == nil && requiredNullable(fields, "change_summary", "task_examples_hash", "contribution_policy_id",
		"contribution_policy_version_id", "activation_operation_id", "approved_by", "effective_at", "superseded_at") &&
		sameUUID(value.GuideID, guide) && sameUUID(value.ProjectID, project) && value.Version != "" &&
		oneOf(value.Status, guideStatuses...) && value.CreatedBy != "" &&
		validTime(value.CreatedAt) && validTime(value.UpdatedAt) && optionalTime(value.EffectiveAt) && optionalTime(value.SupersededAt) &&
		(value.TaskExamplesHash == nil || policyHash.MatchString(*value.TaskExamplesHash)) &&
		optionalUUID(value.ContributionPolicyID) && optionalUUID(value.ContributionPolicyVersionID) &&
		optionalUUID(value.ActivationOperationID) &&
		(value.ContributionPolicyID != nil) == activated && (value.ContributionPolicyVersionID != nil) == activated
}

func validGuideDocuments(raw json.RawMessage, documents []ProjectGuideDocument) bool {
	var entries []json.RawMessage
	if json.Unmarshal(raw, &entries) != nil || entries == nil || len(entries) != len(documents) || len(entries) > 100 {
		return false
	}
	seen := map[[16]byte]bool{}
	previous := big.NewInt(-1)
	for index, entry := range entries {
		var d ProjectGuideDocument
		fields, err := contextObject(entry, &d, []string{"document_id", "label", "media_type", "order", "ingest_state"}, nil)
		id, valid := uuidIdentity(d.DocumentID)
		uploaded := d.IngestState == "uploaded"
		if err != nil || !requiredNullable(fields, "sha256", "byte_count") || !valid || seen[id] ||
			strings.TrimSpace(d.Label) == "" || (TaskGuideDocument{MediaType: d.MediaType}).Extension() == "" ||
			d.Order == nil || d.Order.Cmp(previous) <= 0 || !oneOf(d.IngestState, "awaiting_upload", "uploaded") ||
			(d.SHA256 != nil) != uploaded || (d.ByteCount != nil) != uploaded ||
			(uploaded && (!policyHash.MatchString(*d.SHA256) || d.ByteCount.Sign() <= 0)) {
			return false
		}
		seen[id] = true
		previous = d.Order
		documents[index] = d
	}
	return true
}

func validReviewValues(raw json.RawMessage, value *GuideReviewPolicyValues) bool {
	fields, err := contextObject(raw, value, []string{"policy_id", "generation", "policy_hash", "human_review_required",
		"semantics_format", "semantics_status", "allowed_decisions", "minimum_finding_fields", "created_at"},
		[]string{"allowed_decisions", "minimum_finding_fields"})
	if err != nil || !requiredNullable(fields, "supersedes_policy_id", "review_preference_window_seconds",
		"review_lease_duration_seconds", "max_active_review_leases_per_reviewer", "self_review_allowed", "reject_policy",
		"finding_evidence_requirement") || !validUUID(value.PolicyID) || value.Generation == nil || value.Generation.Sign() <= 0 ||
		!policyHash.MatchString(value.PolicyHash) || !oneOf(value.SemanticsFormat, "v1", "v2") ||
		!oneOf(value.SemanticsStatus, "complete", "legacy_incomplete") || !optionalUUID(value.SupersedesPolicyID) ||
		!validTime(value.CreatedAt) || (value.SemanticsFormat == "v1" && !value.HumanReviewRequired) {
		return false
	}
	for _, decision := range value.AllowedDecisions {
		if !oneOf(decision, "accept", "needs_revision", "reject") {
			return false
		}
	}
	return true
}

func validRevisionValues(raw json.RawMessage, value *GuideRevisionPolicyValues) bool {
	fields, err := contextObject(raw, value, []string{"policy_id", "generation", "policy_hash", "semantics_status",
		"max_revision_rounds", "revision_deadline_hours", "allowed_resubmission_states", "created_at"},
		[]string{"allowed_resubmission_states"})
	return err == nil && requiredNullable(fields, "supersedes_policy_id", "reviewer_reassignment_rule") &&
		validUUID(value.PolicyID) && value.Generation != nil && value.Generation.Sign() > 0 &&
		policyHash.MatchString(value.PolicyHash) && oneOf(value.SemanticsStatus, "complete", "legacy_incomplete") &&
		optionalUUID(value.SupersedesPolicyID) && nonNegative(value.MaxRevisionRounds) &&
		value.RevisionDeadlineHours != nil && value.RevisionDeadlineHours.Sign() > 0 && validTime(value.CreatedAt)
}

// ProjectGuide reads one guide with its declared documents, selected policies and setup lineage.
func (c *Client) ProjectGuide(ctx context.Context, project, guide string) (Result[ProjectGuideDetail], error) {
	var result Result[ProjectGuideDetail]
	path, err := guidePath(project, guide)
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, "", nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	var value ProjectGuideDetail
	fields, err := contextObject(raw, &value, []string{"guide", "documents"}, nil)
	if err != nil || !requiredNullable(fields, "review_policy", "revision_policy", "latest_setup_run_id", "latest_compilation_id") ||
		!validGuideRecord(fields["guide"], &value.Guide, project, guide) ||
		!validGuideDocuments(fields["documents"], value.Documents) ||
		(value.ReviewPolicy != nil && !validReviewValues(fields["review_policy"], value.ReviewPolicy)) ||
		(value.RevisionPolicy != nil && !validRevisionValues(fields["revision_policy"], value.RevisionPolicy)) ||
		(value.Guide.Status != "draft" && (value.ReviewPolicy == nil || value.RevisionPolicy == nil)) ||
		!optionalUUID(value.LatestSetupRunID) || !optionalUUID(value.LatestCompilationID) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ProjectGuideDetail]{Raw: raw, Value: value}, nil
}

func validActivationCondition(raw json.RawMessage, value *GuideActivationCondition) bool {
	_, err := contextObject(raw, value, []string{"code", "reason", "message", "missing_capabilities"}, nil)
	expected, known := activationReasonCodes[value.Reason]
	if err != nil || !known || !oneOf(value.Code, "proposal_unavailable", "proposal_stale", "approval_blocked") ||
		(expected != "" && value.Code != expected) || strings.TrimSpace(value.Message) == "" ||
		value.MissingCapabilities == nil || len(value.MissingCapabilities) > 200 ||
		(len(value.MissingCapabilities) > 0) != (value.Reason == "checker_capability_missing") {
		return false
	}
	for _, capability := range value.MissingCapabilities {
		if !capabilityRequirement.MatchString(capability.RequirementID) ||
			!oneOf(capability.Stage, "pre_submit", "post_submit") || strings.TrimSpace(capability.Title) == "" {
			return false
		}
	}
	return true
}

// GuideActivationReadiness dry-runs activation over the current selections; nothing is written.
func (c *Client) GuideActivationReadiness(ctx context.Context, project, guide string) (Result[GuideActivationReadiness], error) {
	var result Result[GuideActivationReadiness]
	path, err := guidePath(project, guide)
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path+"/activation-readiness", "", nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	var value GuideActivationReadiness
	fields, err := contextObject(raw, &value, []string{"project_id", "guide_id", "ready", "unmet"}, nil)
	var entries []json.RawMessage
	if err != nil || json.Unmarshal(fields["unmet"], &entries) != nil || entries == nil || len(entries) != len(value.Unmet) ||
		!sameUUID(value.ProjectID, project) || !sameUUID(value.GuideID, guide) ||
		value.Ready != (len(value.Unmet) == 0) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for index, entry := range entries {
		if !validActivationCondition(entry, &value.Unmet[index]) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	return Result[GuideActivationReadiness]{Raw: raw, Value: value}, nil
}

// DownloadProjectGuideDocument verifies an uploaded original against the
// SHA-256 and size the guide read declared. The caller writes privately and
// publishes only after every byte is verified.
func (c *Client) DownloadProjectGuideDocument(ctx context.Context, project, guide string, document ProjectGuideDocument, target io.Writer) error {
	path, err := guidePath(project, guide)
	if err != nil || !validUUID(document.DocumentID) || document.IngestState != "uploaded" || document.SHA256 == nil ||
		!policyHash.MatchString(*document.SHA256) || document.ByteCount == nil || !document.ByteCount.IsInt64() ||
		document.ByteCount.Sign() <= 0 || document.ByteCount.Int64() > MaxGuideDocumentBytes ||
		(TaskGuideDocument{MediaType: document.MediaType}).Extension() == "" {
		return &Failure{Code: "invalid_api_response"}
	}
	size := document.ByteCount.Int64()
	response, err := c.openRequest(ctx, c.guideHTTP, http.MethodGet,
		path+"/documents/"+canonicalUUID(document.DocumentID)+"/content", "", nil, "", document.MediaType)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		body, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
		if err != nil || len(body) > maxResponseBytes {
			return &Failure{Code: "invalid_api_response", Status: response.StatusCode}
		}
		return c.responseFailure(http.MethodGet, response, body)
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != document.MediaType ||
		response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity" ||
		response.ContentLength >= 0 && response.ContentLength != size {
		return &Failure{Code: "guide_document_integrity_mismatch"}
	}
	digest := sha256.New()
	count, err := io.Copy(io.MultiWriter(target, digest), io.LimitReader(response.Body, size+1))
	if err != nil {
		return &Failure{Code: "guide_document_download_failed"}
	}
	if count != size || "sha256:"+hex.EncodeToString(digest.Sum(nil)) != *document.SHA256 {
		return &Failure{Code: "guide_document_integrity_mismatch"}
	}
	return nil
}
